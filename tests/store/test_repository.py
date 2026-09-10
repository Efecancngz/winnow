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
    # no intersection with recorded lines, but falls back to the full
    # file-level set rather than returning nothing (see dedicated test below)
    assert repo.tests_covering_file("module_a.py", changed_lines=frozenset({99})) == {"test_a"}


def test_coverage_repository_tests_covering_file_falls_back_when_lines_dont_intersect(
    tmp_path: Path,
):
    repo = CoverageRepository(_conn(tmp_path))

    report = CoverageReport(files=(FileCoverage("module_a.py", frozenset({1, 2, 3})),))
    repo.add_coverage("sha1", "test_a", report)

    # changed_lines don't intersect any recorded coverage line, but the file
    # itself is covered by test_a -> fall back to the full file-level set
    # instead of silently returning nothing.
    assert repo.tests_covering_file("module_a.py", changed_lines=frozenset({99})) == {"test_a"}


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
