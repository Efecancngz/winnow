import sqlite3

from winnow.ingest.models import CoverageReport, TestOutcome

# A case is only judged "permanently failing" once there is enough history to
# tell constancy from coincidence. At 3 collected commits every case looks
# constant, so an unguarded rule deletes the dataset. Same shape as the Phase 2
# circuit breaker: a rate over a minimum sample, never N-in-a-row.
PERMANENT_FAILURE_MIN_OBSERVATIONS = 5


class CommitRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, sha: str, recorded_at: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO commits (sha, recorded_at) VALUES (?, ?)",
            (sha, recorded_at),
        )
        self._conn.commit()

    def get_recent(self, limit: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT sha FROM commits ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]


class CoverageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_coverage(self, commit_sha: str, test_file: str, report: CoverageReport) -> None:
        """One row per (commit, test file, source file).

        Jest produces coverage per test FILE, never per test case. Writing a
        row per case claimed an attribution that was never collected -- and
        cost 26x the space saying it.
        """
        for file_cov in report.files:
            lines_csv = ",".join(str(n) for n in sorted(file_cov.covered_lines))
            self._conn.execute(
                """INSERT INTO test_coverage (commit_sha, test_file, file_path, covered_lines)
                   VALUES (?, ?, ?, ?)""",
                (commit_sha, test_file, file_cov.file_path, lines_csv),
            )
        self._conn.commit()

    def is_known_file(self, file_path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM test_coverage WHERE file_path = ? LIMIT 1",
            (file_path,),
        ).fetchone()
        return row is not None

    def test_files_covering(
        self, file_path: str, changed_lines: frozenset[int] | None = None
    ) -> set[str]:
        rows = self._conn.execute(
            "SELECT test_file, covered_lines FROM test_coverage WHERE file_path = ?",
            (file_path,),
        ).fetchall()

        matched: set[str] = set()
        all_test_files: set[str] = set()
        for test_file, lines_csv in rows:
            all_test_files.add(test_file)
            if changed_lines is None:
                matched.add(test_file)
                continue
            covered = {int(n) for n in lines_csv.split(",") if n}
            if covered & changed_lines:
                matched.add(test_file)

        if changed_lines is not None and not matched and all_test_files:
            return all_test_files
        return matched


class TestOutcomeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_outcomes(
        self, commit_sha: str, test_file: str, outcomes: list[TestOutcome]
    ) -> None:
        self._conn.executemany(
            """INSERT INTO test_outcomes
                   (commit_sha, test_file, case_id, passed, duration_seconds)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (commit_sha, test_file, o.case_id, int(o.passed), o.duration_seconds)
                for o in outcomes
            ],
        )
        self._conn.commit()

    def failure_rate(
        self,
        test_file: str,
        min_observations: int = PERMANENT_FAILURE_MIN_OBSERVATIONS,
    ) -> float:
        """Fraction of commits in which this file had at least one failing case.

        Not the fraction of failing case-runs: a file with one permanently
        broken case out of 88 would score 0.011 under that definition and be
        indistinguishable from a healthy file. The question the scorer asks is
        "is it worth running this file", so the label is "did running it
        surface a failure".

        Cases that have never passed across at least `min_observations`
        commits are excluded before the roll-up: they are constant, not
        signal, and would otherwise pin the whole file at 1.0 forever.
        """
        excluded = self._permanently_failing_cases(test_file, min_observations)

        rows = self._conn.execute(
            "SELECT commit_sha, case_id, passed FROM test_outcomes WHERE test_file = ?",
            (test_file,),
        ).fetchall()
        if not rows:
            return 0.0

        commits: dict[str, bool] = {}
        for commit_sha, case_id, passed in rows:
            if case_id in excluded:
                continue
            commits[commit_sha] = commits.get(commit_sha, False) or passed == 0

        if not commits:
            return 0.0
        return sum(1 for failed in commits.values() if failed) / len(commits)

    def _permanently_failing_cases(self, test_file: str, min_observations: int) -> set[str]:
        # COUNT(DISTINCT commit_sha), not COUNT(*): test_outcomes carries no
        # uniqueness constraint, so duplicate rows for the same case within
        # one commit must not let it reach the observation floor early.
        # "Observations" means commits the case was seen in, per the spec.
        rows = self._conn.execute(
            """SELECT case_id
               FROM test_outcomes
               WHERE test_file = ?
               GROUP BY case_id
               HAVING COUNT(DISTINCT commit_sha) >= ? AND MAX(passed) = 0""",
            (test_file, min_observations),
        ).fetchall()
        return {row[0] for row in rows}

    def all_test_files(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT test_file FROM test_outcomes").fetchall()
        return {row[0] for row in rows}
