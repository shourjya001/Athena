"""Thin SQLite layer. No ORM by design (BUILD_SPEC §4).

Everything above this module talks to `query`/`query_one`/`execute`/`transaction`
and never touches sqlite3 directly. That boundary is what lets the backend swap
to hosted libSQL later (§20.2) without changing a single caller.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .settings import get_settings

def get_migrations_dir() -> Path:
    base = Path(__file__).resolve().parents[2] / "migrations"
    if base.exists():
        return base
    for alt in [Path("/var/task/migrations"), Path("migrations").resolve()]:
        if alt.exists():
            return alt
    return base


def connect() -> sqlite3.Connection:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
        except Exception:
            pass
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
    conn = connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def query_one(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
    conn = connect()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def execute(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
    with transaction() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or cur.rowcount


# ---------- migrations ----------

def _applied(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}


def migrate(verbose: bool = True) -> list[str]:
    """Run any .sql files in migrations/ that have not been applied, in name order."""
    ran: list[str] = []
    conn = connect()
    try:
        done = _applied(conn)
        for path in sorted(get_migrations_dir().glob("*.sql")):
            if path.name in done:
                continue
            conn.executescript(path.read_text())
            conn.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))",
                (path.name,),
            )
            conn.commit()
            ran.append(path.name)
            if verbose:
                print(f"  applied {path.name}")
    finally:
        conn.close()
    if verbose and not ran:
        print("  schema up to date")
    return ran
