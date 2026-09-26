"""Sessions are signed; guests get nothing; owners come from settings."""
from __future__ import annotations

import time

from trackboard import users
from tests.helpers import guest, signed_in


def test_session_signature_is_required():
    tok = users.issue_session(42)
    assert users.verify_session(tok) == 42
    uid, ts, dh, sig = tok.split(".")
    assert users.verify_session(f"{uid}.{ts}.{dh}.{'0' * len(sig)}") is None
    assert users.verify_session(f"7.{ts}.{dh}.{sig}") is None          # uid tampered
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


def test_oauth_redirect_uses_pkce_and_signed_state(monkeypatch):
    from trackboard.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SITE_URL", "https://example.test")
    get_settings.cache_clear()
    try:
        c = guest()
        r = c.get("/auth/google?next=/jobs")
        assert r.status_code == 303
        loc = r.headers["location"]
        assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "code_challenge_method=S256" in loc and "code_challenge=" in loc
        assert "redirect_uri=https%3A%2F%2Fexample.test%2Fauth%2Fgoogle%2Fcallback" in loc
        assert "state=" in loc and "athena_oauth" in r.headers.get("set-cookie", "")
        assert "HttpOnly" in r.headers.get("set-cookie", "")
        # callback without the verifier cookie or with a bad state is rejected
        from trackboard.main import _oauth_state, _verify_oauth_state

        assert _verify_oauth_state("garbage") is None
        st = _oauth_state("/jobs")
        assert _verify_oauth_state(st) == "/jobs"
        assert _verify_oauth_state(st[:-1] + ("0" if st[-1] != "0" else "1")) is None
        r2 = guest().get(f"/auth/google/callback?code=abc&state={st}")
        assert r2.status_code == 303 and "state_mismatch" in r2.headers["location"]
    finally:
        get_settings.cache_clear()


def test_sandbox_can_never_be_owner(monkeypatch):
    from trackboard.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    get_settings.cache_clear()
    try:
        uid = users.create_sandbox_user()
        u = users.load_user(uid)
        assert u["is_sandbox"] and not u["is_owner"]
    finally:
        get_settings.cache_clear()


def test_two_users_never_see_each_others_data():
    from trackboard import db, jobs

    db.migrate(verbose=False)
    jobs.upsert({"company_name": "IsoCo", "title": "Backend Engineer", "description_md": "", "apply_url": "https://boards.greenhouse.io/iso", "source": "greenhouse"})
    job = db.query_one("SELECT id FROM jobs WHERE company_name='IsoCo'")
    a = signed_in("alice@example.com", "Alice")
    b = signed_in("bob@example.com", "Bob")
    a.post(f"/a/jobs/{job['id']}/mark-applied", data={"csrf_token": a.csrf})
    db.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, 'phone', '+91-22222-22222') ON CONFLICT DO NOTHING", (a.uid,))
    assert "IsoCo" in a.get("/pipeline").text
    bp = b.get("/pipeline").text
    assert "IsoCo" not in bp and "22222" not in bp
    assert "22222" not in b.get("/profile").text
    # Bob cannot download Alice's résumé rows or change her application
    app_id = db.query_one("SELECT id FROM applications WHERE user_id=?", (a.uid,))["id"]
    b.post(f"/a/applications/{app_id}/status", data={"csrf_token": b.csrf, "status": "rejected"})
    assert db.query_one("SELECT status FROM applications WHERE id=?", (app_id,))["status"] == "submitted"


def test_session_is_bound_to_device_and_network():
    from trackboard.settings import get_settings

    class R:  # minimal request stand-in
        def __init__(self, ua, ip): self.headers = {"user-agent": ua, "x-forwarded-for": ip}; self.client = None
    a = users.device_hash(R("Mozilla/5.0 Chrome", "49.36.10.20"))
    same_net = users.device_hash(R("Mozilla/5.0 Chrome", "49.36.10.99"))   # last octet changed
    other_net = users.device_hash(R("Mozilla/5.0 Chrome", "8.8.8.8"))
    other_ua = users.device_hash(R("curl/8.0", "49.36.10.20"))
    tok = users.issue_session(5, a)
    assert users.verify_session(tok, a) == 5
    assert users.verify_session(tok, same_net) == 5
    assert users.verify_session(tok, other_net) is None
    assert users.verify_session(tok, other_ua) is None
    # old three-part tokens are rejected outright
    assert users.verify_session("5.1700000000.deadbeef", a) is None


def test_security_txt_and_step_up_prompt(monkeypatch):
    from trackboard.settings import get_settings

    c = guest()
    r = c.get("/.well-known/security.txt")
    assert r.status_code == 200 and "Contact:" in r.text
    get_settings.cache_clear(); monkeypatch.setenv("GOOGLE_CLIENT_ID", "x"); get_settings.cache_clear()
    try:
        loc = c.get("/auth/google").headers["location"]
        assert "prompt=login" in loc  # unknown device -> Google must re-verify the password
    finally:
        get_settings.cache_clear()
