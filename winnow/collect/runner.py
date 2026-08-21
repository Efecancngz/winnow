import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class InstallResult:
    succeeded: bool
    reason: str | None = None


def install(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> InstallResult:
    result = run(["npm", "ci"], cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        return InstallResult(succeeded=False, reason=f"npm ci failed: {result.stderr[-500:]}")
    return InstallResult(succeeded=True)


def list_test_files(
    repo_path: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[str]:
    result = run(
        ["npx", "jest", "--listTests"], cwd=repo_path, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


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
) -> RunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = output_dir / "cobertura-coverage.xml"
    junit_path = output_dir / "junit.xml"

    env = {
        **os.environ,
        "JEST_JUNIT_OUTPUT_DIR": str(output_dir),
        "JEST_JUNIT_OUTPUT_NAME": junit_path.name,
    }

    result = run(
        [
            "npx",
            "jest",
            "--runTestsByPath",
            test_file,
            "--coverage",
            f"--coverageDirectory={output_dir}",
            "--coverageReporters=cobertura",
            "--reporters=default",
            f"--reporters={jest_junit_reporter_path}",
        ],
        cwd=repo_path,
        capture_output=True,
        text=True,
        env=env,
    )

    if not coverage_path.exists() or not junit_path.exists():
        return RunResult(
            None,
            None,
            skipped=True,
            reason=f"jest did not produce reports for {test_file}: {result.stderr[-500:]}",
        )

    return RunResult(coverage_path, junit_path, skipped=False)
