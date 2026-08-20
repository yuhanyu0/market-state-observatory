from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from market_state_observatory.runtime import operator_console
from market_state_observatory.runtime.operator_console import HTML
from market_state_observatory.runtime.runtime_paths import resolve_runtime_paths

ROOT = Path(__file__).resolve().parents[1]


def test_private_operator_console_has_required_pages_and_labels() -> None:
    for page in (
        "Today",
        "Yesterday",
        "Themes",
        "Observation Report",
        "State Certificates",
        "Evidence",
        "Incidents",
        "Experiments",
        "Promotion Gates",
        "Settings",
    ):
        assert page in HTML
    for badge in (
        "OBSERVED",
        "DESCRIPTIVE",
        "CANDIDATE NOT ESTIMATED",
        "NOT CALIBRATED",
        "DATA_BLOCKED",
        "MODEL_SHADOW_ONLY",
        "DISABLED",
    ):
        assert badge in HTML
    assert "127.0.0.1 only" in HTML
    assert "Positions / orders" in HTML
    assert "Capture pipeline" in HTML
    assert "Decision-point feed" in HTML
    assert "Qualifying soak PASS" in HTML
    assert "Total rehearsal runs" in HTML
    assert "direction_ready=false" not in HTML


def test_private_operator_state_labels_candidate_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MSO_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setattr(
        operator_console, "_scheduler_status", lambda: {"state": "TEST_ISOLATED"}
    )
    state = operator_console.operator_state(resolve_runtime_paths(create=True))

    assert state["candidate_authorization"] == {
        "label": "CANDIDATE ONLY",
        "detail": "Not calibrated or validated",
    }
    assert state["paper_positions"] == state["real_orders"] == 0


def test_operator_separates_total_runs_from_qualifying_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MSO_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setattr(operator_console, "_scheduler_status", lambda: {"state": "TEST_ISOLATED"})
    paths = resolve_runtime_paths(create=True)
    for index in range(3):
        run = paths.observations / f"run-{index}"
        run.mkdir()
        (run / "RUN.json").write_text(json.dumps({"run_id": f"run-{index}"}))
        if index < 2:
            quality = run / "quality" / "DATA_QUALITY.json"
            quality.parent.mkdir()
            quality.write_text(json.dumps({"data_quality_pass": index == 0}))

    progress = operator_console.operator_state(paths)["soak_progress"]

    assert progress["qualifying_pass"] == 1
    assert progress["total_rehearsal_runs"] == 3


def test_private_operator_console_mobile_and_accessibility_contract() -> None:
    assert "name='viewport'" in HTML
    assert "@media(max-width:760px)" in HTML
    assert "overflow-wrap:anywhere" in HTML
    assert "Skip to content" in HTML
    assert "aria-label='Operator pages'" in HTML
    assert "aria-pressed" in HTML
    assert "role='status'" in HTML
    assert 'tabindex="0" aria-label="Six-theme structure matrix"' in HTML
    assert "const primaryPages=new Set(['Today','Yesterday','Themes'])" in HTML
    assert "moreButton.textContent='More'" in HTML
    assert ".secondary-nav{display:none}" in HTML


def _run(shell: str, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    command = [shell, "-NoProfile", "-NonInteractive"]
    if Path(shell).name.lower() == "powershell.exe":
        command += ["-ExecutionPolicy", "Bypass"]
    command += ["-File", str(ROOT / script), *arguments]
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell contract")
def test_daily_report_installer_whatif_is_ps51_compatible_and_no_change() -> None:
    shell = str(Path(os.environ["SYSTEMROOT"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    result = _run(shell, "ops/windows/install_daily_report_task.ps1", "-Install", "-WhatIf")
    assert result.returncode == 0, result.stderr
    assert "INSTALL_PREVIEW_ONLY=true" in result.stdout
    assert "SCHEDULER_CHANGED=false" in result.stdout
    assert "PAPER_POSITIONS=0" in result.stdout
    assert "REAL_ORDERS=0" in result.stdout


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 unavailable")
def test_daily_report_installer_whatif_is_ps7_compatible() -> None:
    result = _run(str(shutil.which("pwsh")), "ops/windows/install_daily_report_task.ps1", "-Install", "-WhatIf")
    assert result.returncode == 0, result.stderr
    assert "INSTALL_PREVIEW_ONLY=true" in result.stdout
    assert "SCHEDULER_CHANGED=false" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell contract")
def test_daily_report_whatif_writes_nothing(tmp_path: Path) -> None:
    shell = str(Path(os.environ["SYSTEMROOT"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    output = tmp_path / "never-created"
    result = _run(
        shell,
        "ops/windows/run_daily_report.ps1",
        "-RunDirectory",
        str(ROOT / "tests" / "fixtures" / "completed_run_2026-08-18"),
        "-OutputDirectory",
        str(output),
        "-WhatIf",
        "-ActiveRuntimeWaitSeconds",
        "0",
    )
    assert result.returncode == 0, result.stderr
    assert "WHATIF=true" in result.stdout
    assert "SIDECAR_WRITTEN=false" in result.stdout
    assert "ORIGINAL_RUN_MUTATED=false" in result.stdout
    assert not output.exists()
