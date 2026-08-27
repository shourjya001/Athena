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
