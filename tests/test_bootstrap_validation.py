from pathlib import Path

from winnow.selection.deterministic import ChangedFile, Diff, must_run_tests
from winnow.simulate.generator import generate_coverage_matrix, populate_store
from winnow.store.repository import CoverageRepository
from winnow.store.schema import init_db


def test_deterministic_selection_achieves_full_recall_on_synthetic_ground_truth(
    tmp_path: Path,
):
    """The deterministic selector must recover exactly the tests known (by
    construction) to cover each changed file -- this is the safety-net
    guarantee the whole design depends on."""
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_tests=30, num_files=12, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    for file_path in fixture.file_names:
        expected = {
            test_id
            for test_id, files in fixture.test_to_files.items()
            if file_path in files
        }

        diff = Diff(changed_files=(ChangedFile(path=file_path),))
        result = must_run_tests(diff, coverage_repo)

        assert result.must_run == expected, f"recall failure for {file_path}"
        assert result.full_suite_required is False


def test_deterministic_selection_falls_back_safely_for_unknown_file(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    coverage_repo = CoverageRepository(conn)

    fixture = generate_coverage_matrix(num_tests=10, num_files=5, seed=99)
    populate_store(fixture, coverage_repo, commit_sha="sha1")

    diff = Diff(changed_files=(ChangedFile(path="totally_unrelated_file.py"),))
    result = must_run_tests(diff, coverage_repo)

    assert result.full_suite_required is True
    assert result.must_run == frozenset()
