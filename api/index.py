from __future__ import annotations

import sys
from pathlib import Path

# Add src to pythonpath so trackboard modules load seamlessly
root = Path(__file__).resolve().parent.parent
src_path = str(root / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from trackboard import db
from trackboard.main import app

# Ensure migrations and initial data are ready on cold start
try:
    db.migrate(verbose=False)
except Exception as e:
    print(f"Migration note on serverless boot: {e}")
