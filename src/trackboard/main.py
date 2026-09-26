"""Athena web app. Every route is public-read or explicitly gated with
`users.require_user` / `users.require_owner`; every state change is a POST that
checks a CSRF token; every number shown comes from `stats.site_stats()`."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from . import content, db, drill, listing, llm, practice, stats, users
from .security import (
    SecurityHeadersMiddleware, check_csrf, client_ip, csrf_from_request, host_allowed,
    rate_limit, safe_next, validate_outbound_url,
)
from .settings import get_settings

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
templates = Jinja2Templates(directory=str(BASE / "templates"))
STATIC_VERSION = "20260926a"

LOGIN_ERRORS = {
    "auth_required": "Please sign in to continue.",
    "oauth_cancelled": "Google sign-in was cancelled.",
    "oauth_failed": "Google sign-in failed. Please try again.",
    "oauth_unconfigured": "Google sign-in is not configured on this server yet.",
    "email_unverified": "Your Google email address is not verified.",
    "not_allowed": "This account is not on the access list for this instance.",
    "state_mismatch": "Sign-in session expired. Please try again.",
    "unauthorized": "You do not have access to that page.",
}


def format_ist(val: Any) -> str:
    if not val:
        return ""
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(str(val).strip().replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return str(val)


templates.env.filters["ist"] = format_ist
templates.env.filters["reldate"] = listing._rel_date
templates.env.globals["static_v"] = STATIC_VERSION


# ---------------------------------------------------------------- helpers

def render(request: Request, name: str, ctx: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    user = ctx.get("user") or users.current_user(request)
    base = {
        "user": user,
        "csrf_token": users.csrf_token_for(request),
        "stats": stats.site_stats(),
        "site_url": get_settings().site_url,
        "path": request.url.path,
    }
    base.update(ctx)
    resp = templates.TemplateResponse(request, name, base, status_code=status_code)
    if not request.cookies.get(users.SESSION_COOKIE) and not request.cookies.get("athena_guest"):
        resp.set_cookie("athena_guest", secrets.token_hex(16), max_age=7 * 86400, httponly=True,
                        samesite="lax", secure=not get_settings().insecure_cookies, path="/")
    return resp


async def csrf_guard(request: Request) -> None:
    check_csrf(request, await csrf_from_request(request))


def answers_for(uid: int) -> dict[str, str]:
    return {r["key"]: r["value"] for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (uid,))}


def load_bank_for(user: dict[str, Any]) -> dict[str, Any]:
    """Bullet bank for the signed-in user. Owner uses config/resume.yaml (identity
    overlaid from their profile); everyone else gets a bank built from their
    uploaded master résumé. No user ever sees another user's bank."""
    import yaml

    answers = user.get("answers") or {}
    bank: dict[str, Any] = {}
    if user.get("is_owner"):
        for cp in (ROOT / "config" / "resume.yaml", Path("config/resume.yaml")):
            if cp.exists():
                try:
                    bank = yaml.safe_load(cp.read_text()) or {}
                    if bank.get("roles"):
                        break
                except Exception:
                    bank = {}
    if not bank.get("roles"):
        master = db.query_one(
            "SELECT parsed_text FROM resumes WHERE user_id=? ORDER BY is_master DESC, id DESC LIMIT 1",
            (user["id"],),
        )
        text = master["parsed_text"] if master and master["parsed_text"] else ""
        lines = [l.strip().lstrip("-•* ") for l in text.splitlines() if len(l.strip()) > 15]
        bullets = [{"id": f"b{i + 1}", "text": line, "skills": [], "theme": "Experience"} for i, line in enumerate(lines[:14])]
        bank = {
            "roles": [{"company": "Professional experience", "title": answers.get("titles", "Engineer"), "bullets": bullets}]
            if bullets else [],
            "skills": {"core": [k.strip() for k in answers.get("keywords", "").split(",") if k.strip()]},
        }
    ident = dict(bank.get("identity") or {})
    ident.update({
        "name": answers.get("full_name") or user.get("display_name") or ident.get("name") or "Candidate",
        "email": answers.get("email") or user.get("email") or "",
        "phone": answers.get("phone") or "",
        "linkedin": answers.get("linkedin_url") or ident.get("linkedin") or "",
        "github": answers.get("github_url") or ident.get("github") or "",
        "location": answers.get("current_location") or ident.get("location") or "",
    })
    bank["identity"] = ident
    bank["name"] = ident["name"]
    return bank


def _delete_user_rows(uid: int) -> None:
    for sql in (
        "DELETE FROM application_events WHERE application_id IN (SELECT id FROM applications WHERE user_id=?)",
        "DELETE FROM applications WHERE user_id=?", "DELETE FROM matches WHERE user_id=?",
        "DELETE FROM resumes WHERE user_id=?", "DELETE FROM profile_answers WHERE user_id=?",
        "DELETE FROM reviews WHERE user_id=?", "DELETE FROM attempts WHERE user_id=?",
        "DELETE FROM drill_attempts WHERE user_id=?", "DELETE FROM pattern_reviews WHERE user_id=?",
        "DELETE FROM leetcode_state WHERE user_id=?", "DELETE FROM gmail_seen WHERE user_id=?",
        "DELETE FROM gmail_state WHERE user_id=?", "DELETE FROM feedback WHERE user_id=?",
        "DELETE FROM users WHERE id=?",
    ):
        try:
            db.execute(sql, (uid,))
        except Exception:
            pass


OAUTH_COOKIE = "athena_oauth"


def _pkce_pair() -> tuple[str, str]:
    import base64

    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _sign_verifier(verifier: str) -> str:
    sig = hmac.new(get_settings().session_secret.encode(), f"pkce:{verifier}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{verifier}.{sig}"


def _read_verifier(cookie: str | None) -> str | None:
    if not cookie or "." not in cookie:
        return None
    verifier, sig = cookie.rsplit(".", 1)
    expect = hmac.new(get_settings().session_secret.encode(), f"pkce:{verifier}".encode(), hashlib.sha256).hexdigest()[:32]
    return verifier if hmac.compare_digest(expect, sig) else None


def _oauth_state(nxt: str) -> str:
    nonce = secrets.token_urlsafe(16)
    payload = f"{nonce}|{int(time.time())}|{nxt}"
    sig = hmac.new(get_settings().session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}|{sig}"


def _verify_oauth_state(state: str) -> str | None:
    try:
        nonce, ts, nxt, sig = state.split("|", 3)
    except ValueError:
        return None
    payload = f"{nonce}|{ts}|{nxt}"
    expect = hmac.new(get_settings().session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig) or time.time() - int(ts) > 900:
        return None
    return safe_next(nxt)


def pattern_of_the_day() -> dict[str, Any] | None:
    pats = content.list_patterns(None)
    if not pats:
        return None
    p = pats[datetime.now(UTC).timetuple().tm_yday % len(pats)]
    probs = content.pattern_problems(p["id"], None)
    canon = next((x for x in probs if x.get("is_canonical")), probs[0] if probs else None)
    return {"pattern": p, "problem": canon}


# ---------------------------------------------------------------- app

def create_app() -> FastAPI:
    app = FastAPI(title="Athena", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 303 and exc.headers and exc.headers.get("Location"):
            return RedirectResponse(exc.headers["Location"], status_code=303)
        if exc.status_code == 404:
            return render(request, "pages/404.html", {"nav": ""}, status_code=404)
        if exc.status_code in (403, 429):
            return render(request, "pages/error.html",
                          {"nav": "", "code": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)
        return render(request, "pages/error.html",
                      {"nav": "", "code": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        import logging

        logging.getLogger("athena").exception("Unhandled error on %s", request.url.path)
        return render(request, "pages/error.html", {"nav": "", "code": 500, "detail": "Something broke on our side."}, status_code=500)

    # ------------------------------------------------------------ public pages

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        user = users.current_user(request)
        ctx: dict[str, Any] = {
            "nav": "home",
            "potd": pattern_of_the_day(),
            "newest": listing.newest(5),
            "patterns": content.list_patterns(user["id"] if user["is_authenticated"] else None)[:6],
        }
        if user["is_authenticated"]:
            uid = user["id"]
            ctx["my"] = {
                "matches": db.query_one("SELECT count(*) c FROM matches WHERE user_id=? AND dismissed_at IS NULL AND fit_score IS NOT NULL", (uid,))["c"],
                "applied": db.query_one("SELECT count(*) c FROM applications WHERE user_id=?", (uid,))["c"],
                "due": db.query_one("SELECT count(*) c FROM reviews WHERE user_id=? AND due_at <= datetime('now')", (uid,))["c"],
                "has_resume": db.query_one("SELECT count(*) c FROM resumes WHERE user_id=? AND is_master=1", (uid,))["c"] > 0,
            }
        return render(request, "pages/today.html", {"user": user, **ctx})

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(request: Request):
        user = users.current_user(request)
        f = listing.parse_filters(request.query_params)
        page = listing.list_jobs(f, user)
        ctx = {
            "user": user, "nav": "jobs", "page": page, "f": f,
            "qs": listing.query_string,
            "demand": listing.skill_demand(page["jobs"]),
            "notice": request.query_params.get("notice", "")[:64],
            "expired_company": request.query_params.get("expired_company", "")[:64],
        }
        if user["is_authenticated"]:
            ctx["pipeline_counts"] = {r["status"]: r["n"] for r in db.query(
                "SELECT status, count(*) n FROM applications WHERE user_id=? GROUP BY status", (user["id"],))}
            ctx["has_resume"] = db.query_one("SELECT count(*) c FROM resumes WHERE user_id=? AND is_master=1", (user["id"],))["c"] > 0
        if request.headers.get("hx-request"):
            return render(request, "partials/job_cards.html", ctx)
        return render(request, "pages/jobs.html", ctx)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise HTTPException(404)
        job = dict(job)
        job["source_label"] = stats.source_label(job.get("source"))
        job["seen_label"] = listing._rel_date(job.get("first_seen_at"))
        match = None
        if user["is_authenticated"]:
            m = db.query_one("SELECT * FROM matches WHERE user_id=? AND job_id=?", (user["id"], job_id))
            if m and m["scored_at"] and m["fit_score"] is not None:
                match = dict(m)
                match["gaps"] = json.loads(m["gaps_json"] or "[]")
                match["strengths"] = json.loads(m["strengths_json"] or "[]")
        return render(request, "pages/job.html", {"user": user, "nav": "jobs", "job": job, "match": match})

    @app.get("/prep", response_class=HTMLResponse)
    def prep_index(request: Request):
        user = users.current_user(request)
        due = 0
        if user["is_authenticated"]:
            due = db.query_one("SELECT count(*) c FROM reviews WHERE user_id=? AND due_at <= datetime('now')", (user["id"],))["c"]
        return render(request, "pages/prep.html", {"user": user, "nav": "prep", "potd": pattern_of_the_day(), "due": due})

    @app.get("/patterns", response_class=HTMLResponse)
    def pattern_index(request: Request):
        user = users.current_user(request)
        pats = content.list_patterns(user["id"] if user["is_authenticated"] else None)
        families: dict[str, list] = {}
        for p in pats:
            families.setdefault(p["family"], []).append(p)
        return render(request, "pages/patterns.html", {"user": user, "nav": "prep", "families": families, "total": len(pats)})

    @app.get("/patterns/{slug}", response_class=HTMLResponse)
    def pattern_detail(request: Request, slug: str):
        user = users.current_user(request)
        pat = content.get_pattern(slug)
        if not pat:
            raise HTTPException(404)
        resources = content.pattern_resources(pat["id"])
        return render(request, "pages/pattern.html", {
            "user": user, "nav": "prep", "p": pat,
            "problems": content.pattern_problems(pat["id"], user["id"] if user["is_authenticated"] else None),
            "resources": resources,
        })

    @app.get("/studio", response_class=HTMLResponse)
    def studio_index(request: Request):
        user = users.current_user(request)
        return render(request, "pages/studio.html", {"user": user, "nav": "studio"})

    @app.get("/linkedin", response_class=HTMLResponse)
    def linkedin_page(request: Request):
        user = users.current_user(request)
        answers = user.get("answers") or {}
        parsed = ""
        user_li = answers.get("linkedin_url", "")
        if user["is_authenticated"]:
            master = db.query_one("SELECT parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
            parsed = master["parsed_text"] if master and master["parsed_text"] else ""
            if not user_li and parsed:
                import re

                m = re.search(r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+", parsed)
                user_li = m.group(0) if m else ""
        lines = [l.strip().lstrip("-•* ") for l in parsed.splitlines() if len(l.strip()) > 25]
        return render(request, "pages/linkedin.html", {
            "user": user, "nav": "studio",
            "user_linkedin": user_li,
            "current_headline": answers.get("titles", ""),
            "current_about": "",
            "current_exp": "\n".join(lines[:3]),
        })

    @app.get("/system", response_class=HTMLResponse)
    def system_page(request: Request):
        user = users.current_user(request)
        runs = [dict(r) for r in db.query("SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT 40")]
        latest: dict[str, dict] = {}
        for r in runs:
            latest.setdefault(r["agent"], r)
        companies = [dict(r) for r in db.query(
            "SELECT name, ats, last_ok_at, last_error, active FROM companies ORDER BY active DESC, name")]
        ok = sum(1 for c in companies if c["active"] and not c["last_error"])
        err = sum(1 for c in companies if c["active"] and c["last_error"])
        ctx = {"user": user, "nav": "system", "runs": runs, "latest": latest,
               "companies_ok": ok, "companies_err": err, "companies": companies}
        if user.get("is_owner"):
            ctx["registered_users"] = [dict(u) for u in db.query(
                "SELECT u.id, u.email, u.display_name, u.last_seen_at, "
                "(SELECT count(*) FROM resumes r WHERE r.user_id=u.id) resume_count, "
                "(SELECT count(*) FROM applications a WHERE a.user_id=u.id) app_count "
                "FROM users u ORDER BY u.last_seen_at DESC")]
            ctx["subscribers"] = db.query_one("SELECT count(*) c FROM subscribers")["c"]
        return render(request, "pages/system.html", ctx)

    for _slug, _tpl in (("about", "about"), ("privacy", "privacy"), ("terms", "terms"), ("changelog", "changelog")):
        def _make(tpl: str):
            def page(request: Request):
                ctx: dict[str, Any] = {"nav": ""}
                if tpl == "changelog":
                    ctx["changelog"] = (ROOT / "CHANGELOG.md").read_text() if (ROOT / "CHANGELOG.md").exists() else ""
                return render(request, f"pages/{tpl}.html", ctx)
            return page
        app.add_api_route(f"/{_slug}", _make(_tpl), methods=["GET"], response_class=HTMLResponse, name=_slug)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "open_jobs": stats.site_stats()["open_jobs"]}

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots_txt():
        return (
            "User-agent: *\nAllow: /\n"
            "Disallow: /profile\nDisallow: /pipeline\nDisallow: /practice\nDisallow: /drill\n"
            "Disallow: /auth/\nDisallow: /api/\nDisallow: /a/\nDisallow: /logout\nDisallow: /jobs/*/tailor\n"
            "Disallow: /resumes/\n\n"
            f"Sitemap: {get_settings().site_url}/sitemap.xml\n"
        )

    @app.get("/sitemap.xml")
    def sitemap_xml():
        site = get_settings().site_url
        urls = [(f"{site}/", "daily", "1.0"), (f"{site}/jobs", "hourly", "0.9"), (f"{site}/prep", "weekly", "0.8"),
                (f"{site}/patterns", "weekly", "0.8"), (f"{site}/studio", "monthly", "0.6"),
                (f"{site}/about", "monthly", "0.5"), (f"{site}/system", "daily", "0.4")]
        urls += [(f"{site}/patterns/{p['slug']}", "monthly", "0.7") for p in db.query("SELECT slug FROM patterns")]
        items = "\n".join(f"  <url><loc>{u}</loc><changefreq>{c}</changefreq><priority>{p}</priority></url>" for u, c, p in urls)
        return Response(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>',
                        media_type="application/xml")

    @app.get("/a/jobs/{job_id}/go")
    def apply_go_route(request: Request, job_id: int):
        from . import jobs as jobs_mod

        job = db.query_one("SELECT j.*, c.careers_url FROM jobs j LEFT JOIN companies c ON c.id=j.company_id WHERE j.id=?", (job_id,))
        if not job:
            raise HTTPException(404)
        job = dict(job)
        apply_url = validate_outbound_url(job.get("apply_url") or "")
        rate_limit(f"go:{client_ip(request)}", 120, 600)
        extra = set()
        if job.get("careers_url"):
            from urllib.parse import urlparse

            h = urlparse(job["careers_url"]).hostname
            if h:
                extra.add(h.lower())
        from urllib.parse import urlparse as _up

        if host_allowed(_up(apply_url).hostname or "", extra):
            try:
                if jobs_mod.is_job_url_closed(apply_url):
                    db.execute("UPDATE jobs SET closed_at=datetime('now') WHERE id=?", (job_id,))
                    stats.invalidate()
                    from urllib.parse import quote_plus

                    return RedirectResponse(f"/jobs?notice=closed&expired_company={quote_plus(job.get('company_name') or '')}", status_code=303)
            except Exception:
                pass
        resp = RedirectResponse(apply_url, status_code=303)
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.post("/a/subscribe")
    async def subscribe(request: Request, email: str = Form(""), source: str = Form("home")):
        await csrf_guard(request)
        rate_limit(f"sub:{client_ip(request)}", 5, 3600)
        e = email.strip().lower()[:120]
        import re

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            return RedirectResponse("/?subscribed=invalid#access", status_code=303)
        try:
            db.execute("INSERT OR IGNORE INTO subscribers (email, source, created_at) VALUES (?, ?, datetime('now'))", (e, source[:32]))
        except Exception:
            pass
        return RedirectResponse("/?subscribed=1#access", status_code=303)

    @app.post("/a/feedback")
    async def feedback(request: Request, message: str = Form(""), page: str = Form("")):
        await csrf_guard(request)
        rate_limit(f"fb:{client_ip(request)}", 10, 3600)
        user = users.current_user(request)
        msg = message.strip()[:2000]
        if msg:
            db.execute("INSERT INTO feedback (user_id, page, message, created_at) VALUES (?, ?, ?, datetime('now'))",
                       (user["id"] if user["is_authenticated"] else None, safe_next(page)[:120], msg))
        return RedirectResponse(safe_next(page) + ("&" if "?" in page else "?") + "notice=thanks", status_code=303)

    # ------------------------------------------------------------ auth

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str = "", next: str = "/"):
        s = get_settings()
        return render(request, "pages/login.html", {
            "nav": "", "error": LOGIN_ERRORS.get(error, ""), "next": safe_next(next),
            "google_configured": bool(s.google_client_id),
        })

    @app.get("/auth/google")
    async def auth_google_redirect(request: Request, next: str = "/"):
        s = get_settings()
        nxt = safe_next(next)
        if not s.google_client_id:
            return RedirectResponse(f"/login?error=oauth_unconfigured&next={nxt}", status_code=303)
        import urllib.parse

        verifier, challenge = _pkce_pair()
        params = {
            "client_id": s.google_client_id,
            "redirect_uri": f"{s.site_url}/auth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "prompt": "select_account",
            "access_type": "online",
            "state": _oauth_state(nxt),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        resp = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params), status_code=303)
        resp.set_cookie(OAUTH_COOKIE, _sign_verifier(verifier), max_age=600, httponly=True,
                        secure=not s.insecure_cookies, samesite="lax", path="/auth/google/callback")
        return resp

    @app.get("/auth/google/callback")
    async def auth_google_callback(request: Request, code: str = "", error: str = "", state: str = ""):
        s = get_settings()
        dest = _verify_oauth_state(state)
        if dest is None:
            return RedirectResponse("/login?error=state_mismatch", status_code=303)
        if error or not code:
            return RedirectResponse("/login?error=oauth_cancelled", status_code=303)
        verifier = _read_verifier(request.cookies.get(OAUTH_COOKIE))
        if not verifier:
            return RedirectResponse("/login?error=state_mismatch", status_code=303)
        if not s.google_client_id or not s.google_client_secret:
            return RedirectResponse("/login?error=oauth_unconfigured", status_code=303)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                tok = await client.post("https://oauth2.googleapis.com/token", data={
                    "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                    "redirect_uri": f"{s.site_url}/auth/google/callback", "grant_type": "authorization_code",
                    "code_verifier": verifier})
                if tok.status_code != 200:
                    return RedirectResponse("/login?error=oauth_failed", status_code=303)
                info_r = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
                                          headers={"Authorization": f"Bearer {tok.json().get('access_token')}"})
                if info_r.status_code != 200:
                    return RedirectResponse("/login?error=oauth_failed", status_code=303)
                info = info_r.json()
        except Exception:
            return RedirectResponse("/login?error=oauth_failed", status_code=303)
        if not (info.get("verified_email") or info.get("email_verified")):
            return RedirectResponse("/login?error=email_unverified", status_code=303)
        resp = _finish_login(info.get("email", ""), info.get("name") or "", dest)
        resp.delete_cookie(OAUTH_COOKIE, path="/auth/google/callback")
        return resp

    @app.post("/auth/google/verify")
    async def auth_google_verify_token(request: Request):
        """Google Identity Services ID-token flow (one-tap button)."""
        form = await request.form()
        credential = (form.get("credential") or "").strip()
        dest = safe_next(form.get("next") or "/")
        if not credential:
            return RedirectResponse("/login?error=oauth_failed", status_code=303)
        s = get_settings()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credential})
            if res.status_code != 200:
                return RedirectResponse("/login?error=oauth_failed", status_code=303)
            payload = res.json()
        except Exception:
            return RedirectResponse("/login?error=oauth_failed", status_code=303)
        if s.google_client_id and payload.get("aud") != s.google_client_id:
            return RedirectResponse("/login?error=oauth_failed", status_code=303)
        if payload.get("email_verified") not in ("true", True):
            return RedirectResponse("/login?error=email_unverified", status_code=303)
        return _finish_login(payload.get("email", ""), payload.get("name") or "", dest)

    def _finish_login(email: str, name: str, dest: str) -> Response:
        s = get_settings()
        email = email.strip().lower()
        if not email:
            return RedirectResponse("/login?error=oauth_failed", status_code=303)
        allowed = s.allowlist
        owner = (s.owner_email or "").lower()
        if allowed and email not in allowed and email != owner:
            return RedirectResponse("/login?error=not_allowed", status_code=303)
        uid = users.ensure_user(email, display_name=name or None)
        resp = RedirectResponse(dest, status_code=303)
        users.set_session_cookie(resp, uid)
        return resp

    @app.get("/auth/demo-sandbox")
    def demo_sandbox(request: Request, next: str = "/jobs"):
        rate_limit(f"sandbox:{client_ip(request)}", 5, 3600)
        uid = users.create_sandbox_user()
        resp = RedirectResponse(safe_next(next, "/jobs"), status_code=303)
        users.set_session_cookie(resp, uid)
        return resp

    @app.get("/logout")
    def do_logout(request: Request):
        user = users.current_user(request)
        resp = RedirectResponse("/", status_code=303)
        users.clear_session_cookie(resp)
        if user.get("is_sandbox"):
            _delete_user_rows(user["id"])
        return resp

    # ------------------------------------------------------------ signed-in pages

    @app.get("/practice", response_class=HTMLResponse)
    def practice_page(request: Request, user: dict = Depends(users.require_user)):
        return render(request, "pages/practice.html", {"user": user, "nav": "prep", "q": practice.build_queue(user["id"])})

    @app.post("/a/attempt")
    async def record_attempt(request: Request, problem_id: int = Form(...), outcome: str = Form(...),
                             confidence: int = Form(3), user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        practice.record_attempt(user["id"], problem_id, outcome, confidence)
        return RedirectResponse("/practice", status_code=303)

    @app.get("/drill", response_class=HTMLResponse)
    def drill_page(request: Request, user: dict = Depends(users.require_user)):
        return render(request, "pages/drill.html", {"user": user, "nav": "prep", "item": drill.next_drill(user["id"]),
                                                    "choices": drill.choices(), "result": None})

    @app.post("/drill", response_class=HTMLResponse)
    async def drill_answer(request: Request, problem_id: int = Form(...), chosen_pattern_id: int = Form(...),
                           seconds: int = Form(0), user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        result = drill.answer(user["id"], problem_id, chosen_pattern_id, seconds or None)
        return render(request, "pages/drill.html", {"user": user, "nav": "prep", "item": drill.next_drill(user["id"]),
                                                    "choices": drill.choices(), "result": result})

    @app.get("/pipeline", response_class=HTMLResponse)
    def pipeline_page(request: Request, user: dict = Depends(users.require_user)):
        rows = db.query("SELECT a.*, j.company_name, j.title FROM applications a JOIN jobs j ON j.id=a.job_id "
                        "WHERE a.user_id=? ORDER BY a.last_event_at DESC NULLS LAST", (user["id"],))
        cols: dict[str, list] = {}
        for r in rows:
            cols.setdefault(r["status"], []).append(dict(r))
        return render(request, "pages/pipeline.html", {"user": user, "nav": "jobs", "cols": cols})

    @app.get("/jobs/{job_id}/tailor", response_class=HTMLResponse)
    def tailor_page(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        from . import tailor

        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise HTTPException(404)
        job = dict(job)
        bank = load_bank_for(user)
        if not bank.get("roles"):
            return render(request, "pages/tailor.html", {"user": user, "nav": "studio", "job": job, "data": None,
                                                         "bank": bank, "tailored_resume": None, "needs_resume": True})
        tailored = db.query_one("SELECT * FROM resumes WHERE user_id=? AND label LIKE ? ORDER BY id DESC LIMIT 1",
                                (user["id"], f"%Job {job_id}%"))
        chain = None
        try:
            chain = llm.Chain()
        except Exception:
            pass
        data = tailor.suggest_tailoring(bank, job.get("description_md") or "", chain=chain)
        return render(request, "pages/tailor.html", {
            "user": user, "nav": "studio", "job": job, "data": data, "bank": bank,
            "tailored_resume": dict(tailored) if tailored else None, "needs_resume": False,
            "saved": request.query_params.get("saved") == "1",
        })

    @app.post("/jobs/{job_id}/tailor/approve")
    async def approve_tailor(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        from . import analyst, tailor

        await csrf_guard(request)
        rate_limit(f"tailor:{user['id']}", 20, 600)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise HTTPException(404)
        job = dict(job)
        bank = load_bank_for(user)
        form = await request.form()
        chosen: dict[str, list[dict]] = {}
        for role in bank.get("roles", []):
            picked = []
            for b in role.get("bullets", []):
                val = form.get(f"bullet_{b['id']}")
                if val:
                    nb = dict(b)
                    nb["text"] = str(val).strip()[:400]
                    picked.append(nb)
            if picked:
                chosen[role["company"]] = picked
        raw_skills = form.get("custom_skills")
        skills = [s.strip() for s in str(raw_skills).split(",") if s.strip()] if raw_skills else tailor.reorder_skills(bank, job.get("description_md") or "")
        out_dir = Path("/tmp/resumes") if os.getenv("VERCEL") else (ROOT / "var" / "resumes")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_pdf = out_dir / f"tailored_{user['id']}_{job_id}.pdf"
        tailor.render_pdf(bank, chosen or tailor.select_bullets(bank, job.get("description_md") or ""), skills, out_pdf)
        # §8.4.3 regression gate: reject a PDF that lost a contact field present in the bank.
        try:
            report = analyst.analyse_pdf(out_pdf)
            ident = bank.get("identity") or {}
            for key in ("email", "phone"):
                if ident.get(key) and not (report.contact_fields or {}).get(key):
                    out_pdf.unlink(missing_ok=True)
                    return RedirectResponse(f"/jobs/{job_id}/tailor?error=parse_gate", status_code=303)
        except Exception:
            pass
        label = f"Tailored: {job['title']} @ {job['company_name']} (Job {job_id})"
        with db.transaction() as conn:
            conn.execute("INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) VALUES (?, ?, ?, ?, 0, datetime('now'))",
                         (user["id"], label, str(out_pdf), json.dumps(chosen)[:4000]))
            res_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            conn.execute("INSERT INTO applications (user_id, job_id, resume_id, status, status_source, last_event_at) "
                         "VALUES (?, ?, ?, 'prepared', 'user', datetime('now')) ON CONFLICT(user_id, job_id) DO UPDATE SET "
                         "resume_id=excluded.resume_id, last_event_at=datetime('now')", (user["id"], job_id, res_id))
        return RedirectResponse(f"/jobs/{job_id}/tailor?saved=1", status_code=303)

    @app.get("/resumes/{resume_id}/download")
    def download_resume(resume_id: int, user: dict = Depends(users.require_user)):
        row = db.query_one("SELECT * FROM resumes WHERE id=? AND user_id=?", (resume_id, user["id"]))
        if not row or not row["file_path"] or not row["file_path"].endswith(".pdf"):
            raise HTTPException(404)
        p = Path(row["file_path"])
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(str(p), media_type="application/pdf", filename=p.name)

    @app.post("/a/jobs/{job_id}/discover-bullet")
    async def discover_bullet(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        from . import tailor

        await csrf_guard(request)
        rate_limit(f"llm:{user['id']}", 10, 600)
        body = await request.json()
        chain = None
        try:
            chain = llm.Chain()
        except Exception:
            pass
        result = tailor.synthesize_discovered_bullet(
            (body.get("skill_gap") or "Core Technology")[:120], (body.get("user_notes") or "")[:2000],
            (body.get("experience_type") or "direct")[:20], chain)
        return JSONResponse({"ok": True, "data": result})

    @app.post("/a/jobs/{job_id}/save-bullet-to-bank")
    async def save_bullet_to_bank(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        body = await request.json()
        bullet = (body.get("bullet") or "").strip()[:400]
        skill = (body.get("skill") or "Technical Skills").strip()[:80]
        if not bullet:
            return JSONResponse({"ok": False, "error": "Bullet text is required"}, status_code=400)
        master = db.query_one("SELECT id, parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
        entry = f"\n- {bullet} (Skills: {skill})"
        if master:
            existing = master["parsed_text"] or ""
            marker = "DISCOVERED EXPERIENCES & BULLETS:"
            updated = existing + ("\n\n" + marker if marker not in existing else "") + entry
            db.execute("UPDATE resumes SET parsed_text=? WHERE id=?", (updated, master["id"]))
        else:
            db.execute("INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) VALUES (?, 'master_bullet_bank', 'internal/bank', ?, 1, datetime('now'))",
                       (user["id"], f"DISCOVERED EXPERIENCES & BULLETS:{entry}"))
        return JSONResponse({"ok": True, "message": f"Saved to your bullet bank under {skill}."})

    @app.post("/a/jobs/{job_id}/linkedin-seo")
    async def job_linkedin_seo_endpoint(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        from . import linkedin_optimizer

        await csrf_guard(request)
        rate_limit(f"llm:{user['id']}", 10, 600)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            return JSONResponse({"ok": False, "error": "Job not found"}, status_code=404)
        chain = None
        try:
            chain = llm.Chain.from_env()
        except Exception:
            pass
        master = db.query_one("SELECT parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
        res = linkedin_optimizer.generate_job_targeted_linkedin_seo(
            job_title=job["title"], company=job["company_name"], jd_text=job["description_md"] or "",
            resume_text=(master["parsed_text"] if master and master["parsed_text"] else ""), chain=chain)
        return JSONResponse({"ok": True, "data": res})

    @app.post("/a/linkedin/optimize")
    async def optimize_linkedin_endpoint(request: Request, user: dict = Depends(users.require_user)):
        from . import linkedin_optimizer

        await csrf_guard(request)
        rate_limit(f"llm:{user['id']}", 10, 600)
        body = await request.json()
        chain = None
        try:
            chain = llm.Chain.from_env()
        except Exception:
            pass
        result = linkedin_optimizer.audit_and_optimize_profile(
            headline=(body.get("headline") or "")[:300], about=(body.get("about") or "")[:4000],
            experiences=(body.get("experiences") or "")[:4000],
            target_audience=(body.get("target_audience") or "Engineering leaders & technical recruiters")[:120],
            goal=(body.get("goal") or "job seeker")[:40], linkedin_url=(body.get("linkedin_url") or "")[:200],
            mode=(body.get("mode") or "standard")[:10], chain=chain)
        return JSONResponse({"ok": True, "data": result, "llm": chain is not None})

    @app.post("/a/jobs/{job_id}/mark-applied")
    async def mark_applied_route(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        db.execute("INSERT INTO applications (user_id, job_id, status, status_source, applied_at, last_event_at) "
                   "VALUES (?, ?, 'submitted', 'user', datetime('now'), datetime('now')) ON CONFLICT(user_id, job_id) DO UPDATE SET "
                   "status='submitted', status_source='user', applied_at=coalesce(applications.applied_at, datetime('now')), last_event_at=datetime('now')",
                   (user["id"], job_id))
        app_row = db.query_one("SELECT id FROM applications WHERE user_id=? AND job_id=?", (user["id"], job_id))
        if app_row:
            db.execute("INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                       "VALUES (?, 'submitted', datetime('now'), 'user', 'Marked as applied', datetime('now'))", (app_row["id"],))
        db.execute("UPDATE matches SET dismissed_at=datetime('now') WHERE user_id=? AND job_id=?", (user["id"], job_id))
        if request.headers.get("hx-request"):
            return HTMLResponse('<div class="notice ok">Moved to your pipeline.</div>')
        return RedirectResponse("/pipeline", status_code=303)

    @app.post("/a/applications/{app_id}/status")
    async def update_application_status_route(request: Request, app_id: int, status: str = Form(""),
                                              user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        valid = {"prepared", "submitted", "acknowledged", "screening", "assessment", "interview", "offer", "rejected", "withdrawn", "ghosted"}
        if status in valid:
            owned = db.query_one("SELECT id FROM applications WHERE id=? AND user_id=?", (app_id, user["id"]))
            if owned:
                db.execute("UPDATE applications SET status=?, status_source='user', last_event_at=datetime('now') WHERE id=?", (status, app_id))
                db.execute("INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                           "VALUES (?, ?, datetime('now'), 'user', 'Status changed in pipeline', datetime('now'))", (app_id, status))
        return RedirectResponse("/pipeline", status_code=303)

    @app.post("/a/match/{match_id}/dismiss")
    async def dismiss_match(request: Request, match_id: int, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        db.execute("UPDATE matches SET dismissed_at=datetime('now') WHERE id=? AND user_id=?", (match_id, user["id"]))
        if request.headers.get("hx-request"):
            return HTMLResponse("")
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/a/jobs/{job_id}/dismiss")
    async def dismiss_job(request: Request, job_id: int, user: dict = Depends(users.require_user)):
        """Dismiss by job even when no match row exists yet."""
        await csrf_guard(request)
        db.execute("INSERT INTO matches (user_id, job_id, bm25_score, dismissed_at) VALUES (?, ?, 0, datetime('now')) "
                   "ON CONFLICT(user_id, job_id) DO UPDATE SET dismissed_at=datetime('now')", (user["id"], job_id))
        if request.headers.get("hx-request"):
            return HTMLResponse("")
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/a/digest/send")
    async def send_digest_route(request: Request, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        rate_limit(f"digest:{user['id']}", 3, 3600)
        if user.get("is_sandbox"):
            return RedirectResponse("/jobs?notice=sandbox_no_email", status_code=303)
        try:
            from .agents.digest import send_digest_email

            send_digest_email(user["id"])
            return RedirectResponse("/jobs?notice=digest_sent", status_code=303)
        except Exception:
            return RedirectResponse("/jobs?notice=digest_failed", status_code=303)

    @app.post("/a/matcher/run")
    async def run_matcher_on_demand(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        rate_limit(f"match:{user['id']}", 4, 600)
        from .agents.matcher import run_matcher_for_user

        run_matcher_for_user(user, force_bm25=True)
        if not user.get("is_sandbox"):
            background_tasks.add_task(run_matcher_for_user, user, False, False, 4)
        return RedirectResponse("/jobs?notice=matched", status_code=303)

    @app.post("/a/scout/run")
    async def run_scout_on_demand(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(users.require_owner)):
        await csrf_guard(request)
        from .agents.scout import run_scout

        background_tasks.add_task(run_scout, False, None, 15)
        return RedirectResponse("/system?notice=scout_started", status_code=303)

    # ------------------------------------------------------------ profile

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, user: dict = Depends(users.require_user)):
        master = db.query_one("SELECT * FROM resumes WHERE user_id=? ORDER BY is_master DESC, id DESC LIMIT 1", (user["id"],))
        words = len((master["parsed_text"] or "").split()) if master else 0
        tailored = [dict(r) for r in db.query(
            "SELECT id, label, created_at FROM resumes WHERE user_id=? AND is_master=0 AND file_path LIKE '%.pdf' ORDER BY id DESC LIMIT 10", (user["id"],))]
        return render(request, "pages/profile.html", {
            "user": user, "nav": "", "answers": user.get("answers") or {},
            "master_resume": dict(master) if master else None, "resume_words": words, "tailored": tailored,
            "saved": request.query_params.get("saved") == "1",
            "error": request.query_params.get("error", "")[:120],
        })

    @app.post("/profile/targets")
    async def save_targets(request: Request, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        form = await request.form()
        uid = user["id"]
        display_name = (form.get("display_name") or "").strip()[:80]
        leetcode_user = (form.get("leetcode_user") or "").strip()[:60]
        if display_name or leetcode_user:
            db.execute("UPDATE users SET display_name=coalesce(nullif(?, ''), display_name), leetcode_user=coalesce(nullif(?, ''), leetcode_user) WHERE id=?",
                       (display_name, leetcode_user, uid))
        keys = ("titles", "avoid_titles", "keywords", "locations", "min_ctc", "experience_years", "track",
                "phone", "linkedin_url", "github_url", "current_location", "notice_period_days", "work_authorization", "full_name")
        with db.transaction() as conn:
            for k in keys:
                v = (form.get(k) or "").strip()[:300]
                if k == "track" and v not in ("tech", "business", "dual_track"):
                    v = "tech"
                conn.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
                             (uid, k, v))
        return RedirectResponse("/profile?saved=1", status_code=303)

    @app.post("/profile/resume")
    async def upload_resume(request: Request, resume_file: UploadFile = File(None), resume_text: str = Form(""),
                            user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        rate_limit(f"upload:{user['id']}", 10, 3600)
        uid = user["id"]
        text = (resume_text or "").strip()[:60000]
        label = "Master Resume"
        if resume_file and getattr(resume_file, "filename", None):
            fname = Path(resume_file.filename).name[:120]
            blob = await resume_file.read()
            if len(blob) > 5 * 1024 * 1024:
                return RedirectResponse("/profile?error=File+too+large+(5+MB+max)", status_code=303)
            if fname.lower().endswith(".pdf"):
                try:
                    import io

                    from pdfminer.high_level import extract_text as pdf_extract

                    pdf_txt = pdf_extract(io.BytesIO(blob)).strip()
                    if pdf_txt:
                        text = pdf_txt[:60000]
                        label = fname
                except Exception:
                    pass
            else:
                text = blob.decode("utf-8", errors="ignore").strip()[:60000] or text
                label = fname
        if not text:
            return RedirectResponse("/profile?error=Paste+your+resume+text+or+upload+a+PDF", status_code=303)
        with db.transaction() as conn:
            conn.execute("UPDATE resumes SET is_master=0 WHERE user_id=?", (uid,))
            conn.execute("INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) VALUES (?, ?, ?, ?, 1, datetime('now'))",
                         (uid, label, f"upload/{label}", text))
        try:
            from .agents.matcher import run_matcher_for_user

            run_matcher_for_user(users.load_user(uid) or user, force_bm25=True)
        except Exception:
            pass
        return RedirectResponse("/jobs?notice=matched", status_code=303)

    @app.post("/profile/delete")
    async def self_delete_profile(request: Request, user: dict = Depends(users.require_user)):
        await csrf_guard(request)
        _delete_user_rows(user["id"])
        resp = RedirectResponse("/?deleted=1", status_code=303)
        users.clear_session_cookie(resp)
        return resp

    @app.post("/system/users/{uid}/delete")
    async def admin_delete_user(request: Request, uid: int, user: dict = Depends(users.require_owner)):
        await csrf_guard(request)
        if uid == user["id"]:
            return RedirectResponse("/system?notice=cannot_delete_self", status_code=303)
        _delete_user_rows(uid)
        return RedirectResponse("/system?notice=user_deleted", status_code=303)

    # ------------------------------------------------------------ cron

    @app.api_route("/api/cron/sync-and-match", methods=["GET", "POST"])
    @app.api_route("/api/cron/daily", methods=["GET", "POST"])
    def cron_sync_and_match(request: Request):
        secret = os.getenv("CRON_SECRET", "").strip()
        auth = request.headers.get("authorization", "").strip()
        if not secret or not hmac.compare_digest(auth, f"Bearer {secret}"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from . import email
        from .agents.digest import get_consolidated_digest_matches
        from .agents.matcher import run_matcher_for_user

        do_scout = request.query_params.get("scout", "1") != "0"
        do_match = request.query_params.get("match", "1") != "0"
        do_email = request.query_params.get("email", "1") != "0"
        out: dict[str, Any] = {"ok": True, "scout": None, "results": []}
        if do_scout:
            try:
                from .agents.scout import run_scout

                out["scout"] = run_scout(dry_run=False, limit_companies=5)
            except Exception as e:
                out["scout"] = {"error": str(e)[:200]}
            stats.invalidate()
        real_users = [dict(u) for u in db.query("SELECT * FROM users ORDER BY id") if not u["email"].endswith("@demo.invalid")]
        for u in real_users:
            res: dict[str, Any] = {"user": u["id"]}
            if do_match:
                try:
                    res["matched"] = run_matcher_for_user(users.load_user(u["id"]) or u, force_bm25=False, max_batches=1)
                except Exception as e:
                    res["matcher_error"] = str(e)[:200]
            if do_email:
                try:
                    top = get_consolidated_digest_matches(u["id"], total_limit=25)
                    if top:
                        html = email.render_digest_html({"top_matches": top, "pipeline_moves": [], "problems_practiced": 0, "source_failures": []}, u["email"])
                        sent = email.send_email(to_email=u["email"], subject=f"Athena digest: {len(top)} roles for you today", html_body=html)
                        if sent:
                            now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                            for m in top:
                                if "job_id" in m:
                                    db.execute("UPDATE matches SET digest_sent_at=? WHERE user_id=? AND job_id=?", (now_iso, u["id"], m["job_id"]))
                        res["digest"] = sent
                except Exception as e:
                    res["digest_error"] = str(e)[:200]
            out["results"].append(res)
        # purge stale sandbox users
        for u in db.query("SELECT id FROM users WHERE email LIKE '%@demo.invalid' AND last_seen_at < datetime('now','-2 days')"):
            _delete_user_rows(u["id"])
        return JSONResponse(out)

    return app


app = create_app()


def cli() -> None:
    ap = argparse.ArgumentParser(prog="trackboard")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("migrate", help="apply pending database migrations")
    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    if args.cmd == "migrate":
        print(f"database: {get_settings().db_path}")
        db.migrate()
        return
    import uvicorn

    db.migrate(verbose=False)
    uvicorn.run("trackboard.main:app", host=args.host, port=args.port, reload=True, log_level="warning")
