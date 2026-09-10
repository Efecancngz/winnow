import sqlite3
from pathlib import Path

import pytest

from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.store.repository import (
    PERMANENT_FAILURE_MIN_OBSERVATIONS,
    CommitRepository,
    CoverageRepository,
    TestOutcomeRepository,
)
from winnow.store.schema import init_db


def _conn(tmp_path: Path):
    return init_db(tmp_path / "winnow.db")


def _record(repo, sha: str, test_file: str, cases: dict[str, bool]) -> None:
    repo.add_outcomes(
        sha,
        test_file,
        [TestOutcome(c, passed=p, duration_seconds=0.1) for c, p in cases.items()],
    )


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


def test_all_test_files(tmp_path: Path):
    repo = TestOutcomeRepository(_conn(tmp_path))

    repo.add_outcomes(
        "sha1", "test/a.test.js", [TestOutcome("a.works", passed=True, duration_seconds=0.1)]
    )
    repo.add_outcomes(
        "sha1", "test/b.test.js", [TestOutcome("b.works", passed=True, duration_seconds=0.1)]
    )

    assert repo.all_test_files() == {"test/a.test.js", "test/b.test.js"}
