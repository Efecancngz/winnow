import sqlite3
from pathlib import Path

import pytest

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
