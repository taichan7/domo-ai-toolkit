# Handoff Skill

Use this before stopping non-trivial work or when another AI or human may continue later.

## Where To Put Handoffs

- Use `handoffs/` for dated, concrete handoff notes.
- Use `handoffs/HANDOFF_TEMPLATE.md` as the template source.
- Keep `tasks/in-progress.md` current when work spans turns or agents.
- See `../docs/ai-collaboration.md` for the full Issue / PR / handoff workflow.

Recommended filename:

```bash
handoffs/YYYY-MM-DD-project-or-topic.md
```

## Required Content

- Which AI agent (or human) performed the work — e.g. Codex, Claude Code, GitHub Copilot, Gemini, Cursor, Human. Mandatory in every handoff, including short-form ones: git commit authorship always shows the human user's identity, never the tool, so this is the only durable record of who actually did the work.
- What changed.
- Why it changed.
- Files changed.
- Shared context read before work started.
- Design decisions and assumptions.
- Validation performed.
- Validation not performed.
- Work log / key observations.
- Things that took time or were unexpectedly subtle.
- Failed attempts / dead ends, or `N/A`.
- Root cause / fix pattern for bugs, CI failures, or confusing behavior.
- Reusable knowledge.
- Skill candidates, or `N/A`.
- Shared notices to add, or `N/A`.
- Risks and rollback notes.
- Next steps.
- Files the next agent should read first.

## Knowledge Capture

- Be concrete about commands, paths, symptoms, and outcomes.
- Separate facts from assumptions and unverified Domo state.
- Record failed paths when they cost meaningful time; do not make the next agent rediscover them.
- If a lesson is useful across projects, list it under `Reusable Knowledge`.
- If a repeatable workflow should become an agent instruction, list it under `Skill Candidates`.

## Safety

Do not put secrets, customer-private raw data, raw tokens, SID values, cookies, or large generated exports into handoff notes.
