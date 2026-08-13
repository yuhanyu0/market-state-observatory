from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CREDENTIAL_FILE_NAME = "alpaca.credential.xml"
ALLOWED_FEED = "sip"
KEY_ID_NAME = "APCA_API_" + "KEY_ID"
SECRET_NAME = "APCA_API_" + "SECRET_KEY"


class CredentialError(RuntimeError):
    """Credential failure whose message never includes credential material."""


@dataclass(frozen=True)
class CredentialPresence:
    key_id: bool
    secret: bool
    feed: str

    def safe_lines(self) -> tuple[str, str, str]:
        return (
            f"{KEY_ID_NAME}={'PRESENT' if self.key_id else 'ABSENT'}",
            f"{SECRET_NAME}={'PRESENT' if self.secret else 'ABSENT'}",
            f"ALPACA_DATA_FEED={self.feed}",
        )


def credential_path(runtime_root: Path) -> Path:
    return runtime_root / "secrets" / CREDENTIAL_FILE_NAME


def credential_presence(environment: Mapping[str, str] | None = None) -> CredentialPresence:
    source = environment if environment is not None else os.environ
    feed = source.get("ALPACA_DATA_FEED", "sip").lower()
    return CredentialPresence(
        key_id=bool(source.get(KEY_ID_NAME)),
        secret=bool(source.get(SECRET_NAME)),
        feed=feed,
    )


def require_child_process_credentials(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    source = environment if environment is not None else os.environ
    presence = credential_presence(source)
    if presence.feed != ALLOWED_FEED:
        raise CredentialError("ALPACA_DATA_FEED must be sip; fallback feeds are forbidden")
    if not presence.key_id or not presence.secret:
        raise CredentialError("Alpaca credentials are not present in the collector child process")
    return source[KEY_ID_NAME], source[SECRET_NAME]


def safe_credential_status(environment: Mapping[str, str] | None = None) -> str:
    return "\n".join(credential_presence(environment).safe_lines())
