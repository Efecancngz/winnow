# Winnow Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate the core predictive-test-selection engine — coverage/result ingestion, a SQLite history store, deterministic coverage-based selection, a pluggable risk scorer (heuristic baseline), and a synthetic-data bootstrap that proves the selector achieves full recall on known ground truth.

**Architecture:** Monolith-first, layered Python package (`ingest → store → selection → simulate`), outer layers depending on inner ones only. Adapter pattern for report parsers, Repository pattern for SQLite access, Strategy pattern for the risk scorer.

**Tech Stack:** Python 3.12, `junitparser`, stdlib `sqlite3` and `xml.etree.ElementTree`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-21-winnow-design.md` (see also `docs/architecture.md`, `docs/analiz.md`, `docs/api-spec.md`).

## Global Constraints

- Language: Python 3.12+.
- Data store: SQLite only — no external DB server.
- No paid or closed-source dependencies.
- Safety invariant: the deterministic "must-run" test set is never narrowed
  by risk scoring — risk scoring only adds/reorders. Missing or unknown
  coverage data always falls back to the full suite, visibly (never a
  silent skip). Any change to `winnow/selection/` must preserve this.
- Every backend change ships with a test.
- Commit messages: Conventional Commits, English, imperative mood
  ("Add", "Fix", not "Added"/"Fixed"). Never add an AI co-author trailer.
- Dependency direction: `action → selection → store → ingest`. Inner
  layers must never import from outer layers.

## Scope note

This plan covers the core engine only, validated entirely with synthetic
data. A follow-up plan will add the ML-based risk scorer, the backtesting
harness against a real open-source repository, and the GitHub Action —
deferred because the target repo for backtesting is still an open question
(see `HANDOFF.md`), and it's a genuinely separate milestone: "does the
algorithm work" vs. "does it work on real data in real CI."

---

### Task 1: Project tooling and package scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `winnow/__init__.py`
- Test: `tests/test_sanity.py`

**Interfaces:**
- Produces: an installable `winnow` package and a working `pytest` setup
  that every later task builds on.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "winnow"
version = "0.1.0"
description = "Predictive test selection: coverage-based safety net + ML risk scoring"
requires-python = ">=3.12"
dependencies = [
    "junitparser>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["winnow*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the empty package marker**

`winnow/__init__.py`:
```python
```
(empty file)

- [ ] **Step 3: Write a canary test**

`tests/test_sanity.py`:
```python
def test_sanity():
    assert True
```

- [ ] **Step 4: Install the package in editable/dev mode**

Run: `pip install -e ".[dev]"`
Expected: install succeeds with no errors.

- [ ] **Step 5: Run pytest to verify the setup works**

Run: `pytest -v`
Expected: PASS — `tests/test_sanity.py::test_sanity PASSED`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml winnow/__init__.py tests/test_sanity.py
git commit -m "chore: set up Python package scaffold and test tooling"
```

---

### Task 2: Normalized coverage and test outcome models

**Files:**
- Create: `winnow/ingest/__init__.py`
- Create: `winnow/ingest/models.py`
- Test: `tests/ingest/test_models.py`

**Interfaces:**
- Produces: `FileCoverage(file_path: str, covered_lines: frozenset[int])`,
  `CoverageReport(files: tuple[FileCoverage, ...])`,
  `TestOutcome(test_id: str, passed: bool, duration_seconds: float)` —
  used by every later task as the shared normalized data model.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_models.py`:
```python
from winnow.ingest.models import FileCoverage, CoverageReport, TestOutcome


def test_file_coverage_is_frozen_and_hashable():
    fc = FileCoverage(file_path="module_a.py", covered_lines=frozenset({1, 2, 3}))
    assert fc.file_path == "module_a.py"
    assert fc.covered_lines == frozenset({1, 2, 3})
    hash(fc)  # must not raise


def test_coverage_report_holds_multiple_files():
    report = CoverageReport(files=(
        FileCoverage("a.py", frozenset({1})),
        FileCoverage("b.py", frozenset({2, 3})),
    ))
    assert len(report.files) == 2
    assert report.files[0].file_path == "a.py"


def test_test_outcome_records_pass_and_duration():
    outcome = TestOutcome(test_id="test_foo", passed=False, duration_seconds=0.42)
    assert outcome.test_id == "test_foo"
    assert outcome.passed is False
    assert outcome.duration_seconds == 0.42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ingest/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.ingest'`

- [ ] **Step 3: Write minimal implementation**

`winnow/ingest/__init__.py`:
```python
```
(empty file)

`winnow/ingest/models.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class FileCoverage:
    file_path: str
    covered_lines: frozenset[int]


@dataclass(frozen=True)
class CoverageReport:
    files: tuple[FileCoverage, ...]


@dataclass(frozen=True)
class TestOutcome:
    test_id: str
    passed: bool
    duration_seconds: float
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ingest/test_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/ingest/__init__.py winnow/ingest/models.py tests/ingest/test_models.py
git commit -m "feat: add normalized coverage and test outcome models"
```

---

### Task 3: Parser interfaces (Adapter contract)

**Files:**
- Create: `winnow/ingest/base.py`
- Test: `tests/ingest/test_base.py`

**Interfaces:**
- Consumes: `CoverageReport`, `TestOutcome` from `winnow.ingest.models` (Task 2)
- Produces: `CoverageParser` (abstract method `parse(report_path: Path) -> CoverageReport`),
  `TestResultParser` (abstract method `parse(report_path: Path) -> list[TestOutcome]`) —
  every concrete parser (Tasks 4, 5) implements one of these.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_base.py`:
```python
from pathlib import Path

import pytest

from winnow.ingest.base import CoverageParser, TestResultParser
from winnow.ingest.models import CoverageReport


def test_coverage_parser_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        CoverageParser()


def test_test_result_parser_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        TestResultParser()


def test_incomplete_coverage_parser_cannot_be_instantiated():
    class Incomplete(CoverageParser):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_concrete_coverage_parser_implementing_parse_works():
    class Fake(CoverageParser):
        def parse(self, report_path: Path) -> CoverageReport:
            return CoverageReport(files=())

    parser = Fake()
    assert parser.parse(Path("unused.xml")) == CoverageReport(files=())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ingest/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.ingest.base'`

- [ ] **Step 3: Write minimal implementation**

`winnow/ingest/base.py`:
```python
from abc import ABC, abstractmethod
from pathlib import Path

from winnow.ingest.models import CoverageReport, TestOutcome


class CoverageParser(ABC):
    @abstractmethod
    def parse(self, report_path: Path) -> CoverageReport:
        """Parse a coverage report file into a normalized CoverageReport."""


class TestResultParser(ABC):
    @abstractmethod
    def parse(self, report_path: Path) -> list[TestOutcome]:
        """Parse a test result report file into normalized TestOutcomes."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ingest/test_base.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/ingest/base.py tests/ingest/test_base.py
git commit -m "feat: add coverage and test result parser interfaces"
```

---

### Task 4: Cobertura XML coverage parser

**Files:**
- Create: `winnow/ingest/cobertura.py`
- Create: `tests/fixtures/cobertura_sample.xml`
- Test: `tests/ingest/test_cobertura.py`

**Interfaces:**
- Consumes: `CoverageParser` (Task 3), `CoverageReport`/`FileCoverage` (Task 2)
- Produces: `CoberturaParser` — a concrete `CoverageParser` used later by the
  bootstrap/backtest ingestion flow.

- [ ] **Step 1: Create the fixture report**

`tests/fixtures/cobertura_sample.xml`:
```xml
<?xml version="1.0"?>
<coverage line-rate="0.6" branch-rate="0" version="1.9" timestamp="1700000000">
  <packages>
    <package name="app" line-rate="0.6" branch-rate="0">
      <classes>
        <class name="module_a" filename="module_a.py" line-rate="0.6" branch-rate="0">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
            <line number="3" hits="2"/>
          </lines>
        </class>
        <class name="module_b" filename="module_b.py" line-rate="1.0" branch-rate="0">
          <lines>
            <line number="10" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
```

- [ ] **Step 2: Write the failing test**

`tests/ingest/test_cobertura.py`:
```python
from pathlib import Path

from winnow.ingest.cobertura import CoberturaParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cobertura_sample.xml"


def test_parses_covered_lines_per_file():
    parser = CoberturaParser()
    report = parser.parse(FIXTURE)

    files_by_path = {f.file_path: f for f in report.files}
    assert files_by_path["module_a.py"].covered_lines == frozenset({1, 3})
    assert files_by_path["module_b.py"].covered_lines == frozenset({10})


def test_uncovered_lines_are_excluded():
    parser = CoberturaParser()
    report = parser.parse(FIXTURE)

    files_by_path = {f.file_path: f for f in report.files}
    assert 2 not in files_by_path["module_a.py"].covered_lines
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/ingest/test_cobertura.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.ingest.cobertura'`

- [ ] **Step 4: Write minimal implementation**

`winnow/ingest/cobertura.py`:
```python
import xml.etree.ElementTree as ET
from pathlib import Path

from winnow.ingest.base import CoverageParser
from winnow.ingest.models import CoverageReport, FileCoverage


class CoberturaParser(CoverageParser):
    def parse(self, report_path: Path) -> CoverageReport:
        tree = ET.parse(report_path)
        root = tree.getroot()

        files: dict[str, set[int]] = {}
        for class_el in root.iter("class"):
            filename = class_el.get("filename")
            if filename is None:
                continue
            covered = files.setdefault(filename, set())
            lines_el = class_el.find("lines")
            if lines_el is None:
                continue
            for line_el in lines_el.findall("line"):
                hits = int(line_el.get("hits", "0"))
                if hits > 0:
                    covered.add(int(line_el.get("number")))

        return CoverageReport(
            files=tuple(
                FileCoverage(file_path=path, covered_lines=frozenset(lines))
                for path, lines in files.items()
            )
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/ingest/test_cobertura.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add winnow/ingest/cobertura.py tests/fixtures/cobertura_sample.xml tests/ingest/test_cobertura.py
git commit -m "feat: add Cobertura XML coverage parser"
```

---

### Task 5: JUnit XML test result parser

**Files:**
- Create: `winnow/ingest/junit.py`
- Create: `tests/fixtures/junit_sample.xml`
- Test: `tests/ingest/test_junit.py`

**Interfaces:**
- Consumes: `TestResultParser` (Task 3), `TestOutcome` (Task 2), `junitparser` (external dependency, already declared in Task 1's `pyproject.toml`)
- Produces: `JUnitParser` — a concrete `TestResultParser`.

- [ ] **Step 1: Create the fixture report**

`tests/fixtures/junit_sample.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1" errors="0" time="1.234">
    <testcase classname="tests.test_foo" name="test_passes" time="0.10"/>
    <testcase classname="tests.test_foo" name="test_fails" time="0.20">
      <failure message="AssertionError">Traceback...</failure>
    </testcase>
    <testcase classname="tests.test_bar" name="test_also_passes" time="0.05"/>
  </testsuite>
</testsuites>
```

- [ ] **Step 2: Write the failing test**

`tests/ingest/test_junit.py`:
```python
from pathlib import Path

from winnow.ingest.junit import JUnitParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "junit_sample.xml"


def test_parses_passed_and_failed_outcomes():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.test_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].passed is True
    assert by_id["tests.test_foo.test_fails"].passed is False
    assert by_id["tests.test_bar.test_also_passes"].passed is True


def test_captures_duration():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.test_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].duration_seconds == 0.10
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/ingest/test_junit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.ingest.junit'`

- [ ] **Step 4: Write minimal implementation**

`winnow/ingest/junit.py`:
```python
from pathlib import Path

from junitparser import JUnitXml

from winnow.ingest.base import TestResultParser
from winnow.ingest.models import TestOutcome


class JUnitParser(TestResultParser):
    def parse(self, report_path: Path) -> list[TestOutcome]:
        xml = JUnitXml.fromfile(str(report_path))

        outcomes: list[TestOutcome] = []
        for suite in xml:
            for case in suite:
                test_id = f"{case.classname}.{case.name}"
                passed = len(case.result) == 0
                outcomes.append(
                    TestOutcome(
                        test_id=test_id,
                        passed=passed,
                        duration_seconds=case.time or 0.0,
                    )
                )
        return outcomes
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/ingest/test_junit.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add winnow/ingest/junit.py tests/fixtures/junit_sample.xml tests/ingest/test_junit.py
git commit -m "feat: add JUnit XML test result parser"
```

---

### Task 6: SQLite schema and database initialization

**Files:**
- Create: `winnow/store/__init__.py`
- Create: `winnow/store/schema.py`
- Test: `tests/store/test_schema.py`

**Interfaces:**
- Produces: `init_db(db_path: Path) -> sqlite3.Connection` — creates the
  `commits`, `test_coverage`, `test_outcomes` tables if missing; used by
  every repository in Task 7.

- [ ] **Step 1: Write the failing test**

`tests/store/test_schema.py`:
```python
from pathlib import Path

from winnow.store.schema import init_db


def test_init_db_creates_expected_tables(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"commits", "test_coverage", "test_outcomes"} <= tables


def test_init_db_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    init_db(db_path)
    conn = init_db(db_path)  # must not raise on second call

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "commits" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.store'`

- [ ] **Step 3: Write minimal implementation**

`winnow/store/__init__.py`:
```python
```
(empty file)

`winnow/store/schema.py`:
```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_coverage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    covered_lines TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/store/__init__.py winnow/store/schema.py tests/store/test_schema.py
git commit -m "feat: add SQLite schema and database initialization"
```

---

### Task 7: Commit, coverage, and test outcome repositories

**Files:**
- Create: `winnow/store/repository.py`
- Test: `tests/store/test_repository.py`

**Interfaces:**
- Consumes: `init_db` (Task 6), `CoverageReport`/`FileCoverage`/`TestOutcome` (Task 2)
- Produces:
  - `CommitRepository.add(sha: str, recorded_at: str) -> None`,
    `CommitRepository.get_recent(limit: int) -> list[str]`
  - `CoverageRepository.add_coverage(commit_sha: str, test_id: str, report: CoverageReport) -> None`,
    `CoverageRepository.is_known_file(file_path: str) -> bool`,
    `CoverageRepository.tests_covering_file(file_path: str, changed_lines: frozenset[int] | None = None) -> set[str]`
  - `TestOutcomeRepository.add_outcomes(commit_sha: str, outcomes: list[TestOutcome]) -> None`,
    `TestOutcomeRepository.failure_rate(test_id: str) -> float`,
    `TestOutcomeRepository.all_test_ids() -> set[str]`
  - These are the exact names/signatures Tasks 8–12 depend on.

- [ ] **Step 1: Write the failing test**

`tests/store/test_repository.py`:
```python
from pathlib import Path

from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.store.repository import (
    CommitRepository,
    CoverageRepository,
    TestOutcomeRepository,
)
from winnow.store.schema import init_db


def _conn(tmp_path: Path):
    return init_db(tmp_path / "winnow.db")


def test_commit_repository_add_and_get_recent(tmp_path: Path):
    repo = CommitRepository(_conn(tmp_path))

    repo.add("sha1", "2026-08-01T00:00:00")
    repo.add("sha2", "2026-08-02T00:00:00")

    assert repo.get_recent(2) == ["sha2", "sha1"]


def test_coverage_repository_tests_covering_file(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1, 2, 3})),))
    repo.add_coverage("sha1", "test_a", report)

    assert repo.tests_covering_file("module_a.py") == {"test_a"}
    assert repo.tests_covering_file("module_a.py", changed_lines=frozenset({2})) == {"test_a"}
    assert repo.tests_covering_file("module_a.py", changed_lines=frozenset({99})) == set()


def test_coverage_repository_is_known_file(tmp_path: Path):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1})),))
    repo.add_coverage("sha1", "test_a", report)

    assert repo.is_known_file("module_a.py") is True
    assert repo.is_known_file("module_unknown.py") is False


def test_test_outcome_repository_failure_rate(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    repo.add_outcomes("sha1", [TestOutcome("test_a", passed=False, duration_seconds=0.1)])
    repo.add_outcomes("sha2", [TestOutcome("test_a", passed=True, duration_seconds=0.1)])

    assert repo.failure_rate("test_a") == 0.5
    assert repo.failure_rate("test_unknown") == 0.0


def test_test_outcome_repository_all_test_ids(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    repo.add_outcomes(
        "sha1",
        [
            TestOutcome("test_a", passed=True, duration_seconds=0.1),
            TestOutcome("test_b", passed=True, duration_seconds=0.1),
        ],
    )

    assert repo.all_test_ids() == {"test_a", "test_b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'CommitRepository'`

- [ ] **Step 3: Write minimal implementation**

`winnow/store/repository.py`:
```python
import sqlite3

from winnow.ingest.models import CoverageReport, TestOutcome


class CommitRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, sha: str, recorded_at: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO commits (sha, recorded_at) VALUES (?, ?)",
            (sha, recorded_at),
        )
        self._conn.commit()

    def get_recent(self, limit: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT sha FROM commits ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]


class CoverageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_coverage(self, commit_sha: str, test_id: str, report: CoverageReport) -> None:
        for file_cov in report.files:
            lines_csv = ",".join(str(n) for n in sorted(file_cov.covered_lines))
            self._conn.execute(
                """INSERT INTO test_coverage (commit_sha, test_id, file_path, covered_lines)
                   VALUES (?, ?, ?, ?)""",
                (commit_sha, test_id, file_cov.file_path, lines_csv),
            )
        self._conn.commit()

    def is_known_file(self, file_path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM test_coverage WHERE file_path = ? LIMIT 1",
            (file_path,),
        ).fetchone()
        return row is not None

    def tests_covering_file(
        self, file_path: str, changed_lines: frozenset[int] | None = None
    ) -> set[str]:
        rows = self._conn.execute(
            "SELECT test_id, covered_lines FROM test_coverage WHERE file_path = ?",
            (file_path,),
        ).fetchall()

        matched: set[str] = set()
        for test_id, lines_csv in rows:
            if changed_lines is None:
                matched.add(test_id)
                continue
            covered = {int(n) for n in lines_csv.split(",") if n}
            if covered & changed_lines:
                matched.add(test_id)
        return matched


class TestOutcomeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_outcomes(self, commit_sha: str, outcomes: list[TestOutcome]) -> None:
        self._conn.executemany(
            """INSERT INTO test_outcomes (commit_sha, test_id, passed, duration_seconds)
               VALUES (?, ?, ?, ?)""",
            [
                (commit_sha, o.test_id, int(o.passed), o.duration_seconds)
                for o in outcomes
            ],
        )
        self._conn.commit()

    def failure_rate(self, test_id: str) -> float:
        rows = self._conn.execute(
            "SELECT passed FROM test_outcomes WHERE test_id = ?",
            (test_id,),
        ).fetchall()
        if not rows:
            return 0.0
        failures = sum(1 for (passed,) in rows if passed == 0)
        return failures / len(rows)

    def all_test_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT test_id FROM test_outcomes").fetchall()
        return {row[0] for row in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/store/repository.py tests/store/test_repository.py
git commit -m "feat: add commit, coverage, and test outcome repositories"
```

---

### Task 8: Deterministic coverage-based selection (the safety net)

**Files:**
- Create: `winnow/selection/__init__.py`
- Create: `winnow/selection/deterministic.py`
- Test: `tests/selection/test_deterministic.py`

**Interfaces:**
- Consumes: `CoverageRepository` (Task 7)
- Produces: `ChangedFile(path: str, changed_lines: frozenset[int] | None = None)`,
  `Diff(changed_files: tuple[ChangedFile, ...])`,
  `SelectionResult(must_run: frozenset[str], full_suite_required: bool, unknown_files: frozenset[str])`,
  `must_run_tests(diff: Diff, coverage_repo: CoverageRepository) -> SelectionResult` —
  Task 10's pipeline consumes all of these exact names.

- [ ] **Step 1: Write the failing test**

`tests/selection/test_deterministic.py`:
```python
from pathlib import Path

from winnow.ingest.models import CoverageReport, FileCoverage
from winnow.selection.deterministic import ChangedFile, Diff, must_run_tests
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def _coverage_repo(tmp_path: Path) -> CoverageRepository:
    return CoverageRepository(init_db(tmp_path / "winnow.db"))


def test_selects_tests_covering_changed_file(tmp_path: Path):
    repo = _coverage_repo(tmp_path)
    repo.add_coverage(
        "sha1", "test_a", CoverageReport(files=(FileCoverage("a.py", frozenset({1, 2})),))
    )
    repo.add_coverage(
        "sha1", "test_b", CoverageReport(files=(FileCoverage("b.py", frozenset({1})),))
    )

    diff = Diff(changed_files=(ChangedFile(path="a.py"),))
    result = must_run_tests(diff, repo)

    assert result.must_run == {"test_a"}
    assert result.full_suite_required is False
    assert result.unknown_files == frozenset()


def test_narrows_by_changed_lines_when_given(tmp_path: Path):
    repo = _coverage_repo(tmp_path)
    repo.add_coverage(
        "sha1", "test_a", CoverageReport(files=(FileCoverage("a.py", frozenset({1, 2})),))
    )

    diff = Diff(changed_files=(ChangedFile(path="a.py", changed_lines=frozenset({99})),))
    result = must_run_tests(diff, repo)

    assert result.must_run == frozenset()


def test_unknown_file_triggers_full_suite_fallback(tmp_path: Path):
    repo = _coverage_repo(tmp_path)
    repo.add_coverage(
        "sha1", "test_a", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )

    diff = Diff(changed_files=(ChangedFile(path="never_seen.py"),))
    result = must_run_tests(diff, repo)

    assert result.full_suite_required is True
    assert result.unknown_files == frozenset({"never_seen.py"})
    assert result.must_run == frozenset()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/selection/test_deterministic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.selection'`

- [ ] **Step 3: Write minimal implementation**

`winnow/selection/__init__.py`:
```python
```
(empty file)

`winnow/selection/deterministic.py`:
```python
from dataclasses import dataclass

from winnow.store.repository import CoverageRepository


@dataclass(frozen=True)
class ChangedFile:
    path: str
    changed_lines: frozenset[int] | None = None


@dataclass(frozen=True)
class Diff:
    changed_files: tuple[ChangedFile, ...]


@dataclass(frozen=True)
class SelectionResult:
    must_run: frozenset[str]
    full_suite_required: bool
    unknown_files: frozenset[str]


def must_run_tests(diff: Diff, coverage_repo: CoverageRepository) -> SelectionResult:
    selected: set[str] = set()
    unknown: set[str] = set()

    for changed_file in diff.changed_files:
        if not coverage_repo.is_known_file(changed_file.path):
            unknown.add(changed_file.path)
            continue
        selected |= coverage_repo.tests_covering_file(
            changed_file.path, changed_file.changed_lines
        )

    return SelectionResult(
        must_run=frozenset(selected),
        full_suite_required=bool(unknown),
        unknown_files=frozenset(unknown),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/selection/test_deterministic.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/selection/__init__.py winnow/selection/deterministic.py tests/selection/test_deterministic.py
git commit -m "feat: add deterministic coverage-based test selection"
```

---

### Task 9: Pluggable risk scorer (heuristic baseline)

**Files:**
- Create: `winnow/selection/risk_scorer.py`
- Test: `tests/selection/test_risk_scorer.py`

**Interfaces:**
- Consumes: `TestOutcomeRepository` (Task 7)
- Produces: `RiskScorer` (abstract method `score(test_id: str, changed_files: frozenset[str]) -> float`),
  `HeuristicRiskScorer(outcome_repo: TestOutcomeRepository)` — Task 10's
  pipeline depends on the `RiskScorer` interface and `.score(...)` signature.

- [ ] **Step 1: Write the failing test**

`tests/selection/test_risk_scorer.py`:
```python
from winnow.ingest.models import TestOutcome
from winnow.selection.risk_scorer import HeuristicRiskScorer
from winnow.store.repository import TestOutcomeRepository
from winnow.store.schema import init_db


def test_heuristic_scorer_returns_failure_rate(tmp_path):
    conn = init_db(tmp_path / "winnow.db")
    outcome_repo = TestOutcomeRepository(conn)
    outcome_repo.add_outcomes("sha1", [TestOutcome("test_a", passed=False, duration_seconds=0.1)])
    outcome_repo.add_outcomes("sha2", [TestOutcome("test_a", passed=True, duration_seconds=0.1)])

    scorer = HeuristicRiskScorer(outcome_repo)

    assert scorer.score("test_a", changed_files=frozenset()) == 0.5


def test_heuristic_scorer_returns_zero_for_unknown_test(tmp_path):
    conn = init_db(tmp_path / "winnow.db")
    outcome_repo = TestOutcomeRepository(conn)

    scorer = HeuristicRiskScorer(outcome_repo)

    assert scorer.score("never_run", changed_files=frozenset()) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/selection/test_risk_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.selection.risk_scorer'`

- [ ] **Step 3: Write minimal implementation**

`winnow/selection/risk_scorer.py`:
```python
from abc import ABC, abstractmethod

from winnow.store.repository import TestOutcomeRepository


class RiskScorer(ABC):
    @abstractmethod
    def score(self, test_id: str, changed_files: frozenset[str]) -> float:
        """Return a risk score in [0, 1] for this test given the changed files."""


class HeuristicRiskScorer(RiskScorer):
    """Baseline strategy: risk = historical failure rate. A follow-up plan
    adds a co-change-aware ML strategy behind the same RiskScorer interface."""

    def __init__(self, outcome_repo: TestOutcomeRepository):
        self._outcome_repo = outcome_repo

    def score(self, test_id: str, changed_files: frozenset[str]) -> float:
        return self._outcome_repo.failure_rate(test_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/selection/test_risk_scorer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/selection/risk_scorer.py tests/selection/test_risk_scorer.py
git commit -m "feat: add pluggable risk scorer with heuristic baseline"
```

---

### Task 10: Selection pipeline (merges deterministic + risk-based selection)

**Files:**
- Create: `winnow/selection/pipeline.py`
- Test: `tests/selection/test_pipeline.py`

**Interfaces:**
- Consumes: `Diff`, `must_run_tests` (Task 8), `RiskScorer` (Task 9),
  `CoverageRepository`, `TestOutcomeRepository` (Task 7)
- Produces: `RankedTest(test_id: str, risk_score: float, reason: str)`,
  `PipelineResult(selected_tests: tuple[RankedTest, ...], full_suite_required: bool, unknown_files: frozenset[str])`,
  `SelectionPipeline(coverage_repo, outcome_repo, risk_scorer, risk_threshold: float = 0.5)`
  with `.run(diff: Diff) -> PipelineResult` — this is what the future GitHub
  Action task will call directly.

- [ ] **Step 1: Write the failing test**

`tests/selection/test_pipeline.py`:
```python
from pathlib import Path

from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.selection.deterministic import ChangedFile, Diff
from winnow.selection.pipeline import SelectionPipeline
from winnow.selection.risk_scorer import RiskScorer
from winnow.store.repository import CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db


class StubRiskScorer(RiskScorer):
    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def score(self, test_id: str, changed_files: frozenset[str]) -> float:
        return self._scores.get(test_id, 0.0)


def _repos(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    return CoverageRepository(conn), TestOutcomeRepository(conn)


def test_pipeline_includes_direct_coverage_and_high_risk_tests(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)

    coverage_repo.add_coverage(
        "sha1", "test_direct", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    outcome_repo.add_outcomes(
        "sha1",
        [
            TestOutcome("test_direct", passed=True, duration_seconds=0.1),
            TestOutcome("test_risky", passed=True, duration_seconds=0.1),
            TestOutcome("test_irrelevant", passed=True, duration_seconds=0.1),
        ],
    )

    scorer = StubRiskScorer({"test_direct": 0.2, "test_risky": 0.9, "test_irrelevant": 0.1})
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer, risk_threshold=0.5)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="a.py"),)))

    ids_and_reasons = {r.test_id: r.reason for r in result.selected_tests}
    assert ids_and_reasons["test_direct"] == "direct coverage overlap"
    assert ids_and_reasons["test_risky"] == "risk score above threshold"
    assert "test_irrelevant" not in ids_and_reasons


def test_pipeline_ranks_by_risk_score_descending(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)

    coverage_repo.add_coverage(
        "sha1", "test_low", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    coverage_repo.add_coverage(
        "sha1", "test_high", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    outcome_repo.add_outcomes(
        "sha1",
        [
            TestOutcome("test_low", passed=True, duration_seconds=0.1),
            TestOutcome("test_high", passed=True, duration_seconds=0.1),
        ],
    )

    scorer = StubRiskScorer({"test_low": 0.1, "test_high": 0.8})
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="a.py"),)))

    assert [r.test_id for r in result.selected_tests] == ["test_high", "test_low"]


def test_pipeline_surfaces_full_suite_fallback(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)
    scorer = StubRiskScorer({})
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="never_seen.py"),)))

    assert result.full_suite_required is True
    assert result.unknown_files == frozenset({"never_seen.py"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/selection/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.selection.pipeline'`

- [ ] **Step 3: Write minimal implementation**

`winnow/selection/pipeline.py`:
```python
from dataclasses import dataclass

from winnow.selection.deterministic import Diff, must_run_tests
from winnow.selection.risk_scorer import RiskScorer
from winnow.store.repository import CoverageRepository, TestOutcomeRepository


@dataclass(frozen=True)
class RankedTest:
    test_id: str
    risk_score: float
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    selected_tests: tuple[RankedTest, ...]
    full_suite_required: bool
    unknown_files: frozenset[str]


class SelectionPipeline:
    def __init__(
        self,
        coverage_repo: CoverageRepository,
        outcome_repo: TestOutcomeRepository,
        risk_scorer: RiskScorer,
        risk_threshold: float = 0.5,
    ):
        self._coverage_repo = coverage_repo
        self._outcome_repo = outcome_repo
        self._risk_scorer = risk_scorer
        self._risk_threshold = risk_threshold

    def run(self, diff: Diff) -> PipelineResult:
        det = must_run_tests(diff, self._coverage_repo)
        changed_paths = frozenset(cf.path for cf in diff.changed_files)

        ranked: list[RankedTest] = []
        for test_id in det.must_run:
            score = self._risk_scorer.score(test_id, changed_paths)
            ranked.append(RankedTest(test_id, score, "direct coverage overlap"))

        remaining = self._outcome_repo.all_test_ids() - det.must_run
        for test_id in remaining:
            score = self._risk_scorer.score(test_id, changed_paths)
            if score >= self._risk_threshold:
                ranked.append(RankedTest(test_id, score, "risk score above threshold"))

        ranked.sort(key=lambda r: r.risk_score, reverse=True)

        return PipelineResult(
            selected_tests=tuple(ranked),
            full_suite_required=det.full_suite_required,
            unknown_files=det.unknown_files,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/selection/test_pipeline.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/selection/pipeline.py tests/selection/test_pipeline.py
git commit -m "feat: add selection pipeline combining deterministic and risk-based selection"
```

---

### Task 11: Synthetic coverage matrix generator

**Files:**
- Create: `winnow/simulate/__init__.py`
- Create: `winnow/simulate/generator.py`
- Test: `tests/simulate/test_generator.py`

**Interfaces:**
- Consumes: `CoverageRepository` (Task 7), `CoverageReport`/`FileCoverage` (Task 2)
- Produces: `SyntheticFixture(test_to_files: dict[str, frozenset[str]], file_names: tuple[str, ...], test_ids: tuple[str, ...])`,
  `generate_coverage_matrix(num_tests: int, num_files: int, seed: int = 42) -> SyntheticFixture`,
  `populate_store(fixture: SyntheticFixture, coverage_repo: CoverageRepository, commit_sha: str) -> None` —
  Task 12's end-to-end validation depends on all three.

- [ ] **Step 1: Write the failing test**

`tests/simulate/test_generator.py`:
```python
from pathlib import Path

from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_generate_coverage_matrix_is_deterministic_for_same_seed():
    fixture_a = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)
    fixture_b = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)

    assert fixture_a.test_to_files == fixture_b.test_to_files


def test_generate_coverage_matrix_every_test_covers_at_least_one_file():
    fixture = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)

    assert all(len(files) >= 1 for files in fixture.test_to_files.values())


def test_populate_store_writes_recorded_coverage(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    repo = CoverageRepository(conn)
    fixture = generate_coverage_matrix(num_tests=5, num_files=3, seed=7)

    populate_store(fixture, repo, commit_sha="sha1")

    for test_id, files in fixture.test_to_files.items():
        for file_path in files:
            assert test_id in repo.tests_covering_file(file_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/simulate/test_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'winnow.simulate'`

- [ ] **Step 3: Write minimal implementation**

`winnow/simulate/__init__.py`:
```python
```
(empty file)

`winnow/simulate/generator.py`:
```python
import random
from dataclasses import dataclass

from winnow.ingest.models import CoverageReport, FileCoverage
from winnow.store.repository import CoverageRepository


@dataclass(frozen=True)
class SyntheticFixture:
    test_to_files: dict[str, frozenset[str]]
    file_names: tuple[str, ...]
    test_ids: tuple[str, ...]


def generate_coverage_matrix(
    num_tests: int, num_files: int, seed: int = 42
) -> SyntheticFixture:
    rng = random.Random(seed)
    file_names = tuple(f"module_{i}.py" for i in range(num_files))
    test_ids = tuple(f"test_{i}" for i in range(num_tests))

    test_to_files: dict[str, frozenset[str]] = {}
    for test_id in test_ids:
        k = rng.randint(1, min(3, num_files))
        test_to_files[test_id] = frozenset(rng.sample(file_names, k))

    return SyntheticFixture(
        test_to_files=test_to_files, file_names=file_names, test_ids=test_ids
    )


def populate_store(
    fixture: SyntheticFixture, coverage_repo: CoverageRepository, commit_sha: str
) -> None:
    for test_id, files in fixture.test_to_files.items():
        report = CoverageReport(
            files=tuple(
                FileCoverage(file_path=f, covered_lines=frozenset({1})) for f in files
            )
        )
        coverage_repo.add_coverage(commit_sha, test_id, report)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/simulate/test_generator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add winnow/simulate/__init__.py winnow/simulate/generator.py tests/simulate/test_generator.py
git commit -m "feat: add synthetic coverage matrix generator for bootstrap validation"
```

---

### Task 12: End-to-end bootstrap validation (proves the safety invariant)

**Files:**
- Test: `tests/test_bootstrap_validation.py`

**Interfaces:**
- Consumes: `must_run_tests`/`Diff`/`ChangedFile` (Task 8),
  `generate_coverage_matrix`/`populate_store` (Task 11),
  `CoverageRepository`/`init_db` (Tasks 6–7)
- Produces: nothing new — this is the plan's proof-of-correctness
  deliverable, referenced from `HANDOFF.md` as the concrete evidence that
  the core engine works.

- [ ] **Step 1: Write the test**

`tests/test_bootstrap_validation.py`:
```python
from pathlib import Path

from winnow.selection.deterministic import ChangedFile, Diff, must_run_tests
from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_deterministic_selection_achieves_full_recall_on_synthetic_ground_truth(
    tmp_path: Path,
):
    """The deterministic selector must recover exactly the tests known (by
    construction) to cover each changed file -- this is the safety-net
    guarantee the whole design depends on."""
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_tests=30, num_files=12, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    for file_path in fixture.file_names:
        expected = {
            test_id
            for test_id, files in fixture.test_to_files.items()
            if file_path in files
        }

        diff = Diff(changed_files=(ChangedFile(path=file_path),))
        result = must_run_tests(diff, coverage_repo)

        assert result.must_run == expected, f"recall failure for {file_path}"
        assert result.full_suite_required is False


def test_deterministic_selection_falls_back_safely_for_unknown_file(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_tests=10, num_files=5, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    diff = Diff(changed_files=(ChangedFile(path="totally_unrelated_file.py"),))
    result = must_run_tests(diff, coverage_repo)

    assert result.full_suite_required is True
    assert result.must_run == frozenset()
```

- [ ] **Step 2: Run to verify it passes**

Run: `pytest tests/test_bootstrap_validation.py -v`
Expected: PASS (2 passed) — this confirms 100% recall against synthetic
ground truth across every file in the fixture, plus a visible fallback for
unknown files.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every task pass (28 tests total: 1 sanity + 3
models + 4 base + 2 cobertura + 2 junit + 2 schema + 5 repository +
3 deterministic + 2 risk_scorer + 3 pipeline + 3 generator + 2 bootstrap
validation — 32 total, adjust count if any task's assertions changed).

- [ ] **Step 4: Update HANDOFF.md**

Replace the "Şu an ne yapılıyor" / "Sıradaki somut adım" sections in
`HANDOFF.md` to reflect that the core engine is built and validated, and
that the next step is the follow-up plan (ML risk scorer, backtesting,
GitHub Action) once a target open-source repo is chosen.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bootstrap_validation.py HANDOFF.md
git commit -m "test: add end-to-end bootstrap validation proving full recall"
```
