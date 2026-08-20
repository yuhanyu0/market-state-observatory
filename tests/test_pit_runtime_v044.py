from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from market_state_observatory.runtime.alpaca_adapter import (
    AlpacaSIPAdapter,
    PointCapture,
    RestResult,
    SymbolCapture,
)
from market_state_observatory.runtime.pit_observation import build_point_payload
from market_state_observatory.runtime.quality_engine import CORE_POINTS, evaluate_run_quality
from market_state_observatory.runtime.runtime_heartbeat import run_heartbeat
from market_state_observatory.runtime.stream_store import (
    BoundedHourlyStreamStore,
    CrossSectionFreeze,
    reconstruct_chunk,
)
from market_state_observatory.validation import validate_payload


def _rest_result(body: dict[str, Any], observed: datetime) -> RestResult:
    raw = json.dumps(body).encode()
    return RestResult(
        collector_request_id="request",
        provider_request_id=None,
        request_started_at_utc=observed.isoformat(),
        observed_at_utc=observed.isoformat(),
        response_status=200,
        sanitized_request_parameters={"feed": "sip"},
        response_headers_sha256="a" * 64,
        raw_response=raw,
        body=body,
        server_date_utc=observed.isoformat(),
    )


def _stream_record(
    event_type: str,
    symbol: str,
    event: datetime,
    observed: datetime,
    **values: Any,
) -> dict[str, Any]:
    payload = {"T": event_type, "S": symbol, "t": event.isoformat(), **values}
    return {
        "event_type": event_type,
        "symbol": symbol,
        "event_time_utc": event.isoformat(),
        "observed_at_utc": observed.isoformat(),
        "provider_payload": payload,
    }


def _rest_symbol(symbol: str, event: datetime, *, bid: float = 100.0) -> SymbolCapture:
    return SymbolCapture(
        symbol=symbol,
        quote={
            "bid": bid,
            "ask": 100.02,
            "mid": (bid + 100.02) / 2,
            "quoted_spread": 100.02 - bid,
            "event_time_utc": event.isoformat(),
        },
        quote_status="READY",
        last_trade={"price": 100.01, "event_time_utc": event.isoformat()},
        trade_status="READY",
        minute_bar=None,
        bar_status="MISSING",
        vwap=100.0,
        vwap_status="READY",
        cumulative_volume=1000,
        included_interval_start_utc=event.isoformat(),
        included_interval_end_utc=event.isoformat(),
        quote_age_seconds=0.1,
        rest_observed_at_utc=(event + timedelta(seconds=1)).isoformat(),
        session_high=100.0,
        session_low=99.0,
    )


def _freeze(symbols: list[str], scheduled: datetime, *, post_freeze: bool = False) -> CrossSectionFreeze:
    completed = scheduled + timedelta(milliseconds=100)
    observed = completed + timedelta(seconds=1) if post_freeze else completed - timedelta(milliseconds=20)
    latest = {
        symbol: {
            "q": _stream_record("q", symbol, scheduled, observed, bp=100.0, ap=100.02),
            "t": _stream_record("t", symbol, scheduled, observed, p=100.01),
        }
        for symbol in symbols
    }
    return CrossSectionFreeze(
        scheduled_at_utc=scheduled.isoformat(),
        freeze_started_at_utc=(completed - timedelta(milliseconds=1)).isoformat(),
        freeze_completed_at_utc=completed.isoformat(),
        earliest_event_time_utc=scheduled.isoformat(),
        latest_event_time_utc=scheduled.isoformat(),
        freeze_duration_seconds=0.001,
        event_time_dispersion_seconds=0.0,
        symbols_requested=len(symbols),
        symbols_present=len(symbols),
        latest_state=latest,
    )


def test_open_rest_capture_keeps_all_symbols_without_completed_bar(monkeypatch: Any) -> None:
    scheduled = datetime(2026, 8, 17, 13, 30, tzinfo=UTC)
    symbols = [f"S{index:02d}" for index in range(35)]
    quotes = {
        symbol: {"t": scheduled.isoformat(), "bp": 100, "ap": 100.02}
        for symbol in symbols
    }
    trades = {symbol: {"t": scheduled.isoformat(), "p": 100.01} for symbol in symbols}
    adapter = AlpacaSIPAdapter()
    monkeypatch.setattr(adapter, "latest_quotes", lambda _: _rest_result({"quotes": quotes}, scheduled))
    monkeypatch.setattr(adapter, "latest_trades", lambda _: _rest_result({"trades": trades}, scheduled))
    monkeypatch.setattr(adapter, "snapshots", lambda _: _rest_result({"snapshots": {}}, scheduled))
    monkeypatch.setattr(adapter, "_all_bars", lambda *_: ({symbol: [] for symbol in symbols}, []))

    capture = adapter.capture_exact_point(
        symbols, "open_snapshot", scheduled, scheduled + timedelta(seconds=1)
    )

    assert len(capture.symbols) == 35
    assert {row.bar_status for row in capture.symbols} == {"NOT_YET_DEFINED"}
    assert {row.vwap_status for row in capture.symbols} == {"NOT_YET_DEFINED"}


def test_rest_missing_trade_does_not_erase_quote_observation(monkeypatch: Any) -> None:
    scheduled = datetime(2026, 8, 17, 16, 0, tzinfo=UTC)
    adapter = AlpacaSIPAdapter()
    monkeypatch.setattr(
        adapter,
        "latest_quotes",
        lambda _: _rest_result(
            {"quotes": {"SPY": {"t": scheduled.isoformat(), "bp": 100, "ap": 100.02}}},
            scheduled,
        ),
    )
    monkeypatch.setattr(adapter, "latest_trades", lambda _: _rest_result({"trades": {}}, scheduled))
    monkeypatch.setattr(adapter, "snapshots", lambda _: _rest_result({}, scheduled))
    monkeypatch.setattr(adapter, "_all_bars", lambda *_: ({"SPY": []}, []))

    capture = adapter.capture_exact_point(
        ["SPY"], "midpoint_snapshot", scheduled, scheduled + timedelta(seconds=1)
    )

    assert len(capture.symbols) == 1
    assert capture.symbols[0].quote_status == "READY"
    assert capture.symbols[0].trade_status == "MISSING"


def test_websocket_primary_creates_every_row_when_rest_is_unavailable() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    symbols = [f"S{index:02d}" for index in range(35)]
    capture = PointCapture(
        "decision_snapshot", scheduled.isoformat(), scheduled.isoformat(), (), ()
    )

    payload = build_point_payload(capture, _freeze(symbols, scheduled), None)

    assert len(payload["symbols"]) == 35
    assert {row["observation_status"] for row in payload["symbols"]} == {"CAPTURED"}
    assert {row["quote"]["status"] for row in payload["symbols"]} == {"READY"}
    assert {
        row["rest_reconciliation"]["quote_match_status"] for row in payload["symbols"]
    } == {"REST_UNAVAILABLE"}


def test_pit_observation_v3_schema_accepts_normalized_contract() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    payload = build_point_payload(
        PointCapture("decision_snapshot", scheduled.isoformat(), scheduled.isoformat(), (), ()),
        _freeze(["SPY"], scheduled),
        None,
    )
    validate_payload(payload, "private_observation_point", Path(__file__).resolve().parents[1])


def test_session_range_explicitly_includes_frozen_primary_price() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    capture = PointCapture(
        "decision_snapshot",
        scheduled.isoformat(),
        scheduled.isoformat(),
        (_rest_symbol("SPY", scheduled),),
        (),
    )

    payload = build_point_payload(capture, _freeze(["SPY"], scheduled), None)
    session_range = payload["symbols"][0]["session_range"]

    assert session_range["status"] == "READY"
    assert session_range["source"] == "rest_sip_completed_bars_plus_primary_pit"
    assert session_range["high"] == 100.01
    assert session_range["low"] == 99.0


def test_rest_disagreement_is_recorded_without_substitution() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    capture = PointCapture(
        "decision_snapshot",
        scheduled.isoformat(),
        scheduled.isoformat(),
        (_rest_symbol("SPY", scheduled, bid=99.0),),
        (),
    )

    payload = build_point_payload(capture, _freeze(["SPY"], scheduled), None)
    row = payload["symbols"][0]

    assert row["quote"]["bid"] == 100.0
    reconciliation = row["rest_reconciliation"]
    assert reconciliation["quote_match_status"] == "MATERIAL_DIFFERENCE"
    assert reconciliation["quote_price_difference"] == 1.0
    assert reconciliation["quote_time_difference_seconds"] == 0.0
    assert reconciliation["tolerance_version"] == "rest-reconciliation-v2"


def test_rest_reconciliation_distinguishes_tolerance_and_asynchrony() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    within = _rest_symbol("SPY", scheduled, bid=100.005)
    within.quote["ask"] = 100.025
    asynchronous = _rest_symbol("QQQ", scheduled - timedelta(seconds=5), bid=99.0)
    capture = PointCapture(
        "decision_snapshot",
        scheduled.isoformat(),
        scheduled.isoformat(),
        (within, asynchronous),
        (),
    )

    payload = build_point_payload(capture, _freeze(["SPY", "QQQ"], scheduled), None)
    rows = {row["symbol"]: row for row in payload["symbols"]}

    assert rows["SPY"]["rest_reconciliation"]["quote_match_status"] == (
        "MATCH_WITHIN_TOLERANCE"
    )
    assert rows["QQQ"]["rest_reconciliation"]["quote_match_status"] == "ASYNC_EXPECTED"
    statuses = {
        row["rest_reconciliation"]["quote_match_status"] for row in payload["symbols"]
    }
    assert "DIFFERENT" not in statuses


def test_post_freeze_record_is_rejected_from_primary_pit() -> None:
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    capture = PointCapture(
        "decision_snapshot", scheduled.isoformat(), scheduled.isoformat(), (), ()
    )
    payload = build_point_payload(capture, _freeze(["SPY"], scheduled, post_freeze=True), None)
    assert payload["symbols"][0]["quote"]["status"] == "POST_FREEZE_REJECTED"
    assert payload["future_timestamp_count"] == 2


def test_atomic_freeze_excludes_later_ingest_and_separates_metrics(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = BoundedHourlyStreamStore(
            chunk_directory=tmp_path / "chunks", manifest_directory=tmp_path / "manifests"
        )
        await store.start()
        old = datetime(2026, 8, 17, 19, 44, 20, tzinfo=UTC)
        await store.ingest(
            {"T": "q", "S": "SPY", "t": old.isoformat(), "bp": 100, "ap": 101},
            observed_at=old,
        )
        frozen = await store.freeze_cross_section(["SPY"], old + timedelta(seconds=40))
        new = old + timedelta(seconds=41)
        await store.ingest(
            {"T": "q", "S": "SPY", "t": new.isoformat(), "bp": 200, "ap": 201},
            observed_at=new,
        )
        await store.stop()
        assert frozen.latest_state["SPY"]["q"]["provider_payload"]["bp"] == 100
        assert frozen.freeze_duration_seconds < 1
        assert frozen.event_time_dispersion_seconds == 0

    asyncio.run(scenario())


def _ready_row(symbol: str, *, open_point: bool = False) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "observation_status": "CAPTURED",
        "quote": {"status": "READY", "received_age_seconds": 1, "freshness_age_seconds": 1},
        "last_trade": {"status": "READY"},
        "minute_bar": {"status": "NOT_YET_DEFINED" if open_point else "READY"},
        "vwap": {"status": "NOT_YET_DEFINED" if open_point else "READY", "value": None if open_point else 100},
    }


def test_early_event_dispersion_does_not_poison_decision_transmission(tmp_path: Path) -> None:
    run = {
        "run_id": "run",
        "trading_date": "2026-08-17",
        "status": "DATA_CAPTURE_REHEARSAL",
        "mode": "rehearsal",
        "publication_as_formal": False,
        "production_release": True,
        "membership_snapshot_frozen": True,
        "counts_toward_20_day_gate": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    (tmp_path / "RUN.json").write_text(json.dumps(run))
    symbols = ["SPY", "SMH", "SOXX", "NVDA"]
    for point in CORE_POINTS:
        payload = {
            "observation_point": point,
            "captured_at_utc": "2026-08-17T19:45:00+00:00",
            "freeze_duration_seconds": 0.01,
            "event_time_dispersion_seconds": 35 if point == "open_snapshot" else 2.6,
            "future_timestamp_count": 0,
            "backfilled": False,
            "symbols": [_ready_row(symbol, open_point=point == "open_snapshot") for symbol in symbols],
        }
        path = tmp_path / "manifests" / "points" / f"{point}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    universe = {
        "benchmark": "SPY",
        "themes": [
            {
                "theme_id": "semiconductors",
                "theme_etf": "SMH",
                "industry_benchmark": "SOXX",
                "basket": ["NVDA"],
            }
        ],
    }

    quality = evaluate_run_quality(tmp_path, universe)

    assert quality["observation_capture_rate"] == 1
    assert quality["bar_ready_rate"] < 1
    assert quality["themes"][0]["transmission_ready"] is True


def test_hour_is_finalized_when_next_utc_hour_arrives(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = BoundedHourlyStreamStore(
            chunk_directory=tmp_path / "chunks",
            manifest_directory=tmp_path / "manifests",
            checkpoint_message_interval=2,
        )
        await store.start()
        first = datetime(2026, 8, 17, 13, 59, 59, tzinfo=UTC)
        second = datetime(2026, 8, 17, 14, 0, 1, tzinfo=UTC)
        for stamp in (first, second):
            await store.ingest(
                {"T": "q", "S": "SPY", "t": stamp.isoformat(), "bp": 1, "ap": 2},
                observed_at=stamp,
            )
        await store.drain()
        assert (tmp_path / "chunks" / "stream-20260817T13.ndjson.zst").is_file()
        assert (tmp_path / "manifests" / "stream-20260817T13.manifest.json").is_file()
        assert (tmp_path / "chunks" / "stream-20260817T14.ndjson.zst.partial").is_file()
        await store.stop()

    asyncio.run(scenario())


def test_crash_restart_preserves_finalized_hour_and_recovers_checkpoint(tmp_path: Path) -> None:
    async def scenario() -> None:
        chunks = tmp_path / "chunks"
        manifests = tmp_path / "manifests"
        store = BoundedHourlyStreamStore(
            chunk_directory=chunks,
            manifest_directory=manifests,
            checkpoint_message_interval=2,
            checkpoint_seconds=999,
        )
        await store.start()
        base = datetime(2026, 8, 17, 13, tzinfo=UTC)
        for index in range(3):
            stamp = base + timedelta(seconds=index)
            await store.ingest(
                {"T": "q", "S": "SPY", "t": stamp.isoformat(), "bp": 1, "ap": 2},
                observed_at=stamp,
            )
        hour14 = base + timedelta(hours=1)
        await store.ingest(
            {"T": "q", "S": "SPY", "t": hour14.isoformat(), "bp": 1, "ap": 2},
            observed_at=hour14,
        )
        await store.drain()
        finalized = chunks / "stream-20260817T13.ndjson.zst"
        before = hashlib.sha256(finalized.read_bytes()).hexdigest()
        await store.abort_without_finalizing()

        restarted = BoundedHourlyStreamStore(
            chunk_directory=chunks,
            manifest_directory=manifests,
            checkpoint_message_interval=2,
            checkpoint_seconds=999,
        )
        await restarted.start()
        for offset in (10, 11):
            stamp = hour14 + timedelta(seconds=offset)
            await restarted.ingest(
                {"T": "q", "S": "SPY", "t": stamp.isoformat(), "bp": 1, "ap": 2},
                observed_at=stamp,
            )
        hour15 = base + timedelta(hours=2)
        await restarted.ingest(
            {"T": "q", "S": "SPY", "t": hour15.isoformat(), "bp": 1, "ap": 2},
            observed_at=hour15,
        )
        await restarted.stop()
        after = hashlib.sha256(finalized.read_bytes()).hexdigest()
        events = [
            row["event_time_utc"]
            for path in sorted(chunks.glob("*.ndjson.zst"))
            for row in reconstruct_chunk(path)
        ]
        assert before == after
        assert len(events) == len(set(events)) == 6
        assert restarted.recovery_discarded_bytes >= 0

    asyncio.run(scenario())


def test_normal_stream_has_zero_loss_or_duplicates(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = BoundedHourlyStreamStore(
            chunk_directory=tmp_path / "chunks",
            manifest_directory=tmp_path / "manifests",
            checkpoint_message_interval=25,
        )
        await store.start()
        base = datetime(2026, 8, 17, 13, tzinfo=UTC)
        for index in range(500):
            stamp = base + timedelta(seconds=index * 10)
            await store.ingest(
                {"T": "q", "S": f"S{index % 35:02d}", "t": stamp.isoformat(), "bp": 1, "ap": 2},
                observed_at=stamp,
            )
        await store.stop()
        rows = [
            row
            for path in sorted((tmp_path / "chunks").glob("*.ndjson.zst"))
            for row in reconstruct_chunk(path)
        ]
        assert len(rows) == 500
        assert len({(row["symbol"], row["event_time_utc"]) for row in rows}) == 500
        assert store.dropped_message_count == 0

    asyncio.run(scenario())


def test_operator_heartbeat_advances_during_wait(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = BoundedHourlyStreamStore(
            chunk_directory=tmp_path / "chunks", manifest_directory=tmp_path / "manifests"
        )
        archive = SimpleNamespace(
            store=store,
            websocket_connected=True,
            last_message_at_utc=datetime.now(UTC).isoformat(),
        )
        stop = asyncio.Event()
        path = tmp_path / "runtime_status.json"
        task = asyncio.create_task(
            run_heartbeat(
                path=path,
                archive=archive,
                run={"run_id": "run", "experiment_lane": "lane"},
                universe_size=35,
                state={
                    "runtime_status": "RUNNING",
                    "phase": "WAITING_FOR_OBSERVATION",
                    "next_event": "decision_snapshot",
                    "next_event_at_utc": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                    "last_completed_snapshot": "preclose_snapshot",
                },
                stop=stop,
                interval_seconds=0.01,
            )
        )
        payload: dict[str, Any] = {}
        for _ in range(100):
            await asyncio.sleep(0.02)
            if path.is_file():
                payload = json.loads(path.read_text())
                if payload.get("heartbeat_sequence", 0) >= 2:
                    break
        stop.set()
        await task
        payload = json.loads(path.read_text())
        assert payload["heartbeat_sequence"] >= 2
        assert payload["websocket_connected"] is True
        assert payload["queue_depth"] == 0

    asyncio.run(scenario())


def test_operator_json_is_windows_powershell_51_compatible(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        return
    scheduled = datetime(2026, 8, 17, 19, 45, tzinfo=UTC)
    payload = build_point_payload(
        PointCapture("decision_snapshot", scheduled.isoformat(), scheduled.isoformat(), (), ()),
        _freeze(["SPY"], scheduled),
        None,
    )
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$x = Get-Content -LiteralPath '{path}' -Raw | ConvertFrom-Json; $x.schema_version",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "mso-private-observation-point-v3" in result.stdout
