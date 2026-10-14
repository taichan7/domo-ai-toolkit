# Learning & Handoff Enforcement Skill

In the never-stop autonomous loop, **knowledge must not die with a session.** This skill
makes two duties *hard gates* on every increment, not optional niceties:

1. **Capture every failure and how it was resolved** as durable, searchable knowledge — as it happens (随時).
2. **Hand off and share that knowledge** to the other AIs sharing this workspace.

Read `AGENTS.md` first. This is the operational companion to
[`autonomous-improvement-loop.md`](autonomous-improvement-loop.md) (the loop itself),
[`handoff.md`](handoff.md) (the note mechanics),
[`multi-agent-collaboration.md`](multi-agent-collaboration.md) (coordination + git hygiene),
and [`domo-config-backup.md`](domo-config-backup.md) (backing up Domo-side config). It does not
restate those — it enforces the discipline that ties them together.

## Why this is a gate, not a nicety

- Many agents (Claude Code local/cloud, Codex, `@claude`/`@codex` bots, other sessions) share **one
  file-based contract**. The next agent to touch a file may be a different model with none of your context.
- A failure you hit and solved, if unrecorded, gets **re-hit and re-solved** (wasted cycles) or
  **re-introduced** (regression). The most expensive bug is the one already fixed once.
- "I fixed it" is not *done* until the fix, its guard, and the lesson are written **where the next agent looks**.

## Capture every failure → resolution (随時)

Whenever an increment hits an error, dead-end, failed validation, wrong assumption, or surprising
behavior — **even if you recover immediately** — record it before moving on. Keep it to a few lines,
in this shape:

- **Symptom** — the exact error / command / wrong output. Copy the message, not a paraphrase.
- **Root cause** — *why*, not just what. If you don't know, say "root cause unconfirmed" — that is itself useful.
- **Fix** — the change that resolved it, with the path and/or commit.
- **Guard** — the test, assertion, lint rule, gitignore rule, or doc note that prevents recurrence.
  **Prefer a durable guard over a one-time fix.** A failure with no guard is an invitation to repeat it.
- **Where recorded** — the handoff bullet, plus a memory or skill if the lesson is durable/cross-project.

Worked example (from this workspace): *Symptom* — raw sample CSVs in `soccer-team-tools/<app>/dataset/`
were committable. *Root cause* — a `.gitignore` rule named a stale top-level path that matched nothing.
*Fix* — `ccf71693` rewrote it to the real nested path. *Guard* — the descend-safe `dir/*` glob +
`!*.schema.json` negation, verified with `git check-ignore`. *Where* — commit body + this example.

## Promote recurring failures into skills / memory

Failures are the richest source of skill candidates. Use this escalation ladder — don't over-skill a
one-off, don't under-skill a pattern:

1. **One-off, project-local** → note it in the project handoff + that project's `AGENT.md`/`README.md`.
2. **Cross-project, OR seen ≥2 times, OR it prevents a known failure mode** → promote to a **memory**
   (durable fact) and/or a focused `<topic>.md`, and **add it to `README.md` in the
   same increment**. (Mirrors that README's "Promoting New Skills" rule.)
3. **It changes how everyone must work** → add a notice to `tasks/shared-notices.md`.

## Handoff is a hard gate on every increment

No increment is complete until the next agent could resume **without you**:

- Append to the current `handoffs/<date>-*.md` (**`## Agent` + `## Environment` mandatory** — see
  [`HANDOFF_TEMPLATE.md`](../handoffs/HANDOFF_TEMPLATE.md) + [`AGENTS.md`](../AGENTS.md) §handoffs for
  that pair, and [`handoff.md`](handoff.md) for the full Required-Content list), or to
  `tasks/in-progress.md` for a live claim:
  what changed, **why**, validation **done vs not-done** (say plainly if Domo verification wasn't run),
  what was deferred/rejected **and why**, and the **exact next step**. Convert relative dates to absolute.
- **Update the relevant index in the same increment** — `tools.json`, `TOOLS.md`, the project README,
  any `ai/` index. A catalog that lies is worse than no catalog.
- **Leave the tree green and buildable.** Each pushed increment is a clean stopping point on its own —
  never hand off a half-applied refactor or a failing validation as "someone will finish it."

## Share knowledge to the other AIs — not just to a file

Files are the durable channel; also use the live channel when your change affects what a peer is doing *now*:

- **Claim and release** your slice in `tasks/in-progress.md` so peers route around you; remove/mark it
  done when finished. Keep claims narrow (specific files/dirs).
- For a decision that affects a peer's **active** work, message that peer session (cross-session
  `SendMessage`; see [`multi-agent-collaboration.md`](multi-agent-collaboration.md)). Prefer a new,
  non-overlapping slice over a race.
- **Record "rejected / out of scope / do not touch" where the next agent looks** (handoff + memory), so
  settled calls are not re-litigated by the next loop iteration.
- **Never launder permissions or secrets across sessions.** Auth is per-environment, permission is
  per-session. Summarize sensitive output; never paste raw secrets, tokens, full exports, or PII into a
  handoff or a message.

## Checklist — run before each commit

- [ ] Any failure/dead-end this increment captured (symptom → cause → fix → **guard** → where)?
- [ ] Recurring pattern promoted to memory/skill **and indexed** in `README.md`?
- [ ] Handoff updated (`## Agent`, `## Environment`, why, validation done/not-done, exact next step, absolute dates)?
- [ ] Every touched index truthful (`tools.json` / `TOOLS.md` / project README / skills README)?
- [ ] `in-progress.md` claim updated or released; peer pinged if it affects their live work?
- [ ] No secrets / PII / raw exports in any note or message (`bash ../scripts/check-secrets.sh` if unsure)?
