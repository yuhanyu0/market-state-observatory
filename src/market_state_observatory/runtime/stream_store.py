from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
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
    freeze_duration_seconds: float
    event_time_dispersion_seconds: float | None
    symbols_requested: int
    symbols_present: int
    latest_state: dict[str, dict[str, dict[str, Any]]]


@dataclass
class _OpenChunk:
    hour: str
    partial_path: Path
    final_path: Path
    checkpoint_path: Path
    handle: BinaryIO
    compressor: Any
    message_count: int = 0
    durable_message_count: int = 0
    messages_since_checkpoint: int = 0
    earliest_event_time: str | None = None
    latest_event_time: str | None = None
    last_checkpoint_monotonic: float = 0.0


class StreamDiskBudgetExceeded(RuntimeError):
    pass


class LateStreamRecordError(RuntimeError):
    pass


class BoundedHourlyStreamStore:
    """Latest-state cache plus durable, immutable hourly compressed chunks."""

    def __init__(
        self,
        *,
        chunk_directory: Path,
        manifest_directory: Path,
        queue_size: int = 10_000,
        disk_budget_bytes: int = 2 * 1024 * 1024 * 1024,
        full_stream_debug: bool = False,
        checkpoint_message_interval: int = 10_000,
        checkpoint_seconds: float = 10.0,
    ) -> None:
        self.chunk_directory = chunk_directory
        self.manifest_directory = manifest_directory
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=queue_size)
        self.disk_budget_bytes = disk_budget_bytes
        self.full_stream_debug = full_stream_debug
        self.checkpoint_message_interval = max(1, checkpoint_message_interval)
        self.checkpoint_seconds = max(0.0, checkpoint_seconds)
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
        self.recovered_partial_count = 0
        self.recovery_discarded_bytes = 0
        self.symbols_seen: set[str] = set()

    async def start(self) -> None:
        if self._worker is not None:
            raise RuntimeError("Stream store already started")
        self.chunk_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.manifest_directory.glob("stream-*.manifest.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            count = int(payload.get("message_count", 0))
            self.message_count += count
            self.written_message_count += count
            self.bytes_written += int(payload.get("compressed_bytes", 0))
        self._worker = asyncio.create_task(self._consume(), name="mso-stream-chunk-writer")

    async def ingest(
        self,
        item: dict[str, Any],
        raw: bytes | None = None,
        *,
        observed_at: datetime | None = None,
    ) -> None:
        event_type = str(item.get("T", ""))
        symbol = str(item.get("S", ""))
        event_time = str(item.get("t", ""))
        if event_type not in EVENT_FIELDS or not symbol or not event_time:
            return
        observed = (observed_at or datetime.now(UTC)).astimezone(UTC).isoformat()
        provider_payload = {key: item[key] for key in EVENT_FIELDS[event_type] if key in item}
        record: dict[str, Any] = {
            "event_type": event_type,
            "symbol": symbol,
            "event_time_utc": event_time,
            "observed_at_utc": observed,
            "provider_payload": provider_payload,
        }
        if self.full_stream_debug and raw is not None:
            assert_credential_values_absent(raw)
            record["raw_envelope_sha256"] = sha256_bytes(raw)
            record["raw_envelope"] = raw.decode("utf-8", errors="replace")
        async with self._latest_lock:
            self.latest.setdefault(symbol, {})[event_type] = copy.deepcopy(record)
            self.symbols_seen.add(symbol)
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
        event_times: list[datetime] = []
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
            freeze_duration_seconds=(completed - started).total_seconds(),
            event_time_dispersion_seconds=(
                (latest - earliest).total_seconds() if earliest and latest else None
            ),
            symbols_requested=len(symbols),
            symbols_present=sum(bool(rows) for rows in state.values()),
            latest_state=state,
        )

    async def drain(self) -> None:
        await self.queue.join()

    async def stop(self) -> None:
        if self._worker is None:
            return
        await self.queue.put(None)
        await self._worker
        self._worker = None

    async def abort_without_finalizing(self) -> None:
        """Crash-test hook: retain only prior durable checkpoints and finalized hours."""
        await self.queue.join()
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        for chunk in self._chunks.values():
            try:
                chunk.compressor.close()
            finally:
                chunk.handle.close()
        self._chunks.clear()

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
        for hour in sorted(tuple(self._chunks)):
            self._finalize_chunk(hour)

    def _write_record(self, record: dict[str, Any]) -> None:
        observed = datetime.fromisoformat(str(record["observed_at_utc"]).replace("Z", "+00:00"))
        hour = observed.astimezone(UTC).strftime("%Y%m%dT%H")
        for old_hour in sorted(value for value in self._chunks if value < hour):
            self._finalize_chunk(old_hour)
        chunk = self._chunks.get(hour)
        if chunk is None:
            chunk = self._open_chunk(hour)
            self._chunks[hour] = chunk
        line = canonical_json(record)
        chunk.compressor.write(line)
        chunk.message_count += 1
        chunk.messages_since_checkpoint += 1
        self.written_message_count += 1
        event = str(record["event_time_utc"])
        chunk.earliest_event_time = min(chunk.earliest_event_time or event, event)
        chunk.latest_event_time = max(chunk.latest_event_time or event, event)
        elapsed = time.monotonic() - chunk.last_checkpoint_monotonic
        if (
            chunk.messages_since_checkpoint >= self.checkpoint_message_interval
            or elapsed >= self.checkpoint_seconds
        ):
            self._checkpoint_chunk(chunk, reopen=True)
        if self.written_message_count % 10_000 == 0 and self.disk_usage_bytes() > self.disk_budget_bytes:
            raise StreamDiskBudgetExceeded("Private stream disk budget exceeded")

    def _open_chunk(self, hour: str) -> _OpenChunk:
        partial = self.chunk_directory / f"stream-{hour}.ndjson.zst.partial"
        final = self.chunk_directory / f"stream-{hour}.ndjson.zst"
        checkpoint = self.manifest_directory / f"stream-{hour}.checkpoint.json"
        manifest = self.manifest_directory / f"stream-{hour}.manifest.json"
        if final.exists() or manifest.exists():
            raise LateStreamRecordError(f"Immutable stream hour is already finalized: {hour}")
        recovered_count = 0
        earliest: str | None = None
        latest: str | None = None
        handle: BinaryIO
        if partial.exists():
            original_size = partial.stat().st_size
            durable_bytes = 0
            if checkpoint.is_file():
                recovery = json.loads(checkpoint.read_text(encoding="utf-8"))
                durable_bytes = int(recovery["durable_bytes"])
                recovered_count = int(recovery["durable_message_count"])
                earliest = recovery.get("earliest_event_time_utc")
                latest = recovery.get("latest_event_time_utc")
                if durable_bytes < 0 or durable_bytes > original_size:
                    raise RuntimeError("Stream checkpoint exceeds partial chunk length")
                self.recovered_partial_count += 1
            self.recovery_discarded_bytes += original_size - durable_bytes
            handle = partial.open("r+b")
            handle.truncate(durable_bytes)
            handle.seek(0, os.SEEK_END)
            if checkpoint.exists() and durable_bytes == 0:
                checkpoint.unlink()
        else:
            handle = partial.open("xb")
        compressor = zstd.ZstdCompressor(level=6).stream_writer(handle, closefd=False)
        if recovered_count:
            self.message_count += recovered_count
            self.written_message_count += recovered_count
        return _OpenChunk(
            hour=hour,
            partial_path=partial,
            final_path=final,
            checkpoint_path=checkpoint,
            handle=handle,
            compressor=compressor,
            message_count=recovered_count,
            durable_message_count=recovered_count,
            earliest_event_time=earliest,
            latest_event_time=latest,
            last_checkpoint_monotonic=time.monotonic(),
        )

    @staticmethod
    def _atomic_replace(path: Path, payload: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _checkpoint_chunk(self, chunk: _OpenChunk, *, reopen: bool) -> None:
        chunk.compressor.close()
        chunk.handle.flush()
        os.fsync(chunk.handle.fileno())
        durable_bytes = chunk.handle.tell()
        checkpoint = {
            "schema_version": "mso-private-stream-checkpoint-v1",
            "hour_utc": chunk.hour,
            "durable_bytes": durable_bytes,
            "durable_message_count": chunk.message_count,
            "earliest_event_time_utc": chunk.earliest_event_time,
            "latest_event_time_utc": chunk.latest_event_time,
            "checkpointed_at_utc": datetime.now(UTC).isoformat(),
        }
        self._atomic_replace(chunk.checkpoint_path, canonical_json(checkpoint))
        chunk.durable_message_count = chunk.message_count
        chunk.messages_since_checkpoint = 0
        chunk.last_checkpoint_monotonic = time.monotonic()
        if reopen:
            chunk.compressor = zstd.ZstdCompressor(level=6).stream_writer(
                chunk.handle, closefd=False
            )

    def _finalize_chunk(self, hour: str) -> None:
        chunk = self._chunks[hour]
        self._checkpoint_chunk(chunk, reopen=False)
        chunk.handle.close()
        os.replace(chunk.partial_path, chunk.final_path)
        content = chunk.final_path.read_bytes()
        self.bytes_written += len(content)
        manifest = {
            "schema_version": "mso-private-stream-chunk-v2",
            "hour_utc": hour,
            "relative_chunk_name": chunk.final_path.name,
            "chunk_sha256": hashlib.sha256(content).hexdigest(),
            "compressed_bytes": len(content),
            "message_count": chunk.message_count,
            "earliest_event_time_utc": chunk.earliest_event_time,
            "latest_event_time_utc": chunk.latest_event_time,
            "durable_before_session_end": True,
            "full_stream_debug": self.full_stream_debug,
            "immutable": True,
            "paper_positions": 0,
            "real_orders": 0,
        }
        write_exclusive(
            self.manifest_directory / f"stream-{hour}.manifest.json", canonical_json(manifest)
        )
        if chunk.checkpoint_path.exists():
            chunk.checkpoint_path.unlink()
        del self._chunks[hour]

    def health_payload(self) -> dict[str, Any]:
        finalized = len(list(self.chunk_directory.glob("*.ndjson.zst")))
        return {
            "message_count": self.message_count,
            "written_message_count": self.written_message_count,
            "queue_capacity": self.queue.maxsize,
            "queue_depth": self.queue.qsize(),
            "queue_high_watermark": self.queue_high_watermark,
            "backpressure_count": self.backpressure_count,
            "dropped_message_count": self.dropped_message_count,
            "symbols_seen": len(self.symbols_seen),
            "finalized_chunk_count": finalized,
            "open_chunk_count": len(self._chunks),
            "chunk_count": finalized + len(self._chunks),
            "compressed_bytes": self.bytes_written,
            "disk_budget_bytes": self.disk_budget_bytes,
            "disk_budget_used_bytes": self.disk_usage_bytes(),
            "recovered_partial_count": self.recovered_partial_count,
            "recovery_discarded_bytes": self.recovery_discarded_bytes,
            "checkpoint_message_interval": self.checkpoint_message_interval,
            "checkpoint_seconds": self.checkpoint_seconds,
            "full_stream_debug": self.full_stream_debug,
        }


def reconstruct_chunk(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as source, zstd.ZstdDecompressor().stream_reader(source) as reader:
        payload = reader.read()
    return [json.loads(line) for line in payload.splitlines() if line]
