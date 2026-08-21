from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any


class ExecutionMode(StrEnum):
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    CANDIDATE_REPLAY = "CANDIDATE_REPLAY"
    PROSPECTIVE_CANDIDATE_SHADOW = "PROSPECTIVE_CANDIDATE_SHADOW"
    MODEL_SHADOW = "MODEL_SHADOW"
    PAPER_LIVE = "PAPER_LIVE"


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModeAuthorization:
    mode: ExecutionMode
    may_read_completed_runs: bool
    may_run_candidates: bool
    may_run_validated_models: bool
    may_emit_actions: bool
    paper_positions_allowed: bool
    real_orders_allowed: bool
    evidence_grade: str
    promotion_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "may_read_completed_runs": self.may_read_completed_runs,
            "may_run_candidates": self.may_run_candidates,
            "may_run_validated_models": self.may_run_validated_models,
            "may_emit_actions": self.may_emit_actions,
            "paper_positions_allowed": self.paper_positions_allowed,
            "real_orders_allowed": self.real_orders_allowed,
            "evidence_grade": self.evidence_grade,
            "promotion_sha256": self.promotion_sha256,
        }


def _load_model_shadow_promotion(path: Path | None) -> tuple[dict[str, Any], str]:
    if path is None or not path.is_file():
        raise AuthorizationError("MODEL_SHADOW requires an explicit promotion artifact")
    raw = path.read_bytes()
    payload = json.loads(raw)
    required = {
        "schema_version": "mso-model-shadow-promotion-v1",
        "authorization": "APPROVED",
        "target_mode": "MODEL_SHADOW",
        "paper_only": True,
        "real_orders_allowed": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise AuthorizationError(f"MODEL_SHADOW promotion rejected: {key}")
    return payload, sha256(raw).hexdigest()


def authorize_mode(
    mode: ExecutionMode | str,
    *,
    promotion_artifact: Path | None = None,
) -> ModeAuthorization:
    selected = ExecutionMode(mode)
    if selected is ExecutionMode.OBSERVATION_ONLY:
        return ModeAuthorization(selected, True, False, False, False, False, False, "observed_descriptive")
    if selected is ExecutionMode.CANDIDATE_REPLAY:
        return ModeAuthorization(
            selected,
            True,
            True,
            False,
            False,
            False,
            False,
            "retrospective_unvalidated",
        )
    if selected is ExecutionMode.PROSPECTIVE_CANDIDATE_SHADOW:
        return ModeAuthorization(
            selected,
            True,
            True,
            False,
            False,
            False,
            False,
            "prospective_unvalidated",
        )
    if selected is ExecutionMode.MODEL_SHADOW:
        _, digest = _load_model_shadow_promotion(promotion_artifact)
        return ModeAuthorization(
            selected,
            True,
            True,
            True,
            True,
            True,
            False,
            "prospective_model_shadow",
            digest,
        )
    raise AuthorizationError("PAPER/LIVE is unavailable in this product release")
