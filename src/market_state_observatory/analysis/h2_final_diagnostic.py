from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any


def _float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rank(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    output = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = (cursor + end - 1) / 2.0
        for index in range(cursor, end):
            output[indexed[index][0]] = rank
        cursor = end
    return output


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _correlation(_rank(left), _rank(right))


def _price_index(
    price_root: Path, tickers: Sequence[str]
) -> dict[str, tuple[list[dict[str, Any]], dict[str, int]]]:
    output: dict[str, tuple[list[dict[str, Any]], dict[str, int]]] = {}
    for ticker in tickers:
        with (price_root / f"{ticker}.csv").open(newline="", encoding="utf-8-sig") as handle:
            rows = []
            for row in csv.DictReader(handle):
                opened, closed = _float(row.get("open")), _float(row.get("close"))
                if opened is not None and closed is not None and opened > 0 and closed > 0:
                    rows.append({"date": str(row["date"]), "open": opened, "close": closed})
            output[ticker] = (rows, {str(row["date"]): index for index, row in enumerate(rows)})
    return output


def _five_day_return(
    source: tuple[list[dict[str, Any]], dict[str, int]], signal_date: str
) -> float | None:
    rows, by_date = source
    index = by_date.get(signal_date)
    if index is None or index + 5 >= len(rows):
        return None
    return float(rows[index + 5]["close"]) / float(rows[index + 1]["open"]) - 1.0


def load_panel(
    direction_path: Path, universe_path: Path, price_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    ticker_by_theme = {
        str(row["theme_id"]): str(row["theme_etf"]) for row in universe["themes"]
    }
    prices = _price_index(price_root, sorted(set(ticker_by_theme.values())))
    panel: list[dict[str, Any]] = []
    with direction_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("price_basis") != "raw_unadjusted_main":
                continue
            if row.get("horizon") != "next_open_to_3d_close":
                continue
            theme_id = str(row["theme_id"])
            ticker = ticker_by_theme.get(theme_id)
            score = _float(row.get("relative_momentum_5d"))
            veto = _float(row.get("expected_relative_return"))
            return_3d = _float(row.get("actual_absolute_return"))
            if ticker is None or score is None or veto is None or return_3d is None:
                continue
            return_5d = _five_day_return(prices[ticker], str(row["signal_date"]))
            if return_5d is None:
                continue
            panel.append(
                {
                    "evidence_lane": "H2_HISTORICAL_RECONSTRUCTED_DAILY",
                    "signal_date": str(row["signal_date"]),
                    "theme_id": theme_id,
                    "theme_etf": ticker,
                    "ranking_score": score,
                    "d1_veto_score": veto,
                    "return_next_open_to_3d_close": return_3d,
                    "return_next_open_to_5d_close": return_5d,
                    "outer_fold": str(row["outer_fold"]),
                    "same_day_close_execution_claim": False,
                }
            )
    return panel, {
        "records": len(panel),
        "dates": len({row["signal_date"] for row in panel}),
        "themes": len({row["theme_id"] for row in panel}),
        "raw_unadjusted": True,
        "current_constituent_lookback": False,
    }


def build_daily_diagnostics(
    panel: Sequence[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in panel:
        grouped[str(row["signal_date"])].append(row)
    output: list[dict[str, Any]] = []
    positive_veto = float(config["d1_positive_veto_threshold"])
    negative_veto = float(config["d1_negative_veto_threshold"])
    for signal_date, rows in sorted(grouped.items()):
        ranked = sorted(rows, key=lambda row: (float(row["ranking_score"]), str(row["theme_id"])))
        if len(ranked) < 4:
            continue
        for horizon in config["horizons"]:
            return_key = "return_" + str(horizon)
            scores = [float(row["ranking_score"]) for row in ranked]
            realized = [float(row[return_key]) for row in ranked]
            spearman = _spearman(scores, realized)
            sizes = {
                "top1_bottom1": 1,
                "top2_bottom2": min(2, len(ranked) // 2),
                "top_half_bottom_half": len(ranked) // 2,
            }
            for portfolio, size in sizes.items():
                top = [row for row in ranked[-size:] if float(row["d1_veto_score"]) > positive_veto]
                bottom = [row for row in ranked[:size] if float(row["d1_veto_score"]) < negative_veto]
                positive_leg = mean(float(row[return_key]) for row in top) if top else 0.0
                negative_leg = mean(-float(row[return_key]) for row in bottom) if bottom else 0.0
                output.append(
                    {
                        "evidence_lane": "H2_HISTORICAL_RECONSTRUCTED_DAILY",
                        "signal_date": signal_date,
                        "horizon": horizon,
                        "portfolio": portfolio,
                        "theme_count": len(ranked),
                        "positive_leg_count": len(top),
                        "negative_leg_count": len(bottom),
                        "positive_leg_return": positive_leg,
                        "negative_leg_return": negative_leg,
                        "long_short_spread": positive_leg + negative_leg,
                        "cross_sectional_spearman": spearman,
                        "top_themes": "|".join(str(row["theme_id"]) for row in top),
                        "bottom_themes": "|".join(str(row["theme_id"]) for row in bottom),
                        "d1_role": "veto_only_not_standalone_signal",
                    }
                )
    return output


def _bootstrap(values_by_date: dict[str, float], seed: int) -> tuple[float | None, float | None]:
    keys = sorted(values_by_date)
    if len(keys) < 2:
        return None, None
    rng = random.Random(seed)
    values = [values_by_date[key] for key in keys]
    samples = [
        sum(rng.choices(values, k=len(values))) / len(values)
        for _ in range(300)
    ]
    samples.sort()
    return samples[7], samples[292]


def summarize(
    daily: Sequence[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        grouped[(str(row["horizon"]), str(row["portfolio"]))].append(row)
    output: list[dict[str, Any]] = []
    for (horizon, portfolio), rows in sorted(grouped.items()):
        for cost in config["cost_grid_bps"]:
            cost_value = float(cost) / 10_000.0
            net_spread = [
                float(row["long_short_spread"])
                - cost_value * (int(row["positive_leg_count"] > 0) + int(row["negative_leg_count"] > 0))
                for row in rows
            ]
            by_date = {
                str(row["signal_date"]): value
                for row, value in zip(rows, net_spread, strict=True)
            }
            ci_low, ci_high = _bootstrap(
                by_date, int(sha256(f"{horizon}:{portfolio}:{cost}".encode()).hexdigest()[:8], 16)
            )
            output.append(
                {
                    "evidence_lane": "H2_HISTORICAL_RECONSTRUCTED_DAILY",
                    "horizon": horizon,
                    "portfolio": portfolio,
                    "cost_bps_per_active_leg": cost,
                    "dates": len(rows),
                    "positive_leg_coverage": mean(float(row["positive_leg_count"] > 0) for row in rows),
                    "negative_leg_coverage": mean(float(row["negative_leg_count"] > 0) for row in rows),
                    "mean_positive_leg_return": mean(float(row["positive_leg_return"]) for row in rows),
                    "mean_negative_leg_return": mean(float(row["negative_leg_return"]) for row in rows),
                    "mean_net_long_short_spread": mean(net_spread),
                    "median_net_long_short_spread": median(net_spread),
                    "bootstrap_ci_low": ci_low,
                    "bootstrap_ci_high": ci_high,
                    "mean_cross_sectional_spearman": mean(
                        float(row["cross_sectional_spearman"])
                        for row in rows
                        if row["cross_sectional_spearman"] is not None
                    ),
                    "H2_MODEL_MINING_CLOSED": True,
                    "decision_eligible": False,
                    "paper_positions": 0,
                    "real_orders": 0,
                }
            )
    return output


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_h2_final_diagnostic(
    *,
    direction_path: Path,
    universe_path: Path,
    price_root: Path,
    config_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    panel, audit = load_panel(direction_path, universe_path, price_root)
    daily = build_daily_diagnostics(panel, config)
    summary = summarize(daily, config)
    output_directory.mkdir(parents=True, exist_ok=True)
    _write_csv(output_directory / "H2_FINAL_DIAGNOSTIC_DAILY.csv", daily)
    _write_csv(output_directory / "H2_FINAL_DIAGNOSTIC_SUMMARY.csv", summary)
    primary = [
        row
        for row in summary
        if row["portfolio"] == "top1_bottom1" and float(row["cost_bps_per_active_leg"]) == 10.0
    ]
    robust = bool(primary) and all(
        float(row["mean_net_long_short_spread"]) > 0
        and row["bootstrap_ci_low"] is not None
        and float(row["bootstrap_ci_low"]) > 0
        for row in primary
    )
    report = {
        "schema_version": "mso-h2-final-diagnostic-report-v1",
        "status": "COMPLETE",
        "input_audit": audit,
        "primary_10bps_top1_bottom1": primary,
        "clear_robust_after_cost_cross_theme_result": robust,
        "interpretation": (
            "Mechanically robust diagnostic; remains H2 retrospective and cannot reactivate retired models."
            if robust
            else "No clear robust after-cost cross-theme result. H2 model mining is closed."
        ),
        "d1_role": "veto_only_not_standalone_signal",
        "H2_MODEL_MINING_CLOSED": True,
        "retrospective_unvalidated": True,
        "decision_eligible": False,
        "paper_positions": 0,
        "real_orders": 0,
    }
    (output_directory / "H2_FINAL_DIAGNOSTIC.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# Final H2 Diagnostic",
        "",
        "Evidence lane: `H2_HISTORICAL_RECONSTRUCTED_DAILY`. D1 is used only as a frozen zero-threshold veto on a 5-day relative-momentum ranking; it is not traded as a standalone signal.",
        "",
        f"Panel: {audit['records']} theme-date rows, {audit['dates']} dates, {audit['themes']} themes. Raw/unadjusted ETF data only; no constituent lookback.",
        "",
        "| Horizon | Dates | Mean 10 bps/leg spread | Median | Bootstrap 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in primary:
        lines.append(
            f"| {row['horizon']} | {row['dates']} | {float(row['mean_net_long_short_spread']) * 10000:+.2f} bps | {float(row['median_net_long_short_spread']) * 10000:+.2f} bps | [{float(row['bootstrap_ci_low']) * 10000:+.2f}, {float(row['bootstrap_ci_high']) * 10000:+.2f}] bps |"
        )
    lines.extend(
        [
            "",
            f"Conclusion: {report['interpretation']}",
            "",
            "`H2_MODEL_MINING_CLOSED=true`; `decision_eligible=false`; `paper_positions=0`; `real_orders=0`.",
        ]
    )
    (output_directory / "H2_FINAL_DIAGNOSTIC.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen final H2 ranking diagnostic")
    parser.add_argument("--direction", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--price-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_h2_final_diagnostic(
        direction_path=args.direction.resolve(),
        universe_path=args.universe.resolve(),
        price_root=args.price_root.resolve(),
        config_path=args.config.resolve(),
        output_directory=args.output.resolve(),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
