from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GitPublicationError(RuntimeError):
    pass


def _github_cli() -> str:
    command = shutil.which("gh")
    if command:
        return command
    if os.name == "nt":
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        candidate = program_files / "GitHub CLI" / "gh.exe"
        if candidate.is_file():
            return str(candidate)
    raise GitPublicationError("GitHub CLI is unavailable; public-data push is blocked")


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


def _dispatch_pages(repository: Path) -> None:
    result = subprocess.run(
        [_github_cli(), "workflow", "run", "pages.yml", "--ref", "main"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise GitPublicationError("Public data pushed but Pages workflow dispatch failed")


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
    if worktree.exists():
        raise GitPublicationError("Publication worktree path already exists")
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
            _git(worktree, "push", "origin", "public-data")
            _dispatch_pages(repository)
        return _git(worktree, "rev-parse", "HEAD").stdout.strip()
    finally:
        _git(repository, "worktree", "remove", "--force", str(worktree), check=False)
