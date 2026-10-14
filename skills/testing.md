# Testing Skill

Use this when planning, adding, or running checks.

## Safe Test Strategy

- Prefer local syntax, JSON, lint, unit, and dry-run checks before Domo API calls.
- Avoid external API calls unless the user asks for integration verification or the project already has a safe mocked path.
- Do not mutate production datasets, AppDB collections, filesets, workflows, or dataflows without explicit confirmation.
- For Domo-dependent code, document environment variables by name only and never record values.
- Use small fixtures when possible. Do not commit large exports unless they are intentional test fixtures.

## Recommended Checks

- Workspace:

```bash
bash ../scripts/check-secrets.sh
bash ../scripts/validate-workspace.sh
```

- Pro Code app:

```bash
python3 -m json.tool <project>/pro-code/manifest.json >/dev/null
node --check <project>/pro-code/app.js
```

- Python utility:

```bash
python3 -m py_compile path/to/file.py
```

- Documentation-only change:

```bash
bash ../scripts/check-secrets.sh
bash ../scripts/validate-workspace.sh
```

## Running a whole test fleet (health check before a broad refactor, or periodically)

Running many suites at once, **confirm each one actually executed tests** — a green exit code is
not proof of coverage:

- `unittest.main()` exits **0 with zero tests collected**, so `rc == 0` from running a suite file
  only means "nothing failed," not "something ran." A suite silently emptied — an import error
  swallowed, a `TestCase` renamed out of discovery, or the Write-double-nesting corruption that
  lands the body as a bare literal — passes **hollow**. Parse the runner's own count and assert
  **N > 0** per suite; report the fleet as `S suites / T tests`, not just `S green`. Match the
  runner's marker exactly: Python `unittest` prints `Ran N tests` on **stderr**; Node's `node:test`
  prints `ℹ tests N` / `ℹ pass N` with `✔` per case (not TAP's `# tests` / `ok`). A parser tuned
  to the wrong runner silently counts 0 and fires a **false** hollow alarm — verify the format
  before trusting the count.
- Enumerate the target set first (`git ls-files '*test_*.py'`, minus customer / gated / vendored),
  so "all green" is denominator-backed — the suites you *intended* to cover, not the ones you
  happened to run.
- A shell loop's own trailing test can flip the script's exit code (`[ -n "$fails" ] && …` returns
  1 when there are **no** failures, so the harness reports exit 1 on a clean run) — trust the
  printed `pass=/fail=` summary, not the bare `$?`. (Same false-signal family as grep exit 2.)

## Characterization tests for un-editable source (deployed CE / gated / vendored)

Deployed Code Engine modules, gated FE/CE source, live Magic ETL tile scripts, and vendored
libraries cannot be edited without a gated redeploy — but their **pure helpers** (serializers,
selectors, predicates, normalizers) can still get zero-network regression coverage. Import or
textually extract just the helper, exercise it in isolation, and freeze current behavior so a
later behavior-preserving refactor stays green and any change goes red. The test file never
touches the source, so **no redeploy is required** (tests are additive / harness-read-only).

**Python (single-file utility or class):**

- If the logic is already a method that depends only on its args (e.g. `_select_targets`),
  import the class and call it after `__init__` — provided `__init__` does no network I/O.
- For an orchestration method that *does* call the network, shadow the network methods with
  **instance attributes**: `locker.search_beast_modes = lambda: items`. Because the method
  calls `self.search_beast_modes()` / `self.lock_one`, an instance attribute shadows the class
  method → zero network. Assert on counts (order-independent, so ThreadPool completion order
  doesn't matter). Pin cross-method **stringly-typed contracts** here: e.g. `run()`'s success
  count silently drops to 0 if `lock_one`'s returned status string stops matching
  `success_status` — no exception, so only a test catches it.
- For a deployed CE `.py` whose source must not change, register a `codeengine` stub in
  `sys.modules` **before** `exec_module` (the module imports it at load time), use a scriptable
  fake for `send` (returns queued responses), and rebuild fixtures per test so cases can't leak
  state into each other.
- **Coverage-measurement caveat — don't gauge a closure-nested CE module by `def`-name-in-test.**
  The nested helpers are reached only through the public dispatcher (`*_api(operation=…)`), so
  their names never appear in the suite even when fully path-covered — measure by which
  operations the dispatcher drives, not by name presence (same false-coverage-signal family as
  the hollow-pass guard above: a count against the wrong unit of measure). The canonical
  review-lens treatment, with the denominator-backed proof, is in `code-review.md` →
  "CE closure coverage: audit by API path, not `def`-name"; this is its testing-side pointer.

**JavaScript (deployed CE / app.js with nested helpers):**

- The helper is often a nested `const NAME = (...) => {...}` inside an async function that opens
  with `require('codeengine')`, so exec-ing the whole file hits the runtime. Instead extract
  just the declaration and eval it in `node:vm` (no DOM / no network): block body → brace-match
  from `{`; expression body → up to the first `;`. Prepend dependency consts **in dependency
  order** (`const` is not hoisted): `load('toCsv', ['csvEscape'])`.
- **IIFE-closure gotcha:** an argless IIFE `const x = (() => {...})()` that closes over an
  *outer* parameter (e.g. `columnsHint`) can't be pulled as a named const. Brace-match the arrow
  body and wrap it into a parameterized function: `(columnsHint) => (() => {...})()`
  (soccer-team-tools `loadResolveColumnsHint`).
- **Cross-realm gotcha:** vm-context objects/arrays carry the sandbox's prototype, so
  `assert.deepStrictEqual` fails on prototype identity even when contents match. Shallow-copy
  into the test realm first — `const plain = (o) => (o && typeof o === 'object' ? {...o} : o)`;
  for arrays compare `[...out]`. `Array.isArray` works cross-realm.
- Reference implementations: `beast-mode-manager/tests/test_bm_bulk_lock.py`,
  `soccer-team-tools/code-engine/tests/test_save_service_serializers.js`.

**Pin the seam, not the incidental.** Characterize the *contract* (return keys, sentinel-on-invalid,
count semantics, the status strings two methods agree on) so a behavior-preserving refactor stays
green. When you find a latent-but-unreachable defect in gated source (e.g. a missing
`Array.isArray` re-check that current callers never trigger), pin the **current** behavior with a
⚠-commented test rather than "fixing" it in the test — that way any future fix in the gated source
must deliberately update the test (it can't change behavior silently). This is the test-side
complement to the flag-don't-fix discipline for gated code.

For a function that performs **several sequential mutations** (PUT columns then PUT description;
upload → commit → index), pin each mutation boundary *independently* — a "first write fails" test
(`raise_on={("put",0)}`) does **not** cover "first write succeeds, second fails"
(`raise_on={("put",1)}`), the ordering that exposes a non-atomic partial-success discard. See
`code-review.md` → "Non-atomic multi-step mutation" for the review-side treatment and proven hit.

## Reporting

Always state:

- Checks run.
- Checks skipped and why.
- Domo environment checks not performed.
- Residual risk after testing.
