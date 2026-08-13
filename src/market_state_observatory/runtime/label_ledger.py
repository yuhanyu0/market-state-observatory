from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .market_calendar import next_trading_day
from .observation_freezer import canonical_json, sha256_bytes, write_exclusive

HORIZONS = ("next_open", "next_10_00", "next_15_45")
POINT_TO_HORIZON = {
    "open_snapshot": "next_open",
    "next_10_00": "next_10_00",
    "decision_snapshot": "next_15_45",
}


def _entry_id(source_run_id: str, source_snapshot_hash: str, horizon: str) -> str:
    payload = f"{source_run_id}:{source_snapshot_hash}:{horizon}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def register_source_snapshot(
    *,
    ledger_root: Path,
    source_run_id: str,
    source_snapshot_hash: str,
    source_trading_date: date,
) -> tuple[Path, ...]:
    target_date = next_trading_day(source_trading_date)
    paths: list[Path] = []
    for horizon in HORIZONS:
        entry_id = _entry_id(source_run_id, source_snapshot_hash, horizon)
        path = ledger_root / "pending" / target_date.isoformat() / f"{entry_id}.json"
        payload = {
            "schema_version": "mso-private-label-ledger-v1",
            "ledger_entry_id": entry_id,
            "source_run_id": source_run_id,
            "source_snapshot_hash": source_snapshot_hash,
            "source_trading_date": source_trading_date.isoformat(),
            "target_trading_date": target_date.isoformat(),
            "target_horizon": horizon,
            "next_open": "pending" if horizon == "next_open" else "not_applicable",
            "next_10_00": "pending" if horizon == "next_10_00" else "not_applicable",
            "next_15_45": "pending" if horizon == "next_15_45" else "not_applicable",
            "observed_at_utc": None,
            "settlement_run_id": None,
            "settlement_hash": None,
            "status": "PENDING",
            "immutable": True,
        }
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != payload:
                raise RuntimeError(f"Conflicting label ledger registration: {entry_id}")
        else:
            write_exclusive(path, canonical_json(payload))
        paths.append(path)
    return tuple(paths)


def settle_horizon(
    *,
    ledger_root: Path,
    trading_date: date,
    observation_point: str,
    settlement_run_id: str,
    settlement_snapshot_hash: str,
    observed_at_utc: str,
) -> tuple[Path, ...]:
    horizon = POINT_TO_HORIZON.get(observation_point)
    if horizon is None:
        return ()
    pending_root = ledger_root / "pending" / trading_date.isoformat()
    settled: list[Path] = []
    for pending_path in sorted(pending_root.glob("*.json")):
        source = json.loads(pending_path.read_text(encoding="utf-8"))
        if source.get("target_horizon") != horizon:
            continue
        settlement = {
            **source,
            "observed_at_utc": observed_at_utc,
            "settlement_run_id": settlement_run_id,
            "settlement_hash": settlement_snapshot_hash,
            "status": "SETTLED",
            "settled_at_utc": datetime.now(UTC).isoformat(),
            "source_entry_sha256": sha256_bytes(pending_path.read_bytes()),
        }
        target = ledger_root / "settled" / source["ledger_entry_id"] / f"{settlement_snapshot_hash}.json"
        if target.exists():
            if json.loads(target.read_text(encoding="utf-8")) != settlement:
                existing = json.loads(target.read_text(encoding="utf-8"))
                stable_keys = set(settlement) - {"settled_at_utc"}
                if any(existing.get(key) != settlement.get(key) for key in stable_keys):
                    raise RuntimeError(f"Conflicting label settlement: {source['ledger_entry_id']}")
        else:
            write_exclusive(target, canonical_json(settlement))
        settled.append(target)
    return tuple(settled)


def settlement_bundle_hash(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(payload))
