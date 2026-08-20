from __future__ import annotations

from datetime import UTC, datetime

from .models import NextProbe, ObserverEstimate

INCIDENT_TYPES = {
    "MISSING_POINT",
    "STALE_PRIMARY_FEED",
    "MEMBERSHIP_UNAVAILABLE",
    "EVENT_PROVENANCE_UNAVAILABLE",
    "INSUFFICIENT_HISTORY",
}


def incident_next_probe(
    theme_id: str,
    incident_type: str,
    deadline_utc: str,
) -> dict[str, object]:
    if incident_type not in INCIDENT_TYPES:
        raise ValueError(f"Unsupported incident probe type: {incident_type}")
    definitions: dict[str, tuple[str, list[str], str]] = {
        "MISSING_POINT": (
            "Will the next preregistered observation point be captured completely and on time?",
            ["next legal scheduled snapshot", "capture manifest", "missing-symbol coverage"],
            "The scheduled point is absent. A past point cannot be reconstructed or backfilled.",
        ),
        "STALE_PRIMARY_FEED": (
            "Will the next preregistered decision snapshot restore fresh primary evidence across the required universe?",
            [
                "next legal 15:45 snapshot",
                "connection-event ledger",
                "first-message-after-reconnect",
                "recovered-symbol coverage",
            ],
            "The point was captured, but primary decision evidence was stale. The past point cannot be reconstructed or backfilled.",
        ),
        "MEMBERSHIP_UNAVAILABLE": (
            "Will the next point-in-time membership snapshot establish the required constituent universe?",
            ["frozen issuer membership", "effective-at timestamps", "constituent coverage"],
            "Transmission cannot be estimated without point-in-time membership; current holdings cannot be used as a historical replacement.",
        ),
        "EVENT_PROVENANCE_UNAVAILABLE": (
            "Will known-at event provenance be available before the next legal observation?",
            ["announcement-known-at timestamp", "event source hash", "affected-symbol coverage"],
            "Event context is unavailable and must not be guessed from an event date.",
        ),
        "INSUFFICIENT_HISTORY": (
            "Will sequential point-in-time history reach the frozen minimum for an episode estimate?",
            ["next legal sequential observation", "history count", "history manifest hashes"],
            "Episode state remains unavailable until the preregistered minimum history is observed.",
        ),
    }
    question, acquire, reason = definitions[incident_type]
    return {
        "probe_id": f"{theme_id}-{incident_type.lower()}",
        "theme_id": theme_id,
        "probe_type": incident_type,
        "question": question,
        "acquire": acquire,
        "distinguishes": ["evidence restored", "evidence remains blocked"],
        "deadline_utc": deadline_utc,
        "expected_information_value": "high",
        "acquisition_cost": "next preregistered point-in-time capture",
        "latency": "next legal observation; never backfill",
        "reason": reason,
        "past_point_reconstruction_allowed": False,
        "status": "proposed",
    }


def _deadline(estimates: list[ObserverEstimate]) -> str:
    timestamps = sorted(item.as_of_utc for item in estimates)
    return timestamps[-1] if timestamps else datetime.now(UTC).isoformat()


def recommend_next_probe(
    theme_id: str,
    estimates: list[ObserverEstimate],
    *,
    incident_type: str | None = None,
) -> dict[str, object] | None:
    by_id = {item.observer_id: item for item in estimates}
    direction = by_id.get("direction")
    transmission = by_id.get("transmission")
    radar = by_id.get("theme_radar_attention")
    episode = by_id.get("episode")
    deadline = _deadline(estimates)

    if incident_type is not None:
        return incident_next_probe(theme_id, incident_type, deadline)

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
        fragility = by_id.get("fragility")
        freshness = (
            fragility.metrics.get("primary_feed_gap")
            if fragility and isinstance(fragility.metrics, dict)
            else None
        )
        kind = (
            "STALE_PRIMARY_FEED"
            if freshness is not None and float(freshness) > 60.0
            else "MISSING_POINT"
        )
        return incident_next_probe(theme_id, kind, deadline)
    return None
