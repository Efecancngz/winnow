from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winnow.collect.runner import RunnerError, install, list_test_files


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_install_succeeds_when_npm_ci_returns_zero(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=0))

    result = install(tmp_path, run=fake_run)

    assert result.succeeded is True
    assert result.reason is None
    fake_run.assert_called_once()
    args, kwargs = fake_run.call_args
    assert args[0] == ["npm", "ci"]
    assert kwargs["cwd"] == tmp_path


def test_install_fails_when_npm_ci_returns_nonzero(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=1, stderr="network error"))

    result = install(tmp_path, run=fake_run)

    assert result.succeeded is False
    assert "npm ci failed" in result.reason
    assert "network error" in result.reason


def test_list_test_files_parses_newline_separated_output(tmp_path: Path):
    fake_run = MagicMock(
        return_value=_completed(
            returncode=0, stdout="/repo/src/a.test.ts\n/repo/src/b.test.ts\n"
        )
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == ["/repo/src/a.test.ts", "/repo/src/b.test.ts"]
    args, kwargs = fake_run.call_args
    assert args[0] == ["npx", "jest", "--listTests"]
    assert kwargs["cwd"] == tmp_path


def test_list_test_files_raises_runner_error_on_nonzero_returncode(tmp_path: Path):
    fake_run = MagicMock(
        return_value=_completed(returncode=1, stderr="jest config error")
    )

    with pytest.raises(RunnerError, match="jest --listTests failed"):
        list_test_files(tmp_path, run=fake_run)


def test_list_test_files_ignores_blank_lines(tmp_path: Path):
    fake_run = MagicMock(
        return_value=_completed(returncode=0, stdout="/repo/src/a.test.ts\n\n")
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == ["/repo/src/a.test.ts"]
