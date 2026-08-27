"""Public ATS board fetchers (BUILD_SPEC §7.1). All take an injectable
`fetch(url) -> dict|list` so tests never touch the network; the default uses
httpx with the app User-Agent."""
from __future__ import annotations

import re
from typing import Any, Callable

import httpx

Fetch = Callable[[str], Any]


def default_fetch(user_agent: str) -> Fetch:
    def _fetch(url: str) -> Any:
        r = httpx.get(url, headers={"User-Agent": user_agent}, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    return _fetch


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def fetch_greenhouse(token: str, fetch: Fetch) -> list[dict]:
    data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title", "").strip(),
            "location": (j.get("location") or {}).get("name"),
            "description_md": _strip_html(j.get("content")),
            "apply_url": j.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{j.get('id')}",
            "source": "greenhouse",
            "source_job_id": str(j.get("id")),
            "posted_at": (j.get("updated_at") or "")[:10] or None,
        })
    return out


def fetch_lever(token: str, fetch: Fetch) -> list[dict]:
    data = fetch(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        out.append({
            "title": j.get("text", "").strip(),
            "location": cats.get("location"),
            "description_md": _strip_html(j.get("descriptionPlain") or j.get("description")),
            "apply_url": j.get("hostedUrl") or j.get("applyUrl"),
            "source": "lever",
            "source_job_id": j.get("id"),
            "posted_at": None,
        })
    return out


def fetch_ashby(token: str, fetch: Fetch) -> list[dict]:
    data = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title", "").strip(),
            "location": j.get("location"),
            "remote": 1 if j.get("isRemote") else 0,
            "description_md": _strip_html(j.get("descriptionHtml")) or (j.get("descriptionPlain") or ""),
            "apply_url": j.get("jobUrl") or j.get("applyUrl"),
            "source": "ashby",
            "source_job_id": j.get("id"),
            "posted_at": (j.get("publishedAt") or "")[:10] or None,
        })
    return out


def fetch_workday(token: str, fetch: Fetch | None = None) -> list[dict]:
    if "/" not in token:
        return []
    parts = token.split("/", 1)
    host = parts[0]
    site = parts[1]
    if ".myworkdayjobs.com" not in host:
        host = f"{host}.myworkdayjobs.com"
    tenant = host.split(".")[0]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    postings = []
    for offset in (0, 20, 40, 60, 80):
        try:
            r = httpx.post(
                api,
                json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": "India"},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=12,
            )
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("jobPostings", [])
            postings.extend(items)
            if len(items) < 20 or len(postings) >= 100:
                break
        except Exception:
            break
    out = []
    for item in postings:
        path = item.get("externalPath", "")
        out.append({
            "title": (item.get("title") or "").strip(),
            "location": item.get("locationsText"),
            "remote": 1 if "remote" in (item.get("locationsText") or "").lower() else 0,
            "description_md": "",
            "apply_url": f"https://{host}{path}",
            "source": "workday",
            "source_job_id": path,
            "posted_at": item.get("postedOn"),
        })
    return out


def fetch_oracle_cx(token: str, fetch: Fetch | None = None) -> list[dict]:
    """Fetch jobs from Oracle Recruiting Cloud Candidate Experience (e.g. American Express)."""
    if "/" not in token:
        host, site = "egug.fa.us2.oraclecloud.com", token
    else:
        host, site = token.split("/", 1)
    api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    out = []
    for offset in (0, 50, 100):
        try:
            r = httpx.get(
                api,
                params={
                    "onlyData": "true",
                    "expand": "requisitionList",
                    "finder": f"findReqs;siteNumber={site},limit=50,offset={offset}",
                },
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=12,
            )
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("items", [{}])[0].get("requisitionList", [])
            for it in items:
                loc = it.get("PrimaryLocation") or ""
                # Keep India and remote opportunities
                if any(x in loc for x in ("India", "Bengaluru", "Bangalore", "Mumbai", "Gurugram", "Chennai", "Hyderabad", "Remote")):
                    req_id = str(it.get("Id") or "")
                    title = (it.get("Title") or "").strip()
                    desc = it.get("ExternalResponsibilitiesStr") or it.get("ExternalQualificationsStr") or ""
                    out.append({
                        "title": title,
                        "location": loc,
                        "remote": 1 if "remote" in loc.lower() else 0,
                        "description_md": desc,
                        "apply_url": f"https://careers.americanexpress.com/en/sites/{site}/job/{req_id}",
                        "source": "oracle_cx",
                        "source_job_id": req_id,
                        "posted_at": it.get("PostedDate"),
                    })
            if len(items) < 50 or len(out) >= 100:
                break
        except Exception:
            break
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workday": fetch_workday,
    "oracle_cx": fetch_oracle_cx,
}

