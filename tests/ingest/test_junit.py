from pathlib import Path

from winnow.ingest.junit import JUnitParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "junit_sample.xml"


def test_parses_passed_and_failed_outcomes():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.test_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].passed is True
    assert by_id["tests.test_foo.test_fails"].passed is False
    assert by_id["tests.test_bar.test_also_passes"].passed is True


def test_captures_duration():
    parser = JUnitParser()
    outcomes = parser.parse(FIXTURE)

    by_id = {o.test_id: o for o in outcomes}
    assert by_id["tests.test_foo.test_passes"].duration_seconds == 0.10
