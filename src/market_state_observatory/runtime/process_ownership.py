from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .runtime_heartbeat import write_runtime_status


def process_created_at_utc(pid: int | None = None) -> str | None:
    if os.name != "nt":
        return None
    process_id = pid or os.getpid()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        creation_value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        unix_100ns = creation_value - 116444736000000000
        return datetime.fromtimestamp(unix_100ns / 10_000_000, tz=UTC).isoformat()
    finally:
        kernel32.CloseHandle(handle)


def process_executable(pid: int) -> str | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def _identity_live(
    *, pid: object, expected_created: object, expected_executable: object = None
) -> bool:
    if not pid or not expected_created:
        return False
    try:
        process_id = int(str(pid))
        expected = datetime.fromisoformat(str(expected_created).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    actual_created = process_created_at_utc(process_id)
    if actual_created is None:
        return False
    actual = datetime.fromisoformat(actual_created.replace("Z", "+00:00"))
    if abs((actual - expected).total_seconds()) > 2:
        return False
    if expected_executable:
        actual_executable = process_executable(process_id)
        if actual_executable is None:
            return False
        return os.path.normcase(os.path.abspath(actual_executable)) == os.path.normcase(
            os.path.abspath(str(expected_executable))
        )
    return True


def process_is_live(record: dict[str, Any]) -> bool:
    return _identity_live(
        pid=record.get("runtime_pid"),
        expected_created=record.get("runtime_created_at_utc"),
        expected_executable=record.get("process_executable")
        or record.get("release_base_python"),
    )


def launcher_is_live(record: dict[str, Any]) -> bool:
    return _identity_live(
        pid=record.get("launcher_pid"),
        expected_created=record.get("launcher_created_at_utc"),
        expected_executable=record.get("launcher_executable"),
    )


def process_truth(operator_root: Path) -> dict[str, Any]:
    directory = operator_root / "process-ownership"
    records: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            payload["runtime_process_identity_live"] = process_is_live(payload)
            payload["launcher_process_identity_live"] = launcher_is_live(payload)
            payload["process_identity_live"] = bool(
                payload["runtime_process_identity_live"]
                or payload["launcher_process_identity_live"]
            )
            payload["ownership_path"] = str(path)
            records.append(payload)
    active = [row for row in records if row["process_identity_live"]]
    return {
        "state": "ACTIVE_VERIFIED" if active else "INACTIVE",
        "active_count": len(active),
        "active": active,
        "latest": records[-1] if records else None,
    }


def ownership_identity() -> dict[str, Any]:
    return {
        "ownership_id": os.environ.get("MSO_PROCESS_OWNERSHIP_ID"),
        "ownership_path": os.environ.get("MSO_PROCESS_OWNERSHIP_PATH"),
        "launcher_pid": int(os.environ["MSO_LAUNCHER_PID"])
        if os.environ.get("MSO_LAUNCHER_PID")
        else None,
        "runtime_pid": os.getpid(),
        "process_created_at_utc": process_created_at_utc(),
    }


def claim_run(run_id: str) -> dict[str, Any]:
    identity = ownership_identity()
    path_value = identity["ownership_path"]
    if not path_value:
        return identity
    path = Path(str(path_value))
    if not path.is_file():
        raise RuntimeError("Runtime ownership record is missing")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("ownership_id") != identity["ownership_id"]:
        raise RuntimeError("Runtime ownership record identity mismatch")
    if int(payload.get("launcher_pid", 0)) != identity["launcher_pid"]:
        raise RuntimeError("Runtime ownership launcher PID mismatch")
    payload.update(
        {
            "runtime_pid": identity["runtime_pid"],
            "runtime_created_at_utc": identity["process_created_at_utc"],
            "run_id": run_id,
            "status": "RUNNING",
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    write_runtime_status(path, payload)
    return identity
