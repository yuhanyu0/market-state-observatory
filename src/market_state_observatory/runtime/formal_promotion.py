from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .observation_freezer import canonical_json, write_exclusive
from .release_identity import load_release_manifest, sha256_file

MINIMUM_SCHEDULER_REHEARSAL_SESSIONS = 3
REHEARSAL_TASK_NAME = "MSO-Daily-Rehearsal"
AUTHORIZATION_FILE = "formal_data_shadow_authorization.json"
SOAK_RESULTS_FILE = "SOAK_TEST_RESULTS.json"

IDENTITY_FIELDS = (
    "release_version",
    "release_git_sha",
    "release_wheel_sha256",
    "experiment_lane",
    "universe_sha256",
    "membership_sha256",
    "schema_sha256",
    "quality_policy_sha256",
)


class FormalPromotionError(RuntimeError):
    pass


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FormalPromotionError(f"{label} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FormalPromotionError(f"{label} is malformed") from error
    if not isinstance(payload, dict):
        raise FormalPromotionError(f"{label} must be an object")
    return payload


def _release_identity(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "release_version": str(manifest["release_version"]),
        "release_git_sha": str(manifest["git_sha"]),
        "release_wheel_sha256": str(manifest["wheel_sha256"]),
        "experiment_lane": str(manifest["experiment_lane"]),
        "universe_sha256": str(manifest["universe_sha256"]),
        "membership_sha256": str(manifest["membership_sha256"]),
        "schema_sha256": str(manifest["schema_sha256"]),
        "quality_policy_sha256": str(manifest["quality_policy_sha256"]),
    }


def _assert_release_identity(payload: dict[str, Any], manifest: dict[str, Any], label: str) -> None:
    expected = _release_identity(manifest)
    missing = [field for field in IDENTITY_FIELDS if field not in payload]
    if missing:
        raise FormalPromotionError(f"{label} fields missing: {missing}")
    mismatched = [field for field, value in expected.items() if str(payload[field]) != value]
    if mismatched:
        raise FormalPromotionError(f"{label} release identity mismatch: {mismatched}")


def _required_true(payload: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    failed = [field for field in fields if payload.get(field) is not True]
    if failed:
        raise FormalPromotionError(f"{label} failed gates: {failed}")


def _resolve_rehearsal_run(runtime_root: Path, relative: str) -> Path:
    candidate = (runtime_root / relative).resolve()
    rehearsal_root = (runtime_root / "observations" / "rehearsals").resolve()
    if candidate == rehearsal_root or rehearsal_root not in candidate.parents:
        raise FormalPromotionError("Soak session is outside the rehearsal runtime tree")
    return candidate


def validate_soak_results(
    runtime_root: Path, manifest: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    path = runtime_root / "promotion" / SOAK_RESULTS_FILE
    payload = _read_object(path, SOAK_RESULTS_FILE)
    if payload.get("schema_version") != "mso-soak-test-results-v1":
        raise FormalPromotionError("SOAK_TEST_RESULTS schema_version is invalid")
    if payload.get("status") != "PASS":
        raise FormalPromotionError("SOAK_TEST_RESULTS status must be PASS")
    _assert_release_identity(payload, manifest, "SOAK_TEST_RESULTS")
    _required_true(
        payload,
        (
            "credential_leak_scan_pass",
            "private_public_boundary_pass",
            "settlement_idempotence_pass",
            "publication_rehearsal_isolation_pass",
            "scheduler_version_frozen",
        ),
        "SOAK_TEST_RESULTS",
    )
    if payload.get("scheduler_version") != manifest["powershell_launcher_version"]:
        raise FormalPromotionError("SOAK_TEST_RESULTS scheduler version is stale")
    if int(payload.get("paper_positions", -1)) != 0 or int(payload.get("real_orders", -1)) != 0:
        raise FormalPromotionError("SOAK_TEST_RESULTS position/order counts must be zero")

    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or len(sessions) < MINIMUM_SCHEDULER_REHEARSAL_SESSIONS:
        raise FormalPromotionError(
            f"At least {MINIMUM_SCHEDULER_REHEARSAL_SESSIONS} scheduler rehearsal sessions are required"
        )
    trading_dates: set[str] = set()
    run_ids: set[str] = set()
    for index, session in enumerate(sessions):
        label = f"soak session {index + 1}"
        if not isinstance(session, dict):
            raise FormalPromotionError(f"{label} must be an object")
        _required_true(
            session,
            (
                "scheduler_driven",
                "complete",
                "required_observations_captured",
                "data_quality_pass",
                "secret_scan_pass",
                "private_public_boundary_pass",
                "settlement_idempotence_pass",
                "publication_rehearsal_isolation_pass",
                "scheduler_version_frozen",
            ),
            label,
        )
        if session.get("scheduler_task_name") != REHEARSAL_TASK_NAME:
            raise FormalPromotionError(f"{label} was not produced by the rehearsal task")
        if session.get("scheduler_mode") != "rehearsal":
            raise FormalPromotionError(f"{label} mode is not rehearsal")
        for field in ("future_timestamp_count", "backfill_count", "message_drop_count"):
            if int(session.get(field, -1)) != 0:
                raise FormalPromotionError(f"{label} requires {field}=0")
        if int(session.get("paper_positions", -1)) != 0 or int(
            session.get("real_orders", -1)
        ) != 0:
            raise FormalPromotionError(f"{label} position/order counts must be zero")

        relative = session.get("run_relative_path")
        if not isinstance(relative, str) or not relative:
            raise FormalPromotionError(f"{label} run_relative_path is missing")
        run_directory = _resolve_rehearsal_run(runtime_root, relative)
        run_path = run_directory / "RUN.json"
        quality_path = run_directory / "quality" / "DATA_QUALITY.json"
        run = _read_object(run_path, f"{label} RUN.json")
        quality = _read_object(quality_path, f"{label} DATA_QUALITY.json")
        if sha256_file(run_path) != session.get("source_run_sha256"):
            raise FormalPromotionError(f"{label} RUN.json hash mismatch")
        if sha256_file(quality_path) != session.get("quality_sha256"):
            raise FormalPromotionError(f"{label} DATA_QUALITY.json hash mismatch")
        if run.get("run_id") != session.get("run_id"):
            raise FormalPromotionError(f"{label} run_id mismatch")
        if run.get("mode") != "rehearsal" or run.get("status") != "DATA_CAPTURE_REHEARSAL":
            raise FormalPromotionError(f"{label} immutable run mode is not rehearsal")
        if run.get("scheduler_task_name") != REHEARSAL_TASK_NAME:
            raise FormalPromotionError(f"{label} immutable run is not scheduler-driven")
        if run.get("counts_toward_20_day_gate") is not False:
            raise FormalPromotionError(f"{label} rehearsal attempted to count toward the 20-day gate")
        if run.get("counts_toward_model_shadow") is not False:
            raise FormalPromotionError(f"{label} attempted to count toward Model Shadow")
        if run.get("publication_as_formal") is not False:
            raise FormalPromotionError(f"{label} rehearsal publication boundary is invalid")
        _assert_release_identity(
            {
                "release_version": run.get("release_version"),
                "release_git_sha": run.get("git_sha"),
                "release_wheel_sha256": run.get("wheel_sha256"),
                "experiment_lane": run.get("experiment_lane"),
                "universe_sha256": run.get("universe_sha256"),
                "membership_sha256": run.get("membership_sha256"),
                "schema_sha256": run.get("schema_sha256"),
                "quality_policy_sha256": run.get("quality_policy_sha256"),
            },
            manifest,
            label,
        )
        if quality.get("data_quality_pass") is not True:
            raise FormalPromotionError(f"{label} data quality did not pass")
        if quality.get("counts_toward_20_day_gate") is not False:
            raise FormalPromotionError(f"{label} quality incorrectly counts toward the 20-day gate")
        if quality.get("counts_toward_model_shadow") is not False:
            raise FormalPromotionError(f"{label} quality incorrectly counts toward Model Shadow")
        if quality.get("publication_eligible") is not False:
            raise FormalPromotionError(f"{label} rehearsal was publication eligible")
        if int(quality.get("future_timestamp_count", -1)) != 0:
            raise FormalPromotionError(f"{label} contains future timestamps")
        if int(quality.get("backfill_count", -1)) != 0:
            raise FormalPromotionError(f"{label} contains backfills")
        if int(quality.get("stream_message_drop_count", -1)) != 0:
            raise FormalPromotionError(f"{label} contains stream message drops")
        if int(quality.get("captured_observations", -1)) != int(
            quality.get("planned_observations", -2)
        ):
            raise FormalPromotionError(f"{label} did not capture every planned observation")
        trading_dates.add(str(run.get("trading_date")))
        run_ids.add(str(run.get("run_id")))

    if len(run_ids) < MINIMUM_SCHEDULER_REHEARSAL_SESSIONS:
        raise FormalPromotionError("Soak sessions must have unique run IDs")
    if len(trading_dates) < MINIMUM_SCHEDULER_REHEARSAL_SESSIONS:
        raise FormalPromotionError("Soak sessions must cover at least three distinct trading dates")
    return path, payload


def create_authorization(runtime_root: Path) -> Path:
    manifest = load_release_manifest(required=True)
    assert manifest is not None
    soak_path, _ = validate_soak_results(runtime_root, manifest)
    authorization = {
        "schema_version": "mso-formal-data-shadow-authorization-v1",
        "status": "GO",
        **_release_identity(manifest),
        "soak_result_sha256": sha256_file(soak_path),
        "authorized_at_utc": datetime.now(UTC).isoformat(),
        "minimum_scheduler_rehearsal_sessions": MINIMUM_SCHEDULER_REHEARSAL_SESSIONS,
        "counts_toward_model_shadow": False,
        "paper_positions_allowed": False,
        "real_orders_allowed": False,
    }
    target = runtime_root / "promotion" / AUTHORIZATION_FILE
    write_exclusive(target, canonical_json(authorization))
    return target


def verify_authorization(runtime_root: Path) -> dict[str, Any]:
    manifest = load_release_manifest(required=True)
    assert manifest is not None
    path = runtime_root / "promotion" / AUTHORIZATION_FILE
    payload = _read_object(path, "Formal promotion authorization")
    if payload.get("schema_version") != "mso-formal-data-shadow-authorization-v1":
        raise FormalPromotionError("Formal promotion authorization schema_version is invalid")
    if payload.get("status") != "GO":
        raise FormalPromotionError("Formal promotion authorization status must be GO")
    _assert_release_identity(payload, manifest, "Formal promotion authorization")
    required_fields = (
        "soak_result_sha256",
        "authorized_at_utc",
        "minimum_scheduler_rehearsal_sessions",
        "counts_toward_model_shadow",
        "paper_positions_allowed",
        "real_orders_allowed",
    )
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise FormalPromotionError(f"Formal promotion authorization fields missing: {missing}")
    try:
        datetime.fromisoformat(str(payload["authorized_at_utc"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise FormalPromotionError("Formal promotion authorized_at_utc is invalid") from error
    if int(payload["minimum_scheduler_rehearsal_sessions"]) < MINIMUM_SCHEDULER_REHEARSAL_SESSIONS:
        raise FormalPromotionError("Formal authorization weakened the rehearsal-session gate")
    if payload.get("counts_toward_model_shadow") is not False:
        raise FormalPromotionError("Formal authorization cannot enable Model Shadow")
    if payload.get("paper_positions_allowed") is not False:
        raise FormalPromotionError("Formal authorization cannot enable paper positions")
    if payload.get("real_orders_allowed") is not False:
        raise FormalPromotionError("Formal authorization cannot enable real orders")
    soak_path, _ = validate_soak_results(runtime_root, manifest)
    if payload.get("soak_result_sha256") != sha256_file(soak_path):
        raise FormalPromotionError("Formal promotion soak result hash mismatch")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Formal Data Shadow promotion")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--promote", action="store_true")
    operation.add_argument("--verify-authorization", action="store_true")
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.promote:
            path = create_authorization(args.runtime_root.resolve())
            print(f"FORMAL_PROMOTION=AUTHORIZED artifact={path}")
        else:
            payload = verify_authorization(args.runtime_root.resolve())
            print(
                "FORMAL_PROMOTION=AUTHORIZED "
                f"release={payload['release_version']} lane={payload['experiment_lane']}"
            )
    except Exception as error:
        print(f"FORMAL_PROMOTION=REJECTED reason={error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
