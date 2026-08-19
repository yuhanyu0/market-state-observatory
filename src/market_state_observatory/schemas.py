from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

SCHEMA_SUFFIX = ".schema.json"


def repo_root() -> Path:
    candidates = []
    if release_root := os.environ.get("MSO_RELEASE_ROOT"):
        candidates.append(Path(release_root).resolve())
    candidates.extend(
        (
            Path(__file__).resolve().parents[2],
            Path(sys.prefix).resolve().parent,
        )
    )
    for candidate in candidates:
        if (candidate / "schemas").is_dir():
            return candidate
    return candidates[0]


def schema_path(name: str, root: Path | None = None) -> Path:
    base = root or repo_root()
    normalized = name.removesuffix(SCHEMA_SUFFIX)
    return base / "schemas" / f"{normalized}{SCHEMA_SUFFIX}"


def load_schema(name: str, root: Path | None = None) -> dict[str, Any]:
    path = schema_path(name, root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Schema must be an object: {path}")
    return cast(dict[str, Any], payload)


def schema_names(root: Path | None = None) -> tuple[str, ...]:
    base = root or repo_root()
    return tuple(
        sorted(
            path.name.removesuffix(SCHEMA_SUFFIX)
            for path in (base / "schemas").glob(f"*{SCHEMA_SUFFIX}")
        )
    )
