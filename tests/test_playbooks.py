from market_state_observatory.playbooks import decide


def test_a_enters():
    d = decide("semiconductors", "2026-08-10T19:45:00Z", "A_transition_breakout", "positive", "broad_confirmed", False, "SMH")
    assert d.action == "ENTER"
    assert d.real_order_created is False

def test_unconfirmed_held_exits():
    d = decide("semiconductors", "2026-08-10T19:45:00Z", "NoScript", "negative", "negative_coherence", True, "SMH")
    assert d.action == "EXIT"
