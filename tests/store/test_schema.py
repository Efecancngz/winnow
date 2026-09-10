import sqlite3
from pathlib import Path

import pytest

from winnow.store.schema import ensure_current_schema, ensure_fresh_store, init_db


def _old_schema_db(db_path: Path) -> None:
    """A store shaped like the pre-selection-unit schema (test_id column,
    no test_file/case_id)."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE commits (sha TEXT PRIMARY KEY, recorded_at TEXT NOT NULL);
        CREATE TABLE test_coverage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_sha TEXT NOT NULL,
            test_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            covered_lines TEXT NOT NULL
        );
        CREATE TABLE test_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_sha TEXT NOT NULL,
            test_id TEXT NOT NULL,
            passed INTEGER NOT NULL,
            duration_seconds REAL NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def test_init_db_creates_expected_tables(tmp_path: Path):
    conn = init_db(tmp_path / "winnow.db")

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"commits", "test_coverage", "test_outcomes"} <= tables


def test_init_db_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    init_db(db_path)
    conn = init_db(db_path)  # must not raise on second call

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "commits" in tables


def test_ensure_fresh_store_allows_a_missing_db(tmp_path: Path):
    ensure_fresh_store(tmp_path / "does-not-exist.db")  # must not raise


def test_ensure_fresh_store_allows_an_empty_current_schema_store(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    init_db(db_path)

    ensure_fresh_store(db_path)  # must not raise


def test_ensure_fresh_store_rejects_an_old_schema_store(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    _old_schema_db(db_path)

    with pytest.raises(SystemExit, match="pre-selection-unit schema"):
        ensure_fresh_store(db_path)


def test_ensure_fresh_store_rejects_a_populated_current_schema_store(tmp_path: Path):
    """Collection has no resume feature: any existing data blocks a new run,
    not just a schema mismatch."""
    db_path = tmp_path / "winnow.db"
    conn = init_db(db_path)
    conn.execute("INSERT INTO commits (sha, recorded_at) VALUES (?, ?)", ("sha1", "now"))
    conn.commit()
    conn.close()

    with pytest.raises(SystemExit, match="does not support resuming"):
        ensure_fresh_store(db_path)


def test_ensure_current_schema_allows_a_current_schema_store(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    conn = init_db(db_path)

    ensure_current_schema(conn, db_path)  # must not raise


def test_ensure_current_schema_rejects_an_old_schema_store(tmp_path: Path):
    db_path = tmp_path / "winnow.db"
    _old_schema_db(db_path)
    conn = sqlite3.connect(db_path)

    with pytest.raises(SystemExit, match="pre-selection-unit schema"):
        ensure_current_schema(conn, db_path)
