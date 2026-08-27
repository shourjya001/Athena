import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["DB_URL"] = "sqlite:///" + str(Path(__file__).parent / ".test_practice.db")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from trackboard import db
    from trackboard.settings import get_settings
    path = get_settings().db_path
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    db.migrate(verbose=False)
    with db.transaction() as c:
        c.execute("INSERT INTO users (email, display_name, created_at) VALUES ('t@x.com','t',datetime('now'))")
        c.execute("INSERT INTO patterns (slug,name,family,summary,cues_json,sort_order) "
                  "VALUES ('p1','P1','arrays','s','[\"cue one\"]',1)")
        c.execute("INSERT INTO patterns (slug,name,family,summary,cues_json,sort_order) "
                  "VALUES ('p2','P2','graphs','s','[\"cue two\"]',2)")
        for i, pat in [(1, 1), (2, 1), (3, 2), (4, 2)]:
            c.execute("INSERT INTO problems (leetcode_slug,title,difficulty,pattern_id,is_canonical) "
                      f"VALUES ('prob-{i}','Prob {i}','easy',{pat},1)")
    yield


def test_fsrs_intervals_grow_and_lapse_resets():
    from trackboard.fsrs_lite import ReviewState
    s = ReviewState()
    s, due1 = s.rate(3)
    s, due2 = s.rate(3)
    s, due3 = s.rate(3)
    assert due3 - due2 > due2 - due1          # intervals grow
    lapsed, due4 = s.rate(1)
    assert lapsed.lapses == 1
    assert lapsed.stability == 1.0            # reset on again


def test_record_attempt_schedules_review_and_dedupes():
    from trackboard import db, practice
    practice.record_attempt(1, 1, "solved", 3, occurred_at="2026-01-01T00:00:00Z", source="leetcode_sync")
    practice.record_attempt(1, 1, "solved", 3, occurred_at="2026-01-01T00:00:00Z", source="leetcode_sync")
    assert db.query_one("SELECT COUNT(*) n FROM attempts")["n"] == 1
    rev = db.query_one("SELECT * FROM reviews WHERE user_id=1 AND problem_id=1")
    assert rev is not None and rev["reps"] == 1


def test_queue_reviews_due_then_new_from_weakest():
    from trackboard import db, practice
    # make user non-cold-start: 10 attempts on pattern 1's problems
    for i in range(10):
        practice.record_attempt(1, 1 + (i % 2), "solved", 3,
                                occurred_at=f"2026-01-01T00:00:{i:02d}Z")
    # force a review due now
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute("UPDATE reviews SET due_at=? WHERE user_id=1 AND problem_id=1", (past,))
    q = practice.build_queue(1)
    assert not q["cold_start"]
    assert any(r["id"] == 1 for r in q["reviews"])
    assert q["weak_pattern"]["slug"] == "p2"          # nothing solved there
    assert all(n["pattern_slug"] == "p2" for n in q["new"])


def test_cold_start_uses_taxonomy_order():
    from trackboard import practice
    q = practice.build_queue(1)
    assert q["cold_start"] and len(q["new"]) == 2
    assert q["new"][0]["pattern_slug"] == "p1"


def test_drill_answer_feedback_and_pattern_review():
    from trackboard import db, drill
    item = drill.next_drill(1)
    assert item and item["url"].startswith("https://leetcode.com/problems/")
    res = drill.answer(1, 1, chosen_pattern_id=2, seconds=20)   # wrong: prob 1 is p1
    assert res["correct"] is False and res["cues"] == ["cue one"]
    pr = db.query_one("SELECT * FROM pattern_reviews WHERE user_id=1 AND pattern_id=1")
    assert pr is not None and pr["lapses"] == 1
