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

## 3b. Hosted database — no database on your machine, nothing lost on cold start (10 minutes, once)

Production now uses **Turso** (hosted libSQL, SQLite-compatible, free tier: 9 GB, 500 M reads/month) when two env vars are set. Nothing runs on your laptop; Vercel and GitHub Actions both talk to it over HTTPS. Without the vars the app falls back to the old `/tmp` SQLite demo mode.

1. Sign up at https://turso.tech (GitHub login). Create a database, e.g. `athena`. Region: `aws-ap-south-1` (Mumbai).
2. Copy the database URL (`libsql://athena-<org>.turso.io`) and create an auth token (Databases → athena → Tokens → *read & write*, no expiry).
3. Vercel → Settings → Environment Variables: add `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. Redeploy.
4. GitHub → repo → Settings → Secrets → Actions: add the same two secrets (the nightly workflow writes to the hosted DB now).
5. Seed the content tables once, from your laptop, then never again:
   ```bash
   export TURSO_DATABASE_URL=libsql://athena-<org>.turso.io TURSO_AUTH_TOKEN=<token>
   uv run trackboard migrate
   uv run trackboard seed --from data/seed_data.db     # patterns, problems, resources, companies, jobs (~11k rows, 2-4 min)
   ```
   User tables are never copied. After this, `data/seed_data.db` is only used by tests and by the demo fallback.

Tested here against an emulated Turso endpoint (same JSON protocol); the first real run is yours — if `uv run trackboard migrate` prints `database backend: turso` and returns without error, you're live.

## 3c. Agents, live (`/agents`)

Public page: the pipeline as an SVG whose nodes light from the real `agent_runs` table, a JSON endpoint polled every 15 s, an event log, and a "Replay last run" button that walks Scout → Matcher → Digest → Inbox → Tailor → LeetCode sync with particles along the edges and counters that tick to the real in/out numbers. No fabricated activity: an idle agent says "no run yet".

## 3d. Vercel storage (5.23 GB used) — how to get it down and keep it down

Two causes, both fixed or fixable:
1. **numpy (68 MB) was in every deployment**, pulled in only by `rank_bm25`. Replaced with `src/trackboard/bm25.py` (pure Python, same scores). `uvicorn[standard]` extras (uvloop, httptools, watchfiles) are also gone; Vercel never used them. Next deploy is roughly 80 MB smaller.
2. **Vercel keeps every past deployment's function bundle** and counts it against "Function storage". Go to *Project → Settings → General → Deployment Retention* and set production and preview retention to 30 days (or delete old deployments under *Deployments → … → Delete*). That alone will reclaim most of the 5 GB.
3. After Turso is live (§3b), remove `"data/seed_data.db"` from `includeFiles` in `vercel.json` — another 12 MB per deployment, and the file is only needed for local tests then.

## 3e. Security: sign-in and session model

- **SSO:** Google is the only identity provider. Users' passwords never touch Athena. If a user has Google 2-Step Verification on (most corporate accounts do), that MFA protects Athena too.
- **Device-bound sessions ("IP-based" without OTP):** the session cookie now carries a hash of the browser (User-Agent) and the network (/24 for IPv4, /48 for IPv6). A cookie copied to another browser or another network is rejected outright. Mobile carriers rotating the last octet don't log users out. Set `SESSION_BIND_DEVICE=false` to disable if a user is on a network that hops prefixes constantly.
- **Step-up on unknown devices:** a sign-in from a browser/network that has never signed in before sends Google `prompt=login`, which makes Google re-verify the password (and 2-Step if enabled) instead of just picking an account. Known devices get a one-year `athena_known` cookie and skip the step-up.
- Existing cookies are all invalidated once (old 3-part tokens are rejected); everyone signs in again after this deploy.
- `/.well-known/security.txt` published for responsible disclosure.
- Not done, and honestly not needed for 20 users: passkeys/WebAuthn (needs JS and a credential store), encryption of phone numbers at rest (Turso encrypts at rest; the app never shows them to anyone but their owner).

## 3f. Prep: system design (`/prep/system-design`)

Fifteen original topics in three levels — basics, core building blocks, case studies — each with an animated SVG scene (SMIL, no JS, pauses under reduced-motion), five ideas, three things to say in the interview, and primary-source links. Content is static in `sysdesign.py`; no database, no writes. The topic list follows the standard interview syllabus; the text is Athena's own — the GitHub repo you pointed at has no licence and summarises a copyrighted book, so nothing from it was copied.

## 3g. UI additions this build

- "Every career API, one desk" fan-in animation on the home page (six ATS feeds converging into Athena, then one list to you).
- Horizontal scroll-snap rows for compact cards (newest openings on Home, topic rows in System design), with keyboard focus.
- Pointer tilt on the hero preview and the three "How it works" cards: desktop with a mouse only, off for touch and reduced-motion. No library, no WebGL, no load.

## 4. Things that changed behaviour (read carefully)

- **Admin is `OWNER_EMAIL`.** Nothing is hard-coded to `shourjya001@gmail.com` any more. If `OWNER_EMAIL` is unset, nobody is admin.
- **Everyone signs in fresh.** Old `trackboard_user` cookies are ignored; users will see the login page once.
- **Your bullet bank** (`config/resume.yaml`) no longer contains your email/phone. Enter them once on `/profile` → "Application fields"; the tailored PDF header and copy-chips read from there.
- **Manshi and Prerna's profiles are gone from the seed.** They sign in with Google and re-enter targets on `/profile`; their Google email creates the account. (`scripts/fix_seed_profiles.py` still exists but is not used by CI or deploy any more — delete it or rewrite it with synthetic data.)
- **Vercel's `/tmp` SQLite resets on cold start — fixed by §3b.** Set the two Turso vars and user data persists. Without them the site is demo-only.
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
