# Apply the Athena upgrade (changed files only)

This package contains ONLY the files that are new or modified versus `main` (commit 52dba8c),
plus `DELETED_FILES.txt` listing files that must be removed. Your `.env`, `.venv`, `bin/`
and `.git` are untouched.

## Antigravity prompt (copy-paste)

> Unzip `athena-upgrade-changed-files.zip` over the root of the Athena repository, overwriting existing files.
> Then delete every path listed in `DELETED_FILES.txt`. Run `uv sync --all-extras --dev` and
> `uv run pytest -q tests/` and confirm 110 passed. Commit everything as one commit with the message
> "feat: security, honesty and UX overhaul (see CHANGES.md)", push to a new branch `upgrade`, open a
> pull request to `main`, and merge it. Do not modify any file the zip did not touch. Do not commit `.env`.

## Before the deploy goes live (you, in the Vercel dashboard — 2 minutes)

Project → Settings → Environment Variables:
- `SESSION_SECRET` = a long random string (`openssl rand -hex 32`)
- `CRON_SECRET`    = another random string (Vercel sends it as the Bearer token to the cron route)
- `OWNER_EMAIL`    = your Google address (this is what makes you admin now)
- `SITE_URL`       = https://athena-phi-one.vercel.app
- keep your existing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GEMINI / OPENROUTER / SMTP values

Google Cloud Console → your OAuth client → Authorised redirect URIs:
- add `https://athena-phi-one.vercel.app/auth/google/callback`

## After the deploy (5 minutes)

1. Private window on your phone → open the site. Confirm: no phone number, "Unscored" chips, bottom nav, sandbox button works.
2. Sign in with Google → `/profile` → fill "Application fields" once (name, phone, LinkedIn). These moved out of `config/resume.yaml`.
3. Run one LinkedIn audit in "Deep" mode → `/system` should show a `linkedin` run with `llm_calls > 0`.
4. Scrub git history of the old PDF / seed DB / phone number: commands are in `CHANGES.md` §3. Do this before you post the link.

## Why some things look different

- Everyone is signed out once (old cookies are ignored — they were forgeable).
- Manshi and Prerna sign in with Google and re-enter targets on `/profile`; their rows are no longer shipped in the seed database.
- Hand-entered listings (Amazon, Google, banks) show a "Careers site" badge instead of "darwinbox".
- Data entered on the live site still resets on Vercel cold starts (unchanged; storage decision for later).
