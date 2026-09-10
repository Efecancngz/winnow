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
    test_file TEXT NOT NULL,
    file_path TEXT NOT NULL,
    covered_lines TEXT NOT NULL,
    UNIQUE (commit_sha, test_file, file_path)
);

CREATE INDEX IF NOT EXISTS idx_test_coverage_file_path
    ON test_coverage (file_path);

CREATE TABLE IF NOT EXISTS test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_file TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_test_outcomes_test_file
    ON test_outcomes (test_file);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def schema_generation(conn: sqlite3.Connection) -> str:
    """Classify the store this connection points at.

    Returns "absent" if test_outcomes doesn't exist yet (a brand-new store),
    "old" if it predates the selection-unit migration (test_id, no case_id /
    test_file), or "current" for the schema this module creates now.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(test_outcomes)")}
    if not cols:
        return "absent"
    if "case_id" in cols and "test_file" in cols:
        return "current"
    return "old"


def ensure_fresh_store(db_path: Path) -> None:
    """Guard for tools that start a brand-new collection run.

    Collection has no resume feature (deliberately out of scope): it always
    starts from an empty, current-schema store. Run this BEFORE any cloning
    or npm work, so a doomed run fails in milliseconds instead of after
    `npm ci` and `--listTests`.

    Against a pre-branch store this avoids `OperationalError: no such column:
    test_file` (old schema, `CREATE TABLE IF NOT EXISTS` never alters it);
    against a populated current-schema store it avoids a raw
    `sqlite3.IntegrityError` from re-inserting commits that already exist.
    """
    if not db_path.exists():
        return

    conn = sqlite3.connect(db_path)
    try:
        generation = schema_generation(conn)
        if generation == "old":
            raise SystemExit(
                f"{db_path} uses the pre-selection-unit schema (test_id, no "
                "test_file/case_id columns). Collection does not migrate "
                f"existing data. Delete {db_path} and re-run this command."
            )
        if generation == "current":
            (count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
            if count > 0:
                raise SystemExit(
                    f"{db_path} already has {count} commit(s) collected. "
                    "Collection does not support resuming an existing store "
                    f"— delete {db_path} and re-run this command to start over."
                )
    finally:
        conn.close()


def ensure_current_schema(conn: sqlite3.Connection, db_path: Path) -> None:
    """Guard for tools that read from an existing store.

    Analysis against a pre-selection-unit store crashes on the missing
    `case_id` column; this turns that into a clear instruction instead of a
    raw traceback.
    """
    if schema_generation(conn) == "old":
        raise SystemExit(
            f"{db_path} uses the pre-selection-unit schema (test_id, no "
            "test_file/case_id columns). Re-collect it with "
            f"tools/collect_history.py against a fresh {db_path.name} to "
            "analyze it with this tool."
        )
