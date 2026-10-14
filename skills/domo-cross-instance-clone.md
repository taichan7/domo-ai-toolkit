---
name: clone-content
description: Clone Domo objects (App Studio Apps, Pro Code Apps, Magic ETL Dataflows, Workflows) from one Domo instance to another. Handles dataset ID bridging by name/column matching on the target, workflow environment variable migration, ADR Databricks-integration prerequisites, layout/TABS reconstruction, image/PDF tile cloning, and emits manual-task checklists when API/CLI cannot complete a step. Trigger on phrases like "clone this app to <instance>", "copy this workflow to <instance>", "move this dataflow to <tenant>", "replicate <object> from modocorp to <target>", "promote this to production". Skip for single-instance CRUD (use object-specific skills) and dataset copying (never supported — target must already have data).
---

# Clone Content Between Domo Instances

## Purpose

Replicate Domo objects from a **source instance** to a **target instance** with byte-for-byte parity except for identifiers. The central problem is **identifier translation**: every object embeds instance-specific IDs (dataset UUIDs, card IDs, workflow handles, page IDs, beast-mode templateIds, Code Engine package UUIDs, file IDs, document IDs) that are not portable. This skill gives Claude a deterministic recipe to extract those IDs, remap them against the target, and recreate the object — with explicit manual-task callouts whenever an API path doesn't exist.

Object types covered, in the order they typically need to be cloned (prerequisites first):

1. **Datasets** — never copied; bridged by name + column signature (Section 3).
2. **Filesets** — shell + content copy (Section 4).
3. **AppDB collections** — schema clone, optional document seed (Section 5).
4. **Code Engine packages** — re-author custom packages on target (Section 6).
5. **Magic ETL Dataflows** — including ADR engine with Databricks integration (Section 7).
6. **Workflows** — full v2 lifecycle including release (Section 8).
7. **Pro Code Apps** — `domo publish` from source bundle (Section 9).
8. **App Studio dataapps** — shell + views + layouts + cards + variables + tiles (Section 10).
9. **Native KPI cards** — definition-driven id-swap (Section 11).

## Core principle: ID-only swap

**Between two Domo instances, the only differences should be IDs.** Every other byte of an object's definition is portable.

The lossy alternative — building a target body from a SUBSET of source fields and re-deriving the rest — drops every field you didn't explicitly carry over: chart overrides, conditional formats, dynamic titles, layout style flags, hide-flags, fitToFrame, and dozens of others. That pattern is **deprecated**. Use it only when the source definition isn't accessible.

The canonical clone pattern, for every object type:

1. **Pull the source's full write-ready definition** — use whichever endpoint returns the same shape the UI sends on save (e.g. `PUT /api/content/v3/cards/kpi/definition` for cards).
2. **Walk the entire tree and rewrite IDs only**: dataset UUIDs, card URNs, formulaIds, templateIds, page IDs in drillpath, columnPositions, variable IDs, document IDs, package IDs, fileset IDs.
3. **Apply read→write shape conversions** the read endpoint forces but the write endpoint doesn't accept (formulas array → object, conditionalFormats array → object, etc.).
4. **Strip read-only fields** the target will allocate fresh (urn, id, created, modified-by, etc.).
5. **POST/PUT to target.** Capture the new ID. Persist it in the mapping table for downstream references.

## When to invoke

Trigger keywords from the user: **clone, copy, replicate, move, promote, migrate, between instances**, "from X to Y", "into another instance".

Before any read, confirm these four facts and write them down for the run:

| Fact | Example |
|------|---------|
| Source instance hostname | `source-instance.domo.com` |
| Target instance hostname | `modocorp.domo.com` |
| Object kind | App Studio / Pro Code / Dataflow / Workflow |
| Source object identifier | dataapp ID, design ID, dataflow ID, model ID |

If any of the four is missing, ask the user before doing anything else.

**Do not invoke** for:
- Single-instance CRUD — use `magic-etl`, `magic-etl-cli`, `workflow`, `app-studio-pro-code`, `card-creation`, `variable-creation` directly.
- Dataset copying — never supported. See [Section 3](#section-3--dataset-bridging) for why.

## Process meta-rule: scan available skills FIRST

Before guessing endpoint shapes, asking for DevTools captures, or improvising recipes, **scan the available-skills list for any skill whose topic matches the current step**. This is the most common failure mode of running this skill: the operator dives into reverse-engineering when a documented recipe already exists. Specifically check for:

| If the step is... | Load this skill first |
|---|---|
| Creating a beast mode | `beast-mode-creation` |
| Creating a card variable / control | `variable-creation` |
| Creating any native KPI card | `card-creation` |
| Anything that talks to the `community-domo-cli` | `community-cli-howto` |
| Dataflow JSON shape (Magic ETL) | `magic-etl-cli` (primary) or `magic-etl` (mixed) |
| Creating an AppDB collection | `appdb-collection-create` |
| Creating a Code Engine package | `code-engine-create` |
| Updating a Code Engine package | `code-engine-update` |
| Filesets + file content copy | `fileset-cli` (CLI) / `fileset-api` (API) |
| Manifest patching for a pro-code bundle | `manifest` |
| First-publish of a pro-code bundle | `publish` |
| App Studio dataapp PUT/layout shape | `basic-app-studio` (start) → `advanced-app-studio` (reference) |
| Sample data generation for missing datasets | `domo-data-generator` |

Loading the right skill *before* attempting endpoint guesses prevents the common 5-wasted-turns-of-trial-and-error pattern.

## Hard constraints

1. **Datasets are never cloned.** The target instance must already have datasets containing equivalent data. Bridging matches by name first, then by column signature.
2. **No partial writes.** If any required mapping is missing or ambiguous and the user does not resolve it, abort before any write to target.
3. **Secret env vars are not transferable.** If a workflow env var looks like an API key, password, or token, do not POST its value — emit a manual-task callout instead.
4. **First-publish discipline for Pro Code Apps.** Always drop the source `id` from `manifest.json` before publishing to target so `domo publish` allocates a fresh design ID.
5. **Engine type must be preserved on dataflows.** If source has `databaseType: "ADR"`, do NOT silently downgrade to `"MAGIC"` — Spark SQL functions won't translate. Either require Databricks integration on target or surface a Spark→MySQL translation manual-task list.
6. **Build target bodies from source's full definition, not a synthesized subset.** See [Core principle: ID-only swap](#core-principle-id-only-swap). The synth-from-subset pattern is deprecated.

> **Large-write delivery — distinct from constraint 2.** When you *do* write a large object definition to target (a full pro-code `app.js`, a big dataflow/workflow JSON, an App Studio layout), write it incrementally: a minimal file with unique placeholders first, then a few small anchored edits, so a truncated response can't leave a half-written file. See `AGENTS.md` → "Writing Large Files". This is about surviving truncation and is **orthogonal** to constraint 2's "no partial writes": constraint 2 forbids shipping a clone with a missing or ambiguous mapping; it does not forbid staging a large write across several edits. A clone must still either complete fully or abort.

## Section 2 — Two-instance auth setup

Most reads and most writes use the **Ryuu refresh token as a developer-token header** — this is exactly what `community-domo-cli` does internally when the ryuu login config has `devToken: true` (verified 2026-05-11 by reading the CLI source at `community_domo_cli/config.py:149-156` and `http.py:36-54`).

**Workflow endpoints are different:** `/api/workflow/v1/...` and `/api/workflow/v2/...` reject the ryuu refresh token with 403. They require a **workflow-scoped admin Personal Access Token** minted via Admin → Authentication → Access tokens. There is no `domo login --admin` flag; the user must paste the PAT into the env.

**One-time prereqs** (per instance):

```bash
npm install -g ryuu
domo login -i <source-host>      # e.g. source-instance.domo.com
domo login -i <target-host>      # e.g. modocorp.domo.com
```

Ryuu stores each session at `~/.config/configstore/ryuu/<host>.json` (filename includes `.domo.com`).

**Per-run env vars**:

```bash
export SOURCE_HOST=source-instance.domo.com
export TARGET_HOST=modocorp.domo.com

export SOURCE_REFRESH=$(jq -r '.refreshToken' ~/.config/configstore/ryuu/$SOURCE_HOST.json)
export TARGET_REFRESH=$(jq -r '.refreshToken' ~/.config/configstore/ryuu/$TARGET_HOST.json)

# REQUIRED ONLY if the run touches workflows on source:
export SOURCE_ADMIN_TOKEN=<workflow-scoped PAT from source Admin UI>

# OPTIONAL — only mint if a target workflow write returns 403:
# export TARGET_ADMIN_TOKEN=<workflow-scoped PAT from target Admin UI>

export DOMO_AUTH_MODE=ryuu-session
```

**Smoke test** both instances:

```bash
curl -s "https://$SOURCE_HOST/api/content/v1/user" -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" | jq '.displayName'
curl -s "https://$TARGET_HOST/api/content/v1/user" -H "X-DOMO-Developer-Token: $TARGET_REFRESH" | jq '.displayName'
```

If either returns 403/401, re-run `domo login -i <host>` for that instance.

**CLI variant** (for endpoints `community-domo-cli` covers directly):

```bash
DOMO_INSTANCE=${SOURCE_HOST%%.*} community-domo-cli datasets list >/dev/null      # source
DOMO_INSTANCE=${TARGET_HOST%%.*} community-domo-cli datasets list >/dev/null      # target
```

The CLI swaps instances by changing `DOMO_INSTANCE` — that's the host's first label (e.g., `modocorp` for `modocorp.domo.com`).

**Why not OAuth-exchange to SID?** The CLI's OAuth flow (POST `/api/oauth2/token` → GET `/api/oauth2/sid`) only works for the in-process CLI session — the refresh token rotates and the exchange fails on re-use from a separate process. Using the refresh token as a dev-token header sidesteps that entirely and matches what the CLI actually does on the wire when `devToken: true`.

See `community-cli-howto` for the full auth troubleshooting checklist.

## Section 3 — Dataset bridging

This is the **core translation step** every other section depends on. Every object you clone has dataset references that must be remapped from source UUIDs to target UUIDs. Data is never moved — only references are translated.

### Algorithm

```
For each dataset reference DR in the source object:
  1. Look up DR on source: name N_src, columns C_src (sorted name+type tuples).
  2. Search target for name match → candidates by name.
  3. If 1 candidate → high confidence, accept.
  4. If 0 candidates → fall back to column-signature match across all target datasets.
     - Exact signature match → high confidence, flag as "name-drift" in notes.
     - No signature match → MISSING (manual task).
  5. If 2+ candidates → AMBIGUOUS, prompt user.
  6. Append to mapping table.
```

### Endpoints (verified 2026-05-11)

Source dataset metadata:
```bash
DOMO_INSTANCE=${SOURCE_HOST%%.*} community-domo-cli datasets schema <dataset_id>
# returns: name, owner, columns[{name, type}], rowCount
```

Target dataset search by name:
```bash
curl -s -X POST "https://$TARGET_HOST/api/search/v1/query" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"entities":["DATASET"],"query":"<name>","count":25}' \
  | jq '.searchObjects[] | {id: .databaseId, name, columnCount, rowCount, providerType: .dataProviderType}'
```

The result dataset UUID lives in `databaseId` (not `id`). For schema-by-id reads prefer `/api/data/v3/datasources/<id>/schema` (works on federated datasets) over `/api/query/v1/datasources/<id>/schema` (returns 403 for federated).

### Special case: federated bronze (Databricks ADC)

When source dataflows have `databaseType: "ADR"` and feed from Databricks ADC catalog tables, the target needs the **same catalog tables federated through a Databricks cloud integration**. Bridge those bronze datasets the same way (by name) — but ensure the prerequisite integration step has happened first. See [Section 7 — Dataflows](#section-7--magic-etl-dataflows).

### Mapping table output

Always present this table to the user before any write:

```
| kind    | alias       | source_id   | source_name | target_id   | target_name        | confidence | notes                          |
|---------|-------------|-------------|-------------|-------------|--------------------|------------|--------------------------------|
| dataset | communities | d14df439-…  | Communities | a7c2bb01-…  | Communities (prod) | high       | name match                     |
| dataset | accounts    | ae43b0f3-…  | Accounts    | —           | —                  | missing    | MANUAL: create on target first |
```

Prompt the user only on `confidence ≠ high` rows. See [docs/reference/dataset-bridging.md](../docs/reference/dataset-bridging.md) for the full algorithm including column-signature hashing and manual-task templates.

### If any row is `missing`

Stop. Emit the manual-task checklist (see [Section 13](#section-13--manual-task-template)). Do not proceed to write any object to target. Resume on next invocation once user confirms dataset is present.

## Section 4 — Filesets

Filesets are storage for AI_AGENT context documents. The `clone-content` skill's prior fileset path only created the target shell; **it did not copy file content**, so AI_AGENT contexts that depended on RAG documents returned empty results.

### Recipe

1. **Inventory source files**:
   ```bash
   curl -s -X POST "https://$SOURCE_HOST/api/files/v1/files/search" \
     -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" -H "Content-Type: application/json" \
     -d '{"filters":[{"fieldName":"filesetId","values":["<source_fileset_id>"]}],"limit":1000}' \
     > /tmp/src-fileset-files.json
   ```

2. **Create target fileset shell** (already documented):
   ```bash
   curl -s -X POST "https://$TARGET_HOST/api/files/v1/filesets" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
     -d '{"name":"<name>","description":"<desc>","connector":"DOMO","aiEnabled":true}'
   # → {"id":"<target_filesetId>",...}
   ```
   `connector` is required (DS-0077).

3. **For each source file**, download the binary and re-upload into the target fileset. The endpoints depend on file type (chunked-upload protocol for large files). Defer to `fileset-cli` / `fileset-api` which document the streaming-upload contract.

4. **Persist** `/tmp/clone-<obj>-filesets.tsv`:
   ```
   source_filesetId  target_filesetId  files_copied
   ```

If any source file fails to download/upload, emit a manual-task to re-upload it via the Domo UI.

## Section 5 — AppDB collections

AppDB collections back card data, hold workflow write-back state, and feed AI_AGENT contexts via their auto-mirror dataset.

### Prereq

If the object being cloned references an AppDB collection (pro-code bundle `collectionsMapping[]`, workflow node config, etc.), create the collection on target **before** any other write that depends on it.

### Recipe (per `appdb-collection-create`)

```bash
cat > /tmp/<collection_name>-collection.json <<EOF
{
  "name": "<collection_name>",
  "syncEnabled": true,
  "schema": {
    "columns": [
      {"name": "<col1>", "type": "STRING"},
      ...
    ]
  }
}
EOF
DOMO_INSTANCE=${TARGET_HOST%%.*} DOMO_AUTH_MODE=ryuu-session \
  community-domo-cli appdb collection-create --body-file /tmp/<collection_name>-collection.json
# Capture the new collectionId.
```

### Gotchas

- **ACL collisions at pro-code placement**: a bundle's `collectionsMapping[].id` pointing at a target-instance collection created on a different datastore than the placement context fails with `DA0095: Illegal Collections mapping. Unavailable Collections`. Workaround: strip `collectionsMapping` from the manifest before publish, then wire alias-to-collectionId via the card-editor UI (or via the placement POST's `collections[]` parameter when supported).
- **Mirror dataset doesn't exist until first document**: a collection's `<collection_name>__APP_DB` auto-mirror dataset (queryable surface used by AI_AGENT contexts) only materializes after the collection has documents. If a cloned AI_AGENT context references the mirror dataset, either insert a one-shot seed document via `community-domo-cli appdb document-create`, or drop the dangling reference and emit a manual-task to re-add when the collection has been seeded.
- **REST collection path uses collection NAME, not UUID**: for `/domo/datastores/v1/collections/<...>/documents` use the collection name. Passing UUID throws `DA0088: Invalid collection name`.

### Persist

```
echo '<source_collectionId>  <target_collectionId>  <collection_name>' > /tmp/clone-<obj>-appdb.tsv
```

## Section 6 — Code Engine packages

Code Engine packages back `serviceTaskNode` and AI_AGENT tool invocations inside workflows.

### Built-in vs custom

- **Built-in packages** (Domo-published, friendly-name IDs like `artificialIntelligence`, `DOMO AppDB Collections`, `DOMO DataSets`) are id-stable across instances — no remap needed.
- **Custom packages** (UUID packageId) must exist on target. The package's `code` field is **not exposed via the GET API** — `/api/codeengine/v2/packages/<id>/versions/<v>` returns metadata only, not source. Custom packages must be re-authored from scratch on target.

### Detect

When inventorying workflow refs, treat any `packageId` matching `/^[0-9a-f]{8}-/` (UUID-shaped) as custom. Friendly names skip the prereq check.

### Re-author on target (per `code-engine-create`)

```bash
curl -s -X POST "https://$TARGET_HOST/api/codeengine/v2/packages" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"name":"...","description":"...","code":"...","environment":"LAMBDA","language":"PYTHON",
       "manifest":{"functions":[{
         "name":"<funcName>","displayName":"...","description":"...",
         "inputs":[{"name":"s","type":"text","dataType":"text","required":true,...}],
         "parameters":[],
         "output":{"name":"result","type":"object","dataType":"object","displayName":"...","description":"..."}
       }],"configuration":{"accountsMapping":[]}}}'
```

**Critical**: `output` is a parameter object with `name`, not a bare type. Missing `name` returns 400.

If user explicitly authorizes, release the package:
```bash
curl -s -X POST "https://$TARGET_HOST/api/codeengine/v2/packages/<pkgId>/versions/1.0.0/release" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH"
```

If the source code is genuinely not available (e.g. the user can't share it), emit a manual-task callout: the user must re-author the package by hand on target.

### Persist

```
echo '<source_pkgId>  <target_pkgId>  <pkgName>' > /tmp/clone-<obj>-codeengine.tsv
```

## Section 7 — Magic ETL Dataflows

Dataflows are fully JSON-defined and round-trip through the API. The reference points to remap are `inputs[].dataSourceId`, `outputs[]`, `actions[].dataSourceId` (for LoadFromVault), and `computeCloud` for ADR flows.

`community-domo-cli` does not currently expose a `dataflows` subcommand — use the raw HTTP path until it does, or defer to `magic-etl-cli` which wraps these calls.

### ADR vs MAGIC engine — preserve, don't downgrade

| Engine | When | Behavior |
|---|---|---|
| `databaseType: "ADR"` | Source uses Spark SQL, Databricks-backed | Requires Databricks cloud integration on target. Do NOT downgrade. |
| `databaseType: "MAGIC"` | Source uses legacy MySQL | Portable across instances. |

**Spark SQL functions that DO NOT translate to MAGIC's MySQL** — flag for manual translation if engine must be downgraded:
- `trunc('MM', col)`, `date_trunc(...)` — use `DATE_FORMAT(col, '%Y-%m-01')` in MySQL
- `add_months(col, n)` — use `DATE_ADD(col, INTERVAL n MONTH)`
- `months_between(a, b)` — use `TIMESTAMPDIFF(MONTH, b, a)`
- `LATERAL VIEW explode(sequence(start, end))` — replace with a generated calendar dataset
- `sequence(start, end)` — same

**Working in both**: `concat(year(col), monthname(col))`, basic `CASE WHEN`, basic aggregations.

### ADR prereq detector (block before any write)

If source `databaseType == "ADR"` AND any `inputs[].dataSourceId` resolves to a Databricks ADC dataset on source, the target needs:

1. A Databricks **cloud integration** configured (capture its UUID for `computeCloud`).
2. The same catalog tables (e.g. `<catalog>.<schema>.<table>_bronze`) **federated as datasets on target** via that integration.

Detector recipe:
```bash
TR=$TARGET_REFRESH
curl -s "https://$TARGET_HOST/api/data/v3/datasources?limit=500&offset=0" \
  -H "X-DOMO-Developer-Token: $TR" \
  | jq '[.dataSources[]? | select(.dataProviderType == "databricks")]'
```

If the result is empty or doesn't cover the source's bronze table names, **abort and emit a manual-task**:
```
[target instance] Configure Databricks cloud integration and federate these source tables as datasets:
  <catalog>.<schema>.<table_a>_bronze
  <catalog>.<schema>.<table_b>_bronze
  ...
Why: Source dataflows are ADR (Spark SQL) and reference these tables. Without the integration, the target dataflow will fail with ADR-4001.
Verify:
  curl -s "https://$TARGET_HOST/api/data/v3/datasources?..." | jq '...names...'
```

### Flow — clone an ADR or MAGIC dataflow

1. **Re-fetch source definition** with ryuu refresh (dataflow GET works without admin PAT):
   ```bash
   curl -s "https://$SOURCE_HOST/api/dataprocessing/v1/dataflows/<src_dfid>" \
     -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" > /tmp/dfdef-<id>.json
   ```

2. **Strip source-instance identity fields**:
   ```
   id, dapDataFlowId, created, modified, lastExecution, executionCount, executionSuccessCount,
   hydrationState, container, onboardFlowVersion, editable, numInputs, numOutputs, abandoned,
   deleted, responsibleUserId, passwordProtected, subsetProcessing, triggeredByInput,
   useLegacyTriggerBehavior, neverAbandon, paused
   ```

3. **Bridge inputs** via Section 3 on every `inputs[].dataSourceId` AND every `actions[]` whose `type == "LoadFromVault"` carries a `dataSourceId`.

4. **Null output IDs; suffix names**:
   ```python
   for out in df["outputs"]:
       out["dataSourceId"] = None
       out["dataSourceName"] = out["dataSourceName"] + "_<suffix>"
   for a in df["actions"]:
       if a["type"] == "PublishToVault":
           a["dataSource"]["guid"] = None
           a["dataSource"]["name"] += "_<suffix>"
           a["dataSource"].pop("cloudId", None)
   ```
   Suffix is whatever distinguishes target outputs from any existing static-CSV copies (e.g. `_modocorp`).

5. **For ADR flows**, set required engine fields:
   ```python
   df["databaseType"] = "ADR"
   df["settings"] = {"sqlDialect": "ADRENALINE"}
   df["computeCloud"] = "<target Databricks integration UUID>"
   ```
   Stripping `computeCloud` or `settings` produces flows that CREATE fine but fail at RUN with `ADR-11: unable to create single use connection`.

6. **POST to target**:
   ```bash
   curl -s -X POST "https://$TARGET_HOST/api/dataprocessing/v1/dataflows" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
     --data-binary @/tmp/dfdef-<id>-target.json
   ```
   Response carries the new `id` AND `outputs[].dataSourceId` populated immediately (no first-run wait needed for IDs — only for data).

7. **Match outputs by NAME, not array position.** The CREATE response's `outputs[]` may return entries in a DIFFERENT order than source. Mapping `src_outputs[i] → tgt_outputs[i]` SWAPS UUIDs and downstream dataflows fail mysteriously (e.g. DP-50000 with a row count > 0). Always match by `dataSourceName`.

8. **Run + poll**:
   ```bash
   curl -s -X POST "https://$TARGET_HOST/api/dataprocessing/v1/dataflows/<tgt>/executions" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" -d '{}'
   # then poll executions?limit=1 until state in (SUCCESS, FAILED_DATA_FLOW, FAILED). Timeout 30 min.
   ```
   On FAILED_DATA_FLOW, capture `errors[].localizedMessage` + `_actionId` and surface to user. Don't auto-retry.

### Dependency ordering

If df B's inputs include df A's outputs, run A to SUCCESS before transforming B (so the bridge map can include A's new output UUIDs).

### Persist

```
echo 'src_dfid  tgt_dfid  executionId  final_state  output_uuids...' > /tmp/clone-<obj>-dataflows.tsv
```

See [docs/reference/adr-dataflow-clone.md](../docs/reference/adr-dataflow-clone.md) for full ADR field reference and the Spark→MySQL translation cheatsheet.

## Section 8 — Workflows

### Auth (REQUIRED)

`/api/workflow/v1/*` and `/api/workflow/v2/*` reject ryuu refresh tokens with 403. You need a **workflow-scoped admin Personal Access Token** for source reads and target writes:

```bash
export SOURCE_ADMIN_TOKEN=<source admin PAT>
# Mint TARGET_ADMIN_TOKEN only if a write returns 403 with $TARGET_REFRESH:
# export TARGET_ADMIN_TOKEN=<target admin PAT>
```

Mint via Admin → Authentication → Access tokens in each instance's web UI. There is no CLI flag for admin tokens.

### Endpoints (verified 2026-05-12)

| Purpose | Method | Path | Auth |
|---|---|---|---|
| List models | GET | `/api/workflow/v1/models` | admin PAT |
| Get model metadata + version list | GET | `/api/workflow/v1/models/<modelId>` | admin PAT |
| Get a version definition (v1) | GET | `/api/workflow/v1/models/<modelId>/versions/<version>` | admin PAT — returns `savedJson` stringified |
| Get a version definition (v2) | GET | `/api/workflow/v2/models/<modelId>/versions/<version>/definition` | admin PAT — returns parsed JSON |
| Create model shell | POST | `/api/workflow/v2/models` | admin PAT or ryuu refresh on target |
| Save (overwrite) version definition | PUT | `/api/workflow/v2/models/<modelId>/versions/<version>/definition` | admin PAT or ryuu refresh on target |
| Release version | POST | `/api/workflow/v2/models/<modelId>/versions/<SemanticVersion>/release` | admin PAT or ryuu refresh on target |

**Note**: target writes (POST/PUT) succeeded in PE Ops clone with the ryuu refresh token; only source reads required the admin PAT. If a target write 403s, mint `TARGET_ADMIN_TOKEN` and retry.

### Model shell create

```bash
curl -s -X POST "https://$TARGET_HOST/api/workflow/v2/models" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"name":"<name>","description":"<desc>","versions":[{"version":"1.0.0"}]}'
# → {"id":"<modelId>","versions":["1.0.0"],"activeVersions":[],...}
```

### PUT version definition — overwrite mechanic

When only `1.0.0` exists on a freshly-created model, PUT to `1.0.0` **OVERWRITES it in place** (no draft `1.0.1` is created). When multiple versions exist, PUT to the highest version creates a new draft above it. The release path requires the SemanticVersion string (e.g. `1.0.0`), NOT the integer `versionNumber` returned in the PUT response.

```bash
curl -s -X PUT "https://$TARGET_HOST/api/workflow/v2/models/<TARGET_MODEL_ID>/versions/1.0.0/definition" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  --data-binary @/tmp/wf-<source_id>-definition-target.json
```

### POST release

```bash
curl -s -X POST "https://$TARGET_HOST/api/workflow/v2/models/<TARGET_MODEL_ID>/versions/1.0.0/release" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" -d '{}'
# → {"modelId","version":"1.0.0","active":true,"startEventId","manualTriggerId","releasedAt",...}
```

Capture `version` (the released version string the response gives back — pro-code bundles need this in `workflowsMapping[].version`), `startEventId`, `manualTriggerId`.

Pre-release validation rejects refs to Code Engine packages that don't exist on target. Run Section 6 first.

### Flow

1. **Create model shells** for every source workflow before any other writes (per the prereq-first phase ordering — pro-code bundles' `workflowsMapping[].modelId` need to be target UUIDs).
2. **GET source definitions** with admin PAT for each `(srcModelId, srcVersion)`. Save `savedJson` parsed.
3. **Inventory cross-instance refs** (datasets, persons, groups, secret-text env vars, Code Engine package UUIDs, fileset IDs, AppDB collection IDs). See [docs/reference/workflow-env-vars.md](../docs/reference/workflow-env-vars.md) for the walking algorithm.
4. **Bridge** every dataset/person/group/package/collection/fileset ref via the appropriate section's map. Build a single mapping table.
5. **Redact secrets** (`paramName` matches `/(?i)(secret|password|token|apikey|api[-_]?key|credential|auth|bearer|private[-_]?key)/`) — set values to `""` and emit a manual-task for each.
6. **Strip identity fields**: top-level `owner`, `createdBy`, `createdOn`, `updatedBy`, `updatedOn`, `modelId`.
7. **PUT to target** at `versions/1.0.0/definition` (overwrites the empty 1.0.0 the model-shell POST created).
8. **Release** via POST `/versions/1.0.0/release`.
9. **Persist** to `/tmp/clone-<obj>-workflows.tsv`:
   ```
   source_modelId  target_modelId  released_version  startEventId  manualTriggerId
   ```

### Manual task on secret env vars

```
[target instance] Re-enter workflow env var <paramName> in workflow "<name>".
Why: Secret values are not transferable across instances.
Verify: Open workflow editor → Variables panel → confirm value is set.
```

See [docs/reference/workflow-env-vars.md](../docs/reference/workflow-env-vars.md) for `dataList`/`designElements` walking and reference-type breakdown.

## Section 9 — Pro Code Apps

Pro Code Apps are **source-repo or source-bundle driven**: the source of truth is the developer's repo OR the downloaded bundle ZIP from the Asset Library, and the instance only stores the published bundle plus a design ID. "Source-driven" does **not** mean "no API involved," though — the bundle is **uploaded via the designs REST API** (`POST /api/apps/v1/designs/{id}/versions/{version}/assets?path=<relpath>`, manifest.json first then each globbed file), so a (re)publish works with **any valid Domo auth** — a SID minted from an OAuth refresh token, or an `X-DOMO-Developer-Token` — with **no** `domo` CLI and **no** interactive browser login. `domo publish` (ryuu) is just a thin client over that API, so neither an OAuth-only instance nor a busy shared ryuu session blocks publishing. See [skills/domo-procode-app.md](../skills/domo-procode-app.md) "## Publishing a design" for the REST publisher mechanics.

### Bundle disambiguation

When a single conceptual app has been published multiple times to source (or the user has multiple working bundles staged), **the user must pick which one is canonical** before publish. Asking "which bundle by name?" is unreliable — different builds of the same app share name and aliases but differ in compiled `app.js` content. Better techniques:

- **Hash app.js across candidates**: `sha256sum <candidate>/app.js` for each. Distinct hashes → distinct apps. If user has multiple, ask which hash matches what's currently rendering on the source card.
- **Pull source card's design context** via the placement endpoint to learn which `designId` is wired, then download THAT bundle's app.js for byte comparison.
- **Surface app.js feature snippets** (first 200 chars + size) in the picker so the user can recognize which build is canonical.

Picking the wrong bundle is the single largest source of "the cloned card doesn't look like source" feedback after the clone is done.

### Branch A — source repo available

1. **Identify the repo**: ask for the source repo path (e.g., `/path/to/the-source-app/`). It must contain `manifest.json` and a buildable `package.json`.
2. **Read source manifest** (`public/manifest.json` or `src/manifest.json`):
   ```json
   {
     "id": "0d29843b-…",
     "name": "...",
     "version": "1.0.0",
     "datasetsMapping": [
       { "alias": "communities", "dataSetId": "d14df439-…", "fields": [], "autoSubscribe": true }
     ],
     "collectionsMapping": [{ "id": "<source_collectionId>", "alias": "SOP_recommendations" }],
     "workflowsMapping":  [{ "modelId": "<source_workflow_modelId>", "alias": "<alias>", "version": "1.0.2" }]
   }
   ```

3. **Run all prerequisites first** (sections 3, 5, 6, 8) so the mappings exist:
   - dataset bridging → target UUIDs for `datasetsMapping[].dataSetId`
   - AppDB collection clones → target IDs for `collectionsMapping[].id`
   - Workflow clones → target modelId + released version for `workflowsMapping[]`

4. **Rewrite manifest** for target:
   - `del .id` — ALWAYS strip. First-publish allocates fresh design ID.
   - Rewrite each `datasetsMapping[].dataSetId` to its target UUID. KEEP `fields: []` even if empty.
   - Rewrite each `collectionsMapping[].id` to target collectionId.
   - Rewrite each `workflowsMapping[].modelId` and `.version` from the released version, NOT the source version.
   - **Inspect app.js for alias dependencies**: if app.js calls `WorkflowClient.startModel("<alias>", ...)`, the `workflowsMapping[].alias` must match what app.js expects. If app.js references by `modelId` directly, alias can stay `""`.

5. **Authenticate `domo` CLI against target**:
   ```bash
   domo login -i $TARGET_HOST
   cat ~/.config/configstore/ryuu/$TARGET_HOST.json | jq '.instance'
   ```

6. **Build and publish**:
   ```bash
   npm run build && cd dist && domo publish
   # OR for pre-built bundle:
   cd <bundle-dir> && domo publish
   ```

7. **Capture the new design ID** `domo publish` writes back into the bundle's `manifest.json`.

### Branch B — source bundle ZIP from Asset Library

If the user downloaded the bundle from source's Asset Library:
1. Unzip into a working directory.
2. Edit `manifest.json` per Branch A step 4.
3. Skip `npm run build` — the bundle is already compiled.
4. `cd <unzip-dir> && domo publish`.

**`domo publish` is the CLI convenience here, not a requirement.** Both branches above use the ryuu CLI, but publish is per-file POSTs to the designs REST API (see the start of this section). When `domo login` can't be used — an OAuth-only target drops it to an interactive developer-token prompt, or ryuu's machine-shared "current instance" is already held by another local session — publish the same bundle over REST with a SID or `X-DOMO-Developer-Token`.

### Placement on App Studio pages

```bash
curl -s -X POST "https://$TARGET_HOST/domoapps/apps/v2/contexts" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"designId":"<new_designId>","mapping":[],"collections":[{"id":"<target_collectionId>","alias":"<alias>"}]}'
# → [{"id":"<contextId>","designId":"..."}]   — IT'S AN ARRAY, extract .[0].id
```

Then:
```bash
curl -s -X POST "https://$TARGET_HOST/domoapps/apps/v2?fullpage=true&pageId=<target_viewId>&cardTitle=<url-encoded>" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"contextId":<ctxId>,"id":<ctxId>}'
```

The placement POST writes the card onto the view. Resolve the new card URN via `GET /api/content/v1/pages/<viewId>/cards` matching title, persist to the cards map.

If the placement POST rejects `collections[]`, strip it and wire the collection alias via the card-editor UI (one click).

### What Pro Code Apps do not need

- No DAG/action remap.
- No env-var transfer. Pro Code Apps have no server-side env vars; runtime config comes from datasets, AppDB, or user variables inside the app.

See `manifest` and `publish` for deeper detail on the manifest schema and first-publish flow.

## Section 10 — App Studio dataapps

App Studio dataapps (= the parent container with multiple views) require a multi-step clone: shell create → view-add → theme/nav apply → layout per view → card placement + positioning → tile placement → variable wiring. The endpoints are all `/api/content/v1/dataapps/...` and `/api/content/v4/pages/layouts/...`.

### Step 10a — Reject classic pages

```bash
curl -s "https://$SOURCE_HOST/api/content/v3/stacks/<source_pageId>" \
  -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" > /tmp/page-source.json
jq -r '.type' /tmp/page-source.json   # must be "dataappview"
```

If `.type != "dataappview"`, this skill does not handle classic dashboards — abort with a clear error message.

### Step 10b — Create target dataapp shell

```bash
curl -s -X POST "https://$TARGET_HOST/api/content/v1/dataapps" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"title":"<source title>","description":"<source desc>"}'
# → {"id":<new_dataappId>, ...} with one default landing view
```

### Step 10c — Add views

For each non-landing source view, POST a view. The unified dataapp PUT shape (Step 10d) also accepts new views via `views[]` + `viewIds[]`, but the per-view POST is more reliable:

```bash
curl -s -X POST "https://$TARGET_HOST/api/content/v1/dataapps/<dataappId>/views" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{"type":"dataappview","title":"<view_title>","hasLayout":true,"appPageDataSourceId":"null"}'
# → {"id":<new_viewId>,...}
```

Persist the source-viewId → target-viewId map at `/tmp/clone-<obj>-views.tsv`.

### Step 10d — Unified dataapp PUT (theme, nav, landing, view-order)

The shape the App Studio editor sends on save (capture verified 2026-05-12 against modocorp):

```
PUT /api/content/v1/dataapps/<dataappId>?includeHiddenViews=true
```

The body must include **fields that come back as null on GET** — they're required on PUT or new views[] entries are silently dropped:

| Field | Type | Notes |
|---|---|---|
| `viewIds` | string[] | Required. Parallel to `views[]`. ViewIds as STRINGS. |
| `pageDrillParentStates` | array (usually `[]`) | Required. |
| `conversationalAgentContextRequest` | object `{add: null, remove: {dataSourceIds: []}}` | Required. |
| `views[].viewId` | string | On PUT (numbers on GET). |
| `landingViewId` | string | On PUT (numbers on GET). |
| `views[].parentViewId` | string `"0"` | |
| `views[].viewOrder` | integer 1-indexed | |
| `views[].view` | null | |
| `views[].layout` | null | |
| `views[].children` | `[]` | |
| `navigations[]` | object[] | One VIEW entry per viewId + standard HOME/AI_ASSISTANT/CONTROLS/DISTRIBUTE/MORE system entries. |

The full body shape is captured in [docs/reference/app-studio-clone.md](../docs/reference/app-studio-clone.md). Use a captured-pattern template and substitute source values; do NOT round-trip a GET response without filling in the null-on-read scaffolding fields.

### Step 10e — Nav icon `phosphor` field is stripped on PUT (OPEN gap)

VIEW nav entries with rich icons (`{value: "webpage", phosphor: "Globe"}`) come back as `{value: "pages"}` after a unified PUT — both `phosphor` and `value` are normalized. The icon-picker save call is a SEPARATE endpoint (not yet captured).

**Workaround**: emit a per-view manual task with the source's `phosphor` value as the recommendation:
```
[target instance] App Studio → Settings → Navigation → set icon for each VIEW:
  Executive Summary  → phosphor "Globe"   (source value)
  Property Details   → phosphor "ChartArea"
  Operations Center  → phosphor "Workflow"
Why: nav phosphor field is stripped by the unified dataapp PUT — the icon-picker uses a different endpoint not yet captured.
```

### Step 10f — Per-view layout: layout PUT only accepts surgical in-place mutation

`PUT /api/content/v4/pages/layouts/<layoutId>` does NOT accept a rebuilt body with new `content[]` / `template[]` entries. Returns generic HTTP 400 with no details. It accepts ONLY mutations of entries the target layout already contains (auto-created when cards were placed with `--page-id` or when views were added).

**Recipe**:

```python
# 1. GET the target layout (it already has appendix entries for every card placed earlier)
GET /api/content/v4/pages/<view_id>/layouts

# 2. Build map: target template[] entries by contentKey → target cardId → source cardId (via /tmp/clone-<obj>-cards.tsv) → source position
# 3. For each target CARD entry in standard.template[] AND compact.template[]:
#    - set (x, y, width, height) to source position
#    - flip virtual: false, virtualAppendix: false
#    - KEEP the entry's contentKey and other fields
# 4. For each target CARD entry in content[]:
#    - mirror source's style flags (hideTitle, hideDescription, hideFooter, hideWrench, hideMargins, fitToFrame, hideBorder, acceptFilters, acceptDateFilter, acceptSegments, editInAppViewer, showMoreContent, compactInteractionDefault)
#    - preserve target's contentKey + cardId/cardUrn (don't substitute source IDs)
# 5. Acquire the instance-dependent writelock, PUT, and release it in finally.
#    PUT  /api/content/v4/pages/layouts/<layoutId>/writelock body {}
#    PUT  /api/content/v4/pages/layouts/<layoutId> body <mutated layout>
#    DELETE /api/content/v4/pages/layouts/<layoutId>/writelock
```

Writelock enforcement is instance-dependent. `modocorp` accepted the layout PUT without a lock, while `maintenance-instance` returned 403 `WL003` until `PUT .../writelock` with `{}` was called. `POST .../writelock` is the wrong method and can return 405. When a lock is acquired, always release it with `DELETE` in a `finally` block.

**Source TABS-flattening**: if source uses TABS/TAB_CONTENT containers, recurse `children[]` and compute absolute positions (`abs_x = parent.x + child.x`). Cards in multiple tabs collapse to first-tab position (lossy but acceptable for demo). If reconstructing TABS on target is needed, see [docs/reference/app-studio-clone.md](../docs/reference/app-studio-clone.md)'s **fresh-contentKey surgical append** recipe.

**Source `id` field**: layout entries carry `content[].id` numeric values (internal layout entry IDs). Probably worth stripping any source `id` before any PUT — couldn't isolate empirically due to the surgical-mutation constraint.

### Step 10g — Image / PDF tile clone (chartType=null cards)

Source cards with `type: "document"` and `metadata.chartType: null` are image/PDF tiles backed by a binary file in `/api/data/v1/data-files/<id>`. Full clone recipe verified 2026-05-14:

1. **Download source file**:
   ```bash
   curl -s "https://$SOURCE_HOST/api/data/v1/data-files/<source_dataFileId>" \
     -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" -o /tmp/<filename>
   ```
   The `<source_dataFileId>` is the integer prefix of `metadata.documentId` on the source card (e.g. `"1658:undefined"` → 1658).

2. **Upload to target**:
   ```bash
   curl -s -X POST "https://$TARGET_HOST/api/data/v1/data-files" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" \
     -F "file=@/tmp/<filename>;type=<content-type>"
   # → {"dataFileId": <new_id>}
   ```
   Content-Type: `image/png`, `application/pdf`, etc.

3. **Create document card**:
   ```bash
   curl -s -X POST "https://$TARGET_HOST/api/content/v1/cards?pageId=<target_viewId>" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
     -d '{
       "type": "document",
       "description": "<source metadata.title>",
       "metadata": {
         "title": "<source metadata.title>",
         "documentId": "<new_dataFileId>:undefined",
         "usingSampleData": "",
         "kpiType": "document",
         "description": "<source metadata.title>"
       }
     }'
   ```
   **`metadata.title` MUST be filename-style** (e.g. `Executive Summary.png`, `Domo-Terra-Properties Deck.pdf`). Simple titles ("Banner", "Test") return HTTP 400 — the title is parsed for an extension. Use source's exact `metadata.title` for byte-for-byte fidelity.

4. **Position on layout** per Step 10f surgical mutation, mirroring source content[]'s style flags + source template[]'s (x, y, width, height).

### Step 10h — Card variables and controls

Source dataapps often have a dropdown/pill/slider variable that drives one or more cards via Beast Mode references. The full 5-step recipe is in `variable-creation`. **Load that skill before attempting**.

Summary:
1. Check uniqueness: `GET /api/query/v1/functions/variables/uniqueName?name=<n>`
2. Create function template + embedded control: `POST /api/query/v1/functions/template` (body has `variable: true` + embedded `control` with placeholder IDs `-101`, `-201`)
3. Register variable control: `PUT /api/content/v1/variable/controls` with body as **array** of control objects (real `function.id` from step 2)
4. Read target card definition: `PUT /api/content/v3/cards/kpi/definition` with `{dynamicText: true, variables: true, urn: <cardId>}`
5. Save card with merged controls: `PUT /api/content/v3/cards/kpi/<cardId>` with `variables: true, columns: false` at root, `dataSourceId` in `dataProvider` (NOT `subscriptions.main`)

`community-domo-cli variables create <cardId> --body-file <body.json>` wraps the full flow.

**Known CLI bug**: the CLI's step 4 (`PUT /api/content/v3/cards/kpi/definition`) returns 400 on some target cards where direct curl with identical body returns 200. Workaround: do steps 1-3 via CLI, step 5 manually via curl with the merged body.

**Page-binding gap (OPEN)**: `PUT /api/content/v1/variable/controls/PAGE/<viewId>` is the captured endpoint, but direct token-auth replay returns 400 even with the byte-identical captured body. Appears to require App Studio editor session state. Emit a manual-task:
```
[target instance] Open <dataapp URL> → Controls panel → drag <variable name> onto <view> → Save.
Why: page-binding endpoint rejects direct token-auth PUTs; only the App Studio editor's save sequence successfully fires the call.
```

**Beast Mode rewrites for variable-aware formulas**: any source BM containing `DOMO_BEAST_MODE(<src_templateId>)` must have that reference rewritten to the target variable's templateId before being applied to the target card.

### Step 10i — Apply pro-code placements (from Section 9 mappings)

For each cloned pro-code app, run the placement POSTs from Section 9. Use the now-known target viewIds from Step 10c.

### Verify

After all per-view layouts are PUT:
1. Open `https://$TARGET_HOST/page/<target_landing_viewId>` in a browser.
2. Confirm every view renders all expected cards + pro-code cards + tiles (no `Card not found` / `Dataset unavailable` errors in the network panel).
3. Layouts match source side-by-side: TABS, exact card positions, headers, VARIABLE controls (after manual drag step) present and functional.
4. Drill-throughs land on target view IDs (rewrite any drill-target IDs in card metadata via the view map).
5. Trigger pro-code workflows from inside their cards; confirm workflow execution lands on target and AppDB write-back picks up new rows.

See [docs/reference/app-studio-clone.md](../docs/reference/app-studio-clone.md) for the unified dataapp PUT body template, TABS surgical-append recipe, and worked examples.

## Section 11 — Native KPI cards

Two paths: **CREATE on page** (`PUT /api/content/v3/cards/kpi?pageId=<viewId>`) for new cards, or **UPDATE by urn** (`PUT /api/content/v3/cards/kpi/<urn>`) when overlaying source style onto an existing target card.

### Definition-driven id-swap (CANONICAL)

This is the ID-only-swap principle applied to cards. Verified 2026-05-14 on 6 Exec Summary cards (3 filters + 3 hero pop_multi_value) with full source overrides landing on target.

**Recipe**:

1. **Read source's full write-ready body**:
   ```bash
   curl -s -X PUT "https://$SOURCE_HOST/api/content/v3/cards/kpi/definition" \
     -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" -H "Content-Type: application/json" \
     -d '{"dynamicText": true, "variables": true, "urn": "<src_cardId>"}' > /tmp/src-card-<id>.json
   ```
   This response is the full body in WRITE shape (the same shape the UI sends on save).

2. **For UPDATE** of an existing target card, also pull target's current definition (preserves target's `modified` timestamp + `columns[].sourceId` identity).

3. **Walk the entire tree and rewrite IDs ONLY**:
   - `dataProvider.dataSourceId` (via dataset map)
   - `definition.columns[].sourceId` (via dataset map — top-level on response)
   - `definition.subscriptions.main.dataSourceId` (strip — moves to top-level `dataProvider`)
   - `definition.formulas[].formulaId` references (via formula map if remapping)
   - `definition.charts.main.overrides` formula refs (e.g. `DOMO_BEAST_MODE(<src_templateId>)` → `DOMO_BEAST_MODE(<tgt_templateId>)`)
   - `definition.drillpath[].pageId` (via view map — or strip if drill targets aren't being cloned)
   - `dynamicTitle` variable refs (e.g. `<VARIABLE 752>` → `<VARIABLE 118280>`)
   - Everything else preserved verbatim.

4. **Apply read→write shape conversions** (the read response uses one shape; the write endpoint requires another):
   - **`formulas`**: read returns flat **array** of BMs. Write needs `{dsUpdated: [], dsDeleted: [], card: [...]}`. **CRITICAL**: re-emit every BM from the read array into `card[]` as a card-level BM (`persistedOnDataSource: false`, full normalized BM shape). Emptying `card[]` orphans any `formulaId` reference in main subscription → 400 "The following formula(s) are missing from the definition or datasource".
   - **`conditionalFormats`**: list → `{card: [list], datasource: []}`
   - **`annotations`**: list/null → `{new: [], modified: [], deleted: []}`
   - **`segments`**: any shape → `{active: [], create: [], update: [], delete: []}`

5. **Strip read-only fields**:
   - `urn`, `id`, `embedded`, `dataSourceWrite`, `columns` (top-level)
   - Drop `definition.drillpath` if drill targets aren't being cloned
   - **KEEP `definition.modified` and `definition.allowTableDrill`** — prior skill guidance said remove these, but empirically removing them breaks the UPDATE. The card-creation skill's gotcha #14 is wrong on this point.

6. **Top-level body**:
   ```json
   {
     "definition": <modified definition>,
     "dataProvider": {"dataSourceId": "<target dataset uuid>"},
     "variables": true,
     "columns": false
   }
   ```

7. **PUT**:
   - CREATE on page: `PUT /api/content/v3/cards/kpi?pageId=<tgt_viewId>` → returns new card body with new urn.
   - UPDATE by urn: `PUT /api/content/v3/cards/kpi/<tgt_urn>` → overlays style onto existing card.

### Subscriptions: omit big_number when source doesn't have it

The card-creation skill says "Both `main` and `big_number` subscriptions required" — empirically **wrong for `badge_singlevalue` and `badge_pop_multi_value`** (and likely other pop_* types). If source's card definition has only `main` subscription (no `big_number`), the PUT body should also have only `main`. Don't synthesize a big_number from `first_value` — it will be rejected ("Summary number subscription must have a single aggregated column").

### Card-level beast modes — dependency walk

A card referencing BM `X` via `formulaId` may depend transitively on other BMs (X's formula calls `DOMO_BEAST_MODE(<another_templateId>)`). The dependency graph must be walked recursively and ALL transitive BMs embedded in `formulas.card[]`, with every `DOMO_BEAST_MODE(<src_tid>)` rewritten to target templateId (or kept consistent if all referenced BMs are being embedded card-level under the same source templateIds).

```python
def walk_bm_deps(formula_id, source_bms_by_id, seen=None):
    seen = seen or set()
    if formula_id in seen: return
    seen.add(formula_id)
    bm = source_bms_by_id[formula_id]
    # extract DOMO_BEAST_MODE(N) references from bm['formula']
    for tid in re.findall(r'DOMO_BEAST_MODE\((\d+)\)', bm['formula']):
        dep = find_bm_by_templateId(int(tid))
        if dep: walk_bm_deps(dep['id'], source_bms_by_id, seen)
    return seen
```

### Dataset-level beast modes — attach gap (OPEN)

`POST /api/query/v1/functions/template?strict=false` creates the BM record but doesn't attach it to the target dataset — `templateId` comes back null and the BM doesn't appear in `/api/query/v1/datasources/<id>/schema/indexed`. **Workaround**: embed the BM as card-level (`persistedOnDataSource: false`) in `formulas.card[]` of every card that uses it. This produces functionally identical behavior but loses cross-card reuse.

### Image/document tiles

For `type: "document"` cards (`chartType: null`), use Section 10g's recipe — they're NOT created via the cards KPI endpoint.

See `card-creation`, `beast-mode-creation`, and `variable-creation` for per-component contracts.

## Section 12 — Mapping table

All object types produce mapping tables in the same shape so they're easy to scan side-by-side and easy to diff across runs.

### Schema

| Column | Meaning |
|--------|---------|
| `kind` | `dataset`, `workflow`, `card`, `view`, `page`, `dataapp`, `dataflow`, `fileset`, `appdb_collection`, `code_engine_package`, `pro_code_app`, `beast_mode`, `variable`, `document_tile`, `image_file`, `secret_text` |
| `alias` | The source-side name or alias used in the JSON (e.g., manifest alias, action input name, paramName) |
| `source_id` | The source instance ID |
| `source_name` | The source object's display name |
| `target_id` | The target instance ID, `—` if unresolved, `(recreate)` if a fresh create is required |
| `target_name` | The target object's display name |
| `confidence` | `high` / `medium` / `low` / `ambiguous` / `missing` / `n/a` |
| `notes` | Reason for confidence; manual-task hint if missing |

### Confidence rules

- `high` — exact name match OR exact column signature match OR direct ID-swap (cards/dataflows the skill is cloning fresh).
- `medium` — fuzzy name match or partial column signature.
- `low` — partial name match, column signature mismatch but plausible by domain.
- `ambiguous` — multiple plausible target candidates; user must choose.
- `missing` — no plausible target candidate; abort.
- `n/a` — does not apply (e.g., recreate-fresh).

The mapping table is persisted to `/tmp/clone-<source-obj>-<timestamp>.tsv`. See [docs/reference/mapping-table.md](../docs/reference/mapping-table.md) for full conventions.

## Section 13 — Manual-task template

When the skill cannot complete a step, emit a single structured block the user can act on, then abort the run (no partial writes).

### Template

```
=== MANUAL TASKS REQUIRED before retry ===

TARGET INSTANCE: <target-host>
SOURCE OBJECT:   <source kind + name + ID>
RUN ID:          <timestamp / mapping-table path>

Required:
  1. [target instance] <action>
     Why: <reason>
     Verify: <how to confirm>
  2. ...

Optional (skill will still work without these, but they improve fidelity):
  1. ...

Resume by re-invoking the skill with the same source object once the Required items are done.
```

### Concrete example

```
=== MANUAL TASKS REQUIRED before retry ===

TARGET INSTANCE: customer-trial.domo.com
SOURCE OBJECT:   App Studio dataapp "Private Equity Ops" (id 651749670)
RUN ID:          /tmp/clone-pe-ops-20260514-095412/

Required:
  1. [target instance] Configure Databricks cloud integration "Customer Databricks"
     and federate these bronze tables as datasets:
       demo_pe_ops.pe_ops_bronze.{property_financials_monthly, units, leases, properties,
                                  tenants, maintenance_requests, engagement_events, prospects}_bronze
     Why: Source dataflows are ADR (Spark SQL) and reference these tables. Without
     the integration, target dataflows will fail with ADR-4001.
     Verify: curl ... /api/data/v3/datasources?... | jq '... databricks ...'

  2. [target instance] Re-enter workflow env var SECRET_API_KEY in workflow "Cash Adjudicator"
     Why: Secret values are not transferable across instances.
     Verify: Open workflow editor → Variables panel → confirm value is set.

  3. [target instance] App Studio → Settings → Navigation → set icon for each VIEW:
       Executive Summary  → phosphor "Globe"
       Property Details   → phosphor "ChartArea"
       Operations Center  → phosphor "Workflow"
     Why: nav phosphor field is stripped by the unified dataapp PUT.

Optional:
  1. [target instance] App Studio → Controls → drag variable "Metric_PEOps" onto
     Executive Summary view → Save.
     Why: page-binding PUT only fires via the editor save sequence; the variable
     control exists but isn't placed on the page until this UI action.

Resume by re-invoking the skill with the same source object once the Required items are done.
```

## End-to-end run sequence

For any source object, run prerequisites in dependency order BEFORE writes:

1. **Confirm the four facts** (source host, target host, object kind, source ID).
2. **Verify auth** on both instances (ryuu + admin PAT if workflows).
3. **Read source object** and recursively inventory ALL cross-instance refs (datasets, persons, groups, secrets, Code Engine packages, AppDB collections, filesets, workflows referenced by pro-code, sub-workflows, beast-mode formula refs).
4. **Build the mapping table** in dependency order. Run Section 3 (datasets) first; then 4 (filesets), 5 (AppDB), 6 (Code Engine), 8 (workflow shells + clones) to fill in those columns.
5. **Present the mapping table** to user. Resolve all `ambiguous` / `low` rows. **Abort on `missing`**.
6. **Run prerequisites** end-to-end: data layer (datasets if creating, filesets, AppDB collections), code layer (Code Engine packages), pipeline layer (dataflows), automation layer (workflows).
7. **For App Studio dataapps**: create shell → add views → unified PUT (theme/nav/landing) → per-view layout PUT (surgical mutation) → tile clones → card recreates → variable wiring → pro-code placements.
8. **For Pro Code Apps**: AFTER prerequisites (datasets + AppDB + workflows) — patch manifest → publish → placement on the right views.
9. **Verify** at the URL level (open target dataapp, click through views, trigger workflows, check network panel for missing-resource errors).
10. **Report** new target IDs + any manual follow-ups.

## Related skills

- `community-cli-howto` — auth setup + CLI surface.
- `magic-etl-cli` — dataflow JSON shape via CLI.
- `magic-etl` — dataflow DAG schema, action types, pitfalls.
- `appdb-collection-create` — AppDB datastore/collection lifecycle.
- `code-engine-create`, `code-engine-update` — package authoring.
- `fileset-cli`, `fileset-api` — fileset shell + file content copy.
- `card-creation` — native card body schemas (read with caveats — see Section 11 corrections).
- `beast-mode-creation` — dataset/card-level BM contracts.
- `variable-creation` — 5-step variable + control flow.
- `advanced-app-studio` — App Studio reference and layout schemas.
- `manifest`, `publish` — pro-code manifest + first-publish.
- `dataset-query` — dataset schema endpoints used by bridging.
- `domo-data-generator` — sample data when datasets must be created on target.
