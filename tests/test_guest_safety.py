"""No personal data and no working mutations for anonymous visitors (Phase 0.9 / Addendum A)."""
from __future__ import annotations

import re

import pytest

from trackboard import db
from tests.helpers import guest, signed_in

PUBLIC = ["/", "/jobs", "/jobs?region=all&track=all", "/prep", "/patterns", "/patterns/sliding-window",
          "/studio", "/linkedin", "/login", "/system", "/about", "/privacy", "/terms", "/changelog", "/healthz"]

PII_PATTERNS = [
    re.compile(r"\+91[\d\- ]{8,}"),
    re.compile(r"\b[6-9]\d{9}\b"),
    re.compile(r"[\w.+-]+@(gmail|yahoo|outlook|hotmail)\.", re.I),
    re.compile(r"linkedin\.com/in/(?!shourjya-hazra-683128200)[\w-]+", re.I),
]
FORBIDDEN_STRINGS = [
    "Email: None", "Guest Visitor", "Indian Citizen", "Trackboard", "How Trackboard Works", "config/channels.yaml",
    "role: concept", "Direct 80%", "Trans 85%", "Adj 82%", "Impact 75%", "BM25: 0.0", "100% 200 OK", "0 DEAD LINKS",
    "0.08s LATENCY", "TWIN ACTIVE", "ZERO DATA LEAKAGE", "AI RECRUITER SIMULATION", "Rank #1", "1-Click Autofill",
    "Universal Applier", "60-Second Auto-Apply", "candidate persona", "MAP v2.4", "Copy Safari Autofill Script",
    "Send Digest to Email Now", "Target Roles Configured", "Active Matches", "Scrapes 460+",
]
MUTATING = [
    ("post", "/a/jobs/1/mark-applied"), ("post", "/a/jobs/1/dismiss"), ("post", "/a/match/1/dismiss"),
    ("post", "/a/digest/send"), ("post", "/a/matcher/run"), ("post", "/a/scout/run"), ("post", "/a/linkedin/optimize"),
    ("post", "/a/jobs/1/discover-bullet"), ("post", "/a/jobs/1/save-bullet-to-bank"), ("post", "/a/jobs/1/linkedin-seo"),
    ("post", "/profile/targets"), ("post", "/profile/resume"), ("post", "/profile/delete"), ("post", "/a/attempt"),
    ("post", "/drill"), ("post", "/a/applications/1/status"), ("post", "/jobs/1/tailor/approve"),
    ("get", "/profile"), ("get", "/pipeline"), ("get", "/practice"), ("get", "/drill"), ("get", "/jobs/1/tailor"),
    ("get", "/resumes/1/download"),
]


@pytest.fixture(autouse=True)
def _seed():
    db.migrate(verbose=False)
    # A pattern so /patterns/sliding-window resolves even on an empty DB
    if not db.query_one("SELECT 1 FROM patterns WHERE slug='sliding-window'"):
        db.execute("INSERT INTO patterns (slug, name, family, summary, cues_json, sort_order) VALUES "
                   "('sliding-window','Sliding window','arrays','A contiguous range.','[]',2)")


@pytest.mark.parametrize("path", PUBLIC)
def test_public_route_has_no_pii_and_no_placeholders(path):
    c = guest()
    r = c.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    body = r.text
    for pat in PII_PATTERNS:
        assert not pat.search(body), f"{path} leaked PII matching {pat.pattern}: {pat.search(body).group(0)}"
    for s in FORBIDDEN_STRINGS:
        assert s not in body, f"{path} still contains {s!r}"


@pytest.mark.parametrize("method,path", MUTATING)
def test_mutations_redirect_guests_to_login(method, path):
    c = guest()
    r = c.post(path, data={"x": "1"}) if method == "post" else c.get(path)
    assert r.status_code == 303, f"{method} {path} -> {r.status_code}"
    assert r.headers["location"].startswith("/login?error=auth_required")


def test_signed_in_mutation_requires_csrf():
    c = signed_in()
    r = c.post("/a/jobs/1/dismiss", data={})
    assert r.status_code == 403
    r2 = c.post("/a/jobs/1/dismiss", data={"csrf_token": "wrong"})
    assert r2.status_code == 403


def test_cron_requires_bearer_secret(monkeypatch):
    c = guest()
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert c.get("/api/cron/sync-and-match").status_code == 401
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert c.get("/api/cron/sync-and-match").status_code == 401
    assert c.get("/api/cron/sync-and-match?token=s3cret").status_code == 401  # query param no longer accepted


def test_go_route_blocks_unsafe_targets():
    from trackboard import jobs

    for i, bad in enumerate(("javascript:alert(1)", "http://169.254.169.254/latest/meta-data", "https://127.0.0.1/x", "ftp://x")):
        title = f"Unsafe Engineer {i}"
        jobs.upsert({"company_name": "BadCo", "title": title, "description_md": "", "apply_url": bad, "source": "greenhouse", "location": "Nowhere"})
        db.execute("UPDATE jobs SET apply_url=? WHERE company_name='BadCo' AND title=?", (bad, title))
        row = db.query_one("SELECT id FROM jobs WHERE company_name='BadCo' AND title=?", (title,))
        r = guest().get(f"/a/jobs/{row['id']}/go")
        assert r.status_code == 400, bad


def test_removed_dangerous_routes_are_gone():
    c = guest()
    for path in ("/a/agent/run", "/a/agent/stop", "/a/digest/send-test", "/auth/switch/shourjya"):
        assert c.post(path).status_code in (404, 405)
        assert c.get(path).status_code in (404, 405)


def test_no_public_pdf_and_no_applier():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/trackboard/static/resumes").exists()
    assert not (root / "src/trackboard/agents/applier.py").exists()


def test_seed_database_has_no_users():
    import sqlite3
    from pathlib import Path

    seed = Path(__file__).resolve().parents[1] / "data" / "seed_data.db"
    if not seed.exists():
        pytest.skip("no seed db")
    con = sqlite3.connect(seed)
    for t in ("users", "profile_answers", "resumes", "applications", "matches"):
        assert con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0, t
    con.close()
