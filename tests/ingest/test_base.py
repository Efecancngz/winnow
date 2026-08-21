from pathlib import Path

import pytest

from winnow.ingest.base import CoverageParser, TestResultParser
from winnow.ingest.models import CoverageReport


def test_coverage_parser_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        CoverageParser()


def test_test_result_parser_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        TestResultParser()


def test_incomplete_coverage_parser_cannot_be_instantiated():
    class Incomplete(CoverageParser):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_concrete_coverage_parser_implementing_parse_works():
    class Fake(CoverageParser):
        def parse(self, report_path: Path) -> CoverageReport:
            return CoverageReport(files=())

    parser = Fake()
    assert parser.parse(Path("unused.xml")) == CoverageReport(files=())
