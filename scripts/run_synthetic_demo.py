from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.experiments import run_synthetic_demo


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = run_synthetic_demo(root / "examples")
    reference = result["results"][1]
    aliases = {
        "observation.json": reference["observation"],
        "observer_estimates.json": reference["estimates"],
        "evidence_graph.json": result["results"][0]["graph"],
        "state_certificate.json": reference["certificate"],
        "playbook_decision.json": result["results"][5]["decision"],
        "next_probe.json": reference["certificate"]["next_probe"],
        "experiment.json": reference["experiment"],
    }
    for filename, payload in aliases.items():
        (root / "examples" / filename).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    summary = {
        "status": result["status"],
        "scenario_count": result["scenario_count"],
        "real_orders_created": result["real_orders_created"],
        "allowed_decision_states": ["DATA_BLOCKED_NO_DECISION", "WAIT", "MODEL_SHADOW_ONLY"],
    }
    (root / "examples" / "synthetic_demo_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
