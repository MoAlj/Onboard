from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


class GitCloneError(RuntimeError):
    pass


def is_git_url(value: str) -> bool:
    if value.startswith(("git@", "ssh://")):
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and (
        value.endswith(".git") or "github.com" in parsed.netloc.lower()
    )


@contextmanager
def repo_source(source: str, verbose: bool = False):
    if not is_git_url(source):
        yield Path(source).expanduser()
        return

    temp_dir = Path(tempfile.mkdtemp(prefix="onboard-repo-"))
    clone_path = temp_dir / "repo"
    try:
        _clone_repo(source, clone_path, verbose=verbose)
        yield clone_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _clone_repo(url: str, destination: Path, verbose: bool = False) -> None:
    command = ["git", "clone", "--depth", "1", url, str(destination)]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if verbose and result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git clone error"
        raise GitCloneError(f"Could not clone repository URL: {detail}")
