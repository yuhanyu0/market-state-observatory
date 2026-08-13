from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from market_state_observatory.publication.policy import (
    PublicationPolicyError,
    assert_destination_allowed,
    assert_public_payload,
)
from market_state_observatory.publication.public_projection import project_data_quality
from market_state_observatory.runtime.alpaca_adapter import AlpacaSIPAdapter, ProviderError
from market_state_observatory.runtime.credential_loader import (
    CredentialError,
    require_child_process_credentials,
    safe_credential_status,
)
from market_state_observatory.runtime.market_calendar import is_trading_day, next_trading_day
from market_state_observatory.runtime.observation_freezer import (
    ImmutableWriteError,
    freeze_provider_response,
    write_exclusive,
)
from market_state_observatory.runtime.runtime_lock import RuntimeAlreadyRunning, RuntimeLock
from market_state_observatory.runtime.runtime_paths import RuntimePathError, resolve_runtime_paths


def test_runtime_defaults_outside_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local = tmp_path / "local"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = resolve_runtime_paths(repo_root=repo, create=True)
    assert paths.root == (local / "MarketStateObservatoryRuntime").resolve()
    assert paths.raw.is_dir()


def test_runtime_rejects_repository_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("MSO_RUNTIME_ROOT", str(repo / "runtime"))
    with pytest.raises(RuntimePathError, match="must not be inside"):
        resolve_runtime_paths(repo_root=repo)


def test_credentials_are_presence_only_and_sip_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key-material")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret-material")
    monkeypatch.setenv("ALPACA_DATA_FEED", "sip")
    status = safe_credential_status()
    assert "PRESENT" in status
    assert "test-key-material" not in status
    assert "test-secret-material" not in status
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    with pytest.raises(CredentialError, match="fallback feeds are forbidden"):
        require_child_process_credentials()


def test_actual_credential_value_cannot_be_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key-material")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret-material")
    with pytest.raises(ValueError, match="Credential material rejected"):
        freeze_provider_response(
            raw_directory=tmp_path / "raw",
            manifest_directory=tmp_path / "manifest",
            observation_id="leak-test",
            raw_response=b'{"innocent_name":"test-secret-material"}',
            metadata={"provider": "test"},
        )
    assert not list(tmp_path.rglob("*.*"))


def test_immutable_files_and_runtime_lock(tmp_path: Path) -> None:
    artifact = tmp_path / "immutable.json"
    write_exclusive(artifact, b"{}")
    with pytest.raises(ImmutableWriteError):
        write_exclusive(artifact, b'{"changed":true}')
    lock = RuntimeLock(tmp_path / "runtime.lock")
    lock.acquire()
    try:
        with pytest.raises(RuntimeAlreadyRunning):
            RuntimeLock(lock.path).acquire()
    finally:
        lock.release()


def test_exact_observation_window_rejects_early_and_late() -> None:
    scheduled = datetime(2026, 8, 13, 19, 45, tzinfo=UTC)
    with pytest.raises(ProviderError, match="not due"):
        AlpacaSIPAdapter.validate_capture_window(scheduled, scheduled - timedelta(seconds=1))
    with pytest.raises(ProviderError, match="missed_observation"):
        AlpacaSIPAdapter.validate_capture_window(scheduled, scheduled + timedelta(seconds=61))
    AlpacaSIPAdapter.validate_capture_window(scheduled, scheduled + timedelta(seconds=60))


def test_every_adapter_request_forces_sip() -> None:
    adapter = AlpacaSIPAdapter()
    with pytest.raises(ProviderError, match="Non-SIP"):
        adapter._get("/stocks/quotes/latest", {"feed": "iex"})


def test_market_calendar_does_not_treat_weekdays_as_sufficient() -> None:
    assert not is_trading_day(date(2026, 7, 3))
    assert next_trading_day(date(2026, 7, 2)) == date(2026, 7, 6)


def test_public_projection_keeps_readiness_separate_from_model_state() -> None:
    private = {
        "trading_date": "2026-08-13",
        "data_quality_pass": True,
        "capture_rate": 1.0,
        "quote_age_seconds_max": 2.1,
        "future_timestamp_count": 0,
        "backfill_count": 0,
        "counts_toward_20_day_gate": True,
        "themes": [
            {
                "theme_id": "semiconductors",
                "theme_etf": "SMH",
                "data_ready": True,
                "model_estimated": False,
                "decision_eligible": False,
                "direction_ready": True,
                "transmission_ready": False,
                "constituent_coverage": 0.75,
                "blocking_reasons": ["constituent_coverage_below_80_percent"],
            }
        ],
    }
    public = project_data_quality(private)
    theme = public["themes"][0]
    assert theme["data_ready"] is True
    assert theme["model_estimated"] is False
    assert theme["decision_eligible"] is False
    assert public["paper_positions"] == 0
    assert public["real_orders"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"raw_response": {}},
        {"path": r"C:\\Users\\name\\private.json"},
        {"real_order_" + "created": True},
        {"paper_" + "positions": 1},
        {"provider_request_id": "request"},
    ],
)
def test_publication_firewall_rejects_private_or_action_data(payload: dict[str, object]) -> None:
    with pytest.raises(PublicationPolicyError):
        assert_public_payload(payload)


def test_public_destination_is_only_public_data(tmp_path: Path) -> None:
    assert_destination_allowed(tmp_path / "public" / "data" / "safe.json", tmp_path)
    with pytest.raises(PublicationPolicyError):
        assert_destination_allowed(tmp_path / "site" / "data" / "unsafe.json", tmp_path)


def test_repository_has_no_order_or_position_runtime_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "src" / "market_state_observatory" / "runtime").glob("*.py")
    )
    assert "submit_order" not in runtime_text
    assert "create_position" not in runtime_text
    universe = json.loads((root / "config" / "runtime_universe_v1.json").read_text())
    assert universe["paper_positions_allowed"] is False
    assert universe["real_orders_allowed"] is False


def test_formal_runtime_publishes_only_after_success() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "ops" / "windows" / "run_daily_runtime.ps1").read_text(encoding="utf-8")
    assert "if ($exitCode -eq 0 -and $Mode -eq 'formal')" in script
    assert "publish_public_snapshot.ps1" in script
    assert "-PrivateQualityPath $quality.FullName -Push" in script
    assert "failure_stage = $failureStage" in script
