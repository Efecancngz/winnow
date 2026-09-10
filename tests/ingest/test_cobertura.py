from pathlib import Path

from winnow.ingest.cobertura import CoberturaParser

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cobertura_sample.xml"
SEP = chr(92)  # backslash, written this way to avoid escaping noise


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


def test_windows_separators_are_normalised_to_posix(tmp_path: Path):
    # Measured against mobx on Windows: jest's cobertura reporter emits
    # `packages\mobx\srcpiction.ts`, while git diffs always use `/`.
    # Storing the raw form makes every lookup miss, so `is_known_file` returns
    # False, the selector demands the full suite, and nothing ever errors.
    report_path = tmp_path / "cobertura-coverage.xml"
    report_path.write_text(
        '<?xml version="1.0"?>'
        "<coverage><packages><package><classes>"
        '<class filename="packages@mobx@src@api@action.ts">'
        '<lines><line number="7" hits="1"/></lines>'
        "</class></classes></package></packages></coverage>".replace("@", SEP)
    )

    report = CoberturaParser().parse(report_path)

    paths = [f.file_path for f in report.files]
    assert paths == ["packages/mobx/src/api/action.ts"]
