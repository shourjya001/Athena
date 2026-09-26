"""Request-level security helpers: safe redirects, CSRF, rate limits, URL allow-list,
and the response-header middleware. No third-party dependencies.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from . import db

# ---------- redirects ----------

_NEXT_RE = re.compile(r"^/(?![/\\])[A-Za-z0-9_\-./?=&%+]*$")


def safe_next(value: str | None, default: str = "/") -> str:
    """Only same-origin absolute paths. Rejects //host, backslashes, schemes."""
    v = (value or "").strip()
    if not v or not _NEXT_RE.match(v) or ":" in v:
        return default
    return v


# ---------- CSRF ----------

def check_csrf(request: Request, submitted: str | None) -> None:
    from .users import csrf_token_for

    expected = csrf_token_for(request)
    if not submitted or submitted != expected:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


async def csrf_from_request(request: Request) -> str | None:
    tok = request.headers.get("x-csrf-token")
    if tok:
        return tok
    ctype = request.headers.get("content-type", "")
    try:
        if "application/json" in ctype:
            body = await request.json()
            return (body or {}).get("csrf_token")
        form = await request.form()
        return form.get("csrf_token")
    except Exception:
        return None


# ---------- rate limits (SQLite, no extra deps) ----------

def rate_limit(key: str, limit: int, window_s: int) -> None:
    """Raise 429 when `key` exceeds `limit` hits in the current window."""
    now = int(time.time())
    window_start = now - (now % window_s)
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT count FROM rate_limits WHERE key=? AND window_start=?",
            (key, window_start),
        ).fetchone()
        count = (row["count"] if row else 0) + 1
        conn.execute(
            "INSERT INTO rate_limits (key, window_start, count) VALUES (?, ?, ?) "
            "ON CONFLICT(key, window_start) DO UPDATE SET count=excluded.count",
            (key, window_start, count),
        )
        # opportunistic cleanup
        conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (window_start - 3 * window_s,))
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a few minutes.")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


# ---------- outbound URL allow-list + SSRF guard ----------

ALLOWED_APPLY_SUFFIXES = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "smartrecruiters.com",
    "recruitee.com", "workable.com", "darwinbox.in", "darwinbox.com", "oraclecloud.com",
    "taleo.net", "successfactors.com", "icims.com", "jobvite.com", "bamboohr.com",
    "amazon.jobs", "careers.google.com", "google.com", "microsoft.com", "apple.com",
    "jpmorganchase.com", "morganstanley.com", "goldmansachs.com", "barclays.com", "citi.com",
    "instacart.careers", "remotive.com", "wellfound.com", "linkedin.com", "naukri.com",
)


def host_allowed(host: str, extra_hosts: set[str] | None = None) -> bool:
    h = (host or "").lower().rstrip(".")
    if not h:
        return False
    if extra_hosts and h in extra_hosts:
        return True
    return any(h == s or h.endswith("." + s) for s in ALLOWED_APPLY_SUFFIXES)


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
    )


def validate_outbound_url(url: str, extra_hosts: set[str] | None = None, strict: bool = False) -> str:
    """Return the URL if it is https and resolves only to public IPs (blocks
    javascript:, http:, and anything pointing at loopback/link-local/private
    ranges). With strict=True the host must also be on the allow-list — used
    before any server-side fetch (liveness checks) to prevent SSRF."""
    p = urlparse(url or "")
    if p.scheme != "https" or not p.hostname:
        raise HTTPException(status_code=400, detail="Only https apply links are allowed")
    if strict and not host_allowed(p.hostname, extra_hosts):
        raise HTTPException(status_code=400, detail="Apply link host is not on the allow-list")
    try:
        infos = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Apply link host could not be resolved")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise HTTPException(status_code=400, detail="Apply link resolves to a private address")
    return url


# ---------- headers ----------

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data: https://i.ytimg.com https://*.ytimg.com; "
    "frame-src https://www.youtube-nocookie.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self' https://accounts.google.com; "
    "object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        path = request.url.path
        if path.startswith("/static/"):
            h.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif "text/html" in h.get("content-type", ""):
            h.setdefault("Cache-Control", "private, no-store")
        return resp
