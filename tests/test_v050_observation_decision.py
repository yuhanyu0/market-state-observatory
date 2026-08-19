from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from market_state_observatory.analysis.candidate_stack import (
    EpisodeObservation,
    build_direction_candidates,
    build_episode_candidates,
    build_transmission_candidate,
)
from market_state_observatory.analysis.counterfactuals import build_playbook_counterfactual
from market_state_observatory.analysis.daily_report import build_daily_report
from market_state_observatory.analysis.experiment_runner import (
    ReplayRecord,
    register_experiment,
    run_registered_replay,
)
from market_state_observatory.analysis.feature_compiler import CompletedRunFeatureCompiler
from market_state_observatory.execution_modes import (
    AuthorizationError,
    ExecutionMode,
    authorize_mode,
)
from market_state_observatory.observer_registry import ObserverRegistry
from market_state_observatory.runtime.quality_engine import evaluate_run_quality
from market_state_observatory.runtime.websocket_incidents import WebSocketIncidentLedger
from market_state_observatory.validation import validate_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "completed_run_2026-08-18"


def _tree_hash(root: Path) -> str:
    digest = sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "run"
    shutil.copytree(FIXTURE, destination)
    return destination


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_execution_modes_fail_closed() -> None:
    observation = authorize_mode(ExecutionMode.OBSERVATION_ONLY)
    assert observation.may_run_candidates is False
    candidate = authorize_mode(ExecutionMode.CANDIDATE_REPLAY)
    assert candidate.may_run_candidates is True
    assert candidate.may_run_validated_models is False
    assert candidate.paper_positions_allowed is False
    with pytest.raises(AuthorizationError, match="promotion artifact"):
        authorize_mode(ExecutionMode.MODEL_SHADOW)
    with pytest.raises(AuthorizationError, match="unavailable"):
        authorize_mode(ExecutionMode.PAPER_LIVE)


def test_818_acceptance_report_is_blocked_and_descriptive(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    status = build_daily_report(FIXTURE, output, mode=ExecutionMode.CANDIDATE_REPLAY)
    report = _load(output / "OBSERVATION_REPORT.json")
    quality = _load(output / "FEATURE_QUALITY.json")
    evidence = report["sections"]["A_evidence_validity"]
    health = report["sections"]["G_system_health"]
    assert status["source_run_unchanged"] is True
    assert report["release_version"] == "0.4.5"
    assert report["experiment_lane"] == "data-shadow-v0.4.5-ee531efd-d53e704c"
    assert evidence == {
        "planned": 175,
        "captured": 175,
        "capture_rate": 1.0,
        "future_timestamp_count": 0,
        "backfill_count": 0,
    }
    assert health["stream_message_count"] == 16_660_968
    assert health["stream_message_drop_count"] == 0
    assert health["stream_chunk_count"] == 8
    assert quality["decision_primary_quote_count"] == 35
    assert quality["decision_stale_quote_count"] == 35
    assert 141 <= quality["observed_quote_age_max"] <= 162
    assert report["headline"] == "NO DECISION / PRIMARY FEED FRESHNESS FAILURE"
    themes = {row["theme_id"]: row for row in report["sections"]["C_descriptive_theme_structure"]["themes"]}
    expected = {
        "cybersecurity": "Constituent breadth was stronger than the close ETF return.",
        "solar_energy": "Constituent breadth was broadly negative at the close.",
        "semiconductors": "Broad weakness showed partial late repair without reversing sign.",
        "cloud_computing": "ETF and basket direction disagreed near the close.",
        "commercial_space": "The intraday path whipsawed and finished with low coherence.",
        "uranium_nuclear": "The ETF state was negative while constituent outcomes remained dispersed.",
    }
    for theme_id, finding in expected.items():
        assert finding in themes[theme_id]["descriptive_findings"]
        candidate = themes[theme_id]["candidate_outputs"]
        assert candidate["direction"][1]["candidate_state"] == "unresolved"
        assert candidate["transmission"]["candidate_transmission_state"] == "not_estimable"
        assert candidate["episode"][0]["state"] == "not_estimable"
        assert candidate["certificate"]["decision_status"] == "DATA_BLOCKED_NO_DECISION"


def test_open_not_yet_defined_is_not_applicable() -> None:
    features, _, quality = CompletedRunFeatureCompiler(FIXTURE).compile()
    open_rows = [
        row
        for row in features["features"]
        if row["observation_point"] == "open_snapshot"
        and row["feature_id"] in {"vwap_distance", "range_position", "volume_breadth"}
    ]
    assert len(open_rows) == 18
    assert all(row["availability_status"] == "NOT_APPLICABLE" for row in open_rows)
    assert quality["open_not_yet_defined_excluded_from_readiness"] is True


def test_feature_compiler_is_deterministic_and_timestamped() -> None:
    first = CompletedRunFeatureCompiler(FIXTURE).compile()[0]
    second = CompletedRunFeatureCompiler(FIXTURE).compile()[0]
    assert first == second
    assert len(first["features"]) == 864
    for row in first["features"]:
        assert row["data_max_timestamp"] <= row["observed_at_utc"]
        assert len(row["calculation_sha256"]) == 64


def test_future_source_timestamp_is_rejected(tmp_path: Path) -> None:
    run = _copy_fixture(tmp_path)
    point = run / "manifests" / "points" / "decision_snapshot.json"
    payload = _load(point)
    payload["latest_event_time_utc"] = "2026-08-19T00:00:00+00:00"
    point.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future data rejected"):
        CompletedRunFeatureCompiler(run).compile()


def test_missing_decision_point_remains_descriptive(tmp_path: Path) -> None:
    run = _copy_fixture(tmp_path)
    (run / "manifests" / "points" / "decision_snapshot.json").unlink()
    output = tmp_path / "analysis"
    build_daily_report(run, output, mode=ExecutionMode.OBSERVATION_ONLY)
    report = _load(output / "OBSERVATION_REPORT.json")
    assert report["sections"]["D_candidate_inference_status"]["candidate_replay_executed"] is False
    assert report["sections"]["H_authorization_boundary"]["decision_status"] == "DESCRIPTIVE_ONLY"


def test_clean_decision_inputs_estimate_candidates_but_never_validate(tmp_path: Path) -> None:
    run = _copy_fixture(tmp_path)
    point = run / "manifests" / "points" / "decision_snapshot.json"
    payload = _load(point)
    for row in payload["symbols"]:
        row["quote"]["status"] = "READY"
        row["quote"]["freshness_age_seconds"] = 1.0
    point.write_text(json.dumps(payload), encoding="utf-8")
    features = CompletedRunFeatureCompiler(run).compile()[0]
    directions = build_direction_candidates(features, "cybersecurity")
    transmission = build_transmission_candidate(features, "cybersecurity")
    assert all(row["data_ready"] for row in directions)
    assert all(row["candidate_estimated"] for row in directions)
    assert all(row["validated_model"] is False and row["decision_eligible"] is False for row in directions)
    assert transmission["transmission_input_readiness"] is True
    assert transmission["validated_transmission_state"] is None


def test_episode_minimum_history_and_state_transition() -> None:
    short = [EpisodeObservation("2026-08-01T20:00:00+00:00", -0.01, 0.2, False)]
    blocked = build_episode_candidates("semiconductors", short, short[-1].as_of_utc)
    assert blocked[0]["state"] == "not_estimable"
    rows = [
        EpisodeObservation("2026-08-01T20:00:00+00:00", -0.01, 0.2, False),
        EpisodeObservation("2026-08-02T20:00:00+00:00", -0.005, 0.4, False),
        EpisodeObservation("2026-08-03T20:00:00+00:00", 0.01, 0.75, True),
    ]
    estimated = build_episode_candidates("semiconductors", rows, rows[-1].as_of_utc)
    assert estimated[0]["state"] == "onset"
    assert estimated[0]["candidate_estimated"] is True
    assert estimated[1]["state"] == "not_estimable"
    assert estimated[2]["blocking_reasons"] == ["plugin_not_registered"]


def test_theme_radar_isolation_contract() -> None:
    registry = ObserverRegistry()
    registry.assert_theme_radar_isolated()
    radar = registry.get("theme_radar_attention")
    assert (radar.signed, radar.required_for_decision, radar.may_select_theme, radar.may_decide_playbook) == (False, False, False, False)


def test_playbook_and_vehicle_outputs_are_counterfactual_only() -> None:
    payload = build_playbook_counterfactual(
        run_id="fixture",
        theme_id="semiconductors",
        as_of_utc="2026-08-18T19:45:00+00:00",
        direction_state="positive",
        transmission_state="broad_confirmed",
        episode_state="onset",
        fragility_state="low",
    )
    validate_payload(payload, "playbook_counterfactual")
    assert payload["state_transition"] == "entry"
    assert payload["counterfactual_only"] is True
    assert payload["model_shadow_authorized"] is False
    assert payload["vehicle_eligibility_candidate"]["Torque_Overlay"] is False
    assert payload["paper_positions"] == payload["real_orders"] == 0


def test_daily_report_is_idempotent_and_does_not_mutate_source(tmp_path: Path) -> None:
    before = _tree_hash(FIXTURE)
    output = tmp_path / "analysis"
    first = build_daily_report(FIXTURE, output, mode=ExecutionMode.CANDIDATE_REPLAY)
    output_hash = _tree_hash(output)
    second = build_daily_report(FIXTURE, output, mode=ExecutionMode.CANDIDATE_REPLAY)
    assert first == second
    assert output_hash == _tree_hash(output)
    assert before == _tree_hash(FIXTURE)


def test_sidecar_cannot_write_inside_source_run(tmp_path: Path) -> None:
    run = _copy_fixture(tmp_path)
    with pytest.raises(ValueError, match="must not be written inside"):
        build_daily_report(run, run / "analysis")


def test_websocket_event_ledger_is_append_only_and_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "WEBSOCKET_CONNECTION_EVENTS.ndjson"
    ledger = WebSocketIncidentLedger(path, release_version="0.5.0rc1", run_id="fixture")
    secret = "do-not-persist-this-credential"
    ledger.append("connecting")
    ledger.append("exception", exception=RuntimeError(secret), safe_reason="connection reset")
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert secret not in path.read_text(encoding="utf-8")
    assert _load_line(rows[1])["safe_exception_type"] == "RuntimeError"


def test_connection_gap_overlap_and_quote_age_names(tmp_path: Path) -> None:
    run = _copy_fixture(tmp_path)
    ledger = run / "manifests" / "websocket" / "WEBSOCKET_CONNECTION_EVENTS.ndjson"
    event = {
        "gap_started_at_utc": "2026-08-18T19:44:30+00:00",
        "gap_ended_at_utc": "2026-08-18T19:45:30+00:00",
        "gap_duration_seconds": 60.0,
    }
    ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
    universe = _load(ROOT / "config" / "runtime_universe_v1.json")
    quality = evaluate_run_quality(run, universe)
    assert quality["connection_gap_count"] == 1
    assert quality["connection_gap_seconds_max"] == 60.0
    assert quality["connection_gap_overlap_by_observation_point"]["decision_snapshot"] is True
    assert quality["stale_quote_count_by_point"]["decision_snapshot"] == 35
    assert quality["observed_quote_age_max"] > quality["ready_quote_age_max"]
    assert quality["quote_age_seconds_max"] == quality["ready_quote_age_max"]


def _load_line(line: str) -> dict:
    return json.loads(line)


def test_experiment_registry_replay_is_strict_asof_and_unvalidated() -> None:
    registration = register_experiment("D1+T", [f"2026-08-{day:02d}T20:00:00+00:00" for day in range(1, 32)], registered_at_utc="2026-07-31T20:00:00+00:00")
    assert registration["rehearsal_is_official_evidence"] is False
    records = [
        ReplayRecord("2026-08-01T20:00:00+00:00", "2026-08-02T20:00:00+00:00", "semiconductors", "e1", 0.6, 1, 0.01, 10),
        ReplayRecord("2026-08-02T20:00:00+00:00", "2026-08-03T20:00:00+00:00", "cloud_computing", "e2", 0.4, -1, -0.005, 10),
    ]
    result = run_registered_replay(registration, records)
    validate_payload(registration, "experiment_registration")
    validate_payload(result, "experiment_result")
    assert result["validated_model"] is False
    assert result["decision_eligible"] is False
    bad = [ReplayRecord("2026-08-02T20:00:00+00:00", "2026-08-01T20:00:00+00:00", "x", None, None, None, 0, 0)]
    with pytest.raises(ValueError, match="strict as-of"):
        run_registered_replay(registration, bad)


def test_candidate_schemas_validate_for_acceptance_output(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    build_daily_report(FIXTURE, output, mode=ExecutionMode.CANDIDATE_REPLAY)
    for theme in (output / "themes").iterdir():
        for row in json.loads((theme / "DIRECTION_CANDIDATES.json").read_text()):
            validate_payload(row, "direction_candidate")
        validate_payload(_load(theme / "TRANSMISSION_CANDIDATE.json"), "transmission_candidate")
        for row in json.loads((theme / "EPISODE_CANDIDATES.json").read_text()):
            validate_payload(row, "episode_candidate")
        validate_payload(_load(theme / "STATE_CERTIFICATE_CANDIDATE.json"), "state_certificate_candidate")
