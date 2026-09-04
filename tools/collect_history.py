"""Collect real commit history from an open-source repo into the Winnow store.

The entry point behind the "look at real history data before designing the
ground-truth subsystem" step in HANDOFF.md. The slow integration test proves
the machinery works against two commits; this produces a dataset large enough
to reason about.

Cost, measured against ts-pattern (48 test files, ~450 tests per commit):
roughly 4-10 minutes per commit, since every commit is checked out, npm
installed, and then run through Jest once per test file. The per-commit time
also includes `npm install`, so commits that bump dependencies are noticeably
slower than commits that do not.

Usage:
    python tools/collect_history.py 30
    python tools/collect_history.py 5 --repo https://github.com/user/x.git

Output goes to data/<repo-name>/ (gitignored): the SQLite store, the clone,
and the per-commit Jest reports.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from winnow.collect.history import collect_history  # noqa: E402
from winnow.store.repository import (  # noqa: E402
    CommitRepository,
    CoverageRepository,
    TestOutcomeRepository,
)
from winnow.store.schema import init_db  # noqa: E402

DEFAULT_REPO_URL = "https://github.com/gvergnaud/ts-pattern.git"
JEST_JUNIT_REPORTER = (
    REPO_ROOT / "tools" / "jest-reporters" / "node_modules" / "jest-junit" / "index.js"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("num_commits", type=int, nargs="?", default=30)
    parser.add_argument("--repo", default=DEFAULT_REPO_URL)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    name = args.repo.rstrip("/").split("/")[-1].removesuffix(".git")
    data_dir = REPO_ROOT / "data" / name
    data_dir.mkdir(parents=True, exist_ok=True)

    if not JEST_JUNIT_REPORTER.exists():
        raise SystemExit(
            f"missing {JEST_JUNIT_REPORTER} — run `npm install` in tools/jest-reporters first"
        )

    conn = init_db(data_dir / "winnow.db")

    print(f"=== collecting {args.num_commits} commit(s) of {name} ===", flush=True)
    # perf_counter, not monotonic: on Windows monotonic has a 15.625ms
    # resolution, which is invisible at this scale but wrong by habit.
    start = time.perf_counter()

    result = collect_history(
        repo_url=args.repo,
        clone_dest=data_dir / "repo",
        output_root=data_dir / "reports",
        jest_junit_reporter_path=JEST_JUNIT_REPORTER,
        commit_repo=CommitRepository(conn),
        coverage_repo=CoverageRepository(conn),
        outcome_repo=TestOutcomeRepository(conn),
        num_commits=args.num_commits,
    )

    elapsed = time.perf_counter() - start
    n = len(result.collected)
    print("=== RESULT ===", flush=True)
    print(f"elapsed_total_s {elapsed:.1f}", flush=True)
    print(f"collected_commits {n}", flush=True)
    if n:
        print(f"per_commit_s {elapsed / n:.1f}", flush=True)
    print(f"skipped_commits {len(result.skipped_commits)}", flush=True)
    for sha, reason in result.skipped_commits[:5]:
        print(f"  skip_commit {sha[:8]} {reason[:120]}", flush=True)
    print(f"skipped_files {len(result.skipped_files)}", flush=True)
    for sha, test_file, reason in result.skipped_files[:5]:
        print(f"  skip_file {sha[:8]} {test_file} {reason[:100]}", flush=True)


if __name__ == "__main__":
    main()
