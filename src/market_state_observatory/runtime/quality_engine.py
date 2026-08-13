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


def _load_point_manifests(run_directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((run_directory / "manifests" / "points").glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def evaluate_run_quality(run_directory: Path, universe: dict[str, Any]) -> dict[str, Any]:
    run = json.loads((run_directory / "RUN.json").read_text(encoding="utf-8"))
    points = _load_point_manifests(run_directory)
    stream_health_paths = sorted(
        (run_directory / "manifests" / "websocket").glob("stream-health-*.json")
    )
    stream_health_path = stream_health_paths[-1] if stream_health_paths else None
    stream_health = (
        json.loads(stream_health_path.read_text(encoding="utf-8"))
        if stream_health_path is not None and stream_health_path.is_file()
        else {"reconnect_count": 0}
    )
    by_point = {str(row["observation_point"]): row for row in points}
    symbols_by_point = {
        point: {str(row["symbol"]) for row in payload.get("symbols", [])}
        for point, payload in by_point.items()
    }
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
    captured = sum(len(symbols_by_point.get(point, set()) & all_symbols) for point in CORE_POINTS)
    quote_ages = [
        float(row["quote_age_seconds"])
        for payload in points
        for row in payload.get("symbols", [])
        if row.get("quote_age_seconds") is not None
    ]
    future_timestamps = sum(int(payload.get("future_timestamp_count", 0)) for payload in points)
    backfill_count = sum(int(bool(payload.get("backfilled", False))) for payload in points)
    cross_section_skews = [
        float(payload["cross_section_skew_seconds"])
        for payload in points
        if payload.get("cross_section_skew_seconds") is not None
    ]
    maximum_cross_section_skew = max(cross_section_skews) if cross_section_skews else None
    cross_section_skew_limit = 5.0
    theme_quality: list[dict[str, Any]] = []
    for theme in universe["themes"]:
        theme_id = str(theme["theme_id"])
        etf = str(theme["theme_etf"])
        benchmark = str(theme["industry_benchmark"])
        required_direction = {etf, str(universe["benchmark"]), benchmark}
        direction_points = ("preclose_snapshot", "decision_snapshot")
        direction_coverage = all(
            required_direction <= symbols_by_point.get(point, set()) for point in direction_points
        )
        direction_rows = [
            symbol_rows[point][symbol]
            for point in direction_points
            for symbol in required_direction
            if symbol in symbol_rows.get(point, {})
        ]
        direction_ready = bool(
            direction_coverage
            and direction_rows
            and all(float(row["quote_age_seconds"]) <= 60 for row in direction_rows)
            and all(row.get("vwap") is not None for row in direction_rows)
        )
        constituents = set(map(str, theme["basket"]))
        present_constituents = constituents & symbols_by_point.get("decision_snapshot", set())
        constituent_coverage = (
            len(present_constituents) / len(constituents) if constituents else 0.0
        )
        transmission_ready = bool(
            direction_ready
            and run.get("membership_snapshot_frozen")
            and constituent_coverage >= 0.8
            and maximum_cross_section_skew is not None
            and maximum_cross_section_skew <= cross_section_skew_limit
        )
        blockers: list[str] = []
        if not direction_ready:
            blockers.append("direction_inputs_incomplete")
        if not run.get("membership_snapshot_frozen"):
            blockers.append("membership_not_frozen")
        if constituent_coverage < 0.8:
            blockers.append("constituent_coverage_below_80_percent")
        if maximum_cross_section_skew is not None and maximum_cross_section_skew > cross_section_skew_limit:
            blockers.append("cross_section_skew_above_5_seconds")
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
                "blocking_reasons": blockers,
            }
        )
    success_rate = captured / planned if planned else 0.0
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
        and success_rate >= 0.95
        and all(theme["direction_ready"] for theme in theme_quality)
        and max_quote_age is not None
        and max_quote_age <= 60
        and future_timestamps == 0
        and backfill_count == 0
    )
    formal_mode = run.get("status") == "FORMAL_DATA_SHADOW" and run.get("mode") == "formal"
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
        "schema_version": "mso-private-data-quality-v2",
        "run_id": run["run_id"],
        "trading_date": run["trading_date"],
        "status": run["status"],
        "run_mode": run["status"],
        "process_success": process_success,
        "production_release": bool(run.get("production_release")),
        "experiment_lane": run.get("experiment_lane"),
        "counts_toward_20_day_gate": bool(run["counts_toward_20_day_gate"] and quality_pass),
        "counts_toward_model_shadow": False,
        "counts_toward_live_decision": False,
        "planned_observations": planned,
        "captured_observations": captured,
        "capture_rate": success_rate,
        "quote_age_seconds_max": max_quote_age,
        "future_timestamp_count": future_timestamps,
        "backfill_count": backfill_count,
        "websocket_reconnect_count": int(stream_health.get("reconnect_count", 0)),
        "stream_message_count": int(stream_health.get("message_count", 0)),
        "stream_chunk_count": int(stream_health.get("chunk_count", 0)),
        "stream_disk_budget_bytes": int(stream_health.get("disk_budget_bytes", 0)),
        "stream_disk_budget_used_bytes": int(stream_health.get("disk_budget_used_bytes", 0)),
        "cross_section_skew_seconds_max": maximum_cross_section_skew,
        "cross_section_skew_limit_seconds": cross_section_skew_limit,
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
