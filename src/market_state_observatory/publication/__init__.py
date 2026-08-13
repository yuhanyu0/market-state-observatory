from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..validation import validate_payload
from .policy import assert_destination_allowed, assert_public_payload


def write_public_json(
    payload: Any,
    schema_name: str,
    destination: Path,
    root: Path,
) -> Path:
    assert_public_payload(payload)
    validate_payload(payload, schema_name)
    assert_destination_allowed(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


__all__ = ["write_public_json"]
