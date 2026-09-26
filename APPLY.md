# Apply

Antigravity prompt:
> Unzip `athena-upgrade-changed-files.zip` over the repository root, overwriting existing files. Delete every path in `DELETED_FILES.txt`. Run `uv sync --all-extras --dev` and `uv run pytest -q tests/` - expect 113 passed. Commit as "feat: security, honesty and UX overhaul (see CHANGES.md)" and push to main (or PR and merge). Do not touch other files. Do not commit .env.

Safe to apply over the previous build. Env vars and Google redirect URI: CHANGES.md section 2. History scrub: section 3.
