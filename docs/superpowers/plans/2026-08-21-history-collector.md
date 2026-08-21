# History Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collector that clones `gvergnaud/ts-pattern`, walks its last 30 commits, runs its Jest test suite per test file (for honest test-level coverage attribution) at each commit, and ingests the resulting Cobertura/JUnit reports into the existing SQLite store — producing the first real (non-synthetic) churn/failure-rate history for the risk scorer and future backtesting sub-systems to consume.

**Architecture:** New `winnow/collect/` package (`repo.py` for git operations, `runner.py` for per-test-file Jest invocation, `history.py` for orchestration), depending only on the existing `ingest`/`store` packages — never the reverse. A small standalone Node.js helper at `tools/jest-reporters/` provides a `jest-junit` install once, referenced by absolute path so ts-pattern's own `package.json`/lockfile are never touched.

**Tech Stack:** Python 3.12 (stdlib `subprocess` for git/npm/npx — no new Python dependency), Node.js/npm (already required on the host to run ts-pattern's own suite), `jest-junit` (Node devDependency, installed once).

**Spec:** `docs/superpowers/specs/2026-08-21-history-collector-design.md` (see also the original `docs/superpowers/specs/2026-08-21-winnow-design.md` and `docs/architecture.md`).

## Global Constraints

- Language: Python 3.12+ for all winnow code; the Node.js helper is scoped to `tools/jest-reporters/` only.
- Never modify ts-pattern's own `package.json` or lockfile — `npm ci` only, `jest-junit` is referenced from an external absolute path, never installed into ts-pattern's `node_modules`.
- Test-level coverage attribution is file-granularity, not per-test-case: a test file's coverage report is attributed to every test case (`TestOutcome`) parsed from that same file's run. This is a deliberate, documented approximation — see the spec's Build vs. buy section.
- Error handling: a commit where `npm ci` fails is skipped entirely (logged, loop continues). A test file within a commit that fails to produce both reports is skipped individually (logged, other files in that commit still processed). Nothing propagates past a single commit or single file's failure.
- Every backend change ships with a test. Tests that need real network/npm/jest are marked `@pytest.mark.slow` and excluded from the default `pytest` run (`addopts = "-m 'not slow'"`); `repo.py`'s tests use real `git` subprocess calls against throwaway local repos (no network) and are NOT slow-marked.
- Commit messages: Conventional Commits, English, imperative mood ("Add", "Fix", not "Added"/"Fixed"). Never add an AI co-author trailer.
- Dependency direction: `collect` depends on `ingest` and `store`. Nothing in `ingest`, `store`, or `selection` may import from `collect`.

---

### Task 1: Scaffolding — jest-reporters helper and slow-test marker

**Files:**
- Create: `tools/jest-reporters/package.json`
- Modify: `pyproject.toml`
- Create: `winnow/collect/__init__.py`
- Create: `tests/collect/__init__.py`

**Interfaces:**
- Produces: a `slow` pytest marker (excluded by default), and a place for `jest-junit` to be installed once (`tools/jest-reporters/node_modules/jest-junit`) — Task 4's `run_tests_for_file` will reference `tools/jest-reporters/node_modules/jest-junit/index.js` by absolute path.

- [ ] **Step 1: Create the jest-reporters helper package**

`tools/jest-reporters/package.json`:
```json
{
  "name": "winnow-jest-reporters",
  "private": true,
  "version": "1.0.0",
  "description": "jest-junit installed once and referenced by absolute path from history-collected ts-pattern checkouts, so ts-pattern's own package.json is never touched.",
  "devDependencies": {
    "jest-junit": "^16.0.0"
  }
}
```

- [ ] **Step 2: Add the slow-test marker to pytest config**

Edit `pyproject.toml`'s `[tool.pytest.ini_options]` section to:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: needs real network/npm/jest, excluded by default (run with `pytest -m slow`)",
]
addopts = "-m \"not slow\""
```

- [ ] **Step 3: Create the collect package and test package markers**

`winnow/collect/__init__.py`:
```python
```
(empty file)

`tests/collect/__init__.py`:
```python
```
(empty file)

- [ ] **Step 4: Verify the existing suite is unaffected**

Run: `pytest -v`
Expected: PASS — same 37 tests as before (the new marker doesn't exclude anything yet since no test uses it).

- [ ] **Step 5: Note the manual one-time setup (not automated — needs network)**

Add this line to `tools/jest-reporters/package.json`'s directory by creating `tools/jest-reporters/README.md`:
```md
# jest-reporters helper

One-time setup (not run automatically — needs network access):

```bash
cd tools/jest-reporters
npm install
```

This installs `jest-junit` here so it can be referenced by absolute path
(`tools/jest-reporters/node_modules/jest-junit/index.js`) when running
ts-pattern's own Jest suite — without ever touching ts-pattern's own
`package.json` or lockfile.
```

- [ ] **Step 6: Commit**

```bash
git add tools/jest-reporters/package.json tools/jest-reporters/README.md pyproject.toml winnow/collect/__init__.py tests/collect/__init__.py
git commit -m "chore: scaffold jest-reporters helper and slow-test marker"
```

---

### Task 2: `collect/repo.py` — git operations

**Files:**
- Create: `winnow/collect/repo.py`
- Test: `tests/collect/test_repo.py`

**Interfaces:**
- Produces: `GitError(Exception)`, `ensure_cloned(repo_url: str, dest: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None`, `list_last_n_commits(repo_path: Path, n: int, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]` (oldest-first), `checkout(repo_path: Path, sha: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None`, `commit_date(repo_path: Path, sha: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str` (ISO 8601) — Task 5's `history.py` calls all four by these exact names.

- [ ] **Step 1: Write the failing tests**

`tests/collect/test_repo.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/collect/test_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.collect.repo'`

- [ ] **Step 3: Write minimal implementation**

`winnow/collect/repo.py`:
```python
import subprocess
from pathlib import Path
from typing import Callable


class GitError(Exception):
    pass


def _run(
    args: list[str], cwd: Path, run: Callable[..., subprocess.CompletedProcess]
) -> subprocess.CompletedProcess:
    result = run(args, cwd=cwd, capture_output=True, text=True)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/collect/test_repo.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/repo.py tests/collect/test_repo.py
git commit -m "feat: add git operations for the history collector"
```

---

### Task 3: `collect/runner.py` — test discovery and install

**Files:**
- Create: `winnow/collect/runner.py`
- Test: `tests/collect/test_runner_setup.py`

**Interfaces:**
- Produces: `InstallResult(succeeded: bool, reason: str | None = None)`, `install(repo_path: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> InstallResult`, `list_test_files(repo_path: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]` — Task 5's `history.py` calls both by these exact names.

- [ ] **Step 1: Write the failing tests**

`tests/collect/test_runner_setup.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock

from winnow.collect.runner import install, list_test_files


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_install_succeeds_when_npm_ci_returns_zero(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=0))

    result = install(tmp_path, run=fake_run)

    assert result.succeeded is True
    assert result.reason is None
    fake_run.assert_called_once()
    args, kwargs = fake_run.call_args
    assert args[0] == ["npm", "ci"]
    assert kwargs["cwd"] == tmp_path


def test_install_fails_when_npm_ci_returns_nonzero(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=1, stderr="network error"))

    result = install(tmp_path, run=fake_run)

    assert result.succeeded is False
    assert "npm ci failed" in result.reason
    assert "network error" in result.reason


def test_list_test_files_parses_newline_separated_output(tmp_path: Path):
    fake_run = MagicMock(
        return_value=_completed(
            returncode=0, stdout="/repo/src/a.test.ts\n/repo/src/b.test.ts\n"
        )
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == ["/repo/src/a.test.ts", "/repo/src/b.test.ts"]
    args, kwargs = fake_run.call_args
    assert args[0] == ["npx", "jest", "--listTests"]
    assert kwargs["cwd"] == tmp_path


def test_list_test_files_ignores_blank_lines(tmp_path: Path):
    fake_run = MagicMock(
        return_value=_completed(returncode=0, stdout="/repo/src/a.test.ts\n\n")
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == ["/repo/src/a.test.ts"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/collect/test_runner_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.collect.runner'`

- [ ] **Step 3: Write minimal implementation**

`winnow/collect/runner.py`:
```python
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class InstallResult:
    succeeded: bool
    reason: str | None = None


def install(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> InstallResult:
    result = run(["npm", "ci"], cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        return InstallResult(succeeded=False, reason=f"npm ci failed: {result.stderr[-500:]}")
    return InstallResult(succeeded=True)


def list_test_files(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[str]:
    result = run(
        ["npx", "jest", "--listTests"], cwd=repo_path, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/collect/test_runner_setup.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/runner.py tests/collect/test_runner_setup.py
git commit -m "feat: add npm install and Jest test-file discovery"
```

---

### Task 4: `collect/runner.py` — per-test-file execution

**Files:**
- Modify: `winnow/collect/runner.py`
- Test: `tests/collect/test_runner_execution.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks (adds to the same module as Task 3)
- Produces: `RunResult(coverage_path: Path | None, junit_path: Path | None, skipped: bool, reason: str | None = None)`, `run_tests_for_file(repo_path: Path, test_file: str, output_dir: Path, jest_junit_reporter_path: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> RunResult` — Task 5's `history.py` calls this by this exact name and reads `.coverage_path`/`.junit_path`/`.skipped`/`.reason`.

- [ ] **Step 1: Write the failing tests**

`tests/collect/test_runner_execution.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock

from winnow.collect.runner import run_tests_for_file


def _completed(returncode: int = 0, stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


def test_run_tests_for_file_skips_when_reports_missing(tmp_path: Path):
    output_dir = tmp_path / "out"
    fake_run = MagicMock(return_value=_completed(returncode=1, stderr="jest crashed"))

    result = run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    assert result.skipped is True
    assert result.coverage_path is None
    assert result.junit_path is None
    assert "did not produce reports" in result.reason
    assert "src/a.test.ts" in result.reason


def test_run_tests_for_file_succeeds_when_reports_exist(tmp_path: Path):
    output_dir = tmp_path / "out"

    def fake_run(args, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "cobertura-coverage.xml").write_text("<coverage/>")
        (output_dir / "junit.xml").write_text("<testsuites/>")
        return _completed(returncode=0)

    result = run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    assert result.skipped is False
    assert result.coverage_path == output_dir / "cobertura-coverage.xml"
    assert result.junit_path == output_dir / "junit.xml"


def test_run_tests_for_file_invokes_jest_with_expected_flags(tmp_path: Path):
    output_dir = tmp_path / "out"
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        return _completed(returncode=1)  # reports won't exist; we only check the invocation

    run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    args = captured["args"]
    assert args[0:2] == ["npx", "jest"]
    assert "--runTestsByPath" in args
    assert "src/a.test.ts" in args
    assert "--coverage" in args
    assert f"--coverageDirectory={output_dir}" in args
    assert "--coverageReporters=cobertura" in args
    assert any(a.startswith("--reporters=") and "jest-junit" in a for a in args)
    assert captured["cwd"] == tmp_path
    assert captured["env"]["JEST_JUNIT_OUTPUT_DIR"] == str(output_dir)
    assert captured["env"]["JEST_JUNIT_OUTPUT_NAME"] == "junit.xml"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/collect/test_runner_execution.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_tests_for_file'`

- [ ] **Step 3: Write minimal implementation**

Append to `winnow/collect/runner.py` (add `os` to the existing imports):
```python
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class RunResult:
    coverage_path: Path | None
    junit_path: Path | None
    skipped: bool
    reason: str | None = None


def run_tests_for_file(
    repo_path: Path,
    test_file: str,
    output_dir: Path,
    jest_junit_reporter_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> RunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = output_dir / "cobertura-coverage.xml"
    junit_path = output_dir / "junit.xml"

    env = {
        **os.environ,
        "JEST_JUNIT_OUTPUT_DIR": str(output_dir),
        "JEST_JUNIT_OUTPUT_NAME": junit_path.name,
    }

    result = run(
        [
            "npx",
            "jest",
            "--runTestsByPath",
            test_file,
            "--coverage",
            f"--coverageDirectory={output_dir}",
            "--coverageReporters=cobertura",
            "--reporters=default",
            f"--reporters={jest_junit_reporter_path}",
        ],
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
    )

    if not coverage_path.exists() or not junit_path.exists():
        return RunResult(
            None,
            None,
            skipped=True,
            reason=f"jest did not produce reports for {test_file}: {result.stderr[-500:]}",
        )

    return RunResult(coverage_path, junit_path, skipped=False)
```

Note: the full updated file has both `InstallResult`/`install`/`list_test_files` (from Task 3) and `RunResult`/`run_tests_for_file` (this task) — merge the imports (`os`, `subprocess`, `dataclass`, `Path`, `Callable`) at the top rather than duplicating them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/collect/test_runner_execution.py -v`
Expected: PASS (3 passed)

Run: `pytest tests/collect/ -v`
Expected: PASS (all Task 2-4 tests together, no regressions)

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/runner.py tests/collect/test_runner_execution.py
git commit -m "feat: add per-test-file Jest execution with coverage and JUnit output"
```

---

### Task 5: `collect/history.py` — orchestration

**Files:**
- Create: `winnow/collect/history.py`
- Test: `tests/collect/test_history.py`

**Interfaces:**
- Consumes: `ensure_cloned`, `list_last_n_commits`, `checkout`, `commit_date` (Task 2); `install`, `list_test_files`, `run_tests_for_file`, `RunResult` (Tasks 3-4); `CoberturaParser` (core engine Task 4), `JUnitParser` (core engine Task 5); `CommitRepository`, `CoverageRepository`, `TestOutcomeRepository` (core engine Task 7)
- Produces: `CollectionResult(collected: tuple[str, ...], skipped_commits: tuple[tuple[str, str], ...], skipped_files: tuple[tuple[str, str, str], ...])`, `collect_history(repo_url, clone_dest, output_root, jest_junit_reporter_path, commit_repo, coverage_repo, outcome_repo, num_commits=30, ensure_cloned=..., list_last_n_commits=..., checkout=..., commit_date=..., install=..., list_test_files=..., run_tests_for_file=...) -> CollectionResult` — this is the plan's proof-of-correctness deliverable, exercised end to end in Task 6.

- [ ] **Step 1: Write the failing tests**

`tests/collect/test_history.py`:
```python
from pathlib import Path

from winnow.collect.history import CollectionResult, collect_history
from winnow.collect.runner import InstallResult, RunResult
from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db


def _repos(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    return CommitRepository(conn), CoverageRepository(conn), TestOutcomeRepository(conn)


def _write_fixture_reports(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cobertura-coverage.xml").write_text(
        """<?xml version="1.0"?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class name="a" filename="src/a.ts">
          <lines><line number="1" hits="1"/></lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""
    )
    (output_dir / "junit.xml").write_text(
        """<?xml version="1.0"?>
<testsuites>
  <testsuite name="jest">
    <testcase classname="a.test" name="works" time="0.01"/>
  </testsuite>
</testsuites>
"""
    )


def test_collect_history_ingests_successful_commits(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"
    output_root = tmp_path / "out"

    fake_ensure_cloned = lambda repo_url, dest: None
    fake_list_commits = lambda repo_path, n: ["sha1"]
    fake_checkout = lambda repo_path, sha: None
    fake_commit_date = lambda repo_path, sha: "2026-08-01T00:00:00+00:00"
    fake_install = lambda repo_path: InstallResult(succeeded=True)
    fake_list_test_files = lambda repo_path: ["src/a.test.ts"]

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        _write_fixture_reports(output_dir)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=clone_dest,
        output_root=output_root,
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=fake_ensure_cloned,
        list_last_n_commits=fake_list_commits,
        checkout=fake_checkout,
        commit_date=fake_commit_date,
        install=fake_install,
        list_test_files=fake_list_test_files,
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    assert result.skipped_commits == ()
    assert commit_repo.get_recent(1) == ["sha1"]
    assert coverage_repo.tests_covering_file("src/a.ts") == {"a.test.works"}
    assert outcome_repo.all_test_ids() == {"a.test.works"}


def test_collect_history_skips_commit_when_install_fails(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=tmp_path / "repo",
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=False, reason="npm ci failed: boom"),
        list_test_files=lambda repo_path: ["src/a.test.ts"],
        run_tests_for_file=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("should not be called when install fails")
        ),
    )

    assert result.collected == ()
    assert result.skipped_commits == (("sha1", "npm ci failed: boom"),)
    assert commit_repo.get_recent(1) == []


def test_collect_history_skips_individual_failed_test_file_but_keeps_commit(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        if test_file == "src/good.test.ts":
            _write_fixture_reports(output_dir)
            return RunResult(
                output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
            )
        return RunResult(None, None, skipped=True, reason="jest crashed")

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=tmp_path / "repo",
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=True),
        list_test_files=lambda repo_path: ["src/good.test.ts", "src/bad.test.ts"],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    assert result.skipped_files == (("sha1", "src/bad.test.ts", "jest crashed"),)
    assert coverage_repo.tests_covering_file("src/a.ts") == {"a.test.works"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/collect/test_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.collect.history'`

- [ ] **Step 3: Write minimal implementation**

`winnow/collect/history.py`:
```python
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from winnow.collect import repo as repo_ops
from winnow.collect import runner as runner_ops
from winnow.collect.runner import InstallResult, RunResult
from winnow.ingest.cobertura import CoberturaParser
from winnow.ingest.junit import JUnitParser
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository


@dataclass(frozen=True)
class CollectionResult:
    collected: tuple[str, ...]
    skipped_commits: tuple[tuple[str, str], ...]
    skipped_files: tuple[tuple[str, str, str], ...]


def collect_history(
    repo_url: str,
    clone_dest: Path,
    output_root: Path,
    jest_junit_reporter_path: Path,
    commit_repo: CommitRepository,
    coverage_repo: CoverageRepository,
    outcome_repo: TestOutcomeRepository,
    num_commits: int = 30,
    ensure_cloned: Callable[[str, Path], None] = repo_ops.ensure_cloned,
    list_last_n_commits: Callable[[Path, int], list[str]] = repo_ops.list_last_n_commits,
    checkout: Callable[[Path, str], None] = repo_ops.checkout,
    commit_date: Callable[[Path, str], str] = repo_ops.commit_date,
    install: Callable[[Path], InstallResult] = runner_ops.install,
    list_test_files: Callable[[Path], list[str]] = runner_ops.list_test_files,
    run_tests_for_file: Callable[..., RunResult] = runner_ops.run_tests_for_file,
) -> CollectionResult:
    ensure_cloned(repo_url, clone_dest)
    shas = list_last_n_commits(clone_dest, num_commits)

    cobertura_parser = CoberturaParser()
    junit_parser = JUnitParser()

    collected: list[str] = []
    skipped_commits: list[tuple[str, str]] = []
    skipped_files: list[tuple[str, str, str]] = []

    for sha in shas:
        checkout(clone_dest, sha)

        install_result = install(clone_dest)
        if not install_result.succeeded:
            skipped_commits.append((sha, install_result.reason or "unknown"))
            continue

        test_files = list_test_files(clone_dest)
        commit_repo.add(sha, commit_date(clone_dest, sha))

        any_file_succeeded = False
        for test_file in test_files:
            output_dir = output_root / sha
            run_result = run_tests_for_file(
                clone_dest, test_file, output_dir, jest_junit_reporter_path
            )

            if run_result.skipped:
                skipped_files.append((sha, test_file, run_result.reason or "unknown"))
                continue

            coverage_report = cobertura_parser.parse(run_result.coverage_path)
            outcomes = junit_parser.parse(run_result.junit_path)

            for outcome in outcomes:
                coverage_repo.add_coverage(sha, outcome.test_id, coverage_report)
            outcome_repo.add_outcomes(sha, outcomes)
            any_file_succeeded = True

        if any_file_succeeded:
            collected.append(sha)

    return CollectionResult(
        collected=tuple(collected),
        skipped_commits=tuple(skipped_commits),
        skipped_files=tuple(skipped_files),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/collect/test_history.py -v`
Expected: PASS (3 passed)

Run: `pytest -v`
Expected: all tests pass (default run, `slow`-marked tests excluded — none exist yet)

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/history.py tests/collect/test_history.py
git commit -m "feat: add history collection orchestration with skip-and-continue error handling"
```

---

### Task 6: Slow integration test against the real ts-pattern clone

**Files:**
- Create: `tests/collect/test_integration_ts_pattern.py`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: `collect_history` (Task 5), all of Tasks 2-4's real (non-faked) functions
- Produces: nothing new — this is the plan's end-to-end proof, run manually (`pytest -m slow`) since it needs network, `npm`, and `node` on the host.

- [ ] **Step 1: Write the test**

`tests/collect/test_integration_ts_pattern.py`:
```python
from pathlib import Path

import pytest

from winnow.collect.history import collect_history
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db

TS_PATTERN_URL = "https://github.com/gvergnaud/ts-pattern.git"
JEST_JUNIT_REPORTER = (
    Path(__file__).parent.parent.parent
    / "tools"
    / "jest-reporters"
    / "node_modules"
    / "jest-junit"
    / "index.js"
)


@pytest.mark.slow
def test_collect_history_against_real_ts_pattern(tmp_path: Path):
    if not JEST_JUNIT_REPORTER.exists():
        pytest.skip(
            "jest-junit not installed — run `npm install` in tools/jest-reporters first"
        )

    conn = init_db(tmp_path / "winnow.db")
    commit_repo = CommitRepository(conn)
    coverage_repo = CoverageRepository(conn)
    outcome_repo = TestOutcomeRepository(conn)

    result = collect_history(
        repo_url=TS_PATTERN_URL,
        clone_dest=tmp_path / "ts-pattern",
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=JEST_JUNIT_REPORTER,
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=2,
    )

    assert len(result.collected) >= 1, (
        f"expected at least 1 collected commit, got 0. "
        f"skipped_commits={result.skipped_commits}, skipped_files={result.skipped_files}"
    )
    assert commit_repo.get_recent(2)
    assert outcome_repo.all_test_ids()
```

- [ ] **Step 2: Run it manually (requires network, npm, node, and a one-time `npm install` in tools/jest-reporters)**

Run: `pytest -m slow tests/collect/test_integration_ts_pattern.py -v`
Expected: PASS (1 passed) if `tools/jest-reporters/node_modules/jest-junit` exists; otherwise SKIPPED with the reason printed above — both are acceptable outcomes for this manual-only test, but if it runs, it must pass.

- [ ] **Step 3: Confirm the default fast suite still excludes it**

Run: `pytest -v`
Expected: the new integration test does NOT appear in the run (excluded by the `slow` marker's `addopts`); all previously-passing tests still pass.

- [ ] **Step 4: Update HANDOFF.md**

Replace the "Şu an ne yapılıyor" / "Sıradaki somut adım" sections in `HANDOFF.md` to reflect that the history collector (first of four follow-up sub-systems) is built and validated against the real `ts-pattern` repo, and that mutation-based ground truth (`winnow/backtest/` + Stryker) is the next sub-system to design, once this one has run and real history data exists to inspect.

- [ ] **Step 5: Commit**

```bash
git add tests/collect/test_integration_ts_pattern.py HANDOFF.md
git commit -m "test: add slow integration test collecting real ts-pattern history"
```
