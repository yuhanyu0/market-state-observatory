from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .schemas import load_schema, schema_names


def validate_payload(payload: Any, schema_name: str, root: Path | None = None) -> None:
    schema = load_schema(schema_name, root)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        details = "\n".join(
            f"{list(error.absolute_path)}: {error.message}" for error in errors
        )
        raise ValueError(details)


def validate_json_file(path: Path, schema_name: str, root: Path | None = None) -> None:
    validate_payload(json.loads(path.read_text(encoding="utf-8")), schema_name, root)


def validate_all_schemas(root: Path | None = None) -> dict[str, str]:
    results: dict[str, str] = {}
    for name in schema_names(root):
        Draft202012Validator.check_schema(load_schema(name, root))
        results[name] = "PASS"
    return results
