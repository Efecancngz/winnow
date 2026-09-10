from winnow.ingest.models import TestOutcome
from winnow.selection.risk_scorer import HeuristicRiskScorer
from winnow.store.repository import TestOutcomeRepository
from winnow.store.schema import init_db


def test_heuristic_scorer_returns_failure_rate(tmp_path):
    conn = init_db(tmp_path / "winnow.db")
    outcome_repo = TestOutcomeRepository(conn)
    outcome_repo.add_outcomes(
        "sha1", "test/a.test.js", [TestOutcome("a.works", passed=False, duration_seconds=0.1)]
    )
    outcome_repo.add_outcomes(
        "sha2", "test/a.test.js", [TestOutcome("a.works", passed=True, duration_seconds=0.1)]
    )

    scorer = HeuristicRiskScorer(outcome_repo)

    assert scorer.score("test/a.test.js", changed_files=frozenset()) == 0.5


def test_heuristic_scorer_returns_zero_for_unknown_test(tmp_path):
    conn = init_db(tmp_path / "winnow.db")
    outcome_repo = TestOutcomeRepository(conn)

    scorer = HeuristicRiskScorer(outcome_repo)

    assert scorer.score("test/never_run.test.js", changed_files=frozenset()) == 0.0
