from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUN_ID = "2026-08-14-bc1d37197bc0"
ACTIVE_SYMBOLS = ("SPY", "NVDA", "SMH", "SOXX")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return payload


def raw_for_request(run: Path, point: str, request_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_matches = list((run / "raw" / point).glob(f"{request_id}.*.json"))
    manifest_path = run / "manifests" / "requests" / point / f"{request_id}.manifest.json"
    if len(raw_matches) != 1 or not manifest_path.is_file():
        raise FileNotFoundError(f"Request evidence incomplete: {point}/{request_id}")
    manifest = load_object(manifest_path)
    if sha256(raw_matches[0]) != manifest["raw_response_sha256"]:
        raise ValueError(f"Raw response hash mismatch: {raw_matches[0]}")
    return load_object(raw_matches[0]), manifest


def classify_symbol(
    *,
    symbol: str,
    scheduled: datetime,
    quote_body: dict[str, Any],
    quote_manifest: dict[str, Any],
    trade_body: dict[str, Any],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    quote = quote_body.get("quotes", {}).get(symbol)
    trade = trade_body.get("trades", {}).get(symbol)
    legal_bars = [
        row
        for row in bars_by_symbol.get(symbol, [])
        if parse_utc(str(row["t"])) <= scheduled
    ]
    reasons: list[str] = []
    diagnostics: dict[str, Any] = {
        "quote_present": quote is not None,
        "trade_present": trade is not None,
        "eligible_completed_bar_count": len(legal_bars),
    }
    if quote is None:
        reasons.append("quote_missing")
    if trade is None:
        reasons.append("trade_missing")
    if not legal_bars:
        reasons.append("no_eligible_completed_bar")
    if quote is not None:
        observed = parse_utc(str(quote_manifest["observed_at_utc"]))
        quote_time = parse_utc(str(quote["t"]))
        age = (observed - quote_time).total_seconds()
        bid = float(quote["bp"])
        ask = float(quote["ap"])
        diagnostics.update(
            {
                "quote_event_time_utc": quote_time.isoformat(),
                "quote_observed_at_utc": observed.isoformat(),
                "quote_age_seconds": age,
                "bid": bid,
                "ask": ask,
            }
        )
        if quote_time > observed:
            reasons.append("quote_future_vs_collector_clock")
        elif age > 60:
            reasons.append("quote_age_over_limit")
        if bid <= 0:
            reasons.append("bid_nonpositive")
        if ask <= 0:
            reasons.append("ask_nonpositive")
        if ask < bid:
            reasons.append("crossed_quote")
    primary_order = (
        "quote_missing",
        "trade_missing",
        "no_eligible_completed_bar",
        "quote_future_vs_collector_clock",
        "quote_age_over_limit",
        "bid_nonpositive",
        "ask_nonpositive",
        "crossed_quote",
    )
    primary = next((reason for reason in primary_order if reason in reasons), None)
    return {**diagnostics, "all_exclusion_reasons": reasons, "primary_exclusion_reason": primary}


def audit(run: Path) -> dict[str, Any]:
    run_payload = load_object(run / "RUN.json")
    if run_payload.get("run_id") != RUN_ID:
        raise ValueError(f"Expected immutable Day A run {RUN_ID}")
    points: list[dict[str, Any]] = []
    overall_primary: Counter[str] = Counter()
    overall_all: Counter[str] = Counter()
    active_hypothesis: list[dict[str, Any]] = []
    for point_path in sorted((run / "manifests" / "points").glob("*.json")):
        point = load_object(point_path)
        point_name = str(point["observation_point"])
        request_ids = list(map(str, point["raw_request_ids"]))
        if len(request_ids) < 5:
            raise ValueError(f"Unexpected raw request ordering at {point_name}")
        quote_body, quote_manifest = raw_for_request(run, point_name, request_ids[0])
        trade_body, _ = raw_for_request(run, point_name, request_ids[1])
        raw_for_request(run, point_name, request_ids[2])
        bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for request_id in request_ids[3:]:
            bar_body, _ = raw_for_request(run, point_name, request_id)
            for symbol, rows in bar_body.get("bars", {}).items():
                bars_by_symbol.setdefault(symbol, []).extend(rows)

        scheduled = parse_utc(str(point["scheduled_at_utc"]))
        captured_symbols = {str(row["symbol"]) for row in point.get("symbols", [])}
        expected_symbols = sorted(map(str, point.get("stream_latest_state", {}).keys()))
        if len(expected_symbols) != int(point["stream_symbols_requested"]):
            raise ValueError(f"Stream universe mismatch at {point_name}")
        missing_rows: list[dict[str, Any]] = []
        primary_counts: Counter[str] = Counter()
        all_counts: Counter[str] = Counter()
        for symbol in expected_symbols:
            classification = classify_symbol(
                symbol=symbol,
                scheduled=scheduled,
                quote_body=quote_body,
                quote_manifest=quote_manifest,
                trade_body=trade_body,
                bars_by_symbol=bars_by_symbol,
            )
            if symbol not in captured_symbols:
                if classification["primary_exclusion_reason"] is None:
                    classification["primary_exclusion_reason"] = "other"
                    classification["all_exclusion_reasons"].append("other")
                row = {"symbol": symbol, **classification}
                missing_rows.append(row)
                primary_counts[str(row["primary_exclusion_reason"])] += 1
                all_counts.update(map(str, row["all_exclusion_reasons"]))
                if symbol in ACTIVE_SYMBOLS:
                    active_hypothesis.append({"point": point_name, **row})
        overall_primary.update(primary_counts)
        overall_all.update(all_counts)
        points.append(
            {
                "point": point_name,
                "scheduled_at_utc": scheduled.isoformat(),
                "rest_captured_symbols": len(captured_symbols),
                "planned_symbols": len(expected_symbols),
                "websocket_symbols_present": int(point["stream_symbols_present"]),
                "old_cross_section_skew_seconds": point.get("cross_section_skew_seconds"),
                "primary_exclusion_reason_counts": dict(sorted(primary_counts.items())),
                "all_exclusion_reason_counts": dict(sorted(all_counts.items())),
                "missing_symbols": missing_rows,
            }
        )
    active_exclusions = [row for row in active_hypothesis if row["primary_exclusion_reason"]]
    active_clock_or_eligibility = all(
        row["primary_exclusion_reason"]
        in {"quote_future_vs_collector_clock", "quote_age_over_limit", "no_eligible_completed_bar"}
        for row in active_exclusions
    )
    parts = run.parts
    anchor = parts.index("observations") if "observations" in parts else len(parts) - 1
    source_relative_path = Path(*parts[anchor:]).as_posix()
    return {
        "schema_version": "mso-day-a-capture-forensic-v1",
        "research_grade": "immutable_offline_forensic_audit",
        "source_run_id": RUN_ID,
        "source_run_relative_path": source_relative_path,
        "source_run_sha256": sha256(run / "RUN.json"),
        "source_release_version": run_payload["release_version"],
        "source_git_sha": run_payload["git_sha"],
        "day_a_remains_failed": True,
        "network_called": False,
        "source_artifacts_modified": False,
        "raw_request_id_order": ["quote", "trade", "snapshot", "bar_pages"],
        "overall_primary_exclusion_reason_counts": dict(sorted(overall_primary.items())),
        "overall_all_exclusion_reason_counts": dict(sorted(overall_all.items())),
        "active_symbol_hypothesis": {
            "symbols": list(ACTIVE_SYMBOLS),
            "excluded_rows": active_exclusions,
            "all_exclusions_due_to_timestamp_or_bar_eligibility": active_clock_or_eligibility,
        },
        "points": points,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Day A Capture Forensic Report",
        "",
        f"Source run: `{report['source_run_id']}`. This was an offline, immutable audit. ",
        "No Alpaca call was made, no Day A artifact was altered, and Day A remains `FAIL`.",
        "",
        "## Point Summary",
        "",
        "| Point | REST rows | WebSocket | Missing primary causes |",
        "|---|---:|---:|---|",
    ]
    for point in report["points"]:
        causes = ", ".join(
            f"{name}={count}"
            for name, count in point["primary_exclusion_reason_counts"].items()
        ) or "none"
        lines.append(
            f"| {point['point']} | {point['rest_captured_symbols']}/{point['planned_symbols']} | "
            f"{point['websocket_symbols_present']}/{point['planned_symbols']} | {causes} |"
        )
    lines.extend(
        [
            "",
            "## Missing Symbols",
            "",
            "| Point | Symbol | Primary reason | All reasons | Quote age (s) | Bars |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for point in report["points"]:
        for row in point["missing_symbols"]:
            reasons = ", ".join(row["all_exclusion_reasons"])
            age = row.get("quote_age_seconds")
            age_text = f"{age:.6f}" if isinstance(age, (float, int)) else "n/a"
            lines.append(
                f"| {point['point']} | {row['symbol']} | {row['primary_exclusion_reason']} | "
                f"{reasons} | {age_text} | {row['eligible_completed_bar_count']} |"
            )
    hypothesis = report["active_symbol_hypothesis"]
    lines.extend(
        [
            "",
            "## Active-Symbol Hypothesis",
            "",
            "For SPY, NVDA, SMH, and SOXX, provider absence is distinguished from the old "
            "timestamp/bar eligibility checks in the rows above.",
            "",
            "`all_exclusions_due_to_timestamp_or_bar_eligibility = "
            f"{str(hypothesis['all_exclusions_due_to_timestamp_or_bar_eligibility']).lower()}`",
            "",
            "## Interpretation Boundary",
            "",
            "These classifications reproduce the v0.4.3 exclusion order. They do not apply "
            "v0.4.4 semantics retroactively and do not change Day A quality or promotion status.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline immutable Day A capture audit")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run.resolve())
    args.output_directory.mkdir(parents=True, exist_ok=True)
    json_path = args.output_directory / "DAY_A_CAPTURE_FORENSIC_REPORT.json"
    md_path = args.output_directory / "DAY_A_CAPTURE_FORENSIC_REPORT.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(f"DAY_A_FORENSIC_JSON={json_path}")
    print(f"DAY_A_FORENSIC_MD={md_path}")
    print("NETWORK_CALLED=false")
    print("DAY_A_ARTIFACTS_MODIFIED=false")


if __name__ == "__main__":
    main()
