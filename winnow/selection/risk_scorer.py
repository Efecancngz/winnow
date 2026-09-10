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
