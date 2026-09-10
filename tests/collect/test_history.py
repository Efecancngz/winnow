import sqlite3
from pathlib import Path

from winnow.collect.history import CollectionResult, collect_history
from winnow.collect.runner import InstallResult, RunnerError, RunResult
from winnow.ingest.models import CoverageReport, FileCoverage, TestOutcome
from winnow.store.repository import CommitRepository, CoverageRepository, TestOutcomeRepository
from winnow.store.schema import init_db


def _repos(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")
    return CommitRepository(conn), CoverageRepository(conn), TestOutcomeRepository(conn)


def _write_fixture_reports(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cobertura-coverage.xml").write_text(
        """<?xml version="1.0"?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class name="a" filename="src/a.ts">
          <lines><line number="1" hits="1"/></lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""
    )
    (output_dir / "junit.xml").write_text(
        """<?xml version="1.0"?>
<testsuites>
  <testsuite name="jest">
    <testcase classname="a.test" name="works" time="0.01"/>
  </testsuite>
</testsuites>
"""
    )


def _write_fixture_reports_with_failure(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cobertura-coverage.xml").write_text(
        """<?xml version="1.0"?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class name="a" filename="src/a.ts">
          <lines><line number="1" hits="1"/></lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""
    )
    (output_dir / "junit.xml").write_text(
        """<?xml version="1.0"?>
<testsuites>
  <testsuite name="jest">
    <testcase classname="a.test" name="works" time="0.01"/>
    <testcase classname="a.test" name="broken" time="0.02">
      <failure message="AssertionError">Traceback...</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
    )


def test_collect_history_skips_commit_when_list_test_files_raises(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)

    def fake_list_test_files(repo_path):
        raise RunnerError("jest --listTests failed: config error")

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=tmp_path / "repo",
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=True),
        list_test_files=fake_list_test_files,
        run_tests_for_file=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("should not be called when list_test_files fails")
        ),
    )

    assert result.collected == ()
    assert result.skipped_commits == (
        ("sha1", "jest --listTests failed: config error"),
    )
    assert commit_repo.get_recent(1) == []


def test_collect_history_records_failing_test_outcome(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        _write_fixture_reports_with_failure(output_dir)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=clone_dest,
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=True),
        list_test_files=lambda repo_path: [str(clone_dest / "src" / "a.test.ts")],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    # The file had one passing and one failing case -- the file-level
    # failure rate records that the file failed in this commit.
    assert outcome_repo.failure_rate("src/a.test.ts") == 1.0


def test_collect_history_ingests_successful_commits(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"
    output_root = tmp_path / "out"

    fake_ensure_cloned = lambda repo_url, dest: None
    fake_list_commits = lambda repo_path, n: ["sha1"]
    fake_checkout = lambda repo_path, sha: None
    fake_commit_date = lambda repo_path, sha: "2026-08-01T00:00:00+00:00"
    fake_install = lambda repo_path: InstallResult(succeeded=True)
    fake_list_test_files = lambda repo_path: [str(clone_dest / "src" / "a.test.ts")]

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        _write_fixture_reports(output_dir)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=clone_dest,
        output_root=output_root,
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=fake_ensure_cloned,
        list_last_n_commits=fake_list_commits,
        checkout=fake_checkout,
        commit_date=fake_commit_date,
        install=fake_install,
        list_test_files=fake_list_test_files,
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    assert result.skipped_commits == ()
    assert commit_repo.get_recent(1) == ["sha1"]
    assert coverage_repo.test_files_covering("src/a.ts") == {"src/a.test.ts"}
    assert outcome_repo.all_test_files() == {"src/a.test.ts"}


def test_collect_history_skips_commit_when_install_fails(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=tmp_path / "repo",
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=False, reason="npm ci failed: boom"),
        list_test_files=lambda repo_path: ["src/a.test.ts"],
        run_tests_for_file=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("should not be called when install fails")
        ),
    )

    assert result.collected == ()
    assert result.skipped_commits == (("sha1", "npm ci failed: boom"),)
    assert commit_repo.get_recent(1) == []


def test_collect_history_skips_individual_failed_test_file_but_keeps_commit(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"
    good_test_file = str(clone_dest / "src" / "good.test.ts")
    bad_test_file = str(clone_dest / "src" / "bad.test.ts")

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        if test_file == good_test_file:
            _write_fixture_reports(output_dir)
            return RunResult(
                output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
            )
        return RunResult(None, None, skipped=True, reason="jest crashed")

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=clone_dest,
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=True),
        list_test_files=lambda repo_path: [good_test_file, bad_test_file],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    assert result.skipped_files == (("sha1", bad_test_file, "jest crashed"),)
    assert coverage_repo.test_files_covering("src/a.ts") == {"src/good.test.ts"}


def test_a_test_file_outside_the_repo_root_is_skipped_not_fatal(tmp_path: Path):
    """relative_posix raises ValueError for a path outside clone_dest. Every
    other per-file failure is recorded in skipped_files and the run
    continues -- this one must not abort the whole collection either."""
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"
    # Deliberately outside clone_dest, so relative_posix(clone_dest, ...)
    # raises ValueError instead of returning a relative path.
    outside_test_file = str(tmp_path / "elsewhere" / "a.test.ts")

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        _write_fixture_reports(output_dir)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    result = collect_history(
        repo_url="https://example.invalid/repo.git",
        clone_dest=clone_dest,
        output_root=tmp_path / "out",
        jest_junit_reporter_path=Path("/fake/jest-junit"),
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda repo_url, dest: None,
        list_last_n_commits=lambda repo_path, n: ["sha1"],
        checkout=lambda repo_path, sha: None,
        commit_date=lambda repo_path, sha: "2026-08-01T00:00:00+00:00",
        install=lambda repo_path: InstallResult(succeeded=True),
        list_test_files=lambda repo_path: [outside_test_file],
        run_tests_for_file=fake_run_tests_for_file,
    )

    # The commit is not "collected" (no file succeeded), but the run itself
    # must not raise -- and the failure is recorded, not silently dropped.
    assert result.collected == ()
    assert len(result.skipped_files) == 1
    sha, test_file, reason = result.skipped_files[0]
    assert sha == "sha1"
    assert test_file == outside_test_file
    assert "outside repo root" in reason


def _fixture_reports_with_many_cases(output_dir: Path, num_cases: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cobertura-coverage.xml").write_text(
        """<?xml version="1.0"?>
<coverage><packages><package name="app"><classes>
  <class name="a" filename="src/a.ts"><lines><line number="1" hits="1"/></lines></class>
  <class name="b" filename="src/b.ts"><lines><line number="1" hits="1"/></lines></class>
</classes></package></packages></coverage>
"""
    )
    cases = "\n".join(
        f'<testcase classname="a.test" name="case{i}" time="0.01"/>' for i in range(num_cases)
    )
    (output_dir / "junit.xml").write_text(
        f'<?xml version="1.0"?>\n<testsuites><testsuite name="jest">\n{cases}\n'
        "</testsuite></testsuites>\n"
    )


def test_coverage_is_written_once_per_test_file_not_once_per_case(tmp_path: Path):
    """The whole point of the change: 40 cases in one file used to write 40
    identical copies of the same coverage report."""
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone = tmp_path / "clone"
    clone.mkdir()

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter):
        _fixture_reports_with_many_cases(output_dir, num_cases=40)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    collect_history(
        repo_url="url",
        clone_dest=clone,
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=tmp_path / "reporter.js",
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda url, dest: None,
        list_last_n_commits=lambda dest, n: ["sha1"],
        checkout=lambda dest, sha: None,
        commit_date=lambda dest, sha: "2026-09-10T00:00:00",
        install=lambda dest: InstallResult(succeeded=True),
        list_test_files=lambda dest: [str(clone / "test" / "a.test.js")],
        run_tests_for_file=fake_run_tests_for_file,
    )

    # Real file on disk -- reading via a fresh connection instead of the
    # repository's private _conn confirms exactly the committed rows.
    conn = sqlite3.connect(tmp_path / "winnow.db")
    rows = conn.execute("SELECT COUNT(*) FROM test_coverage").fetchone()[0]
    conn.close()
    # two source files, one test file, one commit -- not 2 * 40
    assert rows == 2
    assert coverage_repo.test_files_covering("src/a.ts") == {"test/a.test.js"}


def test_a_test_file_with_no_cases_still_records_its_coverage(tmp_path: Path):
    """Previously the per-case loop meant an all-skipped file stored nothing."""
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone = tmp_path / "clone"
    clone.mkdir()

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter):
        _fixture_reports_with_many_cases(output_dir, num_cases=0)
        return RunResult(
            output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
        )

    collect_history(
        repo_url="url",
        clone_dest=clone,
        output_root=tmp_path / "reports",
        jest_junit_reporter_path=tmp_path / "reporter.js",
        commit_repo=commit_repo,
        coverage_repo=coverage_repo,
        outcome_repo=outcome_repo,
        num_commits=1,
        ensure_cloned=lambda url, dest: None,
        list_last_n_commits=lambda dest, n: ["sha1"],
        checkout=lambda dest, sha: None,
        commit_date=lambda dest, sha: "2026-09-10T00:00:00",
        install=lambda dest: InstallResult(succeeded=True),
        list_test_files=lambda dest: [str(clone / "test" / "a.test.js")],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert coverage_repo.is_known_file("src/a.ts") is True
