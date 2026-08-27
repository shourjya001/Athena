#!/usr/bin/env python3
"""Resolve careers URLs in config/companies.yaml to (ats, board_token)
and write results into the companies table (BUILD_SPEC §7.1)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db  # noqa: E402
from trackboard.settings import get_settings  # noqa: E402

PATTERNS = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9]+)")),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([a-z0-9]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9\-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9\-\.%]+)")),
    ("recruitee", re.compile(r"([a-z0-9\-]+)\.recruitee\.com")),
    ("smartrecruiters", re.compile(r"careers\.smartrecruiters\.com/([A-Za-z0-9]+)")),
    ("workday", re.compile(r"([a-z0-9\-]+\.wd\d+\.myworkdayjobs\.com)/([A-Za-z0-9\-_]+)")),
    ("darwinbox", re.compile(r"([a-z0-9\-]+)\.darwinbox\.com/ms/candidate")),
]

CONFIG = Path(__file__).resolve().parents[1] / "config" / "companies.yaml"


def detect(html: str) -> tuple[str, str] | None:
    for ats, rx in PATTERNS:
        m = rx.search(html)
        if m:
            if m.lastindex == 2:
                return ats, f"{m.group(1)}/{m.group(2)}"
            return ats, m.group(1)
    return None


def main() -> int:
    if not CONFIG.exists():
        print("config/companies.yaml missing — create it with a `companies:` list "
              "of {name, careers_url} entries (seed list: BUILD_SPEC §7.1).", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    ua = get_settings().user_agent
    found = missed = 0
    for c in cfg.get("companies", []):
        if c.get("ats") and c.get("token"):
            hit = (c["ats"], c["token"])
        else:
            try:
                r = httpx.get(c["careers_url"], headers={"User-Agent": ua},
                              timeout=20, follow_redirects=True)
                hit = detect(str(r.url) + "\n" + r.text)
            except Exception as e:
                print(f"  {c['name']}: fetch failed ({e})")
                missed += 1
                continue
        if hit:
            ats, token = hit
            db.execute(
                "INSERT INTO companies (name, ats, board_token, careers_url) VALUES (?,?,?,?) "
                "ON CONFLICT(ats, board_token) DO UPDATE SET name=excluded.name, "
                "careers_url=excluded.careers_url, active=1",
                (c["name"], ats, token, c["careers_url"]))
            print(f"  {c['name']}: {ats} / {token}")
            found += 1
        else:
            print(f"  {c['name']}: no known ATS pattern")
            missed += 1
    print(f"resolved {found}, unresolved {missed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
