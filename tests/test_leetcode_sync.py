import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["DB_URL"] = "sqlite:///" + str(Path(__file__).parent / ".test_lc.db")

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
        c.execute("INSERT INTO users (email, display_name, leetcode_user, created_at) "
                  "VALUES ('t@x.com','t','handle',datetime('now'))")
        c.execute("INSERT INTO patterns (slug,name,family,summary,cues_json,sort_order) "
                  "VALUES ('p1','P1','arrays','s','[]',1)")
        c.execute("INSERT INTO problems (leetcode_slug,title,difficulty,pattern_id) "
                  "VALUES ('two-sum','Two Sum','easy',1)")
    yield


def fake_fetch(query, variables):
    if "matchedUser" in query:
        return {"matchedUser": {"username": "handle", "submitStatsGlobal": {"acSubmissionNum": [
            {"difficulty": "All", "count": 42}, {"difficulty": "Easy", "count": 20},
            {"difficulty": "Medium", "count": 18}, {"difficulty": "Hard", "count": 4}]}}}
    return {"recentAcSubmissionList": [
        {"id": "1", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1735689600"},
        {"id": "2", "title": "Unknown", "titleSlug": "not-in-catalogue", "timestamp": "1735689700"},
    ]}


def test_sync_records_known_problems_and_state():
    from trackboard import db
    from trackboard.agents.base import AgentRun
    from trackboard.agents.leetcode_sync import sync_user
    user = dict(db.query_one("SELECT * FROM users"))
    with AgentRun("leetcode_sync") as run:
        n = sync_user(user, fake_fetch, run)
    assert n == 1                                    # unknown slug skipped, not an error
    assert db.query_one("SELECT COUNT(*) n FROM attempts")["n"] == 1
    st = db.query_one("SELECT * FROM leetcode_state WHERE user_id=1")
    assert st["total_solved"] == 42 and st["medium_solved"] == 18
    # idempotent: run again, no duplicate attempt
    with AgentRun("leetcode_sync") as run:
        sync_user(user, fake_fetch, run)
    assert db.query_one("SELECT COUNT(*) n FROM attempts")["n"] == 1
    assert db.query_one("SELECT status FROM agent_runs ORDER BY id DESC LIMIT 1")["status"] == "ok"


def test_agent_run_partial_on_error():
    from trackboard import db
    from trackboard.agents.base import AgentRun
    with AgentRun("leetcode_sync") as run:
        run.error("t@x.com", "boom")
    assert db.query_one("SELECT status FROM agent_runs ORDER BY id DESC LIMIT 1")["status"] == "partial"
