from __future__ import annotations

from typing import Any


def infer_response_mode(direction: str, transmission: str, episode: str) -> dict[str, Any]:
    if direction == "unresolved":
        mode = "unresolved_selection"
    elif direction == "negative" and transmission in {"broad_confirmed", "negative_coherence"}:
        mode = "broad_negative_propagation"
    elif transmission == "narrow_only":
        mode = "localized_impulse"
    elif direction == "positive" and transmission == "broad_confirmed":
        mode = "broad_positive_propagation"
    else:
        mode = "no_coherent_response"
    return {"mode": mode, "direction": direction, "transmission": transmission, "episode": episode, "semantic_theme_required": False}
