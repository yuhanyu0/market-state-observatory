from __future__ import annotations

from hashlib import sha256
from typing import Any

from .disagreement import detect_conflicts
from .models import ObserverEstimate, StateCertificate
from .next_probe import recommend_next_probe


def _estimate_payload(item: ObserverEstimate | None, default_state: str) -> dict[str, Any]:
    if item is None:
        return {
            "state": default_state,
            "eligible": False,
            "data_ready": False,
            "model_estimated": False,
            "decision_eligible": False,
            "uncertainty": None,
            "evidence_refs": [],
            "metrics": {},
            "invalidation": None,
        }
    return {
        "state": item.state,
        "eligible": item.eligible,
        "data_ready": item.data_ready,
        "model_estimated": item.model_estimated,
        "decision_eligible": item.decision_eligible,
        "uncertainty": item.uncertainty,
        "evidence_refs": list(item.evidence_refs),
        "metrics": item.metrics,
        "invalidation": item.invalidation,
    }


def _agreement(estimates: list[ObserverEstimate], conflict_count: int) -> dict[str, Any]:
    eligible = [item for item in estimates if item.model_estimated]
    denominator = max(len(eligible), 1)
    score = max(0.0, 1.0 - conflict_count / denominator)
    return {
        "score": round(score, 4),
        "estimated_observers": len(eligible),
        "conflict_count": conflict_count,
        "state": "conflicted" if conflict_count else "no_detected_conflict",
    }


def compile_state_certificate(
    theme_id: str,
    estimates: list[ObserverEstimate],
    facts: list[dict[str, Any]] | None = None,
    evidence_grade: str = "synthetic_demo",
) -> dict[str, Any]:
    by_id = {item.observer_id: item for item in estimates}
    direction = by_id.get("direction")
    transmission = by_id.get("transmission")
    episode = by_id.get("episode")
    attention = by_id.get("theme_radar_attention")
    fragility = by_id.get("fragility")
    conflicts = detect_conflicts(estimates)

    direction_state = direction.state if direction else "unresolved"
    transmission_state = transmission.state if transmission else "not_estimable"
    episode_state = episode.state if episode else "not_estimable"
    fragility_state = fragility.state if fragility else "unknown"
    eligible_playbooks: tuple[str, ...]
    vehicles = {"Theme_ETF": False, "Theme_Basket": False, "Torque_Overlay": False}

    def is_ready(item: ObserverEstimate | None) -> bool:
        if item is None:
            return False
        explicit = item.data_ready or item.model_estimated or item.decision_eligible
        return item.data_ready and item.model_estimated if explicit else item.eligible

    required_ready = all(is_ready(item) for item in (direction, transmission, episode, fragility))
    if not required_ready:
        eligible_playbooks = ("D_wait_unresolved",)
        decision_status = "DATA_BLOCKED_NO_DECISION"
    elif direction_state == "unresolved" or transmission_state in {"not_estimable", "absent"}:
        eligible_playbooks = ("D_wait_unresolved",)
        decision_status = "WAIT"
    elif direction_state == "negative" or fragility_state == "blocked":
        eligible_playbooks = ("NoScript",)
        decision_status = "WAIT"
    elif episode_state == "exhaustion":
        eligible_playbooks = ("F_overextended_no_chase",)
        decision_status = "WAIT"
    elif direction_state == "positive" and transmission_state == "broad_confirmed" and episode_state in {"onset", "expansion"}:
        eligible_playbooks = ("A_transition_breakout",)
        vehicles["Theme_ETF"] = True
        vehicles["Theme_Basket"] = True
        decision_status = "MODEL_SHADOW_ONLY"
    elif direction_state == "positive" and transmission_state == "broad_confirmed" and episode_state == "retest":
        eligible_playbooks = ("B_retest_continuation",)
        vehicles["Theme_ETF"] = True
        vehicles["Theme_Basket"] = True
        decision_status = "MODEL_SHADOW_ONLY"
    else:
        eligible_playbooks = ("NoScript",)
        decision_status = "WAIT"

    as_of = max((item.as_of_utc for item in estimates), default="1970-01-01T00:00:00Z")
    identity_input = f"{theme_id}|{as_of}|{evidence_grade}|" + "|".join(
        sorted(f"{item.observer_id}:{item.state}" for item in estimates)
    )
    certificate_id = "certificate-" + sha256(identity_input.encode("utf-8")).hexdigest()[:24]
    invalidation = tuple(item.invalidation for item in estimates if item.invalidation)
    uncertainty_values = [item.uncertainty for item in estimates if item.uncertainty is not None]
    certificate = StateCertificate(
        certificate_id,
        theme_id,
        as_of,
        evidence_grade,
        tuple(facts or []),
        _estimate_payload(direction, "unresolved"),
        _estimate_payload(transmission, "not_estimable"),
        _estimate_payload(episode, "not_estimable"),
        _estimate_payload(attention, "not_available"),
        _estimate_payload(fragility, "unknown"),
        _agreement(estimates, len(conflicts)),
        tuple(conflict.to_dict() for conflict in conflicts),
        max(uncertainty_values) if uncertainty_values else None,
        invalidation,
        recommend_next_probe(theme_id, estimates),
        eligible_playbooks,
        vehicles,
        decision_status,  # type: ignore[arg-type]
    )
    return certificate.to_dict()


build_state_certificate = compile_state_certificate
