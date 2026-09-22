-- 007_digest_rotation.sql
-- Track digest dispatch timestamps to rotate jobs and ensure fresh daily recommendations

ALTER TABLE matches ADD COLUMN digest_sent_at TEXT;
CREATE INDEX IF NOT EXISTS idx_matches_digest ON matches(user_id, digest_sent_at, fit_score DESC);
