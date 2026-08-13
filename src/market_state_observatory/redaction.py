from __future__ import annotations

from typing import Any

from .security import assert_public_safe

FORBIDDEN_PUBLIC_KEYS = {
    "account_id",
    "account_number",
    "api_key",
    "api_secret",
    "authorization",
    "broker_position",
    "credential",
    "order_id",
    "provider_payload",
    "raw_response",
    "token",
}


def validate_already_redacted(payload: Any) -> None:
    """Reject unsafe input; never attempt to make private input publishable."""

    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in FORBIDDEN_PUBLIC_KEYS:
                    dotted = ".".join((*path, key))
                    raise ValueError(f"Publication rejected: forbidden field {dotted}")
                walk(child, (*path, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))

    walk(payload)
    assert_public_safe(payload)
