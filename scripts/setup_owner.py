#!/usr/bin/env python3
"""One-time owner setup: user row, profile answers used by the Applier,
and a sanity print of the target config. Safe to re-run."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db, users  # noqa: E402
from trackboard.settings import get_settings  # noqa: E402

ANSWERS = {
    "full_name": "Shourjya Hazra",
    "email": "shourjya001@gmail.com",
    "linkedin_url": "https://www.linkedin.com/in/shourjya-hazra-683128200/",
    # Fill these before the first Applier run — the form filler reads them:
    # "phone": "",
    # "current_location": "",
    # "years_experience": "",
    # "notice_period_days": "",
    # "current_ctc": "",
    # "expected_ctc": "",
    # "work_authorization": "Indian citizen",
    # "willing_to_relocate": "Yes",
    # "github_url": "",
}


def main() -> None:
    uid = users.ensure_user(get_settings().owner_email or "shourjya001@gmail.com",
                            "Shourjya Hazra")
    for k, v in ANSWERS.items():
        db.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?,?,?) "
                   "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
                   (uid, k, v))
    lc = input("LeetCode username (enter to skip): ").strip()
    if lc:
        db.execute("UPDATE users SET leetcode_user=? WHERE id=?", (lc, uid))
    print(f"owner user id={uid}, {len(ANSWERS)} answers saved."
          f" Uncomment and fill the remaining ANSWERS keys before using the Applier.")


if __name__ == "__main__":
    main()
