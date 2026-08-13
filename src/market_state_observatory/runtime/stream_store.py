from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import zstandard as zstd

from ..security import assert_credential_values_absent
from .observation_freezer import canonical_json, sha256_bytes, write_exclusive

EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "q": ("T", "S", "t", "bp", "ap", "bs", "as", "c", "z"),
    "t": ("T", "S", "t", "p", "s", "x", "c", "i", "z"),
    "b": ("T", "S", "t", "o", "h", "l", "c", "v", "vw", "n"),
}


@dataclass(frozen=True)
class CrossSectionFreeze:
    scheduled_at_utc: str
    freeze_started_at_utc: str
    freeze_completed_at_utc: str
    earliest_event_time_utc: str | None
    latest_event_time_utc: str | None
    cross_section_skew_seconds: float | None
    symbols_requested: int
    symbols_present: int
    latest_state: dict[str, dict[str, dict[str, Any]]]


@dataclass
class _OpenChunk:
    hour: str
    partial_path: Path
    final_path: Path
    handle: BinaryIO
    compressor: Any
    message_count: int = 0
    earliest_event_time: str | None = None
    latest_event_time: str | None = None


class StreamDiskBudgetExceeded(RuntimeError):
    pass


class BoundedHourlyStreamStore:
    """Bounded stream cache with immutable hourly compressed chunks."""

    def __init__(
        self,
        *,
        chunk_directory: Path,
        manifest_directory: Path,
        queue_size: int = 10_000,
        disk_budget_bytes: int = 2 * 1024 * 1024 * 1024,
        full_stream_debug: bool = False,
    ) -> None:
        self.chunk_directory = chunk_directory
        self.manifest_directory = manifest_directory
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=queue_size)
        self.disk_budget_bytes = disk_budget_bytes
        self.full_stream_debug = full_stream_debug
        self.latest: dict[str, dict[str, dict[str, Any]]] = {}
        self._latest_lock = asyncio.Lock()
        self._chunks: dict[str, _OpenChunk] = {}
        self._worker: asyncio.Task[None] | None = None
        self.message_count = 0
        self.written_message_count = 0
        self.queue_high_watermark = 0
        self.backpressure_count = 0
        self.dropped_message_count = 0
        self.bytes_written = 0

    async def start(self) -> None:
        if self._worker is not None:
            raise RuntimeError("Stream store already started")
        self.chunk_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_directory.mkdir(parents=True, exist_ok=True)
        self._worker = asyncio.create_task(self._consume(), name="mso-stream-chunk-writer")

    async def ingest(self, item: dict[str, Any], raw: bytes | None = None) -> None:
        event_type = str(item.get("T", ""))
        symbol = str(item.get("S", ""))
        event_time = str(item.get("t", ""))
        if event_type not in EVENT_FIELDS or not symbol or not event_time:
            return
        observed_at = datetime.now(UTC).isoformat()
        normalized = {key: item[key] for key in EVENT_FIELDS[event_type] if key in item}
        record: dict[str, Any] = {
            "event_type": event_type,
            "symbol": symbol,
            "event_time_utc": event_time,
            "observed_at_utc": observed_at,
            "payload": normalized,
        }
        if self.full_stream_debug and raw is not None:
            assert_credential_values_absent(raw)
            record["raw_envelope_sha256"] = sha256_bytes(raw)
            record["raw_envelope"] = raw.decode("utf-8", errors="replace")
        async with self._latest_lock:
            self.latest.setdefault(symbol, {})[event_type] = copy.deepcopy(record)
        if self.queue.full():
            self.backpressure_count += 1
        await self.queue.put(record)
        self.message_count += 1
        self.queue_high_watermark = max(self.queue_high_watermark, self.queue.qsize())

    async def freeze_cross_section(
        self, symbols: list[str], scheduled_at: datetime
    ) -> CrossSectionFreeze:
        started = datetime.now(UTC)
        async with self._latest_lock:
            state = {symbol: copy.deepcopy(self.latest.get(symbol, {})) for symbol in symbols}
        completed = datetime.now(UTC)
        event_times = []
        for rows in state.values():
            symbol_times = [
                datetime.fromisoformat(str(record["event_time_utc"]).replace("Z", "+00:00"))
                for record in rows.values()
            ]
            if symbol_times:
                event_times.append(max(symbol_times))
        earliest = min(event_times) if event_times else None
        latest = max(event_times) if event_times else None
        return CrossSectionFreeze(
            scheduled_at_utc=scheduled_at.astimezone(UTC).isoformat(),
            freeze_started_at_utc=started.isoformat(),
            freeze_completed_at_utc=completed.isoformat(),
            earliest_event_time_utc=earliest.isoformat() if earliest else None,
            latest_event_time_utc=latest.isoformat() if latest else None,
            cross_section_skew_seconds=(latest - earliest).total_seconds() if earliest and latest else None,
            symbols_requested=len(symbols),
            symbols_present=sum(bool(rows) for rows in state.values()),
            latest_state=state,
        )

    async def stop(self) -> None:
        if self._worker is None:
            return
        await self.queue.put(None)
        await self._worker
        self._worker = None

    def disk_usage_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.chunk_directory.glob("*") if path.is_file())

    async def _consume(self) -> None:
        while True:
            record = await self.queue.get()
            try:
                if record is None:
                    break
                self._write_record(record)
            finally:
                self.queue.task_done()
        for hour in sorted(self._chunks):
            self._finalize_chunk(hour)

    def _write_record(self, record: dict[str, Any]) -> None:
        event_time = datetime.fromisoformat(str(record["event_time_utc"]).replace("Z", "+00:00"))
        hour = event_time.astimezone(UTC).strftime("%Y%m%dT%H")
        chunk = self._chunks.get(hour)
        if chunk is None:
            partial = self.chunk_directory / f"stream-{hour}.ndjson.zst.partial"
            final = self.chunk_directory / f"stream-{hour}.ndjson.zst"
            if partial.exists() or final.exists():
                raise FileExistsError(f"Immutable stream chunk already exists: {final}")
            handle = partial.open("xb")
            compressor = zstd.ZstdCompressor(level=6).stream_writer(handle, closefd=False)
            chunk = _OpenChunk(hour, partial, final, handle, compressor)
            self._chunks[hour] = chunk
        line = canonical_json(record)
        chunk.compressor.write(line)
        chunk.message_count += 1
        self.written_message_count += 1
        event = str(record["event_time_utc"])
        chunk.earliest_event_time = min(chunk.earliest_event_time or event, event)
        chunk.latest_event_time = max(chunk.latest_event_time or event, event)
        if self.written_message_count % 10_000 == 0 and self.disk_usage_bytes() > self.disk_budget_bytes:
            raise StreamDiskBudgetExceeded("Private stream disk budget exceeded")

    def _finalize_chunk(self, hour: str) -> None:
        chunk = self._chunks[hour]
        chunk.compressor.flush(zstd.FLUSH_FRAME)
        chunk.compressor.close()
        chunk.handle.flush()
        os.fsync(chunk.handle.fileno())
        chunk.handle.close()
        os.replace(chunk.partial_path, chunk.final_path)
        content = chunk.final_path.read_bytes()
        self.bytes_written += len(content)
        manifest = {
            "schema_version": "mso-private-stream-chunk-v1",
            "hour_utc": hour,
            "relative_chunk_name": chunk.final_path.name,
            "chunk_sha256": hashlib.sha256(content).hexdigest(),
            "compressed_bytes": len(content),
            "message_count": chunk.message_count,
            "earliest_event_time_utc": chunk.earliest_event_time,
            "latest_event_time_utc": chunk.latest_event_time,
            "full_stream_debug": self.full_stream_debug,
            "immutable": True,
            "paper_positions": 0,
            "real_orders": 0,
        }
        write_exclusive(
            self.manifest_directory / f"stream-{hour}.manifest.json", canonical_json(manifest)
        )

    def health_payload(self) -> dict[str, Any]:
        return {
            "message_count": self.message_count,
            "written_message_count": self.written_message_count,
            "queue_capacity": self.queue.maxsize,
            "queue_high_watermark": self.queue_high_watermark,
            "backpressure_count": self.backpressure_count,
            "dropped_message_count": self.dropped_message_count,
            "chunk_count": len(self._chunks),
            "compressed_bytes": self.bytes_written,
            "disk_budget_bytes": self.disk_budget_bytes,
            "disk_budget_used_bytes": self.disk_usage_bytes(),
            "full_stream_debug": self.full_stream_debug,
        }


def reconstruct_chunk(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as source, zstd.ZstdDecompressor().stream_reader(source) as reader:
        payload = reader.read()
    return [json.loads(line) for line in payload.splitlines() if line]
