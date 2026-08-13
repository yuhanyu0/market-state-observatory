from __future__ import annotations

from typing import Any

from .policy import assert_public_payload

PRIVATE_KEYS = {
    "raw_response_path",
    "raw_response_sha256",
    "collector_request_id",
    "provider_request_id",
    "request_started_at_utc",
    "sanitized_request_parameters",
    "response_headers_sha256",
    "account_id",
    "order_id",
}


def redact_derived_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop private lineage only from a pre-derived aggregate payload.

    This function intentionally cannot accept raw provider response containers.
    """

    if any(key in payload for key in ("raw_response", "quotes", "trades", "bars")):
        raise ValueError("Raw or near-raw provider payload cannot enter the redactor")

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: walk(child) for key, child in value.items() if key not in PRIVATE_KEYS}
        if isinstance(value, list):
            return [walk(child) for child in value]
        return value

    redacted = walk(payload)
    if not isinstance(redacted, dict):
        raise TypeError("Derived public payload must remain an object")
    assert_public_payload(redacted)
    return redacted
