"""Free aggregator APIs (BUILD_SPEC §7.2), injectable fetch as in ats.py."""
from __future__ import annotations

from typing import Any, Callable

Fetch = Callable[[str], Any]


def fetch_remotive(fetch: Fetch, search: str = "software") -> list[dict]:
    data = fetch(f"https://remotive.com/api/remote-jobs?search={search}")
    return [{
        "title": j.get("title", "").strip(),
        "company_name": j.get("company_name", ""),
        "location": j.get("candidate_required_location"),
        "remote": 1,
        "description_md": "",
        "apply_url": j.get("url"),
        "source": "remotive",
        "source_job_id": str(j.get("id")),
        "posted_at": (j.get("publication_date") or "")[:10] or None,
    } for j in data.get("jobs", [])]


def fetch_arbeitnow(fetch: Fetch) -> list[dict]:
    data = fetch("https://www.arbeitnow.com/api/job-board-api")
    return [{
        "title": j.get("title", "").strip(),
        "company_name": j.get("company_name", ""),
        "location": j.get("location"),
        "remote": 1 if j.get("remote") else 0,
        "description_md": "",
        "apply_url": j.get("url"),
        "source": "arbeitnow",
        "source_job_id": j.get("slug"),
        "posted_at": None,
    } for j in data.get("data", [])]


def fetch_adzuna(fetch: Fetch, app_id: str, app_key: str, what: str, where: str = "india",
                 page: int = 1) -> list[dict]:
    url = (f"https://api.adzuna.com/v1/api/jobs/in/search/{page}"
           f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
           f"&what={what.replace(' ', '%20')}&where={where}")
    data = fetch(url)
    return [{
        "title": j.get("title", "").strip(),
        "company_name": (j.get("company") or {}).get("display_name", ""),
        "location": (j.get("location") or {}).get("display_name"),
        "description_md": j.get("description", ""),
        "salary_min": int(j["salary_min"]) if j.get("salary_min") else None,
        "salary_max": int(j["salary_max"]) if j.get("salary_max") else None,
        "salary_currency": "INR",
        "apply_url": j.get("redirect_url"),
        "source": "adzuna",
        "source_job_id": str(j.get("id")),
        "posted_at": (j.get("created") or "")[:10] or None,
    } for j in data.get("results", [])]
