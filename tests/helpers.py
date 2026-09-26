"""Shared test helpers: a signed-in TestClient with a valid session + CSRF token."""
from __future__ import annotations

from starlette.testclient import TestClient

from trackboard import db, users
from trackboard.main import app

TEST_EMAIL = "tester@example.com"


def signed_in(email: str = TEST_EMAIL, name: str = "Test User") -> TestClient:
    db.migrate(verbose=False)
    uid = users.ensure_user(email, name)
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(users.SESSION_COOKIE, users.issue_session(uid))
    # CSRF token is derived from the session cookie
    class _Req:
        cookies = {users.SESSION_COOKIE: client.cookies.get(users.SESSION_COOKIE)}
    client.csrf = users.csrf_token_for(_Req())  # type: ignore[attr-defined]
    client.uid = uid  # type: ignore[attr-defined]
    return client


def guest() -> TestClient:
    db.migrate(verbose=False)
    return TestClient(app, follow_redirects=False)
