#!/usr/bin/env python3
"""Seed the resources table from data/resources_seed.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "resources_seed.json"


def main() -> int:
    if not DATA_FILE.exists():
        print(f"File not found: {DATA_FILE}", file=sys.stderr)
        return 1

    with open(DATA_FILE) as f:
        resources = json.load(f)

    inserted = updated = 0
    with db.transaction() as conn:
        for r in resources:
            existing = conn.execute(
                "SELECT id FROM resources WHERE kind = ? AND youtube_id = ? "
                "AND (problem_id = ? OR (problem_id IS NULL AND ? IS NULL)) "
                "AND (pattern_id = ? OR (pattern_id IS NULL AND ? IS NULL))",
                (r["kind"], r["youtube_id"], r.get("problem_id"), r.get("problem_id"), r.get("pattern_id"), r.get("pattern_id")),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE resources SET title = ?, channel = ?, role = ?, quality_rank = ? WHERE id = ?",
                    (r["title"], r.get("channel"), r.get("role", "walkthrough"), r.get("quality_rank", 100), existing["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO resources (kind, youtube_id, title, channel, pattern_id, problem_id, role, quality_rank) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["kind"], r["youtube_id"], r["title"], r.get("channel"), r.get("pattern_id"), r.get("problem_id"), r.get("role", "walkthrough"), r.get("quality_rank", 100)),
                )
                inserted += 1

    print(f"resources: {inserted} inserted, {updated} updated ({len(resources)} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
