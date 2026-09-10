import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from winnow.collect import repo as repo_ops
from winnow.collect import runner as runner_ops
from winnow.collect.paths import relative_posix
from winnow.collect.runner import InstallResult, RunnerError, RunResult
from winnow.ingest.cobertura import CoberturaParser
from winnow.ingest.junit import JUnitParser
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionResult:
    collected: tuple[str, ...]
    skipped_commits: tuple[tuple[str, str], ...]
    skipped_files: tuple[tuple[str, str, str], ...]


def collect_history(
    repo_url: str,
    clone_dest: Path,
    output_root: Path,
    jest_junit_reporter_path: Path,
    commit_repo: CommitRepository,
    coverage_repo: CoverageRepository,
    outcome_repo: TestOutcomeRepository,
    num_commits: int = 30,
    ensure_cloned: Callable[[str, Path], None] = repo_ops.ensure_cloned,
    list_last_n_commits: Callable[[Path, int], list[str]] = repo_ops.list_last_n_commits,
    checkout: Callable[[Path, str], None] = repo_ops.checkout,
    commit_date: Callable[[Path, str], str] = repo_ops.commit_date,
    install: Callable[[Path], InstallResult] = runner_ops.install,
    list_test_files: Callable[[Path], list[str]] = runner_ops.list_test_files,
    run_tests_for_file: Callable[..., RunResult] = runner_ops.run_tests_for_file,
) -> CollectionResult:
    ensure_cloned(repo_url, clone_dest)
    shas = list_last_n_commits(clone_dest, num_commits)

    cobertura_parser = CoberturaParser()
    junit_parser = JUnitParser()

    collected: list[str] = []
    skipped_commits: list[tuple[str, str]] = []
    skipped_files: list[tuple[str, str, str]] = []

    for sha in shas:
        checkout(clone_dest, sha)

        install_result = install(clone_dest)
        if not install_result.succeeded:
            reason = install_result.reason or "unknown"
            skipped_commits.append((sha, reason))
            logger.warning("skipping commit %s: %s", sha, reason)
            continue

        try:
            test_files = list_test_files(clone_dest)
        except RunnerError as e:
            skipped_commits.append((sha, str(e)))
            logger.warning("skipping commit %s: %s", sha, str(e))
            continue

        commit_repo.add(sha, commit_date(clone_dest, sha))

        any_file_succeeded = False
        succeeded_count = 0
        for test_file in test_files:
            output_dir = output_root / sha
            run_result = run_tests_for_file(
                clone_dest, test_file, output_dir, jest_junit_reporter_path
            )

            if run_result.skipped:
                reason = run_result.reason or "unknown"
                skipped_files.append((sha, test_file, reason))
                logger.warning("skipping file %s in commit %s: %s", test_file, sha, reason)
                continue

            coverage_report = cobertura_parser.parse(run_result.coverage_path)
            outcomes = junit_parser.parse(run_result.junit_path)

            # Once per test file, never once per case: jest produces coverage
            # per file, so a row per case claimed an attribution that was
            # never collected -- and cost 26x the space saying it. Written
            # before the outcome check so an all-skipped file still records
            # what it covered.
            test_file_id = relative_posix(clone_dest, test_file)
            coverage_repo.add_coverage(sha, test_file_id, coverage_report)
            outcome_repo.add_outcomes(sha, test_file_id, outcomes)
            any_file_succeeded = True
            succeeded_count += 1

        if any_file_succeeded:
            collected.append(sha)
            logger.info(
                "collected commit %s (%d/%d test files succeeded)",
                sha,
                succeeded_count,
                len(test_files),
            )

    return CollectionResult(
        collected=tuple(collected),
        skipped_commits=tuple(skipped_commits),
        skipped_files=tuple(skipped_files),
    )
