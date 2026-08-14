from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .observation_freezer import canonical_json


class _Store(Protocol):
    def health_payload(self) -> dict[str, Any]: ...


class _Archive(Protocol):
    @property
    def store(self) -> _Store: ...

    @property
    def websocket_connected(self) -> bool: ...

    @property
    def last_message_at_utc(self) -> str | None: ...


def write_runtime_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(canonical_json(payload))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def heartbeat_payload(
    *,
    archive: _Archive,
    run: dict[str, Any],
    universe_size: int,
    state: dict[str, Any],
    sequence: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    next_event_value = state.get("next_event_at_utc")
    next_event = (
        datetime.fromisoformat(str(next_event_value).replace("Z", "+00:00")).astimezone(UTC)
        if next_event_value
        else None
    )
    last_message = (
        datetime.fromisoformat(archive.last_message_at_utc.replace("Z", "+00:00")).astimezone(UTC)
        if archive.last_message_at_utc
        else None
    )
    health = archive.store.health_payload()
    used = int(health.get("disk_budget_used_bytes", 0))
    budget = int(health.get("disk_budget_bytes", 0))
    return {
        "schema_version": "mso-private-runtime-heartbeat-v1",
        "heartbeat_sequence": sequence,
        "heartbeat_at_utc": observed.isoformat(),
        "runtime_status": state.get("runtime_status", "RUNNING"),
        "phase": state.get("phase", "INITIALIZING"),
        "run_id": run["run_id"],
        "experiment_lane": run["experiment_lane"],
        "next_event": state.get("next_event"),
        "next_event_at_utc": next_event.isoformat() if next_event else None,
        "countdown_seconds": max(0.0, (next_event - observed).total_seconds()) if next_event else None,
        "websocket_connected": bool(archive.websocket_connected),
        "last_message_at_utc": archive.last_message_at_utc,
        "last_message_age_seconds": (
            max(0.0, (observed - last_message).total_seconds()) if last_message else None
        ),
        "symbols_seen": int(health.get("symbols_seen", 0)),
        "universe_symbols": universe_size,
        "message_count": int(health.get("message_count", 0)),
        "written_message_count": int(health.get("written_message_count", 0)),
        "queue_depth": int(health.get("queue_depth", 0)),
        "queue_high_watermark": int(health.get("queue_high_watermark", 0)),
        "backpressure_count": int(health.get("backpressure_count", 0)),
        "dropped_message_count": int(health.get("dropped_message_count", 0)),
        "disk_usage_bytes": used,
        "disk_budget_bytes": budget,
        "disk_budget_fraction": used / budget if budget else None,
        "finalized_chunk_count": int(health.get("finalized_chunk_count", 0)),
        "open_chunk_count": int(health.get("open_chunk_count", 0)),
        "last_completed_snapshot": state.get("last_completed_snapshot"),
        "paper_positions": 0,
        "real_orders": 0,
    }


async def run_heartbeat(
    *,
    path: Path,
    archive: _Archive,
    run: dict[str, Any],
    universe_size: int,
    state: dict[str, Any],
    stop: asyncio.Event,
    interval_seconds: float = 15.0,
) -> None:
    sequence = 0
    while not stop.is_set():
        sequence += 1
        write_runtime_status(
            path,
            heartbeat_payload(
                archive=archive,
                run=run,
                universe_size=universe_size,
                state=state,
                sequence=sequence,
            ),
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
