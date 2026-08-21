from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from market_state_observatory.validation import validate_payload


class ModelDispositionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelDispositionRegistry:
    payload: dict[str, Any]
    sha256: str

    @classmethod
    def load(cls, path: Path | None = None) -> ModelDispositionRegistry:
        candidates = (
            path,
            Path(__file__).resolve().parents[3] / "MODEL_DISPOSITION_V1.json",
            Path(sys.prefix).parent / "frozen" / "MODEL_DISPOSITION_V1.json",
        )
        selected = next((candidate for candidate in candidates if candidate and candidate.is_file()), None)
        if selected is None:
            raise FileNotFoundError("MODEL_DISPOSITION_V1.json is unavailable")
        raw = selected.read_bytes()
        payload = json.loads(raw)
        validate_payload(payload, "model_disposition_v1")
        if payload.get("retired_models_may_reactivate_from_config") is not False:
            raise ModelDispositionError("Retired model reactivation lock is missing")
        return cls(payload=payload, sha256=sha256(raw).hexdigest())

    def disposition(self, model_id: str) -> str:
        try:
            return str(self.payload["models"][model_id]["disposition"])
        except KeyError as error:
            raise ModelDispositionError(f"Unknown model disposition: {model_id}") from error

    def assert_not_reactivated(self, model_id: str, requested_active: bool) -> None:
        row = self.payload.get("models", {}).get(model_id)
        if not isinstance(row, dict):
            raise ModelDispositionError(f"Unknown model disposition: {model_id}")
        disposition = str(row.get("disposition", ""))
        if requested_active and (
            disposition.startswith("RETIRED")
            or row.get("production_activation_allowed") is not True
        ):
            raise ModelDispositionError(
                f"Model activation rejected by frozen disposition registry: {model_id}={disposition}"
            )
