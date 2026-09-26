# CHANGES.md — handoff for the `upgrade` branch

This branch is the full security, honesty and UX overhaul. Read this before merging.

## 1. Merge and deploy

```bash
# from a clone of https://github.com/shourjya001/Athena.git
git fetch /path/to/athena-upgrade.bundle upgrade:upgrade
git checkout upgrade
uv sync --all-extras --dev && uv run pytest -q tests/      # expect 108 passed
git push -u origin upgrade
# open a PR upgrade -> main, merge. Vercel deploys main automatically.
```

## 2. Vercel environment variables (set BEFORE the deploy goes live)

| Variable | Required | Notes |
|---|---|---|
| `SESSION_SECRET` | yes | Long random string (`openssl rand -hex 32`). Sessions are HMAC-signed with it. |
| `CRON_SECRET` | yes | Vercel sends it automatically as `Authorization: Bearer …` to cron routes. Cron returns 401 without it. |
| `OWNER_EMAIL` | yes | Your Google address. This is what unlocks the admin panel on `/system` and the owner bullet bank. |
| `SITE_URL` | yes | `https://athena-phi-one.vercel.app` (or your custom domain). Used for OAuth redirect URI, canonical and OG URLs. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | yes | Existing. Update the authorised redirect URI in Google Cloud Console to `${SITE_URL}/auth/google/callback`. |
| `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | optional | Without them, matcher falls back to BM25 and the UI says "Unscored" / "AI provider offline". |
| `SMTP_*`, `EMAIL_FROM` | optional | Digest email. `EMAIL_FROM` no longer has a default. |
| `ALLOWED_EMAILS` | optional | Comma-separated allow-list. Leave empty to let anyone sign in. |
| `LLM_REDACT_PII` | keep `true` | Default. |

## 3. Scrub git history (your history is public and contains PII)

Commits `c549c02`, `a207529`, `3d4fdb4`, `8e333d6`, `c37e571`, `451bfd5`, `7045a88` contain a seed DB with real user rows and phone numbers, a résumé PDF with your phone/email, and the phone number in `jobs.html`. Deleting files in a new commit does not remove them from `git log -p`. After merging, rewrite history once:

```bash
pip install git-filter-repo
git clone --mirror https://github.com/shourjya001/Athena.git athena-mirror && cd athena-mirror
git filter-repo --invert-paths \
  --path src/trackboard/static/resumes/tailored_1_823.pdf \
  --path data/seed_data.db \
  --replace-text <(printf '7679530903==>REDACTED\nshourjya001@gmail.com==>REDACTED\nprernarohilla050802@gmail.com==>REDACTED\nmanshirohella21@gmail.com==>REDACTED\n')
git push --force --all && git push --force --tags
```
Then re-add the clean `data/seed_data.db` from this branch in a fresh commit. Everyone with a clone must re-clone. Vercel re-deploys from the new `main`.

## 4. Things that changed behaviour (read carefully)

- **Admin is `OWNER_EMAIL`.** Nothing is hard-coded to `shourjya001@gmail.com` any more. If `OWNER_EMAIL` is unset, nobody is admin.
- **Everyone signs in fresh.** Old `trackboard_user` cookies are ignored; users will see the login page once.
- **Your bullet bank** (`config/resume.yaml`) no longer contains your email/phone. Enter them once on `/profile` → "Application fields"; the tailored PDF header and copy-chips read from there.
- **Manshi and Prerna's profiles are gone from the seed.** They sign in with Google and re-enter targets on `/profile`; their Google email creates the account. (`scripts/fix_seed_profiles.py` still exists but is not used by CI or deploy any more — delete it or rewrite it with synthetic data.)
- **Vercel's `/tmp` SQLite resets on cold start.** This was true before; it is still true. Profiles, matches and applications entered on the live site are lost whenever the function cold-starts. Until you move to Turso/libSQL or similar, tell users this on `/about` or treat the live site as a demo. This is the one architectural issue the branch does not fix.
- **`darwinbox` source rows** are relabelled "Careers site" in the UI (they are hand-entered listings, not a Darwinbox feed).
- **`/system` is public** (agent runs, source counts, company health) so recruiters can see it's real; the user table and delete buttons appear only for the owner.
- **Sandbox**: `/auth/demo-sandbox` creates a throwaway account, wiped at sign-out or after 2 days by the cron.

## 5. Files

New: `security.py`, `stats.py`, `listing.py`, `migrations/008_security.sql`, `static/{app.js,linkedin.js,tailor.js,pattern-lab.js,icons.svg,favicon.svg,og.png,htmx.min.js,fonts/*}`, `templates/partials/*`, `templates/pages/{prep,studio,job,about,privacy,terms,changelog,404,error}.html`, `tests/{helpers,test_auth,test_guest_safety,test_csp_and_headers,test_truth,test_a11y_tokens,test_routes}.py`, `CHANGELOG.md`.
Rewritten: `main.py`, `users.py`, `static/app.css`, `templates/base.html`, all `templates/pages/*.html`.
Deleted: `agents/applier.py`, `static/resumes/`, `templates/pages/missing.html`, `tests/test_auth_personas.py`.
Data: `data/seed_data.db` scrubbed (0 users) and `007` recorded in its migration ledger.

## 6. Not done / next

- Lighthouse was not run (no browser in the build sandbox). Expect Performance to be limited by `pattern-lab.js` (300 KB, only on pattern pages) and the 350 KB variable font — both cached immutable.
- LLM-dependent tests are exercised through the deterministic fallback only; run one LinkedIn audit in `deep` mode on the live site and confirm `agent_runs` shows `llm_calls > 0`.
- Ghost index / company pages, streaks and custom lists from the feature list are not built yet.
