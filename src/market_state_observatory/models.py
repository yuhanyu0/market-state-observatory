from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DecisionStatus = Literal[
    "DATA_BLOCKED_NO_DECISION",
    "WAIT",
    "MODEL_SHADOW_ONLY",
]


@dataclass(frozen=True)
class Observation:
    observation_id: str
    dataset_type: str
    ticker: str
    event_time_utc: str
    observed_at_utc: str
    data_max_timestamp: str
    provider: str
    collector_request_id: str
    raw_response_sha256: str
    backfilled: bool = False
    theme_id: str | None = None
    provider_request_id: str | None = None
    data_ready: bool = False
    model_estimated: bool = False
    decision_eligible: bool = False
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObserverEstimate:
    observer_id: str
    theme_id: str
    as_of_utc: str
    state: str
    eligible: bool
    uncertainty: float | None = None
    evidence_refs: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    invalidation: str | None = None
    notes: str | None = None
    data_ready: bool = False
    model_estimated: bool = False
    decision_eligible: bool = False
    source_version: str | None = None
    source_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


@dataclass(frozen=True)
class ObserverConflict:
    theme_id: str
    left: str
    right: str
    kind: str
    explanation: str
    severity: Literal["low", "medium", "high"] = "medium"
    discriminating_probe: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NextProbe:
    probe_id: str
    theme_id: str
    acquire: str
    distinguishes: tuple[str, str]
    deadline_utc: str
    expected_information_value: Literal["low", "medium", "high"]
    acquisition_cost: str
    latency: str
    reason: str
    status: Literal["proposed", "scheduled", "complete", "missed"] = "proposed"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["distinguishes"] = list(self.distinguishes)
        return data


@dataclass(frozen=True)
class PlaybookDecision:
    theme_id: str
    as_of_utc: str
    playbook: str
    action: str
    currently_held: bool
    eligible: bool
    reason: str
    previous_state: str | None = None
    vehicle: str | None = None
    invalidation: tuple[str, ...] = ()
    decision_status: DecisionStatus = "WAIT"
    paper_only: bool = True
    real_order_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["invalidation"] = list(self.invalidation)
        return data


@dataclass(frozen=True)
class StateCertificate:
    certificate_id: str
    theme_id: str
    as_of_utc: str
    evidence_grade: str
    facts: tuple[dict[str, Any], ...]
    direction: dict[str, Any]
    transmission: dict[str, Any]
    episode: dict[str, Any]
    structural_attention: dict[str, Any]
    fragility: dict[str, Any]
    observer_agreement: dict[str, Any]
    observer_conflicts: tuple[dict[str, Any], ...]
    uncertainty: float | None
    invalidation: tuple[str, ...]
    next_probe: dict[str, Any] | None
    eligible_playbooks: tuple[str, ...]
    vehicle_eligibility: dict[str, bool]
    decision_status: DecisionStatus

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["facts"] = list(self.facts)
        data["observer_conflicts"] = list(self.observer_conflicts)
        data["invalidation"] = list(self.invalidation)
        data["eligible_playbooks"] = list(self.eligible_playbooks)
        return data
