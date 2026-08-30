"""M1 stand-in for auth. Google OAuth replaces `current_user` at M3 (§12).

Deliberately isolated so that swap touches one function, and every read query
already takes a user_id.
"""
from __future__ import annotations

from . import db
from .settings import get_settings


ALIAS_MAP = {
    "shourjya": "shourjya001@gmail.com",
    "shourjya001": "shourjya001@gmail.com",
    "shourjya001@gmail.com": "shourjya001@gmail.com",
    "shourjya hazra": "shourjya001@gmail.com",
    "prerna": "prernarohilla050802@gmail.com",
    "prerna@gmail.com": "prernarohilla050802@gmail.com",
    "prernarohilla": "prernarohilla050802@gmail.com",
    "prernarohilla050802@gmail.com": "prernarohilla050802@gmail.com",
    "prerna rohilla": "prernarohilla050802@gmail.com",
    "manshi": "manshirohella21@gmail.com",
    "manshi@gmail.com": "manshirohella21@gmail.com",
    "manshirohella": "manshirohella21@gmail.com",
    "manshirohella21@gmail.com": "manshirohella21@gmail.com",
    "manshi rohella": "manshirohella21@gmail.com",
}


def resolve_email(input_str: str) -> str:
    clean = (input_str or "").strip().strip('"').strip("'").lower()
    return ALIAS_MAP.get(clean, clean)


def ensure_user(email: str, display_name: str | None = None) -> int:
    canonical = resolve_email(email)
    row = db.query_one("SELECT id FROM users WHERE email = ?", (canonical,))
    if row:
        db.execute("UPDATE users SET last_seen_at = datetime('now') WHERE id = ?", (row["id"],))
        return int(row["id"])
    return db.execute(
        "INSERT INTO users (email, display_name, created_at, last_seen_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        (canonical, display_name or canonical.split("@")[0]),
    )


def current_user(request: any = None) -> dict:
    s = get_settings()
    email = None
    if request:
        cookie_email = request.cookies.get("trackboard_user")
        if cookie_email:
            clean = resolve_email(cookie_email)
            if clean:
                email = clean
    if not email:
        email = resolve_email(s.dev_user_email)
    uid = ensure_user(email)
    row = db.query_one("SELECT * FROM users WHERE id = ?", (uid,))
    user_dict = dict(row) if row else {"id": uid, "email": email}
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id = ?", (uid,))
    }
    user_dict["answers"] = answers
    user_dict["track"] = answers.get("track", "tech")
    return user_dict

