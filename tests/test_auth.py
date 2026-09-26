"""Sessions are signed; guests get nothing; owners come from settings."""
from __future__ import annotations

import time

from trackboard import users
from tests.helpers import guest, signed_in


def test_session_signature_is_required():
    tok = users.issue_session(42)
    assert users.verify_session(tok) == 42
    uid, ts, sig = tok.split(".")
    assert users.verify_session(f"{uid}.{ts}.{'0' * len(sig)}") is None
    assert users.verify_session(f"7.{ts}.{sig}") is None          # uid tampered
    assert users.verify_session("shourjya") is None                # legacy plaintext format
    assert users.verify_session(None) is None


def test_expired_session_rejected(monkeypatch):
    tok = users.issue_session(1)
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + users.SESSION_MAX_AGE + 10)
    assert users.verify_session(tok) is None


def test_legacy_email_cookie_is_ignored():
    c = guest()
    c.cookies.set("trackboard_user", "someone@example.com")
    r = c.get("/profile")
    assert r.status_code == 303 and "/login" in r.headers["location"]


def test_login_page_uses_fixed_error_codes():
    c = guest()
    r = c.get("/login?error=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E")
    assert r.status_code == 200
    assert "onerror" not in r.text
    r2 = c.get("/login?error=auth_required")
    assert "Please sign in to continue." in r2.text


def test_next_parameter_cannot_leave_site():
    from trackboard.security import safe_next

    assert safe_next("https://evil.example") == "/"
    assert safe_next("//evil.example") == "/"
    assert safe_next("/jobs?x=1") == "/jobs?x=1"
    assert safe_next("javascript:alert(1)") == "/"
    c = guest()
    r = c.get("/auth/google?next=https://evil.example")
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "evil.example" not in loc


def test_owner_is_derived_from_settings(monkeypatch):
    from trackboard.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    get_settings.cache_clear()
    try:
        c = signed_in("owner@example.com", "Owner")
        assert c.get("/system").status_code == 200
        assert "Admin" in c.get("/system").text
        c2 = signed_in("notowner@example.com")
        assert "Admin" not in c2.get("/system").text
        r = c2.post(f"/system/users/{c.uid}/delete", data={"csrf_token": c2.csrf})
        assert r.status_code == 404
    finally:
        get_settings.cache_clear()


def test_sandbox_creates_isolated_user_and_logout_wipes_it():
    from trackboard import db

    c = guest()
    r = c.get("/auth/demo-sandbox")
    assert r.status_code == 303
    assert users.SESSION_COOKIE in r.cookies
    uid = users.verify_session(r.cookies[users.SESSION_COOKIE])
    row = db.query_one("SELECT email FROM users WHERE id=?", (uid,))
    assert row and row["email"].endswith("@demo.invalid")
    c.cookies.set(users.SESSION_COOKIE, r.cookies[users.SESSION_COOKIE])
    assert "Sandbox mode" in c.get("/jobs").text
    c.get("/logout")
    assert db.query_one("SELECT id FROM users WHERE id=?", (uid,)) is None


def test_logout_clears_cookie():
    c = signed_in()
    r = c.get("/logout")
    assert r.status_code == 303
    assert "athena_session=" in r.headers.get("set-cookie", "") and "Max-Age=0" in r.headers.get("set-cookie", "")


def test_self_delete_removes_all_rows():
    from trackboard import db

    c = signed_in("deleteme@example.com")
    db.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, 'phone', '+91-11111-11111')", (c.uid,))
    r = c.post("/profile/delete", data={"csrf_token": c.csrf})
    assert r.status_code == 303
    assert db.query_one("SELECT id FROM users WHERE id=?", (c.uid,)) is None
    assert db.query_one("SELECT 1 FROM profile_answers WHERE user_id=?", (c.uid,)) is None
