from __future__ import annotations

from typing import Any


def vehicle_eligibility(
    direction: str,
    transmission: str,
    fragility: str,
    torque_quality: str = "insufficient_history",
) -> dict[str, Any]:
    theme_ready = direction == "positive" and transmission == "broad_confirmed" and fragility != "blocked"
    overlay_ready = theme_ready and torque_quality == "qualified"
    return {
        "Cash": True,
        "Theme_ETF": theme_ready,
        "Theme_Basket": theme_ready,
        "Torque_Overlay": overlay_ready,
        "execution_scope": "MODEL_SHADOW_ONLY" if theme_ready else "WAIT",
        "real_orders_allowed": False,
    }
