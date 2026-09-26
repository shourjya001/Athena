"""Sessions and the current user.

Security model (Phase 0):
- The session cookie is `athena_session` = "<uid>.<issued_ts>.<hmac>". The HMAC is
  keyed on SESSION_SECRET, so a cookie cannot be forged or edited client-side.
- A request with no valid cookie is a GUEST. Guests get `GUEST_PROFILE`, a
  hard-coded synthetic identity, and never touch `users` / `profile_answers`.
- Owner/admin status comes from settings.owner_email, never a hard-coded address.
- Sandbox users are real rows flagged `is_sandbox` in profile_answers so their
  data can be wiped and they can never be promoted to admin.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from . import db
from .settings import get_settings

SESSION_COOKIE = "athena_session"
LEGACY_COOKIE = "trackboard_user"
SESSION_MAX_AGE = 14 * 86400

# Synthetic, obviously fake, and identical for every visitor.
GUEST_PROFILE: dict[str, str] = {
    "full_name": "Sample Candidate",
    "first_name": "Sample",
    "last_name": "Candidate",
    "email": "sample@example.com",
    "phone": "+91-00000-00000",
    "linkedin_url": "",
    "github_url": "",
    "current_location": "Bengaluru, India",
    "locations": "Bengaluru, Mumbai, Remote",
    "experience_years": "2",
    "notice_period_days": "30",
    "work_authorization": "",
    "titles": "Software Engineer, Backend Engineer",
    "keywords": "Python, FastAPI, PostgreSQL",
    "track": "tech",
}


def _secret() -> bytes:
    return (get_settings().session_secret or "change-me").encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def device_hash(request: Any) -> str:
    """Stable fingerprint of the browser + network the session was issued to.
    IP is reduced to its /24 (IPv4) or /48 (IPv6) so mobile carriers rotating the
    last octet don't log people out, while a stolen cookie replayed from another
    network or browser is rejected. Set SESSION_BIND_DEVICE=false to disable."""
    if request is None or not get_settings().session_bind_device:
        return "any"
    ua = request.headers.get("user-agent", "")[:200]
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or ""
    if ":" in ip:
        prefix = ":".join(ip.split(":")[:3])
    else:
        prefix = ".".join(ip.split(".")[:3])
    return hashlib.sha256(f"{ua}|{prefix}".encode()).hexdigest()[:16]


def issue_session(uid: int, dh: str = "any") -> str:
    payload = f"{uid}.{int(time.time())}.{dh}"
    return f"{payload}.{_sign(payload)}"


def verify_session(token: str | None, dh: str = "any") -> int | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) == 3:  # pre-device-binding token: reject, forces one re-login
        return None
    if len(parts) != 4:
        return None
    uid_s, ts_s, tok_dh, sig = parts
    payload = f"{uid_s}.{ts_s}.{tok_dh}"
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    if tok_dh != "any" and dh != "any" and not hmac.compare_digest(tok_dh, dh):
        return None
    try:
        uid = int(uid_s)
        ts = int(ts_s)
    except ValueError:
        return None
    if time.time() - ts > SESSION_MAX_AGE:
        return None
    return uid


def set_session_cookie(resp: Response, uid: int, request: Any = None) -> None:
    resp.set_cookie(
        SESSION_COOKIE,
        issue_session(uid, device_hash(request)),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=not get_settings().insecure_cookies,
        samesite="lax",
        path="/",
    )
    resp.delete_cookie(LEGACY_COOKIE, path="/")


def clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie(LEGACY_COOKIE, path="/")


def csrf_token_for(request: Request) -> str:
    """CSRF token bound to the session (or to a per-guest cookie)."""
    sess = request.cookies.get(SESSION_COOKIE) or request.cookies.get("athena_guest") or ""
    return _sign("csrf:" + sess)


def guest_user() -> dict[str, Any]:
    return {
        "id": 0,
        "email": None,
        "display_name": "Guest",
        "is_authenticated": False,
        "is_guest": True,
        "is_owner": False,
        "is_sandbox": False,
        "answers": dict(GUEST_PROFILE),
        "track": "tech",
    }


def ensure_user(email: str, display_name: str | None = None) -> int:
    canonical = (email or "").strip().lower()
    if not canonical:
        raise ValueError("email required")
    name = display_name or canonical.split("@")[0]
    row = db.query_one("SELECT id FROM users WHERE email = ?", (canonical,))
    if row:
        db.execute("UPDATE users SET last_seen_at = datetime('now') WHERE id = ?", (row["id"],))
        return int(row["id"])
    return db.execute(
        "INSERT INTO users (email, display_name, created_at, last_seen_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        (canonical, name),
    )


def create_sandbox_user() -> int:
    """Ephemeral guest with pre-seeded sample answers. Never an admin."""
    email = f"sandbox_{secrets.token_hex(6)}@demo.invalid"
    uid = ensure_user(email, "Sandbox Visitor")
    with db.transaction() as conn:
        for k, v in GUEST_PROFILE.items():
            conn.execute(
                "INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
                (uid, k, v),
            )
        conn.execute(
            "INSERT INTO profile_answers (user_id, key, value) VALUES (?, 'is_sandbox', '1') "
            "ON CONFLICT(user_id, key) DO UPDATE SET value='1'",
            (uid,),
        )
    return uid


def load_user(uid: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM users WHERE id = ?", (uid,))
    if not row:
        return None
    user = dict(row)
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id = ?", (uid,))
    }
    s = get_settings()
    user["answers"] = answers
    user["track"] = answers.get("track", "tech")
    user["is_authenticated"] = True
    user["is_guest"] = False
    user["is_sandbox"] = answers.get("is_sandbox") == "1"
    owner = (s.owner_email or "").strip().lower()
    user["is_owner"] = bool(owner) and user.get("email") == owner and not user["is_sandbox"]
    return user


def current_user(request: Any = None) -> dict[str, Any]:
    """Resolve the user for a request. Never trusts anything unsigned."""
    if request is not None:
        uid = verify_session(request.cookies.get(SESSION_COOKIE), device_hash(request))
        if uid:
            user = load_user(uid)
            if user:
                return user
        return guest_user()

    # No request: CLI / cron context. Use the configured dev user.
    s = get_settings()
    email = (s.dev_user_email or "").strip().lower()
    if not email:
        return guest_user()
    uid = ensure_user(email)
    return load_user(uid) or guest_user()


def require_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: 303 to /login for guests, user dict otherwise."""
    user = current_user(request)
    if not user.get("is_authenticated"):
        from .security import safe_next

        nxt = safe_next(request.url.path)
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/login?error=auth_required&next={nxt}"},
        )
    return user


def require_owner(request: Request) -> dict[str, Any]:
    user = require_user(request)
    if not user.get("is_owner"):
        raise HTTPException(status_code=404)
    return user


def login_redirect(request: Request, error: str = "auth_required") -> RedirectResponse:
    from .security import safe_next

    return RedirectResponse(
        f"/login?error={error}&next={safe_next(request.url.path)}", status_code=303
    )
