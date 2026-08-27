"""Sync accepted LeetCode submissions into attempts + reviews.

Run: python -m trackboard.agents.leetcode_sync [--user email] [--dry-run]
Schedule: every 2h with inbox (frequent workflow). BUILD_SPEC §7.5, §8.7.1.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .. import db, practice
from ..settings import get_settings
from ..sources import leetcode
from .base import AgentRun


def sync_user(user: dict, fetch: leetcode.Fetch, run: AgentRun, dry: bool = False) -> int:
    handle = user.get("leetcode_user")
    if not handle:
        return 0
    summary = leetcode.user_summary(handle, fetch)
    recent = leetcode.recent_accepted(handle, fetch)
    run.items_in += len(recent)
    synced = 0
    for sub in recent:
        row = db.query_one("SELECT id FROM problems WHERE leetcode_slug = ?", (sub["titleSlug"],))
        if not row:
            continue  # not in our catalogue; fine
        occurred = datetime.fromtimestamp(int(sub["timestamp"]), tz=timezone.utc)\
            .strftime("%Y-%m-%d %H:%M:%S")
        if dry:
            print(f"  would record {sub['titleSlug']} @ {occurred}")
            synced += 1
            continue
        practice.record_attempt(
            user_id=user["id"], problem_id=row["id"], outcome="solved",
            source="leetcode_sync", occurred_at=occurred,
        )
        synced += 1
    if not dry:
        db.execute(
            "INSERT INTO leetcode_state (user_id, total_solved, easy_solved, medium_solved, "
            "hard_solved, last_synced_at, last_error) VALUES (?,?,?,?,?,datetime('now'),NULL) "
            "ON CONFLICT(user_id) DO UPDATE SET total_solved=excluded.total_solved, "
            "easy_solved=excluded.easy_solved, medium_solved=excluded.medium_solved, "
            "hard_solved=excluded.hard_solved, last_synced_at=excluded.last_synced_at, last_error=NULL",
            (user["id"], summary["all"], summary["easy"], summary["medium"], summary["hard"]),
        )
    run.items_out += synced
    return synced


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="only this email")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fetch = leetcode.default_fetch(get_settings().user_agent)
    users = db.query("SELECT * FROM users WHERE leetcode_user IS NOT NULL")
    with AgentRun("leetcode_sync") as run:
        for u in users:
            u = dict(u)
            if args.user and u["email"] != args.user.lower():
                continue
            try:
                n = sync_user(u, fetch, run, dry=args.dry_run)
                print(f"{u['email']}: {n} submissions")
            except Exception as e:  # per-user isolation -> partial, not failed
                run.error(u["email"], str(e))
                db.execute(
                    "INSERT INTO leetcode_state (user_id, last_error, last_synced_at) "
                    "VALUES (?,?,datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
                    "last_error=excluded.last_error",
                    (u["id"], str(e)[:300]),
                )


if __name__ == "__main__":
    main()
