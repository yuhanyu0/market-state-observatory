from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence_graph import build_evidence_graph
from .models import ObserverEstimate
from .playbooks import decide
from .response_modes import infer_response_mode
from .state_certificate import compile_state_certificate

SCENARIOS: tuple[dict[str, str], ...] = (
    {"id": "positive_broad_onset", "direction": "positive", "transmission": "broad_confirmed", "episode": "onset", "attention": "rising", "fragility": "medium"},
    {"id": "attention_rising_direction_unresolved", "direction": "unresolved", "transmission": "absent", "episode": "not_estimable", "attention": "rising", "fragility": "medium"},
    {"id": "positive_narrow", "direction": "positive", "transmission": "narrow_only", "episode": "expansion", "attention": "high", "fragility": "high"},
    {"id": "negative_broad_propagation", "direction": "negative", "transmission": "broad_confirmed", "episode": "reversal", "attention": "high", "fragility": "high"},
    {"id": "positive_exhausted", "direction": "positive", "transmission": "broad_confirmed", "episode": "exhaustion", "attention": "high", "fragility": "high"},
    {"id": "retest_continuation", "direction": "positive", "transmission": "broad_confirmed", "episode": "retest", "attention": "persistent", "fragility": "medium"},
    {"id": "data_blocked", "direction": "unresolved", "transmission": "not_estimable", "episode": "not_estimable", "attention": "not_available", "fragility": "unknown"},
    {"id": "observer_conflict_next_probe", "direction": "negative", "transmission": "negative_coherence", "episode": "mature", "attention": "accelerating", "fragility": "medium"},
)


def _estimates(scenario: dict[str, str]) -> list[ObserverEstimate]:
    blocked = scenario["id"] == "data_blocked"
    as_of = "2026-08-10T19:45:00Z"
    rows = []
    for observer, key in (("direction", "direction"), ("transmission", "transmission"), ("episode", "episode"), ("theme_radar_attention", "attention"), ("fragility", "fragility")):
        estimable = not blocked or observer == "theme_radar_attention"
        rows.append(ObserverEstimate(observer, "semiconductors", as_of, scenario[key], estimable, 0.2 if estimable else None, (f"synthetic:{scenario['id']}:{observer}",), {}, "Synthetic invalidation condition.", data_ready=estimable, model_estimated=estimable, decision_eligible=estimable and observer != "theme_radar_attention"))
    return rows


def run_synthetic_demo(output_root: Path | None = None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        estimates = _estimates(scenario)
        certificate = compile_state_certificate("semiconductors", estimates, [{"kind": "synthetic", "text": scenario["id"]}], "synthetic_demo")
        if certificate["decision_status"] not in {"WAIT", "MODEL_SHADOW_ONLY", "DATA_BLOCKED_NO_DECISION"}:
            raise RuntimeError("Synthetic demo crossed the allowed research-state boundary")
        graph = build_evidence_graph(estimates)
        response_mode = infer_response_mode(scenario["direction"], scenario["transmission"], scenario["episode"])
        playbook = certificate["eligible_playbooks"][0]
        decision = decide("semiconductors", "2026-08-10T19:45:00Z", playbook, scenario["direction"], scenario["transmission"], False, "Theme_ETF", None, scenario["fragility"]).to_dict()
        observation = {
            "observation_id": f"synthetic-{scenario['id']}",
            "dataset_type": "synthetic_reference_state",
            "ticker": "SYNTH",
            "theme_id": "semiconductors",
            "event_time_utc": "2026-08-10T19:45:00Z",
            "observed_at_utc": "2026-08-10T19:45:01Z",
            "data_max_timestamp": "2026-08-10T19:45:00Z",
            "provider": "synthetic_reference_demo",
            "collector_request_id": f"synthetic-{scenario['id']}",
            "provider_request_id": None,
            "raw_response_sha256": "0" * 64,
            "backfilled": False,
            "data_ready": scenario["id"] != "data_blocked",
            "model_estimated": False,
            "decision_eligible": False,
            "values": {"scenario": scenario["id"]},
        }
        experiment = {
            "experiment_id": f"synthetic-{scenario['id']}",
            "title": scenario["id"].replace("_", " ").title(),
            "evidence_grade": "synthetic_demo",
            "hypothesis": "The structured evidence pipeline preserves uncertainty and action boundaries.",
            "frozen_before_results": True,
            "status": "REFERENCE_DEMO",
            "counts_toward_strategy_evidence": False,
            "real_orders_allowed": False,
        }
        results.append({"scenario": scenario, "observation": observation, "estimates": [item.to_dict() for item in estimates], "graph": graph, "response_mode": response_mode, "certificate": certificate, "decision": decision, "experiment": experiment})
        if output_root is not None:
            for directory in ("observations", "observer_estimates", "evidence_graphs", "response_modes", "state_certificates", "playbook_decisions", "experiments"):
                (output_root / directory).mkdir(parents=True, exist_ok=True)
            (output_root / "observations" / f"{scenario['id']}.json").write_text(json.dumps(observation, indent=2) + "\n", encoding="utf-8")
            (output_root / "observer_estimates" / f"{scenario['id']}.json").write_text(json.dumps([item.to_dict() for item in estimates], indent=2) + "\n", encoding="utf-8")
            (output_root / "evidence_graphs" / f"{scenario['id']}.json").write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
            (output_root / "response_modes" / f"{scenario['id']}.json").write_text(json.dumps(response_mode, indent=2) + "\n", encoding="utf-8")
            (output_root / "state_certificates" / f"{scenario['id']}.json").write_text(json.dumps(certificate, indent=2) + "\n", encoding="utf-8")
            (output_root / "playbook_decisions" / f"{scenario['id']}.json").write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
            (output_root / "experiments" / f"{scenario['id']}.json").write_text(json.dumps(experiment, indent=2) + "\n", encoding="utf-8")
    return {"status": "PASS", "scenario_count": len(results), "real_orders_created": 0, "results": results}
