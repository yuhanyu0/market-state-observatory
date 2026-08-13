from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

FORBIDDEN_PARTS = {
    ".git", "node_modules", "dist", "test-results", ".cache", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "raw", "secrets", "credentials",
    "data_shadow", "model_shadow", "private",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".env", ".pyc"}


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    rows = [Path(value.decode()) for value in result.stdout.split(b"\0") if value]
    return [path for path in rows if not (set(path.parts) & FORBIDDEN_PARTS) and path.suffix not in FORBIDDEN_SUFFIXES]


def write_zip(target: Path, root: Path, files: list[Path]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(files):
            archive.write(root / relative, relative.as_posix())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "release-artifacts"
    files = tracked_files(root)
    source = output / "market-state-observatory-v0.4.1-source.zip"
    bootstrap = output / "market-state-observatory-v0.4.1-windows-bootstrap.zip"
    write_zip(source, root, files)
    bootstrap_files = [
        path for path in files
        if path.parts[:2] == ("ops", "windows")
        or path.name in {"README.md", "OPERATIONS_RUNBOOK.md", "LICENSE_DECISION.md", "pyproject.toml"}
    ]
    write_zip(bootstrap, root, bootstrap_files)
    if source.stat().st_size >= 5 * 1024 * 1024:
        raise RuntimeError(f"Source archive exceeds 5 MB: {source.stat().st_size}")
    with zipfile.ZipFile(source) as archive:
        rejected = [name for name in archive.namelist() if set(Path(name).parts) & FORBIDDEN_PARTS]
        if rejected:
            raise RuntimeError(f"Forbidden release entries: {rejected[:5]}")
    sums = output / "SHA256SUMS"
    sums.write_text(
        "\n".join(f"{sha256(path)}  {path.name}" for path in (source, bootstrap)) + "\n",
        encoding="ascii",
    )
    print(f"SOURCE_ZIP={source}")
    print(f"SOURCE_ZIP_BYTES={source.stat().st_size}")
    print(f"WINDOWS_BOOTSTRAP_ZIP={bootstrap}")
    print(f"SHA256SUMS={sums}")


if __name__ == "__main__":
    main()
