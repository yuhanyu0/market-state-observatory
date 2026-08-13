from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class RuntimeAlreadyRunning(RuntimeError):
    pass


@dataclass
class RuntimeLock:
    path: Path
    _descriptor: int | None = None

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _remove_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
            age_seconds = time.time() - self.path.stat().st_mtime
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False
        if age_seconds < 15 * 60 or self._pid_running(pid):
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
