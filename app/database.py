from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "bloomscan.db"
UPLOADS_DIR = BASE_DIR / "static" / "uploads" / "collection"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
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
        )


@contextmanager
def get_connection():
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
