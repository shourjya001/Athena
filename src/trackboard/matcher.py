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


def load_avoid_titles(track: str = "tech") -> list[str]:
    if track == "business":
        return [
            "director", "vice president", "vp of", "head of", "avp ", "avp-",
            "managing director", "partner", "general manager", "chief",
        ]
    avoids = [
        "sde-2", "sde 2", "sde-ii", "sde ii", "sde2",
        "sde-3", "sde 3", "sde-iii", "sde iii", "sde3",
        "sde-iv", "sde iv", "sde-4", "sde 4", "sde4",
        " iii", " - iii", "-iii", "iii -", "iii ",
        " ii", " - ii", "-ii", "ii -", "ii ",
        " - 2", "- 2", "-2", " -2",
        " - 3", "- 3", "-3", " -3",
        "sdet 2", "sdet ii", "sdet-2", "sdet-ii",
        "level 2", "level ii", "level 3", "level iii",
        "senior", "sr.", "sr ", "sr-", "staff", "principal",
        "technical lead", "tech lead", "team lead", "lead ", "lead-",
        "product manager", "project manager", "program manager", "engineering manager",
        "manager", "director", "vice president", "vp of", "head of", "avp ", "avp-",
        "architect", "distinguished", "solutions engineer",
        "field security", "security engineer", "secops", "siem",
    ]
    if TARGETS_PATH.exists():
        try:
            t = yaml.safe_load(TARGETS_PATH.read_text()) or {}
            for item in t.get("avoid_titles", []):
                val = str(item).lower().strip()
                if val and val not in avoids:
                    avoids.append(val)
        except Exception:
            pass
    return avoids


# Shortlist 40 high-relevance jobs for a full, rich daily portal queue
SHORTLIST = 40
BATCH = 5

# ── Track-aware exclusions — tech track excludes ops/business; business track excludes pure dev ──
TECH_TRACK_EXCLUSIONS = [
    "business analyst", "business operations", "operations specialist",
    "operations associate", "operations officer", "operations manager",
    "collections", "accounts payable", "accounts receivable",
    "sales", "marketing", "hr ", "recruiter", "talent acquisition",
    "customer success", "customer support", "content writer",
    "graphic designer", "social media", "seo specialist",
    "branch banking", "policy servicing", "underwriting",
    "clearing & settlement", "kyc documentation",
]

BUSINESS_TRACK_EXCLUSIONS = [
    "engineering manager", "sde", "backend engineer", "frontend engineer",
    "full stack developer", "software engineer", "devops", "cloud network",
    "embedded infrastructure", "lead engineer", "platform engineer",
    "site reliability", "machine learning engineer",
]


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


def _title_matches_targets(title_lower: str, user_titles: list[str]) -> bool:
    """Positive match: does the job title match ANY of the user's target titles?"""
    if not user_titles:
        return True  # no filter set => allow all
    anchors = {
        "backend", "frontend", "fullstack", "full stack", "ai", "settlement",
        "clearing", "operations", "depository", "underwriting", "kyc", "payments",
        "upi", "banking", "sde", "developer", "engineer", "analyst", "specialist",
        "associate", "officer", "distributed", "platform", "machine learning", "data"
    }
    for ut in user_titles:
        ut_clean = ut.strip().lower()
        if not ut_clean:
            continue
        # Exact substring match
        if ut_clean in title_lower or title_lower in ut_clean:
            return True
        # Whole word token match
        tokens = re.findall(r"[a-z0-9+#.]+", title_lower)
        if ut_clean in tokens:
            return True
        # Match significant words with anchors
        ut_words = [w for w in re.findall(r"[a-z0-9+#.]+", ut_clean) if len(w) > 2]
        matches = [w for w in ut_words if w in title_lower]
        if matches:
            if any(w in anchors for w in matches):
                return True
            if len(matches) >= 2:
                return True
    return False


def shortlist(user_id: int, profile_text: str, limit: int = SHORTLIST) -> list[dict]:
    # ── 1. Load user profile preferences ──
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user_id,))
    }
    user_titles = [t.strip().lower() for t in answers.get("titles", "").split(",") if t.strip()]
    if not user_titles and TARGETS_PATH.exists():
        try:
            t = yaml.safe_load(TARGETS_PATH.read_text()) or {}
            user_titles = [str(item).strip().lower() for item in t.get("target_titles", []) if str(item).strip()]
        except Exception:
            pass

    user_exp = int(answers.get("experience_years", "2") or "2")
    user_locs = [l.strip().lower() for l in answers.get("locations", "india,remote").split(",") if l.strip()]
    user_track = answers.get("track", "tech")
    user_avoids = [a.strip().lower() for a in answers.get("avoid_titles", "").split(",") if a.strip()]
    all_avoids = load_avoid_titles(user_track) + user_avoids

    # ── 2. Query only active open jobs not already applied to or dismissed ──
    rows = [
        dict(r)
        for r in db.query(
            "SELECT j.* FROM jobs j WHERE j.closed_at IS NULL "
            "AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
            "AND j.id NOT IN (SELECT job_id FROM matches WHERE user_id=? AND dismissed_at IS NOT NULL)",
            (user_id, user_id),
        )
    ]
       # ── 3. Overseas filter keywords ──
    overseas_keywords = {
        "san francisco", "sf", "seattle", "new york", "dublin", "london",
        "tokyo", "paris", "sydney", "north america", "europe", "ontario",
        "malaysia", "singapore", "são paulo", "washington", "mountain view",
        "california", "united states", "austin", "chicago", "denmark",
        "italy", "calgary", "canada", "israel", "sweden", "netherlands",
        "united kingdom", "germany", "france", "japan", "australia",
        "brazil", "ireland", "spain", "poland", "nordics", "emea", "latam",
        "toronto", "austin", "tel aviv",
    }
    overseas_tokens = {
        "us", "usa", "canada", "toronto", "calgary", "ontario", "israel",
        "denmark", "sweden", "netherlands", "uk", "london", "germany", "france",
        "japan", "tokyo", "australia", "sydney", "brazil", "ireland", "dublin",
        "spain", "poland", "singapore", "malaysia", "nordics", "emea", "latam",
        "pst", "est", "cst", "mst", "austin", "seattle", "sf", "california"
    }

    filtered_rows = []
    for r in rows:
        title_lower = (r.get("title") or "").lower()

        # ── 3a. Seniority & Avoid blocklist (excludes SDE-2, Senior, Manager, etc.) ──
        if user_exp <= 3 or user_avoids:
            if any(ex in title_lower for ex in all_avoids):
                continue

        # ── 3b. Experience check in title: e.g. "7 to 11 years", "4+ YOE", "5-7 years" ──
        exp_match = re.search(r"(\d+)\s*(?:-|to|\+)\s*(?:\d+)?\s*(?:years?|yoe|yrs?)", title_lower)
        if exp_match:
            min_req_years = int(exp_match.group(1))
            if min_req_years > user_exp + 1:
                continue

        # ── 3c. Track-based filtering ──
        if user_track == "tech":
            if any(ex in title_lower for ex in TECH_TRACK_EXCLUSIONS):
                continue
        elif user_track == "business":
            if any(tk in title_lower for tk in BUSINESS_TRACK_EXCLUSIONS):
                continue

        # ── 3d. Positive title matching — only keep jobs matching user targets ──
        if user_titles and not _title_matches_targets(title_lower, user_titles):
            continue

        # ── 3e. Location filtering ──
        loc_lower = (r.get("location") or "").lower()
        loc_tokens = set(re.findall(r"[a-z0-9]+", loc_lower))
        is_overseas = bool(overseas_tokens & loc_tokens) or any(k in loc_lower for k in overseas_keywords)
        is_preferred_loc = any((pl in loc_lower and (pl not in ("remote", "anywhere") or not is_overseas)) for pl in user_locs) if user_locs else False
        is_india_or_general_remote = ("india" in loc_lower or "bengaluru" in loc_lower or "bangalore" in loc_lower
                                      or "mumbai" in loc_lower or "hyderabad" in loc_lower or "delhi" in loc_lower
                                      or "gurugram" in loc_lower or "pune" in loc_lower or "noida" in loc_lower
                                      or "chennai" in loc_lower or ("remote" in loc_lower and not is_overseas))

        if is_overseas and not is_preferred_loc:
            continue
        if not is_preferred_loc and not is_india_or_general_remote and not ("remote" in loc_lower and not is_overseas):
            continue

        filtered_rows.append(r)

    candidate_pool = filtered_rows
    if not candidate_pool:
        return []

    # ── 4. Score with BM25 against user profile text ──
    corpus = [
        _tok(f"{r['title']} {r.get('description_md') or ''} {r.get('location') or ''}")
        for r in candidate_pool
    ]
    tokenized_query = _tok(profile_text)
    if not tokenized_query:
        tokenized_query = ["operations", "analyst"] if user_track == "business" else ["engineer", "developer"]

    scores = BM25Okapi(corpus).get_scores(tokenized_query)
    for r, s in zip(candidate_pool, scores):
        r["bm25_score"] = float(s)

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
        "STRICT EVALUATION RULES:\n"
        "1. EXPERIENCE CHECK: If the JD explicitly requires MORE years of experience than the candidate has, "
        f"the candidate has {exp} years. If JD asks for {int(exp)+3}+ years, verdict MUST be 'skip'.\n"
        "2. ROLE RELEVANCE: Score HIGH only if the role closely matches the candidate's target roles and skills. "
        "A 'Software Engineer' candidate should NOT score high on 'Business Analyst' roles.\n"
        "3. LOCATION: Accept preferred locations or Remote roles. Reject on-site non-India roles.\n"
        "4. SCORING: Score 0-100 for fit against the candidate's profile AS WRITTEN.\n"
        "   - strong (80-100): role matches target titles, skills align, experience fits\n"
        "   - worth_a_shot (60-79): partial match, some skill overlap\n"
        "   - stretch (40-59): tangential fit, significant skill gaps\n"
        "   - skip (<40): wrong domain, wrong seniority, or wrong location\n\n"
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

    # Clear stale unscored matches before re-inserting (prevents phantom scores)
    db.execute(
        "DELETE FROM matches WHERE user_id=? AND fit_score IS NULL AND dismissed_at IS NULL",
        (user_id,),
    )

    for c in cands:
        db.execute(
            "INSERT INTO matches (user_id, job_id, bm25_score) VALUES (?,?,?) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET bm25_score=excluded.bm25_score",
            (user_id, c["id"], c["bm25_score"]),
        )
    scored = failed = llm_calls = 0

    if chain is not None:
        import time
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
            # 3s inter-batch delay to avoid rate-limit cascades on free tiers
            time.sleep(3.0)

    return {"shortlisted": len(cands), "scored": scored, "unscored": failed, "llm_calls": llm_calls}
