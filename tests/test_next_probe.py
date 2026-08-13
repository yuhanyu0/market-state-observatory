from market_state_observatory.models import ObserverEstimate
from market_state_observatory.next_probe import recommend_next_probe


def t(observer, state):
    return ObserverEstimate(observer, "quantum", "2026-08-10T19:45:00Z", state, True)

def test_attention_without_direction_requests_sign_probe():
    p = recommend_next_probe("quantum", [t("theme_radar_attention", "rising"), t("direction", "unresolved")])
    assert "sign" in p["question"].lower()

def test_narrow_requests_propagation_probe():
    p = recommend_next_probe("quantum", [t("direction", "positive"), t("transmission", "narrow_only")])
    assert "propag" in p["question"].lower()
