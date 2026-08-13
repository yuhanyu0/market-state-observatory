from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.experiments import run_synthetic_demo
from market_state_observatory.validation import validate_payload

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_demo_is_safe_and_complete(tmp_path: Path) -> None:
    result = run_synthetic_demo(tmp_path)
    assert result["status"] == "PASS"
    assert result["scenario_count"] == 8
    assert result["real_orders_created"] == 0
    assert len(list((tmp_path / "state_certificates").glob("*.json"))) == 8


def test_all_generated_certificates_validate() -> None:
    for path in (ROOT / "examples" / "state_certificates").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_payload(payload, "state_certificate", ROOT)
        assert payload["decision_status"] in {"DATA_BLOCKED_NO_DECISION", "WAIT", "MODEL_SHADOW_ONLY"}


def test_all_public_playbook_examples_have_zero_orders() -> None:
    for path in (ROOT / "examples" / "playbook_decisions").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["real_order_created"] is False
        assert payload["paper_only"] is True


def test_data_blocked_example_is_not_cash_optimal() -> None:
    payload = json.loads((ROOT / "examples" / "state_certificates" / "data_blocked.json").read_text(encoding="utf-8"))
    assert payload["decision_status"] == "DATA_BLOCKED_NO_DECISION"
    assert "CASH_OPTIMAL" not in json.dumps(payload)
