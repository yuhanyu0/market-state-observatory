from __future__ import annotations

from .models import ObserverEstimate


def estimate_transmission(theme_id: str, as_of_utc: str, breadth: float | None, concentration: float | None, etf_basket_agree: bool | None, evidence_refs: tuple[str, ...] = ()) -> ObserverEstimate:
    ready = breadth is not None and concentration is not None and etf_basket_agree is not None
    if breadth is None or concentration is None or etf_basket_agree is None:
        state = "absent"
    elif not etf_basket_agree:
        state = "negative_coherence"
    elif breadth >= 0.6 and concentration <= 0.45:
        state = "broad_confirmed"
    elif concentration > 0.45:
        state = "narrow_only"
    else:
        state = "absent"
    return ObserverEstimate("transmission", theme_id, as_of_utc, state, ready and state == "broad_confirmed", None if not ready else 0.25, evidence_refs, {"breadth": breadth, "concentration": concentration, "etf_basket_agree": etf_basket_agree}, "Breadth, volume breadth, or ETF/basket agreement falls below confirmation.", data_ready=ready, model_estimated=ready, decision_eligible=ready and state == "broad_confirmed")
