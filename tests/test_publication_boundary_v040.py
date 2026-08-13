from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_state_observatory.publication import write_public_json
from market_state_observatory.redaction import validate_already_redacted
from market_state_observatory.security import audit_public_tree

ROOT = Path(__file__).resolve().parents[1]


def experiment() -> dict[str, object]:
    return {
        "experiment_id": "synthetic-safe",
        "title": "Safe",
        "evidence_grade": "synthetic_demo",
        "hypothesis": "Boundary test",
        "frozen_before_results": True,
        "status": "REFERENCE_DEMO",
        "counts_toward_strategy_evidence": False,
        "real_orders_allowed": False,
    }


def test_public_writer_allows_only_public_data(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only below public/data"):
        write_public_json(experiment(), "experiment", tmp_path / "elsewhere" / "item.json", tmp_path)


def test_public_writer_validates_before_write(tmp_path: Path) -> None:
    destination = tmp_path / "public" / "data" / "item.json"
    write_public_json(experiment(), "experiment", destination, tmp_path)
    assert destination.is_file()


def test_redacted_import_rejects_account_field() -> None:
    key = "account_" + "number"
    payload = {key: "123"}
    with pytest.raises(ValueError, match="forbidden field"):
        validate_already_redacted(payload)


def test_redacted_import_rejects_secret_assignment() -> None:
    name = "APCA_API_" + "SECRET_KEY"
    with pytest.raises(ValueError, match="Publication rejected"):
        validate_already_redacted({"note": f"{name}=not-a-real-secret"})


def test_public_trees_are_safe() -> None:
    for relative in ("public", "examples"):
        assert audit_public_tree(ROOT / relative) == []


def test_day0b_public_summary_has_required_boundaries() -> None:
    payload = json.loads((ROOT / "public" / "data" / "experiments" / "day0b-2026-08-10.json").read_text(encoding="utf-8"))
    assert payload["captured_valid_records"] == 666
    assert payload["counts_toward_20_day_gate"] is False
    assert payload["credential_values_persisted"] is False
    assert payload["readiness_at_15_45"]["episode_ready_themes"] == 0
    assert payload["readiness_at_15_45"]["c2_ready_themes"] == 0
