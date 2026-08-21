from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .analysis.daily_report import build_daily_report
from .analysis.experiment_runner import write_default_registry
from .disagreement import detect_conflicts
from .evidence_graph import build_evidence_graph
from .execution_modes import ExecutionMode
from .experiments import run_synthetic_demo
from .models import ObserverEstimate
from .next_probe import recommend_next_probe
from .playbooks import decide
from .publication import write_public_json
from .security import audit_public_tree
from .state_certificate import compile_state_certificate
from .validation import validate_all_schemas, validate_payload


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_estimates(path: Path) -> list[ObserverEstimate]:
    rows = _json(path)
    return [
        ObserverEstimate(
            observer_id=row["observer_id"],
            theme_id=row["theme_id"],
            as_of_utc=row["as_of_utc"],
            state=row["state"],
            eligible=bool(row["eligible"]),
            uncertainty=row.get("uncertainty"),
            evidence_refs=tuple(row.get("evidence_refs", [])),
            metrics=row.get("metrics", {}),
            invalidation=row.get("invalidation"),
            notes=row.get("notes"),
            data_ready=bool(row.get("data_ready", row.get("eligible", False))),
            model_estimated=bool(row.get("model_estimated", row.get("eligible", False))),
            decision_eligible=bool(row.get("decision_eligible", row.get("eligible", False))),
            source_version=row.get("source_version"),
            source_sha256=row.get("source_sha256"),
        )
        for row in rows
    ]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _serve(site: Path, port: int) -> None:
    class SiteHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=str(site), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), SiteHandler)
    print(f"Serving {site} at http://127.0.0.1:{port}")
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mso")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("payload", type=Path)
    validate.add_argument("--schema", required=True)

    sub.add_parser("validate-repo")

    graph = sub.add_parser("build-evidence-graph")
    graph.add_argument("--estimates", type=Path, required=True)
    graph.add_argument("--output", type=Path, required=True)

    certificate = sub.add_parser("compile-certificate")
    certificate.add_argument("--theme-id", required=True)
    certificate.add_argument("--estimates", type=Path, required=True)
    certificate.add_argument("--facts", type=Path)
    certificate.add_argument("--output", type=Path, required=True)
    certificate.add_argument("--evidence-grade", default="synthetic_demo")

    conflicts = sub.add_parser("detect-conflicts")
    conflicts.add_argument("--estimates", type=Path, required=True)
    conflicts.add_argument("--output", type=Path)

    probe = sub.add_parser("recommend-next-probe")
    probe.add_argument("--theme-id", required=True)
    probe.add_argument("--estimates", type=Path, required=True)
    probe.add_argument("--output", type=Path)

    playbook = sub.add_parser("decide-playbook")
    playbook.add_argument("--theme-id", required=True)
    playbook.add_argument("--as-of-utc", required=True)
    playbook.add_argument("--playbook", required=True)
    playbook.add_argument("--direction", required=True)
    playbook.add_argument("--transmission", required=True)
    playbook.add_argument("--fragility", default="medium")
    playbook.add_argument("--currently-held", action="store_true")
    playbook.add_argument("--previous-state")
    playbook.add_argument("--vehicle")
    playbook.add_argument("--output", type=Path)

    rehearsal = sub.add_parser("import-redacted-rehearsal")
    rehearsal.add_argument("payload", type=Path)
    rehearsal.add_argument("--output", type=Path)

    status = sub.add_parser("build-public-status")
    status.add_argument("payload", type=Path)
    status.add_argument("--output", type=Path, default=Path("public/data/status.json"))

    audit = sub.add_parser("audit-publication")
    audit.add_argument("paths", type=Path, nargs="*", default=[Path("public"), Path("examples")])

    demo = sub.add_parser("synthetic-demo")
    demo.add_argument("--output-root", type=Path, default=Path("examples"))
    demo.add_argument("--summary", type=Path)

    serve = sub.add_parser("serve-site")
    serve.add_argument("--site", type=Path, default=Path("dist/web"))
    serve.add_argument("--port", type=int, default=8000)

    daily_report = sub.add_parser("build-daily-report")
    daily_report.add_argument("--run", type=Path, required=True)
    daily_report.add_argument("--output", type=Path, required=True)
    daily_report.add_argument(
        "--mode",
        choices=[
            ExecutionMode.OBSERVATION_ONLY.value,
            ExecutionMode.CANDIDATE_REPLAY.value,
            ExecutionMode.PROSPECTIVE_CANDIDATE_SHADOW.value,
        ],
        default=ExecutionMode.OBSERVATION_ONLY.value,
    )

    registry = sub.add_parser("register-candidate-experiments")
    registry.add_argument("--output", type=Path, required=True)
    registry.add_argument("--registered-at-utc", required=True)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = _repo_root()
    if args.command == "validate":
        validate_payload(_json(args.payload), args.schema, root)
        print("PASS")
    elif args.command == "validate-repo":
        results = validate_all_schemas(root)
        print(json.dumps({"status": "PASS", "schemas": len(results)}, sort_keys=True))
    elif args.command == "build-evidence-graph":
        _write(args.output, build_evidence_graph(_load_estimates(args.estimates)))
        print(args.output)
    elif args.command == "compile-certificate":
        facts = _json(args.facts) if args.facts else []
        certificate = compile_state_certificate(args.theme_id, _load_estimates(args.estimates), facts, args.evidence_grade)
        validate_payload(certificate, "state_certificate", root)
        _write(args.output, certificate)
        print(args.output)
    elif args.command == "detect-conflicts":
        conflict_payload = [item.to_dict() for item in detect_conflicts(_load_estimates(args.estimates))]
        if args.output:
            _write(args.output, conflict_payload)
        else:
            print(json.dumps(conflict_payload, indent=2))
    elif args.command == "recommend-next-probe":
        probe_payload = recommend_next_probe(args.theme_id, _load_estimates(args.estimates))
        if probe_payload is not None:
            validate_payload(probe_payload, "next_probe", root)
        if args.output:
            _write(args.output, probe_payload)
        else:
            print(json.dumps(probe_payload, indent=2))
    elif args.command == "decide-playbook":
        decision = decide(args.theme_id, args.as_of_utc, args.playbook, args.direction, args.transmission, args.currently_held, args.vehicle, args.previous_state, args.fragility).to_dict()
        validate_payload(decision, "playbook_decision", root)
        if args.output:
            _write(args.output, decision)
        else:
            print(json.dumps(decision, indent=2))
    elif args.command == "import-redacted-rehearsal":
        payload = _json(args.payload)
        destination = args.output or root / "public" / "data" / "experiments" / f"{payload['trading_date']}.json"
        print(write_public_json(payload, "rehearsal_summary", destination, root))
    elif args.command == "build-public-status":
        print(write_public_json(_json(args.payload), "publication_status", args.output, root))
    elif args.command == "audit-publication":
        findings = [finding for path in args.paths for finding in audit_public_tree(path)]
        if findings:
            raise SystemExit("\n".join(findings))
        print("PASS")
    elif args.command == "synthetic-demo":
        summary = run_synthetic_demo(args.output_root)
        if args.summary:
            _write(args.summary, summary)
        print(json.dumps({"status": summary["status"], "scenario_count": summary["scenario_count"], "real_orders_created": 0}))
    elif args.command == "serve-site":
        _serve(args.site.resolve(), args.port)
    elif args.command == "build-daily-report":
        print(json.dumps(build_daily_report(args.run, args.output, mode=args.mode), sort_keys=True))
    elif args.command == "register-candidate-experiments":
        rows = write_default_registry(args.output, registered_at_utc=args.registered_at_utc)
        print(json.dumps({"status": "REGISTERED", "arms": len(rows), "output": str(args.output)}, sort_keys=True))
