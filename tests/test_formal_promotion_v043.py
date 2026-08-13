from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from market_state_observatory.runtime.formal_promotion import (
    FormalPromotionError,
    create_authorization,
    verify_authorization,
)
from market_state_observatory.runtime.release_identity import (
    build_release_manifest,
    sha256_file,
)


def _write(path: Path, value: str | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value) if isinstance(value, dict) else value
    path.write_text(text, encoding="utf-8")


def _release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    release = tmp_path / "release"
    repository = tmp_path / "repository"
    _write(release / "wheel" / "market_state_observatory-0.4.3.whl", "wheel")
    _write(release / "dependency.lock", "dependency==1\n")
    _write(release / "schemas" / "private.json", "{}")
    _write(release / "frozen" / "runtime_universe_v1.json", "{}")
    _write(release / "frozen" / "membership_snapshot_v1.json", "{}")
    _write(release / "config" / "runtime_release_config.json", "{}")
    _write(release / "config" / "publication_policy.yml", "forbidden_fields: []\n")
    _write(release / "runtime_release_launcher.ps1", "# launcher\n")
    _write(release / "lib" / "process_compat.ps1", "# helper\n")
    _write(release / "lib" / "scheduler_safety.ps1", "# scheduler helper\n")
    _write(repository / "src" / "market_state_observatory" / "runtime" / "module.py", "x=1\n")
    manifest = build_release_manifest(
        release=release,
        repository=repository,
        git_sha="c" * 40,
        release_version="0.4.3",
        tested_shells=["Desktop 5.1.26100.9168"],
    )
    _write(release / "release_manifest.json", manifest)
    monkeypatch.setenv("MSO_RELEASE_ROOT", str(release))
    return release, manifest


def _identity(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "release_version": str(manifest["release_version"]),
        "release_git_sha": str(manifest["git_sha"]),
        "release_wheel_sha256": str(manifest["wheel_sha256"]),
        "experiment_lane": str(manifest["experiment_lane"]),
        "universe_sha256": str(manifest["universe_sha256"]),
        "membership_sha256": str(manifest["membership_sha256"]),
        "schema_sha256": str(manifest["schema_sha256"]),
        "quality_policy_sha256": str(manifest["quality_policy_sha256"]),
    }


def _valid_soak(runtime: Path, manifest: dict[str, Any]) -> Path:
    sessions: list[dict[str, Any]] = []
    for index, day in enumerate(("2026-08-10", "2026-08-11", "2026-08-12"), start=1):
        run_id = f"{day}-run-{index}"
        relative = Path("observations") / "rehearsals" / str(manifest["experiment_lane"]) / day / run_id
        run_directory = runtime / relative
        run = {
            "run_id": run_id,
            "trading_date": day,
            "mode": "rehearsal",
            "status": "DATA_CAPTURE_REHEARSAL",
            "scheduler_task_name": "MSO-Daily-Rehearsal",
            "counts_toward_20_day_gate": False,
            "counts_toward_model_shadow": False,
            "publication_as_formal": False,
            "paper_positions_allowed": False,
            "real_orders_allowed": False,
            **manifest,
        }
        quality = {
            "run_id": run_id,
            "data_quality_pass": True,
            "counts_toward_20_day_gate": False,
            "counts_toward_model_shadow": False,
            "publication_eligible": False,
            "future_timestamp_count": 0,
            "backfill_count": 0,
            "stream_message_drop_count": 0,
            "planned_observations": 175,
            "captured_observations": 175,
            "paper_positions": 0,
            "real_orders": 0,
        }
        run_path = run_directory / "RUN.json"
        quality_path = run_directory / "quality" / "DATA_QUALITY.json"
        _write(run_path, run)
        _write(quality_path, quality)
        sessions.append(
            {
                "run_id": run_id,
                "run_relative_path": relative.as_posix(),
                "source_run_sha256": sha256_file(run_path),
                "quality_sha256": sha256_file(quality_path),
                "scheduler_driven": True,
                "scheduler_task_name": "MSO-Daily-Rehearsal",
                "scheduler_mode": "rehearsal",
                "complete": True,
                "required_observations_captured": True,
                "future_timestamp_count": 0,
                "backfill_count": 0,
                "message_drop_count": 0,
                "data_quality_pass": True,
                "secret_scan_pass": True,
                "private_public_boundary_pass": True,
                "settlement_idempotence_pass": True,
                "publication_rehearsal_isolation_pass": True,
                "scheduler_version_frozen": True,
                "paper_positions": 0,
                "real_orders": 0,
            }
        )
    soak = {
        "schema_version": "mso-soak-test-results-v1",
        "status": "PASS",
        **_identity(manifest),
        "scheduler_version": manifest["powershell_launcher_version"],
        "credential_leak_scan_pass": True,
        "private_public_boundary_pass": True,
        "settlement_idempotence_pass": True,
        "publication_rehearsal_isolation_pass": True,
        "scheduler_version_frozen": True,
        "paper_positions": 0,
        "real_orders": 0,
        "sessions": sessions,
    }
    soak_path = runtime / "promotion" / "SOAK_TEST_RESULTS.json"
    _write(soak_path, soak)
    return soak_path


def test_formal_install_is_rejected_without_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    _valid_soak(runtime, manifest)
    with pytest.raises(FormalPromotionError, match="authorization is missing"):
        verify_authorization(runtime)


def test_valid_three_day_soak_creates_and_verifies_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    _valid_soak(runtime, manifest)
    path = create_authorization(runtime)
    payload = verify_authorization(runtime)
    assert path.is_file()
    assert payload["status"] == "GO"
    assert payload["counts_toward_model_shadow"] is False
    assert payload["paper_positions_allowed"] is False
    assert payload["real_orders_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("release_version", "0.4.2", "release identity mismatch"),
        ("release_wheel_sha256", "0" * 64, "release identity mismatch"),
        ("experiment_lane", "stale-lane", "release identity mismatch"),
    ],
)
def test_stale_or_wrong_authorization_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    message: str,
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    _valid_soak(runtime, manifest)
    path = create_authorization(runtime)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    _write(path, payload)
    with pytest.raises(FormalPromotionError, match=message):
        verify_authorization(runtime)


def test_malformed_authorization_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    _valid_soak(runtime, manifest)
    _write(runtime / "promotion" / "formal_data_shadow_authorization.json", "not-json")
    with pytest.raises(FormalPromotionError, match="malformed"):
        verify_authorization(runtime)


def test_authorization_missing_required_field_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    _valid_soak(runtime, manifest)
    path = create_authorization(runtime)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["authorized_at_utc"]
    _write(path, payload)
    with pytest.raises(FormalPromotionError, match="fields missing"):
        verify_authorization(runtime)


def test_hand_written_go_cannot_bypass_missing_soak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, manifest = _release(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    authorization = {
        "schema_version": "mso-formal-data-shadow-authorization-v1",
        "status": "GO",
        **_identity(manifest),
        "soak_result_sha256": "0" * 64,
        "authorized_at_utc": "2026-08-13T12:00:00+00:00",
        "minimum_scheduler_rehearsal_sessions": 3,
        "counts_toward_model_shadow": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    _write(runtime / "promotion" / "formal_data_shadow_authorization.json", authorization)
    with pytest.raises(FormalPromotionError, match="SOAK_TEST_RESULTS.json is missing"):
        verify_authorization(runtime)
