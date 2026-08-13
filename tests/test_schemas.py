import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def validate(schema, payload):
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    assert not errors, [e.message for e in errors]

def test_all_schemas_are_valid():
    for path in (ROOT / "schemas").glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text()))

def test_examples_validate():
    mapping = {
        "publication_status": "publication_status.json",
        "response_mode": "response_mode.json",
        "state_certificate": "state_certificate.json",
        "playbook_decision": "playbook_decision.json",
    }
    for schema_name, example in mapping.items():
        validate(json.loads((ROOT / f"schemas/{schema_name}.schema.json").read_text()), json.loads((ROOT / f"examples/{example}").read_text()))

def test_observer_estimate_rows_validate():
    schema = json.loads((ROOT / "schemas/observer_estimate.schema.json").read_text())
    for row in json.loads((ROOT / "examples/observer_estimates.json").read_text()):
        validate(schema, row)
