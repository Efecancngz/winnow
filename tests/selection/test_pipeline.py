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

    def score(self, test_file: str, changed_files: frozenset[str]) -> float:
        return self._scores.get(test_file, 0.0)


def _repos(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    return CoverageRepository(conn), TestOutcomeRepository(conn)


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

    files_and_reasons = {r.test_file: r.reason for r in result.selected_tests}
    assert files_and_reasons["test/direct.test.js"] == "direct coverage overlap"
    assert files_and_reasons["test/risky.test.js"] == "risk score above threshold"
    assert "test/irrelevant.test.js" not in files_and_reasons


def test_pipeline_ranks_by_risk_score_descending(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)

    coverage_repo.add_coverage(
        "sha1", "test/low.test.js", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    coverage_repo.add_coverage(
        "sha1", "test/high.test.js", CoverageReport(files=(FileCoverage("a.py", frozenset({1})),))
    )
    outcome_repo.add_outcomes(
        "sha1", "test/low.test.js", [TestOutcome("low.works", passed=True, duration_seconds=0.1)]
    )
    outcome_repo.add_outcomes(
        "sha1", "test/high.test.js", [TestOutcome("high.works", passed=True, duration_seconds=0.1)]
    )

    scorer = StubRiskScorer({"test/low.test.js": 0.1, "test/high.test.js": 0.8})
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="a.py"),)))

    assert [r.test_file for r in result.selected_tests] == ["test/high.test.js", "test/low.test.js"]


def test_pipeline_surfaces_full_suite_fallback(tmp_path: Path):
    coverage_repo, outcome_repo = _repos(tmp_path)
    scorer = StubRiskScorer({})
    pipeline = SelectionPipeline(coverage_repo, outcome_repo, scorer)

    result = pipeline.run(Diff(changed_files=(ChangedFile(path="never_seen.py"),)))

    assert result.full_suite_required is True
    assert result.unknown_files == frozenset({"never_seen.py"})
