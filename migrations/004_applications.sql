-- M5/M6: resumes, answers, applications, events, gmail state (BUILD_SPEC §6.3, §6.4)

CREATE TABLE resumes (
  id                INTEGER PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  label             TEXT NOT NULL,
  file_path         TEXT NOT NULL,
  parsed_text       TEXT,
  parse_report_json TEXT,
  is_master         INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL
);

CREATE TABLE profile_answers (
  user_id INTEGER NOT NULL REFERENCES users(id),
  key     TEXT NOT NULL,
  value   TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
);

CREATE TABLE applications (
  id            INTEGER PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  job_id        INTEGER NOT NULL REFERENCES jobs(id),
  resume_id     INTEGER REFERENCES resumes(id),
  status        TEXT NOT NULL DEFAULT 'prepared'
                CHECK (status IN ('prepared','submitted','acknowledged','screening',
                                  'assessment','interview','offer','rejected','withdrawn','ghosted')),
  status_source TEXT CHECK (status_source IN ('user','inbox_agent')),
  applied_at    TEXT,
  last_event_at TEXT,
  notes         TEXT,
  UNIQUE (user_id, job_id)
);

CREATE TABLE application_events (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  status         TEXT NOT NULL,
  occurred_at    TEXT NOT NULL,
  source         TEXT NOT NULL,
  evidence       TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX idx_events_app ON application_events(application_id, occurred_at);

CREATE TABLE gmail_state (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id),
  history_id     TEXT,
  last_synced_at TEXT,
  last_error     TEXT
);

CREATE TABLE gmail_seen (
  user_id       INTEGER NOT NULL REFERENCES users(id),
  message_id    TEXT NOT NULL,
  classified_as TEXT,
  PRIMARY KEY (user_id, message_id)
);
