from __future__ import annotations

from hashlib import sha256
from typing import Any

from .disagreement import detect_conflicts
from .models import ObserverEstimate


def build_evidence_graph(estimates: list[ObserverEstimate]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in estimates:
        node_id = f"estimate:{item.observer_id}:{item.theme_id}"
        nodes.append({"id": node_id, "kind": "estimate", "label": item.state, "payload": {"observer_id": item.observer_id, "eligible": item.eligible, "uncertainty": item.uncertainty, "data_ready": item.data_ready, "model_estimated": item.model_estimated, "decision_eligible": item.decision_eligible}})
        seen.add(node_id)
        for reference in item.evidence_refs:
            observation_id = f"observation:{reference}"
            if observation_id not in seen:
                nodes.append({"id": observation_id, "kind": "observation", "label": reference, "payload": {}})
                seen.add(observation_id)
            edges.append({"source": observation_id, "target": node_id, "relation": "supports", "weight": None})
    for conflict in detect_conflicts(estimates):
        edges.append({"source": f"estimate:{conflict.left}:{conflict.theme_id}", "target": f"estimate:{conflict.right}:{conflict.theme_id}", "relation": "contradicts", "weight": None})
    as_of = max((item.as_of_utc for item in estimates), default="1970-01-01T00:00:00Z")
    identity = sha256("|".join(sorted(node["id"] for node in nodes)).encode("utf-8")).hexdigest()[:24]
    return {"graph_id": f"evidence-{identity}", "as_of_utc": as_of, "nodes": nodes, "edges": edges}
