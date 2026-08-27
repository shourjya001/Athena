"""M1 stand-in for auth. Google OAuth replaces `current_user` at M3 (§12).

Deliberately isolated so that swap touches one function, and every read query
already takes a user_id.
"""
from __future__ import annotations

from . import db
from .settings import get_settings


def ensure_user(email: str, display_name: str | None = None) -> int:
    row = db.query_one("SELECT id FROM users WHERE email = ?", (email.lower(),))
    if row:
        db.execute("UPDATE users SET last_seen_at = datetime('now') WHERE id = ?", (row["id"],))
        return int(row["id"])
    return db.execute(
        "INSERT INTO users (email, display_name, created_at, last_seen_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        (email.lower(), display_name or email.split("@")[0]),
    )


def current_user(request: any = None) -> dict:
    s = get_settings()
    email = None
    if request:
        cookie_email = request.cookies.get("trackboard_user")
        if cookie_email:
            clean = cookie_email.strip().strip('"').strip("'").lower()
            if not s.allowlist or clean in s.allowlist or clean == s.dev_user_email.lower():
                email = clean
    if not email:
        email = s.dev_user_email
    uid = ensure_user(email)
    row = db.query_one("SELECT * FROM users WHERE id = ?", (uid,))
    return dict(row) if row else {"id": uid, "email": email}
