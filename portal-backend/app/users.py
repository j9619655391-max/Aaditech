"""
Local portal accounts (username + password) created by the one-click setup
wizard. SQLite-backed (stdlib `sqlite3`, same pattern as cleanup_store.py),
so an admin login works even when Azure AD SSO isn't configured yet — a fresh
deploy can bootstrap its first admin purely from the wizard.

Passwords are stored as bcrypt hashes (passlib), never plaintext.

Roles reuse the RBAC model in app/roles.py; the wizard grants the bootstrap
admin VIEWER + SUPPORT_ENGINEER + CLEANUP_APPROVER.
"""
from __future__ import annotations

import os
import sqlite3
import threading

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_DB_PATH = os.environ.get("AADITECH_DB_PATH", "")  # "" => in-memory
_conn: sqlite3.Connection | None = None
_conn_lock = threading.RLock()


def init_db(path: str = "") -> None:
    """Point the local-user store at a persistent DB file. "" => in-memory."""
    global _conn, _DB_PATH
    if _conn is not None:
        _conn.close()
    _conn = None
    _DB_PATH = path
    _get_conn()


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(
                _DB_PATH or ":memory:",
                check_same_thread=False,
            )
            _conn.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "username TEXT PRIMARY KEY, "
                "password_hash TEXT NOT NULL, "
                "roles TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            _conn.commit()
        return _conn


def create_user(username: str, password: str, roles: list[str]) -> dict:
    """Creates a local account. Raises ValueError if the username is taken."""
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be empty")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    conn = _get_conn()
    with _conn_lock:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            raise ValueError(f"User '{username}' already exists")

        from datetime import datetime, timezone

        conn.execute(
            "INSERT INTO users (username, password_hash, roles, created_at) VALUES (?, ?, ?, ?)",
            (
                username,
                pwd_context.hash(password),
                ",".join(roles),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

    return get_user(username)


def get_user(username: str) -> dict | None:
    row = _get_conn().execute(
        "SELECT username, password_hash, roles FROM users WHERE username=?", (username,)
    ).fetchone()
    if not row:
        return None
    return {
        "username": row[0],
        "password_hash": row[1],
        "roles": [r for r in row[2].split(",") if r],
    }


def verify_credentials(username: str, password: str) -> dict | None:
    """Returns the user dict on a successful login, else None."""
    user = get_user(username)
    if not user:
        return None
    if not pwd_context.verify(password, user["password_hash"]):
        return None
    return {"username": user["username"], "roles": user["roles"]}
