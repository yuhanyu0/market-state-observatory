from __future__ import annotations

import json
from html import escape
from typing import Any

from market_state_observatory.disagreement import detect_conflicts
from market_state_observatory.next_probe import incident_next_probe, recommend_next_probe
from market_state_observatory.observer_registry import ObserverRegistry

from .candidate_stack import candidate_observer_estimates
from .feature_compiler import POINT_ORDER, CompletedRunFeatureCompiler, feature_index


def _available(index: dict[tuple[str, str, str], dict[str, Any]], theme: str, point: str, feature: str) -> Any:
    row = index.get((theme, point, feature))
    return row.get("value") if row and row.get("availability_status") == "AVAILABLE" else None


def _pct(value: float | None) -> str:
    return "not available" if value is None else f"{value * 100:.2f}%"


def _theme_description(
    theme_id: str,
    index: dict[tuple[str, str, str], dict[str, Any]],
) -> list[str]:
    close = "session_close_diagnostic"
    close_etf = _available(index, theme_id, close, "etf_intraday_return")
    positive = _available(index, theme_id, close, "constituent_positive_breadth")
    negative = _available(index, theme_id, close, "constituent_negative_breadth")
    dispersion = _available(index, theme_id, close, "return_dispersion")
    midpoint = _available(index, theme_id, "midpoint_snapshot", "etf_intraday_return")
    decision = _available(index, theme_id, "decision_snapshot", "etf_intraday_return")
    agreement = _available(index, theme_id, close, "etf_basket_agreement")
    findings: list[str] = []
    if positive is not None and close_etf is not None and positive >= 0.75 and close_etf < 0.002:
        findings.append("Constituent breadth was stronger than the close ETF return.")
    if negative is not None and negative >= 2 / 3:
        findings.append("Constituent breadth was broadly negative at the close.")
    if negative == 1.0 and decision is not None and close_etf is not None and close_etf > decision:
        findings.append("Broad weakness showed partial late repair without reversing sign.")
    if agreement is False:
        findings.append("ETF and basket direction disagreed near the close.")
    if midpoint is not None and close_etf is not None and midpoint > 0 > close_etf:
        findings.append("The intraday path whipsawed and finished with low coherence.")
    if close_etf is not None and close_etf < 0 and dispersion is not None and dispersion > 0.005:
        findings.append("The ETF state was negative while constituent outcomes remained dispersed.")
    if not findings:
        findings.append("Observed structure did not meet a predeclared descriptive exception pattern.")
    return findings


def _descriptive_structure_conflicts(
    theme_id: str,
    index: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    agreement = _available(
        index, theme_id, "session_close_diagnostic", "etf_basket_agreement"
    )
    if agreement is False:
        return [
            {
                "conflict_type": "ETF_BASKET_DIRECTION_DISAGREEMENT",
                "evidence_level": "descriptive_structure",
                "validated_observer_conflict": False,
                "observation_point": "session_close_diagnostic",
            }
        ]
    return []


def _largest_contributors(compiler: CompletedRunFeatureCompiler, theme: dict[str, Any]) -> list[dict[str, Any]]:
    opened = compiler.rows.get("open_snapshot", {})
    closed = compiler.rows.get("session_close_diagnostic", {})

    def price(row: dict[str, Any] | None) -> float | None:
        if not row:
            return None
        trade = row.get("last_trade", {})
        value = trade.get("price")
        return float(value) if value is not None else None

    rows: list[dict[str, Any]] = []
    for symbol in theme["basket"]:
        start, end = price(opened.get(symbol)), price(closed.get(symbol))
        if start not in (None, 0.0) and end is not None:
            rows.append({"symbol": symbol, "intraday_return": end / start - 1})
    return sorted(rows, key=lambda row: abs(float(row["intraday_return"])), reverse=True)[:3]


def build_incident_summary(
    compiler: CompletedRunFeatureCompiler,
    feature_quality: dict[str, Any],
) -> dict[str, Any]:
    stale_by_point: dict[str, int] = {}
    observed_age_by_point: dict[str, float | None] = {}
    ready_age_by_point: dict[str, float | None] = {}
    for point, payload in compiler.points.items():
        ages = [
            float(row["quote"]["freshness_age_seconds"])
            for row in payload.get("symbols", [])
            if row.get("quote", {}).get("freshness_age_seconds") is not None
        ]
        ready = [
            float(row["quote"]["freshness_age_seconds"])
            for row in payload.get("symbols", [])
            if row.get("quote", {}).get("status") == "READY"
            and row.get("quote", {}).get("freshness_age_seconds") is not None
        ]
        stale_by_point[point] = sum(row.get("quote", {}).get("status") == "STALE" for row in payload.get("symbols", []))
        observed_age_by_point[point] = max(ages) if ages else None
        ready_age_by_point[point] = max(ready) if ready else None
    stream_paths = sorted((compiler.run_directory / "manifests" / "websocket").glob("stream-health-*.json"))
    stream = json.loads(stream_paths[-1].read_text(encoding="utf-8")) if stream_paths else {}
    reconnects = int(stream.get("reconnect_count", compiler.quality.get("websocket_reconnect_count", 0)))
    return {
        "schema_version": "mso-incident-summary-v1",
        "run_id": compiler.run["run_id"],
        "connection_gap_count": reconnects,
        "connection_gap_seconds_max": None,
        "connection_gap_overlap_by_observation_point": {point: "UNKNOWN_NO_EVENT_LEDGER" for point in POINT_ORDER if point in compiler.points},
        "stale_quote_count_by_point": stale_by_point,
        "observed_quote_age_max_by_point": observed_age_by_point,
        "ready_quote_age_max_by_point": ready_age_by_point,
        "decision_primary_quote_count": feature_quality["decision_primary_quote_count"],
        "decision_stale_quote_count": feature_quality["decision_stale_quote_count"],
        "stream_message_count": int(stream.get("message_count", compiler.quality.get("stream_message_count", 0))),
        "stream_message_drop_count": int(stream.get("dropped_message_count", compiler.quality.get("stream_message_drop_count", 0))),
        "stream_chunk_count": int(stream.get("chunk_count", compiler.quality.get("stream_chunk_count", 0))),
        "safe_summary": "Historical reconnect count is known; exact gap durations are unavailable because the v0.4.5 run predates the append-only connection-event ledger.",
        "paper_positions": 0,
        "real_orders": 0,
    }


def build_observation_report(
    compiler: CompletedRunFeatureCompiler,
    features: dict[str, Any],
    feature_quality: dict[str, Any],
    incident_summary: dict[str, Any],
    candidate_outputs: dict[str, dict[str, Any]] | None,
    mode_authorization: dict[str, Any],
) -> dict[str, Any]:
    index = feature_index(features)
    stale = int(feature_quality["decision_stale_quote_count"])
    quote_count = int(feature_quality["decision_primary_quote_count"])
    freshness_failure = quote_count > 0 and stale == quote_count
    headline = "NO DECISION / PRIMARY FEED FRESHNESS FAILURE" if freshness_failure else "DESCRIPTIVE OBSERVATION / CANDIDATE OUTPUTS UNVALIDATED"
    themes: list[dict[str, Any]] = []
    registry = ObserverRegistry()
    registry.assert_theme_radar_isolated()
    for theme in compiler.membership["themes"]:
        theme_id = str(theme["theme_id"])
        path = [
            {
                "observation_point": point,
                "etf_intraday_return": _available(index, theme_id, point, "etf_intraday_return"),
                "relative_to_spy": _available(index, theme_id, point, "relative_to_spy_return"),
                "relative_to_industry": _available(index, theme_id, point, "relative_to_industry_return"),
            }
            for point in POINT_ORDER
            if point in compiler.points
        ]
        point = "session_close_diagnostic"
        metrics = {
            name: _available(index, theme_id, point, name)
            for name in (
                "basket_mean_return",
                "basket_median_return",
                "constituent_positive_breadth",
                "constituent_negative_breadth",
                "residual_breadth",
                "volume_coverage",
                "volume_breadth",
                "return_dispersion",
                "single_name_concentration",
                "etf_basket_agreement",
                "vwap_distance",
                "range_position",
                "decision_close_confirmation",
            )
        }
        candidates = candidate_outputs.get(theme_id) if candidate_outputs else None
        conflicts: list[dict[str, Any]] = []
        probe = None
        if candidates:
            estimates = candidate_observer_estimates(
                candidates["direction"], candidates["transmission"], candidates["episode"], candidates["fragility"]
            )
            conflicts = [row.to_dict() for row in detect_conflicts(estimates)]
            probe = recommend_next_probe(theme_id, estimates)
        descriptive_conflicts = _descriptive_structure_conflicts(theme_id, index)
        themes.append(
            {
                "theme_id": theme_id,
                "display_name": theme["display_name"],
                "theme_etf": theme["theme_etf"],
                "etf_path": path,
                "close_structure": metrics,
                "largest_constituent_contributors": _largest_contributors(compiler, theme),
                "descriptive_findings": _theme_description(theme_id, index),
                "descriptive_structure_conflicts": descriptive_conflicts,
                "candidate_observer_conflicts": conflicts,
                "validated_observer_conflicts": [],
                "data_incident_exposure": {
                    "decision_quote_stale": freshness_failure,
                    "decision_observed_quote_age_max": incident_summary["observed_quote_age_max_by_point"].get("decision_snapshot"),
                },
                "next_useful_observation": probe,
                "candidate_outputs": candidates,
            }
        )
    latest_point = compiler.points.get("decision_snapshot") or compiler.run
    probe_deadline = str(
        latest_point.get("scheduled_at_utc")
        or latest_point.get("created_at_utc")
        or compiler.run["created_at_utc"]
    )
    run_probe = incident_next_probe(
        "required_universe",
        "STALE_PRIMARY_FEED"
        if freshness_failure
        else "MISSING_POINT"
        if "decision_snapshot" not in compiler.points
        else "EVENT_PROVENANCE_UNAVAILABLE",
        probe_deadline,
    )
    return {
        "schema_version": "mso-observation-report-v2",
        "run_id": compiler.run["run_id"],
        "trading_date": compiler.run["trading_date"],
        "release_version": compiler.run["release_version"],
        "experiment_lane": compiler.run["experiment_lane"],
        "headline": headline,
        "execution_mode": mode_authorization["mode"],
        "evidence_grade": mode_authorization["evidence_grade"],
        "sections": {
            "A_evidence_validity": {
                "planned": compiler.quality["planned_observations"],
                "captured": compiler.quality["captured_observations"],
                "capture_rate": compiler.quality["observation_capture_rate"],
                "future_timestamp_count": compiler.quality["future_timestamp_count"],
                "backfill_count": compiler.quality["backfill_count"],
            },
            "B_observed_market_facts": {"theme_count": len(themes), "feature_count": feature_quality["feature_count"]},
            "C_descriptive_theme_structure": {"themes": themes},
            "D_candidate_inference_status": {
                "candidate_replay_executed": candidate_outputs is not None,
                "validated_model": False,
                "decision_eligible": False,
            },
            "E_unknown_blocked_claims": [
                "No valid 15:45 Direction certificate can be formed from stale primary quotes." if freshness_failure else "Candidate estimates remain unvalidated.",
                "Episode history is insufficient for a validated state.",
                "Known-at corporate event context is unavailable.",
            ],
            "F_next_useful_observation": run_probe,
            "G_system_health": incident_summary,
            "H_authorization_boundary": {
                **mode_authorization,
                "candidate_outputs_are_validated": False,
                "decision_status": "DATA_BLOCKED_NO_DECISION" if freshness_failure else ("CANDIDATE_ONLY" if candidate_outputs else "DESCRIPTIVE_ONLY"),
                "paper_positions": 0,
                "real_orders": 0,
            },
        },
    }


def report_markdown(report: dict[str, Any]) -> str:
    sections = report["sections"]
    lines = [
        f"# Observation Report: {report['trading_date']}",
        "",
        f"## {report['headline']}",
        "",
        f"Run `{report['run_id']}` | release `{report['release_version']}` | lane `{report['experiment_lane']}`",
        "",
        "## A. Evidence Validity",
        "",
        f"Captured {sections['A_evidence_validity']['captured']} of {sections['A_evidence_validity']['planned']} planned observations (rate {sections['A_evidence_validity']['capture_rate']:.3f}).",
        "",
        "## B. Observed Market Facts",
        "",
        f"The immutable evidence produced {sections['B_observed_market_facts']['feature_count']} point-in-time feature records across six themes.",
        "",
        "## C. Descriptive Theme Structure",
        "",
    ]
    for theme in sections["C_descriptive_theme_structure"]["themes"]:
        close_row = theme["etf_path"][-1]
        lines.extend(
            [
                f"### {theme['display_name']} ({theme['theme_etf']})",
                "",
                f"Close path: ETF {_pct(close_row['etf_intraday_return'])}; relative to SPY {_pct(close_row['relative_to_spy'])}; relative to industry {_pct(close_row['relative_to_industry'])}.",
                "",
                *(f"- {finding}" for finding in theme["descriptive_findings"]),
                "",
            ]
        )
    lines.extend(
        [
            "## D. Candidate Inference Status",
            "",
            "Candidate outputs are retrospective and unvalidated. They are never decision eligible in this report.",
            "",
            "## E. Unknown / Blocked Claims",
            "",
            *(f"- {item}" for item in sections["E_unknown_blocked_claims"]),
            "",
            "## F. Next Useful Observation",
            "",
            f"Probe: `{sections['F_next_useful_observation']['probe_type']}`",
            "",
            sections["F_next_useful_observation"]["question"],
            "",
            *(f"- Acquire: {item}" for item in sections["F_next_useful_observation"]["acquire"]),
            "",
            "Past points cannot be reconstructed or backfilled.",
            "",
            "## G. System Health",
            "",
            f"Stream messages: {sections['G_system_health']['stream_message_count']:,}; drops: {sections['G_system_health']['stream_message_drop_count']}; chunks: {sections['G_system_health']['stream_chunk_count']}.",
            "",
            "## H. Authorization Boundary",
            "",
            f"Status: `{sections['H_authorization_boundary']['decision_status']}`. Paper positions: 0. Real orders: 0.",
            "",
        ]
    )
    return "\n".join(lines)


def report_html(report: dict[str, Any]) -> str:
    markdown = report_markdown(report)
    blocks: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("### "):
            blocks.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("# "):
            blocks.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("- "):
            blocks.append(f"<p class='finding'>{escape(line[2:])}</p>")
        elif line:
            blocks.append(f"<p>{escape(line)}</p>")
    return """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Private Observation Report</title><style>body{font:15px system-ui;max-width:1040px;margin:32px auto;padding:0 20px;color:#15211d;line-height:1.55}h1{font-size:30px}h2{margin-top:36px;border-bottom:1px solid #ccd7d1;padding-bottom:8px}h3{margin-top:24px}.finding{border-left:3px solid #54796a;padding-left:12px;background:#f4f7f5}code{background:#eef2ef;padding:2px 4px}</style></head><body>""" + "".join(blocks) + "</body></html>\n"
