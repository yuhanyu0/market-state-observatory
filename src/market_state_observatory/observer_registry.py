from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObserverDefinition:
    observer_id: str
    layer: str
    signed: bool
    required_for_decision: bool
    may_select_theme: bool
    may_decide_playbook: bool
    description: str


DEFAULT_OBSERVERS: tuple[ObserverDefinition, ...] = (
    ObserverDefinition("direction", "Direction", True, True, False, False, "Estimates signed market-relative release direction."),
    ObserverDefinition("transmission", "Transmission", False, True, False, False, "Tests whether a move propagates across the theme."),
    ObserverDefinition("episode", "Episode", False, True, False, False, "Locates onset, expansion, retest, maturity, exhaustion, or reversal."),
    ObserverDefinition("theme_radar_attention", "Structural attention", False, False, False, False, "External structural-attention observer; never a direction or action gate."),
    ObserverDefinition("fragility", "Fragility", False, True, False, False, "Summarizes liquidity, concentration, event, gap, volatility, and systemic risk."),
    ObserverDefinition("event", "Event", False, False, False, False, "Optional known-at event context; disabled when provenance is incomplete."),
)


class ObserverRegistry:
    def __init__(self, definitions: tuple[ObserverDefinition, ...] = DEFAULT_OBSERVERS):
        self._definitions = {definition.observer_id: definition for definition in definitions}

    def get(self, observer_id: str) -> ObserverDefinition:
        try:
            return self._definitions[observer_id]
        except KeyError as error:
            raise KeyError(f"Unknown observer: {observer_id}") from error

    def all(self) -> tuple[ObserverDefinition, ...]:
        return tuple(self._definitions.values())

    def assert_theme_radar_isolated(self) -> None:
        radar = self.get("theme_radar_attention")
        if radar.signed or radar.required_for_decision or radar.may_select_theme or radar.may_decide_playbook:
            raise RuntimeError("Theme Radar observer isolation contract was violated")
