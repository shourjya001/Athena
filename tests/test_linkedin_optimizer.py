import pytest
from starlette.testclient import TestClient

from trackboard.main import app
from trackboard.linkedin_optimizer import (
    scan_buzzwords,
    calculate_ai_visibility,
    audit_and_optimize_profile,
    generate_job_targeted_linkedin_seo,
)


def test_scan_buzzwords_flags_generic_terms():
    text = "I am a results-driven and passionate professional leveraging synergies to build cutting-edge solutions."
    flags = scan_buzzwords(text)
    flagged_words = [f["buzzword"] for f in flags]
    assert "results-driven" in flagged_words
    assert "passionate" in " ".join(flagged_words)
    assert any("synerg" in w for w in flagged_words)
    assert "cutting-edge" in flagged_words
    assert len(flags) >= 4


def test_calculate_ai_visibility_8_checks():
    headline = "Senior Backend Engineer | High-Scale Distributed Systems & Kafka"
    about = (
        "Architects distributed microservices and payments infrastructure for high-growth FinTech. "
        "Engineered systems processing 15M daily events with sub-40ms latency. "
        "Ex-Razorpay engineer, contributor to open-source Kafka connectors. "
        "If you are hiring senior backend talent, reach out at github.com/user."
    )
    res = calculate_ai_visibility(headline, about, "Razorpay | Senior Engineer | 2024", "https://linkedin.com/in/john-smith-dev")
    assert res["max_score"] == 8
    assert res["score"] >= 5
    assert len(res["checks"]) == 8
    check_names = [c["name"] for c in res["checks"]]
    assert "Entity Clarity" in check_names
    assert "AI Visibility" not in check_names  # is overall category
    assert "Direct Answer Language" in check_names


def test_audit_and_optimize_profile_full_package():
    headline = "Software Engineer at Tech Corp"
    about = "I am a results-oriented developer passionate about building web apps and solving problems."
    exp = "Company A | SDE | Worked on backend APIs and databases."
    res = audit_and_optimize_profile(headline, about, exp)

    assert "audit_scores" in res
    assert res["audit_scores"]["total"] <= 50
    assert len(res["priority_fixes"]) == 5
    assert len(res["buzzwords_found"]) >= 2
    assert "variant_a" in res["headlines"]
    assert "variant_b" in res["headlines"]
    assert "variant_c" in res["headlines"]
    assert len(res["headlines"]["variant_a"]) <= 220
    assert "rewrite" in res["about"]
    assert res["about"]["word_count"] <= 220
    assert len(res["experience_bullets"]) >= 1
    assert "score" in res["ai_visibility"]
    assert len(res["sample_posts"]) >= 2


def test_generate_job_targeted_linkedin_seo():
    jd = "We need an engineer experienced with Python, FastAPI, Redis caching, Kafka message brokers, and PostgreSQL database performance."
    seo = generate_job_targeted_linkedin_seo(
        job_title="Backend Engineer",
        company="Razorpay",
        jd_text=jd
    )
    assert "seo_headline" in seo
    assert "keywords" in seo
    assert any("Python" in k or "Kafka" in k or "Redis" in k for k in seo["keywords"])
    assert "boolean_search" in seo
    assert "about_seo_snippet" in seo
    assert "ai_citation_preview" in seo


def test_linkedin_routes():
    client = TestClient(app, follow_redirects=False)

    # 1. GET /linkedin
    r1 = client.get("/linkedin")
    assert r1.status_code == 200
    assert "LinkedIn Profile &amp; AI Visibility Optimizer" in r1.text
    # Guests can read the form but the submit is disabled and the POST is gated
    assert 'id="li-submit"' in r1.text and "disabled" in r1.text
    r_guest = client.post("/a/linkedin/optimize", json={"headline": "x"})
    assert r_guest.status_code == 303 and "/login" in r_guest.headers["location"]

    # 2. POST /a/linkedin/optimize as a signed-in user with a CSRF token
    from tests.helpers import signed_in
    client = signed_in()
    payload = {
        "headline": "Fullstack Developer",
        "about": "Passionate developer building apps with results-driven approach.",
        "experiences": "Built REST APIs in Node and MongoDB.",
        "target_audience": "Tech Recruiters",
        "goal": "job seeker",
        "linkedin_url": "https://linkedin.com/in/testdev",
        "mode": "standard"
    }
    r2 = client.post("/a/linkedin/optimize", json=payload, headers={"X-CSRF-Token": client.csrf})
    assert r2.status_code == 200
    data = r2.json()
    assert data["ok"] is True
    assert "headlines" in data["data"]
    assert "ai_visibility" in data["data"]

    # 3. POST /a/jobs/{job_id}/linkedin-seo
    from trackboard import db, jobs
    row = db.query_one("SELECT id FROM jobs LIMIT 1")
    if not row:
        jobs.upsert({
            "company_name": "Acme",
            "title": "Backend Engineer",
            "description_md": "Python and Kafka",
            "apply_url": "https://acme/apply",
            "source": "greenhouse"
        })
        row = db.query_one("SELECT id FROM jobs LIMIT 1")

    r3 = client.post(f"/a/jobs/{row['id']}/linkedin-seo", headers={"X-CSRF-Token": client.csrf})
    assert r3.status_code == 200
    seo_data = r3.json()
    assert seo_data["ok"] is True
    assert "seo_headline" in seo_data["data"]


