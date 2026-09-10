import sqlite3
from pathlib import Path

from winnow.simulate.generator import case_ids, generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db


def test_generated_fixture_maps_test_files_to_source_files():
    fixture = generate_coverage_matrix(num_test_files=10, num_files=5, seed=7)

    assert len(fixture.test_files) == 10
    assert all(f.endswith(".test.js") for f in fixture.test_files)
    assert set(fixture.test_file_to_files) == set(fixture.test_files)


def test_generate_coverage_matrix_is_deterministic_for_the_same_seed():
    """The bootstrap recall test relies on the synthetic world being
    reproducible: the same seed must produce the same test-file -> source-file
    mapping every time, not just the same shape."""
    a = generate_coverage_matrix(num_test_files=8, num_files=5, seed=13)
    b = generate_coverage_matrix(num_test_files=8, num_files=5, seed=13)

    assert a.test_file_to_files == b.test_file_to_files


def test_every_generated_test_file_covers_at_least_one_source_file():
    """A test file mapped to zero source files would be unreachable by any
    coverage-based selector and silently invisible to recall measurement."""
    fixture = generate_coverage_matrix(num_test_files=10, num_files=5, seed=7)

    for test_file in fixture.test_files:
        assert len(fixture.test_file_to_files[test_file]) >= 1


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


def test_case_ids_derives_stem_from_test_file_path():
    fixture = generate_coverage_matrix(num_test_files=3, num_files=2, seed=1, cases_per_file=4)

    ids = case_ids(fixture, "test/t_1.test.js")

    assert ids == ("t_1.case_0", "t_1.case_1", "t_1.case_2", "t_1.case_3")


def test_populate_store_writes_cases_per_file_outcomes_per_test_file(tmp_path: Path):
    """cases_per_file must be observable: several JUnit-style cases share one
    Jest test file in the real data, so writing outcomes must scale with
    cases_per_file. This fails if cases_per_file were hardcoded to 1."""
    db_path = tmp_path / "winnow.db"
    conn = init_db(db_path)
    coverage_repo = CoverageRepository(conn)
    outcome_repo = TestOutcomeRepository(conn)

    fixture = generate_coverage_matrix(
        num_test_files=4, num_files=3, seed=7, cases_per_file=5
    )
    populate_store(fixture, coverage_repo, commit_sha="sha1", outcome_repo=outcome_repo)

    raw_conn = sqlite3.connect(db_path)
    try:
        for test_file in fixture.test_files:
            rows = raw_conn.execute(
                "SELECT case_id FROM test_outcomes WHERE test_file = ?",
                (test_file,),
            ).fetchall()
            case_id_values = [row[0] for row in rows]

            assert len(case_id_values) == fixture.cases_per_file
            assert len(set(case_id_values)) == fixture.cases_per_file
            assert set(case_id_values) == set(case_ids(fixture, test_file))
    finally:
        raw_conn.close()

    # Coverage rows stay one per (test file, source file), independent of
    # cases_per_file -- writing per-case outcomes must not change this.
    expected_coverage_rows = sum(
        len(files) for files in fixture.test_file_to_files.values()
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM test_coverage").fetchone()[0]
        == expected_coverage_rows
    )
