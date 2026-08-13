from __future__ import annotations

from pathlib import Path

from market_state_observatory.security import TEXT_SUFFIXES, scan_text


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    findings: list[str] = []
    ignored = {
        ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
        ".pytest-runtime-cache", ".pytest-tmp", "dist", "node_modules",
        "playwright-report", "site", "test-results",
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ignored.intersection(path.parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.name == "check_secret_patterns.py":
            continue
        try:
            findings.extend(scan_text(path.read_text(encoding="utf-8"), str(path.relative_to(root))))
        except UnicodeDecodeError:
            findings.append(f"{path.relative_to(root)}: undecodable text-like file")
    if findings:
        raise SystemExit("FAIL\n" + "\n".join(findings))
    print("PASS: no credential values, private keys, bearer tokens, account identifiers, or nonzero public position/order markers")


if __name__ == "__main__":
    main()
