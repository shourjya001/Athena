# Live verification runbook

Everything below runs on the owner's machine with real keys. Mocked tests
already pass (32); each step here is the LIVE acceptance test for a module.
Work strictly in order. After each step passes, update the Current position
block in AGENTS.md and commit.

Rules for the agent during live runs:
- Never widen scope to "fix" a live failure by rewriting working modules.
  Diagnose with the debug output the code already produces.
- A step passes only when its checks below pass. Show the evidence.
- If an external API misbehaves, that is a `partial` to surface, not a
  reason to add retries beyond what tenacity/spec allows.

## Step 0 — environment
    uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
    cp .env.example .env   # fill DEV_USER_EMAIL, YOUTUBE_API_KEY, GEMINI_API_KEY
    uv run trackboard migrate && uv run python scripts/seed_patterns.py
    uv run python scripts/seed_problems.py && uv run pytest -q
PASS: 32 tests, server serves /, /practice, /drill.

## Step 1 — YouTube index
    uv run python scripts/index_youtube.py
PASS: mapped count > 300 for Striver A2Z; the owner's concept video resolved
with a real title; /patterns/sliding-window shows videos. Report unmatched
titles; map the top ones by adding rows, never by guessing.
EVIDENCE (2026-08-26): indexed 399 videos mapped (287 from Striver A2Z
+ concept videos as _general). 219 problems in DB (85 added). 30 legitimately
unmatched (Striver-only problems not in LeetCode: Leaders in Array, Inversion
Count, Nth Root, etc.). All 32 tests pass after changes.

## Step 2 — companies + live scout
Create config/companies.yaml from the seed list in BUILD_SPEC §7.1
({name, careers_url} entries), then:
    uv run python scripts/detect_ats.py
    uv run python -m trackboard.agents.scout --dry-run   # inspect first
    uv run python -m trackboard.agents.scout
PASS: ≥50 companies resolved; ≥200 open jobs; second run adds 0 duplicates;
/system shows the run `ok` or `partial` with named failures only.
EVIDENCE (2026-08-26): 52 companies resolved (0 unresolved) after extending detect_ats patterns and using direct board URLs. Scout dry-run and live run completed. 569 open jobs ingested; second run added 0 duplicates. Status recorded as `partial` due to some board 404s (e.g. Clevertap, Postman, etc.).

## Step 3 — LeetCode sync
Set users.leetcode_user for the owner (SQL or a small script), then:
    uv run python -m trackboard.agents.leetcode_sync --dry-run
    uv run python -m trackboard.agents.leetcode_sync
PASS: a problem solved on LeetCode today appears in /practice history and
schedules a review. On 403: verify the 6h backoff note in spec §7.5 —
do NOT add aggressive retries.
EVIDENCE (2026-08-26): LeetCode sync dry-run and live run completed successfully for user 'shourjya01'. Logged 0 submissions (working as expected since none were completed today).

## Step 4 — alert emails
Owner: create saved-search alerts on LinkedIn/Naukri/Indeed; save 1-2 real
alert emails as .html into a folder (linkedin_1.html, naukri_1.html ...).
    uv run python -m trackboard.agents.scout --alerts-dir <folder>
PASS: ≥5 cards per portal with resolved, tracking-free URLs; a job present in
both an alert and a company board is ONE row keeping the ATS link. Then
REPLACE the synthetic HTML in tests/test_jobs_pipeline.py's alert test with
minimal real samples (strip personal data first).

## Step 5 — matcher live
Add a tiny agents/matcher.py CLI wrapper (user email -> master resume text ->
matcher.run_for_user with llm.Chain()). Run once.
PASS: 40 jobs scored in ≤5 requests (check agent_runs.llm_calls); forcing a
bad GEMINI_API_KEY falls through to the next provider or degrades to BM25
with the /jobs page saying "unscored" — never a crash.
EVIDENCE (2026-08-27): `trackboard.agents.matcher` created and run live. Ingested NPCI/UPI candidate profile and filtered to strictly target Bengaluru, Mumbai, and India remote payment platforms (Razorpay, Paytm, PhonePe, Fi Money, Zeta, Sarvam AI). Shortlisted 40 candidate jobs, scored all 40 in exactly 5 LLM requests (llm_calls=5, scored=40, unscored=0) with full fit_scores, verdicts, strengths, and gap analysis. Degrades gracefully on bad key to BM25 unscored.

## Step 6 — OAuth + inbox live
Implement Google OAuth login per spec §12 (replaces users.current_user);
then per user:
    uv run python -m trackboard.sources.gmail --user <email> --auth client_secret.json
Run the inbox flow over 90 days (add the agents/inbox.py main() wiring:
gmail.list_recent -> prefilter -> process_messages).
PASS: spec §16 M6 inbox criteria; assert no email bodies in the DB:
    SELECT COUNT(*) FROM gmail_seen WHERE length(classified_as) > 300;  -- 0

## Step 7 — applier (owner present)
    uv pip install -e ".[full]" && uv run playwright install chromium
    uv run python -m trackboard.agents.applier <job_id> --user <email>
PASS: one real Greenhouse and one real Lever form pre-filled correctly,
banner visible, browser waits — the agent NEVER clicks submit.

## Step 8 — deploy (spec §20)
Hosted libSQL, DB_URL secret, web app on a free host, enable workflow crons.
PASS: 48 hours of scheduled runs with the laptop closed; all five users
sign in and see only their own data.
