import random
from dataclasses import dataclass

from winnow.ingest.models import CoverageReport, FileCoverage
from winnow.store.repository import CoverageRepository


@dataclass(frozen=True)
class SyntheticFixture:
    test_to_files: dict[str, frozenset[str]]
    file_names: tuple[str, ...]
    test_ids: tuple[str, ...]


def generate_coverage_matrix(
    num_tests: int, num_files: int, seed: int = 42
) -> SyntheticFixture:
    rng = random.Random(seed)
    file_names = tuple(f"module_{i}.py" for i in range(num_files))
    test_ids = tuple(f"test_{i}" for i in range(num_tests))

    test_to_files: dict[str, frozenset[str]] = {}
    for test_id in test_ids:
        k = rng.randint(1, min(3, num_files))
        test_to_files[test_id] = frozenset(rng.sample(file_names, k))

    return SyntheticFixture(
        test_to_files=test_to_files, file_names=file_names, test_ids=test_ids
    )


def populate_store(
    fixture: SyntheticFixture, coverage_repo: CoverageRepository, commit_sha: str
) -> None:
    for test_id, files in fixture.test_to_files.items():
        report = CoverageReport(
            files=tuple(
                FileCoverage(file_path=f, covered_lines=frozenset({1})) for f in files
            )
        )
        coverage_repo.add_coverage(commit_sha, test_id, report)
