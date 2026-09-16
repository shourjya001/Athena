import pytest
from starlette.testclient import TestClient

from trackboard import db
from trackboard.main import app


def test_auth_page_and_personas():
    client = TestClient(app, follow_redirects=False)

    # 1. GET /login renders Google OAuth interface and zero backdoor switch cards
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Sign in to Athena" in resp.text
    assert "Sign in with Google" in resp.text
    # Backdoors must not exist on login page
    assert "1-Click Switch" not in resp.text

    # 2. Backdoor route /auth/switch/{persona} is completely removed (returns 404)
    r_switch = client.get("/auth/switch/shourjya")
    assert r_switch.status_code == 404

    r_switch_manshi = client.get("/auth/switch/manshi")
    assert r_switch_manshi.status_code == 404

    # 3. GET /logout clears the session cookie
    r_logout = client.get("/logout")
    assert r_logout.status_code == 303
    assert "/login" in r_logout.headers.get("location")

    # 4. Google Auth redirect fallback when not configured
    r_google = client.get("/auth/google")
    assert r_google.status_code == 303
    assert "/login" in r_google.headers.get("location")

    # 5. POST /auth/google/verify rejects empty token
    r_verify = client.post("/auth/google/verify", data={"credential": ""})
    assert r_verify.status_code == 303
    assert "error=Missing+Google+credential+token" in r_verify.headers.get("location")


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
    assert "Shourjya" in r_auth_prof.text or "shourjya001" in r_auth_prof.text

    # 5. Authenticated user can access /pipeline
    r_auth_pipe = client_auth.get("/pipeline")
    assert r_auth_pipe.status_code == 200

    # 6. Public routes are accessible without auth
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "ATHENA CAREER OS" in r_home.text

    r_jobs = client.get("/jobs")
    assert r_jobs.status_code == 200
