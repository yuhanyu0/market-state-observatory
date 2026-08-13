from __future__ import annotations

from datetime import UTC, datetime

from .models import NextProbe, ObserverEstimate


def _deadline(estimates: list[ObserverEstimate]) -> str:
    timestamps = sorted(item.as_of_utc for item in estimates)
    return timestamps[-1] if timestamps else datetime.now(UTC).isoformat()


def recommend_next_probe(theme_id: str, estimates: list[ObserverEstimate]) -> dict[str, object] | None:
    by_id = {item.observer_id: item for item in estimates}
    direction = by_id.get("direction")
    transmission = by_id.get("transmission")
    radar = by_id.get("theme_radar_attention")
    episode = by_id.get("episode")
    deadline = _deadline(estimates)

    if radar and radar.state in {"rising", "high", "accelerating"} and (not direction or direction.state == "unresolved"):
        payload = NextProbe(f"{theme_id}-direction-selection", theme_id, "Next point-in-time relative-strength, VWAP, breadth, and close confirmation.", ("positive signed release", "attention without signed release"), deadline, "high", "one scheduled market-data capture", "next frozen observation", "Structural attention is rising without signed confirmation.").to_dict()
        payload["question"] = "Has structural attention selected a signed direction?"
        return payload
    if direction and direction.state == "positive" and transmission and transmission.state == "narrow_only":
        payload = NextProbe(f"{theme_id}-propagation", theme_id, "Rest-of-basket breadth, median residual, volume breadth, and concentration.", ("broad propagation", "single-name impulse"), deadline, "high", "one constituent snapshot", "next frozen observation", "Direction is positive but support is narrow.").to_dict()
        payload["question"] = "Is leadership propagating to the rest of the theme?"
        return payload
    if direction and direction.state == "positive" and episode and episode.state in {"mature", "exhaustion"}:
        payload = NextProbe(f"{theme_id}-retest", theme_id, "Next pullback with Direction persistence and Transmission coherence.", ("orderly retest", "failed extension"), deadline, "medium", "one to three scheduled observations", "before the next playbook transition", "Fresh entry timing is uncertain late in the episode.").to_dict()
        payload["question"] = "Will an orderly retest preserve the positive structure?"
        return payload
    if not direction or not direction.data_ready:
        payload = NextProbe(f"{theme_id}-data-completion", theme_id, "Complete the missing signed-direction point-in-time inputs.", ("estimable direction", "data blocked"), deadline, "high", "missing scheduled data capture", "next legal observation; never backfill", "The current evidence state is not decision-sufficient.").to_dict()
        payload["question"] = "Can the missing point-in-time evidence be acquired legally?"
        return payload
    return None
