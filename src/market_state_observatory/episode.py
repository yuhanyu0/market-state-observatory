from __future__ import annotations

from .models import ObserverEstimate

VALID_EPISODES = {"onset", "expansion", "retest", "mature", "exhaustion", "reversal"}


def episode_estimate(theme_id: str, as_of_utc: str, state: str | None, history_complete: bool, evidence_refs: tuple[str, ...] = ()) -> ObserverEstimate:
    valid = history_complete and state in VALID_EPISODES
    return ObserverEstimate("episode", theme_id, as_of_utc, state if valid and state is not None else "not_estimable", valid, 0.3 if valid else None, evidence_refs, {"history_complete": history_complete}, "A change point or response-state transition invalidates the current episode.", data_ready=history_complete, model_estimated=valid, decision_eligible=valid)
