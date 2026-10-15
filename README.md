# domo-ai-toolkit

> 🇯🇵 **日本語版はこちら → [README.ja.md](README.ja.md)**

**A field-tested toolkit for building on Domo with AI coding agents.**

This toolkit combines documented Domo contracts with patterns verified in Domo
deployments. Skills label their evidence strength; destination permissions,
features and production behavior still require validation. The reference apps
are teaching examples with synthetic data. Read their distribution and production
limits before deploying them.

Use the latest release for customer distribution. Earlier revisions may retain
reference-instance metadata that has since been removed.

It contains three layers:

| Layer | Path | What you get |
|---|---|---|
| **Starter kit** | [`docs/`](docs/), [`scripts/`](scripts/), [`templates/`](templates/) | Auth flow, API reference, runnable shell/Python helpers, a Pro Code app template |
| **Skills library** | [`skills/`](skills/) | 55 operating notes — one per Domo surface (DataSets, Magic ETL, Workflows, Code Engine, Pro Code, AppDB, App Studio, AI Services, …) plus platform-agnostic agent-workflow skills |
| **Reference architectures** | [`reference-architectures/`](reference-architectures/) | Two complete, deployable Domo apps showing how Pro Code + Code Engine + AppDB + Magic ETL + Workflows + App Studio fit together |
| **Request templates** | [`prompts/`](prompts/) | Copy-paste request templates for asking an AI agent to implement / review / revise a prompt |

## Who this is for

- Engineers and analysts at companies running on Domo who want AI agents to
  work against their instance
- Developers building Pro Code apps who don't want to start from a blank file
- SEs preparing hands-on sessions or reference implementations for customers

You do **not** need to be a senior developer. You need an AI tool, a terminal,
and a Domo login.

## Quickstart

### Step 1 — Install the Domo CLI

Download it from your Domo developer portal (`Admin → Developer → CLI`), then:

### Step 2 — Authenticate from the terminal

```bash
bash scripts/authenticate.sh your-company.domo.com
```

If it prints `Authenticated to your-company.domo.com — SID=...`, you're good.

### Step 3 — Make your first API call

```bash
bash scripts/list-datasets.sh
```

You should see the first datasets in your instance. That's it — you are now
talking to Domo from the command line, which means any AI agent with shell
access can do the same.

### Step 4 — Point your AI agent at this repo

The key file is **[AGENTS.md](AGENTS.md)** — it tells any agent how this repo
works. Claude Code reads [CLAUDE.md](CLAUDE.md) (which points at AGENTS.md)
automatically. Then just ask, e.g.:

- "List my failing Magic ETLs and tell me why they broke" → the agent uses
  `scripts/diagnose-etls.sh` and `skills/domo-magic-etl.md`
- "Build me a Pro Code app on top of dataset X" → it starts from
  `templates/pro-code-app/` and follows `skills/domo-procode-app.md`
- "Deploy the inventory management reference app to my instance" → it follows
  `reference-architectures/inventory-management-app/docs/`

## The reference architectures

Two production-grade apps, each self-contained and deployable to your own
instance with an AI agent guiding you:

- **[inventory-management-app](reference-architectures/inventory-management-app/)** —
  inventory in/out management: Pro Code UI (PC + Domo Mobile, QR scanning),
  Code Engine API, AppDB, Magic ETL with per-item AI commentary, and an
  AI-agent notification Workflow triggered server-side.
- **[pl-summary-app](reference-architectures/pl-summary-app/)** —
  store P/L AI analysis: Magic ETL → parallel parent/child Workflows with AI
  agents → AppDB → a fully self-contained App Studio card.

Both apps include provisioning scripts that discover target-instance object
IDs **by name** — no hardcoded IDs to edit before deploying.

## Using this with an AI agent

This repo is designed so an agent can read it whole and immediately know how to:

1. Authenticate to your Domo instance ([docs/domo-auth.md](docs/domo-auth.md))
2. Query datasets and diagnose dataflows ([docs/api-reference.md](docs/api-reference.md))
3. Build Pro Code apps that respect Domo's manifest and SDK conventions
   ([skills/domo-procode-app.md](skills/domo-procode-app.md))
4. Clone or migrate content between instances
   ([skills/domo-cross-instance-clone.md](skills/domo-cross-instance-clone.md))

## FAQ

**Q: How do I know what changed?**
See [CHANGELOG.md](CHANGELOG.md) and the
[Releases](https://github.com/taichan7/domo-ai-toolkit/releases) page — the
toolkit is versioned so you can tell whether your copy is current.

**Q: Is this an official Domo product?**
No. It is a field kit built by a Domo SE. The APIs used are the same ones the
Domo platform uses internally plus the published developer API — stable, but
not all are formally part of the public developer API. Each skill file marks
claims as `[DOC]` (documented), `[REPO]` (verified in code), `[KB]`
(knowledge base), or `[INFER]` (inferred) so you know how much to trust them.

**Q: Does it work with the public Domo developer API?**
Yes. If you have a developer token you can use it instead of a CLI session —
see [docs/api-reference.md](docs/api-reference.md) for the header difference.

**Q: Can I deploy the reference apps to production?**
They are references, optimized for being understandable and safely deployable
side-by-side (every object can be namespaced with a "name tag" via env var).
Read each app's README before pointing one at a production instance.

**Q: Related projects?**
[domo-ai-starter](https://github.com/Willwwest/domo-ai-starter) by Will West is
a sibling minimal starter kit — a great lighter-weight entry point.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship it. Attribution welcome
but not required.
