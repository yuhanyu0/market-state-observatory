from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .observation_freezer import canonical_json


class ProductionReleaseRequired(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def source_git_sha(repository: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "GIT_SHA_UNAVAILABLE"


def release_root() -> Path | None:
    value = os.environ.get("MSO_RELEASE_ROOT")
    return Path(value).resolve() if value else None


def load_release_manifest(*, required: bool) -> dict[str, Any] | None:
    root = release_root()
    if root is None:
        if required:
            raise ProductionReleaseRequired("Formal runtime requires MSO_RELEASE_ROOT")
        return None
    path = root / "release_manifest.json"
    if not path.is_file():
        raise ProductionReleaseRequired("Frozen release manifest is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProductionReleaseRequired("Frozen release manifest must be an object")
    required_fields = {
        "git_sha",
        "release_version",
        "wheel_sha256",
        "dependency_lock_sha256",
        "collector_bundle_sha256",
        "schema_sha256",
        "universe_sha256",
        "membership_sha256",
        "config_sha256",
        "quality_policy_sha256",
        "experiment_lane",
        "powershell_launcher_version",
        "powershell_launcher_sha256",
        "process_compat_helper_sha256",
        "scheduler_safety_helper_sha256",
        "job_object_helper_sha256",
        "runtime_process_helper_sha256",
        "safe_stop_sha256",
        "base_python_path",
        "base_python_sha256",
        "minimum_windows_powershell_version",
        "tested_shells",
        "release_python_path_class",
    }
    missing = required_fields - payload.keys()
    if missing:
        raise ProductionReleaseRequired(f"Release manifest fields missing: {sorted(missing)}")
    checks = {
        "wheel_sha256": root / str(payload.get("wheel_file", "")),
        "dependency_lock_sha256": root / "dependency.lock",
        "schema_sha256": root / "schemas",
        "universe_sha256": root / "frozen" / "runtime_universe_v1.json",
        "membership_sha256": root / "frozen" / "membership_snapshot_v1.json",
        "config_sha256": root / "config" / "runtime_release_config.json",
        "quality_policy_sha256": root / "config" / "publication_policy.yml",
        "powershell_launcher_sha256": root / "runtime_release_launcher.ps1",
        "process_compat_helper_sha256": root / "lib" / "process_compat.ps1",
        "scheduler_safety_helper_sha256": root / "lib" / "scheduler_safety.ps1",
        "job_object_helper_sha256": root / "lib" / "job_object.ps1",
        "runtime_process_helper_sha256": root / "lib" / "runtime_process.ps1",
        "safe_stop_sha256": root / "stop_runtime.ps1",
        "base_python_sha256": Path(str(payload.get("base_python_path", ""))),
    }
    for field, path in checks.items():
        if not path.exists():
            raise ProductionReleaseRequired(f"Frozen release artifact is missing: {path.name}")
        actual = sha256_tree(path) if path.is_dir() else sha256_file(path)
        if actual != payload[field]:
            raise ProductionReleaseRequired(f"Frozen release hash mismatch: {field}")
    return dict(payload)


def development_identity(repository: Path, universe_path: Path, membership: bytes) -> dict[str, Any]:
    source_root = repository / "src" / "market_state_observatory"
    version = importlib.metadata.version("market-state-observatory")
    collector_hash = sha256_tree(source_root / "runtime")
    schema_hash = sha256_tree(repository / "schemas")
    universe_hash = sha256_file(universe_path)
    membership_hash = hashlib.sha256(membership).hexdigest()
    config_hash = universe_hash
    return {
        "git_sha": source_git_sha(repository),
        "release_version": version,
        "wheel_sha256": "DEVELOPMENT_EDITABLE_NOT_PRODUCTION",
        "dependency_lock_sha256": "DEVELOPMENT_ENVIRONMENT_NOT_LOCKED",
        "collector_bundle_sha256": collector_hash,
        "schema_sha256": schema_hash,
        "universe_sha256": universe_hash,
        "membership_sha256": membership_hash,
        "config_sha256": config_hash,
        "experiment_lane": f"rehearsal-v{version}-{collector_hash[:8]}",
        "production_release": False,
    }


def runtime_identity(
    *, repository: Path, universe_path: Path, membership: bytes, production_required: bool
) -> dict[str, Any]:
    manifest = load_release_manifest(required=production_required)
    if manifest is not None:
        return {**manifest, "production_release": True}
    return development_identity(repository, universe_path, membership)


def build_release_manifest(
    *,
    release: Path,
    repository: Path,
    git_sha: str,
    release_version: str,
    tested_shells: list[str],
    base_python: Path | None = None,
) -> dict[str, Any]:
    wheels = list((release / "wheel").glob("*.whl"))
    if len(wheels) != 1:
        raise ProductionReleaseRequired("Release must contain exactly one wheel")
    wheel_hash = sha256_file(wheels[0])
    universe_hash = sha256_file(release / "frozen" / "runtime_universe_v1.json")
    resolved_base_python = (
        base_python or Path(getattr(sys, "_base_executable", sys.executable))
    ).resolve()
    if not resolved_base_python.is_file():
        raise ProductionReleaseRequired("Base Python executable is missing")
    return {
        "schema_version": "mso-production-release-v1",
        "git_sha": git_sha,
        "release_version": release_version,
        "wheel_file": f"wheel/{wheels[0].name}",
        "wheel_sha256": wheel_hash,
        "dependency_lock_sha256": sha256_file(release / "dependency.lock"),
        "collector_bundle_sha256": sha256_tree(
            repository / "src" / "market_state_observatory" / "runtime"
        ),
        "schema_sha256": sha256_tree(release / "schemas"),
        "universe_sha256": universe_hash,
        "membership_sha256": sha256_file(release / "frozen" / "membership_snapshot_v1.json"),
        "config_sha256": sha256_file(release / "config" / "runtime_release_config.json"),
        "quality_policy_sha256": sha256_file(release / "config" / "publication_policy.yml"),
        "powershell_launcher_version": release_version,
        "powershell_launcher_sha256": sha256_file(release / "runtime_release_launcher.ps1"),
        "process_compat_helper_sha256": sha256_file(release / "lib" / "process_compat.ps1"),
        "scheduler_safety_helper_sha256": sha256_file(
            release / "lib" / "scheduler_safety.ps1"
        ),
        "job_object_helper_sha256": sha256_file(release / "lib" / "job_object.ps1"),
        "runtime_process_helper_sha256": sha256_file(
            release / "lib" / "runtime_process.ps1"
        ),
        "safe_stop_sha256": sha256_file(release / "stop_runtime.ps1"),
        "base_python_path": str(resolved_base_python),
        "base_python_sha256": sha256_file(resolved_base_python),
        "job_object_ownership": "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE",
        "child_creation_order": "CREATE_SUSPENDED_ASSIGN_JOB_RESUME_THREAD",
        "minimum_windows_powershell_version": "5.1",
        "tested_shells": tested_shells,
        "tested_powershell_editions": sorted(
            {"Desktop" if shell.startswith("Desktop ") else "Core" for shell in tested_shells}
        ),
        "release_python_path_class": "release_root_venv",
        "experiment_lane": (
            f"data-shadow-v{release_version}-{wheel_hash[:8]}-{universe_hash[:8]}"
        ),
        "formal_data_shadow_started": False,
        "paper_positions": 0,
        "real_orders": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-manifest", action="store_true")
    parser.add_argument("--verify-release", action="store_true")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--git-sha")
    parser.add_argument("--release-version")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tested-shell", action="append", default=[])
    parser.add_argument("--base-python", type=Path)
    args = parser.parse_args()
    if args.verify_release:
        manifest = load_release_manifest(required=True)
        assert manifest is not None
        print(f"RELEASE_INTEGRITY=PASS lane={manifest['experiment_lane']}")
        return
    if not all(
        (
            args.build_manifest,
            args.release,
            args.repository,
            args.git_sha,
            args.release_version,
            args.output,
            args.tested_shell,
        )
    ):
        parser.error("All manifest-build arguments are required")
    payload = build_release_manifest(
        release=args.release,
        repository=args.repository,
        git_sha=args.git_sha,
        release_version=args.release_version,
        tested_shells=args.tested_shell,
        base_python=args.base_python,
    )
    args.output.write_bytes(canonical_json(payload))


if __name__ == "__main__":
    main()
