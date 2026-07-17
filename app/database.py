from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "bloomscan.db"
UPLOADS_DIR = BASE_DIR / "static" / "uploads" / "collection"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")

# Vercel (and most serverless hosts) expose an ephemeral, read-only filesystem,
# so persistent user uploads are disabled there and we fall back to catalog images.
IS_SERVERLESS = bool(os.getenv("VERCEL"))
UPLOADS_ENABLED = not IS_SERVERLESS

if IS_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


_PG_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (now()::text)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collection_plants (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        nickname TEXT NOT NULL,
        catalog_plant_id TEXT,
        species_name TEXT,
        scientific_name TEXT,
        notes TEXT,
        image_path TEXT,
        location TEXT,
        acquired_at TEXT,
        last_watered TEXT,
        watering_interval_days INTEGER,
        fertilize_interval_days INTEGER,
        light TEXT,
        water TEXT,
        humidity TEXT,
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL DEFAULT (now()::text),
        updated_at TEXT NOT NULL DEFAULT (now()::text)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plant_records (
        id SERIAL PRIMARY KEY,
        collection_plant_id INTEGER NOT NULL REFERENCES collection_plants(id) ON DELETE CASCADE,
        record_type TEXT NOT NULL,
        note TEXT,
        recorded_at TEXT NOT NULL DEFAULT (now()::text)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_collection_user ON collection_plants(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_records_plant ON plant_records(collection_plant_id)",
)

_SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS collection_plants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        nickname TEXT NOT NULL,
        catalog_plant_id TEXT,
        species_name TEXT,
        scientific_name TEXT,
        notes TEXT,
        image_path TEXT,
        location TEXT,
        acquired_at TEXT,
        last_watered TEXT,
        watering_interval_days INTEGER,
        fertilize_interval_days INTEGER,
        light TEXT,
        water TEXT,
        humidity TEXT,
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS plant_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_plant_id INTEGER NOT NULL,
        record_type TEXT NOT NULL,
        note TEXT,
        recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (collection_plant_id) REFERENCES collection_plants(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_collection_user ON collection_plants(user_id);
    CREATE INDEX IF NOT EXISTS idx_records_plant ON plant_records(collection_plant_id);
"""


class _PgConnection:
    """Adapt a psycopg connection to the sqlite3-style API used across the app.

    Translates ``?`` placeholders to ``%s`` so callers can stay database-agnostic.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("?", "%s"), params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def get_connection():
    if IS_POSTGRES:
        # prepare_threshold=None avoids prepared-statement clashes behind the
        # Neon connection pooler (PgBouncer transaction mode).
        conn = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            prepare_threshold=None,
        )
        wrapper = _PgConnection(conn)
        try:
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def insert_returning_id(conn, sql: str, params=()) -> int:
    """Run an INSERT and return the new row id on either backend."""
    if IS_POSTGRES:
        cur = conn.execute(sql + " RETURNING id", params)
        return int(cur.fetchone()["id"])
    cur = conn.execute(sql, params)
    return int(cur.lastrowid)


def init_db() -> None:
    if not IS_POSTGRES:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ensure_uploads_dir()
        with get_connection() as conn:
            conn.executescript(_SQLITE_SCHEMA)
        return

    with get_connection() as conn:
        for statement in _PG_STATEMENTS:
            conn.execute(statement)


def _ensure_uploads_dir() -> None:
    if not UPLOADS_ENABLED:
        return
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
