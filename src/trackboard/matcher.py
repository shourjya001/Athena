"""Two-stage matcher (BUILD_SPEC §8.2): BM25 shortlist locally, then batched
LLM scoring through the provider chain. Chain exhaustion degrades to BM25 rank
with fit_score NULL — never a crash."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from rank_bm25 import BM25Okapi

from pathlib import Path

import yaml

from . import db
from .llm import Chain, parse_json_reply, wrap_untrusted

TARGETS_PATH = Path(__file__).resolve().parents[2] / "config" / "targets.yaml"


def targets_text() -> str:
    """config/targets.yaml flattened into the BM25 profile query, so target
    titles and keywords rank jobs even before the resume is uploaded."""
    if not TARGETS_PATH.exists():
        return ""
    t = yaml.safe_load(TARGETS_PATH.read_text()) or {}
    parts = (t.get("target_titles") or []) + (t.get("keywords") or []) + (t.get("locations") or [])
    return " ".join(parts)

SHORTLIST = 40
BATCH = 8


class FitItem(BaseModel):
    job_ref: str
    fit_score: int = Field(ge=0, le=100)
    verdict: str
    reasoning: str
    strengths: list[str] = []
    gaps: list[str] = []

    @field_validator("verdict")
    @classmethod
    def _v(cls, v: str) -> str:
        s = v.lower().strip().replace(" ", "_").replace("-", "_")
        if "strong" in s:
            return "strong"
        if "worth" in s or "shot" in s:
            return "worth_a_shot"
        if "stretch" in s:
            return "stretch"
        if "skip" in s:
            return "skip"
        if s in ("strong", "worth_a_shot", "stretch", "skip"):
            return s
        return "stretch"


class FitReply(BaseModel):
    results: list[FitItem]


def _tok(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", (text or "").lower())


HARD_EXCLUDE = [
    "lead", "principal", "staff", "director", "manager", "architect", "head", "vp",
    "platform", "devops", "sre", "secops", "infrastructure", "network engineer",
    "cloud network", "intern"
]
SENIOR_HIGH_EXP = re.compile(r"\b(1[0-9]|[6-9])\s*[-+]\s*[0-9]*\s*y|\b[6-9]-|\b1[0-9]\+", re.I)


def shortlist(user_id: int, profile_text: str, limit: int = SHORTLIST) -> list[dict]:
    profile_text = f"{profile_text} {targets_text()}".strip()
    rows = [dict(r) for r in db.query(
        "SELECT j.* FROM jobs j WHERE j.closed_at IS NULL AND j.id NOT IN "
        "(SELECT job_id FROM matches WHERE user_id=?)", (user_id,))]
    if not rows:
        return []

    # Seniority & Platform filter: candidate has ~2 years experience and targets IC SDE / AI roles.
    hard_exclude = HARD_EXCLUDE
    senior_high_exp = SENIOR_HIGH_EXP
    non_india = {
        "san francisco", "sf", "seattle", "new york", "dublin", "london",
        "tokyo", "paris", "sydney", "north america", "europe", "ontario",
        "malaysia", "singapore", "são paulo", "washington", "mountain view",
        "california", "united states", "austin", "chicago"
    }
    india_locs = ["india", "bangalore", "bengaluru", "mumbai", "gurugram", "gurgaon", "chennai", "hyderabad", "delhi", "pune", "noida"]
    filtered_rows = []
    for r in rows:
        title_lower = (r.get("title") or "").lower()
        if any(ex in title_lower for ex in hard_exclude):
            continue
        if senior_high_exp.search(title_lower):
            continue
        loc = (r.get("location") or "").lower()
        is_remote = "remote" in loc
        is_india = any(ind in loc for ind in india_locs)
        is_overseas_onsite = any(f in loc for f in non_india) and not is_remote and not is_india
        if is_overseas_onsite:
            continue
        filtered_rows.append(r)
    rows = filtered_rows or rows

    corpus = [_tok(f"{r['title']} {r.get('description_md') or ''} {r.get('location') or ''}")
              for r in rows]
    scores = BM25Okapi(corpus).get_scores(_tok(profile_text))
    for r, s in zip(rows, scores):
        r["bm25_score"] = float(s)
    return sorted(rows, key=lambda r: r["bm25_score"], reverse=True)[:limit]


SYSTEM = (
    "You are screening jobs for a Software Developer at NPCI (National Payments Corporation of India) "
    "with 2 years of software engineering experience working on core UPI and RuPay digital payments infrastructure. "
    "Tech stack: Python, FastAPI, Java, Spring Boot, React, Redis, PostgreSQL, Docker, Kubernetes, LangChain, RAG, and AI agents.\n\n"
    "CANDIDATE ELIGIBILITY CONSTRAINTS (STRICT):\n"
    "1. EXPERIENCE & TITLE ELIGIBILITY: The candidate has 2 years of total experience (SDE / SDE-II level). "
    "STRICTLY REJECT (verdict='skip') any Lead, Principal, Staff, Architect, or Engineering Manager roles, or roles demanding 7+ years of experience. "
    "STRICTLY REJECT pure Platform, DevOps, SRE, or Infrastructure roles.\n"
    "CARD NETWORKS (Visa, American Express, Mastercard): At Visa, Mastercard, and American Express, IC lateral roles frequently carry titles like 'Sr. SW Engineer' or 'Software Engineer II/III' (e.g. 3-5 years). Do NOT skip them solely because of 'Sr.'—evaluate them as 'worth_a_shot' or 'strong' given the candidate's deep NPCI UPI/RuPay card switch engineering background!\n"
    "Target IC roles: Software Development Engineer (SDE, SDE-II), Backend Engineer, Software Developer, "
    "AI Engineer, Applied AI Engineer, Agent Engineer, Full Stack Builder, Forward Deployed Engineer.\n"
    "2. LOCATION ELIGIBILITY: The candidate accepts: (a) Indian locations (Bengaluru / Bangalore, Mumbai, Gurugram, Delhi-NCR, Hyderabad), or (b) Remote roles (including non-India Remote). "
    "Strictly reject (verdict='skip') any ON-SITE non-India roles.\n"
    "3. DOMAIN PREFERENCE: Highly prioritize payment networks (UPI, RuPay, Visa, Mastercard, Amex, PayPal), payment apps (Razorpay, PhonePe, Paytm, CRED, Fi Money), and top-tier AI/product tech teams.\n\n"
    "Score each job 0-100 for fit against the candidate's profile AS WRITTEN.\n"
    "verdicts: strong | worth_a_shot | stretch | skip. "
    'Respond with JSON: {"results": [{"job_ref": str, "fit_score": int, '
    '"verdict": str, "reasoning": str, "strengths": [str], "gaps": [str]}]} '
    "with exactly one entry per job_ref given."
)


def score_batch(chain: Chain, profile_text: str, batch: list[dict]) -> list[FitItem]:
    parts = [f"RESUME:\n{profile_text[:4000]}"]
    for j in batch:
        parts.append(f"\njob_ref={j['id']} | {j['title']} @ {j['company_name']} "
                     f"({j.get('location') or 'n/a'})\n"
                     + wrap_untrusted((j.get("description_md") or "")[:2500]))
    reply, _ = chain.complete("capable", SYSTEM, "\n".join(parts))
    raw = parse_json_reply(reply)
    if isinstance(raw, list):
        raw = {"results": raw}
    parsed = FitReply.model_validate(raw)
    return parsed.results


def run_for_user(user_id: int, profile_text: str, chain: Chain | None = None) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cands = shortlist(user_id, profile_text)
    for c in cands:  # store BM25 rank first so scoring failure still leaves a queue
        db.execute(
            "INSERT INTO matches (user_id, job_id, bm25_score) VALUES (?,?,?) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET bm25_score=excluded.bm25_score",
            (user_id, c["id"], c["bm25_score"]))
    scored = failed = llm_calls = 0
    if chain is not None:
        for i in range(0, len(cands), BATCH):
            batch = cands[i:i + BATCH]
            llm_calls += 1
            b_num = i // BATCH + 1
            b_total = (len(cands) + BATCH - 1) // BATCH
            print(f"  scoring batch {b_num}/{b_total} ({len(batch)} jobs)...")
            try:
                for item in score_batch(chain, profile_text, batch):
                    ref_clean = re.sub(r"[^\d]", "", str(item.job_ref))
                    match_job = next(
                        (c for c in batch if str(c["id"]) == str(item.job_ref) or (ref_clean and str(c["id"]) == ref_clean)),
                        None,
                    )
                    if not match_job:
                        continue  # hallucinated ref — drop
                    target_id = match_job["id"]
                    db.execute(
                        "UPDATE matches SET fit_score=?, verdict=?, reasoning=?, "
                        "gaps_json=?, strengths_json=?, scored_at=? WHERE user_id=? AND job_id=?",
                        (item.fit_score, item.verdict, item.reasoning,
                         json.dumps(item.gaps), json.dumps(item.strengths), now,
                         user_id, target_id))
                    scored += 1
            except Exception as e:
                import logging
                logging.getLogger("trackboard.matcher").warning("Batch scoring error: %s", e)
                failed += len(batch)
    return {"shortlisted": len(cands), "scored": scored, "unscored": failed, "llm_calls": llm_calls}
