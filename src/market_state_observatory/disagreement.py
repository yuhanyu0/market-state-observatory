from __future__ import annotations

from .models import ObserverConflict, ObserverEstimate


def detect_conflicts(estimates: list[ObserverEstimate]) -> list[ObserverConflict]:
    if not estimates:
        return []
    theme_id = estimates[0].theme_id
    by_id = {item.observer_id: item for item in estimates}
    out: list[ObserverConflict] = []
    direction = by_id.get("direction")
    transmission = by_id.get("transmission")
    radar = by_id.get("theme_radar_attention")
    episode = by_id.get("episode")
    fragility = by_id.get("fragility")

    if radar and radar.state in {"rising", "high", "accelerating"} and direction:
        if direction.state == "negative":
            out.append(ObserverConflict(theme_id, "theme_radar_attention", "direction", "sign_conflict", "Structural attention is rising while signed Direction is negative.", "high", "Capture the next signed relative-return and breadth observation."))
        elif direction.state == "unresolved":
            out.append(ObserverConflict(theme_id, "theme_radar_attention", "direction", "selection_pending", "Structural attention is rising before the market has selected a reliable sign.", "medium", "Observe the next close-period relative-strength confirmation."))

    if direction and direction.state == "positive" and transmission:
        if transmission.state == "narrow_only":
            out.append(ObserverConflict(theme_id, "direction", "transmission", "support_conflict", "Positive tracker direction is concentrated rather than broadly transmitted.", "high", "Measure rest-of-basket breadth and single-name concentration."))
        elif transmission.state == "negative_coherence":
            out.append(ObserverConflict(theme_id, "direction", "transmission", "coherence_conflict", "The tracker is positive while constituent coherence is negative.", "high", "Recheck ETF/basket agreement at the next scheduled observation."))

    if direction and direction.state == "positive" and episode and episode.state == "exhaustion":
        out.append(ObserverConflict(theme_id, "direction", "episode", "timing_conflict", "Direction remains positive but the response mode appears exhausted.", "medium", "Wait for a retest or failed-extension observation."))
    if fragility and fragility.state == "blocked" and direction and direction.state == "positive":
        out.append(ObserverConflict(theme_id, "direction", "fragility", "risk_block", "Positive direction is not decision-sufficient because fragility is blocked.", "high", "Resolve the blocking liquidity, event, or systemic-risk input."))
    return out
