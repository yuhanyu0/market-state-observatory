from market_state_observatory.disagreement import detect_conflicts
from market_state_observatory.models import ObserverEstimate


def t(observer, state):
    return ObserverEstimate(observer, "semiconductors", "2026-08-10T19:45:00Z", state, True)

def test_attention_negative_conflict():
    conflicts = detect_conflicts([t("theme_radar_attention", "rising"), t("direction", "negative")])
    assert any(c.kind == "sign_conflict" for c in conflicts)

def test_positive_narrow_conflict():
    conflicts = detect_conflicts([t("direction", "positive"), t("transmission", "narrow_only")])
    assert any(c.kind == "support_conflict" for c in conflicts)
