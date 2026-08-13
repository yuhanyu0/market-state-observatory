from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from .policy import assert_public_payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_publication_manifest(data_root: Path, output: Path) -> Path:
    rows: list[dict[str, str | int]] = []
    for path in sorted(data_root.rglob("*")):
        if not path.is_file() or path.resolve() == output.resolve():
            continue
        if path.suffix.lower() == ".json":
            import json

            assert_public_payload(json.loads(path.read_text(encoding="utf-8")))
        rows.append(
            {
                "relative_path": path.relative_to(data_root).as_posix(),
                "sha256": sha256_file(path),
                "file_size": path.stat().st_size,
                "frozen_at_utc": datetime.now(UTC).isoformat(),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("relative_path", "sha256", "file_size", "frozen_at_utc")
        )
        writer.writeheader()
        writer.writerows(rows)
    return output
