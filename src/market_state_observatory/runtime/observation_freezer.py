from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..security import assert_credential_values_absent, scan_text


class ImmutableWriteError(RuntimeError):
    pass


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ImmutableWriteError(f"Immutable artifact already exists: {path}") from error
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class FrozenResponse:
    raw_path: Path
    manifest_path: Path
    raw_response_sha256: str


def freeze_provider_response(
    *,
    raw_directory: Path,
    manifest_directory: Path,
    observation_id: str,
    raw_response: bytes,
    metadata: dict[str, Any],
) -> FrozenResponse:
    decoded = raw_response.decode("utf-8", errors="replace")
    assert_credential_values_absent(raw_response)
    if scan_text(decoded, source=observation_id):
        raise ValueError("Provider response rejected by credential and private-data scanner")
    raw_hash = sha256_bytes(raw_response)
    raw_path = raw_directory / f"{observation_id}.{raw_hash[:12]}.json"
    write_exclusive(raw_path, raw_response)
    manifest = {
        **metadata,
        "observation_id": observation_id,
        "raw_response_sha256": raw_hash,
        "raw_response_path": str(raw_path),
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "immutable": True,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    manifest_path = manifest_directory / f"{observation_id}.manifest.json"
    write_exclusive(manifest_path, canonical_json(manifest))
    return FrozenResponse(raw_path, manifest_path, raw_hash)
