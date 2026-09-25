"""Daily digest (BUILD_SPEC §8.9): what moved, what broke — failures first."""
from __future__ import annotations

import json

from .. import db


def get_consolidated_digest_matches(user_id: int, total_limit: int = 25) -> list[dict]:
    """Builds a balanced daily digest consisting of both:
    1. Fresh/New openings (never sent before or newly discovered in the last 48h)
    2. Top high-fit active roles (consistently high-scoring opportunities with rotation)
    """
    fresh_limit = 12
    top_limit = total_limit - fresh_limit

    # 1. Fresh / New Openings (m.digest_sent_at IS NULL)
    fresh_rows = db.query(
        "SELECT m.fit_score, m.verdict, m.reasoning, j.company_name, j.title, j.apply_url, j.location, j.id as job_id, "
        "j.first_seen_at, m.bm25_score "
        "FROM matches m JOIN jobs j ON j.id = m.job_id "
        "WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
        "AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
        "AND (m.fit_score IS NULL OR m.fit_score >= 40) "
        "AND m.digest_sent_at IS NULL "
        "ORDER BY j.first_seen_at DESC, COALESCE(m.fit_score, m.bm25_score) DESC LIMIT ?",
        (user_id, user_id, fresh_limit)
    )
    fresh_jobs = []
    seen_ids = set()
    for r in fresh_rows:
        d = dict(r)
        d["badge"] = "NEW"
        fresh_jobs.append(d)
        seen_ids.add(d["job_id"])

    # 2. Top High-Fit Roles (Highest scoring, active and unapplied, rotated by least recently sent)
    placeholders = ",".join("?" for _ in seen_ids) if seen_ids else "0"
    top_rows = db.query(
        f"SELECT m.fit_score, m.verdict, m.reasoning, j.company_name, j.title, j.apply_url, j.location, j.id as job_id, "
        f"j.first_seen_at, m.bm25_score "
        f"FROM matches m JOIN jobs j ON j.id = m.job_id "
        f"WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
        f"AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
        f"AND (m.fit_score IS NULL OR m.fit_score >= 50) "
        f"AND j.id NOT IN ({placeholders}) "
        f"ORDER BY COALESCE(m.fit_score, m.bm25_score) DESC, COALESCE(m.digest_sent_at, '1970-01-01') ASC LIMIT ?",
        (user_id, user_id, *seen_ids, top_limit)
    )
    top_jobs = []
    for r in top_rows:
        d = dict(r)
        d["badge"] = "TOP FIT"
        top_jobs.append(d)
        seen_ids.add(d["job_id"])

    # 3. Backfill if total < 25
    combined = fresh_jobs + top_jobs
    if len(combined) < total_limit:
        backfill_needed = total_limit - len(combined)
        placeholders = ",".join("?" for _ in seen_ids) if seen_ids else "0"
        extra_rows = db.query(
            f"SELECT m.fit_score, m.verdict, m.reasoning, j.company_name, j.title, j.apply_url, j.location, j.id as job_id, "
            f"j.first_seen_at, m.bm25_score "
            f"FROM matches m JOIN jobs j ON j.id = m.job_id "
            f"WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
            f"AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
            f"AND (m.fit_score IS NULL OR m.fit_score >= 40) "
            f"AND j.id NOT IN ({placeholders}) "
            f"ORDER BY COALESCE(m.fit_score, m.bm25_score) DESC LIMIT ?",
            (user_id, user_id, *seen_ids, backfill_needed)
        )
        for r in extra_rows:
            d = dict(r)
            d["badge"] = "TOP FIT"
            combined.append(d)

    return combined


def build(user_id: int) -> dict:
    failures = [dict(r) for r in db.query(
        "SELECT agent, status, error, started_at FROM agent_runs "
        "WHERE status IN ('failed','partial') AND started_at > datetime('now','-1 day') "
        "ORDER BY started_at DESC LIMIT 10")]
    moved = [dict(r) for r in db.query(
        "SELECT e.status, e.occurred_at, j.company_name, j.title "
        "FROM application_events e JOIN applications a ON a.id = e.application_id "
        "JOIN jobs j ON j.id = a.job_id "
        "WHERE a.user_id=? AND e.occurred_at > datetime('now','-1 day') "
        "ORDER BY e.occurred_at DESC", (user_id,))]

    top = get_consolidated_digest_matches(user_id, total_limit=25)

    return {"source_failures": failures, "pipeline_moves": moved,
            "top_matches": top, "problems_practiced": 0}


def send_digest_email(user_id: int) -> bool:
    """Build and dispatch the daily digest email to user's registered address, updating rotation timestamps."""
    from datetime import datetime, UTC
    from ..email import render_digest_html, send_email

    u = db.query_one("SELECT id, email, display_name FROM users WHERE id=?", (user_id,))
    if not u:
        return False
    u = dict(u)
    d = build(user_id)
    if not d["top_matches"]:
        return False
    html = render_digest_html(d, u["email"])
    subject = f"🎯 Trackboard Digest: {len(d['top_matches'])} Fresh Job Recommendations for {u.get('display_name') or 'You'}"
    sent = send_email(u["email"], subject, html)
    if sent and d["top_matches"]:
        now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        for m in d["top_matches"]:
            if "job_id" in m:
                db.execute("UPDATE matches SET digest_sent_at=? WHERE user_id=? AND job_id=?", (now_iso, user_id, m["job_id"]))
    return sent


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Run daily digest summary")
    parser.add_argument("--email", action="store_true", help="Send HTML digest to user emails")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying state")
    args = parser.parse_args()

    for u in db.query("SELECT id, email FROM users"):
        d = build(u["id"])
        print(f"== {u['email']} ==")
        if d["source_failures"]:
            print("SOURCE FAILURES (fix these first):")
            for f in d["source_failures"]:
                print(f"  {f['agent']} {f['status']}: {f['error']}")
        print(json.dumps({k: v for k, v in d.items() if k != 'source_failures'},
                         indent=1, default=str)[:1500])

        if args.email or not args.dry_run:
            send_digest_email(u["id"])


if __name__ == "__main__":
    main()
