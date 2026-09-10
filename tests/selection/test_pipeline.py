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
