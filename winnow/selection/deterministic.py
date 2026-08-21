from dataclasses import dataclass

from winnow.store.repository import CoverageRepository


@dataclass(frozen=True)
class ChangedFile:
    path: str
    changed_lines: frozenset[int] | None = None


@dataclass(frozen=True)
class Diff:
    changed_files: tuple[ChangedFile, ...]


@dataclass(frozen=True)
class SelectionResult:
    must_run: frozenset[str]
    full_suite_required: bool
    unknown_files: frozenset[str]


def must_run_tests(diff: Diff, coverage_repo: CoverageRepository) -> SelectionResult:
    selected: set[str] = set()
    unknown: set[str] = set()

    for changed_file in diff.changed_files:
        if not coverage_repo.is_known_file(changed_file.path):
            unknown.add(changed_file.path)
            continue
        selected |= coverage_repo.tests_covering_file(
            changed_file.path, changed_file.changed_lines
        )

    return SelectionResult(
        must_run=frozenset(selected),
        full_suite_required=bool(unknown),
        unknown_files=frozenset(unknown),
    )
