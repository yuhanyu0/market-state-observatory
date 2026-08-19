from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from statistics import median, pstdev
from typing import Any

FEATURE_SET_VERSION = "observation-features-v1"
POINT_ORDER = (
    "open_snapshot",
    "next_10_00",
    "midpoint_snapshot",
    "preclose_snapshot",
    "decision_snapshot",
    "session_close_diagnostic",
)
FEATURE_IDS = (
    "relative_to_spy_return",
    "relative_to_industry_return",
    "etf_intraday_return",
    "basket_mean_return",
    "basket_median_return",
    "constituent_positive_breadth",
    "constituent_negative_breadth",
    "residual_breadth",
    "volume_breadth",
    "single_name_concentration",
    "leader_rest_gap",
    "etf_basket_agreement",
    "return_dispersion",
    "vwap_distance",
    "range_position",
    "preclose_decision_confirmation",
    "decision_close_confirmation",
    "spread_percent",
    "quote_freshness",
    "trade_freshness",
    "event_time_dispersion",
    "freeze_duration",
    "primary_feed_gap",
    "rest_reconciliation_summary",
)


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return sum(rows) / len(rows)


def _source_price(row: dict[str, Any] | None) -> float | None:
    if not row or row.get("observation_status") != "CAPTURED":
        return None
    trade = row.get("last_trade", {})
    if trade.get("status") == "READY" and trade.get("price") is not None:
        return float(trade["price"])
    quote = row.get("quote", {})
    if quote.get("status") in {"READY", "STALE"} and quote.get("mid") is not None:
        return float(quote["mid"])
    return None


def _quote_age(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    value = row.get("quote", {}).get("freshness_age_seconds")
    return float(value) if value is not None else None


def _trade_age(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    value = row.get("last_trade", {}).get("freshness_age_seconds")
    return float(value) if value is not None else None


@dataclass(frozen=True)
class FeatureSource:
    refs: tuple[str, ...]
    hashes: tuple[str, ...]
    event_time_utc: str
    observed_at_utc: str
    data_max_timestamp: str


class CompletedRunFeatureCompiler:
    def __init__(self, run_directory: Path):
        self.run_directory = run_directory
        self.run = self._load("RUN.json")
        self.quality = self._load("quality/DATA_QUALITY.json")
        self.membership = self._load("reference/membership_snapshot.json")
        self.points = {
            payload["observation_point"]: payload
            for payload in (
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_directory / "manifests" / "points").glob("*.json"))
            )
        }
        self.rows = {
            point: {str(row["symbol"]): row for row in payload.get("symbols", [])}
            for point, payload in self.points.items()
        }

    def _load(self, relative: str) -> dict[str, Any]:
        path = self.run_directory / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object: {relative}")
        return payload

    def _source(self, *points: str) -> FeatureSource:
        available = [point for point in dict.fromkeys(points) if point in self.points]
        payloads = [self.points[point] for point in available]
        refs = tuple(f"manifests/points/{point}.json" for point in available)
        hashes = tuple(
            str(payload.get("snapshot_bundle_sha256") or file_sha256(self.run_directory / ref))
            for payload, ref in zip(payloads, refs, strict=True)
        )
        event_times = [str(payload.get("latest_event_time_utc") or payload["scheduled_at_utc"]) for payload in payloads]
        observed = [str(payload.get("captured_at_utc") or payload["freeze_completed_at_utc"]) for payload in payloads]
        if not payloads:
            fallback = str(self.run.get("created_at_utc"))
            return FeatureSource((), (), fallback, fallback, fallback)
        if any(_parse(event) > _parse(seen) for event in event_times for seen in [max(observed, key=_parse)]):
            raise ValueError("future data rejected: source event time exceeds observation time")
        return FeatureSource(
            refs,
            hashes,
            max(event_times, key=_parse),
            max(observed, key=_parse),
            max(event_times, key=_parse),
        )

    def _feature(
        self,
        feature_id: str,
        theme_id: str,
        symbol_scope: str,
        point: str,
        source: FeatureSource,
        value: Any,
        units: str,
        *,
        status: str = "AVAILABLE",
        reason: str | None = None,
    ) -> dict[str, Any]:
        semantic = {
            "feature_id": feature_id,
            "feature_set_version": FEATURE_SET_VERSION,
            "theme_id": theme_id,
            "symbol_scope": symbol_scope,
            "observation_point": point,
            "event_time_utc": source.event_time_utc,
            "observed_at_utc": source.observed_at_utc,
            "data_max_timestamp": source.data_max_timestamp,
            "availability_status": status,
            "not_applicable_reason": reason,
            "value": value,
            "units": units,
            "source_snapshot_refs": list(source.refs),
            "source_snapshot_sha256": list(source.hashes),
        }
        semantic["calculation_sha256"] = sha256(canonical_json(semantic)).hexdigest()
        return semantic

    def _not_available(
        self,
        feature_id: str,
        theme_id: str,
        scope: str,
        point: str,
        source: FeatureSource,
        units: str,
        reason: str,
        *,
        not_applicable: bool = False,
    ) -> dict[str, Any]:
        return self._feature(
            feature_id,
            theme_id,
            scope,
            point,
            source,
            None,
            units,
            status="NOT_APPLICABLE" if not_applicable else "NOT_AVAILABLE",
            reason=reason,
        )

    def compile(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        features: list[dict[str, Any]] = []
        for theme in self.membership["themes"]:
            theme_id = str(theme["theme_id"])
            etf = str(theme["theme_etf"])
            industry = str(theme["industry_benchmark"])
            basket = tuple(map(str, theme["basket"]))
            for point in POINT_ORDER:
                if point not in self.points:
                    source = self._source()
                    for feature_id in FEATURE_IDS:
                        features.append(self._not_available(feature_id, theme_id, "theme", point, source, "unknown", "observation_point_missing"))
                    continue
                features.extend(self._compile_theme_point(theme_id, etf, industry, basket, point))

        features.sort(key=lambda row: (row["theme_id"], POINT_ORDER.index(row["observation_point"]), row["feature_id"]))
        artifact = {
            "schema_version": "mso-observation-features-v1",
            "run_id": self.run["run_id"],
            "feature_set_version": FEATURE_SET_VERSION,
            "evidence_grade": "completed_run_point_in_time",
            "features": features,
        }
        source_paths = [
            "RUN.json",
            "quality/DATA_QUALITY.json",
            "reference/membership_snapshot.json",
            *(f"manifests/points/{point}.json" for point in sorted(self.points)),
        ]
        provenance = {
            "schema_version": "mso-feature-provenance-v1",
            "run_id": self.run["run_id"],
            "feature_set_version": FEATURE_SET_VERSION,
            "compiler": "market_state_observatory.analysis.feature_compiler.CompletedRunFeatureCompiler",
            "compiler_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_artifacts": [
                {"relative_path": rel, "sha256": file_sha256(self.run_directory / rel)}
                for rel in source_paths
            ],
            "original_run_mutated": False,
        }
        statuses = Counter(str(row["availability_status"]) for row in features)
        decision = self.points.get("decision_snapshot", {})
        decision_rows = decision.get("symbols", [])
        observed_ages = [age for row in decision_rows if (age := _quote_age(row)) is not None]
        ready_ages = [
            age
            for row in decision_rows
            if row.get("quote", {}).get("status") == "READY" and (age := _quote_age(row)) is not None
        ]
        quality = {
            "schema_version": "mso-feature-quality-v1",
            "run_id": self.run["run_id"],
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_count": len(features),
            "availability_counts": dict(sorted(statuses.items())),
            "open_not_yet_defined_excluded_from_readiness": True,
            "decision_primary_quote_count": len(decision_rows),
            "decision_stale_quote_count": sum(row.get("quote", {}).get("status") == "STALE" for row in decision_rows),
            "observed_quote_age_max": max(observed_ages) if observed_ages else None,
            "ready_quote_age_max": max(ready_ages) if ready_ages else None,
            "future_timestamp_count": int(self.quality.get("future_timestamp_count", 0)),
            "backfill_count": int(self.quality.get("backfill_count", 0)),
            "paper_positions": 0,
            "real_orders": 0,
        }
        return artifact, provenance, quality

    def _compile_theme_point(
        self,
        theme_id: str,
        etf: str,
        industry: str,
        basket: tuple[str, ...],
        point: str,
    ) -> list[dict[str, Any]]:
        source = self._source("open_snapshot", point)
        current = self.rows[point]
        opened = self.rows.get("open_snapshot", {})
        etf_price = _source_price(current.get(etf))
        etf_open = _source_price(opened.get(etf))
        spy_price = _source_price(current.get("SPY"))
        spy_open = _source_price(opened.get("SPY"))
        industry_price = _source_price(current.get(industry))
        industry_open = _source_price(opened.get(industry))

        def change(price: float | None, base: float | None) -> float | None:
            return price / base - 1.0 if price is not None and base not in (None, 0.0) else None

        etf_return = change(etf_price, etf_open)
        spy_return = change(spy_price, spy_open)
        industry_return = change(industry_price, industry_open)
        basket_returns = [
            (symbol, value)
            for symbol in basket
            if (value := change(_source_price(current.get(symbol)), _source_price(opened.get(symbol)))) is not None
        ]
        values = [value for _, value in basket_returns]
        scope = f"{etf}+basket"
        out: list[dict[str, Any]] = []

        def number(feature_id: str, value: float | None, units: str = "decimal_return", reason: str = "required_price_missing") -> None:
            if value is None or not math.isfinite(value):
                out.append(self._not_available(feature_id, theme_id, scope, point, source, units, reason))
            else:
                out.append(self._feature(feature_id, theme_id, scope, point, source, value, units))

        number("etf_intraday_return", etf_return)
        number("relative_to_spy_return", None if etf_return is None or spy_return is None else etf_return - spy_return)
        number("relative_to_industry_return", None if etf_return is None or industry_return is None else etf_return - industry_return)
        number("basket_mean_return", _mean(values) if values else None)
        number("basket_median_return", median(values) if values else None)
        number("constituent_positive_breadth", sum(value > 0 for value in values) / len(values) if values else None, "proportion")
        number("constituent_negative_breadth", sum(value < 0 for value in values) / len(values) if values else None, "proportion")
        number("residual_breadth", sum(value > (spy_return or 0.0) for value in values) / len(values) if values and spy_return is not None else None, "proportion")

        minute_volumes = [
            float(current[symbol]["minute_bar"]["volume"])
            for symbol in basket
            if symbol in current and current[symbol].get("minute_bar", {}).get("status") == "READY"
        ]
        if point == "open_snapshot" and not minute_volumes:
            out.append(self._not_available("volume_breadth", theme_id, scope, point, source, "proportion", "open_minute_bar_not_yet_defined", not_applicable=True))
        else:
            number("volume_breadth", sum(volume > 0 for volume in minute_volumes) / len(basket) if minute_volumes else None, "proportion", "minute_volume_missing")

        abs_total = sum(abs(value) for value in values)
        number("single_name_concentration", max((abs(value) for value in values), default=0.0) / abs_total if abs_total else 0.0, "proportion")
        ordered = sorted(values, reverse=True)
        number("leader_rest_gap", ordered[0] - _mean(ordered[1:]) if len(ordered) > 1 else None)
        agreement = None if etf_return is None or not values else (etf_return >= 0) == (_mean(values) >= 0)
        if agreement is None:
            out.append(self._not_available("etf_basket_agreement", theme_id, scope, point, source, "boolean", "required_returns_missing"))
        else:
            out.append(self._feature("etf_basket_agreement", theme_id, scope, point, source, agreement, "boolean"))
        number("return_dispersion", pstdev(values) if len(values) > 1 else None, "decimal_return")

        etf_row = current.get(etf, {})
        vwap = etf_row.get("vwap", {})
        if vwap.get("status") == "NOT_YET_DEFINED":
            out.append(self._not_available("vwap_distance", theme_id, etf, point, source, "decimal_return", "vwap_not_yet_defined_at_open", not_applicable=point == "open_snapshot"))
        else:
            vwap_value = float(vwap["value"]) if vwap.get("status") == "READY" and vwap.get("value") else None
            number("vwap_distance", change(etf_price, vwap_value), "decimal_return", "vwap_missing")
        bar = etf_row.get("minute_bar", {})
        if bar.get("status") == "NOT_YET_DEFINED":
            out.append(self._not_available("range_position", theme_id, etf, point, source, "unit_interval", "minute_bar_not_yet_defined_at_open", not_applicable=point == "open_snapshot"))
        else:
            high = float(bar["high"]) if bar.get("high") is not None else None
            low = float(bar["low"]) if bar.get("low") is not None else None
            position = None if etf_price is None or high is None or low is None or high == low else (etf_price - low) / (high - low)
            number("range_position", position, "unit_interval", "minute_range_missing_or_flat")

        for feature_id, left, right, valid_point in (
            ("preclose_decision_confirmation", "preclose_snapshot", "decision_snapshot", "decision_snapshot"),
            ("decision_close_confirmation", "decision_snapshot", "session_close_diagnostic", "session_close_diagnostic"),
        ):
            if point != valid_point:
                out.append(self._not_available(feature_id, theme_id, etf, point, source, "boolean", "feature_defined_at_later_observation_point", not_applicable=True))
                continue
            comparison_source = self._source("open_snapshot", left, right)
            left_return = change(_source_price(self.rows.get(left, {}).get(etf)), etf_open)
            right_return = change(_source_price(self.rows.get(right, {}).get(etf)), etf_open)
            confirmed = None if left_return is None or right_return is None else (left_return >= 0) == (right_return >= 0)
            if confirmed is None:
                out.append(self._not_available(feature_id, theme_id, etf, point, comparison_source, "boolean", "comparison_price_missing"))
            else:
                out.append(self._feature(feature_id, theme_id, etf, point, comparison_source, confirmed, "boolean"))

        quote = etf_row.get("quote", {})
        mid = quote.get("mid")
        spread = quote.get("quoted_spread")
        number("spread_percent", float(spread) / float(mid) if spread is not None and mid not in (None, 0) else None, "decimal_fraction", "quote_spread_missing")
        number("quote_freshness", _quote_age(etf_row), "seconds", "quote_timestamp_missing")
        number("trade_freshness", _trade_age(etf_row), "seconds", "trade_timestamp_missing")
        payload = self.points[point]
        number("event_time_dispersion", float(payload["event_time_dispersion_seconds"]) if payload.get("event_time_dispersion_seconds") is not None else None, "seconds", "event_time_dispersion_missing")
        number("freeze_duration", float(payload["freeze_duration_seconds"]) if payload.get("freeze_duration_seconds") is not None else None, "seconds", "freeze_duration_missing")
        theme_rows = [current.get(etf), *(current.get(symbol) for symbol in basket)]
        ages = [age for row in theme_rows if (age := _quote_age(row)) is not None]
        number("primary_feed_gap", max(ages) if ages else None, "seconds", "primary_quote_timestamp_missing")
        statuses = Counter(
            str(row.get("rest_reconciliation", {}).get("quote_match_status", "UNKNOWN"))
            for row in theme_rows
            if row
        )
        out.append(self._feature("rest_reconciliation_summary", theme_id, scope, point, source, dict(sorted(statuses.items())), "status_counts"))
        return out


def feature_index(features: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row["theme_id"]), str(row["observation_point"]), str(row["feature_id"])): row
        for row in features["features"]
    }
