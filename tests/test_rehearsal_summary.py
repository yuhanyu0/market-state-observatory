import json
from pathlib import Path

from market_state_observatory.validators import validate_payload

ROOT = Path(__file__).resolve().parents[1]

def test_public_day0b_summary_validates():
    payload = json.loads((ROOT / "examples/day0b_public_summary.json").read_text(encoding="utf-8"))
    validate_payload(payload, "rehearsal_summary")
    assert payload["future_timestamp_count"] == 0
    assert payload["backfill_count"] == 0
    assert payload["counts_toward_20_day_gate"] is False
    assert payload["readiness_at_15_45"]["direction_data_ready_themes"] == 6
    assert payload["readiness_at_15_45"]["transmission_data_ready_themes"] == 6

def test_data_ready_is_not_model_state():
    payload = json.loads((ROOT / "examples/day0b_public_summary.json").read_text(encoding="utf-8"))
    assert all("direction_state" not in theme for theme in payload["themes"])
    assert all("transmission_state" not in theme for theme in payload["themes"])
