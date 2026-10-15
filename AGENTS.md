# AGENTS.md

Operating instructions for AI coding agents (Codex, Claude Code, Cursor, Cline,
Aider, GitHub Copilot, and others) working in this repository.

This repository is a **public toolkit** for Domo developers and AI coding agents.
It has three layers:

| Layer | Path | What it is |
|---|---|---|
| Starter kit | `docs/`, `scripts/`, `templates/` | Auth helpers, API reference, runnable scripts, Pro Code template |
| Skills | `skills/` | Task/surface-specific operating notes ([skills/README.md](skills/README.md)) |
| Reference architectures | `reference-architectures/` | Two complete, deployable Domo apps to learn from and adapt |

## Before editing

1. Read this file.
2. Read [docs/quickstart.md](docs/quickstart.md) for environment setup.
3. Read the skill under `skills/` that matches the task
   (see the index in [skills/README.md](skills/README.md)).
4. For work inside `reference-architectures/<app>/`, read that app's
   `README.md` and `AGENTS.md` / `AGENT.md` first — each app is an
   independent, self-contained package.

## Safety rules

- **Never commit secrets**: no SIDs, refresh tokens, developer tokens, PATs,
  passwords, private keys, cookies, or `.env` values. Use
  `config/secrets.env.example` as the pattern for documenting required secrets.
- Run `bash scripts/check-secrets.sh` before committing.
- **Read operations are safe.** Destructive or production-affecting actions
  (deletes, deploys, workflow releases, `domo publish`, dataset deletes)
  require explicit confirmation from the human operator.
- Do not automate the Domo web UI; use the Domo CLI, the documented scripts
  here, or Domo APIs.
- Keep the two reference architectures independent — do not move or rewrite
  one app while working on the other.

## Domo auth

Preferred order:

1. Existing `INSTANCE` + `DOMO_TOKEN` environment variables.
2. Existing `INSTANCE` + `SID` environment variables.
3. `bash scripts/authenticate.sh <instance>.domo.com` (uses the Domo CLI session).

See [docs/domo-auth.md](docs/domo-auth.md) before adding new auth code.

## Pro Code rules

- Preserve `manifest.json` mappings and aliases. Never hardcode dataset UUIDs
  in app URLs when a manifest alias exists.
- Use `domo.get('/data/v1/<alias>')` or
  `domo.post('/sql/v1/<alias>', sql, {contentType: 'text/plain'})`.
- Use AppDB through `collectionsMapping[]` and workflows through
  `workflowsMapping[]`.
- Validate that `index.html`, `app.js`, `app.css` / `styles.css`, and
  `manifest.json` exist before publishing.
- Ask before running `domo publish`.

## Validation

Run the narrowest useful checks before finishing a change:

```bash
bash scripts/check-secrets.sh
python3 -m json.tool <app>/pro-code/manifest.json >/dev/null
node --check <app>/pro-code/app.js
```

Each reference app also carries its own test suite under `tests/` — see the
app's README for how to run it.

## Publication

Publish source updates on `main`. Do not create or push version tags, create GitHub
Releases, or build/upload distribution ZIPs unless the user explicitly requests them.
Routine source maintenance and commit/push instructions do not imply that request.

## Conventions

- Keep private work logs, deployment state and internal coordination notes out
  of this public repository.
- Japanese documentation is welcome for human readers; keep command names,
  paths, Domo object names, and API terms in English.
