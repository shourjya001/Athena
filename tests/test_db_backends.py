"""The Turso backend speaks the same API as local SQLite. Exercised with a fake HTTP transport."""
from __future__ import annotations

import json

import pytest

from trackboard import db


class FakeTurso:
    """Minimal Hrana-over-HTTP emulator backed by an in-memory sqlite3 connection."""

    def __init__(self):
        import sqlite3

        self.conn = sqlite3.connect(":memory:", isolation_level=None)  # autocommit, like Turso
        self.conn.row_factory = sqlite3.Row
        self.calls = []

    def __call__(self, url, token, body):
        assert token == "tok" and url.endswith("/v2/pipeline")
        self.calls.append(body)
        results = []
        for req in body["requests"]:
            if req["type"] == "close":
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            stmt = req["stmt"]
            args = [db._from_turso_value(a) for a in stmt.get("args", [])]
            if "named_args" in stmt:
                args = {a["name"]: db._from_turso_value(a["value"]) for a in stmt["named_args"]}
            try:
                cur = self.conn.execute(stmt["sql"], args)
                cols = [{"name": d[0]} for d in (cur.description or [])]
                rows = [[db._turso_value(v) for v in r] for r in cur.fetchall()]
                results.append({"type": "ok", "response": {"type": "execute", "result": {
                    "cols": cols, "rows": rows, "affected_row_count": cur.rowcount if cur.rowcount >= 0 else 0,
                    "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid else None}}})
            except Exception as e:  # mirror turso error shape
                results.append({"type": "error", "error": {"message": str(e)}})
        return {"baton": "b1", "results": results}


@pytest.fixture
def turso(monkeypatch):
    fake = FakeTurso()
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://athena-test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(db, "_turso_post", fake)
    assert db.backend() == "turso"
    return fake


def test_turso_backend_end_to_end(turso):
    ran = db.migrate(verbose=False)
    assert "001_init.sql" in ran and "008_security.sql" in ran
    uid = db.execute("INSERT INTO users (email, display_name, created_at) VALUES (?, ?, datetime('now'))", ("t@example.com", "T"))
    assert uid == 1
    row = db.query_one("SELECT id, email FROM users WHERE id=?", (uid,))
    assert row["email"] == "t@example.com" and row[0] == 1 and dict(row) == {"id": 1, "email": "t@example.com"}
    with db.transaction() as conn:
        conn.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, 'track', 'tech')", (uid,))
        got = conn.execute("SELECT value FROM profile_answers WHERE user_id=?", (uid,)).fetchone()
        assert got["value"] == "tech"
    assert [r["key"] for r in db.query("SELECT key FROM profile_answers WHERE user_id=?", (uid,))] == ["track"]
    # first pipeline call had BEGIN, and a close was sent afterwards
    sqls = [r["stmt"]["sql"] for c in turso.calls for r in c["requests"] if r["type"] == "execute"]
    assert "BEGIN" in sqls and "COMMIT" in sqls
    assert any(r["type"] == "close" for c in turso.calls for r in c["requests"])


def test_turso_transaction_rolls_back_on_error(turso):
    db.migrate(verbose=False)
    with pytest.raises(Exception):
        with db.transaction() as conn:
            conn.execute("INSERT INTO users (email, display_name, created_at) VALUES ('a@example.com','A',datetime('now'))")
            conn.execute("INSERT INTO nope (x) VALUES (1)")
    sqls = [r["stmt"]["sql"] for c in turso.calls for r in c["requests"] if r["type"] == "execute"]
    assert "ROLLBACK" in sqls


def test_value_roundtrip():
    for v in (None, 0, 42, -7, 3.5, "text", "unicode ✓", b"\x00\x01"):
        assert db._from_turso_value(db._turso_value(v)) == v
    assert db._from_turso_value(db._turso_value(True)) == 1


def test_split_sql_handles_comments_and_multiline():
    stmts = db._split_sql("-- c\nCREATE TABLE a (\n  x INT\n);\n\nCREATE INDEX i ON a(x);\n")
    assert len(stmts) == 2 and stmts[0].startswith("CREATE TABLE a")


def test_local_backend_is_default(monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    assert db.backend() == "local"
