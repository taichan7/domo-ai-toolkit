# Autonomous Improvement Loop Skill

Use this when the user wants an improvement cycle that **keeps running until they explicitly command a stop** — not a one-shot task. It turns "keep making this better, don't stop, don't ask" into a concrete, safe, tool-agnostic protocol.

This skill is for any agent (Codex, Claude Code, GitHub Copilot, Gemini, Cursor, Cline, Aider, …). Read `AGENTS.md` first; this skill layers on top of it.

## Core Principle

**Never self-declare "done" and stop.** In this mode, "I finished the task" is not a reason to end the session — it is the trigger to pick the *next* highest-value improvement and continue. The loop ends only when the user says so, through one of the explicit stop signals below. Between those signals, idle silence is a failure mode: there is always a next improvement (a rough edge, a missing test, a doc gap, a robustness hole, a small UX win).

Token consumption is not a constraint in this mode. The user has said so explicitly. Do not optimize for brevity or "wrapping up." Optimize for durable, verified, committed progress.

## The Loop

Repeat indefinitely:

1. **Choose** the single next highest-value improvement (see "Choosing the Next Improvement"). One item — do not batch.
2. **Implement** the smallest useful increment. Small diffs are easier to verify, revert, and review.
3. **Validate** it (see "Validation"). If validation fails, fix it before moving on — a failing increment is not progress.
4. **Commit & push** with explicit paths (see "Commit and Push Every Increment"). This makes progress durable and lets the user watch the cycle live.
5. **Record & tidy:** capture anything non-obvious in the handoff / `tasks/in-progress.md` for the next agent (see "Maintainability, Consolidation, and Handoff"), leave the tree green and navigable, then **go back to step 1.**

Do not stop to ask "should I continue?" — continuing is the default. If you hit a genuine decision you cannot resolve, pick the safest default consistent with `AGENTS.md` and the project's memories, note the assumption in the handoff, and keep going. Surface real blockers as log lines, not as a halt.

## Arming and Stopping the Loop

The loop is **opt-in** and controlled by a single arming sentinel file: `.claude/loop/ACTIVE` (git-ignored, session-local). Its contents, if any, are the standing goal for the loop.

- **Start:** `bash ../scripts/loop-control.sh start "<optional goal>"` (creates the sentinel and records the arming session as owner).
- **Status:** `bash ../scripts/loop-control.sh status` (shows the goal and whether *this* session owns the loop).
- **Resume in a new session:** `bash ../scripts/loop-control.sh resume` — re-claims ownership for the current session (e.g. after a restart), keeping the goal.
- **Stop (any one is enough):**
  1. `bash ../scripts/loop-control.sh stop` — removes the sentinel; the loop ends cleanly at the next turn boundary.
  2. `rm .claude/loop/ACTIVE` — same effect, manual.
  3. In VS Code / terminal, press **Esc** or **Ctrl+C** to interrupt, then run `stop` to disarm so it does not resume next turn.
  4. Tell the agent **"ループを止めて" / "stop the loop"** in plain language — the agent must then run `stop`.

When the user says stop, actually run the `stop` command (or delete the sentinel). Do not just say you stopped.

**Session-scoped (concurrency-safe).** Several agent sessions can share one working directory (no git-worktree isolation), so `start` also records the arming session's id in `.claude/loop/OWNER`. The Stop hook then blocks **only the session that armed the loop** — a concurrent peer session ending its turn is never trapped. If you want a *different* session to run the loop, `resume` there to take ownership.

## Choosing the Next Improvement

Pick from these sources, roughly in priority order. Prefer the highest user-visible value that you can ship and verify in one small increment.

- The **standing goal** in `.claude/loop/ACTIVE`, if set — that is the user's stated focus.
- `tasks/in-progress.md` and open backlog items.
- Recent `handoffs/` notes: `Open items`, `Skill Candidates`, deferred work.
- The active project's own quality bar and memories (per-project READMEs, `AGENT.md`, recorded standing instructions).
- Concrete quality gaps you can see: missing/weak tests, unhandled error paths, confusing UX, dead code, stale docs, accessibility/robustness holes, inconsistent naming.
- **Maintainability and tidiness** (see the next section): duplicated or near-duplicated files/folders to consolidate, scattered docs to merge, orphaned artifacts to remove, catalogs/indexes that have drifted from reality. Building a thing is not the end of its lifecycle — keeping the workspace navigable is itself high-value work.

When in doubt, improve robustness and tests over adding surface area. Respect any recorded "rejected" / "out of scope" / "do not touch" decisions — do not reopen them. Stay inside the project you were pointed at unless the task clearly spans several (`AGENTS.md` → treat top-level folders as independent).

## Maintainability, Consolidation, and Handoff

**Creating something is not the end of its lifecycle — keeping it maintainable is part of the loop.** An autonomous cycle that only ever *adds* (new files, new folders, new docs) slowly buries the workspace in near-duplicates and drift. Counter that continuously:

- **Consolidate near-duplicates (統廃合).** When you notice two files, folders, or docs that cover the same ground, treat merging them as a valid improvement increment. Pick the one canonical home, fold the unique content in, delete the redundant copy, and update every reference (`grep` for the old path first). Examples: overlapping handoff notes, two READMEs describing one thing, a scratch folder that duplicates a real project, parallel "notes" and "docs" that should be one.
- **Prefer editing/merging over re-creating.** Before writing a new doc or helper, check whether one already exists to extend. A new file is justified only when nothing existing is the right home. Fewer, well-placed files beat many overlapping ones.
- **Remove orphans as you go.** Dead code, stale scratch files, artifacts of abandoned attempts, references to deleted paths — delete them (respecting "do not touch" decisions and never touching another agent's uncommitted work). `bash ../scripts/validate-workspace.sh` surfaces catalog/README drift; treat its warnings as a tidiness worklist.
- **Keep indexes truthful.** When you add, rename, merge, or delete a project or doc, update `tools.json`, `TOOLS.md`, the project README, and any `ai/` index in the *same* increment — a catalog that lies is worse than no catalog. This is the "update the index" step of `AGENTS.md`, applied per-increment.
- **Consolidation is a refactor — do it safely.** It touches multiple files, so it carries the "sweep" and "broken reference" risks. Stage explicit paths only, preserve public contracts (Code Engine signatures, manifest aliases, AppDB/Dataset/FileSet/Workflow names, external APIs), verify references still resolve, and split large merges across several small commits rather than one sprawling one.

### Hand off properly to other AIs

This workspace is worked by many agents (Codex, Claude Code, Copilot, Gemini, …) sharing one file-based contract. Every increment should leave the next agent — human or AI — able to pick up without re-deriving your context:

- **Write the handoff as you finish, not "later."** For any non-trivial increment, append to the current `handoffs/<date>-*.md` (or `tasks/in-progress.md` for live work): what changed, *why*, what was deliberately deferred or rejected, and the exact next step. Convert relative dates to absolute.
- **Record decisions where the next agent will actually look** — a "rejected / out of scope / do not touch" note in the handoff and, when durable, in project memory. This is how the loop avoids re-litigating settled choices.
- **Make handoffs consolidate too.** Handoff notes are prime near-duplicate territory; when several cover one thread, fold them into one canonical note and link related lessons rather than leaving a pile of overlapping dated files.
- **Leave the tree buildable and green.** Never hand off a half-applied refactor or a failing validation as "someone will finish it." Each pushed increment is a clean stopping point on its own.

## Commit and Push Every Increment

**After every increment that passes validation, commit AND push — without asking.** This is a hard requirement of this mode (`AGENTS.md` → Git Workflow makes commit+push the default; here it is per-increment, not once at the end).

- Run `git status --short --branch` and review the diff first. Stage with **explicit paths** — never `git add -A` / `git add .` / `git commit -a`. A concurrent agent's or the user's unrelated changes must not be swept in (this has caused real damage before).
- If unrelated changes are present and cannot be cleanly separated, commit only your explicit paths; leave the rest untouched and note it.
- On `main`, push to `origin/main`. For feature-branch/PR work, push the branch and do not merge without human approval.
- Keep commit messages small and specific, one increment each. Do not bundle several improvements into one commit.
- If push fails, report the exact command and reason, then continue with the next improvement (do not silently drop the failure).

## Safety Rails

Autonomy is not a license to bypass the workspace's safety rules. All of `AGENTS.md` still applies. In particular:

- Never write or commit secrets, tokens, SIDs, dev tokens, `.env` values, or session artifacts. Run `bash ../scripts/check-secrets.sh`.
- Domo deploys are pre-authorized for code changes (`domo publish`) per `AGENTS.md`, but respect the standing constraints in `tasks/shared-notices.md` and project memories: do not delete AppDB documents, mutate production data, or trigger long dataflows against the letter of a notice. For long-running RUNs, follow the "do not block" pattern (`Monitor` to a terminal state) instead of stalling the loop.
- Never sweep unrelated changes into a commit (see above). This is the most common way an autonomous loop causes harm.
- Do not restructure or rename unrelated projects while improving one.
- Public Code Engine signatures, manifest aliases, AppDB/Dataset/FileSet/Workflow names, and external API contracts are high-impact — preserve them unless the user asked for a breaking change; log a warning in the handoff if you must touch one.
- **Back up Domo-side config as you change it.** When an increment creates or changes a Domo object (DataFlow, Workflow, Dataset, App Studio, Code Engine, Pro Code, AppDB), mirror its **sanitized** definition locally in the same increment so GitHub holds the backup — see `domo-config-backup.md`. A deploy without an updated local mirror is an incomplete increment.
- The built-in runaway backstop (below) is a safety net, not a substitute for judgment. If you truly have nothing valuable left to do, say so in the handoff and let the loop idle out rather than making low-value churn commits.

## Convergence check — 「価値ある作業が無い」を客観判定する（工事を捏造しない）

上の「truly nothing valuable → idle」と runaway backstop は、**収束をどう客観判定するか**を各エージェントの主観に委ねている。the original workspace は同一 git identity「Taichi Katoh」で複数エージェント（Codex / 別 Claude / Copilot …）が同時に働くため、判定を誤ると **churn（無価値コミット）か peer collision（並行編集・重複作業）** のどちらかを生む。増分を選ぶ**前**に次を実行して飽和を客観化する:

1. **owned dir の recency scan** — `for d in <owned dirs>; do git log -1 --format='%cr %h %s' -- "$d"; done | sort`。**全 owned が ~24h 以内 touch（多くは 1-3h）＝ readily-takeable 面は fleet に飽和**。最古の dir が数時間内なら「まだ手つかずの地面」は無い。
2. **同一 identity 確認** — `git log --since='3 hours ago' --format='%an'` が全て同じ「Taichi Katoh」＝実体は並行 peer。Monitor の「PEER PUSH」通知や自分の push echo と混同しない。
3. **lane 確認** — `tasks/in-progress.md` と `tasks/shared-notices.md` で明示レーン（例: README衛生 / 特性化テスト重複防止 / API-surface skillization / marketdata / PPA）を読む。狙う軸が既にレーン化＝ in-flight。
4. **false-idle を避ける** — 「直近 3h は README のみ touch」で早合点しない。7 日窓（`git log --since='7 days ago' -- <proj>`）で comprehensively swept か確認する。
5. **判定** — 飽和なら repo 変更を**捏造しない**。収束は handoff に**一度だけ**記録する（handoff/skill は共有ファイル＝二重編集の collision 源。記録済みなら再編集もしない）。verify-and-idle の "verify" は `check-secrets.sh` + `validate-workspace.sh` の green 確認まで。あとは正直に status を述べてターンを閉じ、backstop に委ねる。**clean discovery/verification pass は valid outcome**。zero-collision な価値作業（private memory 追記、実際に空いた lane の作業）だけ可。

これは「何もするな」ではなく「飽和した地面に無理やり増分を作るな」。peer lane が実際に**空いた**瞬間（recency scan で 1 つだけ古くなる等）に実作業へ復帰する。特性化テスト等の重複防止は `tasks/shared-notices.md` の協働ノートに従う。

## Harness Enforcement (Claude Code) and Tool-Agnostic Note

On **Claude Code**, a `Stop` hook (`../scripts/loop-stop-hook.sh`, wired in `.claude/settings.json`) enforces the loop mechanically:

- It fires when the agent tries to end its turn. If `.claude/loop/ACTIVE` exists, it exits `2`, which **blocks the stop** and feeds the continuation instruction back to the agent. If the sentinel is absent, it exits `0` (a no-op — normal sessions are unaffected). It also exits `0` in `plan` mode so plan review is never fought.
- **Session-scoped:** when `.claude/loop/OWNER` records the arming session's id, the hook blocks **only that session** — a concurrent peer session ending its turn exits `0` and is never dragged into the loop. If the firing session's id can't be determined, the hook errs toward *not* trapping it. With no `OWNER` recorded (e.g. a manual `touch`), it falls back to directory scope (blocks any session) for backward compatibility.
- **Runaway backstop:** Claude Code overrides a `Stop` hook after it blocks ~8 times in a row *without progress*. Real work (edits, commits) counts as progress and resets this, so an active loop continues; a loop that is genuinely spinning with nothing to do is released automatically. This is intended safety, not a bug.

Other tools do **not** have this hook. There, this skill is a **behavioral contract**: the agent itself must keep looping per "The Loop" until a stop signal, checking `.claude/loop/ACTIVE` where possible and honoring a plain-language "stop." The `loop-control.sh` helper is tool-agnostic and works anywhere with a shell.

## Validation

Before each commit, run the narrowest useful checks for what you touched, then the workspace safety checks:

```bash
# project-specific first (examples)
python3 -m json.tool <project>/pro-code/manifest.json >/dev/null
node --check <project>/pro-code/app.js
# then always:
bash ../scripts/check-secrets.sh
bash ../scripts/validate-workspace.sh
```

Record which checks ran and which did not. Never commit an increment whose validation you did not actually run or that you know is failing. A green, committed, pushed increment is the unit of progress this loop produces.
