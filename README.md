# Trackboard

Pattern-first DSA practice, and later a job pipeline, for a small group.
`BUILD_SPEC.md` is the source of truth. `AGENTS.md` is the short version for
your coding agent.

**State: all modules are written and unit-tested (30 tests) with mocked
network.** What remains is live verification on your machine with real keys —
the ordered list is in AGENTS.md. Nothing here calls a paid API.

## Run it

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env            # edit DEV_USER_EMAIL

trackboard migrate
python scripts/seed_patterns.py
trackboard serve                # http://127.0.0.1:8000
```

## What works now

- 26 patterns with recognition cues, invariants, and traps; 134 problems
  mapped and tagged (blind75 / neetcode150 / striver_a2z, best-effort)
- `/patterns` and `/patterns/{slug}` — cues, invariant, traps, problems, videos
- `/practice` — due reviews + 2 new from your weakest pattern, one-tap 1–4
  rating, FSRS-style scheduling (`fsrs_lite.py`, same fields as py-fsrs)
- `/drill` — pattern-recognition trainer: deep-links to the problem, you answer
  here, wrong answers show the recognition cue and reschedule that pattern
- LeetCode sync agent (`python -m trackboard.agents.leetcode_sync`) — records
  accepted submissions as attempts, idempotent, per-user error isolation
- LLM provider chain with PII redaction and untrusted-content wrapping
  (`llm.py`) and the six-stage resume prompt library (`prompts/analyst.py`) —
  wired up at M5
- `.github/workflows/frequent.yml` — Mode B scheduling for the sync agent
- 14 tests: `pytest tests/`

## What is stubbed

- `scripts/index_youtube.py` is written but needs `YOUTUBE_API_KEY` and a
  network — run it once locally to populate videos. `channels.yaml` already
  lists Striver's A2Z playlist and the owner's concept video.
- Auth is `DEV_USER_EMAIL` from `.env`. Google OAuth lands with deployment
  (spec §12, §16 M3). Every read query already takes a `user_id`, so the swap
  touches `users.current_user()` and nothing else.
- Sheet tags are best-effort; the exact-ordinal sheet import (spec §7.6) can
  replace them without schema changes.

## Working with Antigravity

Open this folder in Antigravity. It reads `AGENTS.md` automatically; that file
tells the agent where the project currently stands, because agent context does
not persist between sessions. Use Planning mode with review-driven autonomy,
and check each implementation-plan artifact against the matching milestone's
acceptance criteria in `BUILD_SPEC.md` §16 before approving it.

First prompt to paste, verbatim:

> Read AGENTS.md, then BUILD_SPEC.md, then this README. Run the
> "Before writing any code" checklist from AGENTS.md and show me the test
> output. Then propose a plan for task 1 of the Next list below — plan only,
> no code until I approve.

Every later session starts the same way: "Read AGENTS.md and continue from
the Current position block."

## Next (hand this list to the coding agent)

1. Run `scripts/index_youtube.py` with a real key; fix any unmatched titles.
2. Google OAuth + allowlist (spec §12), replacing `users.current_user()`.
3. Deploy Mode B (spec §20): hosted libSQL, web app on a free host, enable
   the workflow cron. Acceptance criteria: spec §16 M3.
4. Then M4 — Scout and the job feed. Do not start M4 before M3 accepts.

## Conventions worth not breaking

- `db.py` is the only module that imports `sqlite3`. There is a test.
- `agents/` must not import `routes/` or `fastapi`. There is a test.
- Colours and type are pinned in spec §11.1 and live in `static/app.css`.
