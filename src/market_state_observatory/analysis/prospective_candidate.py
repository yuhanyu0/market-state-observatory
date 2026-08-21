from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from market_state_observatory.execution_modes import ExecutionMode, authorize_mode
from market_state_observatory.runtime.alpaca_adapter import (
    DATA_ENDPOINT,
    AlpacaSIPAdapter,
    RestResult,
    parse_utc,
)
from market_state_observatory.runtime.observation_freezer import (
    canonical_json,
    freeze_provider_response,
    sha256_bytes,
    write_exclusive,
)
from market_state_observatory.validation import validate_payload

from .model_disposition import ModelDispositionRegistry

ET = ZoneInfo("America/New_York")
COST_GRID_BPS = (0.0, 5.0, 10.0, 15.0, 25.0, 50.0)
HORIZONS = (
    "preclose_quote_to_close",
    "preclose_quote_to_next_open",
    "preclose_quote_to_next_close",
    "postclose_signal_next_open_to_next_close",
    "next_open_to_3d_close",
    "next_open_to_5d_close",
)
PROSPECTIVE_ARMS = (
    "B0_ZERO",
    "B1_THEME_ETF_5D_MOMENTUM",
    "B2_SPY_RELATIVE_MOMENTUM",
    "D0_PIT_CONTROL",
    "D1_PIT_CORE",
    "D1_PIT_FULL",
    "T0_PIT",
    "D1_PIT_CORE_PLUS_T",
    "D1_PIT_CORE_PLUS_THEME_RADAR_ATTENTION",
    "D1_PIT_CORE_PLUS_T_PLUS_E0",
)
SAFETY = {
    "prospective_unvalidated": True,
    "decision_eligible": False,
    "counterfactual_only": True,
    "paper_positions": 0,
    "real_orders": 0,
}


class CandidateShadowError(RuntimeError):
    pass


class MarketDataAdapter(Protocol):
    def latest_quotes(self, symbols: Iterable[str]) -> RestResult: ...


@dataclass(frozen=True)
class PriceObservation:
    bid: float
    ask: float
    mid: float
    event_time_utc: str
    observed_at_utc: str
    provider: str
    source_run_id: str
    source_snapshot_sha256: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CandidateShadowError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _protocol(path: Path | None = None) -> tuple[dict[str, Any], str, Path]:
    candidates = (
        path,
        _repo_root() / "config" / "prospective_candidate_protocol_v1.json",
        Path(os.environ.get("MSO_RELEASE_ROOT", ""))
        / "config"
        / "prospective_candidate_protocol_v1.json",
    )
    selected = next((row for row in candidates if row and row.is_file()), None)
    if selected is None:
        raise FileNotFoundError("prospective_candidate_protocol_v1.json is unavailable")
    raw = selected.read_bytes()
    payload = json.loads(raw)
    if tuple(payload.get("arms", ())) != PROSPECTIVE_ARMS:
        raise CandidateShadowError("Prospective candidate arm registry differs from frozen v1")
    if payload.get("H2_MODEL_MINING_CLOSED") is not True:
        raise CandidateShadowError("H2 model-mining closure is not frozen")
    return cast(dict[str, Any], payload), sha256(raw).hexdigest(), selected


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _change(value: float | None, base: float | None) -> float | None:
    return value / base - 1.0 if value is not None and base not in (None, 0.0) else None


def _point(run_directory: Path, name: str) -> tuple[dict[str, Any], Path]:
    path = run_directory / "manifests" / "points" / f"{name}.json"
    if not path.is_file():
        raise CandidateShadowError(f"Required immutable observation point is missing: {name}")
    payload = _load_json(path)
    if payload.get("observation_point") != name:
        raise CandidateShadowError(f"Observation point identity mismatch: {name}")
    return payload, path


def _point_sha(payload: dict[str, Any], path: Path) -> str:
    value = payload.get("snapshot_bundle_sha256")
    return str(value) if value else _file_sha256(path)


def _five_day_momentum_history(
    *,
    run_directory: Path,
    history_run_roots: Sequence[Path],
    lane: str,
    tickers: Sequence[str],
) -> tuple[dict[str, float | None], dict[str, Path]]:
    current = _load_json(run_directory / "RUN.json")
    signal_date = date.fromisoformat(str(current["trading_date"]))
    experiment_lane = str(current.get("experiment_lane", ""))
    run_paths = {run_directory / "RUN.json"}
    for root in history_run_roots:
        if root.exists():
            run_paths.update(root.rglob("RUN.json"))
    by_date: dict[date, list[Path]] = {}
    for run_path in sorted(run_paths):
        candidate = _load_json(run_path)
        candidate_date = date.fromisoformat(str(candidate["trading_date"]))
        if str(candidate.get("experiment_lane", "")) != experiment_lane:
            continue
        if candidate_date > signal_date or (lane == "preclose" and candidate_date == signal_date):
            continue
        by_date.setdefault(candidate_date, []).append(run_path.parent)

    selected: list[tuple[date, Path, dict[str, Any], Path]] = []
    for candidate_date in sorted(by_date, reverse=True):
        for candidate_run in sorted(by_date[candidate_date], reverse=True):
            try:
                point, point_path = _point(candidate_run, "session_close_diagnostic")
            except CandidateShadowError:
                continue
            if point.get("backfilled") is not False or int(point.get("future_timestamp_count", 0)):
                continue
            selected.append((candidate_date, candidate_run, point, point_path))
            break
        if len(selected) == 6:
            break
    selected.reverse()
    artifacts: dict[str, Path] = {}
    histories: dict[str, list[float]] = {ticker: [] for ticker in tickers}
    for candidate_date, candidate_run, point, point_path in selected:
        source_run = _load_json(candidate_run / "RUN.json")
        source_id = str(source_run["run_id"])
        artifacts[f"history/{candidate_date.isoformat()}/{source_id}/RUN.json"] = (
            candidate_run / "RUN.json"
        )
        artifacts[
            f"history/{candidate_date.isoformat()}/{source_id}/session_close_diagnostic.json"
        ] = point_path
        rows = {str(row["symbol"]): row for row in point.get("symbols", [])}
        for ticker in tickers:
            value = _source_price(rows.get(ticker))
            if value is not None:
                histories[ticker].append(value)
    momentum = {
        ticker: values[-1] / values[0] - 1.0 if len(values) == 6 and values[0] > 0 else None
        for ticker, values in histories.items()
    }
    return momentum, artifacts


def _theme_features(run_directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run = _load_json(run_directory / "RUN.json")
    membership = _load_json(run_directory / "reference" / "membership_snapshot.json")
    opened, _ = _point(run_directory, "open_snapshot")
    preclose, _ = _point(run_directory, "preclose_snapshot")
    decision, decision_path = _point(run_directory, "decision_snapshot")
    open_rows = {str(row["symbol"]): row for row in opened.get("symbols", [])}
    preclose_rows = {str(row["symbol"]): row for row in preclose.get("symbols", [])}
    decision_rows = {str(row["symbol"]): row for row in decision.get("symbols", [])}
    rows: list[dict[str, Any]] = []
    for theme in membership.get("themes", []):
        theme_id = str(theme["theme_id"])
        etf = str(theme["theme_etf"])
        industry = str(theme["industry_benchmark"])
        basket = tuple(map(str, theme["basket"]))
        etf_open = _source_price(open_rows.get(etf))
        etf_now = _source_price(decision_rows.get(etf))
        spy_return = _change(_source_price(decision_rows.get("SPY")), _source_price(open_rows.get("SPY")))
        etf_return = _change(etf_now, etf_open)
        industry_return = _change(
            _source_price(decision_rows.get(industry)), _source_price(open_rows.get(industry))
        )
        basket_returns = [
            value
            for symbol in basket
            if (
                value := _change(
                    _source_price(decision_rows.get(symbol)),
                    _source_price(open_rows.get(symbol)),
                )
            )
            is not None
        ]
        relative_spy = (
            etf_return - spy_return
            if etf_return is not None and spy_return is not None
            else None
        )
        relative_industry = (
            etf_return - industry_return
            if etf_return is not None and industry_return is not None
            else None
        )
        etf_row = decision_rows.get(etf, {})
        vwap = etf_row.get("vwap", {})
        vwap_value = float(vwap["value"]) if vwap.get("status") == "READY" else None
        vwap_distance = _change(etf_now, vwap_value)
        preclose_return = _change(_source_price(preclose_rows.get(etf)), etf_open)
        confirmation = (
            (preclose_return >= 0) == (etf_return >= 0)
            if preclose_return is not None and etf_return is not None
            else None
        )
        session_range = etf_row.get("session_range", {})
        high = session_range.get("high")
        low = session_range.get("low")
        range_position = (
            (float(etf_now) - float(low)) / (float(high) - float(low))
            if etf_now is not None
            and high is not None
            and low is not None
            and float(high) > float(low)
            else None
        )
        positive_breadth = (
            sum(value > 0 for value in basket_returns) / len(basket_returns)
            if basket_returns
            else None
        )
        residual_breadth = (
            sum(value > spy_return for value in basket_returns) / len(basket_returns)
            if basket_returns and spy_return is not None
            else None
        )
        absolute_total = sum(abs(value) for value in basket_returns)
        concentration = (
            max(abs(value) for value in basket_returns) / absolute_total
            if absolute_total
            else None
        )
        etf_quote = etf_row.get("quote", {})
        quote_age = etf_quote.get("freshness_age_seconds")
        core = {
            "relative_to_spy_return": relative_spy,
            "relative_to_industry_return": relative_industry,
            "basket_median_return": median(basket_returns) if basket_returns else None,
            "constituent_positive_breadth": positive_breadth,
            "vwap_distance": vwap_distance,
            "preclose_decision_confirmation": confirmation,
        }
        rows.append(
            {
                "theme_id": theme_id,
                "theme_etf": etf,
                "industry_benchmark": industry,
                "basket": list(basket),
                "core": core,
                "range_position": range_position,
                "volume_breadth": None,
                "transmission": {
                    "etf_basket_agreement": (
                        (etf_return >= 0) == (mean(basket_returns) >= 0)
                        if etf_return is not None and basket_returns
                        else None
                    ),
                    "residual_breadth": residual_breadth,
                    "single_name_concentration": concentration,
                    "constituent_coverage": len(basket_returns) / len(basket) if basket else 0.0,
                },
                "decision_quote_status": etf_quote.get("status"),
                "decision_quote_age_seconds": quote_age,
            }
        )
    return rows, {
        "run": run,
        "membership": membership,
        "decision": decision,
        "decision_path": decision_path,
    }


def _core_score(features: dict[str, Any], protocol: dict[str, Any]) -> float | None:
    core = features["core"]
    required = tuple(protocol["d1_core_features"])
    if any(core.get(name) is None for name in required):
        return None
    weights = protocol["d1_core_weights"]
    confirmation = 1.0 if core["preclose_decision_confirmation"] else -1.0
    return float(
        core["relative_to_spy_return"] * weights["relative_to_spy_return"]
        + core["relative_to_industry_return"] * weights["relative_to_industry_return"]
        + core["basket_median_return"] * weights["basket_median_return"]
        + (core["constituent_positive_breadth"] - 0.5)
        * weights["constituent_positive_breadth_centered"]
        + core["vwap_distance"] * weights["vwap_distance"]
        + confirmation * weights["preclose_decision_confirmation"]
    )


def _transmission_state(features: dict[str, Any]) -> str:
    values = features["transmission"]
    if any(values.get(name) is None for name in ("etf_basket_agreement", "residual_breadth", "single_name_concentration")):
        return "not_estimable"
    if float(values["constituent_coverage"]) < 0.8:
        return "absent"
    if values["etf_basket_agreement"] is not True:
        return "negative_coherence"
    if float(values["residual_breadth"]) >= 0.6 and float(values["single_name_concentration"]) <= 0.55:
        return "broad_confirmed"
    if float(values["single_name_concentration"]) > 0.55:
        return "narrow_only"
    return "absent"


def _ranked_signal(
    arm: str,
    theme_scores: list[dict[str, Any]],
    *,
    positive_threshold: float,
    negative_threshold: float,
    blockers: Sequence[str] = (),
) -> dict[str, Any]:
    available = [row for row in theme_scores if isinstance(row.get("score"), (int, float))]
    selected: dict[str, Any] | None = None
    predicted_sign: int | None = None
    if available:
        high = max(available, key=lambda row: (float(row["score"]), str(row["theme_id"])))
        low = min(available, key=lambda row: (float(row["score"]), str(row["theme_id"])))
        if float(high["score"]) >= positive_threshold or float(low["score"]) <= negative_threshold:
            selected = (
                high
                if abs(float(high["score"])) >= abs(float(low["score"]))
                else low
            )
            predicted_sign = 1 if float(selected["score"]) >= 0 else -1
    reasons = list(blockers)
    if not available:
        reasons.append("no_legal_point_in_time_scores")
    elif selected is None:
        reasons.append("all_scores_inside_frozen_unresolved_band")
    return {
        "arm": arm,
        "status": "ESTIMATED" if selected is not None else "INSUFFICIENT",
        "selected_theme_id": selected.get("theme_id") if selected else None,
        "selected_ticker": selected.get("theme_etf") if selected else None,
        "predicted_sign": predicted_sign,
        "probability_positive": None,
        "score": selected.get("score") if selected else None,
        "theme_scores": theme_scores,
        "blocking_reasons": sorted(set(reasons)),
        "vehicle": "Theme_ETF" if selected else "Cash",
        "not_a_recommendation": True,
    }


def build_candidate_arms(
    theme_features: list[dict[str, Any]], protocol: dict[str, Any]
) -> list[dict[str, Any]]:
    positive = float(protocol["positive_threshold"])
    negative = float(protocol["negative_threshold"])
    core_scores = [
        {
            "theme_id": row["theme_id"],
            "theme_etf": row["theme_etf"],
            "score": _core_score(row, protocol),
            "transmission_state": _transmission_state(row),
        }
        for row in theme_features
    ]
    relative_scores = [
        {
            "theme_id": row["theme_id"],
            "theme_etf": row["theme_etf"],
            "score": row["core"]["relative_to_spy_return"],
            "transmission_state": _transmission_state(row),
        }
        for row in theme_features
    ]
    five_day_scores = [
        {
            "theme_id": row["theme_id"],
            "theme_etf": row["theme_etf"],
            "score": row.get("theme_etf_5d_momentum"),
            "transmission_state": _transmission_state(row),
        }
        for row in theme_features
    ]
    full_scores = [
        {
            **score,
            "score": (
                score["score"]
                if row["range_position"] is not None and row["volume_breadth"] is not None
                else None
            ),
        }
        for score, row in zip(core_scores, theme_features, strict=True)
    ]
    broad_scores = [
        {**row, "score": row["score"] if row["transmission_state"] == "broad_confirmed" else None}
        for row in core_scores
    ]
    outputs: list[dict[str, Any]] = [
        {
            "arm": "B0_ZERO",
            "status": "CONTROL_ONLY",
            "selected_theme_id": None,
            "selected_ticker": None,
            "predicted_sign": 0,
            "probability_positive": 0.5,
            "score": 0.0,
            "theme_scores": [],
            "blocking_reasons": [],
            "vehicle": "Cash",
            "not_a_recommendation": True,
        },
        _ranked_signal(
            "B1_THEME_ETF_5D_MOMENTUM",
            five_day_scores,
            positive_threshold=0.0,
            negative_threshold=0.0,
        ),
        _ranked_signal("B2_SPY_RELATIVE_MOMENTUM", relative_scores, positive_threshold=0.0, negative_threshold=0.0),
        _ranked_signal("D0_PIT_CONTROL", relative_scores, positive_threshold=0.0, negative_threshold=0.0),
        _ranked_signal("D1_PIT_CORE", core_scores, positive_threshold=positive, negative_threshold=negative),
        _ranked_signal(
            "D1_PIT_FULL",
            full_scores,
            positive_threshold=positive,
            negative_threshold=negative,
            blockers=("range_and_volume_breadth_are_full_only",),
        ),
        {
            "arm": "T0_PIT",
            "status": "DESCRIPTIVE_ONLY",
            "selected_theme_id": None,
            "selected_ticker": None,
            "predicted_sign": None,
            "probability_positive": None,
            "score": None,
            "theme_scores": core_scores,
            "blocking_reasons": ["transmission_is_not_a_standalone_direction_signal"],
            "vehicle": "Cash",
            "not_a_recommendation": True,
        },
        _ranked_signal("D1_PIT_CORE_PLUS_T", broad_scores, positive_threshold=positive, negative_threshold=negative),
        _ranked_signal(
            "D1_PIT_CORE_PLUS_THEME_RADAR_ATTENTION",
            [{**row, "score": None} for row in core_scores],
            positive_threshold=positive,
            negative_threshold=negative,
            blockers=("theme_radar_attention_not_available_and_cannot_set_sign",),
        ),
        _ranked_signal(
            "D1_PIT_CORE_PLUS_T_PLUS_E0",
            [{**row, "score": None} for row in broad_scores],
            positive_threshold=positive,
            negative_threshold=negative,
            blockers=("e0_minimum_sequential_history_not_met",),
        ),
    ]
    if tuple(row["arm"] for row in outputs) != PROSPECTIVE_ARMS:
        raise CandidateShadowError("Candidate arm output order differs from frozen protocol")
    return outputs


def _decision_gate(
    run_directory: Path,
    theme_features: list[dict[str, Any]],
    context: dict[str, Any],
    generated_at: datetime,
    protocol: dict[str, Any],
) -> list[str]:
    decision = context["decision"]
    blockers: list[str] = []
    scheduled = _parse(str(decision["scheduled_at_utc"])).astimezone(ET)
    expected = time.fromisoformat(str(protocol["preclose"]["decision_snapshot_et"]))
    if scheduled.timetz().replace(tzinfo=None) != expected:
        blockers.append("decision_snapshot_not_scheduled_for_15_45_et")
    if decision.get("backfilled") is not False:
        blockers.append("decision_snapshot_backfilled")
    if int(decision.get("future_timestamp_count", 0)) != 0:
        blockers.append("decision_snapshot_contains_future_timestamp")
    maximum_age = float(protocol["preclose"]["maximum_decision_quote_age_seconds"])
    for row in theme_features:
        if row.get("decision_quote_status") != "READY":
            blockers.append(f"{row['theme_etf']}_decision_quote_not_ready")
        age = row.get("decision_quote_age_seconds")
        if age is None or float(age) > maximum_age:
            blockers.append(f"{row['theme_etf']}_decision_quote_stale")
    decision_observed = _parse(
        str(decision.get("freeze_completed_at_utc") or decision.get("captured_at_utc"))
    )
    if generated_at.astimezone(UTC) <= decision_observed.astimezone(UTC):
        blockers.append("candidate_not_generated_after_decision_freeze")
    execution_time = datetime.combine(
        scheduled.date(),
        time.fromisoformat(str(protocol["preclose"]["execution_quote_schedule_et"])),
        ET,
    )
    if generated_at.astimezone(ET) >= execution_time:
        blockers.append("candidate_generation_timeout")
    return sorted(set(blockers))


def _append_once(path: Path, payload: dict[str, Any], *, id_field: str) -> bool:
    encoded = canonical_json(payload)
    existing: dict[str, bytes] = {}
    if path.is_file():
        for raw in path.read_bytes().splitlines(keepends=True):
            if not raw.strip():
                continue
            row = json.loads(raw)
            existing[str(row[id_field])] = raw
    record_id = str(payload[id_field])
    if record_id in existing:
        if existing[record_id] != encoded:
            raise CandidateShadowError(f"Append-only ledger conflict: {record_id}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _candidate_directory(candidate_root: Path, lane: str, trading_date: str, run_id: str) -> Path:
    return candidate_root / lane / trading_date / f"{run_id}-{lane}"


def freeze_candidate_signal(
    *,
    run_directory: Path,
    candidate_root: Path,
    ledger_root: Path,
    lane: str,
    generated_at: datetime | None = None,
    analysis_directory: Path | None = None,
    history_run_roots: Sequence[Path] = (),
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    if lane not in {"preclose", "postclose"}:
        raise ValueError("Candidate lane must be preclose or postclose")
    authorization = authorize_mode(ExecutionMode.PROSPECTIVE_CANDIDATE_SHADOW)
    protocol, protocol_sha, selected_protocol_path = _protocol(protocol_path)
    disposition = ModelDispositionRegistry.load()
    for retired in (
        "D0_H2_SIMPLE_RELATIVE",
        "D1_H2_DAILY_RECONSTRUCTED",
        "D2_H2_PROBABILISTIC",
        "HISTORICAL_TRANSPARENT_BASELINE",
    ):
        disposition.assert_not_reactivated(retired, False)
    theme_features, context = _theme_features(run_directory)
    run = context["run"]
    trading_date = str(run["trading_date"])
    destination = _candidate_directory(candidate_root, lane, trading_date, str(run["run_id"]))
    signal_path = destination / "CANDIDATE_SIGNAL.json"
    manifest_path = destination / "CANDIDATE_SIGNAL_MANIFEST.json"
    if signal_path.is_file() and manifest_path.is_file():
        signal = _load_json(signal_path)
        if signal.get("protocol_sha256") != protocol_sha or signal.get("source_run_id") != run["run_id"]:
            raise CandidateShadowError("Existing immutable candidate does not match source/protocol")
        return signal
    now = (generated_at or datetime.now(UTC)).astimezone(UTC)
    decision = context["decision"]
    decision_event = _parse(str(decision["latest_event_time_utc"]))
    source_evidence_asof = decision_event
    momentum, history_artifacts = _five_day_momentum_history(
        run_directory=run_directory,
        history_run_roots=history_run_roots,
        lane=lane,
        tickers=[str(row["theme_etf"]) for row in theme_features],
    )
    for row in theme_features:
        row["theme_etf_5d_momentum"] = momentum[str(row["theme_etf"])]
    blockers: list[str] = []
    source_paths: tuple[Path, ...]
    if lane == "preclose":
        blockers.extend(_decision_gate(run_directory, theme_features, context, now, protocol))
        earliest_execution = "post_candidate_15_47_sip_quote"
        same_day_close_claim = False
        source_paths = (
            run_directory / "RUN.json",
            run_directory / "reference" / "membership_snapshot.json",
            run_directory / "manifests" / "points" / "open_snapshot.json",
            run_directory / "manifests" / "points" / "preclose_snapshot.json",
            run_directory / "manifests" / "points" / "decision_snapshot.json",
        )
    else:
        close, close_path = _point(run_directory, "session_close_diagnostic")
        close_observed = _parse(str(close.get("freeze_completed_at_utc") or close["captured_at_utc"]))
        source_evidence_asof = _parse(str(close["latest_event_time_utc"]))
        if now <= close_observed:
            blockers.append("postclose_candidate_not_after_close_evidence")
        if analysis_directory is None:
            blockers.append("daily_report_sidecar_missing")
        elif not (analysis_directory / "DAILY_REPORT_STATUS.json").is_file():
            blockers.append("daily_report_status_missing")
        earliest_execution = "next_trading_day_open"
        same_day_close_claim = False
        source_paths = (
            run_directory / "RUN.json",
            run_directory / "quality" / "DATA_QUALITY.json",
            run_directory / "reference" / "membership_snapshot.json",
            run_directory / "manifests" / "points" / "open_snapshot.json",
            run_directory / "manifests" / "points" / "preclose_snapshot.json",
            run_directory / "manifests" / "points" / "decision_snapshot.json",
            close_path,
            analysis_directory / "OBSERVATION_REPORT.json"
            if analysis_directory is not None
            else run_directory / "__missing_daily_report__",
        )
    source_hashes = {
        path.name if path.parent == run_directory else path.relative_to(run_directory).as_posix()
        if run_directory in path.parents
        else f"analysis/{path.name}": _file_sha256(path)
        for path in source_paths
        if path.is_file()
    }
    source_hashes.update(
        {relative_path: _file_sha256(path) for relative_path, path in history_artifacts.items()}
    )
    arms = build_candidate_arms(theme_features, protocol)
    candidate_id = sha256(
        f"{run['run_id']}:{lane}:{protocol_sha}".encode()
    ).hexdigest()[:24]
    signal = {
        "schema_version": "mso-prospective-candidate-signal-v1",
        "candidate_id": candidate_id,
        "source_run_id": run["run_id"],
        "source_run_sha256": _file_sha256(run_directory / "RUN.json"),
        "source_snapshot_sha256": _point_sha(decision, context["decision_path"]),
        "signal_date": trading_date,
        "lane": lane,
        "execution_mode": authorization.mode.value,
        "generated_at_utc": now.isoformat(),
        "source_evidence_asof_utc": source_evidence_asof.isoformat(),
        "candidate_frozen_before_outcome": not blockers,
        "candidate_status": "FROZEN" if not blockers else "BLOCKED",
        "blocking_reasons": sorted(set(blockers)),
        "earliest_legal_execution": earliest_execution,
        "same_day_close_signal_claim": same_day_close_claim,
        "protocol_version": protocol["version"],
        "protocol_sha256": protocol_sha,
        "model_disposition_sha256": disposition.sha256,
        "arms": arms,
        "source_features": theme_features,
        "broker_order_object": None,
        **SAFETY,
    }
    validate_payload(signal, "prospective_candidate_signal")
    signal_bytes = canonical_json(signal)
    manifest = {
        "schema_version": "mso-prospective-candidate-signal-manifest-v1",
        "candidate_id": candidate_id,
        "candidate_signal_sha256": sha256_bytes(signal_bytes),
        "protocol_relative_path": selected_protocol_path.name,
        "protocol_sha256": protocol_sha,
        "model_disposition_sha256": disposition.sha256,
        "source_artifacts": [
            {"relative_path": path, "sha256": digest}
            for path, digest in sorted(source_hashes.items())
        ],
        "excluded_post_signal_sources": (
            ["session_close_diagnostic", "quality/DATA_QUALITY.json", "future runs"]
            if lane == "preclose"
            else ["future runs"]
        ),
        "immutable": True,
        **SAFETY,
    }
    validate_payload(manifest, "prospective_candidate_signal_manifest")
    write_exclusive(signal_path, signal_bytes)
    write_exclusive(manifest_path, canonical_json(manifest))
    ledger_row = {
        "schema_version": "mso-prospective-signal-ledger-v1",
        "signal_record_id": candidate_id,
        "candidate_id": candidate_id,
        "signal_date": trading_date,
        "lane": lane,
        "generated_at_utc": now.isoformat(),
        "candidate_signal_sha256": sha256_bytes(signal_bytes),
        "candidate_manifest_sha256": _file_sha256(manifest_path),
        "source_run_id": run["run_id"],
        "source_snapshot_sha256": signal["source_snapshot_sha256"],
        "candidate_status": signal["candidate_status"],
        "valid_trading_date": signal["candidate_status"] == "FROZEN",
        "official_strategy_evidence": True,
        **SAFETY,
    }
    validate_payload(ledger_row, "prospective_signal_ledger")
    _append_once(
        ledger_root / "PROSPECTIVE_SIGNAL_LEDGER.ndjson",
        ledger_row,
        id_field="signal_record_id",
    )
    return signal


def capture_execution_quote(
    *,
    candidate_directory: Path,
    adapter: MarketDataAdapter | None = None,
    observed_at: datetime | None = None,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    signal_path = candidate_directory / "CANDIDATE_SIGNAL.json"
    if not signal_path.is_file():
        raise CandidateShadowError("Candidate signal must be frozen before execution quote")
    signal = _load_json(signal_path)
    if signal.get("lane") != "preclose":
        raise CandidateShadowError("Independent execution quote is only valid for preclose candidates")
    protocol, _, _ = _protocol(protocol_path)
    now = (observed_at or datetime.now(UTC)).astimezone(UTC)
    generated = _parse(str(signal["generated_at_utc"])).astimezone(UTC)
    execution_time = datetime.combine(
        date.fromisoformat(str(signal["signal_date"])),
        time.fromisoformat(str(protocol["preclose"]["execution_quote_schedule_et"])),
        ET,
    ).astimezone(UTC)
    if now < execution_time:
        raise CandidateShadowError("Execution quote observation point is not due")
    tickers = sorted(
        {
            str(row["selected_ticker"])
            for row in signal["arms"]
            if row.get("selected_ticker")
        }
    )
    if not tickers:
        tickers = sorted({str(row["theme_etf"]) for row in signal["source_features"]})
    market_adapter = adapter or AlpacaSIPAdapter()
    result = market_adapter.latest_quotes(tickers)
    if result.sanitized_request_parameters.get("feed") != "sip":
        raise CandidateShadowError("Execution quote did not explicitly use SIP")
    raw = freeze_provider_response(
        raw_directory=candidate_directory / "raw" / "execution_quote",
        manifest_directory=candidate_directory / "manifests" / "execution_quote",
        observation_id=result.collector_request_id,
        raw_response=result.raw_response,
        metadata=result.metadata(),
    )
    quotes = result.body.get("quotes", {})
    captured: list[dict[str, Any]] = []
    blockers: list[str] = list(signal.get("blocking_reasons", []))
    maximum_age = float(protocol["preclose"]["maximum_execution_quote_age_seconds"])
    response_observed = parse_utc(result.observed_at_utc)
    for ticker in tickers:
        quote = quotes.get(ticker)
        if not quote:
            blockers.append(f"{ticker}_execution_quote_missing")
            continue
        event = parse_utc(str(quote["t"]))
        bid = float(quote["bp"])
        ask = float(quote["ap"])
        mid = (bid + ask) / 2.0
        age = (response_observed - event).total_seconds()
        if event <= generated:
            blockers.append(f"{ticker}_execution_quote_not_after_candidate")
        if age < 0:
            blockers.append(f"{ticker}_execution_quote_future_timestamp")
        if age > maximum_age:
            blockers.append(f"{ticker}_execution_quote_stale")
        if bid <= 0 or ask <= 0 or ask < bid or not bid <= mid <= ask:
            blockers.append(f"{ticker}_execution_spread_invalid")
        captured.append(
            {
                "ticker": ticker,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "quoted_spread": ask - bid,
                "event_time_utc": event.isoformat(),
                "observed_at_utc": result.observed_at_utc,
                "quote_age_seconds": age,
                "provider": "Alpaca Market Data SIP",
            }
        )
    payload = {
        "schema_version": "mso-prospective-execution-quote-v1",
        "candidate_id": signal["candidate_id"],
        "candidate_signal_sha256": _file_sha256(signal_path),
        "captured_at_utc": result.observed_at_utc,
        "endpoint": DATA_ENDPOINT,
        "feed": "sip",
        "status": "EXECUTION_QUOTE_READY" if not blockers else "BLOCKED",
        "blocking_reasons": sorted(set(blockers)),
        "quotes": captured,
        "raw_response_sha256": raw.raw_response_sha256,
        "broker_order_object": None,
        **SAFETY,
    }
    validate_payload(payload, "prospective_execution_quote")
    write_exclusive(candidate_directory / "EXECUTION_QUOTE.json", canonical_json(payload))
    return payload


def execution_price_returns(
    *,
    predicted_sign: int,
    entry: PriceObservation,
    exit: PriceObservation,
    costs_bps: Sequence[float] = COST_GRID_BPS,
) -> dict[str, Any]:
    if predicted_sign not in {-1, 1}:
        raise ValueError("Execution return requires a long or short diagnostic sign")
    if _parse(exit.event_time_utc) <= _parse(entry.event_time_utc):
        raise CandidateShadowError("Outcome event must follow entry event")
    mid_gross = predicted_sign * (exit.mid / entry.mid - 1.0)
    if predicted_sign == 1:
        realistic_gross = exit.bid / entry.ask - 1.0
        contract = "long_ask_to_future_bid"
    else:
        realistic_gross = (entry.bid - exit.ask) / entry.bid
        contract = "short_bid_to_future_ask"
    return {
        "execution_contract": contract,
        "mid_to_mid_gross_return": mid_gross,
        "spread_realistic_gross_return": realistic_gross,
        "fixed_cost_net_returns": {
            f"{float(cost):g}": realistic_gross - float(cost) / 10_000.0
            for cost in costs_bps
        },
        "mid_is_executable_claim": False,
    }


def distinct_date_gate_status(signal_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    dates = sorted(
        {
            str(row["signal_date"])
            for row in signal_rows
            if row.get("valid_trading_date") is True
            and row.get("official_strategy_evidence") is True
            and row.get("prospective_unvalidated") is True
        }
    )
    count = len(dates)
    return {
        "valid_trading_dates": count,
        "date_keys": dates,
        "theme_rows_inflate_sample_count": False,
        "checkpoints": {
            "10": "REACHED_OPERATIONAL_ONLY" if count >= 10 else "PENDING",
            "20": "REACHED_EARLY_FAILURE_ONLY" if count >= 20 else "PENDING",
            "40": "REACHED_FIRST_PAIRED_ABLATION" if count >= 40 else "PENDING",
            "60": "REACHED_FINAL_REVIEW" if count >= 60 else "PENDING",
        },
        "positive_promotion_before_60_allowed": False,
    }


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _cli_freeze(args: argparse.Namespace) -> dict[str, Any]:
    return freeze_candidate_signal(
        run_directory=args.run.resolve(),
        candidate_root=args.candidate_root.resolve(),
        ledger_root=args.ledger_root.resolve(),
        lane=args.lane,
        analysis_directory=args.analysis.resolve() if args.analysis else None,
        history_run_roots=[path.resolve() for path in args.history_run_root],
    )


def _cli_quote(args: argparse.Namespace) -> dict[str, Any]:
    return capture_execution_quote(candidate_directory=args.candidate_directory.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prospective candidate-only signal and outcome engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--run", type=Path, required=True)
    freeze.add_argument("--candidate-root", type=Path, required=True)
    freeze.add_argument("--ledger-root", type=Path, required=True)
    freeze.add_argument("--lane", choices=("preclose", "postclose"), required=True)
    freeze.add_argument("--analysis", type=Path)
    freeze.add_argument("--history-run-root", type=Path, action="append", default=[])
    quote = subparsers.add_parser("capture-execution-quote")
    quote.add_argument("--candidate-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    result = _cli_freeze(args) if args.command == "freeze" else _cli_quote(args)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
