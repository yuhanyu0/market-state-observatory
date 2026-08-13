from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .observation_freezer import canonical_json, write_exclusive


@dataclass
class RecoveryState:
    trading_date: str
    completed: set[str] = field(default_factory=set)
    missed: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path, trading_date: str) -> RecoveryState:
        if not path.is_file():
            return cls(trading_date=trading_date)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("trading_date") != trading_date:
            return cls(trading_date=trading_date)
        return cls(
            trading_date=trading_date,
            completed=set(payload.get("completed", [])),
            missed=set(payload.get("missed", [])),
        )

    def checkpoint(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"recovery-{self.trading_date}-{datetime.now(UTC).strftime('%H%M%S%f')}.json"
        write_exclusive(
            path,
            canonical_json(
                {
                    "trading_date": self.trading_date,
                    "completed": sorted(self.completed),
                    "missed": sorted(self.missed),
                    "backfill_allowed": False,
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                }
            ),
        )
        return path
