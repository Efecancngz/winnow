from pathlib import Path
from unittest.mock import MagicMock

from winnow.collect.runner import run_tests_for_file


def _completed(returncode: int = 0, stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


def test_run_tests_for_file_skips_when_reports_missing(tmp_path: Path):
    output_dir = tmp_path / "out"
    fake_run = MagicMock(return_value=_completed(returncode=1, stderr="jest crashed"))

    result = run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    assert result.skipped is True
    assert result.coverage_path is None
    assert result.junit_path is None
    assert "did not produce reports" in result.reason
    assert "src/a.test.ts" in result.reason


def test_run_tests_for_file_succeeds_when_reports_exist(tmp_path: Path):
    output_dir = tmp_path / "out"

    def fake_run(args, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "cobertura-coverage.xml").write_text("<coverage/>")
        (output_dir / "junit.xml").write_text("<testsuites/>")
        return _completed(returncode=0)

    result = run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    assert result.skipped is False
    assert result.coverage_path == output_dir / "cobertura-coverage.xml"
    assert result.junit_path == output_dir / "junit.xml"


def test_run_tests_for_file_invokes_jest_with_expected_flags(tmp_path: Path):
    output_dir = tmp_path / "out"
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        return _completed(returncode=1)  # reports won't exist; we only check the invocation

    run_tests_for_file(
        tmp_path, "src/a.test.ts", output_dir, Path("/fake/jest-junit"), run=fake_run
    )

    args = captured["args"]
    assert args[0:2] == ["npx", "jest"]
    assert "--runTestsByPath" in args
    assert "src/a.test.ts" in args
    assert "--coverage" in args
    assert f"--coverageDirectory={output_dir}" in args
    assert "--coverageReporters=cobertura" in args
    assert any(a.startswith("--reporters=") and "jest-junit" in a for a in args)
    assert captured["cwd"] == tmp_path
    assert captured["env"]["JEST_JUNIT_OUTPUT_DIR"] == str(output_dir)
    assert captured["env"]["JEST_JUNIT_OUTPUT_NAME"] == "junit.xml"
