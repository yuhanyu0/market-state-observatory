from __future__ import annotations

from datetime import date
from typing import Any

from .market_calendar import next_trading_day

SETTLEMENT_POINTS = {
    "open_snapshot": "next_open",
    "next_10_00": "next_10_00",
    "decision_snapshot": "next_15_45",
}


def settlement_link(observation_point: str, current_date: date) -> dict[str, Any] | None:
    label = SETTLEMENT_POINTS.get(observation_point)
    if label is None:
        return None
    candidate = current_date
    for _ in range(10):
        candidate = candidate.fromordinal(candidate.toordinal() - 1)
        if next_trading_day(candidate) == current_date:
            return {
                "settlement_label": label,
                "source_observation_date": candidate.isoformat(),
                "settled_on_date": current_date.isoformat(),
                "point_in_time": True,
            }
    return None
