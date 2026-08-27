"""The daily loop: record attempts, schedule reviews, build the queue.

BUILD_SPEC §8.7. The queue is: due reviews (oldest first, cap 5) plus 2 new
problems from the weakest pattern. Cold start (<10 attempts) falls back to
taxonomy order.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import db
from .fsrs_lite import ReviewState

REVIEW_CAP = 5
NEW_PER_DAY = 2
COLD_START_ATTEMPTS = 10

_OUTCOME_DEFAULT_RATING = {"solved": 3, "solved_with_help": 2, "failed": 1, "skipped": 1}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def record_attempt(
    user_id: int,
    problem_id: int,
    outcome: str,
    confidence: int | None = None,
    minutes: int | None = None,
    source: str = "user",
    occurred_at: str | None = None,
) -> None:
    rating = confidence or _OUTCOME_DEFAULT_RATING.get(outcome, 3)
    occurred_at = occurred_at or _now()
    with db.transaction() as conn:
        dup = conn.execute(
            "SELECT 1 FROM attempts WHERE user_id=? AND problem_id=? AND occurred_at=? AND source=?",
            (user_id, problem_id, occurred_at, source),
        ).fetchone()
        if dup:
            return
        conn.execute(
            "INSERT INTO attempts (user_id, problem_id, outcome, minutes, confidence, source, occurred_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, problem_id, outcome, minutes, rating, source, occurred_at),
        )
        row = conn.execute(
            "SELECT stability, difficulty, reps, lapses FROM reviews WHERE user_id=? AND problem_id=?",
            (user_id, problem_id),
        ).fetchone()
        state = (
            ReviewState(row["stability"], row["difficulty"], row["reps"], row["lapses"])
            if row
            else ReviewState()
        )
        nxt, due = state.rate(rating)
        conn.execute(
            "INSERT INTO reviews (user_id, problem_id, stability, difficulty, due_at, reps, lapses, last_review_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, problem_id) DO UPDATE SET stability=excluded.stability, "
            "difficulty=excluded.difficulty, due_at=excluded.due_at, reps=excluded.reps, "
            "lapses=excluded.lapses, last_review_at=excluded.last_review_at",
            (user_id, problem_id, nxt.stability, nxt.difficulty,
             due.strftime("%Y-%m-%d %H:%M:%S"), nxt.reps, nxt.lapses, _now()),
        )


def weakest_pattern(user_id: int) -> dict | None:
    """Lowest solved/total ratio among patterns with problems; ties -> most lapses."""
    row = db.query_one(
        """
        SELECT p.id, p.slug, p.name,
               CAST(COALESCE(s.solved,0) AS REAL) / COUNT(pr.id) AS ratio,
               COALESCE(l.lapses,0) AS lapses
          FROM patterns p
          JOIN problems pr ON pr.pattern_id = p.id
          LEFT JOIN (SELECT x.pattern_id AS pid, COUNT(DISTINCT a.problem_id) AS solved
                       FROM attempts a JOIN problems x ON x.id = a.problem_id
                      WHERE a.user_id = :u AND a.outcome IN ('solved','solved_with_help')
                      GROUP BY x.pattern_id) s ON s.pid = p.id
          LEFT JOIN (SELECT x.pattern_id AS pid, SUM(r.lapses) AS lapses
                       FROM reviews r JOIN problems x ON x.id = r.problem_id
                      WHERE r.user_id = :u GROUP BY x.pattern_id) l ON l.pid = p.id
         GROUP BY p.id
         ORDER BY ratio ASC, lapses DESC, p.sort_order ASC
         LIMIT 1
        """,
        {"u": user_id},
    )
    return dict(row) if row else None


def _attempt_count(user_id: int) -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM attempts WHERE user_id=?", (user_id,))
    return int(row["n"]) if row else 0


def _new_problems(user_id: int, pattern_id: int | None, limit: int) -> list[dict]:
    rows = db.query(
        """
        SELECT pr.*, p.slug AS pattern_slug, p.name AS pattern_name
          FROM problems pr JOIN patterns p ON p.id = pr.pattern_id
         WHERE (:pid IS NULL OR pr.pattern_id = :pid)
           AND pr.id NOT IN (SELECT problem_id FROM attempts WHERE user_id = :u)
         ORDER BY p.sort_order, pr.is_canonical DESC,
                  CASE pr.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
         LIMIT :lim
        """,
        {"pid": pattern_id, "u": user_id, "lim": limit},
    )
    return [dict(r) for r in rows]


def build_queue(user_id: int) -> dict:
    reviews = db.query(
        """
        SELECT r.due_at, r.lapses, pr.*, p.slug AS pattern_slug, p.name AS pattern_name
          FROM reviews r
          JOIN problems pr ON pr.id = r.problem_id
          JOIN patterns p ON p.id = pr.pattern_id
         WHERE r.user_id = ? AND r.due_at <= ?
         ORDER BY r.due_at ASC LIMIT ?
        """,
        (user_id, _now(), REVIEW_CAP),
    )
    cold = _attempt_count(user_id) < COLD_START_ATTEMPTS
    weak = None if cold else weakest_pattern(user_id)
    new = _new_problems(user_id, weak["id"] if weak else None, NEW_PER_DAY)
    return {
        "reviews": [dict(r) for r in reviews],
        "new": new,
        "weak_pattern": weak,
        "cold_start": cold,
    }
