import random
from dataclasses import dataclass

from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.store.repository import CoverageRepository, TestOutcomeRepository


@dataclass(frozen=True)
class SyntheticFixture:
    """The synthetic world the deterministic selector is validated against.

    It mirrors the real data's shape deliberately: coverage is attributed to a
    test FILE, and several cases share that file. A fixture with one case per
    file would validate a world Winnow no longer lives in.
    """

    test_file_to_files: dict[str, frozenset[str]]
    file_names: tuple[str, ...]
    test_files: tuple[str, ...]
    cases_per_file: int


def generate_coverage_matrix(
    num_test_files: int, num_files: int, seed: int = 42, cases_per_file: int = 3
) -> SyntheticFixture:
    rng = random.Random(seed)
    file_names = tuple(f"module_{i}.py" for i in range(num_files))
    test_files = tuple(f"test/t_{i}.test.js" for i in range(num_test_files))

    test_file_to_files: dict[str, frozenset[str]] = {}
    for test_file in test_files:
        k = rng.randint(1, min(3, num_files))
        test_file_to_files[test_file] = frozenset(rng.sample(file_names, k))

    return SyntheticFixture(
        test_file_to_files=test_file_to_files,
        file_names=file_names,
        test_files=test_files,
        cases_per_file=cases_per_file,
    )


def case_ids(fixture: SyntheticFixture, test_file: str) -> tuple[str, ...]:
    stem = test_file.removeprefix("test/").removesuffix(".test.js")
    return tuple(f"{stem}.case_{i}" for i in range(fixture.cases_per_file))


def populate_store(
    fixture: SyntheticFixture,
    coverage_repo: CoverageRepository,
    commit_sha: str,
    outcome_repo: TestOutcomeRepository | None = None,
) -> None:
    for test_file, files in fixture.test_file_to_files.items():
        report = CoverageReport(
            files=tuple(
                FileCoverage(file_path=f, covered_lines=frozenset({1})) for f in files
            )
        )
        coverage_repo.add_coverage(commit_sha, test_file, report)

        if outcome_repo is not None:
            outcomes = [
                TestOutcome(case_id=case_id, passed=True, duration_seconds=0.1)
                for case_id in case_ids(fixture, test_file)
            ]
            outcome_repo.add_outcomes(commit_sha, test_file, outcomes)
