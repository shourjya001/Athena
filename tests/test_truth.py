"""Every number rendered comes from stats; no placeholders survive."""
from __future__ import annotations

import re
from pathlib import Path

from trackboard import db, stats
from tests.helpers import guest

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "trackboard" / "templates"


def test_home_numbers_match_site_stats():
    db.migrate(verbose=False)
    stats.invalidate()
    s = stats.site_stats()
    r = guest().get("/")
    assert f"Browse {s['open_jobs']:,} live jobs" in r.text
    assert f'<div class="val">{s["companies_active"]}</div><div class="lbl">companies</div>' in r.text
    # the hero preview is a labelled sample, never the user's data
    assert 'class="stamp">Sample</span>' in r.text


def test_templates_have_no_hardcoded_counts_or_old_brand():
    for p in TEMPLATES.rglob("*.html"):
        t = p.read_text()
        assert "Trackboard" not in t, p.name
        for bad in ("10,800", "10,862", "10877", "347 LESSONS", "26 PATTERNS", "63 feeds", "80%", "85%"):
            assert bad not in t, f"{p.name} contains {bad}"


def test_multi_factor_refuses_to_fabricate():
    from trackboard.tailor import calculate_multi_factor_fit

    mf = calculate_multi_factor_fit("", "")
    assert mf["overall"] is None and mf["confidence_tier"] == "UNSCORED"


def test_public_jobs_default_filter_hides_non_engineering():
    from trackboard import jobs, listing

    db.migrate(verbose=False)
    titles = ["Sales Associate", "Business Development Representative", "Business Insurance Account Executive",
              "HR Consultant", "Retirement Compliance Specialist", "Sales Onboarding Advocate", "Sales Operations Analyst",
              "Enterprise Account Executive - West", "Audio–Video Editor (Dubbing & Localization)", "GTM Insights & Operations"]
    for t in titles:
        jobs.upsert({"company_name": "TruthCo", "title": t, "description_md": "", "apply_url": "https://boards.greenhouse.io/x",
                     "source": "greenhouse", "location": "Bengaluru, India"})
    jobs.upsert({"company_name": "TruthCo", "title": "Backend Engineer", "description_md": "", "apply_url": "https://boards.greenhouse.io/y",
                 "source": "greenhouse", "location": "Bengaluru, India"})
    f = {"q": "truthco", "region": "india", "track": "tech", "level": "any", "source": "", "page": 1}
    got = [i["title"] for i in listing.list_jobs(f)["jobs"]]
    assert "Backend Engineer" in got
    for t in titles:
        assert t not in got, t


def test_guest_job_cards_are_unscored():
    r = guest().get("/jobs?region=all&track=all")
    assert r.status_code == 200
    assert not re.search(r"\b(STRONG|WORTH A SHOT)\b", r.text)
    assert "Unscored" in r.text or "No roles match" in r.text
