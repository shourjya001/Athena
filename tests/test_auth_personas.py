import pytest
from starlette.testclient import TestClient

from trackboard import db
from trackboard.main import app


def test_auth_page_and_personas():
    client = TestClient(app, follow_redirects=False)

    # 1. GET /login renders candidate personas and Google auth button
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Sign in to Athena" in resp.text
    assert "Continue with Google" in resp.text
    assert "Shourjya Hazra" in resp.text
    assert "Manshi Rohella" in resp.text
    assert "Prerna Rohilla" in resp.text
    assert "Public Showcase" in resp.text

    # 2. Switch to Manshi
    r_manshi = client.get("/auth/switch/manshi")
    assert r_manshi.status_code == 303
    cookie = r_manshi.headers.get("set-cookie")
    assert "trackboard_user=manshirohella21%40gmail.com" in cookie or "manshirohella21@gmail.com" in cookie

    # 3. Switch to Shourjya
    r_shourjya = client.get("/auth/switch/shourjya")
    assert r_shourjya.status_code == 303
    cookie = r_shourjya.headers.get("set-cookie")
    assert "shourjya001" in cookie

    # 4. Switch to Prerna
    r_prerna = client.get("/auth/switch/prerna")
    assert r_prerna.status_code == 303
    cookie = r_prerna.headers.get("set-cookie")
    assert "prernarohilla050802" in cookie

    # 5. Switch to Guest (clears cookie)
    r_guest = client.get("/auth/switch/guest")
    assert r_guest.status_code == 303

    # 6. Google Auth redirect fallback when not configured
    r_google = client.get("/auth/google")
    assert r_google.status_code == 303
    assert "/login" in r_google.headers.get("location")


def test_protected_routes_require_authentication():
    client = TestClient(app, follow_redirects=False)

    # 1. Guest request to /profile MUST redirect to /login
    r_prof = client.get("/profile")
    assert r_prof.status_code == 303
    assert "/login" in r_prof.headers.get("location")
    assert "next=%2Fprofile" in r_prof.headers.get("location") or "next=/profile" in r_prof.headers.get("location")

    # 2. Guest request to /pipeline MUST redirect to /login
    r_pipe = client.get("/pipeline")
    assert r_pipe.status_code == 303
    assert "/login" in r_pipe.headers.get("location")

    # 3. Guest request to /jobs/1/tailor MUST redirect to /login
    r_tailor = client.get("/jobs/1/tailor")
    assert r_tailor.status_code == 303
    assert "/login" in r_tailor.headers.get("location")

    # 4. Authenticated user can access /profile
    client_auth = TestClient(app, follow_redirects=False, cookies={"trackboard_user": "shourjya001@gmail.com"})
    r_auth_prof = client_auth.get("/profile")
    assert r_auth_prof.status_code == 200
    assert "Shourjya" in r_auth_prof.text

    # 5. Authenticated user can access /pipeline
    r_auth_pipe = client_auth.get("/pipeline")
    assert r_auth_pipe.status_code == 200

    # 6. Public routes are accessible without auth
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "ATHENA CAREER OS" in r_home.text

    r_jobs = client.get("/jobs")
    assert r_jobs.status_code == 200
