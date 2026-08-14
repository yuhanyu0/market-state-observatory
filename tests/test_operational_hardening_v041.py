from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from market_state_observatory.publication.policy import (
    PublicationPolicyError,
    assert_publication_eligible,
)
from market_state_observatory.runtime.label_ledger import (
    register_source_snapshot,
    settle_horizon,
)
from market_state_observatory.runtime.market_calendar import session_schedule
from market_state_observatory.runtime.notifications import emit_local_alert
from market_state_observatory.runtime.operator_console import serve
from market_state_observatory.runtime.quality_engine import evaluate_run_quality
from market_state_observatory.runtime.runtime_lock import RuntimeLock
from market_state_observatory.runtime.stream_store import (
    BoundedHourlyStreamStore,
    reconstruct_chunk,
)


def test_early_close_schedule_is_derived_from_exchange_calendar() -> None:
    schedule = session_schedule(date(2026, 11, 27))
    assert schedule.market_close.strftime("%H:%M") == "13:00"
    assert schedule.close_minus_30m.strftime("%H:%M") == "12:30"
    assert schedule.close_minus_15m.strftime("%H:%M") == "12:45"
    assert [stamp for _, stamp in schedule.observation_points()] == sorted(
        stamp for _, stamp in schedule.observation_points()
    )


def test_stream_store_bounds_files_and_reconstructs_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = BoundedHourlyStreamStore(
            chunk_directory=tmp_path / "chunks",
            manifest_directory=tmp_path / "manifests",
            queue_size=32,
            disk_budget_bytes=10_000_000,
        )
        await store.start()
        for index in range(3500):
            hour = 13 + index // 500
            symbol = f"S{index % 35:02d}"
            observed = datetime(2026, 8, 13, hour, 30, tzinfo=UTC)
            await store.ingest(
                {"T": "q", "S": symbol, "t": observed.isoformat(), "bp": 1, "ap": 2},
                observed_at=observed,
            )
        frozen = await store.freeze_cross_section(
            [f"S{index:02d}" for index in range(35)], datetime(2026, 8, 13, 19, 45, tzinfo=UTC)
        )
        await store.stop()
        assert frozen.symbols_present == 35

    asyncio.run(scenario())
    chunks = list((tmp_path / "chunks").glob("*.ndjson.zst"))
    manifests = list((tmp_path / "manifests").glob("*.json"))
    assert len(chunks) == 7
    assert len(manifests) == 7
    assert sum(len(reconstruct_chunk(path)) for path in chunks) == 3500
    assert len(list(tmp_path.rglob("*.*"))) == 14


def _eligible_quality() -> dict[str, object]:
    return {
        "run_mode": "FORMAL_DATA_SHADOW", "process_success": True,
        "data_quality_pass": True, "publication_eligible": True,
        "schema_validation_pass": True, "secret_scan_pass": True,
        "forbidden_path_scan_pass": True, "production_release": True,
        "paper_positions": 0, "real_orders": 0,
    }


def test_publication_fail_closed_for_rehearsal_or_failed_quality() -> None:
    assert_publication_eligible(_eligible_quality())
    for field, value in (("run_mode", "DATA_CAPTURE_REHEARSAL"), ("data_quality_pass", False), ("publication_eligible", False)):
        payload = _eligible_quality()
        payload[field] = value
        with pytest.raises(PublicationPolicyError):
            assert_publication_eligible(payload)


def test_label_ledger_is_immutable_and_settlement_idempotent(tmp_path: Path) -> None:
    pending = register_source_snapshot(
        ledger_root=tmp_path, source_run_id="source", source_snapshot_hash="a" * 64,
        source_trading_date=date(2026, 8, 13),
    )
    before = [path.read_bytes() for path in pending]
    first = settle_horizon(
        ledger_root=tmp_path, trading_date=date(2026, 8, 14), observation_point="open_snapshot",
        settlement_run_id="settle", settlement_snapshot_hash="b" * 64,
        observed_at_utc="2026-08-14T13:30:01+00:00",
    )
    second = settle_horizon(
        ledger_root=tmp_path, trading_date=date(2026, 8, 14), observation_point="open_snapshot",
        settlement_run_id="settle", settlement_snapshot_hash="b" * 64,
        observed_at_utc="2026-08-14T13:30:01+00:00",
    )
    assert first == second
    assert [path.read_bytes() for path in pending] == before
    assert json.loads(first[0].read_text())["source_entry_sha256"]


def test_crash_lock_cleanup_recovers_dead_stale_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "runtime.lock"
    path.write_text('{"pid":999999,"acquired_at_utc":"old"}')
    os.utime(path, (time.time() - 100, time.time() - 100))
    monkeypatch.setattr(RuntimeLock, "_pid_running", staticmethod(lambda _pid: False))
    lock = RuntimeLock(path, stale_after_seconds=1)
    lock.acquire()
    lock.release()
    assert not path.exists()


def test_operator_console_rejects_non_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        serve(object(), host="0.0.0.0", port=0)  # type: ignore[arg-type]


def test_alert_ledger_never_serializes_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "private-key-value")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "private-secret-value")
    path = emit_local_alert(
        tmp_path, kind="quality_failed", title="Quality failed", message="Review run", toast=False
    )
    text = path.read_text()
    assert "private-key-value" not in text
    assert "private-secret-value" not in text


def test_toast_failure_does_not_lose_private_alert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("toast", 3)

    monkeypatch.setattr(subprocess, "run", timeout)
    path = emit_local_alert(
        tmp_path, kind="publication_failed", title="Publication failed", message="Review", toast=True
    )
    assert path.is_file()


def test_decision_freeze_duration_degrades_transmission_quality(tmp_path: Path) -> None:
    run = {
        "run_id": "run", "trading_date": "2026-08-13", "status": "FORMAL_DATA_SHADOW",
        "mode": "formal", "production_release": True, "membership_snapshot_frozen": True,
        "counts_toward_20_day_gate": True,
    }
    (tmp_path / "RUN.json").write_text(json.dumps(run))
    symbols = ["SPY", "SMH", "SOXX", "NVDA"]
    for point in ("open_snapshot", "midpoint_snapshot", "preclose_snapshot", "decision_snapshot", "session_close_diagnostic"):
        payload = {
            "observation_point": point, "scheduled_at_utc": "2026-08-13T19:45:00+00:00",
            "captured_at_utc": "2026-08-13T19:45:01+00:00",
            "freeze_duration_seconds": 9 if point == "decision_snapshot" else 0.01,
            "event_time_dispersion_seconds": 35 if point == "open_snapshot" else 1,
            "symbols": [{"symbol": symbol, "quote_age_seconds": 1, "vwap": 100} for symbol in symbols],
            "future_timestamp_count": 0, "backfilled": False,
        }
        path = tmp_path / "manifests" / "points" / f"{point}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    universe = {
        "benchmark": "SPY",
        "themes": [{"theme_id": "semiconductors", "theme_etf": "SMH", "industry_benchmark": "SOXX", "basket": ["NVDA"]}],
    }
    quality = evaluate_run_quality(tmp_path, universe)
    assert quality["themes"][0]["direction_ready"] is True
    assert quality["themes"][0]["transmission_ready"] is False
    assert "decision_freeze_duration_above_5_seconds" in quality["themes"][0]["blocking_reasons"]
