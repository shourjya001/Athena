from __future__ import annotations

import os
import shutil
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
    """Initialize /tmp/app.db from pre-seeded database or migrations on serverless boot."""
    try:
        tmp_db = Path("/tmp/app.db")
        seed_candidates = [
            root / "data" / "seed_data.db",
            Path("/var/task/data/seed_data.db"),
            Path("data/seed_data.db").resolve(),
        ]
        seed_db = next((p for p in seed_candidates if p.exists() and p.stat().st_size > 0), None)

        if not tmp_db.exists() or tmp_db.stat().st_size == 0:
            if seed_db:
                shutil.copyfile(seed_db, tmp_db)
                print(f"Initialized /tmp/app.db from {seed_db} ({seed_db.stat().st_size // 1024} KB)")
            else:
                db.migrate(verbose=False)
        else:
            # Ensure any new migrations are applied
            db.migrate(verbose=False)
    except Exception as e:
        print(f"Notice on serverless DB init: {e}", file=sys.stderr)

init_serverless_db()
