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
    assert result.full_suite_required is False
    assert result.unknown_files == frozenset()


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
