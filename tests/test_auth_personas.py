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


def test_pipeline_guest_privacy_shield():
    client = TestClient(app, follow_redirects=False)

    # 1. Guest request to /pipeline (no cookie) -> zero application rows shown, privacy banner shown
    resp = client.get("/pipeline")
    assert resp.status_code == 200
    assert "Private Candidate Application Pipeline" in resp.text
    assert "Public Visitor Mode" in resp.text
