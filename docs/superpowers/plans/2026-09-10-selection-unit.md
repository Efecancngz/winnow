# Selection Unit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Winnow's selection unit from the test case to the test file, so that the unit it selects matches the unit CI is billed for, and so the store stops asserting a per-case attribution Jest never produced.

**Architecture:** `test_file` (a repo-root-relative POSIX path) replaces `test_id` as the key of the whole selection chain — `test_files_covering` → `must_run_tests` → `SelectionPipeline` → `RiskScorer` → `failure_rate`. Coverage is written once per `(commit_sha, test_file, file_path)`, enforced by a `UNIQUE` constraint rather than by discipline in a loop. `test_outcomes` stays case-level (renamed `case_id`) and gains a `test_file` column; the file-level failure rate is an aggregation over those rows, excluding permanently-failing cases that have enough observations to judge.

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), pytest, junitparser. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-09-10-selection-unit-design.md`](../specs/2026-09-10-selection-unit-design.md)

## Global Constraints

- **Test-first.** Every code step is preceded by a failing test and a run that confirms it fails for the expected reason.
- **`test_file` is always a repo-root-relative POSIX path** — no drive letters, no backslashes, no leading `/`. This is the same coordinate system as Cobertura's `file_path` and git diff paths.
- **`case_id` is the case-level identity** (JUnit `classname.name`). The name `test_id` is retired entirely — after this plan, `grep -rn "test_id" winnow/ tools/ tests/` returns nothing.
- **No migration.** `data/*/` is gitignored and holds 3 throwaway mobx commits. Re-collection replaces them.
- **No performance claim without a measurement.** Index usage is confirmed with `EXPLAIN QUERY PLAN`; no speedup figure is written down unless it was timed.
- **Commit message rule for this repo:** no `Co-Authored-By` trailer, no session trailer.
- Run the full suite with `pytest` (slow tests are excluded by `addopts`). Run slow tests explicitly with `pytest -m slow`.

---

### Task 1: Repo-relative POSIX path normalization

Jest's `--listTests` emits absolute host-separator paths (`C:\...\packages\mobx\__tests__\v5\base\api.js`). Everything else in the store is repo-relative POSIX. This helper is the single conversion point.

A mismatch here produces no error — it makes every lookup miss, the selector falls back to the full suite, and the run reports success. That is why the out-of-root case raises instead of passing the path through.

**Files:**
- Create: `winnow/collect/paths.py`
- Test: `tests/collect/test_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces: `relative_posix(repo_root: Path, path: str) -> str`, raises `ValueError` when `path` is not inside `repo_root`

- [ ] **Step 1: Write the failing tests**

```python
# tests/collect/test_paths.py
from pathlib import Path

import pytest

from winnow.collect.paths import relative_posix


def test_windows_absolute_path_becomes_repo_relative_posix():
    root = Path(r"C:\dev\winnow\data\mobx\repo")
    given = r"C:\dev\winnow\data\mobx\repo\packages\mobx\__tests__\v5\base\api.js"

    assert relative_posix(root, given) == "packages/mobx/__tests__/v5/base/api.js"


def test_posix_absolute_path_becomes_repo_relative():
    root = Path("/home/e/winnow/data/mobx/repo")
    given = "/home/e/winnow/data/mobx/repo/packages/mobx/src/api.ts"

    assert relative_posix(root, given) == "packages/mobx/src/api.ts"


def test_drive_letter_case_difference_still_matches():
    """node prints a lowercased drive letter on some Windows setups, while
    pathlib keeps whatever the caller wrote. A case-sensitive prefix compare
    would silently store an absolute path and break every later lookup."""
    root = Path(r"C:\dev\winnow\repo")
    given = r"c:\dev\winnow\repo\test\a.test.js"

    assert relative_posix(root, given) == "test/a.test.js"


def test_path_outside_the_repo_root_raises():
    root = Path("/home/e/winnow/data/mobx/repo")

    with pytest.raises(ValueError, match="outside"):
        relative_posix(root, "/etc/passwd")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/collect/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'winnow.collect.paths'`

- [ ] **Step 3: Write the implementation**

```python
# winnow/collect/paths.py
"""One conversion point between jest's absolute host paths and the
repo-relative posix paths every other table stores.

Getting this wrong raises nothing: the selector simply matches no rows,
falls back to the full suite, and reports success. Same failure shape as
the Cobertura backslash defect.
"""

from pathlib import Path


def relative_posix(repo_root: Path, path: str) -> str:
    normalized = str(path).replace("\\", "/")
    root = str(repo_root).replace("\\", "/").rstrip("/")

    # casefold, not ==: node sometimes lowercases the Windows drive letter
    # while pathlib preserves the caller's casing.
    if normalized.casefold().startswith(root.casefold() + "/"):
        return normalized[len(root) + 1 :]

    raise ValueError(f"path {path!r} is outside repo root {repo_root!r}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/collect/test_paths.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/paths.py tests/collect/test_paths.py
git commit -m "feat(paths): convert jest absolute paths to repo-relative posix"
```

---

### Task 2: Coverage store keyed on the test file

The 26× duplication and the false per-case claim both live here. The `UNIQUE` constraint is the part that matters: it turns a future regression into an `IntegrityError` at the first insert instead of a silent return of the original bug.

Note for the executor: because inserts now raise on duplicates, re-running collection into an existing database will fail. That is intended — delete `data/<repo>/winnow.db` before a re-collection.

**Files:**
- Modify: `winnow/store/schema.py`
- Modify: `winnow/store/repository.py` (class `CoverageRepository`)
- Test: `tests/store/test_repository.py`, `tests/store/test_schema.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `CoverageRepository.add_coverage(commit_sha: str, test_file: str, report: CoverageReport) -> None`
  - `CoverageRepository.test_files_covering(file_path: str, changed_lines: frozenset[int] | None = None) -> set[str]`
  - `CoverageRepository.is_known_file(file_path: str) -> bool` (unchanged)

- [ ] **Step 1: Write the failing tests**

Replace the three coverage tests in `tests/store/test_repository.py` (`test_coverage_repository_tests_covering_file`, `..._falls_back_when_lines_dont_intersect`, `..._is_known_file`) with these, and add the duplicate-rejection test:

```python
# tests/store/test_repository.py  (coverage section)
import sqlite3

import pytest

from winnow.ingest.models import CoverageReport, FileCoverage


def test_coverage_repository_test_files_covering(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1, 2, 3})),))
    repo.add_coverage("sha1", "test/a.test.js", report)

    assert repo.test_files_covering("module_a.py") == {"test/a.test.js"}
    assert repo.test_files_covering(
        "module_a.py", changed_lines=frozenset({2})
    ) == {"test/a.test.js"}


def test_coverage_repository_falls_back_when_lines_dont_intersect(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1, 2, 3})),))
    repo.add_coverage("sha1", "test/a.test.js", report)

    # No recorded line intersects the change, but the file is covered by this
    # test file -> fall back to the file-level set rather than returning
    # nothing, which the selector would read as "no tests needed".
    assert repo.test_files_covering(
        "module_a.py", changed_lines=frozenset({99})
    ) == {"test/a.test.js"}


def test_coverage_repository_is_known_file(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1})),))
    repo.add_coverage("sha1", "test/a.test.js", report)

    assert repo.is_known_file("module_a.py") is True
    assert repo.is_known_file("module_unknown.py") is False


def test_coverage_rows_are_unique_per_commit_test_file_and_source_file(tmp_path: Path):
    """The 26x bloat came from writing this row once per test case. The
    constraint makes that regression loud instead of silent."""
    repo = CoverageRepository(_conn(tmp_path))
    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1})),))

    repo.add_coverage("sha1", "test/a.test.js", report)

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_coverage("sha1", "test/a.test.js", report)


def test_same_source_file_may_be_covered_by_several_test_files(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))
    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1})),))

    repo.add_coverage("sha1", "test/a.test.js", report)
    repo.add_coverage("sha1", "test/b.test.js", report)

    assert repo.test_files_covering("module_a.py") == {"test/a.test.js", "test/b.test.js"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/store/test_repository.py -v`
Expected: FAIL — `AttributeError: 'CoverageRepository' object has no attribute 'test_files_covering'`, and the uniqueness test fails because no constraint exists.

- [ ] **Step 3: Update the schema**

```python
# winnow/store/schema.py
SCHEMA = """
CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_coverage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_file TEXT NOT NULL,
    file_path TEXT NOT NULL,
    covered_lines TEXT NOT NULL,
    UNIQUE (commit_sha, test_file, file_path)
);

CREATE INDEX IF NOT EXISTS idx_test_coverage_file_path
    ON test_coverage (file_path);

CREATE TABLE IF NOT EXISTS test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);
"""
```

(`test_outcomes` is left alone here — Task 3 owns it. Keeping the two table changes in separate commits keeps each reviewable.)

- [ ] **Step 4: Update `CoverageRepository`**

```python
# winnow/store/repository.py
class CoverageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_coverage(self, commit_sha: str, test_file: str, report: CoverageReport) -> None:
        """One row per (commit, test file, source file).

        Jest produces coverage per test FILE, never per test case. Writing a
        row per case claimed an attribution that was never collected -- and
        cost 26x the space saying it.
        """
        for file_cov in report.files:
            lines_csv = ",".join(str(n) for n in sorted(file_cov.covered_lines))
            self._conn.execute(
                """INSERT INTO test_coverage (commit_sha, test_file, file_path, covered_lines)
                   VALUES (?, ?, ?, ?)""",
                (commit_sha, test_file, file_cov.file_path, lines_csv),
            )
        self._conn.commit()

    def is_known_file(self, file_path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM test_coverage WHERE file_path = ? LIMIT 1",
            (file_path,),
        ).fetchone()
        return row is not None

    def test_files_covering(
        self, file_path: str, changed_lines: frozenset[int] | None = None
    ) -> set[str]:
        rows = self._conn.execute(
            "SELECT test_file, covered_lines FROM test_coverage WHERE file_path = ?",
            (file_path,),
        ).fetchall()

        matched: set[str] = set()
        all_test_files: set[str] = set()
        for test_file, lines_csv in rows:
            all_test_files.add(test_file)
            if changed_lines is None:
                matched.add(test_file)
                continue
            covered = {int(n) for n in lines_csv.split(",") if n}
            if covered & changed_lines:
                matched.add(test_file)

        if changed_lines is not None and not matched and all_test_files:
            return all_test_files
        return matched
```

- [ ] **Step 5: Run the store tests**

Run: `pytest tests/store/ -v`
Expected: PASS. `tests/store/test_schema.py` may assert on column names — update it to the new `test_coverage` columns if it fails.

- [ ] **Step 6: Confirm the index is actually used**

Run:

```bash
python -c "
from winnow.store.schema import init_db
c = init_db(__import__('pathlib').Path('/tmp/winnow-plan-check.db'))
for r in c.execute('EXPLAIN QUERY PLAN SELECT test_file, covered_lines FROM test_coverage WHERE file_path = ?', ('x',)):
    print(r)
"
```

Expected: the plan mentions `USING INDEX idx_test_coverage_file_path`. If it says `SCAN test_coverage`, stop and report — do not proceed and do not claim an improvement.

- [ ] **Step 7: Commit**

```bash
git add winnow/store/schema.py winnow/store/repository.py tests/store/
git commit -m "feat(store): key coverage on the test file, enforced by a unique constraint"
```

---

### Task 3: Outcomes keyed on case, aggregated to the file

`test_outcomes` keeps one honest row per case — JUnit really does produce that — and gains the `test_file` it belongs to. `failure_rate` becomes an aggregation.

**Definition (from the spec):** the file-level failure rate is *the fraction of commits in which this test file had at least one failing case.* The rejected alternative — fraction of failing case-runs — scores a file with one permanently broken case out of 88 at 0.011, indistinguishable from a healthy file.

**Files:**
- Modify: `winnow/store/schema.py` (`test_outcomes`)
- Modify: `winnow/ingest/models.py` (`TestOutcome.test_id` → `case_id`)
- Modify: `winnow/ingest/junit.py`
- Modify: `winnow/store/repository.py` (class `TestOutcomeRepository`)
- Test: `tests/store/test_repository.py`, `tests/ingest/test_models.py`, `tests/ingest/test_junit.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `TestOutcome(case_id: str, passed: bool, duration_seconds: float)`
  - `TestOutcomeRepository.add_outcomes(commit_sha: str, test_file: str, outcomes: list[TestOutcome]) -> None`
  - `TestOutcomeRepository.failure_rate(test_file: str) -> float`
  - `TestOutcomeRepository.all_test_files() -> set[str]`

- [ ] **Step 1: Write the failing tests**

Replace `test_test_outcome_repository_failure_rate` and `test_test_outcome_repository_all_test_ids` in `tests/store/test_repository.py`:

```python
# tests/store/test_repository.py  (outcomes section)
def test_failure_rate_counts_commits_where_the_file_had_any_failing_case(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    # sha1: one of two cases fails -> the file failed at sha1
    repo.add_outcomes(
        "sha1",
        "test/a.test.js",
        [
            TestOutcome("a.test.works", passed=True, duration_seconds=0.1),
            TestOutcome("a.test.broken", passed=False, duration_seconds=0.1),
        ],
    )
    # sha2: both pass -> the file did not fail at sha2
    repo.add_outcomes(
        "sha2",
        "test/a.test.js",
        [
            TestOutcome("a.test.works", passed=True, duration_seconds=0.1),
            TestOutcome("a.test.broken", passed=True, duration_seconds=0.1),
        ],
    )

    # 1 failing commit out of 2 -- NOT 1 failing case out of 4 (0.25)
    assert repo.failure_rate("test/a.test.js") == 0.5


def test_failure_rate_is_zero_for_an_unknown_file(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    assert repo.failure_rate("test/never-seen.test.js") == 0.0


def test_all_test_files(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    repo.add_outcomes(
        "sha1", "test/a.test.js", [TestOutcome("a.works", passed=True, duration_seconds=0.1)]
    )
    repo.add_outcomes(
        "sha1", "test/b.test.js", [TestOutcome("b.works", passed=True, duration_seconds=0.1)]
    )

    assert repo.all_test_files() == {"test/a.test.js", "test/b.test.js"}
```

And in `tests/ingest/test_models.py`, replace the `TestOutcome` assertions:

```python
def test_test_outcome_carries_the_case_identity():
    outcome = TestOutcome(case_id="a.test.foo", passed=False, duration_seconds=0.42)

    assert outcome.case_id == "a.test.foo"
    assert outcome.passed is False
```

In `tests/ingest/test_junit.py`, change every `outcome.test_id` assertion to `outcome.case_id` (the produced values are unchanged — still `classname.name`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/store/test_repository.py tests/ingest/ -v`
Expected: FAIL — `TypeError: TestOutcome.__init__() got an unexpected keyword argument 'case_id'` and `add_outcomes() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Update the model and the JUnit parser**

```python
# winnow/ingest/models.py
@dataclass(frozen=True)
class TestOutcome:
    case_id: str
    passed: bool
    duration_seconds: float
```

```python
# winnow/ingest/junit.py  (inside the case loop)
                case_id = f"{case.classname}.{case.name}"
                passed = not any(isinstance(r, (Failure, Error)) for r in case.result)
                outcomes.append(
                    TestOutcome(
                        case_id=case_id,
                        passed=passed,
                        duration_seconds=case.time or 0.0,
                    )
                )
```

- [ ] **Step 4: Update the schema**

```python
# winnow/store/schema.py  (test_outcomes only)
CREATE TABLE IF NOT EXISTS test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_file TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_test_outcomes_test_file
    ON test_outcomes (test_file);
```

- [ ] **Step 5: Update `TestOutcomeRepository`**

```python
# winnow/store/repository.py
class TestOutcomeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_outcomes(
        self, commit_sha: str, test_file: str, outcomes: list[TestOutcome]
    ) -> None:
        self._conn.executemany(
            """INSERT INTO test_outcomes
                   (commit_sha, test_file, case_id, passed, duration_seconds)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (commit_sha, test_file, o.case_id, int(o.passed), o.duration_seconds)
                for o in outcomes
            ],
        )
        self._conn.commit()

    def failure_rate(self, test_file: str) -> float:
        """Fraction of commits in which this file had at least one failing case.

        Not the fraction of failing case-runs: a file with one permanently
        broken case out of 88 would score 0.011 under that definition and be
        indistinguishable from a healthy file. The question the scorer asks is
        "is it worth running this file", so the label is "did running it
        surface a failure".
        """
        rows = self._conn.execute(
            """SELECT commit_sha, MIN(passed)
               FROM test_outcomes
               WHERE test_file = ?
               GROUP BY commit_sha""",
            (test_file,),
        ).fetchall()
        if not rows:
            return 0.0
        failed_commits = sum(1 for (_sha, min_passed) in rows if min_passed == 0)
        return failed_commits / len(rows)

    def all_test_files(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT test_file FROM test_outcomes").fetchall()
        return {row[0] for row in rows}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/store/ tests/ingest/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add winnow/store/ winnow/ingest/ tests/store/ tests/ingest/
git commit -m "feat(store): keep outcomes per case, aggregate failure rate per file"
```

---

### Task 4: Exclude permanently-failing cases, with a minimum-observation guard

Three mobx cases fail in every collected commit — they need a production build `--selectProjects mobx` does not run. Their variance is zero and they are worthless as labels. Left in, they pin three whole test files at `failure_rate` 1.0 under Task 3's definition, and the heuristic scorer selects those files on every diff forever.

The minimum-observation guard is not defensive padding. At 3 collected commits *every* case looks constant, so an unguarded rule would delete the entire dataset. This is the same shape as the Phase 2 circuit breaker: a rate over a minimum sample, never "N consecutive".

**Files:**
- Modify: `winnow/store/repository.py`
- Test: `tests/store/test_repository.py`

**Interfaces:**
- Consumes: `TestOutcomeRepository.add_outcomes` (Task 3)
- Produces:
  - module constant `PERMANENT_FAILURE_MIN_OBSERVATIONS: int = 5`
  - `TestOutcomeRepository.failure_rate(test_file: str, min_observations: int = PERMANENT_FAILURE_MIN_OBSERVATIONS) -> float`

- [ ] **Step 1: Write the failing tests**

```python
# tests/store/test_repository.py
from winnow.store.repository import PERMANENT_FAILURE_MIN_OBSERVATIONS


def _record(repo, sha: str, test_file: str, cases: dict[str, bool]) -> None:
    repo.add_outcomes(
        sha,
        test_file,
        [TestOutcome(c, passed=p, duration_seconds=0.1) for c, p in cases.items()],
    )


def test_a_permanently_failing_case_is_excluded_from_the_file_failure_rate(tmp_path: Path):
    """mobx has three cases that fail in every commit because they need a
    production build. Counted, they pin their whole file at 1.0 forever."""
    repo = TestOutcomeRepository(_conn(tmp_path))

    for i in range(PERMANENT_FAILURE_MIN_OBSERVATIONS):
        _record(
            repo,
            f"sha{i}",
            "test/a.test.js",
            {"a.always_broken": False, "a.healthy": True},
        )

    # every commit "failed", but only because of the constant case
    assert repo.failure_rate("test/a.test.js") == 0.0


def test_a_real_failure_still_counts_when_a_constant_case_is_excluded(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    for i in range(PERMANENT_FAILURE_MIN_OBSERVATIONS):
        healthy_passed = i != 0  # genuinely broke at sha0 only
        _record(
            repo,
            f"sha{i}",
            "test/a.test.js",
            {"a.always_broken": False, "a.healthy": healthy_passed},
        )

    assert repo.failure_rate("test/a.test.js") == 1 / PERMANENT_FAILURE_MIN_OBSERVATIONS


def test_below_the_observation_floor_nothing_is_excluded(tmp_path: Path):
    """With 3 commits collected every case looks constant. An unguarded rule
    would throw away the whole dataset."""
    repo = TestOutcomeRepository(_conn(tmp_path))

    for i in range(3):
        _record(repo, f"sha{i}", "test/a.test.js", {"a.looks_constant": False})

    assert repo.failure_rate("test/a.test.js", min_observations=5) == 1.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/store/test_repository.py -k permanent or floor -v`
Expected: FAIL — `ImportError: cannot import name 'PERMANENT_FAILURE_MIN_OBSERVATIONS'`

- [ ] **Step 3: Implement the exclusion**

```python
# winnow/store/repository.py  (module level)
# A case is only judged "permanently failing" once there is enough history to
# tell constancy from coincidence. At 3 collected commits every case looks
# constant, so an unguarded rule deletes the dataset. Same shape as the Phase 2
# circuit breaker: a rate over a minimum sample, never N-in-a-row.
PERMANENT_FAILURE_MIN_OBSERVATIONS = 5
```

```python
# winnow/store/repository.py  (TestOutcomeRepository)
    def failure_rate(
        self,
        test_file: str,
        min_observations: int = PERMANENT_FAILURE_MIN_OBSERVATIONS,
    ) -> float:
        excluded = self._permanently_failing_cases(test_file, min_observations)

        rows = self._conn.execute(
            "SELECT commit_sha, case_id, passed FROM test_outcomes WHERE test_file = ?",
            (test_file,),
        ).fetchall()
        if not rows:
            return 0.0

        commits: dict[str, bool] = {}
        for commit_sha, case_id, passed in rows:
            if case_id in excluded:
                continue
            commits[commit_sha] = commits.get(commit_sha, False) or passed == 0

        if not commits:
            return 0.0
        return sum(1 for failed in commits.values() if failed) / len(commits)

    def _permanently_failing_cases(self, test_file: str, min_observations: int) -> set[str]:
        rows = self._conn.execute(
            """SELECT case_id
               FROM test_outcomes
               WHERE test_file = ?
               GROUP BY case_id
               HAVING COUNT(*) >= ? AND MAX(passed) = 0""",
            (test_file, min_observations),
        ).fetchall()
        return {row[0] for row in rows}
```

- [ ] **Step 4: Run the full store suite**

Run: `pytest tests/store/ -v`
Expected: PASS, including Task 3's `test_failure_rate_counts_commits_where_the_file_had_any_failing_case` — it has only 2 commits, below the floor, so nothing is excluded and it still returns 0.5.

- [ ] **Step 5: Commit**

```bash
git add winnow/store/repository.py tests/store/test_repository.py
git commit -m "feat(store): exclude constant-failure cases above an observation floor"
```

---

### Task 5: Rename the identity through the selection chain

Mechanical, but it is the point of the change: after this task the selector, the pipeline and the scorer all speak test files.

**Files:**
- Modify: `winnow/selection/deterministic.py`
- Modify: `winnow/selection/pipeline.py`
- Modify: `winnow/selection/risk_scorer.py`
- Test: `tests/selection/test_deterministic.py`, `tests/selection/test_pipeline.py`, `tests/selection/test_risk_scorer.py`

**Interfaces:**
- Consumes: `CoverageRepository.test_files_covering` (Task 2), `TestOutcomeRepository.failure_rate` / `all_test_files` (Tasks 3–4)
- Produces:
  - `SelectionResult(must_run: frozenset[str], full_suite_required: bool, unknown_files: frozenset[str])` — `must_run` now holds test file paths
  - `RankedTest(test_file: str, risk_score: float, reason: str)`
  - `RiskScorer.score(test_file: str, changed_files: frozenset[str]) -> float`

- [ ] **Step 1: Update the selection tests to the new identity**

In all three test files under `tests/selection/`, rename the stub scorer parameter and every fixture identity so that what is stored and asserted is a test file path. For example, in `tests/selection/test_pipeline.py`:

```python
class StubRiskScorer(RiskScorer):
    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def score(self, test_file: str, changed_files: frozenset[str]) -> float:
        return self._scores.get(test_file, 0.0)


def test_pipeline_includes_direct_coverage_and_high_risk_test_files(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)

    coverage_repo.add_coverage(
        "sha1", "test/direct.test.js", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    outcome_repo.add_outcomes(
        "sha1", "test/direct.test.js", [TestOutcome("direct.works", passed=True, duration_seconds=0.1)]
    )
    outcome_repo.add_outcomes(
        "sha1", "test/risky.test.js", [TestOutcome("risky.works", passed=True, duration_seconds=0.1)]
    )
    outcome_repo.add_outcomes(
        "sha1", "test/irrelevant.test.js", [TestOutcome("irr.works", passed=True, duration_seconds=0.1)]
    )

    scorer = StubRiskScorer(
        {"test/direct.test.js": 0.2, "test/risky.test.js": 0.9, "test/irrelevant.test.js": 0.1}
    )
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer, risk_threshold=0.5)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="a.py"),)))

    selected = {r.test_file for r in result.selected_tests}
    assert selected == {"test/direct.test.js", "test/risky.test.js"}
```

Apply the same substitution to the remaining assertions in that file and to `test_deterministic.py` / `test_risk_scorer.py`, keeping each test's original intent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/selection/ -v`
Expected: FAIL — `AttributeError: 'CoverageRepository' object has no attribute 'tests_covering_file'` (the pipeline still calls the old name) and `RankedTest` has no `test_file`.

- [ ] **Step 3: Update `deterministic.py`**

```python
def must_run_tests(diff: Diff, coverage_repo: CoverageRepository) -> SelectionResult:
    if not diff.changed_files:
        return SelectionResult(
            must_run=frozenset(), full_suite_required=True, unknown_files=frozenset()
        )

    selected: set[str] = set()
    unknown: set[str] = set()

    for changed_file in diff.changed_files:
        if not coverage_repo.is_known_file(changed_file.path):
            unknown.add(changed_file.path)
            continue
        selected |= coverage_repo.test_files_covering(
            changed_file.path, changed_file.changed_lines
        )

    return SelectionResult(
        must_run=frozenset(selected),
        full_suite_required=bool(unknown),
        unknown_files=frozenset(unknown),
    )
```

- [ ] **Step 4: Update `pipeline.py`**

```python
@dataclass(frozen=True)
class RankedTest:
    test_file: str
    risk_score: float
    reason: str


...

    def run(self, diff: Diff) -> PipelineResult:
        det = must_run_tests(diff, self._coverage_repo)
        changed_paths = frozenset(cf.path for cf in diff.changed_files)

        ranked: list[RankedTest] = []
        for test_file in det.must_run:
            score = self._risk_scorer.score(test_file, changed_paths)
            ranked.append(RankedTest(test_file, score, "direct coverage overlap"))

        remaining = self._outcome_repo.all_test_files() - det.must_run
        for test_file in remaining:
            score = self._risk_scorer.score(test_file, changed_paths)
            if score >= self._risk_threshold:
                ranked.append(RankedTest(test_file, score, "risk score above threshold"))

        ranked.sort(key=lambda r: r.risk_score, reverse=True)

        return PipelineResult(
            selected_tests=tuple(ranked),
            full_suite_required=det.full_suite_required,
            unknown_files=det.unknown_files,
        )
```

- [ ] **Step 5: Update `risk_scorer.py`**

```python
class RiskScorer(ABC):
    @abstractmethod
    def score(self, test_file: str, changed_files: frozenset[str]) -> float:
        """Return a risk score in [0, 1] for this test file given the changed files."""


class HeuristicRiskScorer(RiskScorer):
    """Baseline strategy: risk = historical failure rate of the test file. A
    follow-up plan adds a co-change-aware ML strategy behind the same
    RiskScorer interface."""

    def __init__(self, outcome_repo: TestOutcomeRepository):
        self._outcome_repo = outcome_repo

    def score(self, test_file: str, changed_files: frozenset[str]) -> float:
        return self._outcome_repo.failure_rate(test_file)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/selection/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add winnow/selection/ tests/selection/
git commit -m "refactor(selection): key the selection chain on the test file"
```

---

### Task 6: Wire the collector to the new identity

This is where the 26× is actually deleted: the `for outcome in outcomes:` wrapper around `add_coverage` disappears. A correctness fix comes with it — today a test file whose cases are all skipped produces an empty `outcomes` list, so the loop never runs and its coverage is silently dropped.

**Files:**
- Modify: `winnow/collect/history.py`
- Test: `tests/collect/test_history.py`

**Interfaces:**
- Consumes: `relative_posix` (Task 1), `add_coverage` (Task 2), `add_outcomes` (Task 3)
- Produces: no signature change to `collect_history`

- [ ] **Step 1: Write the failing tests**

Add to `tests/collect/test_history.py` (reuse the existing `_repos` and `_write_fixture_reports` helpers):

```python
def _fixture_reports_with_many_cases(output_dir: Path, num_cases: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cobertura-coverage.xml").write_text(
        """<?xml version="1.0"?>
<coverage><packages><package name="app"><classes>
  <class name="a" filename="src/a.ts"><lines><line number="1" hits="1"/></lines></class>
  <class name="b" filename="src/b.ts"><lines><line number="1" hits="1"/></lines></class>
</classes></package></packages></coverage>
"""
    )
    cases = "\n".join(
        f'<testcase classname="a.test" name="case{i}" time="0.01"/>' for i in range(num_cases)
    )
    (output_dir / "junit.xml").write_text(
        f'<?xml version="1.0"?>\n<testsuites><testsuite name="jest">\n{cases}\n'
        "</testsuite></testsuites>\n"
    )


def test_coverage_is_written_once_per_test_file_not_once_per_case(tmp_path: Path):
    """The whole point of the change: 40 cases in one file used to write 40
    identical copies of the same coverage report."""
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone = tmp_path / "clone"
    clone.mkdir()

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter):
        _fixture_reports_with_many_cases(output_dir, num_cases=40)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    collect_history(
        repo_url="url",
        clone_dest=clone,
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=tmp_path / "reporter.js",
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda url, dest: None,
        list_last_n_commits=lambda dest, n: ["sha1"],
        checkout=lambda dest, sha: None,
        commit_date=lambda dest, sha: "2026-09-10T00:00:00",
        install=lambda dest: InstallResult(succeeded=True),
        list_test_files=lambda dest: [str(clone / "test" / "a.test.js")],
        run_tests_for_file=fake_run_tests_for_file,
    )

    conn = coverage_repo._conn
    rows = conn.execute("SELECT COUNT(*) FROM test_coverage").fetchone()[0]
    # two source files, one test file, one commit -- not 2 * 40
    assert rows == 2
    assert coverage_repo.test_files_covering("src/a.ts") == {"test/a.test.js"}


def test_a_test_file_with_no_cases_still_records_its_coverage(tmp_path: Path):
    """Previously the per-case loop meant an all-skipped file stored nothing."""
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone = tmp_path / "clone"
    clone.mkdir()

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter):
        _fixture_reports_with_many_cases(output_dir, num_cases=0)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    collect_history(
        repo_url="url",
        clone_dest=clone,
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=tmp_path / "reporter.js",
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda url, dest: None,
        list_last_n_commits=lambda dest, n: ["sha1"],
        checkout=lambda dest, sha: None,
        commit_date=lambda dest, sha: "2026-09-10T00:00:00",
        install=lambda dest: InstallResult(succeeded=True),
        list_test_files=lambda dest: [str(clone / "test" / "a.test.js")],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert coverage_repo.is_known_file("src/a.ts") is True
```

Existing tests in this file that assert on stored outcomes need their expectations updated to the new `add_outcomes` signature; keep their intent unchanged.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/collect/test_history.py -v`
Expected: FAIL — the first new test reports 80 rows instead of 2; the second reports `is_known_file` is False.

- [ ] **Step 3: Update the collector**

```python
# winnow/collect/history.py  (imports)
from winnow.collect.paths import relative_posix
```

```python
# winnow/collect/history.py  (inside the per-file loop, replacing the
# coverage/outcome block)
            coverage_report = cobertura_parser.parse(run_result.coverage_path)
            outcomes = junit_parser.parse(run_result.junit_path)

            # Once per test file, never once per case: jest produces coverage
            # per file, so a row per case claimed an attribution that was
            # never collected -- and cost 26x the space saying it. Written
            # before the outcome check so an all-skipped file still records
            # what it covered.
            test_file_id = relative_posix(clone_dest, test_file)
            coverage_repo.add_coverage(sha, test_file_id, coverage_report)
            outcome_repo.add_outcomes(sha, test_file_id, outcomes)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/collect/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add winnow/collect/history.py tests/collect/test_history.py
git commit -m "fix(collect): store coverage once per test file, not once per case"
```

---

### Task 7: Re-express the synthetic world

`simulate/generator.py` and `test_bootstrap_validation.py` **define** the world the engine was validated against. Renamed mechanically, they would keep passing while validating a world that no longer exists — so the generator must now produce several cases per test file, which is the structure the real data has.

**Files:**
- Modify: `winnow/simulate/generator.py`
- Modify: `tests/simulate/test_generator.py`
- Modify: `tests/test_bootstrap_validation.py`

**Interfaces:**
- Consumes: `CoverageRepository.add_coverage` (Task 2), `TestOutcomeRepository.add_outcomes` (Task 3)
- Produces:
  - `SyntheticFixture(test_file_to_files: dict[str, frozenset[str]], file_names: tuple[str, ...], test_files: tuple[str, ...], cases_per_file: int)`
  - `generate_coverage_matrix(num_test_files: int, num_files: int, seed: int = 42, cases_per_file: int = 3) -> SyntheticFixture`
  - `populate_store(fixture, coverage_repo, commit_sha) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/simulate/test_generator.py
from pathlib import Path

from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_generated_fixture_maps_test_files_to_source_files():
    fixture = generate_coverage_matrix(num_test_files=10, num_files=5, seed=7)

    assert len(fixture.test_files) == 10
    assert all(f.endswith(".test.js") for f in fixture.test_files)
    assert set(fixture.test_file_to_files) == set(fixture.test_files)


def test_populate_store_writes_one_coverage_row_per_test_file_and_source_file(
    tmp_path: Path,
):
    """Several cases live in one test file in the real data; coverage is still
    one row per (test file, source file). If this ever writes cases_per_file
    times as many rows, the unique constraint fires."""
    conn = init_db(tmp_path / "winnow.db")
    repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(
        num_test_files=6, num_files=4, seed=7, cases_per_file=5
    )
    populate_store(fixture, repo, commit_sha="sha1")

    expected_rows = sum(len(files) for files in fixture.test_file_to_files.values())
    assert conn.execute("SELECT COUNT(*) FROM test_coverage").fetchone()[0] == expected_rows

    for test_file, files in fixture.test_file_to_files.items():
        for file_path in files:
            assert test_file in repo.test_files_covering(file_path)
```

And in `tests/test_bootstrap_validation.py`:

```python
def test_deterministic_selection_achieves_full_recall_on_synthetic_ground_truth(
    tmp_path: Path,
):
    """The deterministic selector must recover exactly the test files known (by
    construction) to cover each changed file -- the safety-net guarantee the
    whole design depends on."""
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_test_files=30, num_files=12, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    for file_path in fixture.file_names:
        expected = {
            test_file
            for test_file, files in fixture.test_file_to_files.items()
            if file_path in files
        }

        diff = Diff(changed_files=(ChangedFile(path=file_path),))
        result = must_run_tests(diff, coverage_repo)

        assert result.must_run == expected, f"recall failure for {file_path}"
        assert result.full_suite_required is False


def test_deterministic_selection_falls_back_safely_for_unknown_file(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_test_files=10, num_files=5, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    diff = Diff(changed_files=(ChangedFile(path="totally_unrelated_file.py"),))
    result = must_run_tests(diff, coverage_repo)

    assert result.full_suite_required is True
    assert result.must_run == frozenset()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/simulate/ tests/test_bootstrap_validation.py -v`
Expected: FAIL — `TypeError: generate_coverage_matrix() got an unexpected keyword argument 'num_test_files'`

- [ ] **Step 3: Rewrite the generator**

```python
# winnow/simulate/generator.py
import random
from dataclasses import dataclass

from winnow.ingest.models import CoverageReport, FileCoverage
from winnow.store.repository import CoverageRepository


@dataclass(frozen=True)
class SyntheticFixture:
    """The synthetic world the deterministic selector is validated against.

    It mirrors the real data's shape deliberately: coverage is attributed to a
    test FILE, and several cases share that file. A fixture with one case per
    file would validate a world Winnow no longer lives in.
    """

    test_file_to_files: dict[str, frozenset[str]]
    file_names: tuple[str, ...]
    test_files: tuple[str, ...]
    cases_per_file: int


def generate_coverage_matrix(
    num_test_files: int, num_files: int, seed: int = 42, cases_per_file: int = 3
) -> SyntheticFixture:
    rng = random.Random(seed)
    file_names = tuple(f"module_{i}.py" for i in range(num_files))
    test_files = tuple(f"test/t_{i}.test.js" for i in range(num_test_files))

    test_file_to_files: dict[str, frozenset[str]] = {}
    for test_file in test_files:
        k = rng.randint(1, min(3, num_files))
        test_file_to_files[test_file] = frozenset(rng.sample(file_names, k))

    return SyntheticFixture(
        test_file_to_files=test_file_to_files,
        file_names=file_names,
        test_files=test_files,
        cases_per_file=cases_per_file,
    )


def case_ids(fixture: SyntheticFixture, test_file: str) -> tuple[str, ...]:
    stem = test_file.removeprefix("test/").removesuffix(".test.js")
    return tuple(f"{stem}.case_{i}" for i in range(fixture.cases_per_file))


def populate_store(
    fixture: SyntheticFixture, coverage_repo: CoverageRepository, commit_sha: str
) -> None:
    for test_file, files in fixture.test_file_to_files.items():
        report = CoverageReport(
            files=tuple(
                FileCoverage(file_path=f, covered_lines=frozenset({1})) for f in files
            )
        )
        coverage_repo.add_coverage(commit_sha, test_file, report)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/simulate/ tests/test_bootstrap_validation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add winnow/simulate/generator.py tests/simulate/ tests/test_bootstrap_validation.py
git commit -m "refactor(simulate): give the synthetic world several cases per test file"
```

---

### Task 8: Bring the tools and the slow integration test along

`tools/analyze_history.py` queries the store directly, so it breaks on the renamed columns — loudly, but only when run. The slow ts-pattern integration test calls `all_test_ids()`.

**Files:**
- Modify: `tools/analyze_history.py`
- Modify: `tests/collect/test_integration_ts_pattern.py`

**Interfaces:**
- Consumes: everything from Tasks 2–4
- Produces: nothing new

- [ ] **Step 1: Update the SQL in `tools/analyze_history.py`**

Replace `test_id` with `case_id` in the five queries, and add the two lines the new schema makes answerable:

```python
    tests = q1(conn, "SELECT COUNT(DISTINCT case_id) FROM test_outcomes")
    test_files = q1(conn, "SELECT COUNT(DISTINCT test_file) FROM test_outcomes")
    failures = q1(conn, "SELECT COUNT(*) FROM test_outcomes WHERE passed = 0")
    failing_commits = q1(
        conn, "SELECT COUNT(DISTINCT commit_sha) FROM test_outcomes WHERE passed = 0"
    )
    failing_tests = q1(
        conn, "SELECT COUNT(DISTINCT case_id) FROM test_outcomes WHERE passed = 0"
    )
```

Add to the "collection sanity" block:

```python
    print(f"distinct_test_files    {test_files}")
```

And in the failures listing:

```python
        for sha, test_file, case_id in conn.execute(
            "SELECT commit_sha, test_file, case_id FROM test_outcomes "
            "WHERE passed = 0 LIMIT 20"
        ):
            print(f"  {sha[:8]}  {test_file}  {case_id}")
```

Add a constant-failure report, since the exclusion rule now depends on it:

```python
    print()
    print("=== cases that never pass (excluded from ground truth) ===")
    for test_file, case_id, n in conn.execute(
        "SELECT test_file, case_id, COUNT(*) FROM test_outcomes "
        "GROUP BY test_file, case_id HAVING MAX(passed) = 0 ORDER BY COUNT(*) DESC LIMIT 20"
    ):
        print(f"  {test_file}  {case_id}  observations={n}")
```

- [ ] **Step 2: Update the slow integration test**

In `tests/collect/test_integration_ts_pattern.py`, change `assert outcome_repo.all_test_ids()` to `assert outcome_repo.all_test_files()`.

- [ ] **Step 3: Verify nothing still speaks the old identity**

Run: `grep -rn "test_id\|all_test_ids\|tests_covering_file" winnow/ tools/ tests/`
Expected: no matches. If any remain, fix them before committing.

- [ ] **Step 4: Run the whole suite**

Run: `pytest -v`
Expected: all pass, 0 failures. Record the test count — it should be higher than 69 (the pre-change total).

- [ ] **Step 5: Commit**

```bash
git add tools/analyze_history.py tests/collect/test_integration_ts_pattern.py
git commit -m "chore(tools): follow the selection-unit rename through the analysis tool"
```

---

### Task 9: Verify against real data, not just pytest

Green tests prove the code does what the tests say. They do not prove the collector still collects, that the ~0.9 MB/commit estimate was right, or that selection did not quietly lose information. This task is measurement; there is no TDD cycle.

The DB size figure being checked here is *derived* from the 26× ratio, not yet observed. If it comes out materially different, that is a finding to write down, not a number to round toward the prediction.

**Files:**
- Modify: `HANDOFF.md` (record the measured result)

- [ ] **Step 1: Capture the old selection output before deleting the old data**

If `data/mobx/winnow.db` from the 2026-09-08 run still exists, snapshot what the current selector returns for a fixed diff, so the comparison in Step 4 has a reference:

```bash
cd C:/dev/winnow
git stash            # back to the pre-change code
python -c "
import sqlite3, json, pathlib
conn = sqlite3.connect('data/mobx/winnow.db')
rows = conn.execute('SELECT DISTINCT test_id FROM test_coverage WHERE file_path LIKE \"%observable.ts\"').fetchall()
pathlib.Path('/tmp/before-selection.json').write_text(json.dumps(sorted(r[0] for r in rows)))
print(len(rows), 'test ids')
"
git stash pop
```

If that database no longer exists, skip this step and note in Step 5 that the before/after selection comparison could not be run.

- [ ] **Step 2: Re-collect the same three commits**

```bash
cd C:/dev/winnow
rm -rf data/mobx/winnow.db data/mobx/reports
python tools/collect_history.py 3 \
  --repo https://github.com/mobxjs/mobx.git \
  --project mobx
```

Expected: ~34 minutes total (measured 11.2 min/commit), `collected_commits 3`, `skipped_commits 0`, `skipped_files 0`.

- [ ] **Step 3: Measure the database**

```bash
python -c "
import pathlib
b = pathlib.Path('data/mobx/winnow.db').stat().st_size
print(f'{b/1e6:.2f} MB total, {b/3e6:.2f} MB per commit')
"
python tools/analyze_history.py data/mobx/winnow.db
```

Expected: roughly 0.9 MB per commit against the previous 22.8 MB. `distinct_test_files` should be 32. The "cases that never pass" section should list the three production-build cases.

- [ ] **Step 4: Compare selection output**

```bash
python -c "
import sqlite3, json, pathlib
conn = sqlite3.connect('data/mobx/winnow.db')
rows = conn.execute('SELECT DISTINCT test_file FROM test_coverage WHERE file_path LIKE \"%observable.ts\"').fetchall()
after = sorted(r[0] for r in rows)
before_path = pathlib.Path('/tmp/before-selection.json')
print('after :', len(after), 'test files')
if before_path.exists():
    before = json.loads(before_path.read_text())
    print('before:', len(before), 'test ids (cases, so a larger number is expected)')
"
```

The two counts are in different units — cases before, files after — so what is being checked is that the *set of files* implied by the old case ids matches the new file set. If a test file present before is missing now, the refactor lost information: stop and investigate rather than proceeding.

- [ ] **Step 5: Record the measurement in `HANDOFF.md`**

Under "Seçim birimi kararı", add a short "Ölçülen sonuç" block with the actual numbers: MB/commit before and after, distinct test files, the constant-failure cases the analysis tool listed, and whether the selection comparison in Step 4 was possible. Write what was measured, including any figure that missed the prediction.

- [ ] **Step 6: Commit**

```bash
git add HANDOFF.md
git commit -m "docs(handoff): record the measured result of the selection-unit change"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Identity and path coordinates | 1 |
| Schema — `test_coverage`, UNIQUE, index | 2 |
| Schema — `test_outcomes`, `case_id` | 3 |
| No migration | 9 (Step 2 deletes and re-collects) |
| Collector | 6 |
| Selection and scoring | 5 |
| `failure_rate` definition (a) | 3 |
| Data hygiene + minimum observations | 4 |
| Testing items 1–7 | 6, 2, 1, 6, 3, 4, 5 respectively |
| Verification on real data | 9 |
| Risk: synthetic world | 7 |

No spec requirement is unassigned.

**Type consistency:** `test_file: str` everywhere; `case_id: str` only inside `TestOutcome` and the `test_outcomes` table. `test_files_covering` (Task 2) is the name called in Task 5 and grepped for in Task 8. `all_test_files` (Task 3) is the name called in Task 5's pipeline and Task 8's integration test. `SyntheticFixture.test_file_to_files` (Task 7) is the name used in both Task 7 test blocks.

**Known deviation to watch:** Task 2 makes duplicate coverage inserts raise, so re-running collection into an existing database now fails instead of silently duplicating. Task 9 Step 2 deletes the database first. If a future run wants resumability, that is a separate change with its own decision.
