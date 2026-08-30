import sqlite3
from pathlib import Path

def fix_db(db_path: Path):
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        # 1. Fix User 1: Shourjya
        conn.execute("UPDATE users SET display_name='Shourjya Hazra', leetcode_user='shourjya001' WHERE email='shourjya001@gmail.com'")
        u1 = conn.execute("SELECT id FROM users WHERE email='shourjya001@gmail.com'").fetchone()
        if u1:
            uid1 = u1["id"]
            shourjya_answers = {
                "titles": "Backend Engineer, SDE 2, Distributed Systems Engineer, Python Developer",
                "keywords": "Python, FastAPI, Kafka, Go, PostgreSQL, Docker, Redis, Kubernetes, Distributed Systems",
                "locations": "Bengaluru, Mumbai, Remote, India",
                "min_ctc": "25 LPA",
                "experience_years": "2",
                "track": "tech"
            }
            for k, v in shourjya_answers.items():
                conn.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value", (uid1, k, v))

        # 2. Fix User 2: Manshi Rohella (Tech & AI)
        conn.execute("INSERT INTO users (email, display_name, leetcode_user, created_at, last_seen_at) VALUES ('manshirohella21@gmail.com', 'Manshi Rohella', 'manshi_codes', datetime('now'), datetime('now')) ON CONFLICT(email) DO UPDATE SET display_name='Manshi Rohella', leetcode_user='manshi_codes'")
        u2 = conn.execute("SELECT id FROM users WHERE email='manshirohella21@gmail.com'").fetchone()
        if u2:
            uid2 = u2["id"]
            manshi_answers = {
                "titles": "SDE, Backend Engineer, Full Stack Developer, AI Engineer",
                "keywords": "Python, FastAPI, PyTorch, Docker, PostgreSQL, LangChain, React, LLM",
                "locations": "Bengaluru, Mumbai, Remote, India",
                "min_ctc": "20 LPA",
                "experience_years": "2",
                "track": "tech"
            }
            for k, v in manshi_answers.items():
                conn.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value", (uid2, k, v))

        # 3. Fix User 3: Prerna Rohilla (Business & Operations)
        conn.execute("INSERT INTO users (email, display_name, created_at, last_seen_at) VALUES ('prernarohilla050802@gmail.com', 'Prerna Rohilla', datetime('now'), datetime('now')) ON CONFLICT(email) DO UPDATE SET display_name='Prerna Rohilla'")
        u3 = conn.execute("SELECT id FROM users WHERE email='prernarohilla050802@gmail.com'").fetchone()
        if u3:
            uid3 = u3["id"]
            prerna_answers = {
                "titles": "Operations Associate, Banking Operations Specialist, Operations Analyst, Business Analyst",
                "keywords": "Banking Operations, Settlement, Clearing, KYC, AML, Core Banking, Finacle, Operations, SQL, Excel",
                "locations": "Bengaluru, Mumbai, Gurugram, India",
                "min_ctc": "15 LPA",
                "experience_years": "2",
                "track": "business"
            }
            for k, v in prerna_answers.items():
                conn.execute("INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value", (uid3, k, v))

    print(f"✓ Fixed candidate profiles in {db_path}")

if __name__ == "__main__":
    local_db = Path.home() / ".trackboard" / "app.db"
    seed_db = Path(__file__).resolve().parents[1] / "data" / "seed_data.db"
    fix_db(local_db)
    fix_db(seed_db)
