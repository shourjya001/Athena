"""Security headers present; no inline scripts or on* handlers in any rendered page."""
from __future__ import annotations

import re
from pathlib import Path

from tests.helpers import guest

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "trackboard" / "templates"


def test_security_headers_on_html_and_static():
    c = guest()
    r = c.get("/")
    h = r.headers
    assert "Content-Security-Policy" in h and "script-src 'self'" in h["Content-Security-Policy"]
    assert "'unsafe-inline'" not in h["Content-Security-Policy"].split("style-src")[0]
    assert h["Strict-Transport-Security"].startswith("max-age=")
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in h and "Permissions-Policy" in h
    assert h["Cache-Control"] == "private, no-store"
    s = c.get("/static/app.css")
    assert s.status_code == 200 and "immutable" in s.headers["Cache-Control"]


def test_no_inline_script_or_handlers_in_templates():
    bad = []
    for p in TEMPLATES.rglob("*.html"):
        txt = p.read_text()
        if re.search(r"<script(?![^>]*type=\"application/ld\+json\")(?![^>]*\bsrc=)", txt):
            bad.append(f"{p.name}: inline <script>")
        if re.search(r"\son[a-z]+\s*=\s*[\"']", txt):
            bad.append(f"{p.name}: on*= handler")
        if "javascript:" in txt:
            bad.append(f"{p.name}: javascript: url")
    assert not bad, bad


def test_rendered_pages_have_no_inline_js():
    c = guest()
    for path in ("/", "/jobs", "/patterns/two-pointers", "/linkedin", "/login"):
        r = c.get(path)
        if r.status_code != 200:
            continue
        assert not re.search(r"<script(?![^>]*type=\"application/ld\+json\")(?![^>]*\bsrc=)", r.text), path
        assert not re.search(r"\son(click|change|submit|load)\s*=", r.text), path
