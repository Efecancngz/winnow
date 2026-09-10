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
