-- Expand the ATS allow-list to include workday, darwinbox, and workable.
-- SQLite doesn't support ALTER COLUMN, so we recreate companies with the wider constraint.

CREATE TABLE companies_new (
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

INSERT INTO companies_new SELECT * FROM companies;
DROP TABLE companies;
ALTER TABLE companies_new RENAME TO companies;
