from pathlib import Path

from winnow.ingest.junit import JUnitParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "junit_sample.xml"
BARE_TESTSUITE_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "junit_sample_bare_testsuite.xml"
)


def test_parses_passed_and_failed_outcomes():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.case_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].passed is True
    assert by_id["tests.test_foo.test_fails"].passed is False
    assert by_id["tests.test_bar.test_also_passes"].passed is True


def test_skipped_test_is_not_counted_as_failed():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.case_id: o for o in outcomes}
    assert by_id["tests.test_baz.test_skipped"].passed is True


def test_captures_duration():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.case_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].duration_seconds == 0.10


def test_parses_bare_testsuite_root():
    parser = JUnitParser()
    outcomes = parser.parse(BARE_TESTSUITE_FIXTURE)

    by_id = {o.case_id: o for o in outcomes}
    assert by_id["tests.test_qux.test_passes"].passed is True
    assert by_id["tests.test_qux.test_fails"].passed is False
