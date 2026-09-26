-- Rate limiting buckets (Phase 0.3) and a subscribers table for launch signups.
CREATE TABLE IF NOT EXISTS rate_limits (
  key          TEXT NOT NULL,
  window_start INTEGER NOT NULL,
  count        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (key, window_start)
);

CREATE TABLE IF NOT EXISTS subscribers (
  id         INTEGER PRIMARY KEY,
  email      TEXT NOT NULL UNIQUE,
  source     TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER REFERENCES users(id),
  page       TEXT,
  message    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
