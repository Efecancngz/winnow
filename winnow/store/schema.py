import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_coverage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    covered_lines TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
