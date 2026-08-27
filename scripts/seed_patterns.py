#!/usr/bin/env python3
"""Load config/patterns.yaml into the patterns table. Idempotent — re-run freely."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "config" / "patterns.yaml"


def main() -> int:
    data = yaml.safe_load(CONFIG.read_text())
    pats = data.get("patterns", [])
    if not pats:
        print("no patterns found in config", file=sys.stderr)
        return 1

    seen, inserted, updated = set(), 0, 0
    with db.transaction() as conn:
        for p in pats:
            slug = p["slug"]
            if slug in seen:
                print(f"duplicate slug: {slug}", file=sys.stderr)
                return 1
            seen.add(slug)
            row = conn.execute("SELECT id FROM patterns WHERE slug = ?", (slug,)).fetchone()
            payload = (
                p["name"], p["family"], p["summary"].strip(),
                (p.get("invariant") or "").strip() or None,
                json.dumps(p.get("cues", [])),
                (p.get("traps") or "").strip() or None,
                int(p["sort_order"]),
            )
            if row:
                conn.execute(
                    "UPDATE patterns SET name=?, family=?, summary=?, invariant=?, "
                    "cues_json=?, traps=?, sort_order=? WHERE slug=?",
                    (*payload, slug),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO patterns (name, family, summary, invariant, cues_json, "
                    "traps, sort_order, slug) VALUES (?,?,?,?,?,?,?,?)",
                    (*payload, slug),
                )
                inserted += 1

    print(f"patterns: {inserted} inserted, {updated} updated ({len(pats)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
