"""Thin database layer. No ORM by design (BUILD_SPEC §4).

Two backends behind one API (`query`, `query_one`, `execute`, `transaction`, `migrate`):

- **local** — SQLite file via the standard library (dev, tests, CI).
- **turso** — hosted libSQL (SQLite-compatible) over its HTTP pipeline API, used when
  `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are set. This is what production uses
  so that nothing is stored on a serverless function's /tmp and nothing runs on the
  owner's machine. Same SQL, same `?` parameters, same row objects.

Only this module may import sqlite3 (enforced by tests/test_layering.py).
"""
from __future__ import annotations

import os
import re
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


# ============================================================ backend selection

def backend() -> str:
    if os.getenv("TURSO_DATABASE_URL") and os.getenv("TURSO_AUTH_TOKEN"):
        return "turso"
    return "local"


# ============================================================ row object (both backends)

class Row:
    """Behaves like sqlite3.Row: r["col"], r[0], dict(r), len(r), r.keys()."""

    __slots__ = ("_cols", "_vals")

    def __init__(self, cols: list[str], vals: list[Any]):
        self._cols = cols
        self._vals = vals

    def keys(self) -> list[str]:
        return list(self._cols)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        try:
            return self._vals[self._cols.index(key)]
        except ValueError:
            raise KeyError(key) from None

    def __contains__(self, key) -> bool:
        return key in self._cols

    def __len__(self) -> int:
        return len(self._vals)

    def __iter__(self):
        return iter(self._vals)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._cols, self._vals))})"


# ============================================================ local sqlite backend

def _sqlite_connect() -> sqlite3.Connection:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
        except sqlite3.OperationalError:
            pass
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# ============================================================ turso (libSQL over HTTP) backend

def _turso_value(v: Any) -> dict[str, Any]:
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray)):
        import base64

        return {"type": "blob", "base64": base64.b64encode(bytes(v)).decode()}
    return {"type": "text", "value": str(v)}


def _from_turso_value(v: dict[str, Any]) -> Any:
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "blob":
        import base64

        return base64.b64decode(v["base64"])
    return v.get("value")


class _TursoCursor:
    def __init__(self, cols: list[str], rows: list[list[Any]], affected: int, last_id: int | None):
        self._cols = cols
        self._rows = rows
        self.rowcount = affected
        self.lastrowid = last_id

    def fetchone(self) -> Row | None:
        return Row(self._cols, self._rows[0]) if self._rows else None

    def fetchall(self) -> list[Row]:
        return [Row(self._cols, r) for r in self._rows]

    def __iter__(self):
        return iter(self.fetchall())


class TursoConnection:
    """One logical connection (a Hrana 'baton') for the duration of a transaction."""

    def __init__(self):
        url = os.environ["TURSO_DATABASE_URL"].strip()
        url = re.sub(r"^(libsql|wss?)://", "https://", url).rstrip("/")
        self._url = url + "/v2/pipeline"
        self._token = os.environ["TURSO_AUTH_TOKEN"].strip()
        self._baton: str | None = None
        self._closed = False

    # -- transport (module-level so tests can monkeypatch) --
    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        return _turso_post(self._url, self._token, body)

    def _run(self, stmts: list[dict[str, Any]], close: bool = False) -> list[dict[str, Any]]:
        reqs: list[dict[str, Any]] = [{"type": "execute", "stmt": s} for s in stmts]
        if close:
            reqs.append({"type": "close"})
        body: dict[str, Any] = {"requests": reqs}
        if self._baton:
            body["baton"] = self._baton
        data = self._post(body)
        self._baton = data.get("baton")
        out = []
        for res in data.get("results", []):
            if res.get("type") == "error":
                raise sqlite3.OperationalError(res.get("error", {}).get("message", "turso error"))
            out.append(res.get("response", {}))
        if close:
            self._closed = True
        return out

    @staticmethod
    def _stmt(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> dict[str, Any]:
        stmt: dict[str, Any] = {"sql": sql}
        if isinstance(params, dict):
            stmt["named_args"] = [{"name": k, "value": _turso_value(v)} for k, v in params.items()]
        elif params:
            stmt["args"] = [_turso_value(v) for v in params]
        return stmt

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> _TursoCursor:
        resp = self._run([self._stmt(sql, params)])[0]
        result = resp.get("result", {})
        cols = [c.get("name") or f"col{i}" for i, c in enumerate(result.get("cols", []))]
        rows = [[_from_turso_value(v) for v in r] for r in result.get("rows", [])]
        lid = result.get("last_insert_rowid")
        return _TursoCursor(cols, rows, int(result.get("affected_row_count") or 0), int(lid) if lid is not None else None)

    def executescript(self, script: str) -> None:
        for stmt in _split_sql(script):
            self.execute(stmt)

    def commit(self) -> None:  # explicit BEGIN/COMMIT are issued by transaction()
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        if not self._closed:
            try:
                self._run([], close=True)
            except Exception:
                pass


def _turso_post(url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=20.0)
    if r.status_code != 200:
        raise sqlite3.OperationalError(f"turso http {r.status_code}: {r.text[:200]}")
    return r.json()


def _split_sql(script: str) -> list[str]:
    """Split a migration file into statements (no string literals contain ';' in ours)."""
    out, buf = [], []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            out.append("\n".join(buf).strip().rstrip(";"))
            buf = []
    if buf:
        out.append("\n".join(buf).strip().rstrip(";"))
    return [s for s in out if s]


# ============================================================ public API

def connect():
    if backend() == "turso":
        return TursoConnection()
    return _sqlite_connect()


@contextmanager
def transaction() -> Iterator[Any]:
    conn = connect()
    turso = isinstance(conn, TursoConnection)
    try:
        if turso:
            conn.execute("BEGIN")
        yield conn
        if turso:
            conn.execute("COMMIT")
        else:
            conn.commit()
    except Exception:
        try:
            if turso:
                conn.execute("ROLLBACK")
            else:
                conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _rows(cur) -> list[Any]:
    return cur.fetchall()


def query(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[Any]:
    conn = connect()
    try:
        return _rows(conn.execute(sql, params))
    finally:
        conn.close()


def query_one(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> Any | None:
    conn = connect()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def execute(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
    """Run one statement and return lastrowid (INSERT) or rowcount."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        if not isinstance(conn, TursoConnection):
            conn.commit()
        return cur.lastrowid if cur.lastrowid else cur.rowcount
    finally:
        conn.close()


def _applied(conn) -> set[str]:
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
            try:
                conn.executescript(path.read_text())
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e) or "already exists" in str(e):
                    if verbose:
                        print(f"  {path.name}: already applied ({e}); recording")
                else:
                    raise
            conn.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))",
                (path.name,),
            )
            if not isinstance(conn, TursoConnection):
                conn.commit()
            ran.append(path.name)
            if verbose:
                print(f"  applied {path.name}")
    finally:
        conn.close()
    if verbose and not ran:
        print("  schema up to date")
    return ran


# ============================================================ one-time seed upload

SEED_TABLES = ("patterns", "problems", "problem_tags", "resources", "companies", "jobs", "agent_runs")


def import_sqlite_file(path: Path, tables: Sequence[str] = SEED_TABLES, batch: int = 150, verbose: bool = True) -> dict[str, int]:
    """Copy content tables from a local SQLite file into the active backend.
    Used once to seed Turso from data/seed_data.db. Never copies user tables."""
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        for t in tables:
            cols = [r["name"] for r in src.execute(f"PRAGMA table_info([{t}])")]
            if not cols:
                continue
            rows = src.execute(f"SELECT * FROM [{t}]").fetchall()
            placeholders = ",".join("?" for _ in cols)
            sql = f"INSERT OR IGNORE INTO [{t}] ({','.join(cols)}) VALUES ({placeholders})"
            n = 0
            for i in range(0, len(rows), batch):
                with transaction() as conn:
                    for r in rows[i:i + batch]:
                        conn.execute(sql, tuple(r[c] for c in cols))
                        n += 1
            counts[t] = n
            if verbose:
                print(f"  {t}: {n} rows")
    finally:
        src.close()
    return counts
