"""Database connection, schema init, and seed detection."""
from __future__ import annotations

import os
import sqlite3
from sqlite3 import Connection


def get_db_path() -> str:
    """Resolve SQLite db path from env or default."""
    return os.environ.get("DATABASE_PATH", "campusclaw.db")


def connect() -> Connection:
    """Open a connection with Row factory."""
    db_path = get_db_path()
    # Ensure parent dir exists (for Docker volume /app/data)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id         TEXT    NOT NULL,
    owner_id         INTEGER NOT NULL REFERENCES users(id),
    title            TEXT    NOT NULL,
    content          TEXT,
    file_orig_name   TEXT,
    file_stored_name TEXT,
    file_size        INTEGER,
    file_mime        TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_materials_class ON materials(class_id);

CREATE TABLE IF NOT EXISTS teacher_classes (
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    class_id   TEXT    NOT NULL,
    UNIQUE (teacher_id, class_id)
);
"""


def init_schema(conn: Connection) -> None:
    """Run CREATE TABLE IF NOT EXISTS statements, then idempotent migration."""
    conn.executescript(SCHEMA_SQL)
    migrate_schema(conn)


def migrate_schema(conn: Connection) -> None:
    """Idempotent, lossless column migration for databases created before
    file-upload support. SQLite cannot drop/alter constraints via ALTER TABLE,
    so legacy `content NOT NULL` stays — code writes '' for file materials and
    the API layer maps '' back to null (see MaterialsRepo._normalize)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(materials)")}
    stmts = [
        ("file_orig_name",   "ALTER TABLE materials ADD COLUMN file_orig_name TEXT"),
        ("file_stored_name", "ALTER TABLE materials ADD COLUMN file_stored_name TEXT"),
        ("file_size",        "ALTER TABLE materials ADD COLUMN file_size INTEGER"),
        ("file_mime",        "ALTER TABLE materials ADD COLUMN file_mime TEXT"),
    ]
    changed = False
    for col, sql in stmts:
        if col not in cols:
            conn.execute(sql)
            changed = True
    if changed:
        conn.commit()


def get_upload_dir() -> str:
    """Resolve uploads dir from env or default to <db dir>/uploads.
    Kept env-driven (not importing Config) so seed scripts can run standalone."""
    env = os.environ.get("UPLOAD_DIR")
    if env:
        return env
    return os.path.join(os.path.dirname(get_db_path()) or ".", "uploads")


def ensure_upload_dir() -> str:
    """Create the uploads dir if missing; call once at app startup."""
    path = get_upload_dir()
    os.makedirs(path, exist_ok=True)
    return path


def seed_preset(conn: Connection) -> None:
    """Idempotent preset seeding — runs on EVERY startup (not just empty DBs).

    Inserts only missing preset rows, judged by natural keys
    (users.username unique / materials title+class / teacher_classes unique),
    never modifies or deletes existing data. Old volumes therefore get the
    class-002 accounts/materials/teaching relations backfilled losslessly."""
    from scripts.seed import seed_preset as _seed  # local import: standalone-runnable
    _seed(conn)
    conn.commit()
