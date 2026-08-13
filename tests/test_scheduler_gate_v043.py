from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.runtime.formal_promotion import FormalPromotionError
from market_state_observatory.runtime.quality_engine import CORE_POINTS, evaluate_run_quality


def _quality_fixture(tmp_path: Path, *, mode: str, requested_count: bool) -> dict[str, object]:
    formal = mode == "formal"
    run = {
        "run_id": "run",
        "trading_date": "2026-08-13",
        "status": "FORMAL_DATA_SHADOW" if formal else "DATA_CAPTURE_REHEARSAL",
        "mode": mode,
        "publication_as_formal": formal,
        "production_release": True,
        "membership_snapshot_frozen": True,
        "counts_toward_20_day_gate": requested_count,
        "counts_toward_model_shadow": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    (tmp_path / "RUN.json").write_text(json.dumps(run), encoding="utf-8")
    symbols = ["SPY", "SMH", "SOXX", "NVDA"]
    for point in CORE_POINTS:
        payload = {
            "observation_point": point,
            "captured_at_utc": "2026-08-13T15:45:01+00:00",
            "cross_section_skew_seconds": 1,
            "future_timestamp_count": 0,
            "backfilled": False,
            "symbols": [
                {"symbol": symbol, "quote_age_seconds": 1, "vwap": 100} for symbol in symbols
            ],
        }
        path = tmp_path / "manifests" / "points" / f"{point}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
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
    return evaluate_run_quality(tmp_path, universe)


def test_rehearsal_cannot_count_toward_twenty_day_gate_even_if_run_flag_is_tampered(
    tmp_path: Path,
) -> None:
    quality = _quality_fixture(tmp_path, mode="rehearsal", requested_count=True)
    assert quality["data_quality_pass"] is True
    assert quality["counts_toward_20_day_gate"] is False
    assert quality["counts_toward_model_shadow"] is False
    assert quality["publication_as_formal"] is False
    assert quality["publication_eligible"] is False


def test_formal_data_shadow_never_counts_toward_model_shadow(tmp_path: Path) -> None:
    quality = _quality_fixture(tmp_path, mode="formal", requested_count=True)
    assert quality["counts_toward_20_day_gate"] is True
    assert quality["counts_toward_model_shadow"] is False
    assert quality["paper_positions"] == 0
    assert quality["real_orders"] == 0


def test_formal_promotion_error_is_fail_closed() -> None:
    assert issubclass(FormalPromotionError, RuntimeError)
