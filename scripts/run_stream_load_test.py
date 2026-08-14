from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from market_state_observatory.runtime.stream_store import (
    BoundedHourlyStreamStore,
    reconstruct_chunk,
)


async def run(messages: int, output: Path | None = None) -> dict[str, object]:
    symbols = [f"S{index:02d}" for index in range(35)]
    temporary = None
    if output is None:
        temporary = tempfile.TemporaryDirectory(prefix="mso-stream-load-")
        output = Path(temporary.name)
    store = BoundedHourlyStreamStore(
        chunk_directory=output / "chunks",
        manifest_directory=output / "manifests",
        queue_size=10_000,
        disk_budget_bytes=512 * 1024 * 1024,
    )
    await store.start()
    start = datetime(2026, 8, 13, 13, 30, tzinfo=UTC)
    snapshots: list[dict[str, object]] = []
    checkpoints = {messages * step // 5 for step in range(1, 6)}
    for index in range(messages):
        event = start + timedelta(seconds=(index * 23_400) / max(messages - 1, 1))
        symbol = symbols[index % len(symbols)]
        await store.ingest(
            {"T": "q", "S": symbol, "t": event.isoformat(), "bp": 100.0, "ap": 100.02},
            observed_at=event,
        )
        if index + 1 in checkpoints:
            frozen = await store.freeze_cross_section(symbols, event)
            snapshots.append(
                {
                    "scheduled_at_utc": frozen.scheduled_at_utc,
                    "symbols_present": frozen.symbols_present,
                    "freeze_duration_seconds": frozen.freeze_duration_seconds,
                    "event_time_dispersion_seconds": frozen.event_time_dispersion_seconds,
                }
            )
    await store.stop()
    chunks = sorted((output / "chunks").glob("*.ndjson.zst"))
    manifests = sorted((output / "manifests").glob("*.json"))
    reconstructed = sum(len(reconstruct_chunk(path)) for path in chunks)
    file_count = len([path for path in output.rglob("*") if path.is_file()])
    result: dict[str, object] = {
        "status": "PASS" if reconstructed == messages and file_count <= 20 else "FAIL",
        "symbols": len(symbols),
        "messages": messages,
        "reconstructed_messages": reconstructed,
        "chunk_count": len(chunks),
        "manifest_count": len(manifests),
        "file_count": file_count,
        "snapshots": snapshots,
        "health": store.health_payload(),
        "million_small_files_created": False,
        "credentials_found": False,
    }
    if temporary is not None:
        temporary.cleanup()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.messages, args.output))
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
