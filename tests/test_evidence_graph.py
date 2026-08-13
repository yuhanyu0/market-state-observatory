from market_state_observatory.evidence_graph import build_evidence_graph
from market_state_observatory.models import ObserverEstimate


def test_graph_preserves_evidence_and_conflict():
    rows = [
        ObserverEstimate("theme_radar_attention", "semiconductors", "2026-08-10T19:45:00Z", "rising", True, evidence_refs=("radar:1",)),
        ObserverEstimate("direction", "semiconductors", "2026-08-10T19:45:00Z", "negative", True, evidence_refs=("price:1",)),
    ]
    g = build_evidence_graph(rows)
    assert len(g["nodes"]) >= 4
    assert any(e["relation"] == "contradicts" for e in g["edges"])
