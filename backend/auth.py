"""
Real authentication + role-based access control.

Users live in a small SQLite store (data/app.db) — not the JSON files used
for the shared question bank/FSRS state, which stay as-is. Three roles:

  - "student": public self-signup. Uploads are private to them by default.
  - "officer": the original persona type. Shares the official OSS question
    bank, gets competency/iGOT recommendations. Can only be created by an
    admin (see routes gated with @admin_required in app.py).
  - "admin": everything an officer has, plus Manage People / AI Settings.

Sessions are Flask's signed cookie sessions (app.secret_key from app.py) —
no server-side session table needed.
"""

import os
import sqlite3
import time
import uuid
from contextlib import closing
from functools import wraps

from flask import session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "app.db")

VALID_ROLES = ("student", "officer", "admin")

# Demo personas, preserved from the original persona-switcher build so the
# existing seeded cards.json/review_log.json history (keyed by these ids)
# keeps working. Password is intentionally simple + shown in the UI/README —
# these are demo accounts, not production credentials.
DEMO_PASSWORD = "demo1234"
DEMO_USERS = [
    {"id": "demo_officer_1", "name": "Priya Sharma", "email": "priya@demo.oss.gov.in",
     "role": "officer", "title": "Junior Statistical Officer"},
    {"id": "demo_officer_2", "name": "Arjun Mehta", "email": "arjun@demo.oss.gov.in",
     "role": "officer", "title": "Senior Statistical Officer"},
    {"id": "admin_1", "name": "Training Manager", "email": "admin@demo.oss.gov.in",
     "role": "admin", "title": "Admin"},
]


def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if missing and seed demo accounts + a bootstrap admin.
    Safe to call on every app start."""
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                title TEXT,
                leaderboard_opt_in INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        for demo in DEMO_USERS:
            _seed_user_if_missing(
                conn, demo["id"], demo["name"], demo["email"],
                DEMO_PASSWORD, demo["role"], demo["title"], created_by="seed",
            )

        bootstrap_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL")
        bootstrap_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        if bootstrap_email and bootstrap_password:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?", (bootstrap_email,)
            ).fetchone()
            if not existing:
                _seed_user_if_missing(
                    conn, f"admin_{uuid.uuid4().hex[:8]}", "Platform Admin",
                    bootstrap_email, bootstrap_password, "admin", "Admin",
                    created_by="bootstrap",
                )


def _seed_user_if_missing(conn, user_id, name, email, password, role, title, created_by):
    existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash, role, title, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, email, generate_password_hash(password), role, title,
         created_by, str(time.time())),
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "title": row["title"],
        "leaderboard_opt_in": bool(row["leaderboard_opt_in"]),
        "active": bool(row["active"]),
    }


def create_user(name: str, email: str, password: str, role: str = "student",
                 title: str | None = None, created_by: str | None = None) -> dict:
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    if not name or not email or not password:
        raise ValueError("name, email, and password are required")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    user_id = f"{role}_{uuid.uuid4().hex[:10]}"
    with closing(_connect()) as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ValueError("An account with this email already exists")
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, role, title, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, email, generate_password_hash(password), role, title,
             created_by, str(time.time())),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row)


def verify_login(email: str, password: str) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ).fetchone()
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return _row_to_dict(row)


def get_user(user_id: str) -> dict | None:
    if not user_id:
        return None
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_users(role: str | None = None, active_only: bool = True) -> list[dict]:
    query = "SELECT * FROM users"
    clauses, params = [], []
    if role:
        clauses.append("role = ?")
        params.append(role)
    if active_only:
        clauses.append("active = 1")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at ASC"
    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_user_active(user_id: str, active: bool) -> dict | None:
    with closing(_connect()) as conn:
        conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row) if row else None


def set_leaderboard_opt_in(user_id: str, opt_in: bool) -> dict | None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE users SET leaderboard_opt_in = ? WHERE id = ?",
            (1 if opt_in else 0, user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row) if row else None


# ── Session helpers ──────────────────────────────────────────────────────

def login_user(user: dict) -> None:
    session["user_id"] = user["id"]
    session.permanent = True


def logout_user() -> None:
    session.pop("user_id", None)


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user(user_id)
    if user is None or not user["active"]:
        return None
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Authentication required"}), 401
        if user["role"] != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper
