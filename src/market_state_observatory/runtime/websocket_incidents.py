from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from market_state_observatory.validation import validate_payload

EVENT_TYPES = {
    "connecting",
    "authenticated",
    "subscribed",
    "disconnected",
    "timeout",
    "exception",
    "reconnect_scheduled",
    "reconnect_attempt",
    "reauthenticated",
    "resubscribed",
    "first_message_after_reconnect",
    "connection_closed",
}


class WebSocketIncidentLedger:
    """Append-only, credential-free connection lifecycle evidence."""

    def __init__(self, path: Path, *, release_version: str, run_id: str):
        self.path = path
        self.release_version = release_version
        self.run_id = run_id
        self._gap_started: str | None = None
        self._last_message: str | None = None
        self._reconnect_attempt = 0

    def note_message(self, event_time_utc: str | None = None) -> None:
        self._last_message = event_time_utc or datetime.now(UTC).isoformat()

    def append(
        self,
        event_type: str,
        *,
        event_time_utc: str | None = None,
        exception: BaseException | None = None,
        close_code: int | str | None = None,
        safe_reason: str | None = None,
        symbols_seen: list[str] | None = None,
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unsupported WebSocket event type: {event_type}")
        observed = datetime.now(UTC)
        event_time = event_time_utc or observed.isoformat()
        if event_type in {"disconnected", "timeout", "exception"} and self._gap_started is None:
            self._gap_started = event_time
        if event_type == "reconnect_attempt":
            self._reconnect_attempt += 1
        gap_end = event_time if event_type == "first_message_after_reconnect" else None
        gap_duration = None
        if gap_end and self._gap_started:
            gap_duration = max(0.0, (datetime.fromisoformat(gap_end) - datetime.fromisoformat(self._gap_started)).total_seconds())
        reason_hash = sha256(safe_reason.encode()).hexdigest() if safe_reason else None
        payload = {
            "schema_version": "mso-websocket-connection-event-v1",
            "event_id": str(uuid4()),
            "event_time_utc": event_time,
            "observed_at_utc": observed.isoformat(),
            "event_type": event_type,
            "safe_exception_type": type(exception).__name__ if exception else None,
            "safe_close_code": close_code,
            "safe_reason_hash": reason_hash,
            "reconnect_attempt_number": self._reconnect_attempt if self._reconnect_attempt else None,
            "gap_started_at_utc": self._gap_started,
            "gap_ended_at_utc": gap_end,
            "gap_duration_seconds": gap_duration,
            "last_message_before_gap": self._last_message,
            "first_message_after_gap": gap_end,
            "symbols_seen_after_reconnect": sorted(set(symbols_seen or [])),
            "release_version": self.release_version,
            "run_id": self.run_id,
        }
        validate_payload(payload, "websocket_connection_event")
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if gap_end:
            self._gap_started = None
        return payload


def read_connection_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
