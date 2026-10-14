# Code Review Skill

Use this when the user asks for review, PR review, risk review, or validation of another agent's work.

Lead with findings. Focus on bugs, regressions, broken contracts, missing validation, and deploy risk.

## Review Priorities

- Existing behavior: Does the change contradict the current README, manifest, prompt, workflow, or public function contract?
- Public API: Are function names, signatures, return keys, manifest aliases, Dataset names, AppDB names, FileSet names, or Workflow names changed unexpectedly?
- Domo safety: Could the change write, delete, deploy, publish, or mutate production data without explicit confirmation?
- Secrets: Are tokens, SIDs, cookies, `.env` values, API keys, private keys, or downloaded session artifacts exposed?
- Error handling: Are external API calls, Domo API calls, parsing, uploads, and workflow triggers handled with clear failures?
- Logging: Are logs sufficient for diagnosis without exposing sensitive data or excessive payloads?
- AI-facing outputs: Are states and return keys unambiguous for downstream prompts and agents?
- Tests: Are local checks, dry runs, or project-specific validations present for the risk level?

## High-signal heuristics (workspace-proven)

These lenses have each caught real, committed bugs in the original workspace. Apply them whenever the
change touches a multi-branch parser / normalizer / allowlist / dispatcher, or a shell
script that sweeps or greps.

### Sibling-branch contract consistency

A defensive function usually declares a contract — "invalid input → sentinel",
"unknown shape → drop (allowlist / default-deny)", "failure → `return`, not `exit`". That
contract must hold in **every** branch. Walk each branch of the construct and check it
against its siblings: a branch that instead raises, passes a value through via `str(x)`,
`exit`s where siblings `return`, or is simply **dead** (can never execute) is the smell.
The failure is amplified when the function runs over a batch (`.map` / `sort` / loop):
one non-conforming value takes down the whole operation, not just its own row.

The same lens applies **across sibling scripts**, not only across branches inside one
function. A family of tools that hit the same endpoint (`list-X` / `query-X` / `diagnose-X`)
should handle a malformed or auth-expired response identically — if two of them detect the
error shape and print the raw response while a third silently degrades to an empty result,
that third is the non-conforming sibling. Grep the family for the shared parse idiom and
diff how each one treats the unhappy path.

A third variant is **safety-affordance asymmetry** across siblings of differing blast
radius. When two sibling tools do comparable work but one is destructive (permanent delete,
overwrite) and the other is not, the destructive one should carry **at least** the safety
affordances of the safer one — a `dry_run` / preview, a confirmation gate, a path-containment
check. A destructive sibling that *lacks* the preview its non-destructive sibling already has
is backwards: the dangerous tool is the one that most needs "show me what you'd do first."
Diff the constructors and the run/execute paths across the family and flag the missing guard
on the higher-blast-radius member. (Unlike the other two variants — where a branch has the
*wrong* contract — here the contract is simply *absent* on the member that needs it most.)

Proven hits:
- `backup_dataset_schema.sanitize_schema` — a non-dict column element was folded into the
  output name via `str(col)`, leaking inner values (e.g. list-of-list PII) through an
  allowlist that claimed "default-drop" (`583eb17c`).
- `appdb-prune-latest.parse_dt` — the numeric branch called `fromtimestamp` unguarded while
  the string branch had try/except → one out-of-range epoch crashed the entire prune and its
  post-delete verification fetch (`e6dd149e`).
- `lib/common.sh` `domo_load_mcp_auth` — used `exit 1` while sibling auth loaders
  (`domo_find_python` / `domo_load_auth`) `return 1`; `exit` in a sourced library kills the
  caller's shell and is uncatchable in `if domo_load_mcp_auth` (`fc2ac892`).
- `asset_lifecycle` delete E2E — a cleanup branch that could never run (dead sibling) (`7f8ee6db`).
- `list-datasets.sh` — hit the same `/api/data/v3/…` family as `list-dataflows.sh` / `diagnose-etls.sh`
  but, unlike those two, used a bare `data.get('dataSources', [])` that turned an auth-expired
  **error dict** into a silent empty table — indistinguishable from a genuinely empty instance, so a
  logged-out user reads "0 datasets" as "my instance is empty". Aligned to the siblings' explicit
  `isinstance(...) or 'dataSources' not in data` guard that dumps the raw response (`e6d6bbb6`). This
  is the cross-script case: the bug was invisible reading the file alone and only obvious against its
  siblings.
- `fs_bulk_transfer._run_download` / `_run_upload` early-return — a defensive CWE-22 guard
  (`_resolve_local_path`→None on absolute/`..` paths) started appending a **new** `status="error"`
  entry to `results`, but the early-return summary still hardcoded `{completed:0, errors:0}` while the
  non-empty-targets sibling derived counts via `_summarize_results`. When *every* remote file was
  rejected, `targets` was empty → early return → the tool reported `errors:0`, the exact opposite of
  the truth (all rejected). Unified both branches through `_summarize_results` (`853bf531`). This is
  the **defensive-code-adds-a-status** variant: introducing a new `status`/error kind upstream
  obligates you to audit *every* aggregation branch that reads status — a constant shortcut
  (`errors:0`) in one branch goes silently stale the instant a new status appears, and the failure is
  worst on the all-rejected path where correct counting matters most.

### grep-exit=2 false-clean in shell sweeps

`grep PATTERN "$f" || echo none` treats grep's exit 2 (file unreadable / bad option) exactly
like exit 1 (no match), so a real error is silently reported as "clean". When reviewing shell
that gates on grep, require the three cases be split — `rc=$?; case $rc in 0) … ;; 1) … ;; *) error ;; esac`
(exit ≥2 is never "no match") — and confirm any "0 results / clean" claim is backed by a
positive existence check, not merely a non-matching grep. The same caution applies to any
`cmd || fallback` where `cmd` has more than one nonzero exit meaning.

### Mutate-before-validate (partial artifacts + blocked retry)

A script that performs a side effect — `mkdir`, a file write, a network `POST`/`DELETE` —
**before** it has validated all of its inputs leaves partial artifacts behind the moment a
later input turns out to be invalid. The damage compounds when an early pre-existence guard
(`if [[ -e "$PROJECT" ]]; then … exit 1`) then refuses to re-run over that half-built state,
so the tool wedges until someone manually removes it. Walk the script top-to-bottom: any input
that a *later* branch can reject — a trailing `case … *) exit 1`, a late `raise ValueError` —
must be validated **before** the first side effect. The idiom is "validate every input up
front, then act" (入力検証は副作用の前に). Keeping the late branch as a defensive default is
fine; just don't let it be the *only* check. (This is the ordering-in-time complement to
sibling-branch consistency: there the branches disagree on the contract, here a correct check
simply runs too late to prevent the mess.)

Proven hit:
- `scaffold-project.sh` — an unknown `KIND` was only rejected by the `case` *after* the
  `mkdir` and the README / AGENT / docs / scripts writes, so a typo left a half-scaffolded
  directory and then the opening `[[ -e "$PROJECT" ]]` guard blocked every retry until a
  manual `rm`. Fixed by validating `KIND` between the existence guard and the first `mkdir`
  (`cf29ce8e`).

### Non-atomic multi-step mutation (early success discarded on a later step's failure)

A handler that performs **several sequential writes** — PUT columns then PUT description; POST
upload, commit, then index — under a single outer `try/except` with no rollback will, when a
*later* step throws, propagate that exception and return `{"error": …}` **discarding the fact
that an earlier step already succeeded**. The remote is now half-updated, yet the returned shape
says nothing happened: a `columns_updated: True` that was set gets dropped from the result dict.
The caller can't tell "nothing ran" from "step 1 landed, step 2 failed", so a retry re-does step 1
or the partial state goes unnoticed. When reviewing a function that mutates more than once, ask
what the return value says after each *interior* failure — make the sequence atomic, or return
per-step status so the caller can resume; don't collapse a partial success to a bare error. (The
state-axis cousin of mutate-before-validate: there a side effect precedes validation, here a
recorded success is erased by a later step's failure.)

**Coverage-ordering trap (test side):** an existing "step 1 fails" test (`raise_on={("put",0)}`)
looks like it covers the write-failure surface, but the non-atomic case is "step 1 **succeeds**,
step 2 fails" (`raise_on={("put",1)}`) — a structurally *different* ordering the first test never
exercises. Pin each mutation boundary independently; one failing-write test is not coverage of an
N-write sequence. (Same false-coverage-signal family as the CE-closure and hollow-pass guards in
`testing.md`: green on the case you tested says nothing about the ordering you didn't.)

Proven hit:
- `ai_metadata_utils.py` (deployed CE = gated) — `process_ai_generation_result` PUTs the column
  dictionary (setting `columns_updated=True`), then PUTs the dataset description with **no** inner
  `try/except`; a description-PUT failure propagates to the outer handler and returns
  `{"error": …}`, dropping the already-committed `columns_updated`. The pre-existing
  `test_put_failure_on_columns_returns_error` only failed the *first* PUT, so this ordering was
  untested. Pinned the current non-atomic behavior (source gated → flag-don't-fix) with a
  ⚠ characterization test that fails the *second* PUT (`b73613b4`).

### Unreachable guard under `set -e` (extraction raises before the check)

A friendly "empty → explain and `exit 1`" guard only runs if the value it checks was
actually *assigned*. Under `set -euo pipefail`, a command substitution
`VAR=$(… | python -c "d['key']")` whose inner command raises (`KeyError`,
`JSONDecodeError`) makes the **assignment itself** trip errexit, so the script aborts with a
raw traceback *before* the `[[ -z "$VAR" ]]` guard on the next line can fire. The guard is
dead code on exactly the most common failure branch — e.g. an expired/invalid token where the
API returns an error object with no `access_token` key. The fix is a contract choice: the
extraction must return a **sentinel** (empty string), not raise — `d[k]` → `d.get(k, '')` —
so the guard becomes reachable and can print the next step. When reviewing shell that
"extract, then validate", confirm the extraction cannot raise on the unhappy path; a `[[ -z ]]`
below a raising extraction is decoration. (Time-axis cousin of sibling-branch consistency: the
friendly-guard contract is *absent on the most common failure branch* because an earlier line
preempts it — and the cousin of mutate-before-validate, where a correct check simply runs too
late. Watch the piped `$?` caveat too: in `VAR=$(a | b)` only `b`'s failure is seen unless
`pipefail` is set.)

Proven hit:
- `authenticate.sh` — `refreshToken` / `access_token` / `sid` were extracted with `[key]`
  subscripts, so an expired-token error response (no `access_token` key) raised `KeyError` and
  aborted under `set -e` before the existing `[[ -z ]]` "run `domo login` again" guards could
  fire (the user saw a raw Python traceback instead of the next step). Switched the three
  extractions to `.get(key, '')` so the guards are reachable, and added the missing
  `refreshToken` guard (`ad396129`).

### CE closure coverage: audit by API path, not `def`-name

A Domo Code Engine module is typically **two** top-level defs — a `_service()` factory that
builds and returns a dict of nested helpers, and the `*_api(operation, request_json)` entry
point — with all the real logic living in **nested** helpers inside `_service()`. Auditing
that module's test coverage with a `def`-name grep ("is `^\s*def NAME` referenced in the test
file?") produces **false "untested" hits**: the nested helpers are never imported by name;
they run transitively through the public `*_api` path (`REGISTER` / `CORRECT` / `RECALCULATE`
/ …). A well-built CE test may even rebind them explicitly — `_TOOLKIT = SERVICE._service()`
— to pin individual helpers, and their names *still* never appear as `import` targets. So
judge CE coverage by **which operations the tests drive through `*_api`** (and what the
rebound `_TOOLKIT` pins), never by nested-`def`-name presence — a "N helpers untested!" review
comment built from a name grep is almost always wrong for a CE module.

Proven: a `^\s*def` vs test-text grep flagged **15** "untested" nested helpers across
`equipment_service` (11 nested / 2 top-level) and `asset_lifecycle_service` (63 / 2) that are
in fact fully path-covered; the identical grep found **0** in the standalone-CLI utilities
(`fileset-manager` / `beast-mode-manager`), where every helper *is* module-level and
name-referenced — so the false-positive is specific to the closure-factory shape, not a
property of the grep itself.

## Output Shape

For a review response:

1. Findings ordered by severity with file and line references.
2. Open questions or assumptions.
3. Brief summary only after findings.
4. Validation gaps and deploy readiness.

Use "No findings" only when you have actually inspected the relevant files and found no material issue.
