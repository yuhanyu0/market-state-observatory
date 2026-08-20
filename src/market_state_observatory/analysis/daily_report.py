from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from market_state_observatory.disagreement import detect_conflicts
from market_state_observatory.execution_modes import ExecutionMode, authorize_mode
from market_state_observatory.next_probe import recommend_next_probe
from market_state_observatory.validation import validate_payload

from .candidate_stack import (
    EpisodeObservation,
    build_direction_candidates,
    build_episode_candidates,
    build_fragility_candidate,
    build_transmission_candidate,
    candidate_observer_estimates,
)
from .counterfactuals import build_playbook_counterfactual
from .experiment_runner import ARMS, register_experiment
from .feature_compiler import CompletedRunFeatureCompiler, feature_index
from .reporting import (
    build_incident_summary,
    build_observation_report,
    report_html,
    report_markdown,
)


class SidecarConflictError(RuntimeError):
    pass


def _model_input_value(row: dict[str, Any]) -> Any:
    return (
        row.get("value")
        if row.get("availability_status") == "AVAILABLE"
        and row.get("evidence_quality") == "VALID"
        and row.get("model_input_eligible") is True
        else None
    )


def _descriptive_structure_conflicts(
    features: dict[str, Any], theme_id: str
) -> list[dict[str, Any]]:
    index = feature_index(features)
    agreement = index.get(
        (theme_id, "session_close_diagnostic", "etf_basket_agreement")
    )
    if agreement and agreement.get("calculation_exists") and agreement.get("value") is False:
        return [
            {
                "conflict_type": "ETF_BASKET_DIRECTION_DISAGREEMENT",
                "evidence_level": "descriptive_structure",
                "validated_observer_conflict": False,
                "observation_point": "session_close_diagnostic",
            }
        ]
    return []


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _write_deterministic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise SidecarConflictError(f"Immutable sidecar conflict: {path}")
        return
    temporary = path.with_name(f".{path.name}.{sha256(content).hexdigest()[:12]}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _source_hashes(run_directory: Path) -> dict[str, str]:
    return {
        path.relative_to(run_directory).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(run_directory.rglob("*"))
        if path.is_file()
    }


def _candidate_bundle(
    features: dict[str, Any],
    theme_id: str,
) -> dict[str, Any]:
    index = feature_index(features)
    as_of = index[(theme_id, "decision_snapshot", "event_time_dispersion")]["observed_at_utc"]
    relative = index[(theme_id, "decision_snapshot", "relative_to_spy_return")]
    breadth = index[(theme_id, "decision_snapshot", "constituent_positive_breadth")]
    confirmation = index[(theme_id, "decision_snapshot", "preclose_decision_confirmation")]
    history = []
    relative_value = _model_input_value(relative)
    breadth_value = _model_input_value(breadth)
    if relative_value is not None and breadth_value is not None:
        history.append(
            EpisodeObservation(
                as_of,
                float(relative_value),
                float(breadth_value),
                bool(_model_input_value(confirmation) or False),
            )
        )
    directions = build_direction_candidates(features, theme_id)
    transmission = build_transmission_candidate(features, theme_id)
    episodes = build_episode_candidates(theme_id, history, as_of)
    fragility = build_fragility_candidate(features, theme_id)
    estimates = candidate_observer_estimates(directions, transmission, episodes, fragility)
    conflicts = [row.to_dict() for row in detect_conflicts(estimates)]
    probe = recommend_next_probe(theme_id, estimates)
    descriptive_conflicts = _descriptive_structure_conflicts(features, theme_id)
    selected_direction = next(row for row in directions if row["arm"] == "D1_TRANSPARENT_MULTI_FEATURE")
    selected_episode = next(row for row in episodes if row["arm"] == "E0_INTERPRETABLE_STATE_MACHINE")
    data_blocked = not bool(selected_direction["data_ready"])
    certificate = {
        "schema_version": "mso-state-certificate-candidate-v1",
        "certificate_id": f"{features['run_id']}:{theme_id}:candidate-v1",
        "theme_id": theme_id,
        "as_of_utc": as_of,
        "evidence_grade": "retrospective_unvalidated",
        "authorization_level": "CANDIDATE_REPLAY_ONLY",
        "facts": {"feature_set_version": features["feature_set_version"], "feature_count": sum(row["theme_id"] == theme_id for row in features["features"])},
        "data_validity": {"decision_primary_feed_fresh": not data_blocked, "no_future_data": True, "no_backfill": True},
        "direction_candidate": selected_direction,
        "transmission_candidate": transmission,
        "episode_candidate": selected_episode,
        "structural_attention": {"state": "not_available", "signed": False, "required_for_decision": False, "may_select_theme": False, "may_decide_playbook": False},
        "fragility": fragility,
        "event_context": {"state": "unavailable", "reason": "known_at_event_provenance_missing"},
        "observer_agreement": {"status": "INSUFFICIENT_VALIDATED_OBSERVERS", "candidate_conflict_count": len(conflicts)},
        "descriptive_structure_conflicts": descriptive_conflicts,
        "candidate_observer_conflicts": conflicts,
        "validated_observer_conflicts": [],
        "uncertainty": 1.0 if data_blocked else 0.55,
        "invalidation": ["candidate output is not validated", "point-in-time input becomes unavailable"],
        "next_probe": probe,
        "eligible_playbooks_candidate": [] if data_blocked else ["D_wait_unresolved"],
        "vehicle_eligibility_candidate": {"Theme_ETF": False, "Theme_Basket": False, "Equal_Risk_Basket": False, "Torque_Overlay": False},
        "decision_status": "DATA_BLOCKED_NO_DECISION" if data_blocked else "CANDIDATE_ONLY",
        "validated_model": False,
        "decision_eligible": False,
        "paper_positions": 0,
        "real_orders": 0,
    }
    playbook = build_playbook_counterfactual(
        run_id=str(features["run_id"]),
        theme_id=theme_id,
        as_of_utc=as_of,
        direction_state=str(selected_direction["candidate_state"]),
        transmission_state=str(transmission["candidate_transmission_state"]),
        episode_state=str(selected_episode["state"]),
        fragility_state=str(fragility["state"]),
    )
    return {
        "direction": directions,
        "transmission": transmission,
        "episode": episodes,
        "fragility": fragility,
        "certificate": certificate,
        "playbook": playbook,
    }


def build_daily_report(
    run_directory: Path,
    output_directory: Path,
    *,
    mode: ExecutionMode | str = ExecutionMode.OBSERVATION_ONLY,
    promotion_artifact: Path | None = None,
) -> dict[str, Any]:
    run_directory = run_directory.resolve()
    output_directory = output_directory.resolve()
    if _is_within(output_directory, run_directory):
        raise ValueError("Analysis sidecar must not be written inside the immutable source run")
    required = (run_directory / "RUN.json", run_directory / "quality" / "DATA_QUALITY.json")
    if not all(path.is_file() for path in required):
        raise FileNotFoundError("Completed run requires RUN.json and quality/DATA_QUALITY.json")
    before = _source_hashes(run_directory)
    authorization = authorize_mode(mode, promotion_artifact=promotion_artifact)
    validate_payload(authorization.to_dict(), "execution_mode")
    compiler = CompletedRunFeatureCompiler(run_directory)
    features, provenance, feature_quality = compiler.compile()
    candidates: dict[str, dict[str, Any]] | None = None
    if authorization.may_run_candidates:
        candidates = {
            str(theme["theme_id"]): _candidate_bundle(features, str(theme["theme_id"]))
            for theme in compiler.membership["themes"]
        }
    incidents = build_incident_summary(compiler, feature_quality)
    report = build_observation_report(
        compiler,
        features,
        feature_quality,
        incidents,
        candidates,
        authorization.to_dict(),
    )
    validate_payload(features, "observation_features")
    validate_payload(provenance, "feature_provenance")
    validate_payload(feature_quality, "feature_quality")
    validate_payload(report, "observation_report")
    validate_payload(incidents, "incident_summary")
    writes: dict[Path, bytes] = {
        output_directory / "OBSERVATION_FEATURES.json": _json_bytes(features),
        output_directory / "FEATURE_PROVENANCE.json": _json_bytes(provenance),
        output_directory / "FEATURE_QUALITY.json": _json_bytes(feature_quality),
        output_directory / "OBSERVATION_REPORT.json": _json_bytes(report),
        output_directory / "OBSERVATION_REPORT.md": (report_markdown(report) + "\n").encode(),
        output_directory / "OBSERVATION_REPORT.html": report_html(report).encode(),
        output_directory / "INCIDENT_SUMMARY.json": _json_bytes(incidents),
    }
    if candidates:
        experiment_registry = [
            register_experiment(
                arm,
                [str(compiler.run["created_at_utc"])],
                registered_at_utc="2026-08-19T19:00:00+00:00",
            )
            for arm in ARMS
        ]
        for registration in experiment_registry:
            validate_payload(registration, "experiment_registration")
        writes[output_directory / "experiments" / "EXPERIMENT_REGISTRY.json"] = _json_bytes(
            experiment_registry
        )
        for theme_id, bundle in candidates.items():
            for row in bundle["direction"]:
                validate_payload(row, "direction_candidate")
            validate_payload(bundle["transmission"], "transmission_candidate")
            for row in bundle["episode"]:
                validate_payload(row, "episode_candidate")
            validate_payload(bundle["certificate"], "state_certificate_candidate")
            validate_payload(bundle["playbook"], "playbook_counterfactual")
            root = output_directory / "themes" / theme_id
            writes[root / "DIRECTION_CANDIDATES.json"] = _json_bytes(bundle["direction"])
            writes[root / "TRANSMISSION_CANDIDATE.json"] = _json_bytes(bundle["transmission"])
            writes[root / "EPISODE_CANDIDATES.json"] = _json_bytes(bundle["episode"])
            writes[root / "STATE_CERTIFICATE_CANDIDATE.json"] = _json_bytes(bundle["certificate"])
            writes[root / "PLAYBOOK_COUNTERFACTUAL.json"] = _json_bytes(bundle["playbook"])
    for path, content in writes.items():
        _write_deterministic(path, content)
    after = _source_hashes(run_directory)
    if before != after:
        raise RuntimeError("Immutable source run changed during sidecar generation")
    status = {
        "schema_version": "mso-daily-report-status-v1",
        "run_id": compiler.run["run_id"],
        "status": "COMPLETE",
        "execution_mode": authorization.mode.value,
        "source_run_unchanged": True,
        "output_directory": str(output_directory),
        "report_sha256": sha256(writes[output_directory / "OBSERVATION_REPORT.json"]).hexdigest(),
        "candidate_replay_executed": candidates is not None,
        "paper_positions": 0,
        "real_orders": 0,
    }
    validate_payload(status, "daily_report_status")
    _write_deterministic(output_directory / "DAILY_REPORT_STATUS.json", _json_bytes(status))
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a private read-only completed-run analysis sidecar")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=[mode.value for mode in ExecutionMode], default=ExecutionMode.OBSERVATION_ONLY.value)
    parser.add_argument("--promotion-artifact", type=Path)
    args = parser.parse_args()
    result = build_daily_report(args.run, args.output, mode=args.mode, promotion_artifact=args.promotion_artifact)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
