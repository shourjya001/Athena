"""Single source of truth for every number rendered on public pages (Phase 1.1).
Nothing in a template may hard-code a count; it reads from `site_stats()`."""
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from . import db

SOURCE_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "oracle_cx": "Oracle",
    "smartrecruiters": "SmartRecruiters",
    "recruitee": "Recruitee",
    "workable": "Workable",
    "darwinbox": "Careers site",
    "remotive": "Remotive",
}

INDIA_TERMS = (
    "india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune", "gurgaon", "gurugram",
    "noida", "chennai", "delhi", "kolkata", "ahmedabad", "jaipur", "chandigarh", "kochi",
)


def _q1(sql: str, params=()) -> int:
    row = db.query_one(sql, params)
    return int(row[0]) if row else 0


@lru_cache(maxsize=1)
def _cached(bucket: int) -> dict[str, Any]:
    india_where = " OR ".join("lower(coalesce(location,'')) LIKE ?" for _ in INDIA_TERMS)
    india_params = tuple(f"%{t}%" for t in INDIA_TERMS)
    last_scout = db.query_one(
        "SELECT finished_at, status, items_in, items_out FROM agent_runs "
        "WHERE agent IN ('scout','sync_live_jobs') AND finished_at IS NOT NULL "
        "ORDER BY finished_at DESC LIMIT 1"
    )
    last_verify = db.query_one("SELECT MAX(last_seen_at) AS t FROM jobs WHERE closed_at IS NULL")
    return {
        "open_jobs": _q1("SELECT count(*) FROM jobs WHERE closed_at IS NULL"),
        "india_jobs": _q1(f"SELECT count(*) FROM jobs WHERE closed_at IS NULL AND ({india_where})", india_params),
        "remote_jobs": _q1("SELECT count(*) FROM jobs WHERE closed_at IS NULL AND remote=1"),
        "companies_active": _q1("SELECT count(DISTINCT company_name) FROM jobs WHERE closed_at IS NULL"),
        "companies_configured": _q1("SELECT count(*) FROM companies WHERE active=1"),
        "patterns": _q1("SELECT count(*) FROM patterns"),
        "problems": _q1("SELECT count(*) FROM problems"),
        "lessons": _q1("SELECT count(*) FROM resources WHERE kind='youtube'"),
        "last_scout": dict(last_scout) if last_scout else None,
        "last_seen": (last_verify["t"] if last_verify else None),
        "sources": [
            {"source": r["source"], "label": SOURCE_LABELS.get(r["source"], r["source"]), "n": r["n"]}
            for r in db.query(
                "SELECT source, count(*) AS n FROM jobs WHERE closed_at IS NULL GROUP BY source ORDER BY n DESC"
            )
        ],
    }


def site_stats() -> dict[str, Any]:
    # 5-minute bucket so cold serverless boots stay cheap but numbers stay fresh
    bucket = int(datetime.now(UTC).timestamp() // 300)
    return _cached(bucket)


def invalidate() -> None:
    _cached.cache_clear()


def source_label(source: str | None) -> str:
    return SOURCE_LABELS.get(source or "", (source or "").title() or "Unknown")
