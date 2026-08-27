-- M4: companies, jobs, matches (BUILD_SPEC §6.2)

CREATE TABLE companies (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  ats          TEXT NOT NULL CHECK (ats IN
                 ('greenhouse','lever','ashby','recruitee','smartrecruiters',
                  'workable','workday','darwinbox')),
  board_token  TEXT NOT NULL,
  careers_url  TEXT,
  active       INTEGER NOT NULL DEFAULT 1,
  last_ok_at   TEXT,
  last_error   TEXT,
  UNIQUE (ats, board_token)
);

CREATE TABLE jobs (
  id              INTEGER PRIMARY KEY,
  fingerprint     TEXT NOT NULL UNIQUE,
  company_id      INTEGER REFERENCES companies(id),
  company_name    TEXT NOT NULL,
  title           TEXT NOT NULL,
  location        TEXT,
  remote          INTEGER NOT NULL DEFAULT 0,
  employment_type TEXT,
  description_md  TEXT,
  salary_min      INTEGER,
  salary_max      INTEGER,
  salary_currency TEXT,
  apply_url       TEXT NOT NULL,
  source          TEXT NOT NULL,
  source_job_id   TEXT,
  posted_at       TEXT,
  posted_at_approx INTEGER NOT NULL DEFAULT 0,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  strikes         INTEGER NOT NULL DEFAULT 0,
  closed_at       TEXT
);
CREATE INDEX idx_jobs_open ON jobs(closed_at, first_seen_at DESC);
CREATE INDEX idx_jobs_source ON jobs(source, closed_at);

CREATE TABLE matches (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(id),
  job_id         INTEGER NOT NULL REFERENCES jobs(id),
  bm25_score     REAL NOT NULL,
  fit_score      INTEGER,
  verdict        TEXT CHECK (verdict IN ('strong','worth_a_shot','stretch','skip')),
  reasoning      TEXT,
  gaps_json      TEXT,
  strengths_json TEXT,
  scored_at      TEXT,
  dismissed_at   TEXT,
  UNIQUE (user_id, job_id)
);
CREATE INDEX idx_matches_queue ON matches(user_id, dismissed_at, fit_score DESC);
