from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .redactor import redact_derived_payload


def project_data_quality(private_quality: dict[str, Any]) -> dict[str, Any]:
    themes = []
    for row in private_quality.get("themes", []):
        themes.append(
            {
                "theme_id": row["theme_id"],
                "theme_etf": row["theme_etf"],
                "data_ready": bool(row["data_ready"]),
                "model_estimated": bool(row.get("model_estimated", False)),
                "decision_eligible": bool(row.get("decision_eligible", False)),
                "direction_ready": bool(row["direction_ready"]),
                "transmission_ready": bool(row["transmission_ready"]),
                "episode_ready": bool(row.get("episode_ready", False)),
                "constituent_coverage": round(float(row["constituent_coverage"]), 4),
                "blocking_reasons": list(row.get("blocking_reasons", [])),
            }
        )
    projected = {
        "schema_version": "mso-public-data-quality-v1",
        "published_at_utc": datetime.now(UTC).isoformat(),
        "trading_date": private_quality["trading_date"],
        "runtime_phase": "DATA_SHADOW",
        "data_quality_pass": bool(private_quality["data_quality_pass"]),
        "capture_rate": round(float(private_quality["capture_rate"]), 4),
        "quote_age_seconds_max": private_quality.get("quote_age_seconds_max"),
        "future_timestamp_count": int(private_quality["future_timestamp_count"]),
        "backfill_count": int(private_quality["backfill_count"]),
        "websocket_reconnect_count": int(private_quality.get("websocket_reconnect_count", 0)),
        "counts_toward_20_day_gate": bool(private_quality["counts_toward_20_day_gate"]),
        "counts_toward_model_shadow": False,
        "counts_toward_live_decision": False,
        "themes": themes,
        "paper_positions": 0,
        "real_orders": 0,
        "evidence_boundary": "Derived aggregate state only; no SIP redistribution.",
    }
    return redact_derived_payload(projected)


def project_public_status(
    private_quality: dict[str, Any], valid_data_shadow_days: int
) -> dict[str, Any]:
    published_at = datetime.now(UTC).isoformat()
    formal = private_quality.get("run_mode") == "FORMAL_DATA_SHADOW"
    health = "HEALTHY" if private_quality.get("data_quality_pass") else "DEGRADED"
    timeline = list(private_quality.get("timeline", []))
    captured_at = [row.get("evidence_at") for row in timeline if row.get("evidence_at")]
    last_evidence = max(captured_at) if captured_at else published_at
    next_event = next((row for row in timeline if row.get("status") == "pending"), None)
    capture_rate = float(private_quality.get("capture_rate", 0))
    planned = int(private_quality.get("planned_observations", 0))
    themes = list(private_quality.get("themes", []))
    return redact_derived_payload(
        {
            "schema_version": "market-state-observatory-status-v0.4.1",
            "updated_at": published_at,
            "trading_date": private_quality["trading_date"],
            "last_evidence_at": last_evidence,
            "snapshot_evidence_grade": "prospective_point_in_time",
            "snapshot_kind": "formal" if formal else "rehearsal",
            "health_state": health,
            "runtime_phase": private_quality["run_mode"],
            "next_event": (
                {"name": next_event["name"], "scheduled_at": next_event["scheduled_at"]}
                if next_event
                else None
            ),
            "timeline": timeline,
            "action_required": (
                "No action required; continue the frozen data-only lane."
                if health == "HEALTHY"
                else "Operator review required: latest data quality did not pass."
            ),
            "live_trading_enabled": False,
            "formal_data_shadow_started": formal,
            "model_shadow_started": False,
            "paper_positions": 0,
            "real_orders": 0,
            "data_ready": bool(private_quality.get("data_quality_pass")),
            "model_estimated": False,
            "decision_eligible": False,
            "data_shadow_gate": {"valid_days": valid_data_shadow_days, "required_days": 20},
            "quality": {
                "planned": planned,
                "captured": int(private_quality.get("captured_observations", 0)),
                "missed": max(0, planned - int(private_quality.get("captured_observations", 0))),
                "future_timestamps": int(private_quality.get("future_timestamp_count", 0)),
                "backfill": int(private_quality.get("backfill_count", 0)),
                "websocket_reconnects": int(private_quality.get("websocket_reconnect_count", 0)),
                "ticker_coverage": capture_rate,
                "theme_coverage": sum(bool(theme.get("data_ready")) for theme in themes),
                "missing_tickers": [],
            },
            "next_milestone": "Continue point-in-time data collection; models and decisions remain disabled.",
        }
    )
