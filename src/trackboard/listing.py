"""Public and per-user job listing with honest, server-side filters (Phase 1 / 4.2)."""
from __future__ import annotations

import json
import re
from typing import Any

from . import db
from .stats import INDIA_TERMS, source_label

PAGE_SIZE = 20

NON_ENGINEERING = [
    "sales", "account executive", "business development", " hr ", "hr ", "human resources",
    "recruit", "talent acquisition", "insurance", "compliance specialist", "onboarding advocate",
    "editor", "localization", "localisation", "telecaller", "marketing", "customer success",
    "customer support", "content writer", "graphic designer", "social media", "seo specialist",
    "gtm ", "go-to-market", "retirement", "payroll", "accountant", "accounts payable",
    "accounts receivable", "collections", "legal counsel", "paralegal", "office manager",
    "executive assistant", "receptionist", "brand ", "communications", "public relations",
    "partnerships", "solutions consultant", "salesforce admin", "operations analyst", "operations associate",
    "operations manager", "operations specialist", "settlements", "reconciliation", "kyc", "aml ",
]
ENGINEERING_HINT = [
    "engineer", "developer", "sde", "software", "backend", "frontend", "full stack", "fullstack",
    "devops", "sre", "platform", "data scientist", "machine learning", "ml ", "ai ", "architect",
    "programmer", "technical", "infrastructure", "security", "qa ", "quality assurance", "data analyst",
]
SENIOR_MARKERS = [
    "senior", "sr.", "sr ", "staff", "principal", "lead", "manager", "director", "head of", "vp",
    "vice president", "architect", "distinguished", "fellow", " iii", " iv", "-3", " 3", "-4",
]
MID_MARKERS = [" ii", "-2", " 2", "sde2", "sde-2", "mid-level", "mid level", "l4", "l5"]
JUNIOR_MARKERS = ["intern", "junior", "graduate", "new grad", "entry", "associate", "sde i", "sde-1", "sde 1", "l3", "fresher", "trainee", "apprentice"]

BUSINESS_TRACK_TITLES = [
    "business analyst", "product analyst", "data analyst", "operations", "kyc", "aml",
    "banking", "settlement", "reconciliation", "risk analyst", "credit analyst", "treasury",
    "investment", "finance", "compliance", "audit",
]


def _seniority(title: str) -> str:
    t = f" {title.lower()} "
    if any(m in t for m in JUNIOR_MARKERS):
        return "junior"
    if any(m in t for m in SENIOR_MARKERS):
        return "senior"
    if any(m in t for m in MID_MARKERS):
        return "mid"
    return "mid"


def _is_engineering(title: str) -> bool:
    t = f" {title.lower()} "
    if any(x in t for x in NON_ENGINEERING):
        return False
    return any(x in t for x in ENGINEERING_HINT)


def _is_business(title: str) -> bool:
    t = title.lower()
    return any(x in t for x in BUSINESS_TRACK_TITLES)


def _is_india(location: str | None, remote: int) -> bool:
    loc = (location or "").lower()
    return any(t in loc for t in INDIA_TERMS)


def parse_filters(params) -> dict[str, Any]:
    def one(key, default, allowed):
        v = (params.get(key) or default).strip().lower()
        return v if v in allowed else default

    q = (params.get("q") or "").strip()[:80]
    try:
        page = max(1, int(params.get("page") or 1))
    except ValueError:
        page = 1
    return {
        "q": q,
        "region": one("region", "india", {"india", "remote", "all"}),
        "track": one("track", "tech", {"tech", "business", "all"}),
        "level": one("level", "any", {"junior", "mid", "senior", "any"}),
        "source": (params.get("source") or "").strip().lower()[:32],
        "page": page,
    }


def query_string(f: dict[str, Any], **overrides) -> str:
    from urllib.parse import urlencode

    merged = {**f, **overrides}
    out = {k: v for k, v in merged.items() if v not in ("", None) and not (k == "page" and v == 1)}
    for k, default in (("region", "india"), ("track", "tech"), ("level", "any")):
        if out.get(k) == default:
            out.pop(k, None)
    return urlencode(out)


def list_jobs(f: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {items, total, page, pages, filters}. Scores are attached only when a
    signed-in user has a real scored match for that job."""
    where = ["j.closed_at IS NULL"]
    params: list[Any] = []
    if f["q"]:
        where.append("(lower(j.title) LIKE ? OR lower(j.company_name) LIKE ?)")
        like = f"%{f['q'].lower()}%"
        params += [like, like]
    if f["source"]:
        where.append("j.source = ?")
        params.append(f["source"])
    if f["region"] == "india":
        where.append("(" + " OR ".join("lower(coalesce(j.location,'')) LIKE ?" for _ in INDIA_TERMS) + " OR j.remote=1)")
        params += [f"%{t}%" for t in INDIA_TERMS]
    elif f["region"] == "remote":
        where.append("(j.remote=1 OR lower(coalesce(j.location,'')) LIKE '%remote%')")

    uid = user["id"] if user and user.get("is_authenticated") else None
    if uid:
        where.append("j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?)")
        params.append(uid)
        sql = (
            "SELECT j.id, j.company_name, j.title, j.location, j.remote, j.source, j.first_seen_at, "
            "j.posted_at, j.posted_at_approx, j.description_md, j.employment_type, "
            "m.id AS match_id, m.fit_score, m.verdict, m.reasoning, m.gaps_json, m.strengths_json, "
            "m.scored_at, m.bm25_score, m.dismissed_at "
            "FROM jobs j LEFT JOIN matches m ON m.job_id=j.id AND m.user_id=? "
            "WHERE " + " AND ".join(where) + " AND m.dismissed_at IS NULL "
            "ORDER BY (m.fit_score IS NULL), m.fit_score DESC, m.bm25_score DESC, j.first_seen_at DESC"
        )
        params = [uid] + params
    else:
        sql = (
            "SELECT j.id, j.company_name, j.title, j.location, j.remote, j.source, j.first_seen_at, "
            "j.posted_at, j.posted_at_approx, j.description_md, j.employment_type, "
            "NULL AS match_id, NULL AS fit_score, NULL AS verdict, NULL AS reasoning, NULL AS gaps_json, "
            "NULL AS strengths_json, NULL AS scored_at, NULL AS bm25_score, NULL AS dismissed_at "
            "FROM jobs j WHERE " + " AND ".join(where) + " ORDER BY j.first_seen_at DESC, j.id DESC"
        )

    rows = [dict(r) for r in db.query(sql, params)]

    items = []
    for d in rows:
        title = d.get("title") or ""
        if f["track"] == "tech" and not _is_engineering(title):
            continue
        if f["track"] == "business" and not _is_business(title):
            continue
        sen = _seniority(title)
        if f["level"] != "any" and sen != f["level"]:
            continue
        d["seniority"] = sen
        d["source_label"] = source_label(d.get("source"))
        d["is_india"] = _is_india(d.get("location"), d.get("remote") or 0)
        d["scored"] = bool(d.get("scored_at")) and d.get("fit_score") is not None
        d["gaps"] = json.loads(d.get("gaps_json") or "[]") if d["scored"] else []
        d["strengths"] = json.loads(d.get("strengths_json") or "[]") if d["scored"] else []
        # posted_at in this dataset equals ingestion time; show "first seen" honestly.
        d["seen_label"] = _rel_date(d.get("first_seen_at"))
        d["desc_preview"] = _preview(d.get("description_md") or "")
        items.append(d)

    total = len(items)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(f["page"], pages)
    start = (page - 1) * PAGE_SIZE
    return {
        "jobs": items[start:start + PAGE_SIZE],
        "total": total,
        "page": page,
        "pages": pages,
        "has_next": page < pages,
        "filters": f,
    }


_TAG_RE = re.compile(r"<\s*br\s*/?\s*>|</p\s*>|</li\s*>|</h[1-6]\s*>", re.I)
_OTHER_TAG_RE = re.compile(r"<[^>]+>")


def plaintext(md: str | None) -> str:
    """Turn stored description HTML/markdown into readable plain text for display."""
    import html as _html

    text = _TAG_RE.sub("\n", md or "")
    text = _OTHER_TAG_RE.sub("", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _preview(md: str, n: int = 220) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"[#*_`>\[\]]", "", plaintext(md))).strip()
    return text[:n] + ("…" if len(text) > n else "")


def _rel_date(iso: str | None) -> str:
    if not iso:
        return ""
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(iso.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        days = (datetime.now(UTC) - dt).days
    except ValueError:
        return iso[:10]
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    return dt.strftime("%d %b %Y")


def newest(limit: int = 5) -> list[dict[str, Any]]:
    f = {"q": "", "region": "india", "track": "tech", "level": "any", "source": "", "page": 1}
    return list_jobs(f)["jobs"][:limit]


def skill_demand(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real percentage of the current result set mentioning each skill family, capped at 100."""
    families = [
        ("Distributed systems & microservices", ["microservice", "distributed", "grpc"]),
        ("Caching (Redis / Memcached)", ["redis", "memcached", "caching"]),
        ("Containers & Kubernetes", ["docker", "kubernetes", "k8s"]),
        ("Event streaming (Kafka / RabbitMQ)", ["kafka", "rabbitmq", "event-driven", "streaming"]),
        ("Relational databases", ["postgres", "mysql", "sql"]),
        ("System design & scale", ["system design", "high concurrency", "latency", "throughput"]),
        ("Python / FastAPI", ["python", "fastapi", "django", "flask"]),
        ("Cloud (AWS / GCP / Azure)", ["aws", "gcp", "azure"]),
        ("Java / Spring", ["java", "spring"]),
        ("Go", [" go ", "golang"]),
    ]
    if not items:
        return []
    out = []
    n = len(items)
    for name, keys in families:
        c = sum(1 for it in items if any(k in f" {(it.get('title') or '')} {(it.get('description_md') or '')} ".lower() for k in keys))
        if c >= 2:
            out.append({"name": name, "count": c, "pct": min(100, round(100 * c / n))})
    return sorted(out, key=lambda x: -x["count"])[:6]
