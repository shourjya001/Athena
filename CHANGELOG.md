# Changelog

## 2026-09-26 — Security, honesty and UX overhaul

### Security
- Sessions are now HMAC-signed (`athena_session`); the old plaintext-email cookie is ignored. Owner/admin status comes from `OWNER_EMAIL`, not a hard-coded address.
- Every state change is a CSRF-checked POST behind sign-in. Removed `/a/agent/run`, `/a/agent/stop`, `/a/digest/send-test`, and the unauthenticated GET triggers for scout and matcher.
- Cron endpoints require `Authorization: Bearer $CRON_SECRET` unconditionally.
- Outbound apply links: https only, public-IP only; server-side liveness checks run only against allow-listed ATS hosts (SSRF guard).
- Strict CSP (no inline scripts), HSTS, nosniff, frame-deny, referrer and permissions policies. All scripts moved to `/static`.
- SQLite-backed rate limits on LLM, upload, digest, sandbox and redirect routes.
- Removed the Playwright "applier" agent and the console-paste autofill. Tailored PDFs are no longer written under `/static`; they download through an ownership-checked route.
- Seed database ships with zero user rows. Guests get a synthetic sample profile only.

### Honesty
- One `stats.site_stats()` feeds every number on public pages. No hard-coded counts.
- Job cards show a score only when a signed-in user has a real scored match; otherwise "Unscored". The `80/85/82/75` placeholder is gone.
- "Posted" replaced by "first seen" (ingestion time was being shown as posting time).
- Public list defaults to India + remote, engineering only, with server-side filters and pagination.
- Multi-factor fit returns `UNSCORED` instead of a fabricated 84 when there is no résumé text.

### UX / UI
- New design system: semantic tokens, light and dark themes, Inter + JetBrains Mono self-hosted, Lucide icon sprite (no emoji as icons), one accent colour.
- Four sections (Home, Jobs, Prep, Studio) with a desktop header and a mobile bottom nav; skip link; visible focus rings.
- Home page rewritten: one-sentence promise, how it works, pattern of the day, newest India openings, sign-in benefits, sandbox, access-list signup.
- Job card with collapsed/expanded states and a scrollable description; sticky filter rail on desktop, filter sheet on mobile.
- New pages: /prep, /studio, /jobs/{id}, /about, /privacy, /terms, /changelog, branded 404/500, public /system status with a live agent-pipeline diagram.
- LinkedIn audit form open to read, run gated behind sign-in; results rendered safely.
- Pattern pages: YouTube facades (no iframes until play), honest empty states, stacked tables on phones, the step-through lab hidden when no model exists.
- Per-page titles and descriptions, OG image, sitemap with priorities, robots rules.

### Tests
- 42 → 108 tests: guest safety (no PII, no placeholders, all mutations redirect), CSP and headers, truth (numbers match stats, filters hide non-engineering), accessibility tokens (WCAG AA contrast in both themes), routes, auth.

## 2026-09-26 (later) — Visual layer v2
- Hero with a labelled sample job card, trust line and larger CTAs; four live stat tiles; feature cards with icon tiles; FAQ; section headers.
- Prep as icon tiles; patterns as a card grid with per-pattern progress; job cards get company avatar tiles, depth and hover lift.
- Header blur, accent hairline, gradient primary button, softer 20px radii, second accent for tiles. Still one primary accent, no emoji icons, CSP unchanged.

## 2026-09-26 (v3.1) — Hosted database + live agents
- `db.py` gains a Turso/libSQL HTTP backend behind the same API; `trackboard seed` uploads content tables once. Production data no longer lives on a serverless `/tmp`.
- `/agents`: live pipeline diagram driven by `agent_runs`, 15 s polling, event log, replay of the last run.
- Daily GitHub workflow calls the cron with a bearer token and writes to the hosted DB.

## 2026-09-26 (v3.2) — Lighter bundle, device-bound sessions, system design, fan-in
- Dropped numpy (pure-Python BM25) and uvicorn extras: ~80 MB smaller deployments.
- Sessions bound to browser + network prefix; Google password step-up on unknown devices; security.txt.
- `/prep/system-design`: 15 original topics, animated scenes, three levels.
- Home: fan-in "every career API, one desk" animation, compact scroll-snap rows, pointer tilt.
