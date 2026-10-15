# Documentation Skill

Use this when creating or updating README files, runbooks, catalogs, decisions, templates, or agent-facing instructions.

## Rules

- Separate facts from assumptions. Use "Assumption" or "Unknown" where Domo state has not been verified.
- Keep Domo asset names exact: Dataset alias, AppDB collection name, FileSet name, Workflow alias, workflow start name, Code Engine package alias.
- Do not invent IDs, names, endpoints, or deploy commands.
- Mark stale guidance as `Deprecated` instead of silently replacing it when downstream users may still rely on it.
- Prefer concise tables for catalogs and short checklists for operating procedures.
- Link to source files such as `tools.json`, manifests, README files, and `../docs/`.

## Link & anchor resolution audit

When editing or reviewing docs with internal links or a Contents/TOC block, verify links **resolve**, not merely that targets **exist** — a markdown link `[text](target)` (or `[text](file.md#anchor)`) asserts resolution, so a broken one is a real defect.

- **Resolve relative paths against the containing file's directory**, not cwd or repo root. A missing `../` makes `[x](docs/y.md)` inside `a/b/SKILL.md` 404 even though `a/docs/y.md` exists. When you fix an asymmetric link, check the **reverse** direction too (forward links and back-links break independently).
- **Anchor slugs are renderer-generated — match them byte-for-byte.** GitHub and VSCode (this repo's two renderers) slugify identically: lowercase → strip `& / , ( )` → whitespace → hyphens. Gotcha: `&` **between spaces** yields a **double** hyphen — `## Engines & execution model` → `#engines--execution-model` — because the `&` is stripped but the two surrounding spaces each become a hyphen. A single-hyphen TOC link to such a heading silently 404s on both renderers. Confirm inbound anchor refs repo-wide (`git grep '<file>.md#'`) before renaming a heading.
- **Backtick paths are NOT link assertions — triage by section context.** A backtick-quoted `path` in prose merely *names* a path; existence-checking it is not a valid defect signal on its own (a broad sweep hit ~25% false positives). Refs under **Skill Candidates**, **Open items**, **Files touched (deleted…)**, or inside bug-description prose are aspirational / historical / documented-nonexistent **by design** — pre-exclude those sections before flagging anything.
- **Denominator-backed claims only.** Enumerate the target set first (`git ls-files`), then report `N audited → M broken → K fixed` with every false positive and out-of-scope item triaged explicitly. A "clean" / "exhausted" claim with no denominator is over-claim.

Run `python3 scripts/check-links.py` from the repository root to check relative file links; also check anchors when changing headings.

## Objective-claim drift audit

Docs assert **objective, grep-able facts** about the code beside them, and those facts silently drift as the code moves while the prose stays put. Distinct from the link audit: that checks a `[text](target)` *resolves*; this checks a stated *value* still *matches*. For Domo three-layer apps (Code Engine + Jupyter + Pro Code) whose source is all GATED (CE redeploy / `domo publish` / live domojupyter), the README is often the **only committable non-gated surface** — so this audit is frequently the single legitimate edit an improvement tick can make there.

- **Verify only deterministic, grep-able claims** — public/private function counts (`grep -cE '^def [a-zA-Z]'` / `^def _`), class names and version markers (`grep -nE 'class Foo|v[0-9]+\.[0-9]'`), `manifest.json` `name`/`version`/`datasetsMapping`, documented test counts, and named file/path refs (`git ls-files`). Behavior prose and live-DataSet-schema claims are **out of scope** — not deterministically verifiable, so leave them.
- **MATCH = clean negative → do NOT edit.** Touching a claim that already matches is manufactured churn, not an improvement. **MISMATCH = sync the doc to code reality** — the one legitimate edit.
- **Test counts are the highest-yield, recurring subtype.** Test-add commits are frequent, so the actual count grows while the stated number lags — and it *re-drifts* after every wave (fixing it once is not permanent). Dual-verify before editing: the doc's own documented run command output (`Ran N tests` / `pass N`) **and** static `grep -cE '^\s*def test_'` (py) / `grep -cE '^\s*test\('` (node:test) — both must agree. Prose count and command-example count can drift independently within one file, so grep both.
- **Denominator-backed, enumerate first.** Do not declare this axis "saturated" from your current working set — enumerate every doc carrying the claim (e.g. `git grep -lE 'Ran [0-9]+ tests|pass [0-9]+ /|テスト *[0-9]+ *件' -- '*README.md'`), then report `N enumerated → M drifted-fixed → K matched-untouched → excluded`. Declaring saturation from a partial working set is a false-saturation under-claim — as real an error as over-claim.

## Bilingual Guidance

Japanese documentation is welcome for human users. Keep command names, paths, Domo object names, API terms, and enum values in English when translating them would reduce precision.

## Required Safety

- Do not include secrets, tokens, SID values, cookies, customer-private raw data, or unredacted logs.
- Do not document destructive commands as routine steps. Call out explicit confirmation requirements.
