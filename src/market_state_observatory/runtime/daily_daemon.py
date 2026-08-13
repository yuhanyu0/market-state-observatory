from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .alpaca_adapter import AlpacaSIPAdapter
from .alpaca_stream import archive_stream
from .label_settler import settlement_link
from .market_calendar import is_trading_day, market_close_time
from .observation_freezer import canonical_json, freeze_provider_response, write_exclusive
from .quality_engine import freeze_quality
from .recovery import RecoveryState
from .runtime_lock import RuntimeLock
from .runtime_paths import resolve_runtime_paths

ET = ZoneInfo("America/New_York")
POINTS = (
    ("open_snapshot", time(9, 30)),
    ("next_10_00", time(10, 0)),
    ("midday_snapshot", time(12, 0)),
    ("preclose_snapshot", time(15, 30)),
    ("decision_snapshot", time(15, 45)),
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def _point_datetime(day: date, point_time: time) -> datetime:
    return datetime.combine(day, point_time, ET)


def _point_payload(capture: Any, settlement: dict[str, Any] | None) -> dict[str, Any]:
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
        "schema_version": "mso-private-observation-point-v1",
        "observation_point": capture.observation_point,
        "scheduled_at_utc": capture.scheduled_at_utc,
        "captured_at_utc": capture.captured_at_utc,
        "symbols": symbols,
        "raw_request_ids": [result.collector_request_id for result in capture.raw_results],
        "future_timestamp_count": future_count,
        "backfilled": False,
        "settlement": settlement,
        "data_ready_only": True,
        "model_estimated": False,
        "decision_eligible": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }


def capture_and_freeze(
    *,
    adapter: AlpacaSIPAdapter,
    symbols: list[str],
    point: str,
    scheduled: datetime,
    run_directory: Path,
) -> None:
    capture = adapter.capture_exact_point(symbols, point, scheduled, datetime.now(UTC))
    for result in capture.raw_results:
        freeze_provider_response(
            raw_directory=run_directory / "raw" / point,
            manifest_directory=run_directory / "manifests" / "requests" / point,
            observation_id=result.collector_request_id,
            raw_response=result.raw_response,
            metadata=result.metadata(),
        )
    payload = _point_payload(capture, settlement_link(point, scheduled.astimezone(ET).date()))
    write_exclusive(
        run_directory / "manifests" / "points" / f"{point}.json",
        canonical_json(payload),
    )


def create_run(
    *,
    mode: str,
    day: date,
    runtime_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    paths = resolve_runtime_paths(repo_root=project_root(), create=True)
    if runtime_root is not None and runtime_root.resolve() != paths.root:
        raise ValueError("Runtime override must be provided through MSO_RUNTIME_ROOT")
    run_id = f"{day.isoformat()}-{uuid.uuid4().hex[:12]}"
    if mode == "formal":
        run_directory = paths.data_shadow / day.isoformat() / run_id
        status = "DATA_CAPTURE_ONLY"
        counts = True
    else:
        run_directory = paths.observations / "rehearsals" / day.isoformat() / run_id
        status = "DATA_CAPTURE_REHEARSAL"
        counts = False
    run = {
        "schema_version": "mso-private-runtime-run-v1",
        "run_id": run_id,
        "trading_date": day.isoformat(),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "mode": mode,
        "timezone": "America/New_York",
        "feed": "sip",
        "membership_snapshot_frozen": True,
        "counts_toward_20_day_gate": counts,
        "counts_toward_model_shadow": False,
        "counts_toward_live_decision": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    write_exclusive(run_directory / "RUN.json", canonical_json(run))
    universe = load_universe(project_root() / "config" / "runtime_universe_v1.json")
    write_exclusive(
        run_directory / "reference" / "membership_snapshot.json",
        canonical_json(
            {
                "known_at_utc": datetime.now(UTC).isoformat(),
                "source": "frozen_runtime_universe_v1",
                "point_in_time_for_run": True,
                "themes": universe["themes"],
            }
        ),
    )
    return run_directory, run


def open_or_create_run(*, mode: str, day: date) -> tuple[Path, dict[str, Any], bool]:
    paths = resolve_runtime_paths(repo_root=project_root(), create=True)
    parent = (
        paths.data_shadow / day.isoformat()
        if mode == "formal"
        else paths.observations / "rehearsals" / day.isoformat()
    )
    for candidate in sorted(parent.glob("*"), reverse=True):
        run_path = candidate / "RUN.json"
        quality_path = candidate / "quality" / "DATA_QUALITY.json"
        if run_path.is_file() and not quality_path.exists():
            payload = json.loads(run_path.read_text(encoding="utf-8"))
            if payload.get("mode") == mode and payload.get("trading_date") == day.isoformat():
                return candidate, payload, True
    directory, payload = create_run(mode=mode, day=day)
    return directory, payload, False


def latest_recovery(run_directory: Path, trading_date: str) -> RecoveryState:
    candidates = sorted((run_directory / "recovery").glob("*.json"))
    if candidates:
        return RecoveryState.load(candidates[-1], trading_date)
    completed = {
        path.stem for path in (run_directory / "manifests" / "points").glob("*.json")
    }
    return RecoveryState(trading_date=trading_date, completed=completed)


async def run_session(mode: str, dry_run: bool = False) -> int:
    now = datetime.now(ET)
    day = now.date()
    if not is_trading_day(day):
        print(f"NO_SESSION trading_date={day.isoformat()}")
        return 0
    paths = resolve_runtime_paths(repo_root=project_root(), create=not dry_run)
    universe = load_universe(project_root() / "config" / "runtime_universe_v1.json")
    symbols = all_symbols(universe)
    if dry_run:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_PASS",
                    "runtime_root": str(paths.root),
                    "trading_date": day.isoformat(),
                    "symbol_count": len(symbols),
                    "network_called": False,
                    "paper_positions": 0,
                    "real_orders": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    lock = RuntimeLock(paths.locks / "daily-runtime.lock")
    with lock:
        run_directory, _, resumed = open_or_create_run(mode=mode, day=day)
        recovery = latest_recovery(run_directory, day.isoformat())
        adapter = AlpacaSIPAdapter()
        skew = adapter.clock_skew_seconds()
        if skew is not None and skew > 5:
            raise RuntimeError(f"System clock skew exceeds limit: {skew:.3f} seconds")
        stop = asyncio.Event()
        stream_task = asyncio.create_task(
            archive_stream(
                symbols=symbols,
                raw_directory=run_directory / "raw" / "websocket",
                manifest_directory=run_directory / "manifests" / "websocket",
                stop=stop,
            )
        )
        close_hour, close_minute = market_close_time(day)
        schedule = [*POINTS, ("session_close_diagnostic", time(close_hour, close_minute))]
        try:
            for point, point_time in schedule:
                if point in recovery.completed or point in recovery.missed:
                    continue
                scheduled = _point_datetime(day, point_time)
                current = datetime.now(ET)
                wait_seconds = (scheduled - current).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                elif wait_seconds < -60:
                    recovery.missed.add(point)
                    recovery.checkpoint(run_directory / "recovery")
                    continue
                try:
                    await asyncio.to_thread(
                        capture_and_freeze,
                        adapter=adapter,
                        symbols=symbols,
                        point=point,
                        scheduled=scheduled,
                        run_directory=run_directory,
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
                recovery.checkpoint(run_directory / "recovery")
        finally:
            stop.set()
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
        quality_path = freeze_quality(run_directory, universe)
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
