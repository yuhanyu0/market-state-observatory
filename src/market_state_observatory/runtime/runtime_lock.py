from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .process_ownership import process_created_at_utc


class RuntimeAlreadyRunning(RuntimeError):
    pass


@dataclass
class RuntimeLock:
    path: Path
    stale_after_seconds: int = 15 * 60
    ownership: dict[str, Any] | None = None
    release_python: str | None = None
    process_executable: str | None = None
    _descriptor: int | None = None

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    @staticmethod
    def _identity_matches(payload: dict[str, Any]) -> bool:
        pid = int(payload["pid"])
        expected = payload.get("process_created_at_utc")
        if not expected:
            return False
        actual = process_created_at_utc(pid)
        if actual is None:
            return False
        expected_time = datetime.fromisoformat(str(expected).replace("Z", "+00:00"))
        actual_time = datetime.fromisoformat(actual.replace("Z", "+00:00"))
        return abs((actual_time - expected_time).total_seconds()) <= 2

    def _remove_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
            age_seconds = time.time() - self.path.stat().st_mtime
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False
        if self._identity_matches(payload):
            return False
        if "process_created_at_utc" not in payload and (
            age_seconds < self.stale_after_seconds or self._pid_running(pid)
        ):
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            if self._remove_stale():
                return self.acquire()
            raise RuntimeAlreadyRunning(f"Runtime lock already exists: {self.path}") from error
        payload = {
            "pid": os.getpid(),
            "acquired_at_utc": datetime.now(UTC).isoformat(),
            "process_created_at_utc": process_created_at_utc(),
            "release_python": self.release_python,
            "process_executable": self.process_executable,
            "ownership_id": (self.ownership or {}).get("ownership_id"),
            "launcher_pid": (self.ownership or {}).get("launcher_pid"),
        }
        os.write(descriptor, (json.dumps(payload, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
        self._descriptor = descriptor

    def release(self) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> RuntimeLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
