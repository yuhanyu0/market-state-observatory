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

FEATURE_SET_VERSION = "observation-features-v2"
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
    "volume_coverage",
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

EVIDENCE_QUALITIES = {
    "VALID",
    "STALE_SOURCE",
    "INCOMPLETE_SOURCE",
    "BASELINE_ONLY",
    "NOT_APPLICABLE",
}

OPEN_BASELINE_FEATURES = {
    "etf_intraday_return",
    "relative_to_spy_return",
    "relative_to_industry_return",
    "basket_mean_return",
    "basket_median_return",
}

OPEN_NOT_APPLICABLE_FEATURES = {
    "constituent_positive_breadth",
    "constituent_negative_breadth",
    "residual_breadth",
    "volume_coverage",
    "volume_breadth",
    "single_name_concentration",
    "leader_rest_gap",
    "etf_basket_agreement",
    "return_dispersion",
}

RECONCILIATION_STATUSES = {
    "MATCH_WITHIN_TOLERANCE",
    "ASYNC_EXPECTED",
    "MATERIAL_DIFFERENCE",
    "PRIMARY_NOT_READY",
    "REST_UNAVAILABLE",
}


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


def _normalized_reconciliation_status(value: object) -> str:
    status = str(value or "REST_UNAVAILABLE")
    if status in RECONCILIATION_STATUSES:
        return status
    if status == "MATCH":
        return "MATCH_WITHIN_TOLERANCE"
    if status == "DIFFERENT":
        return "ASYNC_EXPECTED"
    if status in {"REST_MISSING", "UNAVAILABLE", "UNKNOWN"}:
        return "REST_UNAVAILABLE"
    return "REST_UNAVAILABLE"


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
        evidence_quality: str = "VALID",
        model_input_eligible: bool | None = None,
    ) -> dict[str, Any]:
        if evidence_quality not in EVIDENCE_QUALITIES:
            raise ValueError(f"Unsupported evidence quality: {evidence_quality}")
        calculation_exists = value is not None
        eligible = (
            status == "AVAILABLE" and evidence_quality == "VALID" and calculation_exists
            if model_input_eligible is None
            else model_input_eligible
        )
        if eligible and (
            status != "AVAILABLE" or evidence_quality != "VALID" or not calculation_exists
        ):
            raise ValueError("Only an available VALID calculation may be model-input eligible")
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
            "calculation_exists": calculation_exists,
            "evidence_quality": evidence_quality,
            "model_input_eligible": eligible,
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
        not_calibrated: bool = False,
        evidence_quality: str | None = None,
    ) -> dict[str, Any]:
        status = (
            "NOT_APPLICABLE"
            if not_applicable
            else "NOT_CALIBRATED"
            if not_calibrated
            else "NOT_AVAILABLE"
        )
        return self._feature(
            feature_id,
            theme_id,
            scope,
            point,
            source,
            None,
            units,
            status=status,
            reason=reason,
            evidence_quality=evidence_quality
            or ("NOT_APPLICABLE" if not_applicable else "INCOMPLETE_SOURCE"),
            model_input_eligible=False,
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
            "schema_version": "mso-observation-features-v2",
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
        evidence_qualities = Counter(str(row["evidence_quality"]) for row in features)
        invalid_unit_intervals = [
            row
            for row in features
            if row["units"] == "unit_interval"
            and row["evidence_quality"] == "VALID"
            and row["value"] is not None
            and not 0.0 <= float(row["value"]) <= 1.0
        ]
        if invalid_unit_intervals:
            raise ValueError("VALID unit_interval feature is outside [0,1]")
        decision = self.points.get("decision_snapshot", {})
        decision_rows = decision.get("symbols", [])
        observed_ages = [age for row in decision_rows if (age := _quote_age(row)) is not None]
        ready_ages = [
            age
            for row in decision_rows
            if row.get("quote", {}).get("status") == "READY" and (age := _quote_age(row)) is not None
        ]
        quality = {
            "schema_version": "mso-feature-quality-v2",
            "run_id": self.run["run_id"],
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_count": len(features),
            "availability_counts": dict(sorted(statuses.items())),
            "evidence_quality_counts": dict(sorted(evidence_qualities.items())),
            "calculation_exists_count": sum(bool(row["calculation_exists"]) for row in features),
            "model_input_eligible_count": sum(
                bool(row["model_input_eligible"]) for row in features
            ),
            "stale_model_input_eligible_count": sum(
                row["evidence_quality"] == "STALE_SOURCE"
                and bool(row["model_input_eligible"])
                for row in features
            ),
            "valid_unit_interval_violation_count": len(invalid_unit_intervals),
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
        is_open = point == "open_snapshot"
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

        def source_quality(symbols: Iterable[str], *dependency_points: str) -> str:
            rows: list[dict[str, Any]] = []
            for dependency_point in dependency_points or (point,):
                point_rows = self.rows.get(dependency_point)
                if point_rows is None:
                    return "INCOMPLETE_SOURCE"
                for symbol in symbols:
                    row = point_rows.get(symbol)
                    if row is None or row.get("observation_status") != "CAPTURED":
                        return "INCOMPLETE_SOURCE"
                    rows.append(row)
            quote_statuses = {str(row.get("quote", {}).get("status")) for row in rows}
            if "STALE" in quote_statuses:
                return "STALE_SOURCE"
            if not quote_statuses or not quote_statuses <= {"READY"}:
                return "INCOMPLETE_SOURCE"
            return "VALID"

        def number(
            feature_id: str,
            value: float | None,
            units: str = "decimal_return",
            reason: str = "required_price_missing",
            *,
            evidence_quality: str = "VALID",
            model_input_eligible: bool | None = None,
        ) -> None:
            if value is None or not math.isfinite(value):
                out.append(
                    self._not_available(
                        feature_id,
                        theme_id,
                        scope,
                        point,
                        source,
                        units,
                        reason,
                        evidence_quality="INCOMPLETE_SOURCE",
                    )
                )
            else:
                out.append(
                    self._feature(
                        feature_id,
                        theme_id,
                        scope,
                        point,
                        source,
                        value,
                        units,
                        evidence_quality=evidence_quality,
                        model_input_eligible=model_input_eligible,
                    )
                )

        etf_quality = source_quality((etf,), "open_snapshot", point)
        spy_quality = source_quality((etf, "SPY"), "open_snapshot", point)
        industry_quality = source_quality((etf, industry), "open_snapshot", point)
        basket_quality = source_quality(basket, "open_snapshot", point)
        baseline_quality = "BASELINE_ONLY" if is_open else None

        number(
            "etf_intraday_return",
            etf_return,
            evidence_quality=baseline_quality or etf_quality,
        )
        number(
            "relative_to_spy_return",
            None if etf_return is None or spy_return is None else etf_return - spy_return,
            evidence_quality=baseline_quality or spy_quality,
        )
        number(
            "relative_to_industry_return",
            None
            if etf_return is None or industry_return is None
            else etf_return - industry_return,
            evidence_quality=baseline_quality or industry_quality,
        )
        number(
            "basket_mean_return",
            _mean(values) if values else None,
            evidence_quality=baseline_quality or basket_quality,
        )
        number(
            "basket_median_return",
            median(values) if values else None,
            evidence_quality=baseline_quality or basket_quality,
        )

        if is_open:
            for feature_id in (
                "constituent_positive_breadth",
                "constituent_negative_breadth",
                "residual_breadth",
            ):
                out.append(
                    self._not_available(
                        feature_id,
                        theme_id,
                        scope,
                        point,
                        source,
                        "proportion",
                        "open_baseline_has_no_path_information",
                        not_applicable=True,
                    )
                )
        else:
            number(
                "constituent_positive_breadth",
                sum(value > 0 for value in values) / len(values) if values else None,
                "proportion",
                evidence_quality=basket_quality,
            )
            number(
                "constituent_negative_breadth",
                sum(value < 0 for value in values) / len(values) if values else None,
                "proportion",
                evidence_quality=basket_quality,
            )
            number(
                "residual_breadth",
                sum(value > spy_return for value in values) / len(values)
                if values and spy_return is not None
                else None,
                "proportion",
                evidence_quality=(
                    "STALE_SOURCE"
                    if "STALE_SOURCE" in {basket_quality, spy_quality}
                    else "INCOMPLETE_SOURCE"
                    if "INCOMPLETE_SOURCE" in {basket_quality, spy_quality}
                    else "VALID"
                ),
            )

        minute_volumes = [
            float(current[symbol]["minute_bar"]["volume"])
            for symbol in basket
            if symbol in current and current[symbol].get("minute_bar", {}).get("status") == "READY"
        ]
        if is_open:
            for feature_id in ("volume_coverage", "volume_breadth"):
                out.append(
                    self._not_available(
                        feature_id,
                        theme_id,
                        scope,
                        point,
                        source,
                        "proportion",
                        "open_minute_bar_not_yet_defined",
                        not_applicable=True,
                    )
                )
        else:
            coverage = len(minute_volumes) / len(basket) if basket else None
            number(
                "volume_coverage",
                coverage,
                "proportion",
                "minute_volume_missing",
                evidence_quality=(
                    "VALID" if coverage == 1.0 else "INCOMPLETE_SOURCE"
                ),
            )
            out.append(
                self._not_available(
                    "volume_breadth",
                    theme_id,
                    scope,
                    point,
                    source,
                    "proportion",
                    "historical_time_of_day_volume_calibration_unavailable",
                    not_calibrated=True,
                )
            )

        if is_open:
            units_by_feature = {
                "single_name_concentration": "proportion",
                "leader_rest_gap": "decimal_return",
                "etf_basket_agreement": "boolean",
                "return_dispersion": "decimal_return",
            }
            for feature_id, units in units_by_feature.items():
                out.append(
                    self._not_available(
                        feature_id,
                        theme_id,
                        scope,
                        point,
                        source,
                        units,
                        "open_baseline_has_no_path_information",
                        not_applicable=True,
                    )
                )
        else:
            abs_total = sum(abs(value) for value in values)
            number(
                "single_name_concentration",
                max((abs(value) for value in values), default=0.0) / abs_total
                if abs_total
                else None,
                "proportion",
                "constituent_move_total_is_zero",
                evidence_quality=basket_quality,
            )
            ordered = sorted(values, reverse=True)
            number(
                "leader_rest_gap",
                ordered[0] - _mean(ordered[1:]) if len(ordered) > 1 else None,
                evidence_quality=basket_quality,
            )
            agreement = (
                None
                if etf_return is None or not values
                else (etf_return >= 0) == (_mean(values) >= 0)
            )
            agreement_quality = (
                "STALE_SOURCE"
                if "STALE_SOURCE" in {etf_quality, basket_quality}
                else "INCOMPLETE_SOURCE"
                if "INCOMPLETE_SOURCE" in {etf_quality, basket_quality}
                else "VALID"
            )
            if agreement is None:
                out.append(
                    self._not_available(
                        "etf_basket_agreement",
                        theme_id,
                        scope,
                        point,
                        source,
                        "boolean",
                        "required_returns_missing",
                    )
                )
            else:
                out.append(
                    self._feature(
                        "etf_basket_agreement",
                        theme_id,
                        scope,
                        point,
                        source,
                        agreement,
                        "boolean",
                        evidence_quality=agreement_quality,
                    )
                )
            number(
                "return_dispersion",
                pstdev(values) if len(values) > 1 else None,
                "decimal_return",
                evidence_quality=basket_quality,
            )

        etf_row = current.get(etf, {})
        vwap = etf_row.get("vwap", {})
        if vwap.get("status") == "NOT_YET_DEFINED":
            out.append(
                self._not_available(
                    "vwap_distance",
                    theme_id,
                    etf,
                    point,
                    source,
                    "decimal_return",
                    "vwap_not_yet_defined_at_open",
                    not_applicable=is_open,
                )
            )
        else:
            vwap_value = (
                float(vwap["value"])
                if vwap.get("status") == "READY" and vwap.get("value")
                else None
            )
            number(
                "vwap_distance",
                change(etf_price, vwap_value),
                "decimal_return",
                "vwap_missing",
                evidence_quality=etf_quality,
            )

        session_range = etf_row.get("session_range", {})
        if is_open:
            out.append(
                self._not_available(
                    "range_position",
                    theme_id,
                    etf,
                    point,
                    source,
                    "unit_interval",
                    "session_range_not_yet_defined_at_open",
                    not_applicable=True,
                )
            )
        else:
            high = (
                float(session_range["high"])
                if session_range.get("status") == "READY"
                and session_range.get("high") is not None
                else None
            )
            low = (
                float(session_range["low"])
                if session_range.get("status") == "READY"
                and session_range.get("low") is not None
                else None
            )
            position = (
                None
                if etf_price is None
                or high is None
                or low is None
                or high <= low
                else (etf_price - low) / (high - low)
            )
            if position is not None and not 0.0 <= position <= 1.0:
                raise ValueError("range_position calculation is outside [0,1]")
            number(
                "range_position",
                position,
                "unit_interval",
                "cumulative_session_range_missing_or_flat",
                evidence_quality=etf_quality,
            )

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
            confirmed = (
                None
                if left_return is None or right_return is None
                else (left_return >= 0) == (right_return >= 0)
            )
            confirmation_quality = source_quality(
                (etf,), "open_snapshot", left, right
            )
            if confirmed is None:
                out.append(
                    self._not_available(
                        feature_id,
                        theme_id,
                        etf,
                        point,
                        comparison_source,
                        "boolean",
                        "comparison_price_missing",
                    )
                )
            else:
                out.append(
                    self._feature(
                        feature_id,
                        theme_id,
                        etf,
                        point,
                        comparison_source,
                        confirmed,
                        "boolean",
                        evidence_quality=confirmation_quality,
                    )
                )

        quote = etf_row.get("quote", {})
        mid = quote.get("mid")
        spread = quote.get("quoted_spread")
        quote_quality = (
            "STALE_SOURCE"
            if quote.get("status") == "STALE"
            else "VALID"
            if quote.get("status") == "READY"
            else "INCOMPLETE_SOURCE"
        )
        number(
            "spread_percent",
            float(spread) / float(mid)
            if spread is not None and mid not in (None, 0)
            else None,
            "decimal_fraction",
            "quote_spread_missing",
            evidence_quality=quote_quality,
        )
        number(
            "quote_freshness",
            _quote_age(etf_row),
            "seconds",
            "quote_timestamp_missing",
            evidence_quality="VALID",
        )
        number(
            "trade_freshness",
            _trade_age(etf_row),
            "seconds",
            "trade_timestamp_missing",
            evidence_quality="VALID",
        )
        payload = self.points[point]
        number(
            "event_time_dispersion",
            float(payload["event_time_dispersion_seconds"])
            if payload.get("event_time_dispersion_seconds") is not None
            else None,
            "seconds",
            "event_time_dispersion_missing",
        )
        number(
            "freeze_duration",
            float(payload["freeze_duration_seconds"])
            if payload.get("freeze_duration_seconds") is not None
            else None,
            "seconds",
            "freeze_duration_missing",
        )
        theme_rows = [current.get(etf), *(current.get(symbol) for symbol in basket)]
        ages = [age for row in theme_rows if (age := _quote_age(row)) is not None]
        number(
            "primary_feed_gap",
            max(ages) if ages else None,
            "seconds",
            "primary_quote_timestamp_missing",
        )
        statuses = Counter(
            _normalized_reconciliation_status(
                row.get("rest_reconciliation", {}).get("quote_match_status")
            )
            for row in theme_rows
            if row
        )
        out.append(
            self._feature(
                "rest_reconciliation_summary",
                theme_id,
                scope,
                point,
                source,
                dict(sorted(statuses.items())),
                "status_counts",
                model_input_eligible=False,
            )
        )
        return out


def feature_index(features: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row["theme_id"]), str(row["observation_point"]), str(row["feature_id"])): row
        for row in features["features"]
    }
