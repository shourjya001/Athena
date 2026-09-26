"""Route map: expected status for guest and user; SEO endpoints; branded 404."""
from __future__ import annotations

from trackboard import db
from tests.helpers import guest, signed_in


def test_sitemap_and_robots():
    c = guest()
    r = c.get("/robots.txt")
    assert r.status_code == 200 and "Sitemap:" in r.text and "Disallow: /profile" in r.text
    s = c.get("/sitemap.xml")
    assert s.status_code == 200 and "<urlset" in s.text and "/patterns" in s.text


def test_unknown_path_returns_branded_404():
    r = guest().get("/definitely-not-a-page")
    assert r.status_code == 404 and "That page doesn't exist." in r.text


def test_signed_in_pages_render():
    c = signed_in()
    for path in ("/profile", "/pipeline", "/practice", "/drill", "/"):
        r = c.get(path)
        assert r.status_code == 200, path
    assert "Your desk" in c.get("/").text


def test_jobs_htmx_partial_and_pagination():
    c = guest()
    r = c.get("/jobs?region=all&track=all&page=1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "<html" not in r.text and "results-head" in r.text


def test_per_page_meta_is_unique():
    c = guest()
    descs = set()
    for path in ("/", "/jobs", "/prep", "/patterns", "/about"):
        t = c.get(path).text
        d = t.split('<meta name="description" content="')[1].split('"')[0]
        descs.add(d)
        assert '<meta property="og:image"' in t
    assert len(descs) == 5


def test_mark_applied_moves_job_to_pipeline():
    from trackboard import jobs

    db.migrate(verbose=False)
    jobs.upsert({"company_name": "FlowCo", "title": "Backend Engineer", "description_md": "", "apply_url": "https://boards.greenhouse.io/f", "source": "greenhouse"})
    row = db.query_one("SELECT id FROM jobs WHERE company_name='FlowCo'")
    c = signed_in("flow@example.com")
    r = c.post(f"/a/jobs/{row['id']}/mark-applied", data={"csrf_token": c.csrf})
    assert r.status_code == 303 and r.headers["location"] == "/pipeline"
    assert "FlowCo" in c.get("/pipeline").text
    assert db.query_one("SELECT status FROM applications WHERE user_id=? AND job_id=?", (c.uid, row["id"]))["status"] == "submitted"


def test_chain_from_env_exists_and_feedback_works():
    from trackboard import llm

    assert hasattr(llm.Chain, "from_env") and callable(llm.Chain.from_env)
    c = signed_in("fb@example.com")
    r = c.post("/a/feedback", data={"csrf_token": c.csrf, "message": "The bottom nav overlaps on my phone", "page": "/jobs"})
    assert r.status_code == 303
    assert db.query_one("SELECT message FROM feedback WHERE user_id=?", (c.uid,))["message"].startswith("The bottom nav")


def test_json_ld_present_on_home_and_about():
    c = guest()
    assert '"@type":"WebSite"' in c.get("/").text
    assert '"@type":"Person"' in c.get("/about").text
