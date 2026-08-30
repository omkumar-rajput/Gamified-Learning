"""
Runtime, admin-editable settings (currently just the AI provider/key), stored
in the same SQLite file as auth so an admin can rotate the key from the
running app with no redeploy. See backend/generate.resolve_api_key for the
full precedence order (DB setting -> env var -> local `api-key` file).
"""

import os
import sqlite3
from contextlib import closing

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "app.db")


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * 8}{key[-4:]}"
