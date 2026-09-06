"""Job normalisation, deduplication, and closure (BUILD_SPEC §8.1)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from . import db

SOURCE_RANK = {"greenhouse": 4, "lever": 4, "ashby": 4, "recruitee": 4, "smartrecruiters": 4,
               "adzuna": 3, "alert:linkedin": 2, "alert:naukri": 2, "alert:indeed": 2,
               "alert:instahyre": 2, "remotive": 2, "arbeitnow": 2}

TITLE_ALLOW = re.compile(
    r"engineer|developer|\bsde\b|\bswe\b|architect|\bsre\b|devops|backend|frontend|"
    r"full[- ]stack|platform|infrastructure|mobile|android|\bios\b|data|machine learning|"
    r"\bml\b|\bqa\b|security|programmer|"
    # AI-era titles (owner targets: SDE, AI Backend, AI Engineer, FDE)
    r"\bai\b|\bllm\b|\bgen ?ai\b|applied ai|forward[- ]deployed|\bfde\b|"
    r"member of technical staff|\bmts\b|solutions engineer|deployment engineer|"
    r"\bmlops\b|inference|\brag\b|agent", re.I)
TITLE_DENY = re.compile(
    r"sales|marketing|\bhr\b|recruit|finance|legal|account manager|customer success|"
    r"business development|\bbdm\b|content writ", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()


def fingerprint(company: str, title: str, location: str | None) -> str:
    city = _norm((location or "").split(",")[0])
    raw = f"{_norm(company)}|{_norm(title)}|{city}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_technical_ic(title: str) -> bool:
    return bool(TITLE_ALLOW.search(title)) and not TITLE_DENY.search(title)


def upsert(job: dict) -> str:
    """Insert or merge one normalised posting. Returns 'new'|'seen'|'upgraded'|'filtered'."""
    if not job.get("title") or not job.get("apply_url"):
        return "filtered"
    if not is_technical_ic(job["title"]):
        return "filtered"
    fp = fingerprint(job.get("company_name", ""), job["title"], job.get("location"))
    rank = SOURCE_RANK.get(job["source"], 1)
    with db.transaction() as conn:
        row = conn.execute("SELECT id, source FROM jobs WHERE fingerprint=?", (fp,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO jobs (fingerprint, company_id, company_name, title, location, remote, "
                "employment_type, description_md, salary_min, salary_max, salary_currency, "
                "apply_url, source, source_job_id, posted_at, posted_at_approx, first_seen_at, last_seen_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fp, job.get("company_id"), job.get("company_name", ""), job["title"],
                 job.get("location"), job.get("remote", 0), job.get("employment_type"),
                 job.get("description_md"), job.get("salary_min"), job.get("salary_max"),
                 job.get("salary_currency"), job["apply_url"], job["source"],
                 job.get("source_job_id"), job.get("posted_at"),
                 job.get("posted_at_approx", 0), _now(), _now()))
            return "new"
        existing_rank = SOURCE_RANK.get(row["source"], 1)
        if rank > existing_rank:
            conn.execute(
                "UPDATE jobs SET apply_url=?, source=?, source_job_id=?, "
                "description_md=COALESCE(NULLIF(?, ''), description_md), "
                "last_seen_at=?, strikes=0, closed_at=NULL WHERE id=?",
                (job["apply_url"], job["source"], job.get("source_job_id"),
                 job.get("description_md") or "", _now(), row["id"]))
            return "upgraded"
        conn.execute("UPDATE jobs SET last_seen_at=?, strikes=0, closed_at=NULL WHERE id=?",
                     (_now(), row["id"]))
        return "seen"


def apply_strikes(source: str, seen_fingerprints: set[str],
                  company_id: int | None = None) -> int:
    """After a SUCCESSFUL sync: unseen open jobs get a strike; two closes.
    Board sources MUST pass company_id — striking at source level would let
    one company's sync close every other company's jobs on the same ATS.
    Never call after a failed sync (§8.1.4)."""
    closed = 0
    with db.transaction() as conn:
        if company_id is not None:
            rows = conn.execute(
                "SELECT id, fingerprint, strikes FROM jobs "
                "WHERE source=? AND company_id=? AND closed_at IS NULL",
                (source, company_id)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, fingerprint, strikes FROM jobs WHERE source=? AND closed_at IS NULL",
                (source,)).fetchall()
        for r in rows:
            if r["fingerprint"] in seen_fingerprints:
                continue
            strikes = r["strikes"] + 1
            if strikes >= 2:
                conn.execute("UPDATE jobs SET strikes=?, closed_at=? WHERE id=?",
                             (strikes, _now(), r["id"]))
                closed += 1
            else:
                conn.execute("UPDATE jobs SET strikes=? WHERE id=?", (strikes, r["id"]))
    return closed


def is_job_url_closed(url: str) -> bool:
    """Verify whether a job apply URL is live or expired."""
    if not url or not url.startswith("http"):
        return False
    try:
        import httpx
        r = httpx.get(
            url,
            follow_redirects=True,
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        if r.status_code in (404, 410):
            return True
        final_url = str(r.url)
        if "error=true" in final_url:
            return True
        if "/jobs/" in url and "/jobs/" not in final_url and not final_url.endswith("/apply"):
            return True
        closure_phrases = [
            "no longer open", "no longer accepting applications", "job is closed",
            "position has been filled", "opening is closed", "job not found", "job expired",
            "this job has expired", "job is no longer available"
        ]
        text_lower = r.text.lower()
        if any(p in text_lower for p in closure_phrases):
            return True
        return False
    except Exception:
        return False


def verify_and_close_job(job_id: int) -> bool:
    """Check a single job; if closed, mark closed_at and return True."""
    row = db.query_one("SELECT id, apply_url, closed_at FROM jobs WHERE id=?", (job_id,))
    if not row or row["closed_at"] is not None:
        return True
    if is_job_url_closed(row["apply_url"]):
        db.execute("UPDATE jobs SET closed_at=datetime('now') WHERE id=?", (job_id,))
        return True
    return False


def clean_expired_matched_jobs(user_id: int | None = None, limit: int = 30) -> int:
    """Background task to continuously verify active matches and auto-close dead jobs."""
    if user_id:
        rows = db.query(
            "SELECT DISTINCT j.id, j.apply_url FROM jobs j "
            "JOIN matches m ON m.job_id=j.id "
            "WHERE j.closed_at IS NULL AND m.user_id=? AND m.dismissed_at IS NULL "
            "ORDER BY COALESCE(m.fit_score, m.bm25_score) DESC LIMIT ?",
            (user_id, limit)
        )
    else:
        rows = db.query(
            "SELECT DISTINCT j.id, j.apply_url FROM jobs j "
            "JOIN matches m ON m.job_id=j.id "
            "WHERE j.closed_at IS NULL AND m.dismissed_at IS NULL "
            "ORDER BY j.id DESC LIMIT ?",
            (limit,)
        )
    closed = 0
    for r in rows:
        if is_job_url_closed(r["apply_url"]):
            db.execute("UPDATE jobs SET closed_at=datetime('now') WHERE id=?", (r["id"],))
            closed += 1
    return closed
