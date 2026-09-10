from pathlib import Path

from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_generate_coverage_matrix_is_deterministic_for_same_seed():
    fixture_a = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)
    fixture_b = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)

    assert fixture_a.test_to_files == fixture_b.test_to_files


def test_generate_coverage_matrix_every_test_covers_at_least_one_file():
    fixture = generate_coverage_matrix(num_tests=10, num_files=5, seed=1)

    assert all(len(files) >= 1 for files in fixture.test_to_files.values())


def test_populate_store_writes_recorded_coverage(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    repo = CoverageRepository(conn)
    fixture = generate_coverage_matrix(num_tests=5, num_files=3, seed=7)

    populate_store(fixture, repo, commit_sha="sha1")

    for test_id, files in fixture.test_to_files.items():
        for file_path in files:
            assert test_id in repo.tests_covering_file(file_path)
