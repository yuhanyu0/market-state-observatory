from __future__ import annotations

import csv
import shutil
from pathlib import Path

from market_state_observatory.analysis.experiment_runner import (
    ReplayRecord,
    register_experiment,
    run_registered_replay,
)
from market_state_observatory.analysis.historical_validation import (
    EVIDENCE_H1,
    EVIDENCE_H3,
    _label,
    _load_price_bars,
    audit_h1_runs,
    build_ablations,
    freeze_evaluation_folds,
    load_h3_attention,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "completed_run_2026-08-18"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_frozen_folds_are_expanding_with_one_date_purge_and_embargo() -> None:
    dates = [f"2026-01-{day:02d}" for day in range(1, 13)]
    folds = freeze_evaluation_folds(dates, minimum_train=5, test_size=2, purge=1, embargo=1)
    assert len(folds) == 2
    assert folds[0].train_dates == tuple(dates[:4])
    assert folds[0].purged_dates == (dates[4],)
    assert folds[0].embargoed_dates == (dates[5],)
    assert folds[0].test_dates == tuple(dates[6:8])
    assert set(folds[0].train_dates).isdisjoint(folds[0].test_dates)
    assert len(folds[1].train_dates) > len(folds[0].train_dates)


def test_close_origin_labels_are_future_diagnostics_not_execution_claims(tmp_path: Path) -> None:
    rows = [
        {
            "date": f"2026-01-{day:02d}",
            "open": 100 + day,
            "close": 101 + day,
            "dividends": 0,
            "stock_splits": 0,
            "capital_gains": 0,
        }
        for day in range(1, 8)
    ]
    for ticker, scale in (("ETF", 1.0), ("SPY", 0.5)):
        adjusted = [
            {**row, "open": 100 + (int(str(row["date"])[-2:]) * scale), "close": 101 + (int(str(row["date"])[-2:]) * scale)}
            for row in rows
        ]
        _write_csv(
            tmp_path / f"{ticker}.csv",
            ["date", "open", "close", "dividends", "stock_splits", "capital_gains"],
            adjusted,
        )
    etf_rows, etf_index = _load_price_bars(tmp_path / "ETF.csv")
    spy_rows, spy_index = _load_price_bars(tmp_path / "SPY.csv")
    close_label = _label(
        etf_rows, etf_index, spy_rows, spy_index, "2026-01-01", "close_to_next_close"
    )
    executable = _label(
        etf_rows,
        etf_index,
        spy_rows,
        spy_index,
        "2026-01-01",
        "next_open_to_next_close",
    )
    assert close_label is not None and close_label["target_date"] > "2026-01-01"
    assert close_label["same_day_close_execution_claim"] is False
    assert close_label["execution_eligible"] is False
    assert executable is not None and executable["execution_eligible"] is True


def test_exact_pit_rehearsal_has_provenance_but_not_accuracy_eligibility(tmp_path: Path) -> None:
    run = tmp_path / "observations" / "rehearsals" / "2026-08-18" / "run"
    shutil.copytree(FIXTURE, run)
    records, audit = audit_h1_runs(tmp_path / "observations")
    assert audit["run_count"] == 1
    assert audit["theme_run_records"] == 6
    assert audit["labeled_outcome_records"] == 0
    assert all(row["evidence_lane"] == EVIDENCE_H1 for row in records)
    assert all(row["rehearsal"] is True for row in records)
    assert all(row["official_strategy_evidence"] is False for row in records)


def test_theme_radar_import_remains_unsigned_and_shifted_rows_are_separate(tmp_path: Path) -> None:
    output = tmp_path / "output"
    _write_csv(
        output / "signal_snapshots.csv",
        ["log_date", "session"],
        [
            {"log_date": "2026-01-02", "session": "midday"},
            {"log_date": "2026-01-02", "session": "postclose"},
        ],
    )
    state_fields = [
        "signal_date",
        "session",
        "session_bucket",
        "time_eligibility",
        "selected_theme",
        "theme_etf",
        "theme_etf_next_close_return",
        "spy_next_close_return",
        "theme_relative_return",
        "episode_age",
    ]
    _write_csv(
        output / "theme_state_daily.csv",
        state_fields,
        [
            {
                "signal_date": "2026-01-02",
                "session": "midday",
                "session_bucket": "same_day_midday",
                "time_eligibility": "same_day_pre_entry",
                "selected_theme": "Semis",
                "theme_etf": "SMH",
                "theme_etf_next_close_return": 0.01,
                "spy_next_close_return": 0.002,
                "theme_relative_return": 0.008,
                "episode_age": 1,
            },
            {
                "signal_date": "2026-01-03",
                "session": "postclose",
                "session_bucket": "postclose_shifted",
                "time_eligibility": "postclose_shifted",
                "selected_theme": "Semis",
                "theme_etf": "SMH",
                "theme_etf_next_close_return": -0.01,
                "spy_next_close_return": -0.002,
                "theme_relative_return": -0.008,
                "episode_age": 2,
            },
        ],
    )
    episode_fields = [
        "mode",
        "episode_id",
        "episode_theme",
        "episode_length",
        "gross_return",
        "net_return_10bps",
        "counts_as_settled_return",
    ]
    _write_csv(
        output / "s5_episode_trades.csv",
        episode_fields,
        [
            {
                "mode": "daily_reset",
                "episode_id": 1,
                "episode_theme": "Semis",
                "episode_length": 2,
                "gross_return": 0.01,
                "net_return_10bps": 0.009,
                "counts_as_settled_return": True,
            },
            {
                "mode": "hold_until_change",
                "episode_id": 1,
                "episode_theme": "Semis",
                "episode_length": 2,
                "gross_return": 0.02,
                "net_return_10bps": 0.019,
                "counts_as_settled_return": True,
            },
            {
                "mode": "transition_only",
                "episode_id": 1,
                "episode_theme": "Semis",
                "episode_length": 2,
                "gross_return": 0.01,
                "net_return_10bps": 0.009,
                "counts_as_settled_return": True,
            },
        ],
    )
    attention, episodes, audit = load_h3_attention(tmp_path)
    assert len(attention) == 2 and len(episodes) == 1
    assert audit["same_day_pre_entry_rows"] == 1
    assert audit["shifted_rows"] == 1
    assert all(row["evidence_lane"] == EVIDENCE_H3 for row in attention)
    assert all(row["unsigned_attention_only"] is True for row in attention)
    assert all(row["may_determine_direction"] is False for row in attention)


def test_missing_transmission_produces_zero_common_sample_ablations() -> None:
    rows = build_ablations({})
    required = {
        "D1_vs_D1_plus_T",
        "D1_plus_T_vs_D1_plus_T_plus_E0",
        "D1_plus_T_vs_D1_plus_T_plus_ThemeRadarAttention",
        "T_plus_E_vs_T_plus_E_plus_Playbook",
    }
    blocked = [row for row in rows if row["ablation"] in required]
    assert len(blocked) == 4
    assert all(row["common_legal_dates"] == 0 for row in blocked)
    assert all(row["status"] == "INSUFFICIENT_EVIDENCE" for row in blocked)


def test_experiment_runner_completes_metric_placeholders() -> None:
    registration = register_experiment(
        "D1", ["2026-01-01T20:00:00+00:00"], registered_at_utc="2026-01-01T00:00:00+00:00"
    )
    records = [
        ReplayRecord(
            "2026-01-01T20:00:00+00:00",
            "2026-01-02T20:00:00+00:00",
            "semiconductors",
            "episode-1",
            0.7,
            1,
            0.02,
            10,
            "SMH",
            0.005,
        ),
        ReplayRecord(
            "2026-02-01T20:00:00+00:00",
            "2026-02-02T20:00:00+00:00",
            "cloud_computing",
            "episode-2",
            0.3,
            -1,
            -0.01,
            10,
            "SKYY",
            -0.002,
        ),
    ]
    result = run_registered_replay(registration, records)
    metrics = result["metrics"]
    assert metrics["turnover"] == 1.0
    assert metrics["maximum_drawdown"] is not None
    assert metrics["calibration_curve"]
    assert metrics["conditional_return"]["predicted_positive"] == 0.02
    assert metrics["concentration"]["top_theme_absolute_pnl_share"] is not None
    assert metrics["ablation"]["status"] == "complete_same_record_pairing"
    assert result["failure_slices"]
    assert result["paper_positions"] == result["real_orders"] == 0
