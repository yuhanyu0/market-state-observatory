from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_state_observatory.runtime.release_identity import (
    ProductionReleaseRequired,
    build_release_manifest,
    load_release_manifest,
)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _release_fixture(tmp_path: Path) -> tuple[Path, Path]:
    release = tmp_path / "release"
    repository = tmp_path / "repository"
    _write(release / "wheel" / "market_state_observatory-0.4.2.whl", "wheel")
    _write(release / "dependency.lock", "dependency==1\n")
    _write(release / "schemas" / "public.json", "{}")
    _write(release / "frozen" / "runtime_universe_v1.json", "{}")
    _write(release / "frozen" / "membership_snapshot_v1.json", "{}")
    _write(release / "config" / "runtime_release_config.json", "{}")
    _write(release / "runtime_release_launcher.ps1", "# launcher 0.4.2\n")
    _write(release / "lib" / "process_compat.ps1", "# compatibility helper\n")
    _write(repository / "src" / "market_state_observatory" / "runtime" / "module.py", "x = 1\n")
    return release, repository


def test_v042_release_manifest_locks_powershell_launcher_and_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, repository = _release_fixture(tmp_path)
    payload = build_release_manifest(
        release=release,
        repository=repository,
        git_sha="a" * 40,
        release_version="0.4.2",
        tested_shells=["Desktop 5.1.26100.9168", "Core 7.4.6"],
    )
    (release / "release_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MSO_RELEASE_ROOT", str(release))

    loaded = load_release_manifest(required=True)

    assert loaded is not None
    assert loaded["powershell_launcher_version"] == "0.4.2"
    assert loaded["minimum_windows_powershell_version"] == "5.1"
    assert loaded["tested_powershell_editions"] == ["Core", "Desktop"]
    assert loaded["release_python_path_class"] == "release_root_venv"


def test_v042_release_manifest_rejects_modified_process_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, repository = _release_fixture(tmp_path)
    payload = build_release_manifest(
        release=release,
        repository=repository,
        git_sha="b" * 40,
        release_version="0.4.2",
        tested_shells=["Desktop 5.1.26100.9168"],
    )
    (release / "release_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    (release / "lib" / "process_compat.ps1").write_text("tampered", encoding="utf-8")
    monkeypatch.setenv("MSO_RELEASE_ROOT", str(release))

    with pytest.raises(ProductionReleaseRequired, match="process_compat_helper_sha256"):
        load_release_manifest(required=True)
