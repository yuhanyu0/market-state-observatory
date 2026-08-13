from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.validation import validate_all_schemas, validate_payload


def validate_directory(root: Path, directory: str, schema: str, arrays: bool = False) -> int:
    count = 0
    for path in sorted((root / "examples" / directory).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if arrays else [payload]
        for row in rows:
            validate_payload(row, schema, root)
            count += 1
    return count


def public_schema(relative: Path) -> str:
    value = relative.as_posix()
    if value == "status.json":
        return "publication_status"
    if value == "themes.json":
        return "public_themes"
    if value == "experiments.json":
        return "public_experiments"
    if value == "roadmap.json":
        return "public_roadmap"
    if value == "validation.json":
        return "public_validation"
    if value.startswith("certificates/") or value.startswith("synthetic_certificates/"):
        return "state_certificate"
    if value.startswith("experiments/"):
        return "rehearsal_summary"
    if value.startswith("data-quality/"):
        return "public_data_quality"
    raise ValueError(f"Public JSON has no explicit schema mapping: public/data/{value}")


def validate_public_tree(root: Path) -> int:
    public_root = root / "public" / "data"
    count = 0
    for path in sorted(public_root.rglob("*.json")):
        validate_payload(
            json.loads(path.read_text(encoding="utf-8")), public_schema(path.relative_to(public_root)), root
        )
        count += 1
    return count


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    schemas = validate_all_schemas(root)
    count = 0
    count += validate_directory(root, "observations", "observation")
    count += validate_directory(root, "observer_estimates", "observer_estimate", arrays=True)
    count += validate_directory(root, "evidence_graphs", "evidence_graph")
    count += validate_directory(root, "state_certificates", "state_certificate")
    count += validate_directory(root, "playbook_decisions", "playbook_decision")
    count += validate_directory(root, "experiments", "experiment")
    count += validate_public_tree(root)
    validate_payload(
        json.loads((root / "examples" / "day0b_public_summary.json").read_text(encoding="utf-8")),
        "rehearsal_summary", root,
    )
    print(json.dumps({"status": "PASS", "schemas": len(schemas), "validated_objects": count + 1}, sort_keys=True))


if __name__ == "__main__":
    main()
