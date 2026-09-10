import subprocess
from pathlib import Path
from typing import Callable


class GitError(Exception):
    pass


def _run(
    args: list[str], cwd: Path, run: Callable[..., subprocess.CompletedProcess]
) -> subprocess.CompletedProcess:
    # Explicit utf-8, not the locale codec: on a Turkish Windows console
    # that is cp1254, whose decode failures kill the reader thread and
    # leave GitError reporting an empty reason.
    result = run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise GitError(f"{' '.join(args)} (in {cwd}) failed: {result.stderr}")
    return result


def ensure_cloned(
    repo_url: str,
    dest: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    if (dest / ".git").exists():
        _run(["git", "fetch", "origin"], cwd=dest, run=run)
        _run(["git", "checkout", "main"], cwd=dest, run=run)
        _run(["git", "reset", "--hard", "origin/main"], cwd=dest, run=run)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", repo_url, str(dest)], cwd=dest.parent, run=run)


def list_last_n_commits(
    repo_path: Path,
    n: int,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[str]:
    result = _run(
        ["git", "log", "main", f"-{n}", "--format=%H", "--reverse"], cwd=repo_path, run=run
    )
    return [line for line in result.stdout.splitlines() if line]


def checkout(
    repo_path: Path,
    sha: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    _run(["git", "checkout", "--force", sha], cwd=repo_path, run=run)


def commit_date(
    repo_path: Path,
    sha: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    result = _run(["git", "show", "-s", "--format=%cI", sha], cwd=repo_path, run=run)
    return result.stdout.strip()
