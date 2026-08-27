"""Pattern-recognition trainer (BUILD_SPEC §8.8.3).

Copyright note: problem statements are NOT stored or displayed — that would
re-host LeetCode content. The drill deep-links to the problem (user reads it
there, ignoring the tags) and answers here. Original, self-authored scenario
text can be added later via an authored field; copied statements never.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from . import db
from .fsrs_lite import ReviewState


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def next_drill(user_id: int) -> dict | None:
    """Prefer patterns whose recognition track is due or unseen; avoid problems
    drilled in the last 14 days."""
    rows = db.query(
        """
        SELECT pr.id, pr.title, pr.leetcode_slug, pr.external_url, pr.difficulty,
               pr.pattern_id
          FROM problems pr
         WHERE pr.pattern_id IS NOT NULL
           AND pr.id NOT IN (
               SELECT problem_id FROM drill_attempts
                WHERE user_id = ? AND occurred_at > datetime('now','-14 days'))
        """,
        (user_id,),
    )
    if not rows:
        return None
    due = {
        r["pattern_id"]
        for r in db.query(
            "SELECT pattern_id FROM pattern_reviews WHERE user_id=? AND due_at <= ?",
            (user_id, _now()),
        )
    }
    seen = {
        r["pattern_id"]
        for r in db.query("SELECT pattern_id FROM pattern_reviews WHERE user_id=?", (user_id,))
    }
    pool = [r for r in rows if r["pattern_id"] in due] or \
           [r for r in rows if r["pattern_id"] not in seen] or list(rows)
    pick = dict(random.choice(pool))
    pick["url"] = (
        f"https://leetcode.com/problems/{pick['leetcode_slug']}/"
        if pick.get("leetcode_slug") else pick.get("external_url")
    )
    return pick


def choices() -> list[dict]:
    return [dict(r) for r in db.query(
        "SELECT id, slug, name, family FROM patterns ORDER BY family, sort_order")]


def answer(user_id: int, problem_id: int, chosen_pattern_id: int, seconds: int | None) -> dict:
    prob = db.query_one(
        "SELECT pr.*, p.name AS pattern_name, p.cues_json, p.id AS pid "
        "FROM problems pr JOIN patterns p ON p.id = pr.pattern_id WHERE pr.id = ?",
        (problem_id,),
    )
    if not prob:
        raise ValueError("unknown problem")
    chosen = db.query_one("SELECT id FROM patterns WHERE id = ?", (chosen_pattern_id,))
    chosen_id = int(chosen["id"]) if chosen else None
    correct = chosen_id == int(prob["pid"])
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO drill_attempts (user_id, problem_id, chosen_pattern_id, correct, seconds, occurred_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, problem_id, chosen_id, int(correct), seconds, _now()),
        )
        row = conn.execute(
            "SELECT stability, difficulty, reps, lapses FROM pattern_reviews "
            "WHERE user_id=? AND pattern_id=?",
            (user_id, prob["pid"]),
        ).fetchone()
        state = (
            ReviewState(row["stability"], row["difficulty"], row["reps"], row["lapses"])
            if row else ReviewState()
        )
        nxt, due = state.rate(3 if correct else 1)
        conn.execute(
            "INSERT INTO pattern_reviews (user_id, pattern_id, stability, difficulty, due_at, reps, lapses, last_review_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, pattern_id) DO UPDATE SET stability=excluded.stability, "
            "difficulty=excluded.difficulty, due_at=excluded.due_at, reps=excluded.reps, "
            "lapses=excluded.lapses, last_review_at=excluded.last_review_at",
            (user_id, prob["pid"], nxt.stability, nxt.difficulty,
             due.strftime("%Y-%m-%d %H:%M:%S"), nxt.reps, nxt.lapses, _now()),
        )
    import json
    return {
        "correct": correct,
        "pattern_name": prob["pattern_name"],
        "cues": json.loads(prob["cues_json"] or "[]"),
        "problem_title": prob["title"],
    }
