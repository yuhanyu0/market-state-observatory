from __future__ import annotations

import csv
import hashlib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "PROJECT_MANIFEST.csv"
    digest_file = root / "PROJECT_MANIFEST.sha256"
    expected_digest = digest_file.read_text(encoding="ascii").split()[0]
    actual_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    findings: list[str] = []
    if actual_digest != expected_digest:
        findings.append("manifest digest mismatch")
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            path = root / row["relative_path"]
            if not path.is_file():
                findings.append(f"missing: {row['relative_path']}")
                continue
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                findings.append(f"hash mismatch: {row['relative_path']}")
            if len(content) != int(row["file_size"]):
                findings.append(f"size mismatch: {row['relative_path']}")
    if findings:
        raise SystemExit("FAIL\n" + "\n".join(findings))
    print(f"PASS: manifest {actual_digest}")


if __name__ == "__main__":
    main()
