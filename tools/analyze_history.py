"""Report what a collected history actually contains.

Written to answer one design-deciding question — how many real test failures
exist in collected history — because that number decides whether real history
can supply training labels at all, or whether mutation-based ground truth is
mandatory rather than merely convenient.

Everything else here exists to keep that headline number honest: zero failures
means nothing if the collection silently gathered nothing, so the sanity block
comes first. Two further sections cover findings that only appeared once real
data existed:

- JUnit test time versus wall clock. On ts-pattern the suite's own reported
  runtime is ~0.2s per commit while a commit costs minutes, so a selector
  evaluated on JUnit durations would be optimising a quantity nobody pays.
  Cost is charged per test FILE invoked, not per test.
- The size of the feature space. A repo with a handful of source files leaves
  a coverage-based heuristic very little room to be beaten, which matters for
  choosing a backtest subject.

Usage:
    python tools/analyze_history.py [data/ts-pattern/winnow.db]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data" / "ts-pattern" / "winnow.db"


def q1(conn: sqlite3.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def main() -> None:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not db.exists():
        raise SystemExit(f"no store at {db} — run tools/collect_history.py first")

    conn = sqlite3.connect(db)

    commits = q1(conn, "SELECT COUNT(*) FROM commits")
    outcomes = q1(conn, "SELECT COUNT(*) FROM test_outcomes")
    tests = q1(conn, "SELECT COUNT(DISTINCT test_id) FROM test_outcomes")
    failures = q1(conn, "SELECT COUNT(*) FROM test_outcomes WHERE passed = 0")
    failing_commits = q1(
        conn, "SELECT COUNT(DISTINCT commit_sha) FROM test_outcomes WHERE passed = 0"
    )
    failing_tests = q1(
        conn, "SELECT COUNT(DISTINCT test_id) FROM test_outcomes WHERE passed = 0"
    )

    print("=== collection sanity ===")
    print(f"commits_collected      {commits}")
    print(f"outcome_rows           {outcomes}")
    print(f"distinct_tests         {tests}")
    if commits:
        print(f"tests_per_commit_avg   {outcomes / commits:.1f}")

    print()
    print("=== the number that decides the ground-truth design ===")
    print(f"test_failures          {failures}")
    print(f"commits_with_failure   {failing_commits} / {commits}")
    print(f"distinct_failing_tests {failing_tests}")
    if outcomes:
        print(f"failure_rate           {100 * failures / outcomes:.4f}% of (commit, test) pairs")

    print()
    print("=== cost model: what a selector would actually save ===")
    row = conn.execute(
        "SELECT SUM(duration_seconds), AVG(duration_seconds), MAX(duration_seconds) "
        "FROM test_outcomes"
    ).fetchone()
    if row and row[0] is not None:
        total, avg, mx = row
        print(f"junit_total_seconds    {total:.3f} across all commits")
        if commits:
            print(f"junit_seconds_per_commit {total / commits:.3f}")
        print(f"avg_test_seconds       {avg:.4f}")
        print(f"slowest_test_seconds   {mx:.3f}")
        print("NOTE: wall clock per commit is minutes. The gap is per-file Jest")
        print("startup and type-checking, charged per test FILE selected.")

    print()
    print("=== feature space ===")
    print(f"coverage_rows          {q1(conn, 'SELECT COUNT(*) FROM test_coverage')}")
    print(
        f"distinct_source_files  "
        f"{q1(conn, 'SELECT COUNT(DISTINCT file_path) FROM test_coverage')}"
    )

    print()
    print("=== per-commit spread ===")
    for sha, n, fails in conn.execute(
        "SELECT commit_sha, COUNT(*), SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) "
        "FROM test_outcomes GROUP BY commit_sha ORDER BY MIN(id)"
    ):
        print(f"  {sha[:8]}  tests={n:<5} failures={fails}")

    if failures:
        print()
        print("=== the failures themselves ===")
        for sha, test_id in conn.execute(
            "SELECT commit_sha, test_id FROM test_outcomes WHERE passed = 0 LIMIT 20"
        ):
            print(f"  {sha[:8]}  {test_id}")


if __name__ == "__main__":
    main()
