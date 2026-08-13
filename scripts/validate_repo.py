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
    for path in sorted((root / "public" / "data" / "certificates").glob("*.json")):
        validate_payload(json.loads(path.read_text(encoding="utf-8")), "state_certificate", root)
        count += 1
    for path in sorted((root / "public" / "data" / "data-quality").glob("*.json")):
        validate_payload(json.loads(path.read_text(encoding="utf-8")), "public_data_quality", root)
        count += 1
    validate_payload(json.loads((root / "examples" / "day0b_public_summary.json").read_text(encoding="utf-8")), "rehearsal_summary", root)
    print(json.dumps({"status": "PASS", "schemas": len(schemas), "validated_example_objects": count + 1}, sort_keys=True))


if __name__ == "__main__":
    main()
