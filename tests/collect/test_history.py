from pathlib import Path

from winnow.collect.history import CollectionResult, collect_history
from winnow.collect.runner import InstallResult, RunResult
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


def test_collect_history_ingests_successful_commits(tmp_path: Path):
    commit_repo, coverage_repo, outcome_repo = _repos(tmp_path)
    clone_dest = tmp_path / "repo"
    output_root = tmp_path / "out"

    fake_ensure_cloned = lambda repo_url, dest: None
    fake_list_commits = lambda repo_path, n: ["sha1"]
    fake_checkout = lambda repo_path, sha: None
    fake_commit_date = lambda repo_path, sha: "2026-08-01T00:00:00+00:00"
    fake_install = lambda repo_path: InstallResult(succeeded=True)
    fake_list_test_files = lambda repo_path: ["src/a.test.ts"]

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
    assert coverage_repo.tests_covering_file("src/a.ts") == {"a.test.works"}
    assert outcome_repo.all_test_ids() == {"a.test.works"}


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

    def fake_run_tests_for_file(repo_path, test_file, output_dir, reporter_path):
        if test_file == "src/good.test.ts":
            _write_fixture_reports(output_dir)
            return RunResult(
                output_dir / "cobertura-coverage.xml", output_dir / "junit.xml", skipped=False
            )
        return RunResult(None, None, skipped=True, reason="jest crashed")

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
        list_test_files=lambda repo_path: ["src/good.test.ts", "src/bad.test.ts"],
        run_tests_for_file=fake_run_tests_for_file,
    )

    assert result.collected == ("sha1",)
    assert result.skipped_files == (("sha1", "src/bad.test.ts", "jest crashed"),)
    assert coverage_repo.tests_covering_file("src/a.ts") == {"a.test.works"}
