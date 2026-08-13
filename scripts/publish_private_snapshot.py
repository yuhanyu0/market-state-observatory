from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from market_state_observatory.publication.git_publisher import publish_public_data
from market_state_observatory.publication.manifest import build_publication_manifest
from market_state_observatory.publication.policy import (
    assert_destination_allowed,
    assert_public_payload,
)
from market_state_observatory.publication.public_projection import (
    project_data_quality,
    project_public_status,
)
from market_state_observatory.runtime.observation_freezer import canonical_json, write_exclusive
from market_state_observatory.runtime.runtime_paths import resolve_runtime_paths
from market_state_observatory.validation import validate_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project private data quality into public-data")
    parser.add_argument("quality", type=Path)
    parser.add_argument("--push", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = resolve_runtime_paths(repo_root=root, create=True)
    private_quality = json.loads(args.quality.read_text(encoding="utf-8"))
    public_payload = project_data_quality(private_quality)
    assert_public_payload(public_payload)
    validate_payload(public_payload, "public_data_quality", root)
    valid_days = sum(
        1
        for path in paths.data_shadow.glob("????-??-??/*/quality/DATA_QUALITY.json")
        if json.loads(path.read_text(encoding="utf-8")).get("counts_toward_20_day_gate") is True
    )
    public_status = project_public_status(private_quality, valid_days)
    validate_payload(public_status, "publication_status", root)
    snapshot_id = f"{public_payload['trading_date']}-{datetime.now(UTC).strftime('%H%M%S%f')}"
    staging = paths.public_staging / snapshot_id / "data"
    repository_public = root / "public" / "data"
    assert_destination_allowed(repository_public, root)
    if repository_public.exists():
        shutil.copytree(repository_public, staging, dirs_exist_ok=True)
    write_exclusive(
        staging / "data-quality" / f"{snapshot_id}.json",
        canonical_json(public_payload),
    )
    status_path = staging / "status.json"
    if status_path.exists():
        status_path.unlink()
    write_exclusive(status_path, canonical_json(public_status))
    manifest_path = staging / "PUBLICATION_MANIFEST.csv"
    build_publication_manifest(staging, manifest_path)
    result = publish_public_data(
        repository=root,
        staged_data=staging,
        worktree=paths.public_staging / f"worktree-{snapshot_id}",
        commit_message=f"data: publish redacted snapshot {public_payload['trading_date']}",
        push=args.push,
    )
    print(f"PUBLICATION_RESULT={result}")
    print("RAW_MARKET_DATA_PUBLISHED=false")
    print("PAPER_POSITIONS=0")
    print("REAL_ORDERS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
