# Domo Magic ETL Skill

Use this when editing dataflow helper scripts, generated dataset files, or Magic ETL JSON, **or authoring a
new dataflow programmatically**. Full per-tile / per-engine catalog: [`../docs/domo-magic-etl-reference.md`](../docs/domo-magic-etl-reference.md).

## Rules

- Document input Dataset names and output Dataset names.
- Distinguish physical Datasets from Views.
- Treat column renames as high-risk because downstream Beast Modes, ETL tiles, AutoML, dashboards, and prompts may depend on them.
- Confirm schema compatibility for AutoML prediction tiles and any downstream model scoring.
- Document whether writes use `REPLACE`, `APPEND`, or `UPSERT`.
- **Prefer native tiles over code tiles (Python / SQL / R) for new work** — usually faster and always more maintainable. See "Prefer native tiles over code tiles" for the evidence and the real exceptions.
- **Maintainability hygiene is mandatory, not optional:** every tile must carry a note (`notes[].body`) explaining *why* it exists, and every tile must sit inside a **Section** on the canvas. See "Mandatory canvas hygiene."
- For Magic ETL JSON changes, follow the full-object workflow: GET full object, mutate, PUT full object, trigger/run, verify.
- Do not trigger production dataflows without explicit confirmation.

## Engines (databaseType / engine)

| Engine value | What it is | Author new work here? |
|---|---|---|
| `MAGIC` | Magic ETL 2.0 (Adrenaline-backed, columnar). Default. | **Yes** — default for all in-Domo transforms. |
| `ETL` | Legacy Magic ETL 1.0 (MySQL-backed). | No — maintenance only. |
| `MYSQL` | SQL DataFlow (MySQL dialect). | Only for existing SQL flows. |
| `REDSHIFT` | SQL DataFlow (Redshift dialect). | Only for existing SQL flows. |
| `ADR` | Adrenaline / Spark-style dataflow. | Rare; existing flows. |
| `JUPYTER` | Jupyter Workspaces dataflow. | Notebook-driven only. |

v2 (`MAGIC`) has **behavior changes** vs v1 that bite silently — see Gotchas.

## Prefer native tiles over code tiles (Python / SQL / R)

**Default to native Magic ETL v2 tiles; reach for a Python/R/SQL scripting tile only when native genuinely
can't express the logic.** This is both a performance and a maintainability rule, and it is what the user
has asked to standardize.

Why (evidence, hedged honestly):

- **Maintainability (the strong, unconditional reason).** A native tile is self-describing in the graph,
  editable in the UI by anyone, versioned as part of the flow, and carries no hidden runtime/library
  dependencies. A Python/R tile is an opaque box: its logic isn't visible on the canvas, it pins a
  container/library version, and only a coder can safely change it. Fewer code tiles = a flow the next
  maintainer (or AI) can actually read.
- **Performance (true in the typical case, not guaranteed).** Native v2 runs on the columnar Adrenaline
  engine; Domo positions it as frequently outperforming even Redshift SQL flows. First-hand on DF3063,
  replacing scripting tiles with native subgraphs kept output **consumer-equivalent** while reducing the
  Python-tile count increment by increment. **Caveat:** the widely-quoted "2–4×" is *v2-vs-legacy-engine*,
  **not** native-vs-Python head-to-head — there is no published head-to-head. Treat "native is faster" as a
  strong default, not a promise; measure when it matters.

Real exceptions — where a code tile is the *right* call (do **not** force these into native):

- **Recursion, simulation, iterative/stateful logic, custom per-row algorithms, string-template
  generation.** One Python tile is clearer and often faster than a dozen native tiles emulating it.
  DF3063's floor of ~10 Python tiles is exactly these cases — nativizing them would *hurt* maintainability.
- **A single SQL statement that replaces many Magic tiles**, when maintainers are SQL-fluent (SQL DataFlow
  with warehouse pushdown is a distinct fast path).
- **Watch the native OOM/ row-explosion traps.** `Join`, `Rank & Window`, and `Remove Duplicates` are the
  costliest native actions; a naive native rewrite can explode row counts (DF3063's native mj-prio hit
  ~157M rows / 70+ min). Native ≠ automatically cheaper at scale.

**When rewriting an existing code tile to native, prove equivalence before deploying:** compare row counts,
key metric sums, and consumer/byte-level output against the prior run (the DF3063 increments did exactly
this — "consumer等価PASS" each time). A native rewrite that changes output is a regression, not a cleanup.


## Authoring API (verified live on maintenance-instance, 2026-09-05)

Base: `/api/dataprocessing/v1/dataflows`. Auth: `X-Domo-Authentication: <SID>` is sufficient for GET, POST
(create), PUT (replace) and run on your own instance — no admin PAT needed. (`X-Domo-Developer-Token` also works
where a dev token exists.)

**Edit an existing flow (full-object workflow):**

1. `GET /api/dataprocessing/v1/dataflows/{id}` → the complete object.
2. Mutate `actions[]` / `outputs[]` in memory. Do **not** re-PUT the volatile `tables` field just to run it —
   raw re-PUT makes every tile look changed and resets input display names to ASCII.
3. `PUT /api/dataprocessing/v1/dataflows/{id}` with the full object.
4. Run: `POST /api/dataprocessing/v1/dataflows/{id}/executions` with body `{}`.
5. Verify (see Validation).

**Create from scratch (verified end-to-end — create → run → correct output):**

- `POST /api/dataprocessing/v1/dataflows` with the full object. The response returns the new `id` and
  **populated `outputs[].dataSourceId`** immediately (the output Dataset is registered on first successful run).
- The top-level `tables` field is **NOT required** for create — the backend computes it.
- A `FixedInput` action (inline `schema` + `rows`) lets you build a flow with **no input Dataset** — ideal for
  self-contained tests and seed tables.
- Minimal viable envelope:

```jsonc
{
  "name": "...", "description": "...",
  "databaseType": "MAGIC", "magic": true, "runState": "ENABLED",
  "engineProperties": { "kettle.mode": "STRICT" },
  "inputs": [],                        // LoadFromVault actions add inputs; FixedInput needs none
  "outputs": [{ "onboardFlowId": null, "dataSourceId": null,
                "dataSourceName": "<out name>", "versionChainType": "REPLACE" }],
  "actions": [ /* see below */ ],
  "gui": { "version": "1.0", "useGraphUI": true, "disabledActions": [],
           "elements": [ /* {id,type:"Tile",x,y} per action */ ],
           "canvases": { "default": { "canvasSettings": {}, "elements": [] } } }
}
```

**Action wiring:** each action `id` = `"<Type>-<uuid>"`. Chain with `dependsOn: [upstreamId]` plus either
`input: upstreamId` (single-input tiles) or `inputs: [upstreamId]` (Publish/Join). Common verified shapes:

- `FixedInput` — inline seed: `schema:[{name,dataType}]`, `rows:[["a","1"],…]` (values as strings), no `input`.
- `ExpressionEvaluator` (Add Formula) — `expressions:[{expression:"`sales` * 2", fieldName:"x2", settings:{}}]`.
  Column refs use **backticks**.
- `GroupBy` — `groups:[{name:"region"}]`, `fields:[{name:"total",source:"sales",type:"SUM"}]`.
- `PublishToVault` (output) — `dataSource:{guid:null,type:"DataFlow",name}`, `versionChainType:"REPLACE"`,
  `schemaSource:"DATAFLOW"`, `inputs:[upstreamId]`.

The full per-tile field lists (Join, Pivot/Unpivot, Rank & Window, Filter, Alter Columns, Python/R, AI tiles,
etc.) are in the reference doc. When unsure of a tile's exact JSON, **GET a live dataflow that already uses it**
and copy the shape — do not guess field names.

## Mandatory canvas hygiene (notes on every tile, every tile in a Section)

Two requirements, mandatory for every dataflow you author or edit (maintainability policy — the flow must be
legible to the next maintainer or AI):

1. **Every tile carries a note** explaining *why* it exists / what business rule it encodes — not a restatement
   of the tile type.
2. **Every tile sits inside a Section** that groups it by pipeline stage.

How these serialize (verified 2026-09-05 against the live production flow DF3063 — 21 Sections enclosing
229 Tiles, **229/229 tiles annotated**):

- **Note** = an object in the action's `notes[]` array:
  `{"x1":null,"y1":null,"x2":null,"y2":null,"body":"① 需要｜… なぜこのタイルが要るか"}`. `body` is the memo
  text; `x1/y1/x2/y2` are the callout-line endpoints (all `null` = the note is anchored to the tile). An empty
  `notes:[]` is a **non-compliant** tile. Write the *why*, and prefer a stage prefix (`① 需要｜…`) so the note
  reads coherently next to its Section.
- **Section** = a canvas element in `gui.canvases.<canvas>.elements`:
  `{"id":"<uuid>","type":"Section","x","y","width","height","name":"② 在庫｜…","backgroundColor":"var(--colorChartGreen6)"}`.
  A tile is a sibling element `{"x","y","id":"<actionId>","type":"Tile","color"}`.
- **Assignment is by GEOMETRY, not a foreign key.** There is **no `sectionId` on a tile.** A tile belongs to a
  Section when its `(x,y)` anchor falls inside the Section's rectangle (`x … x+width`, `y … y+height`). So to
  place a tile in a section you position the Section rectangle to enclose the tile — and "every tile in a
  Section" means every `Tile` element's anchor lies inside some `Section` rectangle. Give Sections distinct
  pastel `backgroundColor`s (`var(--colorChartBlue6)`, `…Green6`, `…Yellow6`, …) and stage names.

Lint it before you PUT (offline, on the GET-ed dataflow JSON):

```python
import json, sys
d = json.load(open(sys.argv[1]))
acts = d["actions"]
els  = d["gui"]["canvases"]["default"]["elements"]
secs  = [e for e in els if e.get("type") == "Section"]
tiles = [e for e in els if e.get("type") == "Tile"]
def inside(t, s):  # tile anchor within the section rectangle
    return s["x"] <= t["x"] <= s["x"] + s["width"] and s["y"] <= t["y"] <= s["y"] + s["height"]
no_note = [a["id"] for a in acts if not (a.get("notes") and (a["notes"][0].get("body") or "").strip())]
orphan  = [t["id"] for t in tiles if not any(inside(t, s) for s in secs)]
print("tiles missing a note:", len(no_note), "| tiles outside every Section:", len(orphan))
assert not no_note and not orphan, "canvas hygiene FAILED"
```


## Output write modes (`versionChainType` / update method)

| Mode | Effect | Notes |
|---|---|---|
| `REPLACE` | Overwrite the whole output each run. | Default; safest for derived tables. |
| `APPEND` | Add rows to existing. | Watch for duplicates on re-run. |
| `UPSERT` (Merge) | Merge on an upsert key. | Requires key column(s). |
| Partition | Partition-based upsert. | Requires partition id column; ~3,000-partition ceiling. |

## Gotchas that cost time

- **v1→v2 behavior changes:** null comparisons use SQL 3-valued logic (any compare with null → null → Filter
  treats as false; use IS NULL); date ops use **company timezone, not UTC**; stricter date parsing;
  `WEEK_OF_YEAR` redefined. Read Domo's "Behavior Changes" before porting a v1 flow.
- **Column ceiling:** max ~1,500 columns per dataflow.
- **Fixed decimals:** precision/scale (19,5) — only 5 decimal places retained.
- **OOM risk:** `Rank & Window` and `Remove Duplicates` are the costliest actions on large flows. A single huge
  Python tile that explodes row counts can get KILLED in production — prefer native tile subgraphs, but mind the
  native Join/Rank&Window/Remove-Duplicates traps (see "Prefer native tiles over code tiles"). Only hard runtime
  limit is completing within a 24-hour window.
- **Federated Datasets** cannot be used as input (Virtual/AppDB-backed are OK).
- **A successful run does not mark output "Updated"** if the data did not actually change.

## Long-running RUN handling (do NOT block on completion)

Some production dataflows take tens of minutes to hours. (DF3063 now runs ≈ 25–26 min after its
native migration + action simplification; the older "≈ 170 min" figure is stale — verified 2026-09-10
across three consecutive SUCCESS executions.) Once a RUN is
triggered **with explicit confirmation**, never stop the session and idle-wait for it to finish, and
never treat "waiting for the dataflow" as a reason to end a turn. Instead:

- Set up **out-of-band monitoring**: a `Monitor` polling `GET /api/dataprocessing/v1/dataflows/{id}/executions/{execId}`
  (or `?limit=1`) until a **terminal** state, and make the filter cover **every** terminal state, not
  just success — `SUCCESS|FAILED|ABORTED|ERROR|CANCELLED`. Silence must never look like success.
- **Keep working** on RUN-independent tasks (offline prototypes/validation against existing output
  datasets, FE wiring, docs, blueprints for the next increment) while the run is in flight.
- Run post-completion verification (`query-dataset.sh` stock-identity / record-type row counts /
  metric sums vs the prior run) only **after** the terminal notification arrives — this fires
  automatically from the monitor; do not sit on the turn waiting for it.
- Trigger a run-only refresh (no redeploy) with `POST .../executions` and an empty body. Do NOT
  re-PUT the canonical definition just to run it (raw re-PUT treats all tiles as changed because of
  the volatile `tables` field and resets input display names to ASCII).

## Validation

- For generator scripts, run syntax checks and small local fixture generation when possible.
- For Domo dataflow changes, record the dataflow ID, execution ID, and verification result when actually run.
- If Domo verification was not run, say so clearly.

## Regression-testing a Python tile without re-deploying (characterization via `domomagic` stub)

To *lock* what a Python tile does now — most importantly a **seeded-reproducibility** contract ("same seed →
same output") — so a later edit can't silently regress it, add a characterization test **without touching the
tile `.py`** (editing tile source forces a DataFlow re-deploy = a gated action) and **without a live DataFlow run**.

The obstacle mirrors the browser `app.js` case (see `domo-procode-app.md` → "Regression-testing the pure security
helpers"): a Magic ETL Python tile is **not** function-wrapped. It runs `from domomagic import *` and then
`read_dataframe(...)` / `write_dataframe(...)` **at module top level**, so there is no pure function to import —
`import`-ing the tile immediately tries to hit `domomagic` and read real Datasets. The tile's *logic*, however, is
deterministic given its inputs.

Technique (stdlib `unittest`, runnable via `python3 <path>` — no pytest dep):

1. Build a fake module: `fake = types.ModuleType("domomagic")` with `fake.read_dataframe` = a fixture dispatcher
   (return `fixtures[alias].copy()` so the tile's `[[...]]` column-selection can't mutate your fixture), and
   `fake.write_dataframe` = a capture (`captured["out"] = df`). Set `fake.__all__ = ["read_dataframe","write_dataframe"]`
   so `from domomagic import *` picks them up.
2. Inject and restore: `saved = sys.modules.get("domomagic"); sys.modules["domomagic"] = fake`; in a `finally`,
   restore `saved` (or `pop` it) so the stub never leaks to other tests.
3. Read the tile source and `exec(compile(source, tile_path, "exec"), {"__name__": "__domo_tile__"})`.
4. Assert on the captured output DataFrame.

Once you have ≥2 sibling tile suites, DRY steps 1–3 into a shared `tests/_tile_harness.py` exposing
`run_tile(dataflow_dir, tile_filename, fixtures)`, and have each suite `from _tile_harness import run_tile`
(prepend `sys.path.insert(0, os.path.dirname(__file__))` so both `python3 <path>` and `unittest` discovery
resolve the sibling import). The fake-`domomagic` inject/restore then lives in one place instead of copy-pasted
per suite. Commit `2e3b7776`.

Lock **contract invariants, not brittle golden digests** — the point is to catch *unintended* regressions while
letting the demo's look be re-tuned freely: determinism (same seed → `df.equals`), seed-actually-drives-output
(a different seed differs — proves the RNG is wired), column names **and order**, row count (= cross-join × grain),
value-range structural bounds (`integers(a,b)` → `[a, b-1]`), sign/ordering invariants (inventory ≥ 0, cost > 0,
`売上原価 < 売上高`), and any regime boundary. A band **derived from a documented range** (e.g. std-cost
`[760,2299]` from base `[800,1999] × [0.95,1.15]`, or implied margin `[0.05,0.40)` with a `1e-6` rounding
tolerance) is locked **with a comment saying "range change → update this too"** — that coupling *is* the
characterization intent, not a defect. `numpy` `default_rng(seed)` (PCG64) is stable across numpy versions, so a
determinism/`equals` assertion is safe.

**Rounding-safe band, not a ratio band.** When the value under test is a *rounded* product
(`act = round(std × multiplier)`), do **not** assert on the *ratio* `act/std` against the multiplier's
`[min,max]` — rounding pushes the ratio just outside the band (observed `[0.9495, 1.3003]` for a `[0.95,1.30]`
design across 240k rows), so a ratio assertion **flakes**. Assert **per row** that
`round(min×std) ≤ act ≤ round(max×std)` — `round` is monotone in `std`, so the bound is exact and non-flaky. For a
**two-regime** (bimodal) value, assert the inter-regime *gap* is empty the same per-row way (normal
`≤ round(1.10×std)` vs variance `≥ round(1.15×std)` ⇒ `(round(1.10×std), round(1.15×std))` must be unpopulated).
Commit `7e71e4f8` / `test_cost_monthly_generator.test_actual_cost_two_regime_variance`.

Reference (proved on one generator project, one suite per tile, 8–9 invariants each — production_daily 9 /
cost_monthly 9 / pl_monthly 8): `mfg-costops-app/tests/test_production_daily_generator.py` /
`test_cost_monthly_generator.py` / `test_pl_monthly_generator.py` (initial suites `03107d13` / `26aa6a80` /
`07c3bbdc`; shared harness `2e3b7776`; later invariants `7e71e4f8` two-regime variance / `ed3d4433` daily grain),
documented in that project's README "テスト" section. This is a *characterization* test — it fixes "what the tile
does now", so it's the regression net you add *before* a refactor (or before nativizing a code tile per "Prefer
native tiles"), not a spec written first.

## Safety

- On shared instances (e.g. `maintenance-instance`), create only clearly-named disposable test assets
  (`zz-...-verify-*`), own them, and delete them when done. Never modify or delete assets you did not create.
- Do not commit SID values, developer tokens, or **unsanitized** dataflow JSON exports (nor publish bundles). A **sanitized** definition mirror — secrets/credentials/PII stripped — *is* committed for backup: see `domo-config-backup.md`.
