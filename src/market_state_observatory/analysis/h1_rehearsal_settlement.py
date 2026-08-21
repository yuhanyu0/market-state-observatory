from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from market_state_observatory.runtime.observation_freezer import canonical_json

from .prospective_candidate import (
    COST_GRID_BPS,
    PriceObservation,
    _file_sha256,
    _load_json,
    execution_price_returns,
)
from .prospective_settlement import (
    SETTLEMENT_VERSION,
    _pick_run,
    _point_observation,
    _run_index,
    trading_day_offset,
)

AUDIT_HORIZONS = (
    "preclose_quote_to_close",
    "preclose_quote_to_next_open",
    "preclose_quote_to_next_close",
    "postclose_signal_next_open_to_next_close",
    "next_open_to_3d_close",
    "next_open_to_5d_close",
)


def _write_deterministic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.read_bytes() != payload:
            raise RuntimeError(f"H1 audit output conflict: {path}")
        return
    path.write_bytes(payload)


def _source_runs(index: dict[str, list[Path]], run_ids: Sequence[str]) -> list[Path]:
    by_id: dict[str, Path] = {}
    for paths in index.values():
        for path in paths:
            run = _load_json(path / "RUN.json")
            by_id[str(run["run_id"])] = path
    return [by_id[run_id] for run_id in run_ids if run_id in by_id]


def _theme_rows(run_directory: Path) -> list[dict[str, str]]:
    membership = _load_json(run_directory / "reference" / "membership_snapshot.json")
    return [
        {"theme_id": str(row["theme_id"]), "ticker": str(row["theme_etf"])}
        for row in membership["themes"]
    ]


def _audit_inputs(
    source_run: Path,
    ticker: str,
    horizon: str,
    index: dict[str, list[Path]],
) -> tuple[PriceObservation | None, PriceObservation | None, str]:
    run = _load_json(source_run / "RUN.json")
    signal_date = date.fromisoformat(str(run["trading_date"]))
    next_date = trading_day_offset(signal_date, 1)
    preclose = _point_observation(source_run, "decision_snapshot", ticker)
    if horizon == "preclose_quote_to_close":
        return preclose, _point_observation(source_run, "session_close_diagnostic", ticker), signal_date.isoformat()
    if horizon == "preclose_quote_to_next_open":
        target = _pick_run(index, next_date, "open_snapshot")
        return preclose, _point_observation(target, "open_snapshot", ticker) if target else None, next_date.isoformat()
    if horizon == "preclose_quote_to_next_close":
        target = _pick_run(index, next_date, "session_close_diagnostic")
        return preclose, _point_observation(target, "session_close_diagnostic", ticker) if target else None, next_date.isoformat()
    entry_run = _pick_run(index, next_date, "open_snapshot")
    entry = _point_observation(entry_run, "open_snapshot", ticker) if entry_run else None
    if horizon == "postclose_signal_next_open_to_next_close":
        target_date = next_date
    elif horizon == "next_open_to_3d_close":
        target_date = trading_day_offset(signal_date, 3)
    else:
        target_date = trading_day_offset(signal_date, 5)
    target_run = _pick_run(index, target_date, "session_close_diagnostic")
    exit_value = _point_observation(target_run, "session_close_diagnostic", ticker) if target_run else None
    return entry, exit_value, target_date.isoformat()


def audit_h1_rehearsal_settlement(
    *,
    run_roots: Sequence[Path],
    config_path: Path,
    output_directory: Path,
    audit_at_utc: str,
) -> dict[str, Any]:
    config = _load_json(config_path)
    index = _run_index(run_roots)
    sources = _source_runs(index, [str(value) for value in config["frozen_source_run_ids"]])
    audit_at = datetime.fromisoformat(audit_at_utc.replace("Z", "+00:00")).astimezone(UTC)
    outcomes: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    source_manifest: list[dict[str, Any]] = []
    for source_run in sources:
        run = _load_json(source_run / "RUN.json")
        source_manifest.append(
            {
                "source_run_id": run["run_id"],
                "run_sha256": _file_sha256(source_run / "RUN.json"),
                "source_run_mutated": False,
            }
        )
        for theme in _theme_rows(source_run):
            for horizon in AUDIT_HORIZONS:
                entry, exit_value, target_date = _audit_inputs(
                    source_run, theme["ticker"], horizon, index
                )
                record_id = sha256(
                    f"{run['run_id']}:{theme['theme_id']}:{horizon}".encode()
                ).hexdigest()[:32]
                if (
                    entry is None
                    or exit_value is None
                    or datetime.fromisoformat(exit_value.observed_at_utc) > audit_at
                ):
                    unavailable.append(
                        {
                            "outcome_record_id": record_id,
                            "source_run_id": run["run_id"],
                            "theme_id": theme["theme_id"],
                            "ticker": theme["ticker"],
                            "horizon": horizon,
                            "target_date": target_date,
                            "status": "NOT_SETTLED",
                            "reason": "legal_future_price_unavailable",
                            "backfill_used": False,
                        }
                    )
                    continue
                returns = execution_price_returns(
                    predicted_sign=1,
                    entry=entry,
                    exit=exit_value,
                    costs_bps=COST_GRID_BPS,
                )
                outcomes.append(
                    {
                        "schema_version": "mso-h1-rehearsal-outcome-audit-v1",
                        "outcome_record_id": record_id,
                        "source_run_id": run["run_id"],
                        "source_snapshot_sha256": entry.source_snapshot_sha256,
                        "signal_date": run["trading_date"],
                        "theme_id": theme["theme_id"],
                        "ticker": theme["ticker"],
                        "horizon": horizon,
                        "entry": entry.__dict__,
                        "exit": exit_value.__dict__,
                        "long_return_diagnostic": returns,
                        "label_event_time": exit_value.event_time_utc,
                        "label_observed_at": exit_value.observed_at_utc,
                        "provider_source": exit_value.provider,
                        "settled_at": audit_at.isoformat(),
                        "settlement_version": SETTLEMENT_VERSION,
                        "status": "SETTLED",
                        "evidence_lane": "H1_EXACT_PIT",
                        "research_use": "rehearsal_research_only",
                        "candidate_freeze_before_outcome_available": False,
                        "official_strategy_evidence": False,
                        "counts_toward_formal_gate": False,
                        "counts_toward_model_shadow_gate": False,
                        "decision_eligible": False,
                        "paper_positions": 0,
                        "real_orders": 0,
                    }
                )
    ledger_bytes = b"".join(canonical_json(row) for row in outcomes)
    _write_deterministic(output_directory / "H1_REHEARSAL_OUTCOME_LEDGER.ndjson", ledger_bytes)
    manifest = {
        "schema_version": "mso-h1-rehearsal-settlement-manifest-v1",
        "audit_at_utc": audit_at.isoformat(),
        "frozen_source_run_ids": config["frozen_source_run_ids"],
        "source_runs_found": len(sources),
        "source_theme_records": len(sources) * 6,
        "settled_outcomes": len(outcomes),
        "not_settled_outcomes": len(unavailable),
        "settled_by_horizon": {
            horizon: sum(row["horizon"] == horizon for row in outcomes)
            for horizon in AUDIT_HORIZONS
        },
        "source_manifest": source_manifest,
        "unavailable": unavailable,
        "outcome_ledger_sha256": sha256(ledger_bytes).hexdigest(),
        "source_runs_mutated": False,
        "backfill_used": False,
        "rehearsal_research_only": True,
        "official_strategy_evidence": False,
        "counts_toward_formal_gate": False,
        "counts_toward_model_shadow_gate": False,
        "decision_eligible": False,
        "paper_positions": 0,
        "real_orders": 0,
    }
    _write_deterministic(output_directory / "SETTLEMENT_MANIFEST.json", canonical_json(manifest))
    _write_deterministic(
        output_directory / "H1_NOT_SETTLED.json",
        json.dumps(unavailable, indent=2, sort_keys=True).encode() + b"\n",
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit legal future labels for frozen H1 rehearsal runs")
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-at-utc", required=True)
    args = parser.parse_args(argv)
    result = audit_h1_rehearsal_settlement(
        run_roots=[path.resolve() for path in args.run_root],
        config_path=args.config.resolve(),
        output_directory=args.output.resolve(),
        audit_at_utc=args.audit_at_utc,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
