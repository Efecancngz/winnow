from pathlib import Path

from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_generated_fixture_maps_test_files_to_source_files():
    fixture = generate_coverage_matrix(num_test_files=10, num_files=5, seed=7)

    assert len(fixture.test_files) == 10
    assert all(f.endswith(".test.js") for f in fixture.test_files)
    assert set(fixture.test_file_to_files) == set(fixture.test_files)


def test_populate_store_writes_one_coverage_row_per_test_file_and_source_file(
    tmp_path: Path,
):
    """Several cases live in one test file in the real data; coverage is still
    one row per (test file, source file). If this ever writes cases_per_file
    times as many rows, the unique constraint fires."""
    conn = init_db(tmp_path / "winnow.db")
    repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(
        num_test_files=6, num_files=4, seed=7, cases_per_file=5
    )
    populate_store(fixture, repo, commit_sha="sha1")

    expected_rows = sum(len(files) for files in fixture.test_file_to_files.values())
    assert conn.execute("SELECT COUNT(*) FROM test_coverage").fetchone()[0] == expected_rows

    for test_file, files in fixture.test_file_to_files.items():
        for file_path in files:
            assert test_file in repo.test_files_covering(file_path)
