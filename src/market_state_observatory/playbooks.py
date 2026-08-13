from __future__ import annotations

from .models import PlaybookDecision

PLAYBOOKS = {
    "A_transition_breakout",
    "B_retest_continuation",
    "D_wait_unresolved",
    "F_overextended_no_chase",
    "NoScript",
}


def decide(
    theme_id: str,
    as_of_utc: str,
    playbook: str,
    direction: str,
    transmission: str,
    currently_held: bool,
    vehicle: str | None = None,
    previous_state: str | None = None,
    fragility: str = "medium",
) -> PlaybookDecision:
    if playbook not in PLAYBOOKS:
        raise ValueError(f"Unsupported playbook: {playbook}")
    confirmed = direction == "positive" and transmission == "broad_confirmed"
    blocked = fragility == "blocked"

    if blocked:
        action = "EXIT" if currently_held else "WAIT"
        return PlaybookDecision(theme_id, as_of_utc, "NoScript", action, currently_held, False, "Fragility blocks the playbook.", previous_state, vehicle, ("Resolve the blocking fragility input.",), "WAIT")
    if playbook == "A_transition_breakout" and confirmed:
        action = "HOLD" if currently_held else "ENTER"
        return PlaybookDecision(theme_id, as_of_utc, playbook, action, currently_held, True, "Positive Direction and broad Transmission support the transition option.", previous_state, vehicle, ("Direction or Transmission confirmation fails.",), "MODEL_SHADOW_ONLY")
    if playbook == "B_retest_continuation" and confirmed:
        action = "HOLD" if currently_held else "ENTER"
        return PlaybookDecision(theme_id, as_of_utc, playbook, action, currently_held, True, "A qualified retest preserves the positive response state.", previous_state, vehicle, ("The retest loses Direction or broad Transmission.",), "MODEL_SHADOW_ONLY")
    if playbook == "F_overextended_no_chase":
        action = "REDUCE_MODEL_SHADOW" if currently_held else "WAIT"
        return PlaybookDecision(theme_id, as_of_utc, playbook, action, currently_held, False, "The response mode is overextended or exhausted.", previous_state, vehicle, ("A new retest certificate is required.",), "WAIT")
    if currently_held and not confirmed:
        return PlaybookDecision(theme_id, as_of_utc, "NoScript", "EXIT", True, False, "The prior confirmation state no longer holds.", previous_state, vehicle, ("A new decision-sufficient certificate is required.",), "WAIT")
    return PlaybookDecision(theme_id, as_of_utc, "D_wait_unresolved", "WAIT", currently_held, False, "Required Direction and Transmission evidence is unresolved.", previous_state, vehicle, ("Direction and broad Transmission must both confirm.",), "WAIT")
