#!/usr/bin/env python3
"""Index the playlists and videos in config/channels.yaml into `resources`.

Needs YOUTUBE_API_KEY in .env. Costs ~1 quota unit per 50 playlist items —
effectively free against the 10k/day allowance (spec §7.4).

Mapping: `maps_to: <pattern-slug>` pins everything to that pattern;
`_auto` matches problem titles inside video titles (then that problem's
pattern); `_general` attaches to no pattern-specific page but is surfaced on
/drill. Unmatched videos in _auto mode are reported, never guessed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db  # noqa: E402
from trackboard.settings import get_settings  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
CONFIG = Path(__file__).resolve().parents[1] / "config" / "channels.yaml"


def yt(path: str, key: str, **params) -> dict:
    r = httpx.get(f"{API}/{path}", params={"key": key, **params}, timeout=20)
    r.raise_for_status()
    return r.json()


def playlist_items(playlist_id: str, key: str):
    token = None
    while True:
        data = yt("playlistItems", key, part="snippet,contentDetails",
                  playlistId=playlist_id, maxResults=50,
                  **({"pageToken": token} if token else {}))
        for it in data.get("items", []):
            sn = it["snippet"]
            yield {"video_id": it["contentDetails"]["videoId"],
                   "title": sn["title"], "channel": sn.get("channelTitle", "")}
        token = data.get("nextPageToken")
        if not token:
            return


def match_problem(video_title: str, problems: list[dict]) -> dict | None:
    low = video_title.lower()
    hits = [p for p in problems if p["title"].lower() in low]
    return max(hits, key=lambda p: len(p["title"])) if hits else None


def upsert(kind, video_id, title, channel, pattern_id, problem_id, role, quality_rank: int = 100):
    existing = db.query_one(
        "SELECT id FROM resources WHERE kind = ? AND youtube_id = ? "
        "AND (problem_id = ? OR (problem_id IS NULL AND ? IS NULL)) "
        "AND (pattern_id = ? OR (pattern_id IS NULL AND ? IS NULL))",
        (kind, video_id, problem_id, problem_id, pattern_id, pattern_id),
    )
    if existing:
        db.execute(
            "UPDATE resources SET title = ?, channel = ?, role = ?, quality_rank = ? WHERE id = ?",
            (title, channel, role, quality_rank, existing[0]),
        )
        return
    db.execute(
        "INSERT INTO resources (kind, youtube_id, title, channel, pattern_id, problem_id, role, quality_rank) "
        "VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(kind, youtube_id, problem_id, pattern_id) DO UPDATE SET "
        "title=excluded.title, channel=excluded.channel, role=excluded.role, quality_rank=excluded.quality_rank",
        (kind, video_id, title, channel, pattern_id, problem_id, role, quality_rank),
    )


def main() -> int:
    key = get_settings().youtube_api_key
    if not key:
        print("YOUTUBE_API_KEY missing in .env — nothing indexed.", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    problems = [dict(r) for r in db.query(
        "SELECT id, title, pattern_id FROM problems WHERE pattern_id IS NOT NULL")]
    pat = {r["slug"]: r["id"] for r in db.query("SELECT id, slug FROM patterns")}

    mapped = unmatched = 0
    for ch in cfg.get("channels") or []:
        for pl in ch.get("playlists", []):
            role = pl.get("role", "walkthrough")
            maps_to = pl.get("maps_to", "_auto")
            aliases: dict[str, str] = pl.get("title_aliases", {})
            general_ids: set[str] = set(pl.get("general_video_ids", []))
            # Build lookup: title (lower) -> problem row for alias validation
            prob_by_title = {p["title"].lower(): p for p in problems}
            for item in playlist_items(pl["id"], key):
                vid = item["video_id"]
                if maps_to == "_auto":
                    # 1. Hard-coded general IDs (intro / concept, no problem)
                    if vid in general_ids:
                        upsert("youtube", vid, item["title"], ch["name"], None, None, "concept")
                        mapped += 1
                    # 1b. Direct pattern slug mapping
                    elif vid in pl.get("pattern_aliases", {}):
                        p_slug = pl["pattern_aliases"][vid]
                        p_id = pat.get(p_slug)
                        upsert("youtube", vid, item["title"], ch["name"], p_id, None, role)
                        mapped += 1
                    # 2. Explicit problem alias table
                    elif vid in aliases:
                        canon = aliases[vid]
                        hit = prob_by_title.get(canon.lower())
                        if hit:
                            upsert("youtube", vid, item["title"], ch["name"],
                                   hit["pattern_id"], hit["id"], role)
                            mapped += 1
                        else:
                            print(f"WARN alias '{canon}' for {vid} not in problems DB — skipped",
                                  file=sys.stderr)
                            unmatched += 1
                    # 3. Fallback: substring auto-match
                    else:
                        hit = match_problem(item["title"], problems)
                        if hit:
                            upsert("youtube", vid, item["title"],
                                   ch["name"], hit["pattern_id"], hit["id"], role)
                            mapped += 1
                        else:
                            unmatched += 1
                elif maps_to == "_general":
                    upsert("youtube", vid, item["title"], ch["name"], None, None, role)
                    mapped += 1
                else:
                    upsert("youtube", vid, item["title"], ch["name"],
                           pat[maps_to], None, role)
                    mapped += 1
    for v in cfg.get("videos") or []:
        data = yt("videos", key, part="snippet", id=v["id"])
        items = data.get("items", [])
        if not items:
            print(f"video {v['id']} not found", file=sys.stderr)
            continue
        sn = items[0]["snippet"]
        maps_to = v.get("maps_to", "_general")
        qrank = v.get("quality_rank", 10)
        upsert("youtube", v["id"], sn["title"], sn["channelTitle"],
               pat.get(maps_to) if maps_to not in ("_general",) else None,
               None, v.get("role", "concept"), quality_rank=qrank)
        mapped += 1
    print(f"indexed: {mapped} mapped, {unmatched} unmatched (title match failed — assign manually)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
