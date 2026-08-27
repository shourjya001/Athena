"""Job-alert email parsers (BUILD_SPEC §7.7): LinkedIn, Naukri, Indeed.

These templates change every few months. Each parser returns [] rather than
guessing when the structure is unrecognised; the caller treats zero cards from
a non-empty email as `partial` and saves the raw HTML for repair. Golden-file
tests use synthetic emails mirroring the current card structure — replace the
goldens with real saved alert emails on first live run.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from selectolax.parser import HTMLParser

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                   "trk", "trackingId", "refId", "eid", "midToken", "midSig", "trkEmail",
                   "lipi", "otpToken", "src", "sid", "xp", "px", "cid"}


def strip_tracking(url: str) -> str:
    p = urlparse(url)
    if not p.query:
        return url
    kept = [(k, v[0]) for k, v in parse_qs(p.query).items() if k not in TRACKING_PARAMS]
    q = "&".join(f"{k}={v}" for k, v in kept)
    return p._replace(query=q).geturl().rstrip("?")


def _cards_by_link(html: str, host_fragment: str) -> list[dict]:
    """Generic card extractor: anchors pointing at the portal's job pages,
    with title in the anchor text and company/location in nearby text."""
    tree = HTMLParser(html)
    seen, out = set(), []
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if host_fragment not in href:
            continue
        title = (a.text() or "").strip()
        if not title or len(title) < 4 or title.lower() in ("view job", "see all jobs", "apply now"):
            continue
        if title in seen:
            continue
        seen.add(title)
        company = location = None
        parent = a.parent
        for _ in range(3):
            if parent is None:
                break
            text = re.sub(r"\s+", " ", parent.text() or "").strip()
            m = re.search(re.escape(title) + r"\s+(.+?)(?:\s[·\-|•]\s|$)", text)
            if m and m.group(1) and m.group(1) != title:
                bits = re.split(r"\s[·\-|•]\s", text.split(title, 1)[1].strip())
                bits = [b.strip() for b in bits if b.strip()]
                if bits:
                    company = bits[0][:80]
                if len(bits) > 1:
                    location = bits[1][:80]
                break
            parent = parent.parent
        out.append({"title": title[:150], "company_name": company or "",
                    "location": location, "raw_url": href})
    return out


def parse_linkedin(html: str) -> list[dict]:
    return [{**c, "source": "alert:linkedin"} for c in _cards_by_link(html, "linkedin.com/comm/jobs/view")
            ] or [{**c, "source": "alert:linkedin"} for c in _cards_by_link(html, "linkedin.com/jobs/view")]


def parse_naukri(html: str) -> list[dict]:
    return [{**c, "source": "alert:naukri"} for c in _cards_by_link(html, "naukri.com/job-listings")]


def parse_indeed(html: str) -> list[dict]:
    cards = _cards_by_link(html, "indeed.com/rc/clk") or _cards_by_link(html, "indeed.com/viewjob")
    return [{**c, "source": "alert:indeed"} for c in cards]


PARSERS = {"linkedin": parse_linkedin, "naukri": parse_naukri, "indeed": parse_indeed}


def detect_portal(sender: str) -> str | None:
    s = sender.lower()
    if "linkedin.com" in s:
        return "linkedin"
    if "naukri.com" in s:
        return "naukri"
    if "indeed.com" in s:
        return "indeed"
    return None
