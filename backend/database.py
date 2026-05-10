import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/data/tvtracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shows (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id         INTEGER UNIQUE NOT NULL,
            name            TEXT NOT NULL,
            poster_path     TEXT,
            synopsis        TEXT,
            total_seasons   INTEGER DEFAULT 1,
            status          TEXT,
            current_season  INTEGER DEFAULT 1,
            current_episode INTEGER DEFAULT 1,
            current_ep_title TEXT DEFAULT '',
            next_air_date   TEXT,
            finished        INTEGER DEFAULT 0,
            added_at        TEXT DEFAULT (datetime('now')),
            network         TEXT,
            network_logo    TEXT,
            next_ep_info    TEXT
        );
    """)
    # Migraciones seguras
    for col, typedef in [("network", "TEXT"), ("next_ep_info", "TEXT"), ("network_logo", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE shows ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # Cache para calendario de Trakt
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_cache (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            data       TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    # Cache para info de series individuales (tmdb_id → datos)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS show_info_cache (
            tmdb_id    INTEGER PRIMARY KEY,
            data       TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
