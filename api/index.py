from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add src to pythonpath so trackboard modules load seamlessly
root = Path(__file__).resolve().parent.parent
src_path = str(root / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Set VERCEL flag so settings.py directs SQLite to /tmp/app.db
os.environ.setdefault("VERCEL", "1")

from trackboard import db
from trackboard.main import app

def init_serverless_db() -> None:
    """Run migrations and initial seed data if table is empty on serverless cold start."""
    try:
        db.migrate(verbose=False)

        # 1. Seed patterns if table is empty
        p_count = db.query_one("SELECT COUNT(*) as c FROM patterns")
        if not p_count or p_count["c"] == 0:
            import yaml
            cfg_paths = [
                root / "config" / "patterns.yaml",
                Path("/var/task/config/patterns.yaml"),
                Path("config/patterns.yaml").resolve(),
            ]
            cfg_file = next((p for p in cfg_paths if p.exists()), None)
            if cfg_file:
                data = yaml.safe_load(cfg_file.read_text()) or {}
                with db.transaction() as conn:
                    for p in data.get("patterns", []):
                        conn.execute(
                            "INSERT OR REPLACE INTO patterns (name, slug, family, summary, invariant, cues_json, traps, sort_order) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                p["name"],
                                p["slug"],
                                p["family"],
                                p["summary"].strip(),
                                (p.get("invariant") or "").strip() or None,
                                json.dumps(p.get("cues", [])),
                                (p.get("traps") or "").strip() or None,
                                int(p["sort_order"]),
                            ),
                        )

        # 2. Seed starter problems if table is empty
        prob_count = db.query_one("SELECT COUNT(*) as c FROM problems")
        if not prob_count or prob_count["c"] == 0:
            data_paths = [
                root / "data" / "problems_seed.json",
                Path("/var/task/data/problems_seed.json"),
                Path("data/problems_seed.json").resolve(),
            ]
            data_file = next((p for p in data_paths if p.exists()), None)
            if data_file:
                pdata = json.loads(data_file.read_text()) or {}
                with db.transaction() as conn:
                    pat_ids = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM patterns")}
                    for p in pdata.get("problems", []):
                        pid = pat_ids.get(p["pattern"])
                        if pid:
                            conn.execute(
                                "INSERT OR REPLACE INTO problems (leetcode_slug, title, difficulty, pattern_id, is_canonical, external_url) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    p["leetcode_slug"],
                                    p["title"],
                                    p["difficulty"],
                                    pid,
                                    int(p.get("is_canonical", 0)),
                                    f"https://leetcode.com/problems/{p['leetcode_slug']}/",
                                ),
                            )
    except Exception as e:
        print(f"Notice on serverless DB init: {e}", file=sys.stderr)

init_serverless_db()
