from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from market_state_observatory.analysis.model_disposition import (
    ModelDispositionError,
    ModelDispositionRegistry,
)
from market_state_observatory.analysis.prospective_candidate import (
    PriceObservation,
    capture_execution_quote,
    distinct_date_gate_status,
    execution_price_returns,
    freeze_candidate_signal,
)
from market_state_observatory.analysis.prospective_settlement import (
    day_clustered_bootstrap,
    paired_common_date_ablation,
    settle_pending_candidates,
    trading_day_offset,
)
from market_state_observatory.execution_modes import ExecutionMode, authorize_mode
from market_state_observatory.runtime.alpaca_adapter import RestResult


def _symbol(
    symbol: str,
    price: float,
    event_time: str,
    observed_at: str,
    *,
    quote_age: float = 1.0,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "observation_status": "CAPTURED",
        "primary_pit_source": "websocket_sip",
        "quote": {
            "status": "READY",
            "bid": price - 0.05,
            "ask": price + 0.05,
            "mid": price,
            "quoted_spread": 0.1,
            "freshness_age_seconds": quote_age,
            "provider_event_time_utc": event_time,
            "collector_observed_at_utc": observed_at,
        },
        "last_trade": {"status": "READY", "price": price},
        "minute_bar": {"status": "READY", "volume": 1000.0},
        "vwap": {"status": "READY", "value": price * 0.995},
        "session_range": {"status": "READY", "low": price * 0.98, "high": price * 1.01},
    }


def _point_payload(name: str, scheduled: str, observed: str, prices: dict[str, float]) -> dict[str, Any]:
    event = datetime.fromisoformat(scheduled).replace(tzinfo=UTC).isoformat()
    return {
        "schema_version": "mso-private-observation-point-v3",
        "observation_point": name,
        "scheduled_at_utc": scheduled,
        "captured_at_utc": observed,
        "freeze_started_at_utc": observed,
        "freeze_completed_at_utc": observed,
        "earliest_event_time_utc": event,
        "latest_event_time_utc": event,
        "event_time_dispersion_seconds": 0.0,
        "freeze_duration_seconds": 0.01,
        "snapshot_bundle_sha256": "a" * 64,
        "backfilled": False,
        "future_timestamp_count": 0,
        "symbols": [
            _symbol(symbol, price, event, observed) for symbol, price in sorted(prices.items())
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _make_run(
    root: Path,
    *,
    trading_date: str = "2026-08-24",
    run_id: str = "run-20260824",
    include_close: bool = True,
    price_shift: float = 0.0,
) -> Path:
    run = root / trading_date / run_id
    _write_json(
        run / "RUN.json",
        {
            "run_id": run_id,
            "trading_date": trading_date,
            "experiment_lane": "test-lane",
            "created_at_utc": f"{trading_date}T13:20:00+00:00",
            "paper_positions": 0,
            "real_orders": 0,
        },
    )
    _write_json(
        run / "reference" / "membership_snapshot.json",
        {
            "themes": [
                {
                    "theme_id": "semiconductors",
                    "theme_etf": "SMH",
                    "industry_benchmark": "SOXX",
                    "basket": ["NVDA", "AMD"],
                },
                {
                    "theme_id": "solar_energy",
                    "theme_etf": "TAN",
                    "industry_benchmark": "XLE",
                    "basket": ["FSLR", "ENPH"],
                },
            ]
        },
    )
    day = date.fromisoformat(trading_date)
    base = {
        "SPY": 500.0 + price_shift,
        "SMH": 250.0 + price_shift,
        "SOXX": 200.0 + price_shift,
        "NVDA": 180.0 + price_shift,
        "AMD": 160.0 + price_shift,
        "TAN": 40.0 + price_shift,
        "XLE": 90.0 + price_shift,
        "FSLR": 220.0 + price_shift,
        "ENPH": 35.0 + price_shift,
    }
    points = {
        "open_snapshot": ("13:30:00", "13:30:01", base),
        "preclose_snapshot": (
            "19:30:00",
            "19:30:01",
            {key: value * (1.005 if key in {"SMH", "NVDA", "AMD"} else 0.998) for key, value in base.items()},
        ),
        "decision_snapshot": (
            "19:45:00",
            "19:45:01",
            {key: value * (1.01 if key in {"SMH", "NVDA", "AMD"} else 0.995) for key, value in base.items()},
        ),
    }
    if include_close:
        points["session_close_diagnostic"] = (
            "20:00:00",
            "20:00:01",
            {key: value * 1.012 for key, value in base.items()},
        )
    for name, (clock, observed_clock, prices) in points.items():
        scheduled = f"{day.isoformat()}T{clock}+00:00"
        observed = f"{day.isoformat()}T{observed_clock}+00:00"
        _write_json(
            run / "manifests" / "points" / f"{name}.json",
            _point_payload(name, scheduled, observed, prices),
        )
    if include_close:
        _write_json(run / "quality" / "DATA_QUALITY.json", {"data_quality_pass": True})
    return run


class _FakeAdapter:
    def __init__(self, result: RestResult):
        self.result = result

    def latest_quotes(self, symbols: object) -> RestResult:
        return self.result


def _rest_result(event_time: str, observed_at: str, *, bid: float = 251.0, ask: float = 251.1) -> RestResult:
    body = {
        "quotes": {
            "SMH": {"bp": bid, "ap": ask, "t": event_time},
            "TAN": {"bp": 39.7, "ap": 39.8, "t": event_time},
        }
    }
    raw = json.dumps(body, sort_keys=True).encode()
    return RestResult(
        collector_request_id="00000000-0000-0000-0000-000000000001",
        provider_request_id=None,
        request_started_at_utc=observed_at,
        observed_at_utc=observed_at,
        response_status=200,
        sanitized_request_parameters={"symbols": "SMH,TAN", "feed": "sip"},
        response_headers_sha256="b" * 64,
        raw_response=raw,
        body=body,
        server_date_utc=observed_at,
    )


def test_prospective_mode_is_candidate_only() -> None:
    authorization = authorize_mode(ExecutionMode.PROSPECTIVE_CANDIDATE_SHADOW)
    assert authorization.evidence_grade == "prospective_unvalidated"
    assert authorization.may_run_candidates is True
    assert authorization.may_emit_actions is False
    assert authorization.paper_positions_allowed is False
    assert authorization.real_orders_allowed is False


def test_retired_model_cannot_reactivate() -> None:
    registry = ModelDispositionRegistry.load()
    with pytest.raises(ModelDispositionError, match="activation rejected"):
        registry.assert_not_reactivated("D1_H2_DAILY_RECONSTRUCTED", True)


def test_candidate_freezes_before_outcome_and_excludes_post_signal_sources(tmp_path: Path) -> None:
    run = _make_run(tmp_path / "runs")
    signal = freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
    )
    assert signal["candidate_status"] == "FROZEN"
    assert signal["candidate_frozen_before_outcome"] is True
    assert signal["broker_order_object"] is None
    candidate_dir = tmp_path / "candidate" / "preclose" / "2026-08-24" / "run-20260824-preclose"
    before = (candidate_dir / "CANDIDATE_SIGNAL.json").read_bytes()
    second = freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, 30, tzinfo=UTC),
    )
    assert second == signal
    assert (candidate_dir / "CANDIDATE_SIGNAL.json").read_bytes() == before
    manifest = json.loads((candidate_dir / "CANDIDATE_SIGNAL_MANIFEST.json").read_text())
    sources = {row["relative_path"] for row in manifest["source_artifacts"]}
    assert not any("session_close" in value or "DATA_QUALITY" in value for value in sources)


def test_five_day_momentum_uses_only_prior_immutable_closes(tmp_path: Path) -> None:
    history = tmp_path / "history"
    prior_dates = (
        "2026-08-14",
        "2026-08-17",
        "2026-08-18",
        "2026-08-19",
        "2026-08-20",
        "2026-08-21",
    )
    for index, trading_date in enumerate(prior_dates):
        _make_run(
            history,
            trading_date=trading_date,
            run_id=f"history-{trading_date}",
            price_shift=float(index),
        )
    current = _make_run(history, include_close=True)
    candidate_root = tmp_path / "candidate"
    signal = freeze_candidate_signal(
        run_directory=current,
        candidate_root=candidate_root,
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
        history_run_roots=[history],
    )
    b1 = next(row for row in signal["arms"] if row["arm"] == "B1_THEME_ETF_5D_MOMENTUM")
    assert b1["status"] == "ESTIMATED"
    assert b1["score"] is not None
    manifest = json.loads(
        next(candidate_root.rglob("CANDIDATE_SIGNAL_MANIFEST.json")).read_text(encoding="utf-8")
    )
    history_paths = [
        row["relative_path"]
        for row in manifest["source_artifacts"]
        if row["relative_path"].startswith("history/")
    ]
    assert len(history_paths) == 12
    assert all("2026-08-24" not in path for path in history_paths)


def test_stale_candidate_is_blocked(tmp_path: Path) -> None:
    run = _make_run(tmp_path / "runs", run_id="late-run")
    signal = freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 47, tzinfo=UTC),
    )
    assert signal["candidate_status"] == "BLOCKED"
    assert "candidate_generation_timeout" in signal["blocking_reasons"]


def test_execution_quote_must_follow_candidate_and_be_fresh(tmp_path: Path) -> None:
    run = _make_run(tmp_path / "runs")
    freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
    )
    candidate_dir = tmp_path / "candidate" / "preclose" / "2026-08-24" / "run-20260824-preclose"
    quote = capture_execution_quote(
        candidate_directory=candidate_dir,
        adapter=_FakeAdapter(_rest_result("2026-08-24T19:47:01+00:00", "2026-08-24T19:47:02+00:00")),
        observed_at=datetime(2026, 8, 24, 19, 47, 2, tzinfo=UTC),
    )
    assert quote["status"] == "EXECUTION_QUOTE_READY"
    assert datetime.fromisoformat(quote["quotes"][0]["event_time_utc"]) > datetime.fromisoformat(
        "2026-08-24T19:46:00+00:00"
    )


@pytest.mark.parametrize(
    ("event_time", "observed_at", "reason"),
    [
        ("2026-08-24T19:45:59+00:00", "2026-08-24T19:47:02+00:00", "execution_quote_not_after_candidate"),
        ("2026-08-24T19:45:50+00:00", "2026-08-24T19:47:02+00:00", "execution_quote_stale"),
    ],
)
def test_bad_execution_quote_is_blocked(
    tmp_path: Path, event_time: str, observed_at: str, reason: str
) -> None:
    run = _make_run(tmp_path / "runs")
    freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
    )
    candidate_dir = tmp_path / "candidate" / "preclose" / "2026-08-24" / "run-20260824-preclose"
    quote = capture_execution_quote(
        candidate_directory=candidate_dir,
        adapter=_FakeAdapter(_rest_result(event_time, observed_at)),
        observed_at=datetime.fromisoformat(observed_at),
    )
    assert quote["status"] == "BLOCKED"
    assert any(reason in value for value in quote["blocking_reasons"])


def test_long_and_short_execution_contracts() -> None:
    entry = PriceObservation(99.0, 101.0, 100.0, "2026-08-24T19:47:00+00:00", "2026-08-24T19:47:01+00:00", "SIP", "a", "a" * 64)
    exit_value = PriceObservation(109.0, 111.0, 110.0, "2026-08-25T20:00:00+00:00", "2026-08-25T20:00:01+00:00", "SIP", "b", "b" * 64)
    long_result = execution_price_returns(predicted_sign=1, entry=entry, exit=exit_value)
    short_result = execution_price_returns(predicted_sign=-1, entry=entry, exit=exit_value)
    assert long_result["spread_realistic_gross_return"] == pytest.approx(109 / 101 - 1)
    assert short_result["spread_realistic_gross_return"] == pytest.approx((99 - 111) / 99)
    assert long_result["fixed_cost_net_returns"]["10"] == pytest.approx(109 / 101 - 1 - 0.001)
    assert long_result["mid_is_executable_claim"] is False


def test_holiday_and_weekend_horizon() -> None:
    assert trading_day_offset(date(2026, 7, 2), 1) == date(2026, 7, 6)
    assert trading_day_offset(date(2026, 7, 2), 3) == date(2026, 7, 8)


def test_settlement_is_append_only_and_idempotent(tmp_path: Path) -> None:
    source = _make_run(tmp_path / "runs")
    next_run = _make_run(
        tmp_path / "runs",
        trading_date="2026-08-25",
        run_id="run-20260825",
        price_shift=20.0,
    )
    assert source != next_run
    freeze_candidate_signal(
        run_directory=source,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
    )
    candidate_dir = tmp_path / "candidate" / "preclose" / "2026-08-24" / "run-20260824-preclose"
    capture_execution_quote(
        candidate_directory=candidate_dir,
        adapter=_FakeAdapter(_rest_result("2026-08-24T19:47:01+00:00", "2026-08-24T19:47:02+00:00")),
        observed_at=datetime(2026, 8, 24, 19, 47, 2, tzinfo=UTC),
    )
    first = settle_pending_candidates(
        candidate_root=tmp_path / "candidate",
        run_roots=[tmp_path / "runs"],
        ledger_root=tmp_path / "ledger",
        settlement_root=tmp_path / "settlements",
        settlement_run_id="settlement-20260825",
        settled_at_utc="2026-08-25T20:15:00+00:00",
    )
    ledger = tmp_path / "ledger" / "PROSPECTIVE_OUTCOME_LEDGER.ndjson"
    before = ledger.read_bytes()
    manifest_before = Path(first["settlement_manifest_path"]).read_bytes()
    second = settle_pending_candidates(
        candidate_root=tmp_path / "candidate",
        run_roots=[tmp_path / "runs"],
        ledger_root=tmp_path / "ledger",
        settlement_root=tmp_path / "settlements",
        settlement_run_id="settlement-20260825",
        settled_at_utc="2026-08-25T20:15:00+00:00",
    )
    assert ledger.read_bytes() == before
    assert Path(second["settlement_manifest_path"]).read_bytes() == manifest_before


def test_missing_future_run_remains_pending(tmp_path: Path) -> None:
    source = _make_run(tmp_path / "runs")
    analysis = tmp_path / "analysis"
    _write_json(analysis / "DAILY_REPORT_STATUS.json", {"status": "COMPLETE"})
    _write_json(analysis / "OBSERVATION_REPORT.json", {"status": "COMPLETE"})
    freeze_candidate_signal(
        run_directory=source,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="postclose",
        generated_at=datetime(2026, 8, 24, 20, 15, tzinfo=UTC),
        analysis_directory=analysis,
    )
    result = settle_pending_candidates(
        candidate_root=tmp_path / "candidate",
        run_roots=[tmp_path / "runs"],
        ledger_root=tmp_path / "ledger",
        settlement_root=tmp_path / "settlements",
        settlement_run_id="missing-future",
        settled_at_utc="2026-08-24T20:16:00+00:00",
    )
    assert result["appended_outcome_ids"] == []
    assert result["pending"]
    assert result["backfill_used"] is False


def test_common_date_ablation_and_day_cluster_count() -> None:
    def row(day: str, arm: str, value: float) -> dict[str, Any]:
        return {
            "signal_date": day,
            "arm": arm,
            "horizon": "next_open_to_3d_close",
            "status": "SETTLED",
            "returns": {"fixed_cost_net_returns": {"10": value}},
        }

    rows = [row("2026-08-24", "A", 0.01), row("2026-08-24", "B", 0.02), row("2026-08-25", "A", -0.01)]
    result = paired_common_date_ablation(rows, "A", "B", "next_open_to_3d_close")
    assert result["common_legal_dates"] == 1
    assert result["paired_mean_difference"] == pytest.approx(0.01)
    clustered = day_clustered_bootstrap(
        [
            {"signal_date": "2026-08-24", "value": 1.0},
            {"signal_date": "2026-08-24", "value": 3.0},
            {"signal_date": "2026-08-25", "value": 2.0},
        ],
        value_key="value",
        iterations=50,
    )
    assert clustered["mean"] is not None


def test_gate_counts_dates_not_theme_rows_and_excludes_rehearsal() -> None:
    base = {
        "valid_trading_date": True,
        "official_strategy_evidence": True,
        "prospective_unvalidated": True,
    }
    rows = [
        {**base, "signal_date": "2026-08-24", "theme_id": "a"},
        {**base, "signal_date": "2026-08-24", "theme_id": "b"},
        {**base, "signal_date": "2026-08-25", "theme_id": "a"},
        {**base, "signal_date": "2026-08-26", "official_strategy_evidence": False},
    ]
    status = distinct_date_gate_status(rows)
    assert status["valid_trading_dates"] == 2
    assert status["theme_rows_inflate_sample_count"] is False
    assert status["positive_promotion_before_60_allowed"] is False


def test_generated_artifacts_never_contain_positions_or_orders(tmp_path: Path) -> None:
    run = _make_run(tmp_path / "runs")
    freeze_candidate_signal(
        run_directory=run,
        candidate_root=tmp_path / "candidate",
        ledger_root=tmp_path / "ledger",
        lane="preclose",
        generated_at=datetime(2026, 8, 24, 19, 46, tzinfo=UTC),
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json"))
    assert '"paper_positions":0' in text
    assert '"real_orders":0' in text
    assert '"broker_order_object":null' in text


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell contract")
def test_preclose_powershell_whatif_changes_nothing() -> None:
    shell = (
        Path(os.environ["SYSTEMROOT"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    result = subprocess.run(
        [
            str(shell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "tests/powershell/prospective_candidate_shadow_tests.ps1",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "PRECLOSE_CANDIDATE_POWERSHELL_TESTS=PASS" in result.stdout
    assert "SCHEDULER_CHANGED=false" in result.stdout
