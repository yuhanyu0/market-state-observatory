from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


class GitPublicationError(RuntimeError):
    pass


def _git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise GitPublicationError(f"Git publication command failed: git {arguments[0]}")
    return result


def _cleanup_crashed_worktree(repository: Path, worktree: Path) -> None:
    if not worktree.exists():
        return
    if repository.resolve() == worktree.resolve() or repository.resolve() in worktree.resolve().parents:
        raise GitPublicationError("Publication worktree must be outside the source repository")
    _git(repository, "worktree", "remove", "--force", str(worktree), check=False)
    if worktree.exists():
        shutil.rmtree(worktree)


def _push_with_retry(worktree: Path, attempts: int = 3) -> None:
    for attempt in range(1, attempts + 1):
        result = _git(worktree, "push", "origin", "public-data", check=False)
        if result.returncode == 0:
            return
        if attempt < attempts:
            time.sleep(2 ** (attempt - 1))
    raise GitPublicationError(f"Public-data push failed after {attempts} attempts")


def publish_public_data(
    *,
    repository: Path,
    staged_data: Path,
    worktree: Path,
    commit_message: str,
    push: bool,
) -> str:
    if not (repository / ".git").exists():
        raise GitPublicationError("Git repository is not initialized")
    _cleanup_crashed_worktree(repository, worktree)
    _git(repository, "fetch", "origin", "public-data", check=False)
    remote = _git(repository, "show-ref", "--verify", "refs/remotes/origin/public-data", check=False)
    if remote.returncode == 0:
        _git(repository, "worktree", "add", "-B", "public-data", str(worktree), "origin/public-data")
    else:
        _git(repository, "worktree", "add", "--detach", str(worktree), "HEAD")
        _git(worktree, "checkout", "--orphan", "public-data")
        _git(worktree, "rm", "-rf", ".", check=False)
    try:
        destination = worktree / "data"
        destination.mkdir(parents=True, exist_ok=True)
        for path in staged_data.rglob("*"):
            if path.is_file():
                target = destination / path.relative_to(staged_data)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        _git(worktree, "add", "data")
        changes = _git(worktree, "status", "--porcelain").stdout.strip()
        if not changes:
            return "NO_PUBLIC_DATA_CHANGE"
        _git(worktree, "commit", "-m", commit_message)
        if push:
            _push_with_retry(worktree)
        return _git(worktree, "rev-parse", "HEAD").stdout.strip()
    finally:
        _git(repository, "worktree", "remove", "--force", str(worktree), check=False)
