from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PRIVATE_PARTS = {
    "broker",
    "credentials",
    "data_shadow",
    "model_shadow",
    "orders",
    "positions",
    "private",
    "provider_payloads",
    "raw",
    "secrets",
}

# Names are assembled so the scanner cannot match its own source text.
_KEY_ID = "APCA_API_" + "KEY_ID"
_SECRET = "APCA_API_" + "SECRET_KEY"
_PRIVATE_KEY = "BEGIN " + "PRIVATE KEY"

SECRET_PATTERNS = (
    re.compile(
        rf"{_KEY_ID}\s*[:=]\s*(?!PRESENT\b|ABSENT\b|MISSING\b|<REDACTED>\b)[^\s]+",
        re.I,
    ),
    re.compile(
        rf"{_SECRET}\s*[:=]\s*(?!PRESENT\b|ABSENT\b|MISSING\b|<REDACTED>\b)[^\s]+",
        re.I,
    ),
    re.compile(_PRIVATE_KEY, re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r'["\']account_number["\']\s*:\s*(?!null\b|["\']REDACTED["\'])', re.I),
    re.compile(r'["\']real_order_created["\']\s*:\s*true\b', re.I),
    re.compile(r'["\']paper_positions["\']\s*:\s*[1-9][0-9]*\b', re.I),
    re.compile(r"Windows\s+Credential\s+(?:dump|export)", re.I),
)


def scan_text(text: str, source: str = "<memory>") -> list[str]:
    return [
        f"{source}: forbidden pattern {index + 1}"
        for index, pattern in enumerate(SECRET_PATTERNS)
        if pattern.search(text)
    ]


def scan_payload(payload: Any, source: str = "<payload>") -> list[str]:
    return scan_text(json.dumps(payload, sort_keys=True), source)


def audit_public_tree(path: Path) -> list[str]:
    findings: list[str] = []
    if not path.exists():
        return [f"{path}: missing public tree"]
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        relative_parts = {part.lower() for part in file.relative_to(path).parts}
        forbidden_parts = relative_parts & PRIVATE_PARTS
        if forbidden_parts:
            findings.append(f"{file}: forbidden public path {sorted(forbidden_parts)}")
        if file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            findings.extend(scan_text(file.read_text(encoding="utf-8"), str(file)))
        except UnicodeDecodeError:
            findings.append(f"{file}: undecodable text-like public file")
    return findings


def assert_public_safe(payload: Any, source: str = "<payload>") -> None:
    findings = scan_payload(payload, source)
    if findings:
        raise ValueError("Publication rejected:\n" + "\n".join(findings))


def credential_values_in_environment() -> tuple[str, ...]:
    return tuple(
        value
        for name in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")
        if (value := os.environ.get(name))
    )


def assert_credential_values_absent(payload: bytes | str) -> None:
    encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
    if any(value.encode("utf-8") in encoded for value in credential_values_in_environment()):
        raise ValueError("Credential material rejected before persistence")
