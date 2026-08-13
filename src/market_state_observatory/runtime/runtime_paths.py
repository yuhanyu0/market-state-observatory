from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

RUNTIME_DIRECTORY_NAME = "MarketStateObservatoryRuntime"
RUNTIME_CHILDREN = (
    "secrets",
    "raw",
    "observations",
    "data_shadow",
    "model_shadow",
    "logs",
    "locks",
    "public_staging",
    "backups",
)


class RuntimePathError(ValueError):
    """Raised when private runtime data could land inside the source repository."""


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    secrets: Path
    raw: Path
    observations: Path
    data_shadow: Path
    model_shadow: Path
    logs: Path
    locks: Path
    public_staging: Path
    backups: Path

    def as_public_status(self) -> dict[str, str]:
        return {"runtime_root": str(self.root), "status": "PRIVATE_RUNTIME_RESOLVED"}


def _default_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimePathError("LOCALAPPDATA is unavailable; private runtime path cannot be resolved")
    return Path(local_app_data) / RUNTIME_DIRECTORY_NAME


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_runtime_paths(
    *,
    repo_root: Path | None = None,
    config_path: Path | None = None,
    create: bool = False,
) -> RuntimePaths:
    configured_root: Path | None = None
    if config_path is not None and config_path.is_file():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        value = payload.get("runtime_root")
        if value:
            configured_root = Path(os.path.expandvars(str(value))).expanduser()
    env_root = os.environ.get("MSO_RUNTIME_ROOT")
    root = Path(env_root).expanduser() if env_root else configured_root or _default_root()
    root = root.resolve()
    if not root.is_absolute():
        raise RuntimePathError("Runtime root must be absolute")
    if repo_root is not None and _is_within(root, repo_root.resolve()):
        raise RuntimePathError("Private runtime root must not be inside the Git repository")

    children = {name: root / name for name in RUNTIME_CHILDREN}
    paths = RuntimePaths(root=root, **children)
    if create:
        root.mkdir(parents=True, exist_ok=True)
        for path in children.values():
            path.mkdir(parents=True, exist_ok=True)
    return paths
