from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.security import audit_public_tree


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    findings: list[str] = []
    for relative in ("public", "examples"):
        findings.extend(audit_public_tree(root / relative))
    for json_file in sorted((root / "public" / "data").rglob("*.json")):
        try:
            json.loads(json_file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            findings.append(f"{json_file}: invalid public JSON ({type(error).__name__})")
    forbidden_directories = {
        "broker", "credentials", "data_shadow", "model_shadow", "orders",
        "positions", "private", "provider_payloads", "raw", "secrets",
    }
    ignored_directories = {
        ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
        "dist", "node_modules", "playwright-report", "site", "test-results",
    }
    for path in sorted(root.rglob("*")):
        if path.is_file() and not ignored_directories.intersection(path.parts) and forbidden_directories.intersection(
            part.lower() for part in path.relative_to(root).parts
        ):
            findings.append(f"{path}: forbidden private path in public repository")
    if findings:
        raise SystemExit("FAIL\n" + "\n".join(findings))
    print("PASS: publication boundary, secret patterns, order/position fields, and public JSON")


if __name__ == "__main__":
    main()
