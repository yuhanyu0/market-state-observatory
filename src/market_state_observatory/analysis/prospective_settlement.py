from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any

from market_state_observatory.runtime.market_calendar import next_trading_day
from market_state_observatory.runtime.observation_freezer import canonical_json, write_exclusive
from market_state_observatory.validation import validate_payload

from .prospective_candidate import (
    COST_GRID_BPS,
    SAFETY,
    CandidateShadowError,
    PriceObservation,
    _append_once,
    _file_sha256,
    _load_json,
    _parse,
    _point,
    _point_sha,
    execution_price_returns,
    read_ndjson,
)

SETTLEMENT_VERSION = "prospective-outcome-settlement-v1"


def trading_day_offset(value: date, sessions: int) -> date:
    if sessions < 0:
        raise ValueError("Trading-day offset cannot be negative")
    result = value
    for _ in range(sessions):
        result = next_trading_day(result)
    return result


def _run_index(roots: Iterable[Path]) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for root in roots:
        if not root.exists():
            continue
        for run_path in sorted(root.rglob("RUN.json")):
            run = _load_json(run_path)
            index[str(run["trading_date"])].append(run_path.parent)
    return index


def _point_observation(run_directory: Path, point_name: str, ticker: str) -> PriceObservation | None:
    try:
        point, path = _point(run_directory, point_name)
    except CandidateShadowError:
        return None
    if point.get("backfilled") is not False or int(point.get("future_timestamp_count", 0)):
        return None
    row = next((item for item in point.get("symbols", []) if item.get("symbol") == ticker), None)
    if not isinstance(row, dict):
        return None
    quote = row.get("quote", {})
    if quote.get("status") not in {None, "READY"}:
        return None
    bid = quote.get("bid")
    ask = quote.get("ask")
    mid = quote.get("mid")
    event = quote.get("provider_event_time_utc") or quote.get("event_time_utc")
    observed = (
        quote.get("collector_observed_at_utc")
        or point.get("freeze_completed_at_utc")
        or point.get("captured_at_utc")
    )
    if None in (bid, ask, mid, event, observed):
        return None
    bid_value, ask_value, mid_value = float(bid), float(ask), float(mid)
    if bid_value <= 0 or ask_value < bid_value or not bid_value <= mid_value <= ask_value:
        return None
    run = _load_json(run_directory / "RUN.json")
    return PriceObservation(
        bid=bid_value,
        ask=ask_value,
        mid=mid_value,
        event_time_utc=str(event),
        observed_at_utc=str(observed),
        provider=str(row.get("primary_pit_source") or "Alpaca Market Data SIP"),
        source_run_id=str(run["run_id"]),
        source_snapshot_sha256=_point_sha(point, path),
    )


def _execution_observation(candidate_directory: Path, ticker: str) -> PriceObservation | None:
    path = candidate_directory / "EXECUTION_QUOTE.json"
    if not path.is_file():
        return None
    payload = _load_json(path)
    if payload.get("status") != "EXECUTION_QUOTE_READY":
        return None
    row = next((item for item in payload.get("quotes", []) if item.get("ticker") == ticker), None)
    if not isinstance(row, dict):
        return None
    return PriceObservation(
        bid=float(row["bid"]),
        ask=float(row["ask"]),
        mid=float(row["mid"]),
        event_time_utc=str(row["event_time_utc"]),
        observed_at_utc=str(row["observed_at_utc"]),
        provider=str(row["provider"]),
        source_run_id=str(payload["candidate_id"]),
        source_snapshot_sha256=str(payload["raw_response_sha256"]),
    )


def _pick_run(index: dict[str, list[Path]], trading_date: date, point: str) -> Path | None:
    for run_directory in reversed(index.get(trading_date.isoformat(), [])):
        if (run_directory / "manifests" / "points" / f"{point}.json").is_file():
            return run_directory
    return None


def _outcome_inputs(
    *,
    signal: dict[str, Any],
    candidate_directory: Path,
    ticker: str,
    horizon: str,
    runs: dict[str, list[Path]],
) -> tuple[PriceObservation | None, PriceObservation | None, str]:
    signal_date = date.fromisoformat(str(signal["signal_date"]))
    next_date = trading_day_offset(signal_date, 1)
    if horizon.startswith("preclose_quote"):
        entry = _execution_observation(candidate_directory, ticker)
        if horizon == "preclose_quote_to_close":
            target_date, target_point = signal_date, "session_close_diagnostic"
        elif horizon == "preclose_quote_to_next_open":
            target_date, target_point = next_date, "open_snapshot"
        else:
            target_date, target_point = next_date, "session_close_diagnostic"
        target_run = _pick_run(runs, target_date, target_point)
        exit_value = _point_observation(target_run, target_point, ticker) if target_run else None
        return entry, exit_value, target_date.isoformat()
    entry_run = _pick_run(runs, next_date, "open_snapshot")
    entry = _point_observation(entry_run, "open_snapshot", ticker) if entry_run else None
    if horizon == "postclose_signal_next_open_to_next_close":
        target_date = next_date
    elif horizon == "next_open_to_3d_close":
        target_date = trading_day_offset(signal_date, 3)
    elif horizon == "next_open_to_5d_close":
        target_date = trading_day_offset(signal_date, 5)
    else:
        raise ValueError(f"Unsupported settlement horizon: {horizon}")
    target_run = _pick_run(runs, target_date, "session_close_diagnostic")
    exit_value = (
        _point_observation(target_run, "session_close_diagnostic", ticker)
        if target_run
        else None
    )
    return entry, exit_value, target_date.isoformat()


def _candidate_horizons(lane: str) -> tuple[str, ...]:
    if lane == "preclose":
        return (
            "preclose_quote_to_close",
            "preclose_quote_to_next_open",
            "preclose_quote_to_next_close",
        )
    return (
        "postclose_signal_next_open_to_next_close",
        "next_open_to_3d_close",
        "next_open_to_5d_close",
    )


def _same_or_exclusive(path: Path, payload: bytes) -> None:
    if path.is_file():
        if path.read_bytes() != payload:
            raise CandidateShadowError(f"Immutable settlement manifest conflict: {path}")
        return
    write_exclusive(path, payload)


def settle_pending_candidates(
    *,
    candidate_root: Path,
    run_roots: Sequence[Path],
    ledger_root: Path,
    settlement_root: Path,
    settlement_run_id: str,
    settled_at_utc: str,
) -> dict[str, Any]:
    settled_at = _parse(settled_at_utc).astimezone(UTC)
    for existing_manifest in settlement_root.rglob("SETTLEMENT_MANIFEST.json"):
        existing = _load_json(existing_manifest)
        if existing.get("settlement_run_id") == settlement_run_id:
            if existing.get("settled_at_utc") != settled_at.isoformat():
                raise CandidateShadowError(
                    "Settlement run id was reused with a different settlement timestamp"
                )
            return {**existing, "settlement_manifest_path": str(existing_manifest)}
    runs = _run_index(run_roots)
    outcome_path = ledger_root / "PROSPECTIVE_OUTCOME_LEDGER.ndjson"
    existing_ids = {
        str(row["outcome_record_id"]) for row in read_ndjson(outcome_path)
    }
    appended: list[str] = []
    already_settled: list[str] = []
    pending: list[dict[str, Any]] = []
    for signal_path in sorted(candidate_root.rglob("CANDIDATE_SIGNAL.json")):
        signal = _load_json(signal_path)
        if signal.get("candidate_status") != "FROZEN":
            continue
        candidate_directory = signal_path.parent
        for arm in signal.get("arms", []):
            ticker = arm.get("selected_ticker")
            predicted_sign = arm.get("predicted_sign")
            if not ticker or predicted_sign not in {-1, 1}:
                continue
            for horizon in _candidate_horizons(str(signal["lane"])):
                outcome_id = sha256(
                    f"{signal['candidate_id']}:{arm['arm']}:{horizon}".encode()
                ).hexdigest()[:32]
                if outcome_id in existing_ids:
                    already_settled.append(outcome_id)
                    continue
                entry, exit_value, target_date = _outcome_inputs(
                    signal=signal,
                    candidate_directory=candidate_directory,
                    ticker=str(ticker),
                    horizon=horizon,
                    runs=runs,
                )
                if entry is None or exit_value is None:
                    pending.append(
                        {
                            "outcome_record_id": outcome_id,
                            "candidate_id": signal["candidate_id"],
                            "arm": arm["arm"],
                            "horizon": horizon,
                            "target_date": target_date,
                            "status": "NOT_SETTLED",
                            "reason": "legal_future_quote_unavailable",
                        }
                    )
                    continue
                if _parse(entry.event_time_utc) <= _parse(str(signal["generated_at_utc"])) and signal["lane"] == "preclose":
                    pending.append(
                        {
                            "outcome_record_id": outcome_id,
                            "candidate_id": signal["candidate_id"],
                            "arm": arm["arm"],
                            "horizon": horizon,
                            "target_date": target_date,
                            "status": "NOT_SETTLED",
                            "reason": "entry_quote_not_after_candidate",
                        }
                    )
                    continue
                if _parse(exit_value.event_time_utc) > settled_at:
                    pending.append(
                        {
                            "outcome_record_id": outcome_id,
                            "candidate_id": signal["candidate_id"],
                            "arm": arm["arm"],
                            "horizon": horizon,
                            "target_date": target_date,
                            "status": "NOT_SETTLED",
                            "reason": "label_not_observed_by_settlement_time",
                        }
                    )
                    continue
                returns = execution_price_returns(
                    predicted_sign=int(predicted_sign), entry=entry, exit=exit_value
                )
                outcome = {
                    "schema_version": "mso-prospective-outcome-ledger-v1",
                    "outcome_record_id": outcome_id,
                    "candidate_id": signal["candidate_id"],
                    "arm": arm["arm"],
                    "horizon": horizon,
                    "signal_date": signal["signal_date"],
                    "theme_id": arm["selected_theme_id"],
                    "ticker": ticker,
                    "predicted_sign": predicted_sign,
                    "entry": entry.__dict__,
                    "exit": exit_value.__dict__,
                    "returns": returns,
                    "label_event_time": exit_value.event_time_utc,
                    "label_observed_at": exit_value.observed_at_utc,
                    "provider_source": exit_value.provider,
                    "source_run": exit_value.source_run_id,
                    "source_snapshot_sha256": exit_value.source_snapshot_sha256,
                    "settled_at": settled_at.isoformat(),
                    "settlement_run_id": settlement_run_id,
                    "settlement_version": SETTLEMENT_VERSION,
                    "status": "SETTLED",
                    "official_strategy_evidence": True,
                    **SAFETY,
                }
                validate_payload(outcome, "prospective_outcome_ledger")
                if _append_once(outcome_path, outcome, id_field="outcome_record_id"):
                    appended.append(outcome_id)
                    existing_ids.add(outcome_id)
    manifest_semantic = {
        "schema_version": "mso-prospective-settlement-manifest-v1",
        "settlement_run_id": settlement_run_id,
        "settled_at_utc": settled_at.isoformat(),
        "settlement_version": SETTLEMENT_VERSION,
        "appended_outcome_ids": sorted(appended),
        "already_settled_outcome_ids": sorted(set(already_settled)),
        "pending": sorted(pending, key=lambda row: str(row["outcome_record_id"])),
        "signal_ledger_sha256": (
            _file_sha256(ledger_root / "PROSPECTIVE_SIGNAL_LEDGER.ndjson")
            if (ledger_root / "PROSPECTIVE_SIGNAL_LEDGER.ndjson").is_file()
            else None
        ),
        "outcome_ledger_sha256": _file_sha256(outcome_path) if outcome_path.is_file() else None,
        "source_runs_mutated": False,
        "backfill_used": False,
        **SAFETY,
    }
    validate_payload(manifest_semantic, "prospective_settlement_manifest")
    manifest_id = sha256(canonical_json(manifest_semantic)).hexdigest()[:24]
    manifest_path = settlement_root / settled_at.date().isoformat() / manifest_id / "SETTLEMENT_MANIFEST.json"
    _same_or_exclusive(manifest_path, canonical_json(manifest_semantic))
    return {**manifest_semantic, "settlement_manifest_path": str(manifest_path)}


def _maximum_drawdown(values: Sequence[float]) -> float | None:
    if not values:
        return None
    equity = peak = 1.0
    worst = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def day_clustered_bootstrap(
    rows: Sequence[dict[str, Any]], *, value_key: str, seed: int = 51, iterations: int = 1000
) -> dict[str, float | None]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(value_key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            grouped[str(row["signal_date"])].append(float(value))
    keys = sorted(grouped)
    if not keys:
        return {"mean": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        values = [value for _ in keys for value in grouped[rng.choice(keys)]]
        estimates.append(mean(values))
    estimates.sort()
    return {
        "mean": mean(estimates),
        "ci_low": estimates[int(0.025 * (len(estimates) - 1))],
        "ci_high": estimates[int(0.975 * (len(estimates) - 1))],
    }


def paired_common_date_ablation(
    rows: Sequence[dict[str, Any]], left_arm: str, right_arm: str, horizon: str
) -> dict[str, Any]:
    by_key = {
        (str(row["signal_date"]), str(row["arm"])): float(
            row["returns"]["fixed_cost_net_returns"]["10"]
        )
        for row in rows
        if row.get("horizon") == horizon and row.get("status") == "SETTLED"
    }
    dates = sorted(
        {date_key for date_key, arm in by_key if arm == left_arm}
        & {date_key for date_key, arm in by_key if arm == right_arm}
    )
    differences = [by_key[(value, right_arm)] - by_key[(value, left_arm)] for value in dates]
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "horizon": horizon,
        "common_legal_dates": len(dates),
        "paired_mean_difference": mean(differences) if differences else None,
        "paired_median_difference": median(differences) if differences else None,
        "day_clustered_bootstrap": day_clustered_bootstrap(
            [
                {"signal_date": date_key, "difference": difference}
                for date_key, difference in zip(dates, differences, strict=True)
            ],
            value_key="difference",
        ),
    }


def summarize_outcomes(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "SETTLED":
            grouped[(str(row["arm"]), str(row["horizon"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (arm, horizon), group in sorted(grouped.items()):
        signs = [int(row["predicted_sign"]) for row in group]
        gross = [float(row["returns"]["spread_realistic_gross_return"]) for row in group]
        positive = [value > 0 for value in gross]
        themes: dict[str, float] = defaultdict(float)
        months: dict[str, float] = defaultdict(float)
        for row, value in zip(group, gross, strict=True):
            themes[str(row["theme_id"])] += abs(value)
            months[str(row["signal_date"])[:7]] += abs(value)
        total_abs = sum(abs(value) for value in gross)
        for cost in COST_GRID_BPS:
            key = f"{cost:g}"
            net = [float(row["returns"]["fixed_cost_net_returns"][key]) for row in group]
            ordered = sorted(net, reverse=True)
            without_best = ordered[1:] if len(ordered) > 1 else []
            summaries.append(
                {
                    "arm": arm,
                    "horizon": horizon,
                    "cost_bps": cost,
                    "distinct_dates": len({str(row["signal_date"]) for row in group}),
                    "coverage": 1.0,
                    "mean_net_return": mean(net),
                    "median_net_return": median(net),
                    "brier_score": None,
                    "log_loss": None,
                    "signed_accuracy": mean(float(value) for value in positive),
                    "cross_sectional_rank_correlation": None,
                    "top_bottom_spread": None,
                    "false_positive_rate": (
                        mean(float(not won) for sign, won in zip(signs, positive, strict=True) if sign == 1)
                        if any(sign == 1 for sign in signs)
                        else None
                    ),
                    "maximum_drawdown": _maximum_drawdown(net),
                    "downside_beta": None,
                    "top_theme_absolute_pnl_share": max(themes.values(), default=0.0) / total_abs if total_abs else None,
                    "top_month_absolute_pnl_share": max(months.values(), default=0.0) / total_abs if total_abs else None,
                    "remove_best_1_event_mean": mean(without_best) if without_best else None,
                    "day_clustered_bootstrap": day_clustered_bootstrap(
                        [
                            {"signal_date": row["signal_date"], "net": value}
                            for row, value in zip(group, net, strict=True)
                        ],
                        value_key="net",
                    ),
                    **SAFETY,
                }
            )
    return summaries


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Settle mature prospective candidate outcomes")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--settlement-root", type=Path, required=True)
    parser.add_argument("--settlement-run-id", required=True)
    parser.add_argument("--settled-at-utc", required=True)
    args = parser.parse_args(argv)
    result = settle_pending_candidates(
        candidate_root=args.candidate_root.resolve(),
        run_roots=[row.resolve() for row in args.run_root],
        ledger_root=args.ledger_root.resolve(),
        settlement_root=args.settlement_root.resolve(),
        settlement_run_id=args.settlement_run_id,
        settled_at_utc=args.settled_at_utc,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
