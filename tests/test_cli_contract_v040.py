from __future__ import annotations

from market_state_observatory.cli import build_parser


def test_cli_exposes_required_commands() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert {
        "validate", "validate-repo", "build-evidence-graph", "compile-certificate",
        "detect-conflicts", "recommend-next-probe", "decide-playbook",
        "import-redacted-rehearsal", "build-public-status", "audit-publication",
        "synthetic-demo", "serve-site",
    } <= set(subparsers.choices)
