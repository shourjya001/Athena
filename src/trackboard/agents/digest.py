"""Daily digest (BUILD_SPEC §8.9): what moved, what broke — failures first."""
from __future__ import annotations

import json

from .. import db


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
    top = [dict(r) for r in db.query(
        "SELECT m.fit_score, m.verdict, m.reasoning, j.company_name, j.title, j.apply_url, j.location "
        "FROM matches m JOIN jobs j ON j.id = m.job_id WHERE m.user_id=? AND m.dismissed_at IS NULL "
        "AND m.fit_score >= 70 ORDER BY m.fit_score DESC LIMIT 8",
        (user_id,))]
    practiced = db.query_one(
        "SELECT COUNT(*) n FROM attempts WHERE user_id=? AND occurred_at > datetime('now','-1 day')",
        (user_id,))["n"]
    return {"source_failures": failures, "pipeline_moves": moved,
            "top_matches": top, "problems_practiced": practiced}


def send_digest_email(user_id: int) -> bool:
    """Build and dispatch the daily digest email to user's registered address."""
    from ..email import render_digest_html, send_email

    u = db.query_one("SELECT id, email FROM users WHERE id=?", (user_id,))
    if not u:
        return False
    d = build(user_id)
    html = render_digest_html(d, u["email"])
    subject = f"🎯 Trackboard Digest: {len(d['top_matches'])} High-Fit Job Recommendations"
    return send_email(u["email"], subject, html)


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
