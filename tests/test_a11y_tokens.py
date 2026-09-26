"""WCAG contrast for the token pairs in both themes, plus basic landmarks."""
from __future__ import annotations

import re
from pathlib import Path

from tests.helpers import guest

CSS = (Path(__file__).resolve().parents[1] / "src/trackboard/static/app.css").read_text()


def _lum(hexc: str) -> float:
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-fA-F]{6})", block))


def _blocks():
    dark = CSS[CSS.index(":root{"):CSS.index("@media (prefers-color-scheme:light)")]
    light = CSS[CSS.index(':root[data-theme="light"]'):CSS.index("/* ---------- reset")]
    return {"dark": _tokens(dark), "light": _tokens(light)}


def test_text_contrast_meets_aa_in_both_themes():
    for theme, t in _blocks().items():
        for fg in ("text", "text-2"):
            for bg in ("bg", "bg-2", "surface", "surface-2"):
                assert _ratio(t[fg], t[bg]) >= 4.5, f"{theme}: {fg} on {bg} = {_ratio(t[fg], t[bg]):.2f}"
        assert _ratio(t["text-3"], t["bg"]) >= 3.0, theme
        assert _ratio(t["accent-ink"], t["accent"]) >= 4.5, theme


def test_landmarks_and_skip_link():
    r = guest().get("/")
    assert '<a class="skip" href="#main">' in r.text
    assert '<main id="main"' in r.text and "<header" in r.text and "<footer" in r.text
    assert r.text.count("<h1") == 1
    assert 'aria-label="Primary"' in r.text and 'aria-label="Primary mobile"' in r.text
