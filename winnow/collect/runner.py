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
