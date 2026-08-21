import subprocess
from pathlib import Path

import pytest

from winnow.collect.repo import GitError, checkout, commit_date, ensure_cloned, list_last_n_commits


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _make_origin(tmp_path: Path) -> tuple[Path, list[str]]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _run(["git", "init"], cwd=origin)
    _run(["git", "config", "user.email", "test@example.com"], cwd=origin)
    _run(["git", "config", "user.name", "Test"], cwd=origin)

    shas = []
    for i in range(3):
        (origin / f"file{i}.txt").write_text(str(i))
        _run(["git", "add", "."], cwd=origin)
        _run(["git", "commit", "-m", f"commit {i}"], cwd=origin)
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=origin, capture_output=True, text=True, check=True
        )
        shas.append(result.stdout.strip())

    _run(["git", "branch", "-M", "main"], cwd=origin)
    return origin, shas


def test_ensure_cloned_clones_when_absent(tmp_path: Path):
    origin, _ = _make_origin(tmp_path)
    dest = tmp_path / "dest"

    ensure_cloned(str(origin), dest)

    assert (dest / ".git").exists()
    assert (dest / "file2.txt").exists()


def test_ensure_cloned_updates_when_present(tmp_path: Path):
    origin, _ = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    ensure_cloned(str(origin), dest)

    (origin / "file3.txt").write_text("3")
    _run(["git", "add", "."], cwd=origin)
    _run(["git", "commit", "-m", "commit 3"], cwd=origin)

    ensure_cloned(str(origin), dest)

    assert (dest / "file3.txt").exists()


def test_list_last_n_commits_returns_oldest_first(tmp_path: Path):
    origin, shas = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    ensure_cloned(str(origin), dest)

    result = list_last_n_commits(dest, 2)

    assert result == shas[-2:]


def test_checkout_moves_head_to_given_sha(tmp_path: Path):
    origin, shas = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    ensure_cloned(str(origin), dest)

    checkout(dest, shas[0])

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head == shas[0]
    assert not (dest / "file1.txt").exists()


def test_commit_date_returns_iso8601(tmp_path: Path):
    origin, shas = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    ensure_cloned(str(origin), dest)

    date = commit_date(dest, shas[0])

    # ISO 8601 with a timezone offset, e.g. 2026-08-21T12:00:00+00:00
    assert "T" in date
    assert len(date) >= len("2026-08-21T00:00:00+00:00")


def test_checkout_raises_git_error_on_invalid_repo(tmp_path: Path):
    with pytest.raises(GitError):
        checkout(tmp_path, "nonexistent-sha")
