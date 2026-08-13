from __future__ import annotations

from market_state_observatory.experiments import SCENARIOS
from market_state_observatory.models import ObserverEstimate
from market_state_observatory.next_probe import recommend_next_probe
from market_state_observatory.observer_registry import ObserverRegistry
from market_state_observatory.playbooks import decide
from market_state_observatory.response_modes import infer_response_mode
from market_state_observatory.schemas import load_schema, schema_names
from market_state_observatory.state_certificate import compile_state_certificate
from market_state_observatory.vehicles import vehicle_eligibility


def estimate(observer: str, state: str, *, ready: bool = True) -> ObserverEstimate:
    return ObserverEstimate(
        observer,
        "semiconductors",
        "2026-08-10T19:45:00Z",
        state,
        ready,
        0.2 if ready else None,
        (f"synthetic:{observer}",),
        {},
        "invalidation",
        data_ready=ready,
        model_estimated=ready,
        decision_eligible=ready,
    )


def test_required_schema_set_is_present() -> None:
    required = {
        "observation", "observer_estimate", "evidence_graph", "response_mode",
        "state_certificate", "playbook_decision", "next_probe", "publication_status",
        "rehearsal_summary", "data_shadow_summary", "model_shadow_summary", "theme",
            "validation_result", "experiment", "observer_conflict", "reflexive_memory_entry",
            "public_data_quality", "private_data_quality", "public_themes",
            "public_experiments", "public_roadmap", "public_validation",
    }
    assert set(schema_names()) == required


def test_every_schema_is_draft_2020_12_with_stable_id() -> None:
    for name in schema_names():
        schema = load_schema(name)
        assert schema["$schema"].endswith("draft/2020-12/schema")
        assert schema["$id"] == f"https://yuhanyu0.github.io/market-state-observatory/schemas/{name}.schema.json"


def test_theme_radar_registry_is_unsigned_and_non_gating() -> None:
    registry = ObserverRegistry()
    registry.assert_theme_radar_isolated()
    radar = registry.get("theme_radar_attention")
    assert not radar.signed
    assert not radar.required_for_decision
    assert not radar.may_select_theme
    assert not radar.may_decide_playbook


def test_certificate_has_complete_required_state() -> None:
    rows = [estimate("direction", "positive"), estimate("transmission", "broad_confirmed"), estimate("episode", "onset"), estimate("fragility", "medium"), estimate("theme_radar_attention", "rising")]
    certificate = compile_state_certificate("semiconductors", rows)
    assert certificate["decision_status"] == "MODEL_SHADOW_ONLY"
    assert "observer_agreement" in certificate
    assert "observer_conflicts" in certificate
    assert "next_probe" in certificate


def test_data_ready_is_not_direction() -> None:
    direction = estimate("direction", "unresolved")
    assert direction.data_ready
    assert direction.state == "unresolved"


def test_missing_required_estimate_is_data_blocked() -> None:
    certificate = compile_state_certificate("semiconductors", [estimate("theme_radar_attention", "rising")])
    assert certificate["decision_status"] == "DATA_BLOCKED_NO_DECISION"


def test_next_probe_exposes_information_value_cost_and_deadline() -> None:
    probe = recommend_next_probe("semiconductors", [estimate("theme_radar_attention", "rising"), estimate("direction", "unresolved")])
    assert probe is not None
    assert {"acquire", "distinguishes", "deadline_utc", "expected_information_value", "acquisition_cost", "latency"} <= set(probe)


def test_response_mode_does_not_require_semantic_theme() -> None:
    mode = infer_response_mode("positive", "broad_confirmed", "onset")
    assert mode["mode"] == "broad_positive_propagation"
    assert mode["semantic_theme_required"] is False


def test_torque_requires_qualified_quality() -> None:
    high_beta_only = vehicle_eligibility("positive", "broad_confirmed", "medium", "high-risk")
    qualified = vehicle_eligibility("positive", "broad_confirmed", "medium", "qualified")
    assert not high_beta_only["Torque_Overlay"]
    assert qualified["Torque_Overlay"]


def test_playbook_keeps_previous_state_and_never_creates_order() -> None:
    result = decide("semiconductors", "2026-08-10T19:45:00Z", "A_transition_breakout", "positive", "broad_confirmed", False, "Theme_ETF", "D_wait_unresolved")
    assert result.previous_state == "D_wait_unresolved"
    assert result.decision_status == "MODEL_SHADOW_ONLY"
    assert result.real_order_created is False


def test_synthetic_scenario_count_is_frozen() -> None:
    assert len(SCENARIOS) == 8
