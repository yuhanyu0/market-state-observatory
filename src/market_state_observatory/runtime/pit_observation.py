from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .alpaca_adapter import PointCapture, SymbolCapture, parse_utc
from .stream_store import CrossSectionFreeze


def _record_known_at_freeze(record: dict[str, Any] | None, freeze: datetime) -> bool:
    if not record:
        return False
    return parse_utc(str(record["observed_at_utc"])) <= freeze


def _provider_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("provider_payload", {})
    return payload if isinstance(payload, dict) else {}


def _clock_fields(record: dict[str, Any], freeze: datetime) -> dict[str, Any]:
    observed = parse_utc(str(record["observed_at_utc"]))
    event = parse_utc(str(record["event_time_utc"]))
    return {
        "provider_event_time_utc": event.isoformat(),
        "collector_observed_at_utc": observed.isoformat(),
        "received_age_seconds": max(0.0, (freeze - observed).total_seconds()),
        "provider_event_age_seconds": (freeze - event).total_seconds(),
        "freshness_age_seconds": max(0.0, (freeze - event).total_seconds()),
        "provider_clock_ahead_seconds": max(0.0, (event - observed).total_seconds()),
    }


def _quote_field(record: dict[str, Any] | None, freeze: datetime) -> dict[str, Any]:
    if not record:
        return {"status": "MISSING", "source": "websocket_sip"}
    if not _record_known_at_freeze(record, freeze):
        return {"status": "POST_FREEZE_REJECTED", "source": "websocket_sip"}
    payload = _provider_payload(record)
    try:
        bid = float(payload["bp"])
        ask = float(payload["ap"])
    except (KeyError, TypeError, ValueError):
        return {"status": "INVALID", "source": "websocket_sip", **_clock_fields(record, freeze)}
    mid = (bid + ask) / 2
    freshness = max(0.0, (freeze - parse_utc(str(record["event_time_utc"]))).total_seconds())
    status = (
        "READY"
        if bid > 0 and ask > 0 and bid <= mid <= ask and freshness <= 60
        else "STALE" if freshness > 60 else "INVALID"
    )
    return {
        "status": status,
        "source": "websocket_sip",
        **_clock_fields(record, freeze),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "quoted_spread": ask - bid,
    }


def _trade_field(record: dict[str, Any] | None, freeze: datetime) -> dict[str, Any]:
    if not record:
        return {"status": "MISSING", "source": "websocket_sip"}
    if not _record_known_at_freeze(record, freeze):
        return {"status": "POST_FREEZE_REJECTED", "source": "websocket_sip"}
    payload = _provider_payload(record)
    try:
        price = float(payload["p"])
    except (KeyError, TypeError, ValueError):
        return {"status": "INVALID", "source": "websocket_sip", **_clock_fields(record, freeze)}
    return {
        "status": "READY" if price > 0 else "INVALID",
        "source": "websocket_sip",
        **_clock_fields(record, freeze),
        "price": price,
    }


def _bar_field(
    record: dict[str, Any] | None,
    freeze: datetime,
    scheduled: datetime,
    observation_point: str,
) -> dict[str, Any]:
    if observation_point == "open_snapshot":
        return {"status": "NOT_YET_DEFINED", "source": "websocket_sip"}
    if not record:
        return {"status": "MISSING", "source": "websocket_sip"}
    if not _record_known_at_freeze(record, freeze):
        return {"status": "POST_FREEZE_REJECTED", "source": "websocket_sip"}
    event = parse_utc(str(record["event_time_utc"]))
    if event + timedelta(minutes=1) > scheduled:
        return {
            "status": "INCOMPLETE_AT_CUTOFF",
            "source": "websocket_sip",
            **_clock_fields(record, freeze),
        }
    payload = _provider_payload(record)
    required = ("o", "h", "l", "c", "v")
    if any(key not in payload for key in required):
        return {"status": "INVALID", "source": "websocket_sip", **_clock_fields(record, freeze)}
    return {
        "status": "READY",
        "source": "websocket_sip",
        **_clock_fields(record, freeze),
        "open": float(payload["o"]),
        "high": float(payload["h"]),
        "low": float(payload["l"]),
        "close": float(payload["c"]),
        "volume": float(payload["v"]),
        "completed_at_utc": (event + timedelta(minutes=1)).isoformat(),
    }


RECONCILIATION_TOLERANCE_VERSION = "rest-reconciliation-v2"
RECONCILIATION_TIME_TOLERANCE_SECONDS = 2.0
RECONCILIATION_PRICE_TOLERANCE_BPS = 1.0


def _reconciliation_detail(
    primary: dict[str, Any],
    rest: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    if primary.get("status") != "READY":
        return {
            "status": "PRIMARY_NOT_READY",
            "price_difference": None,
            "time_difference_seconds": None,
        }
    if rest is None:
        return {
            "status": "REST_UNAVAILABLE",
            "price_difference": None,
            "time_difference_seconds": None,
        }
    price_keys = tuple(key for key in keys if key != "volume")
    if any(primary.get(key) is None or rest.get(key) is None for key in price_keys):
        return {
            "status": "REST_UNAVAILABLE",
            "price_difference": None,
            "time_difference_seconds": None,
        }
    differences = [abs(float(primary[key]) - float(rest[key])) for key in price_keys]
    price_difference = max(differences, default=0.0)
    reference = max(
        [abs(float(primary[key])) for key in price_keys]
        + [abs(float(rest[key])) for key in price_keys],
        default=0.0,
    )
    price_tolerance = max(0.0001, reference * RECONCILIATION_PRICE_TOLERANCE_BPS / 10_000)
    primary_time = primary.get("provider_event_time_utc")
    rest_time = rest.get("event_time_utc")
    time_difference = (
        abs((parse_utc(str(primary_time)) - parse_utc(str(rest_time))).total_seconds())
        if primary_time and rest_time
        else None
    )
    if price_difference <= price_tolerance and (
        time_difference is None
        or time_difference <= RECONCILIATION_TIME_TOLERANCE_SECONDS
    ):
        status = "MATCH_WITHIN_TOLERANCE"
    elif (
        time_difference is not None
        and time_difference > RECONCILIATION_TIME_TOLERANCE_SECONDS
    ):
        status = "ASYNC_EXPECTED"
    else:
        status = "MATERIAL_DIFFERENCE"
    return {
        "status": status,
        "price_difference": price_difference,
        "time_difference_seconds": time_difference,
    }


def _rest_reconciliation(
    quote: dict[str, Any],
    trade: dict[str, Any],
    bar: dict[str, Any],
    rest: SymbolCapture | None,
) -> dict[str, Any]:
    if rest is None:
        return {
            "source": "rest_sip",
            "role": "backup_reconciliation_and_derived_features_only",
            "retrieved_at_utc": None,
            "quote_match_status": "REST_UNAVAILABLE",
            "trade_match_status": "REST_UNAVAILABLE",
            "minute_bar_match_status": "REST_UNAVAILABLE",
            "rest_quote_status": "UNAVAILABLE",
            "rest_trade_status": "UNAVAILABLE",
            "rest_bar_status": "UNAVAILABLE",
            "tolerance_version": RECONCILIATION_TOLERANCE_VERSION,
            "quote_price_difference": None,
            "quote_time_difference_seconds": None,
            "trade_price_difference": None,
            "trade_time_difference_seconds": None,
            "minute_bar_price_difference": None,
            "minute_bar_time_difference_seconds": None,
        }
    quote_detail = _reconciliation_detail(quote, rest.quote, ("bid", "ask"))
    trade_detail = _reconciliation_detail(trade, rest.last_trade, ("price",))
    bar_detail = _reconciliation_detail(
        bar, rest.minute_bar, ("open", "high", "low", "close", "volume")
    )
    return {
        "source": "rest_sip",
        "role": "backup_reconciliation_and_derived_features_only",
        "retrieved_at_utc": rest.rest_observed_at_utc,
        "quote_match_status": quote_detail["status"],
        "trade_match_status": trade_detail["status"],
        "minute_bar_match_status": bar_detail["status"],
        "quote_price_difference": quote_detail["price_difference"],
        "quote_time_difference_seconds": quote_detail["time_difference_seconds"],
        "trade_price_difference": trade_detail["price_difference"],
        "trade_time_difference_seconds": trade_detail["time_difference_seconds"],
        "minute_bar_price_difference": bar_detail["price_difference"],
        "minute_bar_time_difference_seconds": bar_detail["time_difference_seconds"],
        "tolerance_version": RECONCILIATION_TOLERANCE_VERSION,
        "rest_quote_status": rest.quote_status,
        "rest_trade_status": rest.trade_status,
        "rest_bar_status": rest.bar_status,
    }


def _session_range_field(
    rest: SymbolCapture | None,
    quote: dict[str, Any],
    trade: dict[str, Any],
    observation_point: str,
) -> dict[str, Any]:
    base = {
        "source": "rest_sip_completed_bars_plus_primary_pit",
        "included_interval_start_utc": rest.included_interval_start_utc if rest else None,
        "included_interval_end_utc": rest.included_interval_end_utc if rest else None,
        "retrieved_at_utc": rest.rest_observed_at_utc if rest else None,
    }
    if observation_point == "open_snapshot":
        return {"status": "NOT_YET_DEFINED", "high": None, "low": None, **base}
    if rest is None or rest.session_high is None or rest.session_low is None:
        return {"status": "MISSING", "high": None, "low": None, **base}
    high = float(rest.session_high)
    low = float(rest.session_low)
    current_price = (
        float(trade["price"])
        if trade.get("status") == "READY" and trade.get("price") is not None
        else float(quote["mid"])
        if quote.get("status") in {"READY", "STALE"} and quote.get("mid") is not None
        else None
    )
    if current_price is not None:
        high = max(high, current_price)
        low = min(low, current_price)
    status = "READY" if high > low else "MISSING"
    return {"status": status, "high": high, "low": low, **base}


def build_point_payload(
    capture: PointCapture,
    cross_section: CrossSectionFreeze,
    rest_snapshot_backup_sha256: str | None,
) -> dict[str, Any]:
    freeze = parse_utc(cross_section.freeze_completed_at_utc)
    scheduled = parse_utc(cross_section.scheduled_at_utc)
    rest_by_symbol = {row.symbol: row for row in capture.symbols}
    rows: list[dict[str, Any]] = []
    post_freeze_count = 0
    provider_ahead: list[float] = []
    for symbol in sorted(cross_section.latest_state):
        state = cross_section.latest_state[symbol]
        quote = _quote_field(state.get("q"), freeze)
        trade = _trade_field(state.get("t"), freeze)
        bar = _bar_field(state.get("b"), freeze, scheduled, capture.observation_point)
        for field in (quote, trade, bar):
            if field["status"] == "POST_FREEZE_REJECTED":
                post_freeze_count += 1
            ahead = field.get("provider_clock_ahead_seconds")
            if ahead is not None:
                provider_ahead.append(float(ahead))
        rest = rest_by_symbol.get(symbol)
        state_present = any(
            _record_known_at_freeze(record, freeze) for record in state.values()
        )
        rows.append(
            {
                "symbol": symbol,
                "observation_status": "CAPTURED" if state_present else "PRIMARY_STATE_MISSING",
                "primary_pit_source": "websocket_sip",
                "quote": quote,
                "last_trade": trade,
                "minute_bar": bar,
                "vwap": {
                    "status": rest.vwap_status if rest else "UNAVAILABLE",
                    "source": "rest_sip_completed_bars",
                    "value": rest.vwap if rest else None,
                    "cumulative_volume": rest.cumulative_volume if rest else None,
                    "included_interval_start_utc": (
                        rest.included_interval_start_utc if rest else None
                    ),
                    "included_interval_end_utc": rest.included_interval_end_utc if rest else None,
                    "retrieved_at_utc": rest.rest_observed_at_utc if rest else None,
                },
                "session_range": _session_range_field(
                    rest, quote, trade, capture.observation_point
                ),
                "rest_reconciliation": _rest_reconciliation(quote, trade, bar, rest),
            }
        )
    return {
        "schema_version": "mso-private-observation-point-v3",
        "observation_point": capture.observation_point,
        "scheduled_at_utc": cross_section.scheduled_at_utc,
        "freeze_started_at_utc": cross_section.freeze_started_at_utc,
        "freeze_completed_at_utc": cross_section.freeze_completed_at_utc,
        "freeze_duration_seconds": cross_section.freeze_duration_seconds,
        "earliest_event_time_utc": cross_section.earliest_event_time_utc,
        "latest_event_time_utc": cross_section.latest_event_time_utc,
        "event_time_dispersion_seconds": cross_section.event_time_dispersion_seconds,
        "stream_symbols_requested": cross_section.symbols_requested,
        "stream_symbols_present": cross_section.symbols_present,
        "pit_primary_source": "websocket_sip",
        "rest_role": "backup_reconciliation_and_derived_features_only",
        "captured_at_utc": capture.captured_at_utc,
        "symbols": rows,
        "raw_request_ids": [result.collector_request_id for result in capture.raw_results],
        "rest_snapshot_backup_sha256": rest_snapshot_backup_sha256,
        "rest_capture_status": "AVAILABLE" if rest_by_symbol else "UNAVAILABLE",
        "future_timestamp_count": post_freeze_count,
        "post_freeze_primary_record_count": post_freeze_count,
        "provider_clock_ahead_record_count": sum(value > 0 for value in provider_ahead),
        "provider_clock_ahead_seconds_max": max(provider_ahead, default=0.0),
        "backfilled": False,
        "data_ready_only": True,
        "model_estimated": False,
        "decision_eligible": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
