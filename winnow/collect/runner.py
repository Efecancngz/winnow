import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class RunnerError(Exception):
    pass


@dataclass(frozen=True)
class InstallResult:
    succeeded: bool
    reason: str | None = None


def install(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> InstallResult:
    result = run(
        ["npm", "ci"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        # Not the locale codec: on a Turkish Windows console that is
        # cp1254, and jest emits bytes it cannot decode. The reader thread
        # then dies and the captured output is lost, which list_test_files
        # would read as "this commit has no test files".
        encoding="utf-8",
        errors="replace",
        shell=(os.name == "nt"),
    )
    if result.returncode != 0:
        return InstallResult(succeeded=False, reason=f"npm ci failed: {result.stderr[-500:]}")
    return InstallResult(succeeded=True)


def _is_absolute_test_path(line: str) -> bool:
    """True for a jest --listTests path, false for its human-readable preamble.

    With --selectProjects, jest prints a header ("Running one project: mobx")
    to stdout before the paths. Filtering on shape rather than on that exact
    string keeps this working if the wording changes: jest always emits
    absolute paths, and the preamble is never one.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("/"):
        return True
    return len(stripped) > 2 and stripped[1] == ":" and stripped[2] in ('\\', "/")


def _jest_argv(jest_project: str | None) -> list[str]:
    """Base jest invocation, scoped to one project when the repo defines several.

    mobx's root config declares `projects: packages/*/jest.config.js`, so an
    unscoped run would install and execute mobx-react and friends on every
    commit. Single-package repos (ts-pattern) have no named projects and jest
    fails if the flag is passed, so it is omitted unless asked for.
    """
    if jest_project is None:
        return ["npx", "jest"]
    return ["npx", "jest", "--selectProjects", jest_project]


def list_test_files(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    jest_project: str | None = None,
) -> list[str]:
    result = run(
        _jest_argv(jest_project) + ["--listTests"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        # Not the locale codec: on a Turkish Windows console that is
        # cp1254, and jest emits bytes it cannot decode. The reader thread
        # then dies and the captured output is lost, which list_test_files
        # would read as "this commit has no test files".
        encoding="utf-8",
        errors="replace",
        shell=(os.name == "nt"),
    )
    if result.returncode != 0:
        raise RunnerError(f"jest --listTests failed: {result.stderr[-500:]}")
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if _is_absolute_test_path(line)
    ]


@dataclass(frozen=True)
class RunResult:
    coverage_path: Path | None
    junit_path: Path | None
    skipped: bool
    reason: str | None = None


def run_tests_for_file(
    repo_path: Path,
    test_file: str,
    output_dir: Path,
    jest_junit_reporter_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    jest_project: str | None = None,
) -> RunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = output_dir / "cobertura-coverage.xml"
    junit_path = output_dir / "junit.xml"
    coverage_path.unlink(missing_ok=True)
    junit_path.unlink(missing_ok=True)

    env = {
        **os.environ,
        "JEST_JUNIT_OUTPUT_DIR": str(output_dir),
        "JEST_JUNIT_OUTPUT_NAME": junit_path.name,
    }

    result = run(
        _jest_argv(jest_project)
        + [
            "--runTestsByPath",
            test_file,
            "--coverage",
            f"--coverageDirectory={output_dir}",
            "--coverageReporters=cobertura",
            # v8, not Jest's default `babel` provider. Babel instruments the
            # source, and on a type-heavy project that is not merely slow: on
            # ts-pattern at 2025-08-31 it consumed a 4GB heap and died, and an
            # 8GB limit only moved the crash to 8.1GB — unbounded, not short.
            # The same file runs in 1.5s without coverage and 4.4s under v8,
            # which emits the same `src/` entries in Cobertura form.
            # This only shows up when walking back into older toolchains, so
            # HEAD-only testing will keep reporting that it works.
            "--coverageProvider=v8",
            "--reporters=default",
            f"--reporters={jest_junit_reporter_path}",
        ],
        cwd=repo_path,
        capture_output=True,
        text=True,
        # Not the locale codec: on a Turkish Windows console that is
        # cp1254, and jest emits bytes it cannot decode. The reader thread
        # then dies and the captured output is lost, which list_test_files
        # would read as "this commit has no test files".
        encoding="utf-8",
        errors="replace",
        env=env,
        shell=(os.name == "nt"),
    )

    if not coverage_path.exists() or not junit_path.exists():
        return RunResult(
            None,
            None,
            skipped=True,
            reason=f"jest did not produce reports for {test_file}: {result.stderr[-500:]}",
        )

    return RunResult(coverage_path, junit_path, skipped=False)
