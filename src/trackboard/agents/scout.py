"""Scout: pull every source, normalise, dedupe, strike (BUILD_SPEC §8.1).

Run: python -m trackboard.agents.scout [--dry-run] [--alerts-dir DIR]
--alerts-dir parses saved .html alert emails (filename prefix picks the
portal: linkedin_*.html etc.) so the pipeline works before Gmail is wired.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .. import db, jobs
from ..settings import get_settings
from ..sources import aggregators, alert_emails, ats
from .base import AgentRun


def sync_company(company: dict, fetch, run: AgentRun, dry: bool) -> None:
    fetcher = ats.FETCHERS.get(company["ats"])
    if fetcher is None:
        run.error(company["name"], f"no fetcher for {company['ats']}")
        return
    postings = fetcher(company["board_token"], fetch)
    run.items_in += len(postings)
    seen = set()
    for p in postings:
        p["company_name"] = company["name"]
        p["company_id"] = company["id"]
        fp = jobs.fingerprint(company["name"], p["title"], p.get("location"))
        seen.add(fp)
        if dry:
            continue
        if jobs.upsert(p) in ("new", "upgraded"):
            run.items_out += 1
    if not dry:
        jobs.apply_strikes(company["ats"], seen, company_id=company["id"])
        db.execute("UPDATE companies SET last_ok_at=datetime('now'), last_error=NULL WHERE id=?",
                   (company["id"],))


def sync_alerts_dir(directory: Path, run: AgentRun, dry: bool) -> None:
    for path in sorted(directory.glob("*.html")):
        portal = path.name.split("_")[0].lower()
        parser = alert_emails.PARSERS.get(portal)
        if parser is None:
            run.error(path.name, "unknown portal prefix")
            continue
        cards = parser(path.read_text(errors="ignore"))
        run.items_in += len(cards)
        if not cards:
            run.error(path.name, "0 cards from non-empty email — template changed?")
            continue
        for c in cards:
            c["apply_url"] = alert_emails.strip_tracking(c.pop("raw_url"))
            c["posted_at_approx"] = 1
            if not dry and jobs.upsert(c) in ("new", "upgraded"):
                run.items_out += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--alerts-dir", type=Path)
    args = ap.parse_args()

    fetch = ats.default_fetch(get_settings().user_agent)
    companies = [dict(r) for r in db.query("SELECT * FROM companies WHERE active=1")]
    with AgentRun("scout") as run:
        for c in companies:
            try:
                sync_company(c, fetch, run, args.dry_run)
            except Exception as e:
                run.error(c["name"], str(e))
                db.execute("UPDATE companies SET last_error=? WHERE id=?", (str(e)[:300], c["id"]))
        try:
            remotive_seen: set[str] = set()
            for job in aggregators.fetch_remotive(fetch):
                run.items_in += 1
                remotive_seen.add(jobs.fingerprint(job.get("company_name", ""),
                                                   job["title"], job.get("location")))
                if not args.dry_run and jobs.upsert(job) in ("new", "upgraded"):
                    run.items_out += 1
            if not args.dry_run:
                jobs.apply_strikes("remotive", remotive_seen)
        except Exception as e:
            run.error("remotive", str(e))   # failed fetch -> no strikes, per §8.1.4
        if args.alerts_dir and args.alerts_dir.exists():
            sync_alerts_dir(args.alerts_dir, run, args.dry_run)
        run.detail["mode"] = "dry" if args.dry_run else "live"
    print(f"scout: in={run.items_in} out={run.items_out} errors={len(run.detail.get('errors', []))}")


if __name__ == "__main__":
    main()
