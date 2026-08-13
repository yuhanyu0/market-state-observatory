from __future__ import annotations

from .models import ObserverEstimate


def estimate_direction(theme_id: str, as_of_utc: str, relative_return: float | None, confidence: float, evidence_refs: tuple[str, ...] = ()) -> ObserverEstimate:
    data_ready = relative_return is not None
    if relative_return is None or confidence < 0.55:
        state = "unresolved"
    else:
        state = "positive" if relative_return > 0 else "negative"
    return ObserverEstimate("direction", theme_id, as_of_utc, state, data_ready and state != "unresolved", 1.0 - confidence, evidence_refs, {"relative_return": relative_return, "confidence": confidence}, "Relative return or close-period confirmation reverses.", data_ready=data_ready, model_estimated=data_ready, decision_eligible=data_ready and state != "unresolved")
