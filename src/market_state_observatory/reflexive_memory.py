from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReflexiveMemoryEntry:
    entry_id: str
    certificate_id: str
    recorded_at_utc: str
    prior_state: str
    observed_outcome: str
    invalidation_triggered: bool
    lesson: str
    may_change_core_contract: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
