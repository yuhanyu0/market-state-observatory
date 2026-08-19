from __future__ import annotations

from typing import Any

PLAYBOOKS = (
    "A_transition_breakout",
    "B_retest_continuation",
    "D_wait_unresolved",
    "F_overextended_no_chase",
    "NoScript",
)
VEHICLES = ("Theme_ETF", "Theme_Basket", "Equal_Risk_Basket", "Torque_Overlay")


def build_playbook_counterfactual(
    *,
    run_id: str,
    theme_id: str,
    as_of_utc: str,
    direction_state: str,
    transmission_state: str,
    episode_state: str,
    fragility_state: str,
    previous_certificate: dict[str, Any] | None = None,
    currently_held_counterfactual: bool = False,
) -> dict[str, Any]:
    confirmed = direction_state == "positive" and transmission_state == "broad_confirmed"
    blocked = fragility_state == "blocked"
    previous_state = previous_certificate.get("decision_status") if previous_certificate else None
    transition = "wait"
    playbook = "D_wait_unresolved"
    reason = "Required candidate evidence is unresolved or blocked."
    invalidation = ["Direction or Transmission remains unresolved", "Fragility remains blocked"]
    if blocked:
        playbook = "NoScript"
        transition = "exit" if currently_held_counterfactual else "wait"
        reason = "Candidate Fragility is blocked."
    elif confirmed and episode_state == "onset":
        playbook = "A_transition_breakout"
        transition = "hold" if currently_held_counterfactual else "entry"
        reason = "Counterfactual candidate Direction and Transmission align at onset."
        invalidation = ["Direction ceases to be positive", "Transmission ceases to be broad"]
    elif confirmed and episode_state == "retest":
        playbook = "B_retest_continuation"
        transition = "hold" if currently_held_counterfactual else "re-entry"
        reason = "Counterfactual retest candidate preserves broad positive coherence."
        invalidation = ["Retest candidate loses Direction or Transmission coherence"]
    elif episode_state in {"mature", "exhaustion"}:
        playbook = "F_overextended_no_chase"
        transition = "reduce" if currently_held_counterfactual else "wait"
        reason = "Counterfactual episode candidate is mature or exhausted."
        invalidation = ["A separately observed retest candidate is required"]

    vehicle_eligibility = {
        "Theme_ETF": confirmed and not blocked,
        "Theme_Basket": confirmed and not blocked,
        "Equal_Risk_Basket": confirmed and not blocked,
        "Torque_Overlay": False,
    }
    return {
        "schema_version": "mso-playbook-counterfactual-v1",
        "counterfactual_id": f"{run_id}:{theme_id}:{playbook}",
        "run_id": run_id,
        "theme_id": theme_id,
        "as_of_utc": as_of_utc,
        "playbook": playbook,
        "previous_certificate_status": previous_state,
        "currently_held_counterfactual": currently_held_counterfactual,
        "state_transition": transition,
        "reason": reason,
        "invalidation": invalidation,
        "vehicle_eligibility_candidate": vehicle_eligibility,
        "torque_disqualification_reason": "Torque overlay has no separately validated qualification artifact.",
        "counterfactual_only": True,
        "model_shadow_authorized": False,
        "paper_positions": 0,
        "real_orders": 0,
    }
