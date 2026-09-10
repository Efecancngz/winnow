from dataclasses import dataclass


@dataclass(frozen=True)
class FileCoverage:
    file_path: str
    covered_lines: frozenset[int]


@dataclass(frozen=True)
class CoverageReport:
    files: tuple[FileCoverage, ...]


@dataclass(frozen=True)
class TestOutcome:
    case_id: str
    passed: bool
    duration_seconds: float
