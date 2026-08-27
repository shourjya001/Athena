-- Trackboard M1: identity + DSA content + progress + observability.
-- Job/application tables land in 003 at M4. See BUILD_SPEC.md §6.

CREATE TABLE users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  leetcode_user TEXT,
  created_at    TEXT NOT NULL,
  last_seen_at  TEXT
);

-- ---------- shared content ----------

CREATE TABLE patterns (
  id          INTEGER PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  family      TEXT NOT NULL,
  summary     TEXT NOT NULL,
  invariant   TEXT,
  cues_json   TEXT NOT NULL DEFAULT '[]',
  traps       TEXT,
  sort_order  INTEGER NOT NULL
);

CREATE TABLE problems (
  id            INTEGER PRIMARY KEY,
  leetcode_slug TEXT UNIQUE,
  external_url  TEXT,
  title         TEXT NOT NULL,
  difficulty    TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
  pattern_id    INTEGER REFERENCES patterns(id),
  is_canonical  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_problems_pattern ON problems(pattern_id, is_canonical DESC, difficulty);

CREATE TABLE problem_tags (
  problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  tag        TEXT NOT NULL,
  section    TEXT,
  ordinal    INTEGER,
  PRIMARY KEY (problem_id, tag)
);
CREATE INDEX idx_problem_tags_tag ON problem_tags(tag, ordinal);

CREATE TABLE resources (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL CHECK (kind IN ('youtube','article')),
  youtube_id   TEXT,
  url          TEXT,
  title        TEXT NOT NULL,
  channel      TEXT,
  duration_s   INTEGER,
  start_s      INTEGER NOT NULL DEFAULT 0,
  pattern_id   INTEGER REFERENCES patterns(id),
  problem_id   INTEGER REFERENCES problems(id),
  role         TEXT NOT NULL CHECK (role IN ('concept','walkthrough','contest','revision')),
  quality_rank INTEGER NOT NULL DEFAULT 100,
  UNIQUE (kind, youtube_id, problem_id, pattern_id)
);
CREATE INDEX idx_resources_pattern ON resources(pattern_id, role, quality_rank);

-- ---------- private progress ----------

CREATE TABLE attempts (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  problem_id  INTEGER NOT NULL REFERENCES problems(id),
  outcome     TEXT NOT NULL CHECK (outcome IN ('solved','solved_with_help','failed','skipped')),
  minutes     INTEGER,
  confidence  INTEGER CHECK (confidence BETWEEN 1 AND 4),
  source      TEXT NOT NULL CHECK (source IN ('user','leetcode_sync')),
  occurred_at TEXT NOT NULL
);
CREATE INDEX idx_attempts_user ON attempts(user_id, occurred_at DESC);

CREATE TABLE reviews (
  user_id        INTEGER NOT NULL REFERENCES users(id),
  problem_id     INTEGER NOT NULL REFERENCES problems(id),
  stability      REAL NOT NULL,
  difficulty     REAL NOT NULL,
  due_at         TEXT NOT NULL,
  reps           INTEGER NOT NULL DEFAULT 0,
  lapses         INTEGER NOT NULL DEFAULT 0,
  last_review_at TEXT,
  PRIMARY KEY (user_id, problem_id)
);
CREATE INDEX idx_reviews_due ON reviews(user_id, due_at);

CREATE TABLE leetcode_state (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id),
  total_solved   INTEGER,
  easy_solved    INTEGER,
  medium_solved  INTEGER,
  hard_solved    INTEGER,
  last_synced_at TEXT,
  last_error     TEXT
);

-- ---------- observability ----------

CREATE TABLE agent_runs (
  id           INTEGER PRIMARY KEY,
  agent        TEXT NOT NULL,
  user_id      INTEGER REFERENCES users(id),
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  status       TEXT NOT NULL CHECK (status IN ('running','ok','partial','failed')),
  items_in     INTEGER NOT NULL DEFAULT 0,
  items_out    INTEGER NOT NULL DEFAULT 0,
  llm_calls    INTEGER NOT NULL DEFAULT 0,
  error        TEXT,
  detail_json  TEXT
);
CREATE INDEX idx_agent_runs_recent ON agent_runs(agent, started_at DESC);
