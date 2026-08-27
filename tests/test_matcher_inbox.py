import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["DB_URL"] = "sqlite:///" + str(Path(__file__).parent / ".test_mi.db")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from trackboard import db
    from trackboard.settings import get_settings
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(get_settings().db_path) + suffix)
        if p.exists():
            p.unlink()
    db.migrate(verbose=False)
    with db.transaction() as c:
        c.execute("INSERT INTO users (email, display_name, created_at) VALUES ('t@x.com','t',datetime('now'))")
    yield


class FakeChain:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.calls = reply, fail, 0

    def complete(self, task_class, system, user):
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm_chain_exhausted")
        return self.reply, "fake"


def _seed_jobs(n=3):
    from trackboard import jobs
    for i in range(n):
        jobs.upsert({"company_name": f"Co{i}", "title": f"Backend Engineer {i}",
                     "location": "Bengaluru", "apply_url": f"https://x/{i}",
                     "source": "greenhouse", "description_md": "python fastapi postgres"})


def test_matcher_scores_via_chain_and_validates():
    from trackboard import db, matcher
    _seed_jobs()
    ids = [r["id"] for r in db.query("SELECT id FROM jobs ORDER BY id")]
    reply = json.dumps({"results": [
        {"job_ref": str(ids[0]), "fit_score": 82, "verdict": "strong",
         "reasoning": "solid overlap", "strengths": ["python"], "gaps": ["k8s"]},
        {"job_ref": str(ids[1]), "fit_score": 40, "verdict": "stretch",
         "reasoning": "junior", "strengths": [], "gaps": ["scale"]},
        {"job_ref": "9999", "fit_score": 99, "verdict": "strong",
         "reasoning": "hallucinated", "strengths": [], "gaps": []},
    ]})
    out = matcher.run_for_user(1, "python fastapi engineer", FakeChain(reply))
    assert out["shortlisted"] == 3 and out["scored"] == 2      # hallucinated ref dropped
    top = db.query_one("SELECT fit_score, verdict FROM matches WHERE job_id=?", (ids[0],))
    assert top["fit_score"] == 82 and top["verdict"] == "strong"


def test_matcher_degrades_to_bm25_when_chain_exhausted():
    from trackboard import db, matcher
    _seed_jobs()
    out = matcher.run_for_user(1, "python fastapi", FakeChain(fail=True))
    assert out["shortlisted"] == 3 and out["scored"] == 0
    rows = db.query("SELECT fit_score, bm25_score FROM matches")
    assert all(r["fit_score"] is None and r["bm25_score"] is not None for r in rows)


def test_inbox_prefilter():
    from trackboard.agents.inbox import prefilter
    doms = {"razorpay.com"}
    assert prefilter("no-reply@greenhouse.io", "anything", doms)
    assert prefilter("talent@razorpay.com", "hello", doms)
    assert prefilter("someone@random.io", "Your application to Acme", doms)
    assert not prefilter("newsletter@random.io", "50% off shoes", doms)


def _mk_application():
    from trackboard import db, jobs
    jobs.upsert({"company_name": "Razorpay", "title": "Backend Engineer",
                 "location": "Bengaluru", "apply_url": "https://x", "source": "greenhouse"})
    jid = db.query_one("SELECT id FROM jobs")["id"]
    db.execute("INSERT INTO applications (user_id, job_id, status, applied_at, last_event_at) "
               "VALUES (1, ?, 'submitted', datetime('now'), datetime('now'))", (jid,))
    return db.query_one("SELECT id FROM applications")["id"]


def test_status_engine_forward_only_and_terminal():
    from trackboard.agents.inbox import advance
    app_id = _mk_application()
    assert advance(app_id, "interview", "gmail:m1", "invited to interview")
    assert not advance(app_id, "acknowledged", "gmail:m2", "regression ignored")
    assert advance(app_id, "rejected", "gmail:m3", "rejected after interview")
    assert not advance(app_id, "offer", "gmail:m4", "cannot leave terminal")
    from trackboard import db
    assert db.query_one("SELECT COUNT(*) n FROM application_events")["n"] == 2


def test_high_confidence_writes_medium_goes_to_review():
    from trackboard import db
    from trackboard.agents.base import AgentRun
    from trackboard.agents.inbox import process_messages
    app_id = _mk_application()
    reply = json.dumps({"results": [
        {"message_ref": "m-high", "is_job_related": True, "company": "Razorpay",
         "role_hint": "Backend", "status": "interview", "evidence": "interview scheduled",
         "confidence": "high"},
        {"message_ref": "m-med", "is_job_related": True, "company": "Razorpay",
         "role_hint": None, "status": "rejected", "evidence": "maybe a rejection",
         "confidence": "medium"},
    ]})
    msgs = [{"id": "m-high", "sender_domain": "greenhouse.io", "subject": "Interview", "snippet": ""},
            {"id": "m-med", "sender_domain": "greenhouse.io", "subject": "Update", "snippet": ""}]
    with AgentRun("inbox", user_id=1) as run:
        process_messages(1, msgs, FakeChain(reply), run)
    assert db.query_one("SELECT status FROM applications WHERE id=?", (app_id,))["status"] == "interview"
    med = db.query_one("SELECT classified_as FROM gmail_seen WHERE message_id='m-med'")
    assert "review" in med["classified_as"]


def test_ghost_pass():
    from trackboard import db
    from trackboard.agents.inbox import ghost_pass
    app_id = _mk_application()
    db.execute("UPDATE applications SET last_event_at=datetime('now','-30 days') WHERE id=?", (app_id,))
    assert ghost_pass() == 1
    assert db.query_one("SELECT status FROM applications WHERE id=?", (app_id,))["status"] == "ghosted"
