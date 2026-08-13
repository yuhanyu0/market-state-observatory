from __future__ import annotations

import re
from pathlib import Path, PurePath
from typing import Any

import yaml

from ..security import assert_public_safe

POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "publication_policy.yml"


class PublicationPolicyError(ValueError):
    pass


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicationPolicyError("Publication policy must be an object")
    return payload


def _key_matches(key: str, forbidden: set[str]) -> bool:
    lowered = key.lower()
    return lowered in forbidden or any(token in lowered for token in ("credential", "secret", "token"))


def assert_public_payload(payload: Any, policy: dict[str, Any] | None = None) -> None:
    active = policy or load_policy()
    forbidden = {str(item).lower() for item in active["forbidden_fields"]}
    path_pattern = re.compile(r"(?:[A-Za-z]:\\|/Users/|/home/|%LOCALAPPDATA%)", re.I)

    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if _key_matches(str(key), forbidden):
                    raise PublicationPolicyError(
                        f"Publication rejected: forbidden field {'.'.join((*path, str(key)))}"
                    )
                if str(key) == "real_order_created" and child is True:
                    raise PublicationPolicyError("Publication rejected: real_order_created=true")
                if str(key) in {"paper_positions", "positions", "orders"} and child not in (0, [], None):
                    raise PublicationPolicyError(f"Publication rejected: non-empty {key}")
                walk(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))
        elif isinstance(value, str) and path_pattern.search(value):
            raise PublicationPolicyError(
                f"Publication rejected: local filesystem path at {'.'.join(path)}"
            )

    walk(payload)
    assert_public_safe(payload)


def assert_destination_allowed(destination: Path, repository_root: Path) -> None:
    allowed = (repository_root.resolve() / "public" / "data").resolve()
    resolved = destination.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise PublicationPolicyError("Public output may be written only below public/data/")
    forbidden_parts = {"raw", "private", "data_shadow", "model_shadow", "orders", "positions"}
    if forbidden_parts & {part.lower() for part in PurePath(resolved).parts}:
        raise PublicationPolicyError("Public destination contains a forbidden path segment")
