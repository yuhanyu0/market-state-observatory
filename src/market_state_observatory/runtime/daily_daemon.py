from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .alpaca_adapter import AlpacaSIPAdapter
from .alpaca_stream import AlpacaStreamArchive
from .label_ledger import register_source_snapshot, settle_horizon
from .market_calendar import is_trading_day, session_schedule
from .notifications import emit_local_alert
from .observation_freezer import (
    canonical_json,
    freeze_provider_response,
    sha256_bytes,
    write_exclusive,
)
from .quality_engine import freeze_quality
from .recovery import RecoveryState
from .release_identity import release_root, runtime_identity
from .runtime_lock import RuntimeLock
from .runtime_paths import RuntimePaths, resolve_runtime_paths
from .stream_store import BoundedHourlyStreamStore, CrossSectionFreeze

ET = ZoneInfo("America/New_York")


def project_root() -> Path:
    configured = os.environ.get("MSO_SOURCE_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[3]


def universe_path() -> Path:
    release = release_root()
    if release is not None:
        frozen = release / "frozen" / "runtime_universe_v1.json"
        if frozen.is_file():
            return frozen
    return project_root() / "config" / "runtime_universe_v1.json"


def load_universe(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Runtime universe must be an object")
    return payload


def all_symbols(universe: dict[str, Any]) -> list[str]:
    symbols = {str(universe["benchmark"])}
    for theme in universe["themes"]:
        symbols.update(
            [str(theme["theme_etf"]), str(theme["industry_benchmark"]), *theme["basket"]]
        )
    return sorted(symbols)


def session_points(day: date) -> tuple[tuple[str, datetime], ...]:
    schedule = session_schedule(day)
    points = [*schedule.observation_points(), ("next_10_00", schedule.market_open + timedelta(minutes=30))]
    return tuple(sorted(points, key=lambda row: row[1]))


def membership_payload(universe: dict[str, Any]) -> bytes:
    return canonical_json(
        {
            "schema_version": "mso-frozen-membership-v1",
            "source": "runtime_universe_v1",
            "effective_start": universe["frozen_at_utc"],
            "themes": universe["themes"],
        }
    )


def _point_payload(
    capture: Any,
    cross_section: CrossSectionFreeze,
    rest_snapshot_backup_sha256: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    symbols = []
    future_count = 0
    for row in capture.symbols:
        event_times = [
            datetime.fromisoformat(str(row.quote["event_time_utc"])),
            datetime.fromisoformat(str(row.last_trade["event_time_utc"])),
            datetime.fromisoformat(str(row.minute_bar["event_time_utc"])),
        ]
        future_count += sum(event.astimezone(UTC) > now for event in event_times)
        symbols.append(
            {
                "symbol": row.symbol,
                "quote": row.quote,
                "last_trade": row.last_trade,
                "minute_bar": row.minute_bar,
                "vwap": row.vwap,
                "cumulative_volume": row.cumulative_volume,
                "included_interval_start_utc": row.included_interval_start_utc,
                "included_interval_end_utc": row.included_interval_end_utc,
                "quote_age_seconds": row.quote_age_seconds,
            }
        )
    return {
        "schema_version": "mso-private-observation-point-v2",
        "observation_point": capture.observation_point,
        "scheduled_at_utc": cross_section.scheduled_at_utc,
        "freeze_started_at_utc": cross_section.freeze_started_at_utc,
        "freeze_completed_at_utc": cross_section.freeze_completed_at_utc,
        "earliest_event_time_utc": cross_section.earliest_event_time_utc,
        "latest_event_time_utc": cross_section.latest_event_time_utc,
        "cross_section_skew_seconds": cross_section.cross_section_skew_seconds,
        "stream_symbols_requested": cross_section.symbols_requested,
        "stream_symbols_present": cross_section.symbols_present,
        "stream_latest_state": cross_section.latest_state,
        "captured_at_utc": capture.captured_at_utc,
        "symbols": symbols,
        "raw_request_ids": [result.collector_request_id for result in capture.raw_results],
        "rest_snapshot_backup_sha256": rest_snapshot_backup_sha256,
        "future_timestamp_count": future_count,
        "backfilled": False,
        "data_ready_only": True,
        "model_estimated": False,
        "decision_eligible": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }


async def capture_and_freeze(
    *,
    adapter: AlpacaSIPAdapter,
    stream_store: BoundedHourlyStreamStore,
    symbols: list[str],
    point: str,
    scheduled: datetime,
    run_directory: Path,
    run_id: str,
    trading_date: date,
    ledger_root: Path,
) -> str:
    cross_section = await stream_store.freeze_cross_section(symbols, scheduled)
    capture = await asyncio.to_thread(
        adapter.capture_exact_point, symbols, point, scheduled, datetime.now(UTC)
    )
    for result in capture.raw_results:
        freeze_provider_response(
            raw_directory=run_directory / "raw" / point,
            manifest_directory=run_directory / "manifests" / "requests" / point,
            observation_id=result.collector_request_id,
            raw_response=result.raw_response,
            metadata=result.metadata(),
        )
    backup_hash = sha256_bytes(capture.raw_results[2].raw_response)
    payload = _point_payload(capture, cross_section, backup_hash)
    bundle = canonical_json(payload)
    bundle_hash = sha256_bytes(bundle)
    write_exclusive(
        run_directory / "snapshots" / point / f"{bundle_hash}.bundle.json",
        bundle,
    )
    write_exclusive(
        run_directory / "manifests" / "points" / f"{point}.json",
        canonical_json(
            {
                **payload,
                "snapshot_bundle_sha256": bundle_hash,
                "snapshot_bundle_relative_path": f"snapshots/{point}/{bundle_hash}.bundle.json",
            }
        ),
    )
    settle_horizon(
        ledger_root=ledger_root,
        trading_date=trading_date,
        observation_point=point,
        settlement_run_id=run_id,
        settlement_snapshot_hash=bundle_hash,
        observed_at_utc=capture.captured_at_utc,
    )
    if point == "session_close_diagnostic":
        register_source_snapshot(
            ledger_root=ledger_root,
            source_run_id=run_id,
            source_snapshot_hash=bundle_hash,
            source_trading_date=trading_date,
        )
    return bundle_hash


def _run_parent(paths: RuntimePaths, mode: str, experiment_lane: str, day: date) -> Path:
    root = paths.data_shadow if mode == "formal" else paths.observations / "rehearsals"
    return root / experiment_lane / day.isoformat()


def create_run(
    *,
    mode: str,
    day: date,
    identity: dict[str, Any],
    universe: dict[str, Any],
    paths: RuntimePaths,
) -> tuple[Path, dict[str, Any]]:
    run_id = f"{day.isoformat()}-{uuid.uuid4().hex[:12]}"
    run_directory = _run_parent(paths, mode, str(identity["experiment_lane"]), day) / run_id
    status = "FORMAL_DATA_SHADOW" if mode == "formal" else "DATA_CAPTURE_REHEARSAL"
    run = {
        "schema_version": "mso-private-runtime-run-v2",
        "run_id": run_id,
        "trading_date": day.isoformat(),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "mode": mode,
        "timezone": "America/New_York",
        "feed": "sip",
        "membership_snapshot_frozen": True,
        **identity,
        "counts_toward_20_day_gate": mode == "formal",
        "counts_toward_model_shadow": False,
        "counts_toward_live_decision": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    write_exclusive(run_directory / "RUN.json", canonical_json(run))
    write_exclusive(run_directory / "reference" / "membership_snapshot.json", membership_payload(universe))
    return run_directory, run


def open_or_create_run(
    *, mode: str, day: date, identity: dict[str, Any], universe: dict[str, Any], paths: RuntimePaths
) -> tuple[Path, dict[str, Any], bool]:
    parent = _run_parent(paths, mode, str(identity["experiment_lane"]), day)
    for candidate in sorted(parent.glob("*"), reverse=True):
        run_path = candidate / "RUN.json"
        quality_path = candidate / "quality" / "DATA_QUALITY.json"
        if run_path.is_file() and not quality_path.exists():
            payload = json.loads(run_path.read_text(encoding="utf-8"))
            if (
                payload.get("mode") == mode
                and payload.get("trading_date") == day.isoformat()
                and payload.get("experiment_lane") == identity["experiment_lane"]
            ):
                return candidate, payload, True
    directory, payload = create_run(
        mode=mode, day=day, identity=identity, universe=universe, paths=paths
    )
    return directory, payload, False


def latest_recovery(run_directory: Path, trading_date: str) -> RecoveryState:
    candidates = sorted((run_directory / "recovery").glob("*.json"))
    if candidates:
        return RecoveryState.load(candidates[-1], trading_date)
    completed = {path.stem for path in (run_directory / "manifests" / "points").glob("*.json")}
    return RecoveryState(trading_date=trading_date, completed=completed)


def _write_operator_status(paths: RuntimePaths, payload: dict[str, Any]) -> None:
    path = paths.operator / "runtime_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_json(payload))
    os.replace(temporary, path)


async def run_session(mode: str, dry_run: bool = False) -> int:
    now = datetime.now(ET)
    day = now.date()
    if not is_trading_day(day):
        print(f"NO_SESSION trading_date={day.isoformat()}")
        return 0
    paths = resolve_runtime_paths(repo_root=project_root(), create=not dry_run)
    universe_file = universe_path()
    universe = load_universe(universe_file)
    symbols = all_symbols(universe)
    schedule = session_points(day)
    if dry_run:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_PASS",
                    "runtime_root": str(paths.root),
                    "trading_date": day.isoformat(),
                    "symbol_count": len(symbols),
                    "schedule": {name: timestamp.isoformat() for name, timestamp in schedule},
                    "production_release_configured": release_root() is not None,
                    "network_called": False,
                    "formal_data_shadow_started": False,
                    "paper_positions": 0,
                    "real_orders": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    membership = membership_payload(universe)
    identity = runtime_identity(
        repository=project_root(),
        universe_path=universe_file,
        membership=membership,
        production_required=mode == "formal",
    )
    lock = RuntimeLock(paths.locks / "daily-runtime.lock")
    with lock:
        run_directory, run, resumed = open_or_create_run(
            mode=mode, day=day, identity=identity, universe=universe, paths=paths
        )
        recovery = latest_recovery(run_directory, day.isoformat())
        adapter = AlpacaSIPAdapter()
        skew = adapter.clock_skew_seconds()
        if skew is not None and skew > 5:
            raise RuntimeError(f"System clock skew exceeds limit: {skew:.3f} seconds")
        stop = asyncio.Event()
        archive = AlpacaStreamArchive(
            run_directory / "raw" / "websocket",
            run_directory / "manifests" / "websocket",
        )
        stream_task = asyncio.create_task(archive.run(symbols=symbols, stop=stop))
        await asyncio.sleep(0)
        try:
            for point, scheduled in schedule:
                _write_operator_status(
                    paths,
                    {
                        "status": "RUNNING",
                        "run_id": run["run_id"],
                        "experiment_lane": run["experiment_lane"],
                        "current_point": point,
                        "next_event_at_et": scheduled.isoformat(),
                        "websocket_last_message_at_utc": archive.last_message_at_utc,
                        "paper_positions": 0,
                        "real_orders": 0,
                    },
                )
                if point in recovery.completed or point in recovery.missed:
                    continue
                current = datetime.now(ET)
                wait_seconds = (scheduled - current).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                elif wait_seconds < -60:
                    recovery.missed.add(point)
                    recovery.checkpoint(run_directory / "recovery")
                    emit_local_alert(
                        paths.alerts,
                        kind="observation_missed",
                        title="MSO observation missed",
                        message=f"{point} was missed and was not backfilled.",
                        run_id=str(run["run_id"]),
                    )
                    continue
                try:
                    await capture_and_freeze(
                        adapter=adapter,
                        stream_store=archive.store,
                        symbols=symbols,
                        point=point,
                        scheduled=scheduled,
                        run_directory=run_directory,
                        run_id=str(run["run_id"]),
                        trading_date=day,
                        ledger_root=paths.label_ledger,
                    )
                    recovery.completed.add(point)
                except Exception as error:
                    recovery.missed.add(point)
                    write_exclusive(
                        run_directory / "logs" / f"{point}-failure.json",
                        canonical_json(
                            {
                                "point": point,
                                "error_type": type(error).__name__,
                                "missing_preserved": True,
                                "backfill_attempted": False,
                            }
                        ),
                    )
                    emit_local_alert(
                        paths.alerts,
                        kind="observation_missed",
                        title="MSO capture failed",
                        message=f"{point} failed with {type(error).__name__}; no backfill was attempted.",
                        run_id=str(run["run_id"]),
                    )
                recovery.checkpoint(run_directory / "recovery")
        finally:
            stop.set()
            try:
                await asyncio.wait_for(stream_task, timeout=35)
            except TimeoutError:
                stream_task.cancel()
                await asyncio.gather(stream_task, return_exceptions=True)
        quality_path = freeze_quality(run_directory, universe)
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        if not quality["data_quality_pass"]:
            emit_local_alert(
                paths.alerts,
                kind="quality_failed",
                title="MSO data quality failed",
                message="The completed run is blocked from publication and gate counting.",
                run_id=str(run["run_id"]),
            )
        _write_operator_status(
            paths,
            {
                "status": "COMPLETE",
                "run_id": run["run_id"],
                "quality_path": str(quality_path),
                "data_quality_pass": quality["data_quality_pass"],
                "publication_eligible": quality["publication_eligible"],
                "websocket": archive.store.health_payload(),
                "paper_positions": 0,
                "real_orders": 0,
            },
        )
        print(
            f"DATA_CAPTURE_COMPLETE run={run_directory.name} resumed={str(resumed).lower()} "
            f"quality={quality_path}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MSO private Alpaca SIP data-only runtime")
    parser.add_argument("--mode", choices=("rehearsal", "formal"), default="rehearsal")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_session(args.mode, args.dry_run))
    except Exception as error:
        print(f"RUNTIME_FAIL error_type={type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
