from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from ..runtime.observation_freezer import canonical_json, write_exclusive
from ..runtime.runtime_lock import RuntimeLock
from ..runtime.runtime_paths import resolve_runtime_paths
from ..validation import validate_payload
from .git_publisher import publish_public_data
from .manifest import build_publication_manifest
from .policy import assert_destination_allowed, assert_public_payload, assert_publication_eligible
from .public_projection import project_data_quality, project_public_status


def validation_root(repository: Path) -> Path:
    release = os.environ.get("MSO_RELEASE_ROOT")
    return Path(release).resolve() if release else repository


def publish_quality_snapshot(*, repository: Path, quality_path: Path, push: bool) -> str:
    repository = repository.resolve()
    paths = resolve_runtime_paths(repo_root=repository, create=True)
    resolved_quality = quality_path.resolve()
    if paths.data_shadow.resolve() not in resolved_quality.parents:
        raise ValueError("Publication quality input must be inside private data_shadow")
    private_quality = json.loads(resolved_quality.read_text(encoding="utf-8"))
    schemas = validation_root(repository)
    validate_payload(private_quality, "private_data_quality", schemas)
    assert_publication_eligible(private_quality)
    public_payload = project_data_quality(private_quality)
    assert_public_payload(public_payload)
    validate_payload(public_payload, "public_data_quality", schemas)
    valid_days = sum(
        1
        for path in paths.data_shadow.rglob("quality/DATA_QUALITY.json")
        if json.loads(path.read_text(encoding="utf-8")).get("counts_toward_20_day_gate") is True
    )
    public_status = project_public_status(private_quality, valid_days)
    validate_payload(public_status, "publication_status", schemas)
    snapshot_id = f"{public_payload['trading_date']}-{datetime.now(UTC).strftime('%H%M%S%f')}"
    staging = paths.public_staging / snapshot_id / "data"
    repository_public = repository / "public" / "data"
    assert_destination_allowed(repository_public, repository)
    if repository_public.exists():
        shutil.copytree(repository_public, staging, dirs_exist_ok=True)
    write_exclusive(staging / "data-quality" / f"{snapshot_id}.json", canonical_json(public_payload))
    status_path = staging / "status.json"
    if status_path.exists():
        status_path.unlink()
    write_exclusive(status_path, canonical_json(public_status))
    build_publication_manifest(staging, staging / "PUBLICATION_MANIFEST.csv")
    with RuntimeLock(paths.locks / "publication.lock", stale_after_seconds=3600):
        return publish_public_data(
            repository=repository,
            staged_data=staging,
            worktree=paths.public_staging / f"worktree-{snapshot_id}",
            commit_message=f"data: publish redacted snapshot {public_payload['trading_date']}",
            push=push,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish fail-closed redacted runtime quality")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--push", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = publish_quality_snapshot(
        repository=args.repository,
        quality_path=args.quality,
        push=args.push,
    )
    print(f"PUBLICATION_RESULT={result}")
    print("RAW_MARKET_DATA_PUBLISHED=false")
    print("PAPER_POSITIONS=0")
    print("REAL_ORDERS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
