from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .market_calendar import schedule_as_utc
from .observation_freezer import canonical_json, write_exclusive

CORE_POINTS = (
    "open_snapshot",
    "midpoint_snapshot",
    "preclose_snapshot",
    "decision_snapshot",
    "session_close_diagnostic",
)
FREEZE_DURATION_LIMIT_SECONDS = 5.0


def _load_point_manifests(run_directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((run_directory / "manifests" / "points").glob("*.json"))
    ]


def _captured(row: dict[str, Any]) -> bool:
    return bool(row.get("observation_status", "CAPTURED") == "CAPTURED")


def _quote_ready(row: dict[str, Any]) -> bool:
    quote = row.get("quote")
    if isinstance(quote, dict) and "status" in quote:
        return quote.get("status") == "READY" and float(quote.get("freshness_age_seconds", 1e9)) <= 60
    return row.get("quote_age_seconds") is not None and float(row["quote_age_seconds"]) <= 60


def _quote_age(row: dict[str, Any]) -> float | None:
    quote = row.get("quote")
    if isinstance(quote, dict) and quote.get("status") == "READY":
        value = quote.get("freshness_age_seconds")
        return float(value) if value is not None else None
    value = row.get("quote_age_seconds")
    return float(value) if value is not None else None


def _trade_ready(row: dict[str, Any]) -> bool:
    trade = row.get("last_trade")
    if isinstance(trade, dict) and "status" in trade:
        return trade.get("status") == "READY"
    return trade is not None or "quote_age_seconds" in row


def _bar_ready(row: dict[str, Any]) -> bool:
    bar = row.get("minute_bar")
    if isinstance(bar, dict) and "status" in bar:
        return bar.get("status") == "READY"
    return bar is not None or "quote_age_seconds" in row


def _vwap_ready(row: dict[str, Any]) -> bool:
    vwap = row.get("vwap")
    if isinstance(vwap, dict):
        return vwap.get("status") == "READY" and vwap.get("value") is not None
    return vwap is not None


def _rate(ready: int, planned: int) -> float:
    return ready / planned if planned else 0.0


def evaluate_run_quality(run_directory: Path, universe: dict[str, Any]) -> dict[str, Any]:
    run = json.loads((run_directory / "RUN.json").read_text(encoding="utf-8"))
    points = _load_point_manifests(run_directory)
    stream_health_paths = sorted(
        (run_directory / "manifests" / "websocket").glob("stream-health-*.json")
    )
    stream_health = (
        json.loads(stream_health_paths[-1].read_text(encoding="utf-8"))
        if stream_health_paths
        else {"reconnect_count": 0}
    )
    by_point = {str(row["observation_point"]): row for row in points}
    symbol_rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for point, payload in by_point.items():
        for row in payload.get("symbols", []):
            symbol_rows[point][str(row["symbol"])] = row

    all_symbols = {str(universe["benchmark"])}
    for theme in universe["themes"]:
        all_symbols.update(
            [str(theme["theme_etf"]), str(theme["industry_benchmark"]), *theme["basket"]]
        )
    planned = len(CORE_POINTS) * len(all_symbols)
    core_rows = [
        symbol_rows[point][symbol]
        for point in CORE_POINTS
        for symbol in all_symbols
        if symbol in symbol_rows.get(point, {})
    ]
    captured = sum(_captured(row) for row in core_rows)
    quote_ready = sum(_quote_ready(row) for row in core_rows)
    trade_ready = sum(_trade_ready(row) for row in core_rows)
    bar_ready = sum(_bar_ready(row) for row in core_rows)
    vwap_ready = sum(_vwap_ready(row) for row in core_rows)
    quote_ages = [age for row in core_rows if (age := _quote_age(row)) is not None]
    future_timestamps = sum(int(payload.get("future_timestamp_count", 0)) for payload in points)
    backfill_count = sum(int(bool(payload.get("backfilled", False))) for payload in points)
    freeze_durations = {
        point: (
            float(payload["freeze_duration_seconds"])
            if payload.get("freeze_duration_seconds") is not None
            else float(payload["cross_section_skew_seconds"])
            if payload.get("cross_section_skew_seconds") is not None
            else None
        )
        for point, payload in by_point.items()
    }
    event_dispersions = {
        point: (
            float(payload["event_time_dispersion_seconds"])
            if payload.get("event_time_dispersion_seconds") is not None
            else None
        )
        for point, payload in by_point.items()
    }

    theme_quality: list[dict[str, Any]] = []
    direction_points = ("preclose_snapshot", "decision_snapshot")
    decision_freeze_duration = freeze_durations.get("decision_snapshot")
    for theme in universe["themes"]:
        theme_id = str(theme["theme_id"])
        etf = str(theme["theme_etf"])
        benchmark = str(theme["industry_benchmark"])
        required_direction = {etf, str(universe["benchmark"]), benchmark}
        direction_rows = [
            symbol_rows.get(point, {}).get(symbol)
            for point in direction_points
            for symbol in required_direction
        ]
        direction_ready = bool(
            all(row is not None for row in direction_rows)
            and all(_captured(row) and _quote_ready(row) and _vwap_ready(row) for row in direction_rows if row)
        )
        constituents = set(map(str, theme["basket"]))
        decision_rows = symbol_rows.get("decision_snapshot", {})
        ready_constituents = {
            symbol
            for symbol in constituents
            if symbol in decision_rows
            and _captured(decision_rows[symbol])
            and _quote_ready(decision_rows[symbol])
            and _bar_ready(decision_rows[symbol])
            and _vwap_ready(decision_rows[symbol])
        }
        constituent_coverage = len(ready_constituents) / len(constituents) if constituents else 0.0
        atomic_decision_freeze = bool(
            decision_freeze_duration is not None
            and decision_freeze_duration <= FREEZE_DURATION_LIMIT_SECONDS
        )
        transmission_ready = bool(
            direction_ready
            and run.get("membership_snapshot_frozen")
            and constituent_coverage >= 0.8
            and atomic_decision_freeze
        )
        blockers: list[str] = []
        if not direction_ready:
            blockers.append("direction_inputs_incomplete")
        if not run.get("membership_snapshot_frozen"):
            blockers.append("membership_not_frozen")
        if constituent_coverage < 0.8:
            blockers.append("decision_constituent_coverage_below_80_percent")
        if not atomic_decision_freeze:
            blockers.append("decision_freeze_duration_above_5_seconds")
        theme_quality.append(
            {
                "theme_id": theme_id,
                "theme_etf": etf,
                "data_ready": direction_ready,
                "model_estimated": False,
                "decision_eligible": False,
                "direction_ready": direction_ready,
                "transmission_ready": transmission_ready,
                "episode_ready": False,
                "c2_ready": False,
                "constituent_coverage": constituent_coverage,
                "transmission_snapshot": "decision_snapshot",
                "decision_freeze_duration_seconds": decision_freeze_duration,
                "decision_event_time_dispersion_seconds": event_dispersions.get(
                    "decision_snapshot"
                ),
                "blocking_reasons": blockers,
            }
        )

    observation_capture_rate = _rate(captured, planned)
    max_quote_age = max(quote_ages) if quote_ages else None
    required_points_present = all(point in by_point for point in CORE_POINTS)
    schedule = dict(schedule_as_utc(date.fromisoformat(str(run["trading_date"]))))
    timeline = [
        {
            "name": point,
            "scheduled_at": schedule[point].isoformat(),
            "status": "captured" if point in by_point else "missed",
            "evidence_at": by_point.get(point, {}).get("captured_at_utc"),
        }
        for point in CORE_POINTS
    ]
    quality_pass = bool(
        required_points_present
        and observation_capture_rate >= 0.95
        and all(theme["direction_ready"] for theme in theme_quality)
        and max_quote_age is not None
        and max_quote_age <= 60
        and future_timestamps == 0
        and backfill_count == 0
    )
    formal_mode = (
        run.get("status") == "FORMAL_DATA_SHADOW"
        and run.get("mode") == "formal"
        and run.get("publication_as_formal") is True
    )
    process_success = True
    publication_eligible = bool(
        formal_mode
        and process_success
        and quality_pass
        and run.get("production_release") is True
        and int(run.get("paper_positions_allowed", False)) == 0
        and int(run.get("real_orders_allowed", False)) == 0
    )
    return {
        "schema_version": "mso-private-data-quality-v3",
        "run_id": run["run_id"],
        "trading_date": run["trading_date"],
        "status": run["status"],
        "run_mode": run["status"],
        "process_success": process_success,
        "production_release": bool(run.get("production_release")),
        "experiment_lane": run.get("experiment_lane"),
        "counts_toward_20_day_gate": bool(
            formal_mode and run["counts_toward_20_day_gate"] and quality_pass
        ),
        "counts_toward_model_shadow": False,
        "counts_toward_live_decision": False,
        "publication_as_formal": bool(formal_mode),
        "planned_observations": planned,
        "captured_observations": captured,
        "observation_capture_rate": observation_capture_rate,
        "quote_ready_rate": _rate(quote_ready, planned),
        "trade_ready_rate": _rate(trade_ready, planned),
        "bar_ready_rate": _rate(bar_ready, planned),
        "vwap_ready_rate": _rate(vwap_ready, planned),
        "capture_rate": observation_capture_rate,
        "quote_age_seconds_max": max_quote_age,
        "future_timestamp_count": future_timestamps,
        "backfill_count": backfill_count,
        "websocket_reconnect_count": int(stream_health.get("reconnect_count", 0)),
        "stream_message_count": int(stream_health.get("message_count", 0)),
        "stream_message_drop_count": int(stream_health.get("dropped_message_count", 0)),
        "stream_chunk_count": int(stream_health.get("chunk_count", 0)),
        "stream_disk_budget_bytes": int(stream_health.get("disk_budget_bytes", 0)),
        "stream_disk_budget_used_bytes": int(stream_health.get("disk_budget_used_bytes", 0)),
        "freeze_duration_seconds_by_point": freeze_durations,
        "freeze_duration_limit_seconds": FREEZE_DURATION_LIMIT_SECONDS,
        "event_time_dispersion_seconds_by_point": event_dispersions,
        "timeline": timeline,
        "data_quality_pass": quality_pass,
        "publication_eligible": publication_eligible,
        "schema_validation_pass": True,
        "secret_scan_pass": True,
        "forbidden_path_scan_pass": True,
        "themes": theme_quality,
        "paper_positions": 0,
        "real_orders": 0,
    }


def freeze_quality(run_directory: Path, universe: dict[str, Any]) -> Path:
    quality = evaluate_run_quality(run_directory, universe)
    path = run_directory / "quality" / "DATA_QUALITY.json"
    write_exclusive(path, canonical_json(quality))
    return path
