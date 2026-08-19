from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from market_state_observatory.models import ObserverEstimate

from .feature_compiler import feature_index

DIRECTION_ARMS = (
    "D0_SIMPLE_RELATIVE",
    "D1_TRANSPARENT_MULTI_FEATURE",
    "D2_CALIBRATED_PROBABILISTIC",
)
EPISODE_STATES = {"onset", "expansion", "retest", "mature", "exhaustion", "reversal", "not_estimable"}


class EpisodeCandidatePlugin(Protocol):
    arm: str
    minimum_history: int

    def estimate(self, history: list[EpisodeObservation]) -> tuple[str, float, dict[str, float]]: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _config(name: str) -> tuple[dict[str, Any], str]:
    candidates = (
        _repo_root() / "config" / "candidates" / name,
        Path(sys.prefix).parent / "config" / "candidates" / name,
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    raw = path.read_bytes()
    return json.loads(raw), sha256(raw).hexdigest()


def _value(index: dict[tuple[str, str, str], dict[str, Any]], theme: str, point: str, feature: str) -> Any:
    row = index.get((theme, point, feature))
    return row.get("value") if row and row.get("availability_status") == "AVAILABLE" else None


def _candidate_state(score: float | None, negative: float, positive: float) -> str:
    if score is None:
        return "unresolved"
    if score >= positive:
        return "positive"
    if score <= negative:
        return "negative"
    return "unresolved"


def _decision_input_readiness(
    index: dict[tuple[str, str, str], dict[str, Any]], theme_id: str
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    freshness = _value(index, theme_id, "decision_snapshot", "primary_feed_gap")
    if freshness is None:
        blockers.append("decision_primary_quote_freshness_missing")
    elif float(freshness) > 60.0:
        blockers.append("decision_primary_quote_freshness_above_60_seconds")
    for feature in (
        "relative_to_spy_return",
        "relative_to_industry_return",
        "basket_median_return",
        "constituent_positive_breadth",
        "vwap_distance",
        "range_position",
    ):
        if _value(index, theme_id, "decision_snapshot", feature) is None:
            blockers.append(f"{feature}_missing")
    return not blockers, blockers


def build_direction_candidates(features: dict[str, Any], theme_id: str) -> list[dict[str, Any]]:
    index = feature_index(features)
    ready, blockers = _decision_input_readiness(index, theme_id)
    as_of = index[(theme_id, "decision_snapshot", "event_time_dispersion")]["observed_at_utc"]
    values = {
        name: _value(index, theme_id, "decision_snapshot", name)
        for name in (
            "relative_to_spy_return",
            "relative_to_industry_return",
            "basket_median_return",
            "constituent_positive_breadth",
            "vwap_distance",
            "range_position",
            "preclose_decision_confirmation",
        )
    }
    outputs: list[dict[str, Any]] = []
    configs = (
        _config("direction_d0_v1.json"),
        _config("direction_d1_v1.json"),
        _config("direction_d2_v1.json"),
    )
    for config, digest in configs:
        arm = str(config["arm"])
        score: float | None = None
        probability: float | None = None
        if ready:
            if arm == "D0_SIMPLE_RELATIVE":
                score = float(values["relative_to_spy_return"])
            else:
                weights = configs[1][0]["weights"]
                breadth_centered = float(values["constituent_positive_breadth"]) - 0.5
                confirmation = 1.0 if values["preclose_decision_confirmation"] else -1.0
                score = (
                    float(values["relative_to_spy_return"]) * float(weights["relative_to_spy_return"])
                    + float(values["relative_to_industry_return"]) * float(weights["relative_to_industry_return"])
                    + float(values["basket_median_return"]) * float(weights["basket_median_return"])
                    + breadth_centered * float(weights["constituent_positive_breadth_centered"])
                    + float(values["vwap_distance"]) * float(weights["vwap_distance"])
                    + confirmation * float(weights["preclose_decision_confirmation"])
                )
                if arm == "D2_CALIBRATED_PROBABILISTIC":
                    probability = 1.0 / (1.0 + math.exp(-score * 200.0))
        negative = float(config.get("negative_threshold", configs[1][0]["negative_threshold"]))
        positive = float(config.get("positive_threshold", configs[1][0]["positive_threshold"]))
        state = _candidate_state(score, negative, positive)
        outputs.append(
            {
                "schema_version": "mso-direction-candidate-v1",
                "candidate_id": f"{features['run_id']}:{theme_id}:{arm}",
                "arm": arm,
                "config_version": config["version"],
                "config_sha256": digest,
                "theme_id": theme_id,
                "as_of_utc": as_of,
                "candidate_state": state,
                "calibration_status": config["calibration_status"],
                "data_ready": ready,
                "candidate_estimated": ready,
                "validated_model": False,
                "decision_eligible": False,
                "score": score,
                "probability_positive": probability,
                "uncertainty": None if not ready else (0.5 if arm == "D2_CALIBRATED_PROBABILISTIC" else 0.35),
                "inputs": values,
                "blocking_reasons": blockers,
                "invalidation": ["decision quote freshness exceeds 60 seconds", "required point-in-time input becomes unavailable"],
                "evidence_grade": "retrospective_unvalidated",
            }
        )
    return outputs


def build_transmission_candidate(features: dict[str, Any], theme_id: str) -> dict[str, Any]:
    config, digest = _config("transmission_t0_v1.json")
    index = feature_index(features)
    direction_ready, blockers = _decision_input_readiness(index, theme_id)
    names = (
        "etf_basket_agreement",
        "residual_breadth",
        "basket_median_return",
        "volume_breadth",
        "leader_rest_gap",
        "single_name_concentration",
        "return_dispersion",
    )
    inputs = {name: _value(index, theme_id, "decision_snapshot", name) for name in names}
    missing = [name for name, value in inputs.items() if value is None]
    blockers.extend(f"{name}_missing" for name in missing)
    input_ready = direction_ready and not missing
    state = "not_estimable"
    if input_ready:
        agreement = bool(inputs["etf_basket_agreement"])
        residual_breadth = float(inputs["residual_breadth"])
        concentration = float(inputs["single_name_concentration"])
        median_response = float(inputs["basket_median_return"])
        if not agreement or median_response == 0:
            state = "negative_coherence"
        elif residual_breadth >= float(config["broad_breadth_minimum"]) and concentration <= float(config["concentration_maximum"]):
            state = "broad_confirmed"
        elif concentration > float(config["concentration_maximum"]):
            state = "narrow_only"
        else:
            state = "absent"
    dispersion = inputs.get("return_dispersion")
    agreement_value = inputs.get("etf_basket_agreement")
    inputs["leader_to_rest_propagation"] = None if inputs.get("leader_rest_gap") is None else -abs(float(inputs["leader_rest_gap"]))
    inputs["dynamic_coherence"] = (
        None
        if dispersion is None or agreement_value is None
        else (1.0 if bool(agreement_value) else -1.0) * max(0.0, 1.0 - min(1.0, float(dispersion) / 0.05))
    )
    inputs["negative_coherence"] = state == "negative_coherence"
    as_of = index[(theme_id, "decision_snapshot", "event_time_dispersion")]["observed_at_utc"]
    return {
        "schema_version": "mso-transmission-candidate-v1",
        "candidate_id": f"{features['run_id']}:{theme_id}:T0_TRANSPARENT_TRANSMISSION",
        "arm": "T0_TRANSPARENT_TRANSMISSION",
        "config_version": config["version"],
        "config_sha256": digest,
        "theme_id": theme_id,
        "as_of_utc": as_of,
        "transmission_input_readiness": input_ready,
        "candidate_transmission_state": state,
        "validated_transmission_state": None,
        "candidate_estimated": input_ready,
        "validated_model": False,
        "decision_eligible": False,
        "inputs": inputs,
        "blocking_reasons": sorted(set(blockers)),
        "uncertainty": None if not input_ready else 0.35,
        "invalidation": ["ETF/basket coherence reverses", "breadth or concentration leaves the frozen candidate band"],
        "evidence_grade": "retrospective_unvalidated",
    }


@dataclass(frozen=True)
class EpisodeObservation:
    as_of_utc: str
    relative_return: float
    breadth: float
    confirmation: bool


def _e0_state(history: list[EpisodeObservation]) -> tuple[str, dict[str, float]]:
    latest = history[-1]
    previous = history[-2]
    if latest.relative_return < 0 and previous.relative_return > 0:
        state = "reversal"
    elif latest.relative_return > 0 and previous.relative_return <= 0:
        state = "onset"
    elif latest.relative_return > previous.relative_return and latest.breadth >= 0.6:
        state = "expansion"
    elif latest.relative_return > 0 and latest.relative_return < previous.relative_return and latest.confirmation:
        state = "retest"
    elif latest.relative_return > 0 and latest.breadth < 0.4:
        state = "exhaustion"
    else:
        state = "mature"
    return state, {state: 0.65, "not_estimable": 0.35}


def _normal_density(value: float, center: float, variance: float) -> float:
    safe_variance = max(variance, 1e-8)
    return math.exp(-((value - center) ** 2) / (2 * safe_variance)) / math.sqrt(2 * math.pi * safe_variance)


def _bocpd(history: list[EpisodeObservation], hazard: float) -> tuple[str, dict[str, float]]:
    """Gaussian BOCPD candidate using only observations available in sequence."""
    values = [row.relative_return for row in history]
    center = sum(values) / len(values)
    empirical_variance = max(1e-6, sum((value - center) ** 2 for value in values) / len(values))
    run_probabilities = [1.0]
    seen: list[float] = []
    for value in values:
        prior_predictive = _normal_density(value, 0.0, empirical_variance * 4)
        growth: list[float] = []
        for run_length, probability in enumerate(run_probabilities):
            segment = seen[-run_length:] if run_length else []
            segment_center = sum(segment) / len(segment) if segment else 0.0
            predictive = _normal_density(
                value,
                segment_center,
                empirical_variance * (1.0 + 1.0 / (len(segment) + 1)),
            )
            growth.append(probability * (1.0 - hazard) * predictive)
        change = sum(run_probabilities) * hazard * prior_predictive
        updated = [change, *growth]
        normalizer = sum(updated)
        run_probabilities = [probability / normalizer for probability in updated]
        seen.append(value)
    change_probability = run_probabilities[0]
    latest = history[-1]
    if change_probability >= 0.35:
        state = "onset" if latest.relative_return >= 0 else "reversal"
    elif latest.relative_return > 0 and latest.breadth >= 0.6:
        state = "expansion"
    elif latest.relative_return < 0 and latest.breadth >= 0.5:
        state = "retest"
    elif latest.relative_return > 0 and latest.breadth < 0.4:
        state = "exhaustion"
    else:
        state = "mature"
    return state, {"change_point": change_probability, "continuation": 1.0 - change_probability}


def build_episode_candidates(theme_id: str, history: Iterable[EpisodeObservation], as_of_utc: str) -> list[dict[str, Any]]:
    rows = sorted(history, key=lambda row: row.as_of_utc)
    outputs: list[dict[str, Any]] = []
    for name, config_name in (
        ("E0_INTERPRETABLE_STATE_MACHINE", "episode_e0_v1.json"),
        ("E1_BOCPD_CANDIDATE", "episode_e1_v1.json"),
    ):
        config, digest = _config(config_name)
        minimum = int(config["minimum_history"])
        estimable = len(rows) >= minimum
        state = "not_estimable"
        transitions: dict[str, float] = {}
        if estimable and name == "E0_INTERPRETABLE_STATE_MACHINE":
            state, transitions = _e0_state(rows)
        elif estimable:
            state, transitions = _bocpd(rows, float(config["hazard_probability"]))
        outputs.append(
            {
                "schema_version": "mso-episode-candidate-v1",
                "candidate_id": f"{theme_id}:{as_of_utc}:{name}",
                "arm": name,
                "config_version": config["version"],
                "config_sha256": digest,
                "theme_id": theme_id,
                "as_of_utc": as_of_utc,
                "history_observations": len(rows),
                "minimum_history": minimum,
                "sequential_only": True,
                "state": state,
                "candidate_estimated": estimable,
                "validated_model": False,
                "decision_eligible": False,
                "uncertainty": None if not estimable else 0.4,
                "transition_probabilities": transitions,
                "invalidation": ["a later sequential observation changes the candidate state"],
                "blocking_reasons": [] if estimable else [f"minimum_history_{minimum}_not_met"],
                "evidence_grade": "retrospective_unvalidated",
            }
        )
    outputs.append(
        {
            "schema_version": "mso-episode-candidate-v1",
            "candidate_id": f"{theme_id}:{as_of_utc}:E2_HSMM_CANDIDATE",
            "arm": "E2_HSMM_CANDIDATE",
            "config_version": "episode-e2-plugin-v1",
            "config_sha256": sha256(b"episode-e2-plugin-v1").hexdigest(),
            "theme_id": theme_id,
            "as_of_utc": as_of_utc,
            "history_observations": len(rows),
            "minimum_history": 60,
            "sequential_only": True,
            "state": "not_estimable",
            "candidate_estimated": False,
            "validated_model": False,
            "decision_eligible": False,
            "uncertainty": None,
            "transition_probabilities": {},
            "invalidation": ["plugin remains disabled until separately registered and validated"],
            "blocking_reasons": ["plugin_not_registered"],
            "evidence_grade": "retrospective_unvalidated",
        }
    )
    return outputs


def candidate_observer_estimates(
    directions: list[dict[str, Any]],
    transmission: dict[str, Any],
    episodes: list[dict[str, Any]],
    fragility: dict[str, Any],
) -> list[ObserverEstimate]:
    direction = next(row for row in directions if row["arm"] == "D1_TRANSPARENT_MULTI_FEATURE")
    episode = next(row for row in episodes if row["arm"] == "E0_INTERPRETABLE_STATE_MACHINE")
    theme_id = str(direction["theme_id"])
    as_of = str(direction["as_of_utc"])
    return [
        ObserverEstimate("direction", theme_id, as_of, str(direction["candidate_state"]), bool(direction["candidate_estimated"]), direction["uncertainty"], tuple(), direction["inputs"], "Candidate Direction input invalidates.", data_ready=bool(direction["data_ready"]), model_estimated=bool(direction["candidate_estimated"]), decision_eligible=False, source_version=str(direction["config_version"]), source_sha256=str(direction["config_sha256"])),
        ObserverEstimate("transmission", theme_id, as_of, str(transmission["candidate_transmission_state"]), bool(transmission["candidate_estimated"]), transmission["uncertainty"], tuple(), transmission["inputs"], "Candidate Transmission input invalidates.", data_ready=bool(transmission["transmission_input_readiness"]), model_estimated=bool(transmission["candidate_estimated"]), decision_eligible=False, source_version=str(transmission["config_version"]), source_sha256=str(transmission["config_sha256"])),
        ObserverEstimate("episode", theme_id, as_of, str(episode["state"]), bool(episode["candidate_estimated"]), episode["uncertainty"], tuple(), {"history_observations": episode["history_observations"]}, "Sequential state changes.", data_ready=bool(episode["candidate_estimated"]), model_estimated=bool(episode["candidate_estimated"]), decision_eligible=False, source_version=str(episode["config_version"]), source_sha256=str(episode["config_sha256"])),
        ObserverEstimate("theme_radar_attention", theme_id, as_of, "not_available", False, None, tuple(), {}, "External benchmark is isolated.", data_ready=False, model_estimated=False, decision_eligible=False, source_version="isolated-benchmark-v1"),
        ObserverEstimate("fragility", theme_id, as_of, str(fragility["state"]), True, float(fragility["uncertainty"]), tuple(), fragility["inputs"], "Fragility inputs change.", data_ready=True, model_estimated=True, decision_eligible=False, source_version="fragility-candidate-v1"),
        ObserverEstimate("event", theme_id, as_of, "unavailable", False, None, tuple(), {}, "Known-at event provenance becomes available.", data_ready=False, model_estimated=False, decision_eligible=False, source_version="event-context-v1"),
    ]


def build_fragility_candidate(features: dict[str, Any], theme_id: str) -> dict[str, Any]:
    index = feature_index(features)
    inputs = {
        name: _value(index, theme_id, "decision_snapshot", name)
        for name in ("spread_percent", "single_name_concentration", "return_dispersion", "primary_feed_gap", "relative_to_spy_return")
    }
    freshness = inputs["primary_feed_gap"]
    if freshness is None or float(freshness) > 60:
        state = "blocked"
    elif float(inputs.get("single_name_concentration") or 0) > 0.55 or float(inputs.get("spread_percent") or 0) > 0.005:
        state = "high"
    elif float(inputs.get("return_dispersion") or 0) > 0.02:
        state = "medium"
    else:
        state = "low"
    return {
        "state": state,
        "uncertainty": 0.4,
        "inputs": inputs,
        "scheduled_event_provenance": "unavailable",
        "torque_overlay_qualified": False,
    }
