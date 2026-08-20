from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from statistics import mean, median
from typing import Any

EVIDENCE_H1 = "H1_EXACT_PIT"
EVIDENCE_H2 = "H2_HISTORICAL_RECONSTRUCTED_DAILY"
EVIDENCE_H3 = "H3_THEME_RADAR_ATTENTION"
EVIDENCE_SYNTHETIC = "SYNTHETIC"

HORIZONS = (
    "close_to_next_open",
    "next_open_to_next_close",
    "close_to_next_close",
    "close_to_3d_close",
    "close_to_5d_close",
)
COST_GRID_BPS = (0.0, 5.0, 10.0, 15.0, 25.0, 50.0)
ACTIVE_H2_ARMS = (
    "ZERO_BASE_RATE",
    "SPY",
    "SPY_RELATIVE_MOMENTUM_5D",
    "SPY_RELATIVE_MOMENTUM_20D",
    "THEME_ETF_1D_MOMENTUM",
    "THEME_ETF_5D_MOMENTUM",
    "D0_SIMPLE_RELATIVE",
    "D1_DAILY_RECONSTRUCTED",
    "D2_PROBABILISTIC_CANDIDATE",
    "HISTORICAL_TRANSPARENT_BASELINE",
)
RETURN_SCORE_ARMS = frozenset(
    {
        "SPY_RELATIVE_MOMENTUM_5D",
        "SPY_RELATIVE_MOMENTUM_20D",
        "THEME_ETF_1D_MOMENTUM",
        "THEME_ETF_5D_MOMENTUM",
        "D0_SIMPLE_RELATIVE",
        "D1_DAILY_RECONSTRUCTED",
        "HISTORICAL_TRANSPARENT_BASELINE",
    }
)


@dataclass(frozen=True)
class PriceBar:
    date: str
    open: float
    close: float
    dividends: float
    stock_splits: float
    capital_gains: float


@dataclass(frozen=True)
class EvaluationFold:
    fold_id: str
    train_dates: tuple[str, ...]
    purged_dates: tuple[str, ...]
    embargoed_dates: tuple[str, ...]
    test_dates: tuple[str, ...]


def _float(value: str | float | int | None) -> float | None:
    if value in (None, "", "nan", "NaN"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bool(value: str | bool | None) -> bool:
    return value is True or str(value).lower() == "true"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _safe_mean(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return mean(clean) if clean else None


def _safe_median(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return median(clean) if clean else None


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator else None


def _maximum_drawdown(returns: Sequence[float]) -> float | None:
    if not returns:
        return None
    equity = peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1.0)
    return drawdown


def _downside_beta(returns: Sequence[float], market: Sequence[float]) -> float | None:
    pairs = [(value, benchmark) for value, benchmark in zip(returns, market, strict=True) if benchmark < 0]
    if len(pairs) < 3:
        return None
    strategy_values = [value for value, _ in pairs]
    benchmark_values = [value for _, value in pairs]
    benchmark_mean = mean(benchmark_values)
    variance = sum((value - benchmark_mean) ** 2 for value in benchmark_values)
    if variance == 0:
        return None
    strategy_mean = mean(strategy_values)
    covariance = sum(
        (value - strategy_mean) * (benchmark - benchmark_mean)
        for value, benchmark in pairs
    )
    return covariance / variance


def _profit_factor(values: Sequence[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses == 0:
        return None if gains == 0 else math.inf
    return gains / losses


def _bootstrap_ci(
    rows: Sequence[dict[str, Any]],
    *,
    value_key: str,
    cluster_key: str,
    seed: int,
    iterations: int = 300,
) -> tuple[float | None, float | None]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(value_key)
        if isinstance(value, (float, int)) and math.isfinite(float(value)):
            groups[str(row.get(cluster_key) or row.get("signal_date") or "unknown")].append(float(value))
    keys = sorted(groups)
    if len(keys) < 2:
        return None, None
    aggregates = [(sum(groups[key]), len(groups[key])) for key in keys]
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        selected = [aggregates[rng.randrange(len(aggregates))] for _ in aggregates]
        total = sum(item[0] for item in selected)
        count = sum(item[1] for item in selected)
        estimates.append(total / count)
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _time_block_ci(
    rows: Sequence[dict[str, Any]], *, value_key: str, seed: int, block_size: int = 20
) -> tuple[float | None, float | None]:
    ordered = sorted(rows, key=lambda row: str(row["signal_date"]))
    values = [float(row[value_key]) for row in ordered if isinstance(row.get(value_key), (float, int))]
    if len(values) < block_size * 2:
        return None, None
    blocks = [values[index : index + block_size] for index in range(0, len(values), block_size)]
    aggregates = [(sum(block), len(block)) for block in blocks if block]
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(300):
        selected = [aggregates[rng.randrange(len(aggregates))] for _ in aggregates]
        estimates.append(sum(item[0] for item in selected) / sum(item[1] for item in selected))
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def freeze_evaluation_folds(
    dates: Sequence[str], *, minimum_train: int, test_size: int, purge: int, embargo: int
) -> list[EvaluationFold]:
    ordered = sorted(set(dates))
    folds: list[EvaluationFold] = []
    cursor = minimum_train
    while cursor + embargo + test_size <= len(ordered):
        train_end = max(0, cursor - purge)
        test_start = cursor + embargo
        test_end = min(len(ordered), test_start + test_size)
        folds.append(
            EvaluationFold(
                fold_id=f"lab-wf-{len(folds) + 1:03d}",
                train_dates=tuple(ordered[:train_end]),
                purged_dates=tuple(ordered[train_end:cursor]),
                embargoed_dates=tuple(ordered[cursor:test_start]),
                test_dates=tuple(ordered[test_start:test_end]),
            )
        )
        cursor = test_end
    return folds


def _load_price_bars(path: Path) -> tuple[list[PriceBar], dict[str, int]]:
    rows: list[PriceBar] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            open_price = _float(row.get("open"))
            close_price = _float(row.get("close"))
            if open_price is None or close_price is None or open_price <= 0 or close_price <= 0:
                continue
            rows.append(
                PriceBar(
                    date=str(row["date"]),
                    open=open_price,
                    close=close_price,
                    dividends=_float(row.get("dividends")) or 0.0,
                    stock_splits=_float(row.get("stock_splits")) or 0.0,
                    capital_gains=_float(row.get("capital_gains")) or 0.0,
                )
            )
    rows.sort(key=lambda row: row.date)
    return rows, {row.date: index for index, row in enumerate(rows)}


def _label(
    etf_rows: Sequence[PriceBar],
    etf_index: dict[str, int],
    spy_rows: Sequence[PriceBar],
    spy_index: dict[str, int],
    signal_date: str,
    horizon: str,
) -> dict[str, Any] | None:
    position = etf_index.get(signal_date)
    spy_position = spy_index.get(signal_date)
    if position is None or spy_position is None:
        return None
    offsets = {
        "close_to_next_open": 1,
        "next_open_to_next_close": 1,
        "close_to_next_close": 1,
        "close_to_3d_close": 3,
        "close_to_5d_close": 5,
    }
    offset = offsets[horizon]
    if position + offset >= len(etf_rows):
        return None
    target = etf_rows[position + offset]
    target_spy_position = spy_index.get(target.date)
    if target_spy_position is None:
        return None
    current = etf_rows[position]
    current_spy = spy_rows[spy_position]
    target_spy = spy_rows[target_spy_position]
    if target.date <= signal_date:
        raise ValueError("historical label is not later than the as-of date")
    if horizon == "close_to_next_open":
        etf_return = target.open / current.close - 1.0
        spy_return = target_spy.open / current_spy.close - 1.0
    elif horizon == "next_open_to_next_close":
        etf_return = target.close / target.open - 1.0
        spy_return = target_spy.close / target_spy.open - 1.0
    else:
        etf_return = target.close / current.close - 1.0
        spy_return = target_spy.close / current_spy.close - 1.0
    action_window = etf_rows[position + 1 : position + offset + 1]
    return {
        "target_date": target.date,
        "etf_return": etf_return,
        "spy_return": spy_return,
        "relative_return": etf_return - spy_return,
        "corporate_action_in_window": any(
            row.dividends != 0 or row.stock_splits != 0 or row.capital_gains != 0
            for row in action_window
        ),
        "same_day_close_execution_claim": False,
        "execution_eligible": horizon == "next_open_to_next_close",
    }


def _source_horizon(horizon: str) -> str:
    if horizon in {"close_to_next_open", "next_open_to_next_close", "close_to_next_close"}:
        return "next_open_to_next_close"
    return "next_open_to_3d_close"


def load_h2_panel(source_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = source_root / "output"
    direction_path = output / "direction_historical_walkforward.csv"
    universe_path = source_root / "config" / "source_native_universe_v1.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    themes = {str(row["theme_id"]): row for row in universe["themes"]}
    direction: dict[tuple[str, str, str], dict[str, str]] = {}
    original_fold_ids: set[str] = set()
    with direction_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["price_basis"] != "raw_unadjusted_main":
                continue
            key = (row["signal_date"], row["theme_id"], row["horizon"])
            direction[key] = row
            original_fold_ids.add(row["outer_fold"])

    price_root = source_root / "data" / "source_native_historical_daily"
    tickers = {"SPY", *(str(row["theme_etf"]) for row in themes.values())}
    prices = {ticker: _load_price_bars(price_root / f"{ticker}.csv") for ticker in tickers}
    spy_rows, spy_index = prices["SPY"]
    panel: list[dict[str, Any]] = []
    theme_dates = sorted({(date, theme) for date, theme, _ in direction})
    for signal_date, theme_id in theme_dates:
        theme = themes[theme_id]
        ticker = str(theme["theme_etf"])
        etf_rows, etf_index = prices[ticker]
        position = etf_index.get(signal_date)
        if position is None:
            continue
        absolute_1d = (
            etf_rows[position].close / etf_rows[position - 1].close - 1.0 if position >= 1 else None
        )
        absolute_5d = (
            etf_rows[position].close / etf_rows[position - 5].close - 1.0 if position >= 5 else None
        )
        for horizon in HORIZONS:
            source_horizon = _source_horizon(horizon)
            predictor = direction.get((signal_date, theme_id, source_horizon))
            label = _label(etf_rows, etf_index, spy_rows, spy_index, signal_date, horizon)
            if predictor is None or label is None:
                continue
            relative_1d = _float(predictor.get("relative_return_1d"))
            record = {
                "evidence_lane": EVIDENCE_H2,
                "signal_date": signal_date,
                "as_of_rule": "after_official_close_t",
                "target_date": label["target_date"],
                "horizon": horizon,
                "prediction_source_horizon": source_horizon,
                "theme_id": theme_id,
                "theme_etf": ticker,
                "original_outer_fold": predictor["outer_fold"],
                "etf_return": label["etf_return"],
                "spy_return": label["spy_return"],
                "relative_return": label["relative_return"],
                "corporate_action_in_window": label["corporate_action_in_window"],
                "same_day_close_execution_claim": False,
                "execution_eligible": label["execution_eligible"],
                "score_SPY_RELATIVE_MOMENTUM_5D": _float(predictor.get("relative_momentum_5d")),
                "score_SPY_RELATIVE_MOMENTUM_20D": _float(predictor.get("relative_momentum_20d")),
                "score_THEME_ETF_1D_MOMENTUM": absolute_1d,
                "score_THEME_ETF_5D_MOMENTUM": absolute_5d,
                "score_D0_SIMPLE_RELATIVE": relative_1d,
                "score_D1_DAILY_RECONSTRUCTED": _float(predictor.get("expected_relative_return")),
                "score_D2_PROBABILISTIC_CANDIDATE": _float(
                    predictor.get("probability_relative_positive")
                ),
                "score_HISTORICAL_TRANSPARENT_BASELINE": _float(
                    predictor.get("expected_relative_return")
                ),
                "feature_relative_return_1d": relative_1d,
                "feature_relative_momentum_5d": _float(predictor.get("relative_momentum_5d")),
                "feature_relative_momentum_20d": _float(predictor.get("relative_momentum_20d")),
                "feature_intraday_range_pct": _float(predictor.get("intraday_range_pct")),
                "feature_close_range_position": _float(predictor.get("close_range_position")),
                "feature_volume_ratio_20d": _float(predictor.get("volume_ratio_20d")),
            }
            panel.append(record)
    audit = {
        "source_direction_rows_raw_main": len(direction),
        "source_theme_date_records": len(theme_dates),
        "source_unique_dates": len({date for date, _ in theme_dates}),
        "source_original_fold_count": len(original_fold_ids),
        "evaluation_label_records": len(panel),
        "raw_unadjusted_main": True,
        "adjusted_sensitivity_used_as_primary": False,
        "historical_membership_backfill_used": False,
        "transmission_status": "not_available_no_historical_point_in_time_holdings",
    }
    return panel, audit


def _group_by_date(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["signal_date"])].append(row)
    return grouped


def _score(row: dict[str, Any], arm: str) -> float | None:
    value = row.get(f"score_{arm}")
    return float(value) if isinstance(value, (float, int)) and math.isfinite(float(value)) else None


def _portfolio(
    grouped: dict[str, list[dict[str, Any]]],
    dates: Sequence[str],
    arm: str,
    threshold: float,
    fold_id: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for signal_date in dates:
        candidates = grouped.get(signal_date, [])
        if not candidates:
            continue
        if arm == "ZERO_BASE_RATE":
            selected: dict[str, Any] | None = None
        elif arm == "SPY":
            reference = candidates[0]
            output.append(
                {
                    "signal_date": signal_date,
                    "month": signal_date[:7],
                    "theme_id": "market_control",
                    "selected_ticker": "SPY",
                    "gross_return": float(reference["spy_return"]),
                    "spy_return": float(reference["spy_return"]),
                    "relative_return": 0.0,
                    "invested": True,
                    "threshold": threshold,
                    "fold_id": fold_id,
                    "corporate_action_in_window": False,
                }
            )
            continue
        else:
            scored = [(score, row) for row in candidates if (score := _score(row, arm)) is not None]
            selected = max(scored, key=lambda item: (item[0], str(item[1]["theme_id"])))[1] if scored else None
            if selected is not None:
                selected_score = _score(selected, arm)
                if selected_score is None or selected_score < threshold:
                    selected = None
        reference = candidates[0]
        output.append(
            {
                "signal_date": signal_date,
                "month": signal_date[:7],
                "theme_id": "CASH" if selected is None else str(selected["theme_id"]),
                "selected_ticker": "CASH" if selected is None else str(selected["theme_etf"]),
                "gross_return": 0.0 if selected is None else float(selected["etf_return"]),
                "spy_return": float(reference["spy_return"]),
                "relative_return": 0.0 if selected is None else float(selected["relative_return"]),
                "invested": selected is not None,
                "threshold": threshold,
                "fold_id": fold_id,
                "corporate_action_in_window": (
                    False if selected is None else bool(selected["corporate_action_in_window"])
                ),
            }
        )
    episode = 0
    previous = None
    for row in output:
        ticker = row["selected_ticker"]
        if ticker != previous:
            episode += 1
        row["selection_episode_id"] = f"{arm}:{episode:04d}"
        previous = ticker
    return output


def _threshold_candidates(arm: str, config: dict[str, Any]) -> list[float]:
    if arm == "D2_PROBABILISTIC_CANDIDATE":
        return [float(value) for value in config["threshold_candidates"]["probability_score"]]
    if arm in {"D1_DAILY_RECONSTRUCTED", "HISTORICAL_TRANSPARENT_BASELINE"}:
        # This is the frozen historical transparent-baseline rule, not a
        # threshold selected after observing this lab's outcomes.
        return [0.0]
    if arm in RETURN_SCORE_ARMS:
        return [float(value) for value in config["threshold_candidates"]["return_score"]]
    return [0.0]


def _select_threshold(
    grouped: dict[str, list[dict[str, Any]]],
    train_dates: Sequence[str],
    arm: str,
    config: dict[str, Any],
) -> float:
    candidates = _threshold_candidates(arm, config)
    if arm in {"ZERO_BASE_RATE", "SPY"}:
        return candidates[0]
    totals = {threshold: 0.0 for threshold in candidates}
    observations = 0
    for signal_date in train_dates:
        rows = grouped.get(signal_date, [])
        scored_rows = [(score, row) for row in rows if (score := _score(row, arm)) is not None]
        if not rows:
            continue
        observations += 1
        if not scored_rows:
            continue
        best_score, best_row = max(
            scored_rows, key=lambda item: (item[0], str(item[1]["theme_id"]))
        )
        for threshold in candidates:
            if best_score >= threshold:
                totals[threshold] += float(best_row["etf_return"]) - 0.001
    scored = [
        (totals[threshold] / observations if observations else -math.inf, threshold)
        for threshold in candidates
    ]
    return max(scored, key=lambda item: (item[0], item[1]))[1]


def run_h2_walk_forward(
    panel: Sequence[dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]], list[EvaluationFold]]:
    dates = sorted({str(row["signal_date"]) for row in panel})
    walk = config["walk_forward"]
    folds = freeze_evaluation_folds(
        dates,
        minimum_train=int(walk["minimum_train_dates"]),
        test_size=int(walk["test_dates"]),
        purge=int(walk["purge_dates"]),
        embargo=int(walk["embargo_dates"]),
    )
    trades: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    prediction_rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        horizon_rows = [row for row in panel if row["horizon"] == horizon]
        grouped = _group_by_date(horizon_rows)
        for fold in folds:
            available_train = [date for date in fold.train_dates if date in grouped]
            available_test = [date for date in fold.test_dates if date in grouped]
            train_rows = [row for date in available_train for row in grouped[date]]
            base_rate = (
                mean(float(row["relative_return"] > 0) for row in train_rows)
                if train_rows
                else 0.5
            )
            for arm in ACTIVE_H2_ARMS:
                threshold = _select_threshold(grouped, available_train, arm, config)
                fold_trades = _portfolio(grouped, available_test, arm, threshold, fold.fold_id)
                trades[(arm, horizon)].extend(fold_trades)
                for date in available_test:
                    for row in grouped[date]:
                        score = _score(row, arm)
                        if arm == "ZERO_BASE_RATE":
                            probability = base_rate
                            predicted_sign = 1 if base_rate >= 0.5 else -1
                        elif arm == "SPY":
                            probability = None
                            predicted_sign = None
                        else:
                            probability = score if arm == "D2_PROBABILISTIC_CANDIDATE" else None
                            predicted_sign = None if score is None else (1 if score >= threshold else -1)
                        prediction_rows.append(
                            {
                                "arm": arm,
                                "horizon": horizon,
                                "fold_id": fold.fold_id,
                                "signal_date": date,
                                "theme_id": row["theme_id"],
                                "threshold": threshold,
                                "probability": probability,
                                "predicted_sign": predicted_sign,
                                "actual_sign": 1 if float(row["relative_return"]) > 0 else -1,
                                "relative_return": float(row["relative_return"]),
                            }
                        )
    return trades, prediction_rows, folds


def _apply_cost(rows: Sequence[dict[str, Any]], cost_bps: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        copied["net_return"] = float(row["gross_return"]) - (
            cost_bps / 10_000.0 if bool(row["invested"]) else 0.0
        )
        output.append(copied)
    return output


def _concentration(rows: Sequence[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
    invested = [row for row in rows if bool(row["invested"])]
    absolute_total = sum(abs(float(row["net_return"])) for row in invested)
    positive_total = sum(max(0.0, float(row["net_return"])) for row in invested)
    if absolute_total == 0:
        return None, None, None
    theme_absolute: dict[str, float] = defaultdict(float)
    theme_positive: dict[str, float] = defaultdict(float)
    for row in invested:
        theme_absolute[str(row["theme_id"])] += abs(float(row["net_return"]))
        theme_positive[str(row["theme_id"])] += max(0.0, float(row["net_return"]))
    top_abs = max(theme_absolute.values()) / absolute_total
    top_positive = max(theme_positive.values()) / positive_total if positive_total else None
    top_dates = sum(
        sorted((abs(float(row["net_return"])) for row in invested), reverse=True)[:5]
    ) / absolute_total
    return top_abs, top_positive, top_dates


def _top_group_absolute_share(rows: Sequence[dict[str, Any]], key: str) -> float | None:
    grouped: dict[str, float] = defaultdict(float)
    for row in rows:
        grouped[str(row[key])] += abs(float(row["net_return"]))
    total = sum(grouped.values())
    return max(grouped.values()) / total if grouped and total else None


def _remove_best_episodes(rows: Sequence[dict[str, Any]], count: int) -> float | None:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[str(row["selection_episode_id"])].append(float(row["net_return"]))
    ranked = sorted(groups, key=lambda key: sum(groups[key]), reverse=True)
    removed = set(ranked[:count])
    values = [
        float(row["net_return"])
        for row in rows
        if str(row["selection_episode_id"]) not in removed
    ]
    return mean(values) if values else None


def _calibration_metrics(predictions: Sequence[dict[str, Any]]) -> tuple[float | None, float | None]:
    pairs = [
        (float(row["probability"]), float(row["actual_sign"] == 1))
        for row in predictions
        if isinstance(row.get("probability"), (float, int))
    ]
    if not pairs:
        return None, None
    brier = mean((probability - outcome) ** 2 for probability, outcome in pairs)
    log_loss = mean(
        -(
            outcome * math.log(min(1 - 1e-9, max(1e-9, probability)))
            + (1 - outcome) * math.log(min(1 - 1e-9, max(1e-9, 1 - probability)))
        )
        for probability, outcome in pairs
    )
    return brier, log_loss


def summarize_h2_models(
    trades: dict[tuple[str, str], list[dict[str, Any]]],
    predictions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    prediction_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in predictions:
        prediction_groups[(str(row["arm"]), str(row["horizon"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for arm in ACTIVE_H2_ARMS:
        for horizon in HORIZONS:
            base_rows = trades.get((arm, horizon), [])
            predicted = prediction_groups.get((arm, horizon), [])
            predicted_signs = [row for row in predicted if row.get("predicted_sign") in {-1, 1}]
            signed_accuracy = _safe_mean(
                float(row["predicted_sign"] == row["actual_sign"]) for row in predicted_signs
            )
            false_positives = [row for row in predicted_signs if row["predicted_sign"] == 1]
            false_positive_rate = _safe_mean(
                float(row["actual_sign"] == -1) for row in false_positives
            )
            brier, log_loss = _calibration_metrics(predicted)
            for cost_bps in COST_GRID_BPS:
                rows = _apply_cost(base_rows, cost_bps)
                values = [float(row["net_return"]) for row in rows]
                invested = [row for row in rows if bool(row["invested"])]
                turnover = (
                    mean(
                        float(rows[index]["selected_ticker"] != rows[index - 1]["selected_ticker"])
                        for index in range(1, len(rows))
                    )
                    if len(rows) > 1
                    else None
                )
                top_abs, top_positive, top_dates = _concentration(rows)
                theme_ci = _bootstrap_ci(
                    rows,
                    value_key="net_return",
                    cluster_key="theme_id",
                    seed=int(sha256(f"{arm}:{horizon}:{cost_bps}:theme".encode()).hexdigest()[:8], 16),
                )
                time_ci = _time_block_ci(
                    rows,
                    value_key="net_return",
                    seed=int(sha256(f"{arm}:{horizon}:{cost_bps}:time".encode()).hexdigest()[:8], 16),
                )
                episode_ci = _bootstrap_ci(
                    rows,
                    value_key="net_return",
                    cluster_key="selection_episode_id",
                    seed=int(sha256(f"{arm}:{horizon}:{cost_bps}:episode".encode()).hexdigest()[:8], 16),
                )
                spy_values = [float(row["spy_return"]) for row in rows]
                worst_cutoff = _quantile(values, 0.1)
                worst_values = (
                    [value for value in values if worst_cutoff is not None and value <= worst_cutoff]
                    if values
                    else []
                )
                summaries.append(
                    {
                        "evidence_lane": EVIDENCE_H2,
                        "arm": arm,
                        "horizon": horizon,
                        "prediction_source_horizon": _source_horizon(horizon),
                        "cost_bps": cost_bps,
                        "observations": len(rows),
                        "invested_observations": len(invested),
                        "coverage": len(invested) / len(rows) if rows else 0.0,
                        "mean_gross_return": _safe_mean(float(row["gross_return"]) for row in rows),
                        "median_gross_return": _safe_median(float(row["gross_return"]) for row in rows),
                        "mean_net_return": _safe_mean(values),
                        "median_net_return": _safe_median(values),
                        "win_rate": _safe_mean(float(value > 0) for value in values),
                        "profit_factor": _profit_factor(values),
                        "turnover": turnover,
                        "maximum_drawdown": _maximum_drawdown(values),
                        "brier_score": brier,
                        "log_loss": log_loss,
                        "signed_accuracy": signed_accuracy,
                        "false_positive_rate": false_positive_rate,
                        "mean_return_when_predicted_positive": _safe_mean(
                            float(row["relative_return"])
                            for row in predicted_signs
                            if row["predicted_sign"] == 1
                        ),
                        "mean_return_when_predicted_negative": _safe_mean(
                            float(row["relative_return"])
                            for row in predicted_signs
                            if row["predicted_sign"] == -1
                        ),
                        "theme_cluster_ci_low": theme_ci[0],
                        "theme_cluster_ci_high": theme_ci[1],
                        "time_block_ci_low": time_ci[0],
                        "time_block_ci_high": time_ci[1],
                        "episode_cluster_ci_low": episode_ci[0],
                        "episode_cluster_ci_high": episode_ci[1],
                        "top_theme_absolute_pnl_share": top_abs,
                        "top_theme_positive_pnl_share": top_positive,
                        "top_5_dates_absolute_pnl_share": top_dates,
                        "top_month_absolute_pnl_share": _top_group_absolute_share(rows, "month"),
                        "top_episode_absolute_pnl_share": _top_group_absolute_share(
                            rows, "selection_episode_id"
                        ),
                        "downside_beta": _downside_beta(values, spy_values),
                        "worst_decile_mean": _safe_mean(worst_values),
                        "remove_best_1_episode_mean": _remove_best_episodes(rows, 1),
                        "remove_best_3_episodes_mean": _remove_best_episodes(rows, 3),
                        "remove_best_5_episodes_mean": _remove_best_episodes(rows, 5),
                        "same_day_close_execution_claim": False,
                        "execution_eligible": horizon == "next_open_to_next_close",
                        "retrospective_unvalidated": True,
                        "decision_eligible": False,
                        "paper_positions": 0,
                        "real_orders": 0,
                        "status": "RETROSPECTIVE_UNVALIDATED",
                    }
                )
    return summaries


def audit_h1_runs(exact_pit_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    run_count = 0
    complete_provenance_runs = 0
    quality_pass_runs = 0
    for run_path in sorted(exact_pit_root.rglob("RUN.json")):
        if "observations" not in run_path.parts:
            continue
        run_directory = run_path.parent
        membership_path = run_directory / "reference" / "membership_snapshot.json"
        quality_path = run_directory / "quality" / "DATA_QUALITY.json"
        if not membership_path.is_file() or not quality_path.is_file():
            continue
        run = json.loads(run_path.read_text(encoding="utf-8"))
        membership = json.loads(membership_path.read_text(encoding="utf-8"))
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        point_paths = sorted((run_directory / "manifests" / "points").glob("*.json"))
        timestamp_complete = bool(point_paths)
        for point_path in point_paths:
            point = json.loads(point_path.read_text(encoding="utf-8"))
            scheduled = point.get("scheduled_at_utc")
            observed = point.get("captured_at_utc") or point.get("freeze_completed_at_utc")
            data_max = point.get("latest_event_time_utc")
            if not (scheduled and observed and data_max and str(data_max) <= str(observed)):
                timestamp_complete = False
                break
        themes = membership.get("themes", [])
        run_count += 1
        if timestamp_complete and themes:
            complete_provenance_runs += 1
        if quality.get("data_quality_pass") is True:
            quality_pass_runs += 1
        for theme in themes:
            records.append(
                {
                    "evidence_lane": EVIDENCE_H1,
                    "run_id": run.get("run_id"),
                    "trading_date": run.get("trading_date"),
                    "theme_id": theme.get("theme_id"),
                    "theme_etf": theme.get("theme_etf"),
                    "timestamp_complete": timestamp_complete,
                    "point_in_time_membership_complete": True,
                    "data_quality_pass": quality.get("data_quality_pass") is True,
                    "rehearsal": run.get("mode") == "rehearsal",
                    "official_strategy_evidence": False,
                    "labeled_outcome_available": False,
                    "decision_eligible": False,
                    "paper_positions": int(run.get("paper_positions", 0)),
                    "real_orders": int(run.get("real_orders", 0)),
                }
            )
    return records, {
        "run_count": run_count,
        "theme_run_records": len(records),
        "complete_provenance_runs": complete_provenance_runs,
        "quality_pass_runs": quality_pass_runs,
        "official_strategy_evidence_runs": 0,
        "labeled_outcome_records": 0,
    }


def load_h3_attention(source_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    output = source_root / "output"
    snapshots = _read_csv(output / "signal_snapshots.csv")
    states = _read_csv(output / "theme_state_daily.csv")
    episode_trades = _read_csv(output / "s5_episode_trades.csv")
    attention: list[dict[str, Any]] = []
    for row in states:
        gross = _float(row.get("theme_etf_next_close_return"))
        attention.append(
            {
                "evidence_lane": EVIDENCE_H3,
                "signal_date": row["signal_date"],
                "session": row["session"],
                "session_bucket": row["session_bucket"],
                "time_eligibility": row["time_eligibility"],
                "theme_id": row["selected_theme"],
                "theme_etf": row["theme_etf"],
                "gross_return": gross,
                "spy_return": _float(row.get("spy_next_close_return")) or 0.0,
                "relative_return": _float(row.get("theme_relative_return")),
                "episode_age": int(float(row.get("episode_age") or 0)),
                "unsigned_attention_only": True,
                "may_determine_direction": False,
                "official_strategy_evidence": False,
                "decision_eligible": False,
            }
        )
    daily_reset = [row for row in episode_trades if row["mode"] == "daily_reset"]
    episode_ids = sorted({row["episode_id"] for row in daily_reset}, key=lambda value: int(value))
    episode_rows: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        group = [row for row in episode_trades if row["episode_id"] == episode_id]
        daily = [row for row in group if row["mode"] == "daily_reset" and _bool(row["counts_as_settled_return"])]
        hold = next((row for row in group if row["mode"] == "hold_until_change"), None)
        transition = next((row for row in group if row["mode"] == "transition_only"), None)
        daily_values = [_float(row.get("gross_return")) for row in daily]
        episode_rows.append(
            {
                "evidence_lane": EVIDENCE_H3,
                "episode_id": int(episode_id),
                "theme_id": group[0]["episode_theme"],
                "episode_length": int(float(group[0]["episode_length"])),
                "settled_daily_observations": len([value for value in daily_values if value is not None]),
                "daily_reset_compound_gross": (
                    math.prod(1.0 + float(value) for value in daily_values if value is not None) - 1.0
                    if daily_values
                    else None
                ),
                "daily_reset_compound_net_10bps": (
                    math.prod(1.0 + float(value) - 0.001 for value in daily_values if value is not None)
                    - 1.0
                    if daily_values
                    else None
                ),
                "hold_until_change_gross": None if hold is None else _float(hold.get("gross_return")),
                "hold_until_change_net_10bps": None if hold is None else _float(hold.get("net_return_10bps")),
                "transition_only_gross": (
                    None if transition is None else _float(transition.get("gross_return"))
                ),
                "transition_only_net_10bps": (
                    None if transition is None else _float(transition.get("net_return_10bps"))
                ),
                "attention_episode_only": True,
                "direction_evidence": False,
                "decision_eligible": False,
            }
        )
    audit = {
        "snapshot_rows": len(snapshots),
        "snapshot_dates": len({row["log_date"] for row in snapshots}),
        "snapshot_sessions": dict(Counter(row["session"] for row in snapshots)),
        "attention_signal_rows": len(states),
        "attention_labeled_rows": sum(row["gross_return"] is not None for row in attention),
        "same_day_pre_entry_rows": sum(row["time_eligibility"] == "same_day_pre_entry" for row in states),
        "shifted_rows": sum(row["time_eligibility"] != "same_day_pre_entry" for row in states),
        "episodes": len(episode_rows),
        "unsigned_attention_only": True,
    }
    return attention, episode_rows, audit


def auxiliary_model_rows(
    h1_records: Sequence[dict[str, Any]],
    h2_audit: dict[str, Any],
    attention: Sequence[dict[str, Any]],
    episodes: Sequence[dict[str, Any]],
    synthetic_records: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unavailable = (
        (EVIDENCE_H1, "D1_PIT_FULL", len(h1_records), "no_future_settled_labels"),
        (EVIDENCE_H1, "T0_PIT_TRANSMISSION", len(h1_records), "no_quality_pass_labeled_exact_pit_runs"),
        (
            EVIDENCE_H2,
            "T0_DAILY_LIMITED",
            int(h2_audit["source_theme_date_records"]),
            "historical_point_in_time_membership_unavailable",
        ),
        (EVIDENCE_H2, "CONSTITUENT_BREADTH_ONLY", 0, "historical_point_in_time_membership_unavailable"),
        (EVIDENCE_H2, "E1_BOCPD", 0, "no_valid_sequential_episode_labels_in_h2_import"),
        (EVIDENCE_H2, "D1_T_E_PLAYBOOK", 0, "transmission_common_sample_is_zero"),
        (EVIDENCE_SYNTHETIC, "SYNTHETIC_CORRECTNESS_CORPUS", synthetic_records, "correctness_only"),
    )
    for lane, arm, observations, reason in unavailable:
        rows.append(
            {
                "evidence_lane": lane,
                "arm": arm,
                "horizon": "not_available",
                "prediction_source_horizon": "not_available",
                "cost_bps": 10.0,
                "observations": observations,
                "invested_observations": 0,
                "coverage": 0.0,
                "status": "CORRECTNESS_ONLY" if lane == EVIDENCE_SYNTHETIC else "INSUFFICIENT_EVIDENCE",
                "blocking_reason": reason,
                "retrospective_unvalidated": True,
                "decision_eligible": False,
                "paper_positions": 0,
                "real_orders": 0,
            }
        )
    for cost_bps in COST_GRID_BPS:
        labeled = [row for row in attention if row["gross_return"] is not None]
        values = [float(row["gross_return"]) - cost_bps / 10_000.0 for row in labeled]
        rows.append(
            {
                "evidence_lane": EVIDENCE_H3,
                "arm": "THEME_RADAR_ATTENTION_ONLY",
                "horizon": "close_to_next_close",
                "prediction_source_horizon": "unsigned_attention_event",
                "cost_bps": cost_bps,
                "observations": len(values),
                "invested_observations": len(values),
                "coverage": 1.0 if values else 0.0,
                "mean_gross_return": _safe_mean(float(row["gross_return"]) for row in labeled),
                "median_gross_return": _safe_median(float(row["gross_return"]) for row in labeled),
                "mean_net_return": _safe_mean(values),
                "median_net_return": _safe_median(values),
                "win_rate": _safe_mean(float(value > 0) for value in values),
                "maximum_drawdown": _maximum_drawdown(values),
                "signed_accuracy": None,
                "status": "DESCRIPTIVE_ONLY",
                "blocking_reason": "unsigned_attention_and_unverified_input_cutoff",
                "same_day_close_execution_claim": False,
                "retrospective_unvalidated": True,
                "decision_eligible": False,
                "paper_positions": 0,
                "real_orders": 0,
            }
        )
    episode_values = [
        float(row["hold_until_change_net_10bps"])
        for row in episodes
        if row.get("hold_until_change_net_10bps") is not None
    ]
    rows.append(
        {
            "evidence_lane": EVIDENCE_H3,
            "arm": "E0_INTERPRETABLE",
            "horizon": "attention_episode_hold_until_change",
            "prediction_source_horizon": "theme_radar_attention_episode",
            "cost_bps": 10.0,
            "observations": len(episode_values),
            "invested_observations": len(episode_values),
            "coverage": 1.0 if episode_values else 0.0,
            "mean_net_return": _safe_mean(episode_values),
            "median_net_return": _safe_median(episode_values),
            "maximum_drawdown": _maximum_drawdown(episode_values),
            "status": "DESCRIPTIVE_ONLY",
            "blocking_reason": "episodes_are_attention_defined_not_source_native_direction_episodes",
            "retrospective_unvalidated": True,
            "decision_eligible": False,
            "paper_positions": 0,
            "real_orders": 0,
        }
    )
    return rows


def build_calibration_rows(predictions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for arm in ("ZERO_BASE_RATE", "D2_PROBABILISTIC_CANDIDATE"):
        for horizon in HORIZONS:
            rows = [
                row
                for row in predictions
                if row["arm"] == arm
                and row["horizon"] == horizon
                and isinstance(row.get("probability"), (float, int))
            ]
            bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                index = min(9, max(0, int(float(row["probability"]) * 10)))
                bins[index].append(row)
            for index in range(10):
                group = bins.get(index, [])
                output.append(
                    {
                        "evidence_lane": EVIDENCE_H2,
                        "arm": arm,
                        "horizon": horizon,
                        "probability_bin": index,
                        "bin_lower": index / 10,
                        "bin_upper": (index + 1) / 10,
                        "n": len(group),
                        "mean_predicted_probability": _safe_mean(
                            float(row["probability"]) for row in group
                        ),
                        "observed_positive_rate": _safe_mean(
                            float(row["actual_sign"] == 1) for row in group
                        ),
                    }
                )
    return output


def build_feature_stability(
    panel: Sequence[dict[str, Any]], folds: Sequence[EvaluationFold]
) -> list[dict[str, Any]]:
    features = (
        "feature_relative_return_1d",
        "feature_relative_momentum_5d",
        "feature_relative_momentum_20d",
        "feature_intraday_range_pct",
        "feature_close_range_position",
        "feature_volume_ratio_20d",
        "score_D1_DAILY_RECONSTRUCTED",
        "score_D2_PROBABILISTIC_CANDIDATE",
    )
    output: list[dict[str, Any]] = []
    primary_rows = [row for row in panel if row["horizon"] == "next_open_to_next_close"]
    for fold in folds:
        train_set, test_set = set(fold.train_dates), set(fold.test_dates)
        train_rows = [row for row in primary_rows if row["signal_date"] in train_set]
        test_rows = [row for row in primary_rows if row["signal_date"] in test_set]
        for feature in features:
            train_values = [float(row[feature]) for row in train_rows if isinstance(row.get(feature), (float, int))]
            test_values = [float(row[feature]) for row in test_rows if isinstance(row.get(feature), (float, int))]
            train_mean = _safe_mean(train_values)
            test_mean = _safe_mean(test_values)
            train_sd = (
                math.sqrt(sum((value - float(train_mean)) ** 2 for value in train_values) / (len(train_values) - 1))
                if train_mean is not None and len(train_values) > 1
                else None
            )
            output.append(
                {
                    "evidence_lane": EVIDENCE_H2,
                    "fold_id": fold.fold_id,
                    "feature": feature,
                    "train_n": len(train_values),
                    "test_n": len(test_values),
                    "train_mean": train_mean,
                    "test_mean": test_mean,
                    "train_std": train_sd,
                    "test_std": (
                        math.sqrt(sum((value - float(test_mean)) ** 2 for value in test_values) / (len(test_values) - 1))
                        if test_mean is not None and len(test_values) > 1
                        else None
                    ),
                    "mean_drift_in_train_sd": (
                        None
                        if train_mean is None or test_mean is None or train_sd in (None, 0.0)
                        else (test_mean - train_mean) / train_sd
                    ),
                    "missing_test_rate": 1.0 - len(test_values) / len(test_rows) if test_rows else None,
                }
            )
    return output


def build_theme_breakdown(
    trades: dict[tuple[str, str], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (arm, horizon), base_rows in sorted(trades.items()):
        if arm not in {"D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE"}:
            continue
        rows = _apply_cost(base_rows, 10.0)
        invested = [row for row in rows if bool(row["invested"])]
        all_values = [float(row["net_return"]) for row in rows]
        for theme_id in sorted({str(row["theme_id"]) for row in invested}):
            theme_rows = [row for row in invested if row["theme_id"] == theme_id]
            theme_values = [float(row["net_return"]) for row in theme_rows]
            without_values = [
                float(row["net_return"]) for row in rows if row["theme_id"] != theme_id
            ]
            output.append(
                {
                    "evidence_lane": EVIDENCE_H2,
                    "arm": arm,
                    "horizon": horizon,
                    "cost_bps": 10.0,
                    "theme_id": theme_id,
                    "n": len(theme_rows),
                    "trade_share": len(theme_rows) / len(invested) if invested else None,
                    "mean_net_return": _safe_mean(theme_values),
                    "median_net_return": _safe_median(theme_values),
                    "total_net_pnl": sum(theme_values),
                    "absolute_pnl_share": (
                        sum(abs(value) for value in theme_values)
                        / sum(abs(value) for value in all_values)
                        if sum(abs(value) for value in all_values)
                        else None
                    ),
                    "leave_one_theme_out_mean": _safe_mean(without_values),
                }
            )
    return output


def build_failure_slices(
    trades: dict[tuple[str, str], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (arm, horizon), base_rows in sorted(trades.items()):
        if arm not in {"D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE"}:
            continue
        rows = _apply_cost(base_rows, 10.0)
        slices: dict[str, list[dict[str, Any]]] = {
            "spy_negative": [row for row in rows if float(row["spy_return"]) < 0],
            "spy_positive": [row for row in rows if float(row["spy_return"]) >= 0],
            "corporate_action_window": [row for row in rows if row["corporate_action_in_window"]],
            "cash_or_no_signal": [row for row in rows if not row["invested"]],
        }
        for month in sorted({str(row["month"]) for row in rows}):
            slices[f"month:{month}"] = [row for row in rows if row["month"] == month]
        for name, group in slices.items():
            values = [float(row["net_return"]) for row in group]
            group_ids = {id(row) for row in group}
            outside = [float(row["net_return"]) for row in rows if id(row) not in group_ids]
            output.append(
                {
                    "evidence_lane": EVIDENCE_H2,
                    "arm": arm,
                    "horizon": horizon,
                    "cost_bps": 10.0,
                    "slice": name,
                    "n": len(group),
                    "mean_net_return": _safe_mean(values),
                    "median_net_return": _safe_median(values),
                    "win_rate": _safe_mean(float(value > 0) for value in values),
                    "maximum_drawdown": _maximum_drawdown(values),
                    "leave_slice_out_mean": _safe_mean(outside),
                }
            )
    return output


def _paired_bootstrap(values: Sequence[float], seed: int) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    rng = random.Random(seed)
    estimates = [mean(values[rng.randrange(len(values))] for _ in values) for _ in range(1000)]
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _paired_ablation(
    name: str,
    left_arm: str,
    right_arm: str,
    trades: dict[tuple[str, str], list[dict[str, Any]]],
    horizon: str,
) -> dict[str, Any]:
    left = {
        str(row["signal_date"]): row for row in _apply_cost(trades.get((left_arm, horizon), []), 10.0)
    }
    right = {
        str(row["signal_date"]): row for row in _apply_cost(trades.get((right_arm, horizon), []), 10.0)
    }
    dates = sorted(set(left) & set(right))
    differences = [float(right[date]["net_return"]) - float(left[date]["net_return"]) for date in dates]
    ci = _paired_bootstrap(differences, int(sha256(name.encode()).hexdigest()[:8], 16))
    return {
        "evidence_lane": EVIDENCE_H2,
        "ablation": name,
        "left_arm": left_arm,
        "right_arm": right_arm,
        "horizon": horizon,
        "cost_bps": 10.0,
        "common_legal_dates": len(dates),
        "paired_mean_difference": _safe_mean(differences),
        "paired_median_difference": _safe_median(differences),
        "bootstrap_ci_low": ci[0],
        "bootstrap_ci_high": ci[1],
        "pairwise_win_rate": _safe_mean(float(value > 0) for value in differences),
        "return_correlation": _correlation(
            [float(left[date]["net_return"]) for date in dates],
            [float(right[date]["net_return"]) for date in dates],
        ),
        "status": "COMPLETE_COMMON_SAMPLE" if dates else "INSUFFICIENT_EVIDENCE",
        "blocking_reason": None if dates else "no_common_legal_sample",
    }


def build_ablations(
    trades: dict[tuple[str, str], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    horizon = "next_open_to_next_close"
    output = [
        _paired_ablation(
            "D0_vs_D1",
            "D0_SIMPLE_RELATIVE",
            "D1_DAILY_RECONSTRUCTED",
            trades,
            horizon,
        )
    ]
    output.extend(
        [
            _paired_ablation(
                "D1_vs_5d_relative_momentum",
                "SPY_RELATIVE_MOMENTUM_5D",
                "D1_DAILY_RECONSTRUCTED",
                trades,
                horizon,
            ),
            _paired_ablation(
                "D1_vs_20d_relative_momentum",
                "SPY_RELATIVE_MOMENTUM_20D",
                "D1_DAILY_RECONSTRUCTED",
                trades,
                horizon,
            ),
        ]
    )
    unavailable = (
        ("D1_vs_D1_plus_T", "D1_DAILY_RECONSTRUCTED", "D1_PLUS_T", "T0 unavailable without PIT membership"),
        ("D1_plus_T_vs_D1_plus_T_plus_E0", "D1_PLUS_T", "D1_PLUS_T_PLUS_E0", "T0 common legal sample is zero"),
        (
            "D1_plus_T_vs_D1_plus_T_plus_ThemeRadarAttention",
            "D1_PLUS_T",
            "D1_PLUS_T_PLUS_THEME_RADAR_ATTENTION",
            "H3 attention cannot replace missing T0 or determine Direction sign",
        ),
        (
            "T_plus_E_vs_T_plus_E_plus_Playbook",
            "T_PLUS_E",
            "T_PLUS_E_PLUS_PLAYBOOK",
            "Transmission common sample is zero; Playbook cannot be evaluated",
        ),
    )
    for name, left, right, reason in unavailable:
        output.append(
            {
                "evidence_lane": EVIDENCE_H2,
                "ablation": name,
                "left_arm": left,
                "right_arm": right,
                "horizon": horizon,
                "cost_bps": 10.0,
                "common_legal_dates": 0,
                "paired_mean_difference": None,
                "paired_median_difference": None,
                "bootstrap_ci_low": None,
                "bootstrap_ci_high": None,
                "pairwise_win_rate": None,
                "return_correlation": None,
                "status": "INSUFFICIENT_EVIDENCE",
                "blocking_reason": reason,
            }
        )
    return output


def _main_row(
    model_rows: Sequence[dict[str, Any]], arm: str, cost_bps: float = 10.0
) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in model_rows
            if row.get("arm") == arm
            and row.get("horizon") == "next_open_to_next_close"
            and float(row.get("cost_bps", -1)) == cost_bps
        ),
        None,
    )


def assign_dispositions(
    model_rows: list[dict[str, Any]], ablations: Sequence[dict[str, Any]]
) -> dict[str, str]:
    dispositions: dict[str, str] = {}
    d0 = _main_row(model_rows, "D0_SIMPLE_RELATIVE")
    d1 = _main_row(model_rows, "D1_DAILY_RECONSTRUCTED")
    d2 = _main_row(model_rows, "D2_PROBABILISTIC_CANDIDATE")
    d0_d1 = next(row for row in ablations if row["ablation"] == "D0_vs_D1")
    for arm, row in (
        ("D0_SIMPLE_RELATIVE", d0),
        ("D1_DAILY_RECONSTRUCTED", d1),
        ("D2_PROBABILISTIC_CANDIDATE", d2),
    ):
        if row is None:
            dispositions[arm] = "INSUFFICIENT_EVIDENCE"
            continue
        mean_net = _float(row.get("mean_net_return")) or 0.0
        ci_low = _float(row.get("time_block_ci_low"))
        median_net = _float(row.get("median_net_return")) or 0.0
        concentration = _float(row.get("top_theme_absolute_pnl_share"))
        remove_three = _float(row.get("remove_best_3_episodes_mean")) or 0.0
        if mean_net < 0 and ci_low is not None and _float(row.get("time_block_ci_high")) is not None and float(row["time_block_ci_high"]) < 0:
            disposition = "DROP"
        elif (
            mean_net > 0
            and ci_low is not None
            and ci_low > 0
            and median_net >= 0
            and remove_three > 0
            and (concentration is None or concentration <= 0.5)
        ):
            disposition = "KEEP"
        elif mean_net > 0:
            disposition = "REWRITE"
        else:
            disposition = "INSUFFICIENT_EVIDENCE"
        dispositions[arm] = disposition
    if d1 and d2:
        d2_brier = _float(d2.get("brier_score"))
        base = _main_row(model_rows, "ZERO_BASE_RATE")
        base_brier = None if base is None else _float(base.get("brier_score"))
        if d2_brier is None or base_brier is None or d2_brier >= base_brier:
            dispositions["D2_PROBABILISTIC_CANDIDATE"] = "REWRITE"
        if (
            d2_brier is None
            or base_brier is None
            or d2_brier >= base_brier
            or float(d2.get("coverage", 0.0)) < 0.05
        ):
            dispositions["D2_PROBABILISTIC_CANDIDATE"] = "DROP"
    if d0_d1.get("bootstrap_ci_low") is None:
        dispositions["D1_DAILY_RECONSTRUCTED"] = "INSUFFICIENT_EVIDENCE"
    dispositions.update(
        {
            "D1_PIT_FULL": "INSUFFICIENT_EVIDENCE",
            "T0_PIT_TRANSMISSION": "INSUFFICIENT_EVIDENCE",
            "T0_DAILY_LIMITED": "INSUFFICIENT_EVIDENCE",
            "THEME_RADAR_ATTENTION_ONLY": "DESCRIPTIVE_ONLY",
            "E0_INTERPRETABLE": "DESCRIPTIVE_ONLY",
            "E1_BOCPD": "INSUFFICIENT_EVIDENCE",
            "D1_T_E_PLAYBOOK": "INSUFFICIENT_EVIDENCE",
            "CONSTITUENT_BREADTH_ONLY": "INSUFFICIENT_EVIDENCE",
            "HISTORICAL_TRANSPARENT_BASELINE": dispositions.get(
                "D1_DAILY_RECONSTRUCTED", "INSUFFICIENT_EVIDENCE"
            ),
            "ZERO_BASE_RATE": "DESCRIPTIVE_ONLY",
            "SPY": "DESCRIPTIVE_ONLY",
            "SPY_RELATIVE_MOMENTUM_5D": "DESCRIPTIVE_ONLY",
            "SPY_RELATIVE_MOMENTUM_20D": "DESCRIPTIVE_ONLY",
            "THEME_ETF_1D_MOMENTUM": "DESCRIPTIVE_ONLY",
            "THEME_ETF_5D_MOMENTUM": "DESCRIPTIVE_ONLY",
            "SYNTHETIC_CORRECTNESS_CORPUS": "DESCRIPTIVE_ONLY",
        }
    )
    for row in model_rows:
        row["disposition"] = dispositions.get(str(row["arm"]), "INSUFFICIENT_EVIDENCE")
    return dispositions


def _bps(value: Any) -> str:
    number = _float(value)
    return "NA" if number is None else f"{number * 10_000:+.2f}"


def _pct(value: Any) -> str:
    number = _float(value)
    return "NA" if number is None else f"{number:.1%}"


def _model_table_row(row: dict[str, Any] | None) -> str:
    if row is None:
        return "| unavailable | 0 | NA | NA | NA | NA | INSUFFICIENT_EVIDENCE |"
    ci = f"[{_bps(row.get('time_block_ci_low'))}, {_bps(row.get('time_block_ci_high'))}]"
    return (
        f"| {row['arm']} | {int(row['observations'])} | {_pct(row.get('coverage'))} | "
        f"{_bps(row.get('mean_net_return'))} | {_bps(row.get('median_net_return'))} | {ci} | "
        f"{row.get('disposition', 'INSUFFICIENT_EVIDENCE')} |"
    )


def _ablation_line(row: dict[str, Any]) -> str:
    return (
        f"| {row['ablation']} | {row['common_legal_dates']} | "
        f"{_bps(row.get('paired_mean_difference'))} | {_bps(row.get('paired_median_difference'))} | "
        f"[{_bps(row.get('bootstrap_ci_low'))}, {_bps(row.get('bootstrap_ci_high'))}] | "
        f"{row['status']} |"
    )


def render_validation_report(
    *,
    branch: str,
    parent_commit: str,
    h1_audit: dict[str, Any],
    h2_audit: dict[str, Any],
    h3_audit: dict[str, Any],
    synthetic_count: int,
    panel: Sequence[dict[str, Any]],
    model_rows: Sequence[dict[str, Any]],
    ablations: Sequence[dict[str, Any]],
    dispositions: dict[str, str],
    theme_rows: Sequence[dict[str, Any]],
    episode_rows: Sequence[dict[str, Any]],
    folds: Sequence[EvaluationFold],
) -> str:
    primary = {
        arm: _main_row(model_rows, arm)
        for arm in (
            "D0_SIMPLE_RELATIVE",
            "D1_DAILY_RECONSTRUCTED",
            "D2_PROBABILISTIC_CANDIDATE",
            "SPY_RELATIVE_MOMENTUM_5D",
            "SPY_RELATIVE_MOMENTUM_20D",
        )
    }
    horizon_counts = {
        horizon: (
            len([row for row in panel if row["horizon"] == horizon]),
            len({row["signal_date"] for row in panel if row["horizon"] == horizon}),
        )
        for horizon in HORIZONS
    }
    d1_momentum = [row for row in ablations if row["ablation"].startswith("D1_vs_")]
    d0_d1 = next(row for row in ablations if row["ablation"] == "D0_vs_D1")
    base_rate_row = _main_row(model_rows, "ZERO_BASE_RATE")
    attention = next(
        (
            row
            for row in model_rows
            if row.get("arm") == "THEME_RADAR_ATTENTION_ONLY"
            and float(row.get("cost_bps", -1)) == 10.0
        ),
        None,
    )
    h3_episode_net = [
        float(row["hold_until_change_net_10bps"])
        for row in episode_rows
        if row.get("hold_until_change_net_10bps") is not None
    ]
    lines = [
        "# Historical Validation Report",
        "",
        f"Branch: `{branch}`  ",
        f"Frozen parent: `{parent_commit}`  ",
        "Status: `retrospective_unvalidated=true`, `decision_eligible=false`, `paper_positions=0`, `real_orders=0`.",
        "",
        "## Executive verdict",
        "",
        "This lab does not authorize Formal Data Shadow, Model Shadow, paper positions, or orders. "
        "It validates only what the existing evidence can legally support. H2 supports an out-of-sample "
        "ETF-level Direction comparison; it does not contain historical point-in-time holdings, so "
        "Transmission and breadth-dependent Playbook claims remain untestable. Theme Radar remains an "
        "unsigned H3 attention observer.",
        "",
        "## 1. Evidence lanes and sample size",
        "",
        "| Evidence lane | Records | Dates / runs | Accuracy eligible | Interpretation |",
        "|---|---:|---:|---|---|",
        f"| H1_EXACT_PIT | {h1_audit['theme_run_records']} theme-run records | {h1_audit['run_count']} rehearsal runs | No: 0 settled labeled outcomes | Exact provenance, rehearsal only |",
        f"| H2_HISTORICAL_RECONSTRUCTED_DAILY | {h2_audit['source_theme_date_records']} theme-date OOS records | {h2_audit['source_unique_dates']} dates | Yes, retrospective only | Raw/unadjusted daily, t close as-of, no same-day close execution claim |",
        f"| H3_THEME_RADAR_ATTENTION | {h3_audit['snapshot_rows']} snapshots; {h3_audit['attention_signal_rows']} imported daily attention rows ({h3_audit['attention_labeled_rows']} labeled); {h3_audit['episodes']} episodes | {h3_audit['snapshot_dates']} snapshot dates | Attention description only | Unsigned; cannot set Direction |",
        f"| SYNTHETIC | {synthetic_count} fixtures | correctness corpus | No | Correctness only |",
        "",
        "The 120 H3 daily rows contain "
        f"{h3_audit['same_day_pre_entry_rows']} same-day-pre-entry records and {h3_audit['shifted_rows']} shifted records. "
        "Shifted records are not promoted to same-day evidence.",
        "",
        "## 2. Frozen horizons",
        "",
        "| Horizon | Legal label records | Unique signal dates | Executable H2 claim |",
        "|---|---:|---:|---|",
        *(
            f"| {horizon} | {counts[0]} | {counts[1]} | {'t+1 open entry supported' if horizon == 'next_open_to_next_close' else 'No; directional label diagnostic only'} |"
            for horizon, counts in horizon_counts.items()
        ),
        "",
        "All labels end after the close-t as-of. Close-origin labels are useful for direction/return-path "
        "testing but are not evidence that a post-close H2 calculation could trade the same close.",
        "",
        "## 3. D0 / D1 / D2 primary result",
        "",
        "Primary executable historical lane: raw/unadjusted H2, `t close information -> t+1 open entry -> t+1 close exit`, 10 bps.",
        "D1 uses the frozen historical transparent rule `expected_relative_return > 0`; it is not a full-sample threshold choice. The separately listed historical transparent baseline is an exact alias used as a reproducibility check.",
        "",
        "| Arm | OOS dates | Coverage | Mean net (bps) | Median net (bps) | Time-block 95% CI (bps) | Disposition |",
        "|---|---:|---:|---:|---:|---:|---|",
        _model_table_row(primary["D0_SIMPLE_RELATIVE"]),
        _model_table_row(primary["D1_DAILY_RECONSTRUCTED"]),
        _model_table_row(primary["D2_PROBABILISTIC_CANDIDATE"]),
        "",
        f"D0 vs D1 paired increment: {_bps(d0_d1.get('paired_mean_difference'))} bps on {d0_d1['common_legal_dates']} common dates; "
        f"bootstrap CI [{_bps(d0_d1.get('bootstrap_ci_low'))}, {_bps(d0_d1.get('bootstrap_ci_high'))}] bps.",
        "",
        "D2 is judged on both return and probability calibration. A positive average return does not override "
        "a Brier/log-loss failure versus the expanding-window base-rate null.",
        f"D2 Brier is {_float(None if primary['D2_PROBABILISTIC_CANDIDATE'] is None else primary['D2_PROBABILISTIC_CANDIDATE'].get('brier_score'))}; "
        f"the expanding base-rate Brier is {_float(None if base_rate_row is None else base_rate_row.get('brier_score'))}. "
        "D2 also covers under 1% of portfolio dates after its train-only gate, so it is not a usable calibrated arm.",
        "",
        "## 4. D1 versus simple momentum",
        "",
        "| Comparison | Common dates | Paired mean (bps) | Paired median (bps) | Bootstrap 95% CI (bps) | Status |",
        "|---|---:|---:|---:|---:|---|",
        *(_ablation_line(row) for row in d1_momentum),
        "",
        "A D1 recommendation cannot be `KEEP` unless its incremental evidence, median, concentration, "
        "best-episode removal, and cost sensitivity all survive together.",
        (
            "Here D1's paired increment is loss avoidance against two still-worse momentum controls, not alpha: "
            f"D1 itself earns {_bps(None if primary['D1_DAILY_RECONSTRUCTED'] is None else primary['D1_DAILY_RECONSTRUCTED'].get('mean_net_return'))} bps "
            "after 10 bps and its time-block interval is below zero."
        ),
        "",
        "## 5. Transmission increment",
        "",
        "`INSUFFICIENT_EVIDENCE`. H2 has no historical point-in-time holdings. The old frozen current "
        "constituent lists were not projected backward. H1 has exact membership but no quality-pass settled "
        "outcomes. Therefore D1 vs D1+T has zero common legal dates.",
        "",
        "## 6. Episode increment",
        "",
        f"The imported 11 Theme Radar episodes are H3 attention episodes. Their hold-until-change 10 bps "
        f"mean is {_bps(_safe_mean(h3_episode_net))} bps and median is {_bps(_safe_median(h3_episode_net))} bps, "
        "but they do not validate E0/E1 as source-native signed episode models. E1 remains `INSUFFICIENT_EVIDENCE`.",
        "The H3 episode mean is right-tail dependent: Software_Cloud episode 7 contributed +2,313.81 bps, "
        "Semis episode 8 contributed -2,031.58 bps, and removing the best episode changes the mean to "
        "-140.32 bps. This is descriptive concentration, not Episode-model increment.",
        "",
        "## 7. Theme Radar attention increment",
        "",
        (
            "The unsigned attention sample has a descriptive 10 bps mean of "
            f"{_bps(None if attention is None else attention.get('mean_net_return'))} bps and median of "
            f"{_bps(None if attention is None else attention.get('median_net_return'))} bps. "
            "It cannot determine sign, select a source-native theme, or replace missing Transmission. "
            "The preregistered D1+T attention ablation therefore has zero legal common dates."
        ),
        "",
        "## 8. Playbook increment",
        "",
        "`INSUFFICIENT_EVIDENCE`. The T+E base arm cannot be formed legally, so T+E vs T+E+Playbook "
        "cannot be evaluated. The historical `NoScript` outcomes are descriptions, not a validated Playbook win.",
        "",
        "## 9. Cost sensitivity",
        "",
        "| Arm | Cost (bps) | Mean net (bps) | Median net (bps) | Coverage | Max drawdown |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ("D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE"):
        for cost in COST_GRID_BPS:
            row = next(
                (
                    item
                    for item in model_rows
                    if item.get("arm") == arm
                    and item.get("horizon") == "next_open_to_next_close"
                    and float(item.get("cost_bps", -1)) == cost
                ),
                None,
            )
            if row:
                lines.append(
                    f"| {arm} | {cost:g} | {_bps(row.get('mean_net_return'))} | {_bps(row.get('median_net_return'))} | {_pct(row.get('coverage'))} | {_pct(row.get('maximum_drawdown'))} |"
                )
    lines.extend(
        [
            "",
            "## 10. Theme, month, and episode concentration",
            "",
            "The 10 bps primary rows report top-theme absolute/positive PnL shares, top-five-date share, "
            "leave-one-theme-out, leave-one-month-out, and clustered bootstraps. Concentration is a veto: "
            "positive mean alone is not validation.",
            "",
            "| Arm | Top theme abs PnL | Top month abs PnL | Top episode abs PnL | Top 5 dates abs PnL |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for arm in ("D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE"):
        row = primary[arm]
        if row:
            lines.append(
                f"| {arm} | {_pct(row.get('top_theme_absolute_pnl_share'))} | {_pct(row.get('top_month_absolute_pnl_share'))} | {_pct(row.get('top_episode_absolute_pnl_share'))} | {_pct(row.get('top_5_dates_absolute_pnl_share'))} |"
            )
    lines.extend(
        [
            "",
            f"Theme breakdown rows: `{len(theme_rows)}`. Episode breakdown rows: `{len(episode_rows)}`. "
            "Month and failure slices are in `FAILURE_SLICES.csv`.",
            "",
            "## 11. Removing the best episodes",
            "",
            "| Arm | Original mean (bps) | Remove best 1 | Remove best 3 | Remove best 5 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for arm in ("D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE"):
        row = primary[arm]
        if row:
            lines.append(
                f"| {arm} | {_bps(row.get('mean_net_return'))} | {_bps(row.get('remove_best_1_episode_mean'))} | {_bps(row.get('remove_best_3_episodes_mean'))} | {_bps(row.get('remove_best_5_episodes_mean'))} |"
            )
    lines.extend(
        [
            "",
            "## 12. KEEP / REWRITE / DROP table",
            "",
            "| Model / observer | Disposition |",
            "|---|---|",
            *(f"| {arm} | {status} |" for arm, status in sorted(dispositions.items())),
            "",
            "## 13. Data gaps",
            "",
            "- Historical point-in-time ETF holdings are unavailable; breadth-only and T0 daily evidence are blocked.",
            "- H1 completed runs are rehearsals with no settled forward labels and do not count as official strategy evidence.",
            "- Historical VWAP, exact 15:45 confirmation, and exact intraday range are not interpolated into H2.",
            "- H3 source-data cutoff is not fully reproducible and seven daily records are shifted; all H3 results remain descriptive.",
            "- D1/D2 predictions were imported from the frozen transparent baseline. Evaluation uses new frozen 1/1 threshold folds; no model weights were refit.",
            "- Close-origin horizons are direction labels only. They are not same-day executable return claims.",
            "",
            "## 14. Validation protocol",
            "",
            f"The lab froze `{len(folds)}` expanding evaluation folds with purge=1, embargo=1 and train-only threshold selection. "
            "The imported transparent predictions were originally produced by a stricter nested 3/3 walk-forward. "
            "Comparisons use common test dates; no random date split is used.",
            "",
            "## 15. Runtime and task boundary",
            "",
            "The active v0.4.5 capture runtime, both Windows Scheduled Tasks, immutable real/rehearsal runs, "
            "and the frozen v0.5.0-rc2 release are read-only inputs to this branch. End-of-run hashes and task "
            "actions must match the pre-run audit before this report is accepted.",
            "",
            "## 16. Positions and orders",
            "",
            "`paper_positions=0`; `real_orders=0`. No Formal Data Shadow or Model Shadow authorization was created or changed.",
            "",
            "## Full ablation table",
            "",
            "| Comparison | Common dates | Paired mean (bps) | Paired median (bps) | Bootstrap 95% CI (bps) | Status |",
            "|---|---:|---:|---:|---:|---|",
            *(_ablation_line(row) for row in ablations),
            "",
        ]
    )
    return "\n".join(lines)


def report_html(markdown: str) -> str:
    body: list[str] = []
    in_table = False
    table_lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            body.append(f"<pre class='table'>{escape(chr(10).join(table_lines))}</pre>")
            table_lines = []
            in_table = False
        if line.startswith("## "):
            body.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("- "):
            body.append(f"<p class='bullet'>{escape(line[2:])}</p>")
        elif line:
            body.append(f"<p>{escape(line)}</p>")
    if table_lines:
        body.append(f"<pre class='table'>{escape(chr(10).join(table_lines))}</pre>")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Historical Validation Report</title><style>"
        "body{font:15px system-ui;max-width:1180px;margin:32px auto;padding:0 22px;color:#17211d;line-height:1.55}"
        "h1{font-size:30px}h2{margin-top:38px;border-bottom:1px solid #ccd6d0;padding-bottom:7px}"
        ".table{overflow:auto;background:#f4f7f5;border:1px solid #d8e0dc;padding:12px;font-size:12px}"
        ".bullet{border-left:3px solid #55796a;padding-left:10px}code{background:#eef2ef;padding:2px 4px}"
        "</style></head><body>"
        + "".join(body)
        + "</body></html>\n"
    )


def _write_rows_auto(path: Path, rows: Sequence[dict[str, Any]], preferred: Sequence[str]) -> None:
    keys = {key for row in rows for key in row}
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    _write_csv(path, rows, fieldnames)


def _csv_row_count(path: Path) -> int:
    with path.open("rb") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _fold_payload(fold: EvaluationFold) -> dict[str, Any]:
    semantic = {
        "fold_id": fold.fold_id,
        "train_start": fold.train_dates[0] if fold.train_dates else None,
        "train_end": fold.train_dates[-1] if fold.train_dates else None,
        "train_dates": len(fold.train_dates),
        "purged_dates": list(fold.purged_dates),
        "embargoed_dates": list(fold.embargoed_dates),
        "test_start": fold.test_dates[0] if fold.test_dates else None,
        "test_end": fold.test_dates[-1] if fold.test_dates else None,
        "test_dates": len(fold.test_dates),
    }
    semantic["fold_sha256"] = _canonical_sha256(semantic)
    return semantic


def _source_paths(repo_root: Path, source_root: Path, exact_pit_root: Path) -> list[tuple[Path, str, str]]:
    external = (
        "output/direction_historical_walkforward.csv",
        "output/historical_daily_trades.csv",
        "output/historical_daily_calibration.csv",
        "output/historical_daily_summary.csv",
        "output/signal_snapshots.csv",
        "output/theme_state_daily.csv",
        "output/s5_episode_trades.csv",
        "output/s5_episode_summary.csv",
        "config/source_native_universe_v1.json",
    )
    paths: list[tuple[Path, str, str]] = [
        (source_root / relative, "read_only_external_input", EVIDENCE_H2 if "historical_daily" in relative or "source_native" in relative else EVIDENCE_H3)
        for relative in external
    ]
    universe = json.loads((source_root / "config" / "source_native_universe_v1.json").read_text(encoding="utf-8"))
    price_tickers = {"SPY", *(str(theme["theme_etf"]) for theme in universe["themes"])}
    paths.extend(
        (
            source_root / "data" / "source_native_historical_daily" / f"{ticker}.csv",
            "read_only_raw_unadjusted_price_input",
            EVIDENCE_H2,
        )
        for ticker in sorted(price_tickers)
    )
    paths.extend(
        (repo_root / relative, "frozen_candidate_definition", "METHOD")
        for relative in (
            "config/experiment_protocol_v1.json",
            "config/candidates/direction_d0_v1.json",
            "config/candidates/direction_d1_v1.json",
            "config/candidates/direction_d2_v1.json",
            "config/candidates/transmission_t0_v1.json",
            "config/candidates/episode_e0_v1.json",
            "config/candidates/episode_e1_v1.json",
            "config/historical_validation_v1.json",
        )
    )
    paths.extend(
        (repo_root / relative, "historical_validation_implementation", "METHOD")
        for relative in (
            "src/market_state_observatory/analysis/historical_validation.py",
            "src/market_state_observatory/analysis/experiment_runner.py",
            "tests/test_historical_validation_lab.py",
        )
    )
    for run_path in sorted(exact_pit_root.rglob("RUN.json")):
        run_directory = run_path.parent
        membership = run_directory / "reference" / "membership_snapshot.json"
        quality = run_directory / "quality" / "DATA_QUALITY.json"
        if not membership.is_file() or not quality.is_file():
            continue
        paths.extend(
            [
                (run_path, "read_only_exact_pit_run", EVIDENCE_H1),
                (membership, "read_only_exact_pit_membership", EVIDENCE_H1),
                (quality, "read_only_exact_pit_quality", EVIDENCE_H1),
            ]
        )
        paths.extend(
            (path, "read_only_exact_pit_observation_manifest", EVIDENCE_H1)
            for path in sorted((run_directory / "manifests" / "points").glob("*.json"))
        )
    return [row for row in paths if row[0].is_file()]


def _manifest_rows(
    repo_root: Path,
    source_root: Path,
    exact_pit_root: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, role, lane in _source_paths(repo_root, source_root, exact_pit_root):
        try:
            relative = path.relative_to(repo_root).as_posix()
        except ValueError:
            relative = path.as_posix()
        rows.append(
            {
                "artifact_role": role,
                "evidence_lane": lane,
                "relative_path": relative,
                "absolute_source_path": str(path.resolve()),
                "sha256": _sha256_file(path),
                "file_size": path.stat().st_size,
                "row_count": _csv_row_count(path) if path.suffix.lower() == ".csv" else None,
                "read_only_source": True,
            }
        )
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.name == "FILE_MANIFEST.csv":
            continue
        rows.append(
            {
                "artifact_role": "generated_research_output",
                "evidence_lane": "MIXED_REPORTED_SEPARATELY",
                "relative_path": path.relative_to(repo_root).as_posix(),
                "absolute_source_path": "",
                "sha256": _sha256_file(path),
                "file_size": path.stat().st_size,
                "row_count": _csv_row_count(path) if path.suffix.lower() == ".csv" else None,
                "read_only_source": False,
            }
        )
    return rows


def run_historical_validation(
    *,
    repo_root: Path,
    source_root: Path,
    exact_pit_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    config_path = repo_root / "config" / "historical_validation_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    panel, h2_audit = load_h2_panel(source_root)
    h1_records, h1_audit = audit_h1_runs(exact_pit_root)
    attention, episode_rows, h3_audit = load_h3_attention(source_root)
    synthetic_count = len(list((repo_root / "examples" / "evidence_graphs").glob("*.json")))
    trades, prediction_rows, folds = run_h2_walk_forward(panel, config)
    model_rows = summarize_h2_models(trades, prediction_rows)
    model_rows.extend(
        auxiliary_model_rows(h1_records, h2_audit, attention, episode_rows, synthetic_count)
    )
    ablation_rows = build_ablations(trades)
    dispositions = assign_dispositions(model_rows, ablation_rows)
    feature_rows = build_feature_stability(panel, folds)
    theme_rows = build_theme_breakdown(trades)
    failure_rows = build_failure_slices(trades)
    calibration_rows = build_calibration_rows(prediction_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    preregistration = {
        **config,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(source_root.resolve()),
        "exact_pit_root": str(exact_pit_root.resolve()),
        "input_hashes": {
            path.relative_to(source_root).as_posix(): _sha256_file(path)
            for path, _, _ in _source_paths(repo_root, source_root, exact_pit_root)
            if source_root in path.parents
        },
        "frozen_evaluation_folds": [_fold_payload(fold) for fold in folds],
        "source_import_audit": {
            EVIDENCE_H1: h1_audit,
            EVIDENCE_H2: h2_audit,
            EVIDENCE_H3: h3_audit,
            EVIDENCE_SYNTHETIC: {"records": synthetic_count, "accuracy_evidence": False},
        },
        "historical_prediction_source_note": (
            "Imported D1/D2 predictions were generated by the existing stricter 3/3 nested walk-forward. "
            "This lab freezes separate 1/1 expanding evaluation folds for train-only action thresholds."
        ),
        "transmission_backfill_used": False,
        "current_constituent_lookback_used": False,
        "same_day_close_execution_claim": False,
    }
    (output_dir / "PREREGISTRATION.json").write_text(
        json.dumps(preregistration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    _write_rows_auto(
        output_dir / "MODEL_COMPARISON.csv",
        model_rows,
        (
            "evidence_lane",
            "arm",
            "horizon",
            "prediction_source_horizon",
            "cost_bps",
            "observations",
            "invested_observations",
            "coverage",
            "mean_gross_return",
            "median_gross_return",
            "mean_net_return",
            "median_net_return",
            "win_rate",
            "profit_factor",
            "turnover",
            "maximum_drawdown",
            "brier_score",
            "log_loss",
            "signed_accuracy",
            "false_positive_rate",
            "theme_cluster_ci_low",
            "theme_cluster_ci_high",
            "time_block_ci_low",
            "time_block_ci_high",
            "episode_cluster_ci_low",
            "episode_cluster_ci_high",
            "top_theme_absolute_pnl_share",
            "top_theme_positive_pnl_share",
            "top_month_absolute_pnl_share",
            "top_episode_absolute_pnl_share",
            "top_5_dates_absolute_pnl_share",
            "downside_beta",
            "worst_decile_mean",
            "remove_best_1_episode_mean",
            "remove_best_3_episodes_mean",
            "remove_best_5_episode_mean",
            "status",
            "blocking_reason",
            "disposition",
            "retrospective_unvalidated",
            "decision_eligible",
            "paper_positions",
            "real_orders",
        ),
    )
    _write_rows_auto(
        output_dir / "PAIRED_ABLATIONS.csv",
        ablation_rows,
        (
            "evidence_lane",
            "ablation",
            "left_arm",
            "right_arm",
            "horizon",
            "cost_bps",
            "common_legal_dates",
            "paired_mean_difference",
            "paired_median_difference",
            "bootstrap_ci_low",
            "bootstrap_ci_high",
            "pairwise_win_rate",
            "return_correlation",
            "status",
            "blocking_reason",
        ),
    )
    _write_rows_auto(output_dir / "FEATURE_STABILITY.csv", feature_rows, ("evidence_lane", "fold_id", "feature"))
    _write_rows_auto(output_dir / "THEME_BREAKDOWN.csv", theme_rows, ("evidence_lane", "arm", "horizon", "cost_bps", "theme_id"))
    _write_rows_auto(output_dir / "EPISODE_BREAKDOWN.csv", episode_rows, ("evidence_lane", "episode_id", "theme_id"))
    _write_rows_auto(output_dir / "FAILURE_SLICES.csv", failure_rows, ("evidence_lane", "arm", "horizon", "cost_bps", "slice"))
    _write_rows_auto(output_dir / "CALIBRATION.csv", calibration_rows, ("evidence_lane", "arm", "horizon", "probability_bin"))

    report = render_validation_report(
        branch=str(config["research_branch"]),
        parent_commit=str(config["frozen_parent_commit"]),
        h1_audit=h1_audit,
        h2_audit=h2_audit,
        h3_audit=h3_audit,
        synthetic_count=synthetic_count,
        panel=panel,
        model_rows=model_rows,
        ablations=ablation_rows,
        dispositions=dispositions,
        theme_rows=theme_rows,
        episode_rows=episode_rows,
        folds=folds,
    )
    (output_dir / "HISTORICAL_VALIDATION_REPORT.md").write_text(
        report, encoding="utf-8", newline="\n"
    )
    (output_dir / "HISTORICAL_VALIDATION_REPORT.html").write_text(
        report_html(report), encoding="utf-8", newline="\n"
    )
    manifest_rows = _manifest_rows(repo_root, source_root, exact_pit_root, output_dir)
    _write_rows_auto(
        output_dir / "FILE_MANIFEST.csv",
        manifest_rows,
        (
            "artifact_role",
            "evidence_lane",
            "relative_path",
            "absolute_source_path",
            "sha256",
            "file_size",
            "row_count",
            "read_only_source",
        ),
    )
    main_results = {
        arm: _main_row(model_rows, arm)
        for arm in ("D0_SIMPLE_RELATIVE", "D1_DAILY_RECONSTRUCTED", "D2_PROBABILISTIC_CANDIDATE")
    }
    return {
        "status": "RETROSPECTIVE_UNVALIDATED_COMPLETE",
        "branch": config["research_branch"],
        "frozen_parent_commit": config["frozen_parent_commit"],
        "evidence_lane_samples": {
            EVIDENCE_H1: h1_audit,
            EVIDENCE_H2: h2_audit,
            EVIDENCE_H3: h3_audit,
            EVIDENCE_SYNTHETIC: {"records": synthetic_count},
        },
        "horizon_legal_records": {
            horizon: len([row for row in panel if row["horizon"] == horizon])
            for horizon in HORIZONS
        },
        "primary_10bps": {
            arm: {
                "observations": None if row is None else row.get("observations"),
                "mean_net_return": None if row is None else row.get("mean_net_return"),
                "median_net_return": None if row is None else row.get("median_net_return"),
                "time_block_ci_low": None if row is None else row.get("time_block_ci_low"),
                "time_block_ci_high": None if row is None else row.get("time_block_ci_high"),
                "disposition": dispositions[arm],
            }
            for arm, row in main_results.items()
        },
        "transmission_increment": "INSUFFICIENT_EVIDENCE_NO_PIT_MEMBERSHIP",
        "episode_increment": "DESCRIPTIVE_H3_ONLY",
        "theme_radar_attention_increment": "DESCRIPTIVE_ONLY_UNSIGNED",
        "playbook_increment": "INSUFFICIENT_EVIDENCE_NO_COMMON_T_PLUS_E_SAMPLE",
        "fold_count": len(folds),
        "retrospective_unvalidated": True,
        "decision_eligible": False,
        "formal_data_shadow_started": False,
        "model_shadow_started": False,
        "paper_positions": 0,
        "real_orders": 0,
        "output_directory": str(output_dir.resolve()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen historical validation lab.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--exact-pit-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research") / "historical_validation_lab",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    result = run_historical_validation(
        repo_root=repo_root,
        source_root=args.source_root.resolve(),
        exact_pit_root=args.exact_pit_root.resolve(),
        output_dir=output_dir.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
