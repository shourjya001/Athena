#!/usr/bin/env python3
"""Import data/problems_seed.json into problems + problem_tags. Idempotent.

This starter set (~134 problems) is hand-curated; sheet tags are best-effort.
The full Striver A2Z / NeetCode ordinal import (spec §7.6) replaces tags with
exact sections when a sheet-source JSON is supplied via --sheet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "problems_seed.json"


def main() -> int:
    payload = json.loads(DATA.read_text())
    ins = upd = 0
    with db.transaction() as conn:
        pat_ids = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM patterns")}
        for p in payload["problems"]:
            pid = pat_ids.get(p["pattern"])
            if pid is None:
                print(f"unknown pattern {p['pattern']} for {p['leetcode_slug']}", file=sys.stderr)
                return 1
            if p["difficulty"] not in ("easy", "medium", "hard"):
                print(f"bad difficulty on {p['leetcode_slug']}", file=sys.stderr)
                return 1
            row = conn.execute(
                "SELECT id FROM problems WHERE leetcode_slug=?", (p["leetcode_slug"],)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE problems SET title=?, difficulty=?, pattern_id=?, is_canonical=? WHERE id=?",
                    (p["title"], p["difficulty"], pid, p["is_canonical"], row["id"]),
                )
                prid, upd = row["id"], upd + 1
            else:
                cur = conn.execute(
                    "INSERT INTO problems (leetcode_slug, title, difficulty, pattern_id, is_canonical) "
                    "VALUES (?,?,?,?,?)",
                    (p["leetcode_slug"], p["title"], p["difficulty"], pid, p["is_canonical"]),
                )
                prid, ins = cur.lastrowid, ins + 1
            for tag in p.get("tags", []):
                conn.execute(
                    "INSERT OR IGNORE INTO problem_tags (problem_id, tag) VALUES (?,?)", (prid, tag)
                )
    print(f"problems: {ins} inserted, {upd} updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
