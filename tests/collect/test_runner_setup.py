from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winnow.collect.runner import RunnerError, install, list_test_files

WIN_PATH = "C:" + chr(92) + "repo" + chr(92) + "__tests__" + chr(92) + "a.js"


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


def test_list_test_files_ignores_jest_project_header_line(tmp_path: Path):
    # `jest --selectProjects x --listTests` prints a human-readable header to
    # stdout before the paths. Measured against mobx, line 1 is
    # "Running one project: mobx"; unfiltered it is stored as a test path.
    fake_run = MagicMock(
        return_value=_completed(
            returncode=0,
            stdout="Running one project: mobx\n/repo/__tests__/a.js\n",
        )
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == ["/repo/__tests__/a.js"]


def test_list_test_files_keeps_windows_absolute_paths(tmp_path: Path):
    # The collector runs on Windows, where jest emits drive-letter paths.
    fake_run = MagicMock(
        return_value=_completed(
            returncode=0,
            stdout="Running one project: mobx\n" + WIN_PATH + "\n",
        )
    )

    result = list_test_files(tmp_path, run=fake_run)

    assert result == [WIN_PATH]


def test_list_test_files_scopes_to_jest_project_when_given(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=0, stdout="/repo/a.js"))

    list_test_files(tmp_path, run=fake_run, jest_project="mobx")

    args, _ = fake_run.call_args
    assert args[0] == ["npx", "jest", "--selectProjects", "mobx", "--listTests"]


def test_list_test_files_omits_project_flag_when_not_given(tmp_path: Path):
    # Single-package repos (ts-pattern) have no named projects; passing
    # --selectProjects there makes jest fail.
    fake_run = MagicMock(return_value=_completed(returncode=0, stdout="/repo/a.js"))

    list_test_files(tmp_path, run=fake_run)

    args, _ = fake_run.call_args
    assert "--selectProjects" not in args[0]


def test_subprocess_calls_decode_as_utf8_not_locale(tmp_path: Path):
    # Measured on a Turkish Windows locale (cp1254): jest emits bytes that the
    # locale codec cannot decode, the reader thread dies with UnicodeDecodeError
    # and the captured stdout is lost. list_test_files PARSES stdout, so that
    # loss becomes "this commit has zero test files" rather than an error.
    fake_run = MagicMock(return_value=_completed(returncode=0, stdout="/repo/a.js"))

    list_test_files(tmp_path, run=fake_run)

    _, kwargs = fake_run.call_args
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_install_decodes_as_utf8_not_locale(tmp_path: Path):
    fake_run = MagicMock(return_value=_completed(returncode=0))

    install(tmp_path, run=fake_run)

    _, kwargs = fake_run.call_args
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
