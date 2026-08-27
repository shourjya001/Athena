"""Compact spaced-repetition scheduler.

Same state fields as py-fsrs (stability, difficulty, reps, lapses, due) so the
tables are drop-in compatible if the full FSRS library is adopted later. Kept
dependency-free deliberately: py-fsrs changed its public API between major
versions, and a scheduler that silently drifts is worse than a simple one that
is fully tested here.

Ratings: 1 again · 2 hard · 3 good · 4 easy.
Intervals are whole days — this schedules DSA problems, not vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

FIRST_INTERVAL = {1: 1.0, 2: 2.0, 3: 3.0, 4: 7.0}
GROWTH = {1: 0.0, 2: 1.3, 3: 2.3, 4: 3.2}
MAX_INTERVAL_DAYS = 180.0
MIN_INTERVAL_DAYS = 1.0


@dataclass
class ReviewState:
    stability: float = 0.0   # current interval length in days
    difficulty: float = 5.0  # 1 easy .. 10 hard, nudged by ratings
    reps: int = 0
    lapses: int = 0

    def rate(self, rating: int, now: datetime | None = None) -> tuple["ReviewState", datetime]:
        if rating not in (1, 2, 3, 4):
            raise ValueError(f"rating must be 1-4, got {rating}")
        now = now or datetime.now(timezone.utc)

        difficulty = min(10.0, max(1.0, self.difficulty + {1: 1.2, 2: 0.4, 3: -0.2, 4: -0.8}[rating]))

        if self.reps == 0 or rating == 1:
            stability = FIRST_INTERVAL[rating]
        else:
            # harder items grow slower: scale growth by (11 - difficulty) / 6
            factor = GROWTH[rating] * (11.0 - difficulty) / 6.0
            stability = max(MIN_INTERVAL_DAYS, self.stability * max(1.05, factor))

        stability = min(MAX_INTERVAL_DAYS, stability)
        nxt = ReviewState(
            stability=stability,
            difficulty=difficulty,
            reps=self.reps + 1,
            lapses=self.lapses + (1 if rating == 1 else 0),
        )
        return nxt, now + timedelta(days=stability)
