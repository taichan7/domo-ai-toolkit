# AI Agent Setup

> Japanese: [ai-agent-setup.ja.md](ai-agent-setup.ja.md)

This repo is structured so AI coding agents can share one contract: read `AGENTS.md`, use the scripts in `../scripts/`, and look up endpoint details in `api-reference.md`.

## Context Files

| Agent/tool | What to give it |
|---|---|
| Codex | `AGENTS.md` |
| Codex Cloud | `AGENTS.md` (auto). Setup script = `bash ../scripts/cloud-bootstrap.sh`; auth as env vars (not "secrets") |
| Claude Code | `CLAUDE.md` loads automatically, then points to `AGENTS.md` |
| Claude Code cloud/web | `CLAUDE.md` → `AGENTS.md`; `.claude/settings.json` SessionStart hook runs the bootstrap |
| Cursor | Attach or mention `AGENTS.md`, or index the codebase |
| Cline / Continue | Attach `AGENTS.md` as project context |
| Aider | `aider AGENTS.md api-reference.md` |
| Generic web LLM | Paste `AGENTS.md` and relevant sections of `api-reference.md` |

For the verified Domo MCP server and client-specific setup, read [domo-mcp.md](domo-mcp.md).

In cloud and remote agent environments (Codex Cloud, Claude Code cloud/web,
Codespaces/devcontainer, GitHub bots), provide Domo auth as environment
variables (`INSTANCE` + `DOMO_TOKEN` or `SID`) — cloud sandboxes have no
local keychain or CLI session.

## Claude Code

```bash
cd domo-ai-toolkit
claude
```

Claude Code reads `CLAUDE.md`; that file tells it to read `AGENTS.md`.

Authenticate through the agent:

```text
Run bash ../scripts/authenticate.sh your-company.domo.com to authenticate.
```

Then try:

```text
List the 10 datasets in this instance with the most rows.
```

## Other Agents

For any agent that can read files and run shell commands, make these files authoritative:

- `AGENTS.md`
- `api-reference.md`
- `quickstart.md` for first-run flow
- `../templates/pro-code-app/README.md` for Pro Code app work
- `autonomous-loop.md` when the user wants an improvement cycle that runs until they say stop

## Useful Prompts

Inventory:

- "How many datasets do I have? Group by connector type."
- "Find every dataset owned by [name] that has not been updated in 90 days."
- "List the 5 largest datasets and their schemas."

Diagnosis:

- "Find every failing Magic ETL and group by error code."
- "Look at dataflow 92 and tell me what is wrong."
- "What broke in this dataflow's last run? Recommend a fix."

Pro Code:

- "Build a workflow app on top of dataset [id]."
- "Take `../templates/pro-code-app/` and bind it to dataset [id]."

Clone/migration:

- "Read `SKILL.md` and clone this App Studio app from source instance X to target instance Y."

## Guardrails

If an agent starts using browser automation, guessing endpoints, or writing secrets to files, tell it:

```text
Re-read AGENTS.md and follow the Domo API, auth, and safety rules there.
```

When an agent creates a reusable script or pattern, place it in `../scripts/` or `../templates/` and update the relevant doc under `` or `docs/`.
