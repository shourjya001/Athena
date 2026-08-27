"""LeetCode public GraphQL (BUILD_SPEC §7.5). Unauthenticated, polled gently.

`fetch` is injectable so tests never touch the network.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

GQL_URL = "https://leetcode.com/graphql"

SUMMARY_Q = """
query userSummary($username: String!) {
  matchedUser(username: $username) {
    username
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
}"""

RECENT_Q = """
query recentAc($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id title titleSlug timestamp
  }
}"""

Fetch = Callable[[str, dict], dict]


def default_fetch(user_agent: str) -> Fetch:
    def _fetch(query: str, variables: dict) -> dict:
        r = httpx.post(
            GQL_URL,
            json={"query": query, "variables": variables},
            headers={"User-Agent": user_agent, "Referer": "https://leetcode.com"},
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"])[:300])
        return payload["data"]
    return _fetch


def user_summary(username: str, fetch: Fetch) -> dict[str, int]:
    data = fetch(SUMMARY_Q, {"username": username})
    user = data.get("matchedUser")
    if not user:
        raise RuntimeError(f"leetcode user not found: {username}")
    out = {"all": 0, "easy": 0, "medium": 0, "hard": 0}
    for row in user["submitStatsGlobal"]["acSubmissionNum"]:
        out[row["difficulty"].lower()] = int(row["count"])
    return out


def recent_accepted(username: str, fetch: Fetch, limit: int = 20) -> list[dict[str, Any]]:
    data = fetch(RECENT_Q, {"username": username, "limit": limit})
    return list(data.get("recentAcSubmissionList") or [])
