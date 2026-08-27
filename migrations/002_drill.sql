-- Pattern-recognition track (BUILD_SPEC §8.8.3). Kept separate from `attempts`
-- because recognition and implementation are different skills.

CREATE TABLE drill_attempts (
  id                INTEGER PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  problem_id        INTEGER NOT NULL REFERENCES problems(id),
  chosen_pattern_id INTEGER REFERENCES patterns(id),
  correct           INTEGER NOT NULL,
  seconds           INTEGER,
  occurred_at       TEXT NOT NULL
);
CREATE INDEX idx_drill_user ON drill_attempts(user_id, occurred_at DESC);

CREATE TABLE pattern_reviews (
  user_id        INTEGER NOT NULL REFERENCES users(id),
  pattern_id     INTEGER NOT NULL REFERENCES patterns(id),
  stability      REAL NOT NULL,
  difficulty     REAL NOT NULL,
  due_at         TEXT NOT NULL,
  reps           INTEGER NOT NULL DEFAULT 0,
  lapses         INTEGER NOT NULL DEFAULT 0,
  last_review_at TEXT,
  PRIMARY KEY (user_id, pattern_id)
);
