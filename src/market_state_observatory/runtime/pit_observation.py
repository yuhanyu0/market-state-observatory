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


def _match_status(primary: dict[str, Any], rest: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    if primary.get("status") != "READY":
        return "PRIMARY_NOT_READY"
    if rest is None:
        return "REST_MISSING"
    return "MATCH" if all(primary.get(key) == rest.get(key) for key in keys) else "DIFFERENT"


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
        }
    return {
        "source": "rest_sip",
        "role": "backup_reconciliation_and_derived_features_only",
        "retrieved_at_utc": rest.rest_observed_at_utc,
        "quote_match_status": _match_status(quote, rest.quote, ("bid", "ask")),
        "trade_match_status": _match_status(trade, rest.last_trade, ("price",)),
        "minute_bar_match_status": _match_status(
            bar, rest.minute_bar, ("open", "high", "low", "close", "volume")
        ),
        "rest_quote_status": rest.quote_status,
        "rest_trade_status": rest.trade_status,
        "rest_bar_status": rest.bar_status,
    }


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
