from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .alpaca_adapter import INGESTION_VERSION, PARSER_VERSION, PROVIDER, AlpacaSIPAdapter
from .observation_freezer import canonical_json, freeze_provider_response, write_exclusive


class AlpacaStreamArchive:
    """Reconnectable private SIP stream archive; never publishes provider payloads."""

    def __init__(self, raw_directory: Path, manifest_directory: Path) -> None:
        self.raw_directory = raw_directory
        self.manifest_directory = manifest_directory
        self.message_count = 0
        self.reconnect_count = 0

    async def on_message(self, item: dict[str, Any], raw: bytes) -> None:
        event_time = str(item.get("t", datetime.now(UTC).isoformat()))
        observation_id = f"ws-{datetime.now(UTC).strftime('%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
        freeze_provider_response(
            raw_directory=self.raw_directory,
            manifest_directory=self.manifest_directory,
            observation_id=observation_id,
            raw_response=raw,
            metadata={
                "source": "alpaca_sip_websocket",
                "provider": PROVIDER,
                "feed": "sip",
                "event_type": item.get("T"),
                "symbol": item.get("S"),
                "event_time_utc": event_time,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "data_max_timestamp": event_time,
                "collector_request_id": observation_id,
                "provider_request_id": None,
                "parser_version": PARSER_VERSION,
                "ingestion_version": INGESTION_VERSION,
            },
        )
        self.message_count += 1


async def archive_stream(
    *,
    symbols: list[str],
    raw_directory: Path,
    manifest_directory: Path,
    stop: asyncio.Event,
) -> AlpacaStreamArchive:
    archive = AlpacaStreamArchive(raw_directory, manifest_directory)
    adapter = AlpacaSIPAdapter()
    try:
        await adapter.stream(symbols, archive.on_message, stop)
    finally:
        archive.reconnect_count = adapter.reconnect_count
        stamp = datetime.now(UTC).strftime("%H%M%S%f")
        write_exclusive(
            manifest_directory / f"stream-health-{stamp}.json",
            canonical_json(
                {
                    "provider": PROVIDER,
                    "feed": "sip",
                    "message_count": archive.message_count,
                    "reconnect_count": archive.reconnect_count,
                    "observed_at_utc": datetime.now(UTC).isoformat(),
                    "private_raw_only": True,
                }
            ),
        )
    return archive


def stream_status(archive: AlpacaStreamArchive) -> str:
    return json.dumps(
        {
            "message_count": archive.message_count,
            "reconnect_count": archive.reconnect_count,
            "private_raw_only": True,
        },
        sort_keys=True,
    )
