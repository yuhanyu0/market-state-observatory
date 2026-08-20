from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any

ARMS = ("D0", "D1", "D2", "D1+T", "D1+T+E0", "D1+T+E1", "D1+T+E+P")


@dataclass(frozen=True)
class ReplayRecord:
    as_of_utc: str
    target_time_utc: str
    theme_id: str
    episode_id: str | None
    probability_positive: float | None
    predicted_sign: int | None
    realized_return: float
    cost_bps: float
    selected_ticker: str | None = None
    benchmark_return: float | None = None


def _maximum_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = peak = 1.0
    maximum = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        maximum = min(maximum, equity / peak - 1.0)
    return maximum


def _calibration_curve(pairs: list[tuple[float, float]]) -> list[dict[str, float | int | None]]:
    bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for probability, outcome in pairs:
        bins[min(9, max(0, int(probability * 10)))].append((probability, outcome))
    return [
        {
            "bin": index,
            "lower": index / 10,
            "upper": (index + 1) / 10,
            "observations": len(group),
            "mean_probability": mean(item[0] for item in group) if group else None,
            "observed_positive_rate": mean(item[1] for item in group) if group else None,
        }
        for index in range(10)
        if (group := bins.get(index, []))
    ]


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    )
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )
    return numerator / denominator if denominator else None


def frozen_walk_forward_folds(
    timestamps: Iterable[str],
    *,
    minimum_train: int = 20,
    test_size: int = 10,
    purge: int = 1,
    embargo: int = 1,
) -> list[dict[str, Any]]:
    rows = sorted(set(timestamps))
    folds: list[dict[str, Any]] = []
    start = minimum_train
    while start + test_size <= len(rows):
        train_end = max(0, start - purge)
        test_start = min(len(rows), start + embargo)
        test_end = min(len(rows), test_start + test_size)
        if train_end and test_start < test_end:
            folds.append(
                {
                    "fold_id": f"wf-{len(folds) + 1:03d}",
                    "train": rows[:train_end],
                    "purged": rows[train_end:start],
                    "embargoed": rows[start:test_start],
                    "test": rows[test_start:test_end],
                }
            )
        start = test_end
    return folds


def register_experiment(
    arm: str,
    timestamps: Iterable[str],
    *,
    registered_at_utc: str,
) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError(f"Unsupported experiment arm: {arm}")
    folds = frozen_walk_forward_folds(timestamps)
    semantic = {
        "arm": arm,
        "registered_at_utc": registered_at_utc,
        "strict_as_of": True,
        "frozen_folds": folds,
        "rehearsal_is_official_evidence": False,
    }
    digest = sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "mso-experiment-registration-v1",
        "experiment_id": f"{arm.lower().replace('+', '-')}-{digest[:12]}",
        **semantic,
        "manifest_sha256": digest,
        "status": "REPLAY_ONLY",
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }


def _cluster_bootstrap(
    records: list[ReplayRecord],
    cluster: str,
    *,
    iterations: int,
    seed: int,
) -> dict[str, float | None]:
    grouped: dict[str, list[ReplayRecord]] = defaultdict(list)
    for row in records:
        key = row.theme_id if cluster == "theme" else (row.episode_id or row.as_of_utc[:10])
        grouped[key].append(row)
    keys = sorted(grouped)
    if not keys:
        return {"mean": None, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iterations):
        selected = [grouped[rng.choice(keys)] for _ in keys]
        values = [row.realized_return - row.cost_bps / 10_000 for group in selected for row in group]
        samples.append(mean(values))
    samples.sort()
    return {
        "mean": mean(samples),
        "ci_low": samples[int(0.025 * (len(samples) - 1))],
        "ci_high": samples[int(0.975 * (len(samples) - 1))],
    }


def run_registered_replay(
    registration: dict[str, Any],
    records: Iterable[ReplayRecord],
) -> dict[str, Any]:
    rows = sorted(records, key=lambda row: row.as_of_utc)
    for row in rows:
        if datetime.fromisoformat(row.target_time_utc) <= datetime.fromisoformat(row.as_of_utc):
            raise ValueError("strict as-of replay rejected a non-future target")
    predicted = [row for row in rows if row.predicted_sign in {-1, 1}]
    probabilities = [
        (float(row.probability_positive), float(row.realized_return > 0))
        for row in rows
        if row.probability_positive is not None
    ]
    net = [row.realized_return - row.cost_bps / 10_000 for row in rows]
    brier = mean((probability - outcome) ** 2 for probability, outcome in probabilities) if probabilities else None
    log_loss = mean(
        -(
            outcome * math.log(min(1 - 1e-9, max(1e-9, probability)))
            + (1 - outcome) * math.log(min(1 - 1e-9, max(1e-9, 1 - probability)))
        )
        for probability, outcome in probabilities
    ) if probabilities else None
    signed_accuracy = mean(float(row.predicted_sign == (1 if row.realized_return > 0 else -1)) for row in predicted) if predicted else None
    states = [row.selected_ticker or str(row.predicted_sign) for row in rows]
    turnover = (
        mean(float(states[index] != states[index - 1]) for index in range(1, len(states)))
        if len(states) > 1
        else None
    )
    theme_absolute: dict[str, float] = defaultdict(float)
    for row, value in zip(rows, net, strict=True):
        theme_absolute[row.theme_id] += abs(value)
    total_absolute = sum(theme_absolute.values())
    concentration = {
        "top_theme_absolute_pnl_share": (
            max(theme_absolute.values()) / total_absolute if total_absolute else None
        ),
        "top_observation_absolute_pnl_share": (
            max((abs(value) for value in net), default=0.0) / total_absolute
            if total_absolute
            else None
        ),
    }
    conditional_return = {
        "predicted_positive": (
            mean(row.realized_return for row in predicted if row.predicted_sign == 1)
            if any(row.predicted_sign == 1 for row in predicted)
            else None
        ),
        "predicted_negative": (
            mean(row.realized_return for row in predicted if row.predicted_sign == -1)
            if any(row.predicted_sign == -1 for row in predicted)
            else None
        ),
    }
    paired = [
        (row.realized_return - row.cost_bps / 10_000, row.benchmark_return)
        for row in rows
        if row.benchmark_return is not None
    ]
    differences = [value - float(benchmark) for value, benchmark in paired]
    ablation = (
        {
            "status": "complete_same_record_pairing",
            "observations": len(differences),
            "paired_mean_difference": mean(differences),
            "paired_median_difference": median(differences),
            "pairwise_win_rate": mean(float(value > 0) for value in differences),
            "return_correlation": _correlation(
                [value for value, _ in paired],
                [float(benchmark) for _, benchmark in paired],
            ),
        }
        if differences
        else {"status": "not_available_no_paired_benchmark", "observations": 0}
    )
    failure_slices: list[dict[str, Any]] = []
    for theme in sorted({row.theme_id for row in rows}):
        values = [
            row.realized_return - row.cost_bps / 10_000
            for row in rows
            if row.theme_id == theme
        ]
        failure_slices.append(
            {
                "slice": f"theme:{theme}",
                "observations": len(values),
                "mean_net_return": mean(values),
                "median_net_return": median(values),
                "maximum_drawdown": _maximum_drawdown(values),
            }
        )
    for month in sorted({row.as_of_utc[:7] for row in rows}):
        values = [
            row.realized_return - row.cost_bps / 10_000
            for row in rows
            if row.as_of_utc.startswith(month)
        ]
        failure_slices.append(
            {
                "slice": f"month:{month}",
                "observations": len(values),
                "mean_net_return": mean(values),
                "median_net_return": median(values),
                "maximum_drawdown": _maximum_drawdown(values),
            }
        )
    seed = int(str(registration["manifest_sha256"])[:8], 16)
    metrics = {
        "observations": len(rows),
        "coverage": len(predicted) / len(rows) if rows else 0.0,
        "mean_net_return": mean(net) if net else None,
        "brier_score": brier,
        "log_loss": log_loss,
        "signed_accuracy": signed_accuracy,
        "turnover": turnover,
        "maximum_drawdown": _maximum_drawdown(net),
        "theme_clustered_bootstrap": _cluster_bootstrap(rows, "theme", iterations=1000, seed=seed),
        "time_block_bootstrap": _cluster_bootstrap(rows, "time", iterations=1000, seed=seed + 1),
        "episode_clustered_bootstrap": _cluster_bootstrap(rows, "episode", iterations=1000, seed=seed + 2),
        "theme_fixed_effects": {theme: mean([row.realized_return for row in rows if row.theme_id == theme]) for theme in sorted({row.theme_id for row in rows})},
        "calibration_curve": _calibration_curve(probabilities),
        "conditional_return": conditional_return,
        "cost_grid_bps": [0, 5, 10, 15, 25, 50],
        "concentration": concentration,
        "ablation": ablation,
    }
    return {
        "schema_version": "mso-experiment-result-v1",
        "experiment_id": registration["experiment_id"],
        "arm": registration["arm"],
        "manifest_sha256": registration["manifest_sha256"],
        "evidence_grade": "retrospective_unvalidated",
        "metrics": metrics,
        "failure_slices": failure_slices,
        "validated_model": False,
        "decision_eligible": False,
        "paper_positions": 0,
        "real_orders": 0,
    }


def write_default_registry(path: Path, *, registered_at_utc: str | None = None) -> list[dict[str, Any]]:
    timestamp = registered_at_utc or datetime.now(UTC).isoformat()
    registrations = [register_experiment(arm, (), registered_at_utc=timestamp) for arm in ARMS]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registrations, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registrations
