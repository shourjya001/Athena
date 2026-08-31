"""Agent: Matcher — score top BM25 candidate jobs with LLM.

Run: python -m trackboard.agents.matcher [--user email] [--dry-run] [--force-bm25]
Schedule: daily at 06:00 IST (BUILD_SPEC §8.2, LIVE_RUNBOOK Step 5).
"""
from __future__ import annotations

import argparse
import sys

from .. import db, llm, matcher
from ..settings import get_settings
from .base import AgentRun


def resume_text_for_user(user_id: int) -> str:
    """Retrieve master resume text from resumes table, profile answers, or fallback."""
    row = db.query_one(
        "SELECT parsed_text FROM resumes WHERE user_id=? ORDER BY is_master DESC, id DESC LIMIT 1",
        (user_id,),
    )
    base_text = ""
    if row and row["parsed_text"]:
        base_text = row["parsed_text"]
    else:
        from pathlib import Path
        import yaml
        from .. import tailor

        p = Path("config/resume.yaml")
        if p.exists():
            try:
                bank = yaml.safe_load(p.read_text()) or {}
                txt = tailor.bank_to_text(bank)
                if txt:
                    base_text = txt
            except Exception:
                pass

    if not base_text:
        base_text = matcher.targets_text()

    # Append custom user target keywords & titles from profile_answers if present
    answers = {
        r["key"]: r["value"]
        for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user_id,))
    }
    extra_parts = []
    if answers.get("titles"):
        extra_parts.append(f"Target Roles: {answers['titles']}")
    if answers.get("keywords"):
        extra_parts.append(f"Key Skills & Technologies: {answers['keywords']}")
    if answers.get("locations"):
        extra_parts.append(f"Preferred Locations: {answers['locations']}")

    if extra_parts:
        base_text = base_text + "\n\n" + "\n".join(extra_parts)

    return base_text


def run_matcher_for_user(user: dict, dry_run: bool = False, force_bm25: bool = False, max_batches: int | None = None) -> dict:
    profile_text = resume_text_for_user(user["id"])
    with AgentRun("matcher", user_id=user["id"]) as run:
        if dry_run or force_bm25:
            chain = None
        else:
            chain = llm.Chain()

        res = matcher.run_for_user(user["id"], profile_text, chain=chain, max_batches=max_batches)
        run.items_in = res["shortlisted"]
        run.items_out = res["scored"]
        run.llm_calls = res.get("llm_calls", 0)
        run.detail = {
            "shortlisted": res["shortlisted"],
            "scored": res["scored"],
            "unscored": res["unscored"],
            "mode": "bm25_only" if chain is None else "llm",
        }
        if res["unscored"] > 0 and chain is not None:
            run.error("matcher", f"{res['unscored']} jobs could not be scored via LLM (degraded to BM25)")
        print(
            f"matcher: {user['email']} shortlisted={res['shortlisted']} "
            f"scored={res['scored']} unscored={res['unscored']} llm_calls={run.llm_calls}"
        )
        return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Score open jobs against candidate profiles.")
    ap.add_argument("--user", help="run only for this user email")
    ap.add_argument("--dry-run", action="store_true", help="run shortlist and BM25 without LLM scoring")
    ap.add_argument("--force-bm25", action="store_true", help="force BM25 degradation (no LLM)")
    args = ap.parse_args()

    if args.user:
        users = db.query("SELECT * FROM users WHERE email = ?", (args.user,))
        if not users:
            print(f"User with email '{args.user}' not found.", file=sys.stderr)
            return 1
    else:
        users = db.query("SELECT * FROM users ORDER BY id")
        if not users:
            dev_email = get_settings().dev_user_email
            users = db.query("SELECT * FROM users WHERE email = ?", (dev_email,))

    for u in users:
        run_matcher_for_user(dict(u), dry_run=args.dry_run, force_bm25=args.force_bm25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
