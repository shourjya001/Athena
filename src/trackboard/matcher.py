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


def shortlist(user_id: int, profile_text: str, limit: int = SHORTLIST) -> list[dict]:
    # Extract user profile preferences
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user_id,))
    }
    user_titles = [t.strip().lower() for t in answers.get("titles", "").split(",") if t.strip()]
    user_exp = int(answers.get("experience_years", "2") or "2")
    user_locs = [l.strip().lower() for l in answers.get("locations", "india,remote").split(",") if l.strip()]
    user_track = answers.get("track", "tech")

    # Query only active open jobs
    rows = [
        dict(r)
        for r in db.query(
            "SELECT j.* FROM jobs j WHERE j.closed_at IS NULL "
            "AND j.id NOT IN (SELECT job_id FROM matches WHERE user_id=?)",
            (user_id,),
        )
    ]
    if not rows:
        return []

    # Non-India on-site filter (allow Remote and preferred locations)
    non_india = {
        "san francisco", "sf", "seattle", "new york", "dublin", "london",
        "tokyo", "paris", "sydney", "north america", "europe", "ontario",
        "malaysia", "singapore", "são paulo", "washington", "mountain view",
        "california", "united states", "austin", "chicago"
    }

    filtered_rows = []
    for r in rows:
        title_lower = (r.get("title") or "").lower()
        desc_lower = (r.get("description_md") or "").lower()
        loc_lower = (r.get("location") or "").lower()

        # Filter extreme executive/director titles if candidate has <= 3 years experience
        if user_exp <= 3:
            extreme_senior = ["director", "vice president", "vp of", "head of", "principal", "avp ", "avp -"]
            if any(ex in title_lower for ex in extreme_senior):
                continue

        # Track-based filtering
        if user_track == "business":
            # For business/operations track, exclude pure software dev & engineering manager roles
            tech_dev_exclusions = [
                "engineering manager", "sde", "backend engineer", "frontend engineer",
                "full stack developer", "software engineer", "devops", "cloud network",
                "embedded infrastructure", "architect", "lead engineer"
            ]
            if any(tk in title_lower for tk in tech_dev_exclusions):
                continue

        # Location filtering
        is_remote = "remote" in loc_lower or "anywhere" in loc_lower
        is_preferred_loc = any(pl in loc_lower for pl in user_locs) if user_locs else True
        is_overseas_onsite = any(f in loc_lower for f in non_india) and not is_remote and not is_preferred_loc
        if is_overseas_onsite:
            continue

        # Boost matching if title contains one of user target titles
        if user_titles:
            has_title_match = any(
                ut in title_lower or any(word in title_lower for word in ut.split() if len(word) > 3)
                for ut in user_titles
            )
            r["title_matched"] = has_title_match

        filtered_rows.append(r)

    candidate_pool = filtered_rows or rows

    # Score with BM25 against user profile text
    corpus = [
        _tok(f"{r['title']} {r.get('description_md') or ''} {r.get('location') or ''}")
        for r in candidate_pool
    ]
    tokenized_query = _tok(profile_text)
    if not tokenized_query:
        tokenized_query = ["operations", "analyst"] if user_track == "business" else ["engineer", "developer"]

    scores = BM25Okapi(corpus).get_scores(tokenized_query)
    for r, s in zip(candidate_pool, scores):
        bonus = 10.0 if r.get("title_matched") else 0.0
        r["bm25_score"] = float(s) + bonus

    return sorted(candidate_pool, key=lambda r: r["bm25_score"], reverse=True)[:limit]


def build_system_prompt(user_id: int) -> str:
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user_id,))
    }
    user_row = db.query_one("SELECT display_name, email FROM users WHERE id=?", (user_id,))
    name = (user_row["display_name"] if user_row else "") or "Candidate"
    titles = answers.get("titles") or "Software Engineer, Backend Developer"
    keywords = answers.get("keywords") or ""
    locations = answers.get("locations") or "India, Remote, Bengaluru, Mumbai"
    exp = answers.get("experience_years") or "2"
    track = answers.get("track") or "tech"

    return (
        f"You are a rigorous technical and corporate talent recruiter evaluating job descriptions against {name}'s profile.\n\n"
        f"CANDIDATE TARGET PREFERENCES:\n"
        f"- Target Roles: {titles}\n"
        f"- Core Skills & Keywords: {keywords}\n"
        f"- Preferred Locations: {locations}\n"
        f"- Total Experience: ~{exp} years\n"
        f"- Career Track: {track}\n\n"
        "EVALUATION RULES:\n"
        "1. ROLE RELEVANCE: Prioritize jobs matching the candidate's target roles and skills. "
        f"If the role demands 7+ years of experience and candidate has {exp} years, mark verdict='skip' or 'stretch'. "
        "2. LOCATION: Accept preferred locations or Remote roles. Reject on-site non-India roles unless remote is allowed.\n"
        "3. SCORING: Score 0-100 for fit against the candidate's profile AS WRITTEN.\n"
        "verdicts: strong (80-100) | worth_a_shot (60-79) | stretch (40-59) | skip (<40).\n\n"
        "Respond ONLY with valid JSON matching:\n"
        '{"results": [{"job_ref": str, "fit_score": int, "verdict": str, "reasoning": str, "strengths": [str], "gaps": [str]}]}'
    )


def score_batch(chain: Chain, user_id: int, profile_text: str, batch: list[dict]) -> list[FitItem]:
    system_prompt = build_system_prompt(user_id)
    parts = [f"CANDIDATE RESUME & PREFERENCES:\n{profile_text[:3500]}"]
    for j in batch:
        parts.append(
            f"\njob_ref={j['id']} | {j['title']} @ {j['company_name']} ({j.get('location') or 'n/a'})\n"
            + wrap_untrusted((j.get("description_md") or "")[:2000])
        )
    reply, _ = chain.complete("fast", system_prompt, "\n".join(parts))
    raw = parse_json_reply(reply)
    if isinstance(raw, list):
        raw = {"results": raw}
    parsed = FitReply.model_validate(raw)
    return parsed.results


def run_for_user(user_id: int, profile_text: str, chain: Chain | None = None) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cands = shortlist(user_id, profile_text)
    for c in cands:
        db.execute(
            "INSERT INTO matches (user_id, job_id, bm25_score) VALUES (?,?,?) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET bm25_score=excluded.bm25_score",
            (user_id, c["id"], c["bm25_score"]),
        )
    scored = failed = llm_calls = 0

    if chain is not None:
        for i in range(0, len(cands), BATCH):
            batch = cands[i:i + BATCH]
            llm_calls += 1
            b_num = i // BATCH + 1
            b_total = (len(cands) + BATCH - 1) // BATCH
            print(f"  scoring batch {b_num}/{b_total} ({len(batch)} jobs)...")
            try:
                for item in score_batch(chain, user_id, profile_text, batch):
                    ref_clean = re.sub(r"[^\d]", "", str(item.job_ref))
                    match_job = next(
                        (c for c in batch if str(c["id"]) == str(item.job_ref) or (ref_clean and str(c["id"]) == ref_clean)),
                        None,
                    )
                    if not match_job:
                        continue
                    target_id = match_job["id"]
                    db.execute(
                        "UPDATE matches SET fit_score=?, verdict=?, reasoning=?, "
                        "gaps_json=?, strengths_json=?, scored_at=? WHERE user_id=? AND job_id=?",
                        (
                            item.fit_score,
                            item.verdict,
                            item.reasoning,
                            json.dumps(item.gaps),
                            json.dumps(item.strengths),
                            now,
                            user_id,
                            target_id,
                        ),
                    )
                    scored += 1
            except Exception as e:
                import logging
                logging.getLogger("trackboard.matcher").warning("Batch scoring error: %s", e)
                failed += len(batch)
            import time
            time.sleep(0.5)

    return {"shortlisted": len(cands), "scored": scored, "unscored": failed, "llm_calls": llm_calls}
