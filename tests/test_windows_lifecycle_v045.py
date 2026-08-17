from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.runtime.process_ownership import process_truth
from market_state_observatory.runtime.runtime_lock import RuntimeLock


def test_operator_process_truth_does_not_trust_stale_status(tmp_path: Path) -> None:
    ownership = tmp_path / "process-ownership"
    ownership.mkdir()
    (ownership / "dead.json").write_text(
        json.dumps(
            {
                "runtime_pid": 999_999_999,
                "runtime_created_at_utc": "2026-08-17T13:00:00+00:00",
                "status": "RUNNING",
            }
        ),
        encoding="utf-8",
    )
    state = process_truth(tmp_path)
    assert state["state"] == "INACTIVE"
    assert state["active_count"] == 0
    assert state["latest"]["process_identity_live"] is False


def test_operator_process_truth_rejects_malformed_identity(tmp_path: Path) -> None:
    ownership = tmp_path / "process-ownership"
    ownership.mkdir()
    (ownership / "malformed.json").write_text(
        json.dumps(
            {
                "runtime_pid": "not-a-pid",
                "runtime_created_at_utc": "not-a-timestamp",
                "status": "RUNNING",
            }
        ),
        encoding="utf-8",
    )
    state = process_truth(tmp_path)
    assert state["state"] == "INACTIVE"
    assert state["active_count"] == 0


def test_runtime_lock_records_strong_process_identity(tmp_path: Path) -> None:
    path = tmp_path / "daily-runtime.lock"
    lock = RuntimeLock(
        path,
        ownership={"ownership_id": "owner", "launcher_pid": 123},
        release_python="C:/frozen/python.exe",
        process_executable="C:/base/python.exe",
    )
    lock.acquire()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pid"] > 0
        assert payload["process_created_at_utc"]
        assert payload["ownership_id"] == "owner"
        assert payload["launcher_pid"] == 123
        assert payload["release_python"] == "C:/frozen/python.exe"
        assert payload["process_executable"] == "C:/base/python.exe"
    finally:
        lock.release()


def test_v045_launcher_uses_suspended_job_ownership() -> None:
    root = Path(__file__).resolve().parents[1]
    job = (root / "ops/windows/lib/job_object.ps1").read_text(encoding="utf-8")
    launcher = (root / "ops/windows/runtime_release_launcher.ps1").read_text(encoding="utf-8")
    selector = (root / "ops/windows/select_runtime_release.ps1").read_text(encoding="utf-8")
    stop = (root / "ops/windows/stop_runtime.ps1").read_text(encoding="utf-8")
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in job
    assert "CREATE_SUSPENDED" in job
    assert "AssignProcessToJobObject" in job
    assert "ResumeThread" in job
    assert "Invoke-MsoOwnedChildProcess" in launcher
    assert "New-MsoOwnedProcess" in (
        root / "ops/windows/lib/process_compat.ps1"
    ).read_text(encoding="utf-8")
    assert "Assert-MsoRuntimeStartSafe" in launcher
    assert "Assert-MsoReleaseSelectionSafe" in selector
    assert "live ownership task identity mismatch" in stop
    assert "Stop-Process python" not in stop
    assert "Stop-MsoNamedJob" in stop
