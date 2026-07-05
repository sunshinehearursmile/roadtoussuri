"""SQLite storage. Two tables: sessions + game_state.

Family is always 5 members (father, mother, son, daughter, elder).
DB path from env DB_PATH; relative paths resolved against project root.
"""
import os
import sqlite3

from mcp_server.config_loader import PROJECT_ROOT


def db_path() -> str:
    # read env live so tests / deploys can repoint the DB without re-import
    p = os.environ.get("DB_PATH", "data/road_to_ussuri.db")
    return p if os.path.isabs(p) else os.path.join(PROJECT_ROOT, p)


def get_conn() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            class_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS game_state (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id),
            day INTEGER DEFAULT 1,
            date TEXT DEFAULT '1862-04-15',
            current_leg INTEGER DEFAULT 0,
            distance_in_leg INTEGER DEFAULT 0,
            total_distance INTEGER DEFAULT 0,
            money REAL DEFAULT 0,
            food_lbs INTEGER DEFAULT 0,
            ammo INTEGER DEFAULT 0,
            equipment INTEGER DEFAULT 0,
            spare_parts INTEGER DEFAULT 0,
            pace TEXT DEFAULT 'steady',
            ration TEXT DEFAULT 'moderate',
            family_json TEXT,
            livestock_json TEXT,
            event_log TEXT DEFAULT '[]'
        );
        """
    )
    conn.commit()
    conn.close()
