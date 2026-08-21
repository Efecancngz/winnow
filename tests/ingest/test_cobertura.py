from pathlib import Path

from winnow.ingest.cobertura import CoberturaParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cobertura_sample.xml"


def test_parses_covered_lines_per_file():
    parser = CoberturaParser()
    report = parser.parse(FIXTURE)

    files_by_path = {f.file_path: f for f in report.files}
    assert files_by_path["module_a.py"].covered_lines == frozenset({1, 3})
    assert files_by_path["module_b.py"].covered_lines == frozenset({10})


def test_uncovered_lines_are_excluded():
    parser = CoberturaParser()
    report = parser.parse(FIXTURE)

    files_by_path = {f.file_path: f for f in report.files}
    assert 2 not in files_by_path["module_a.py"].covered_lines
