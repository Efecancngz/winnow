from pathlib import Path

from winnow.store.schema import init_db


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
