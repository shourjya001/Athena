-- 006: Add oracle_cx to companies.ats check constraint
PRAGMA foreign_keys = OFF;
CREATE TABLE IF NOT EXISTS companies_new (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  ats          TEXT NOT NULL CHECK (ats IN
                 ('greenhouse','lever','ashby','recruitee','smartrecruiters',
                  'workable','workday','darwinbox','oracle_cx')),
  board_token  TEXT NOT NULL,
  careers_url  TEXT,
  active       INTEGER NOT NULL DEFAULT 1,
  last_ok_at   TEXT,
  last_error   TEXT,
  UNIQUE (ats, board_token)
);
INSERT OR IGNORE INTO companies_new SELECT * FROM companies;
DROP TABLE IF EXISTS companies;
ALTER TABLE companies_new RENAME TO companies;
PRAGMA foreign_keys = ON;
