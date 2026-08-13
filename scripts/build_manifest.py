from __future__ import annotations

import csv
import hashlib
from pathlib import Path

EXCLUDED_PARTS = {
    ".cache", ".git", ".mypy_cache", ".pytest-runtime-cache", ".pytest-tmp",
    ".pytest_cache", ".ruff_cache", ".tmp", ".venv", "__pycache__", "dist",
    "node_modules", "playwright-report", "release-artifacts", "site", "test-results",
}
EXCLUDED_NAMES = {"PROJECT_MANIFEST.csv", "PROJECT_MANIFEST.sha256"}
EXCLUDED_SUFFIXES = {".tsbuildinfo"}
BINARY_SUFFIXES = {".ico", ".jpeg", ".jpg", ".pdf", ".png", ".zip"}


def canonical_content(path: Path) -> bytes:
    content = path.read_bytes()
    return content if path.suffix.lower() in BINARY_SUFFIXES else content.replace(b"\r\n", b"\n")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rows: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or EXCLUDED_PARTS.intersection(path.parts)
            or path.name in EXCLUDED_NAMES
            or path.suffix in EXCLUDED_SUFFIXES
        ):
            continue
        relative = path.relative_to(root).as_posix()
        content = canonical_content(path)
        rows.append((relative, hashlib.sha256(content).hexdigest(), len(content)))
    manifest = root / "PROJECT_MANIFEST.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["relative_path", "sha256", "file_size"])
        writer.writerows(rows)
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (root / "PROJECT_MANIFEST.sha256").write_text(f"{digest}  PROJECT_MANIFEST.csv\n", encoding="ascii")
    print(f"files={len(rows)} sha256={digest}")


if __name__ == "__main__":
    main()
