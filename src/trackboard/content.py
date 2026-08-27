"""Read queries for the DSA content surfaces."""
from __future__ import annotations

import json
from typing import Any

from . import db


def _pattern(row) -> dict[str, Any]:
    d = dict(row)
    d["cues"] = json.loads(d.pop("cues_json") or "[]")
    return d


def list_patterns(user_id: int | None = None) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM problems x WHERE x.pattern_id = p.id) AS problem_count,
               (SELECT COUNT(*) FROM resources r WHERE r.pattern_id = p.id) AS resource_count,
               (SELECT COUNT(DISTINCT a.problem_id)
                  FROM attempts a JOIN problems x ON x.id = a.problem_id
                 WHERE x.pattern_id = p.id AND a.user_id = ?
                   AND a.outcome IN ('solved','solved_with_help')) AS solved_count
          FROM patterns p
         ORDER BY p.sort_order
        """,
        (user_id or -1,),
    )
    return [_pattern(r) for r in rows]


def get_pattern(slug: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM patterns WHERE slug = ?", (slug,))
    return _pattern(row) if row else None


def pattern_problems(pattern_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT pr.*,
               (SELECT GROUP_CONCAT(t.tag) FROM problem_tags t
                 WHERE t.problem_id = pr.id) AS tags,
               (SELECT COUNT(*) FROM attempts a
                 WHERE a.problem_id = pr.id AND a.user_id = ?
                   AND a.outcome IN ('solved','solved_with_help')) AS solved
          FROM problems pr
         WHERE pr.pattern_id = ?
         ORDER BY pr.is_canonical DESC,
                  CASE pr.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                  pr.title
        """,
        (user_id or -1, pattern_id),
    )
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        d["url"] = (
            f"https://leetcode.com/problems/{d['leetcode_slug']}/"
            if d.get("leetcode_slug")
            else d.get("external_url")
        )
        out.append(d)
    return out


def pattern_resources(pattern_id: int) -> dict[str, list[dict[str, Any]]]:
    rows = db.query(
        "SELECT * FROM resources WHERE pattern_id = ? ORDER BY role, quality_rank, id",
        (pattern_id,),
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        if d["kind"] == "youtube" and d.get("youtube_id"):
            d["embed"] = f"https://www.youtube-nocookie.com/embed/{d['youtube_id']}"
            if d.get("start_s"):
                d["embed"] += f"?start={d['start_s']}"
            d["watch"] = f"https://www.youtube.com/watch?v={d['youtube_id']}"
        grouped.setdefault(d["role"], []).append(d)
    return grouped


def general_resources() -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM resources WHERE pattern_id IS NULL AND problem_id IS NULL AND role = 'concept' "
        "ORDER BY quality_rank, id",
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d["kind"] == "youtube" and d.get("youtube_id"):
            d["embed"] = f"https://www.youtube-nocookie.com/embed/{d['youtube_id']}"
            if d.get("start_s"):
                d["embed"] += f"?start={d['start_s']}"
            d["watch"] = f"https://www.youtube.com/watch?v={d['youtube_id']}"
        out.append(d)
    return out


def content_health() -> dict[str, int]:
    def n(sql: str) -> int:
        row = db.query_one(sql)
        return int(row[0]) if row else 0

    return {
        "patterns": n("SELECT COUNT(*) FROM patterns"),
        "problems": n("SELECT COUNT(*) FROM problems"),
        "mapped": n("SELECT COUNT(*) FROM problems WHERE pattern_id IS NOT NULL"),
        "resources": n("SELECT COUNT(*) FROM resources"),
        "channels": n("SELECT COUNT(DISTINCT channel) FROM resources WHERE channel IS NOT NULL"),
        "sheets": n("SELECT COUNT(DISTINCT tag) FROM problem_tags"),
    }
