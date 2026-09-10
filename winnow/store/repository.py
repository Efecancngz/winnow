import sqlite3

from winnow.ingest.models import CoverageReport, TestOutcome


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

    def failure_rate(self, test_file: str) -> float:
        """Fraction of commits in which this file had at least one failing case.

        Not the fraction of failing case-runs: a file with one permanently
        broken case out of 88 would score 0.011 under that definition and be
        indistinguishable from a healthy file. The question the scorer asks is
        "is it worth running this file", so the label is "did running it
        surface a failure".
        """
        rows = self._conn.execute(
            """SELECT commit_sha, MIN(passed)
               FROM test_outcomes
               WHERE test_file = ?
               GROUP BY commit_sha""",
            (test_file,),
        ).fetchall()
        if not rows:
            return 0.0
        failed_commits = sum(1 for (_sha, min_passed) in rows if min_passed == 0)
        return failed_commits / len(rows)

    def all_test_files(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT test_file FROM test_outcomes").fetchall()
        return {row[0] for row in rows}
