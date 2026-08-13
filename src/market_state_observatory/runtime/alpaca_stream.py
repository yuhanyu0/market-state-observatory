from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .alpaca_adapter import PROVIDER, AlpacaSIPAdapter
from .observation_freezer import canonical_json, write_exclusive
from .stream_store import BoundedHourlyStreamStore


class AlpacaStreamArchive:
    """SIP latest-state cache plus bounded immutable hourly stream chunks."""

    def __init__(
        self,
        raw_directory: Path,
        manifest_directory: Path,
        *,
        queue_size: int = 10_000,
        disk_budget_bytes: int = 2 * 1024 * 1024 * 1024,
        full_stream_debug: bool | None = None,
    ) -> None:
        debug = (
            os.environ.get("MSO_FULL_STREAM_DEBUG", "false").lower() == "true"
            if full_stream_debug is None
            else full_stream_debug
        )
        self.store = BoundedHourlyStreamStore(
            chunk_directory=raw_directory,
            manifest_directory=manifest_directory / "chunks",
            queue_size=queue_size,
            disk_budget_bytes=disk_budget_bytes,
            full_stream_debug=debug,
        )
        self.manifest_directory = manifest_directory
        self.reconnect_count = 0
        self.last_message_at_utc: str | None = None

    async def on_message(self, item: dict[str, Any], raw: bytes) -> None:
        await self.store.ingest(item, raw)
        self.last_message_at_utc = datetime.now(UTC).isoformat()

    async def run(
        self, *, symbols: list[str], stop: asyncio.Event, adapter: AlpacaSIPAdapter | None = None
    ) -> None:
        provider = adapter or AlpacaSIPAdapter()
        await self.store.start()
        try:
            await provider.stream(symbols, self.on_message, stop)
        finally:
            self.reconnect_count = provider.reconnect_count
            await self.store.stop()
            stamp = datetime.now(UTC).strftime("%H%M%S%f")
            write_exclusive(
                self.manifest_directory / f"stream-health-{stamp}.json",
                canonical_json(
                    {
                        "provider": PROVIDER,
                        "feed": "sip",
                        **self.store.health_payload(),
                        "reconnect_count": self.reconnect_count,
                        "last_message_at_utc": self.last_message_at_utc,
                        "observed_at_utc": datetime.now(UTC).isoformat(),
                        "private_raw_only": True,
                    }
                ),
            )


async def archive_stream(
    *,
    symbols: list[str],
    raw_directory: Path,
    manifest_directory: Path,
    stop: asyncio.Event,
) -> AlpacaStreamArchive:
    archive = AlpacaStreamArchive(raw_directory, manifest_directory)
    await archive.run(symbols=symbols, stop=stop)
    return archive


def stream_status(archive: AlpacaStreamArchive) -> dict[str, Any]:
    return {
        **archive.store.health_payload(),
        "reconnect_count": archive.reconnect_count,
        "last_message_at_utc": archive.last_message_at_utc,
        "private_raw_only": True,
    }
