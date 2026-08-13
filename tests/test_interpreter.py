from market_state_observatory.interpreter import build_state_certificate
from market_state_observatory.models import ObserverEstimate


def e(observer, state, eligible=True):
    return ObserverEstimate(observer, "semiconductors", "2026-08-10T19:45:00Z", state, eligible)


def test_unresolved_waits():
    c = build_state_certificate("semiconductors", [e("direction", "unresolved", False), e("transmission", "not_estimable", False)])
    assert c["decision_status"] in {"WAIT", "DATA_BLOCKED_NO_DECISION"}
    assert "D_wait_unresolved" in c["eligible_playbooks"]


def test_positive_broad_onset_is_model_shadow_only():
    c = build_state_certificate("semiconductors", [e("direction", "positive"), e("transmission", "broad_confirmed"), e("episode", "onset"), e("fragility", "medium")])
    assert c["decision_status"] == "MODEL_SHADOW_ONLY"
    assert c["vehicle_eligibility"]["Theme_ETF"] is True
    assert "A_transition_breakout" in c["eligible_playbooks"]


def test_negative_never_enters():
    c = build_state_certificate("semiconductors", [e("direction", "negative"), e("transmission", "broad_confirmed"), e("episode", "onset"), e("fragility", "medium")])
    assert c["vehicle_eligibility"]["Theme_ETF"] is False
