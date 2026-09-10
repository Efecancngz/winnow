from winnow.ingest.models import FileCoverage, CoverageReport, TestOutcome


def test_file_coverage_is_frozen_and_hashable():
    fc = FileCoverage(file_path="module_a.py", covered_lines=frozenset({1, 2, 3}))
    assert fc.file_path == "module_a.py"
    assert fc.covered_lines == frozenset({1, 2, 3})
    hash(fc)  # must not raise


def test_coverage_report_holds_multiple_files():
    report = CoverageReport(files=(
        FileCoverage("a.py", frozenset({1})),
        FileCoverage("b.py", frozenset({2, 3})),
    ))
    assert len(report.files) == 2
    assert report.files[0].file_path == "a.py"


def test_test_outcome_records_pass_and_duration():
    outcome = TestOutcome(test_id="test_foo", passed=False, duration_seconds=0.42)
    assert outcome.test_id == "test_foo"
    assert outcome.passed is False
    assert outcome.duration_seconds == 0.42
