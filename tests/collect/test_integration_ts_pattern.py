from pathlib import Path

import pytest

from winnow.collect.history import collect_history
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db

TS_PATTERN_URL = "https://github.com/gvergnaud/ts-pattern.git"
JEST_JUNIT_REPORTER = (
    Path(__file__).parent.parent.parent
    / "tools"
    / "jest-reporters"
    / "node_modules"
    / "jest-junit"
    / "index.js"
)


@pytest.mark.slow
def test_collect_history_against_real_ts_pattern(tmp_path: Path):
    if not JEST_JUNIT_REPORTER.exists():
        pytest.skip(
            "jest-junit not installed — run `npm install` in tools/jest-reporters first"
        )

    conn = init_db(tmp_path / "winnow.db")
    commit_repo = CommitRepository(conn)
    coverage_repo = CoverageRepository(conn)
    outcome_repo = TestOutcomeRepository(conn)

    result = collect_history(
        repo_url=TS_PATTERN_URL,
        clone_dest=tmp_path / "ts-pattern",
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=JEST_JUNIT_REPORTER,
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=2,
    )

    assert len(result.collected) >= 1, (
        f"expected at least 1 collected commit, got 0. "
        f"skipped_commits={result.skipped_commits}, skipped_files={result.skipped_files}"
    )
    assert commit_repo.get_recent(2)
    assert outcome_repo.all_test_ids()
