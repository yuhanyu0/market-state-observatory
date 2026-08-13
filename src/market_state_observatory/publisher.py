from __future__ import annotations

import json
from pathlib import Path

from .publication import write_public_json


def publish_status(status_path: Path, site_dir: Path) -> Path:
    root = site_dir.resolve().parent
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    return write_public_json(payload, "publication_status", root / "public" / "data" / "status.json", root)


def publish_certificate(certificate_path: Path, site_dir: Path) -> Path:
    root = site_dir.resolve().parent
    payload = json.loads(certificate_path.read_text(encoding="utf-8"))
    return write_public_json(payload, "state_certificate", root / "public" / "data" / "certificates" / certificate_path.name, root)
