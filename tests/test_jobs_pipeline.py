import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["DB_URL"] = "sqlite:///" + str(Path(__file__).parent / ".test_jobs.db")

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


def _job(**kw):
    base = {"company_name": "Acme", "title": "Backend Engineer", "location": "Bengaluru, India",
            "apply_url": "https://x/apply", "source": "greenhouse", "description_md": "python apis"}
    base.update(kw)
    return base


def test_fingerprint_dedupe_and_source_precedence():
    from trackboard import db, jobs
    assert jobs.upsert(_job()) == "new"
    # same real-world job via an alert email: dedupes, ATS link kept
    assert jobs.upsert(_job(source="alert:linkedin", apply_url="https://lnkd/track?x=1")) == "seen"
    row = db.query_one("SELECT source, apply_url FROM jobs")
    assert row["source"] == "greenhouse" and row["apply_url"] == "https://x/apply"
    # arriving first via alert, then the ATS board: upgraded to the direct link
    assert jobs.upsert(_job(title="Platform Engineer", source="alert:naukri",
                            apply_url="https://naukri/track")) == "new"
    assert jobs.upsert(_job(title="Platform Engineer")) == "upgraded"
    row = db.query_one("SELECT source FROM jobs WHERE title='Platform Engineer'")
    assert row["source"] == "greenhouse"


def test_non_technical_titles_filtered():
    from trackboard import jobs
    assert jobs.upsert(_job(title="Sales Manager")) == "filtered"
    assert jobs.upsert(_job(title="HR Recruiter")) == "filtered"
    assert jobs.upsert(_job(title="Senior SDE II")) == "new"


def test_ai_era_titles_pass_the_filter():
    from trackboard import jobs
    for t in ["AI Engineer", "Forward Deployed Engineer", "GenAI Backend Engineer",
              "Member of Technical Staff", "LLM Platform Engineer",
              "Applied AI Engineer", "Solutions Engineer - AI"]:
        assert jobs.is_technical_ic(t), t
    assert not jobs.is_technical_ic("AI Sales Specialist")      # deny still wins
    assert not jobs.is_technical_ic("Marketing Manager, AI")


def test_strikes_close_after_two_misses_and_reset_on_reappearance():
    from trackboard import db, jobs
    jobs.upsert(_job())
    fp_other = jobs.fingerprint("Acme", "Backend Engineer", "Bengaluru, India")
    assert jobs.apply_strikes("greenhouse", set()) == 0          # strike 1
    assert db.query_one("SELECT strikes FROM jobs")["strikes"] == 1
    jobs.upsert(_job())                                          # reappears -> reset
    assert db.query_one("SELECT strikes FROM jobs")["strikes"] == 0
    jobs.apply_strikes("greenhouse", set())
    assert jobs.apply_strikes("greenhouse", set()) == 1          # strike 2 -> closed
    assert db.query_one("SELECT closed_at FROM jobs")["closed_at"] is not None
    assert fp_other  # silence lint


def test_ats_normalisation_from_fixture():
    from trackboard.sources import ats
    gh = {"jobs": [{"id": 9, "title": "SDE", "location": {"name": "Pune"},
                    "content": "<p>Build &amp; ship</p>", "absolute_url": "https://gh/9",
                    "updated_at": "2026-08-01T00:00:00Z"}]}
    out = ats.fetch_greenhouse("tok", lambda url: gh)
    assert out[0]["description_md"] == "Build & ship" and out[0]["posted_at"] == "2026-08-01"
    lv = [{"id": "a1", "text": "Data Engineer", "categories": {"location": "Remote"},
           "descriptionPlain": "spark", "hostedUrl": "https://lv/a1"}]
    out = ats.fetch_lever("tok", lambda url: lv)
    assert out[0]["title"] == "Data Engineer" and out[0]["apply_url"] == "https://lv/a1"


def test_alert_parser_extracts_cards_and_strips_tracking():
    from trackboard.sources.alert_emails import parse_linkedin, strip_tracking
    html = """
    <table><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/1234?trackingId=zz&refId=aa">Senior Backend Engineer</a>
      <span>Razorpay · Bengaluru</span>
    </td></tr><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/5678?trk=email">Platform Engineer</a>
      <span>CRED · Remote</span>
    </td></tr></table>"""
    cards = parse_linkedin(html)
    assert len(cards) == 2
    assert cards[0]["title"] == "Senior Backend Engineer"
    assert cards[0]["company_name"].startswith("Razorpay")
    assert strip_tracking(cards[0]["raw_url"]).endswith("/jobs/view/1234")
    assert parse_linkedin("<p>no cards here</p>") == []          # zero-card signal, not a guess


def test_strikes_scoped_per_company_not_per_source():
    """CRITICAL regression: syncing company A must never strike company B's
    jobs just because both use the same ATS."""
    from trackboard import db, jobs
    with db.transaction() as c:
        c.execute("INSERT INTO companies (name, ats, board_token) VALUES ('A','greenhouse','a')")
        c.execute("INSERT INTO companies (name, ats, board_token) VALUES ('B','greenhouse','b')")
    ida = db.query_one("SELECT id FROM companies WHERE name='A'")["id"]
    idb = db.query_one("SELECT id FROM companies WHERE name='B'")["id"]
    jobs.upsert(_job(company_name="A", company_id=ida, title="Backend Engineer A"))
    jobs.upsert(_job(company_name="B", company_id=idb, title="Backend Engineer B"))
    # A syncs twice, its job now missing; B is not being synced at all
    jobs.apply_strikes("greenhouse", set(), company_id=ida)
    jobs.apply_strikes("greenhouse", set(), company_id=ida)
    a = db.query_one("SELECT closed_at FROM jobs WHERE company_name='A'")
    b = db.query_one("SELECT closed_at, strikes FROM jobs WHERE company_name='B'")
    assert a["closed_at"] is not None            # A's vanished job closes
    assert b["closed_at"] is None and b["strikes"] == 0   # B untouched
