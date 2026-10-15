# Workflow JSON & Environment Variables Reference

Originally reverse-engineered against source-instance on 2026-05-11 from workflow `a80ff1b3-5a8a-5476-8a11-7b85d01fd8e9` ("AI Facility Management", version 2.0.7). Write-path endpoints captured + verified during the PE Ops clone on 2026-05-12.

## Auth — admin PAT required for source reads

**All `/api/workflow/v1/*` and `/api/workflow/v2/*` endpoints reject the ryuu refresh token with 403.** They require a workflow-scoped admin Personal Access Token minted via Admin → Authentication → Access tokens. There is no `domo login --admin` CLI flag.

```bash
export SOURCE_ADMIN_TOKEN=<source PAT>     # required for source reads
export TARGET_REFRESH=$(jq -r '.refreshToken' ~/.config/configstore/ryuu/$TARGET_HOST.json)
# TARGET_ADMIN_TOKEN only needed if a target write returns 403 with ryuu refresh
```

Per PE Ops clone empirical results: **target writes (POST/PUT) succeed with `TARGET_REFRESH`** (ryuu refresh used as dev-token header). Only mint a target admin token if a write returns 403.

## Endpoints (VERIFIED 2026-05-12)

| Purpose | Method | Path | Auth | Returns |
|---|---|---|---|---|
| List models | GET | `/api/workflow/v1/models` | source admin PAT | up to 1000 models |
| Get model metadata + version list | GET | `/api/workflow/v1/models/<modelId>` | source admin PAT | `versions[]` with timestamps + `deployedOn` |
| Get a version definition (v1) | GET | `/api/workflow/v1/models/<modelId>/versions/<version>` | source admin PAT | `savedJson` (stringified) |
| Get a version definition (v2) | GET | `/api/workflow/v2/models/<modelId>/versions/<version>/definition` | source admin PAT | parsed JSON (cleaner than v1) |
| Create model shell | POST | `/api/workflow/v2/models` | target ryuu refresh OR admin PAT | `{id, versions: ["1.0.0"], activeVersions: [], ...}` |
| Save (overwrite) version definition | PUT | `/api/workflow/v2/models/<modelId>/versions/<version>/definition` | target ryuu refresh OR admin PAT | numeric `version` (internal versionNumber, NOT a SemanticVersion) |
| Release version | POST | `/api/workflow/v2/models/<modelId>/versions/<SemanticVersion>/release` | target ryuu refresh OR admin PAT | `{modelId, version, active: true, startEventId, manualTriggerId, releasedAt, ...}` |

## Model shell POST body

```json
{"name": "Ops Optimizer", "description": "", "versions": [{"version": "1.0.0"}]}
```

## PUT-definition mechanic

- When only `1.0.0` exists on a freshly-created model, PUT to `1.0.0` **OVERWRITES it in place** — does NOT create a draft `1.0.1`.
- When multiple versions exist, PUT to the highest version creates a new draft above it.
- The release path requires the SemanticVersion string (e.g. `1.0.0`), NOT the integer `versionNumber` returned in the PUT response.
- Pre-release validation rejects refs to Code Engine packages that don't exist on target. Clone those packages first.

## Version GET response shape

```json
{
  "modelId": "0d3f2c48-…",
  "version": "2.0.7",
  "active": null,
  "description": "",
  "owner": "753621073",
  "createdBy": "753621073",
  "createdOn": "2025-11-17T18:20:42.617Z",
  "updatedBy": "753621073",
  "updatedOn": "2026-05-11T15:55:17.807Z",
  "savedJson": "<stringified JSON, see below>"
}
```

`savedJson` is a **string** that must be `JSON.parse`d. Its shape:

```json
{
  "version": "<schema-version>",
  "schema": {
    "inputs":  { "<id>": { "name": "...", "type": "text|number|dataset|person|...", "isList": false, "isNullable": false, "id": "...", "parent": null, "isChild": false } },
    "outputs": { /* same shape */ }
  },
  "dataList": [ /* see below — this is where env vars live */ ],
  "designElements": [ /* DAG nodes — see below */ ]
}
```

## `dataList` — the environment variables

This is the key insight. **Every variable a workflow uses lives in `dataList[]`** — runtime inputs, outputs, constants, dataset references, person references, prompts. Each entry:

```json
{
  "id": "<random-15-char-id>",
  "paramName": "<human-readable-name>",
  "dataType": "text" | "number" | "dataset" | "person" | "object" | "group" | "boolean",
  "value": <type-dependent or null>,
  "isOutput": false,
  "children": [],
  "showChildren": false,
  "entitySubType": null
}
```

### Cross-instance reference types

| `dataType` | Source of breakage | Resolution |
|------------|--------------------|------------|
| `dataset` | `value` is a dataset UUID | **Dataset bridging** ([Section 3](../../skills/domo-cross-instance-clone.md#section-3--dataset-bridging)). Look up by source UUID → schema → name → target candidate. |
| `person` | `value` is a Domo user ID like `"753621073"` | **Per-instance user IDs** are not portable. Look up source user by ID → get email → search target by email. If no match, emit manual task to remap or zero out. |
| `group` | `value` is a Domo group ID | Same as person — look up by name on source, search target by name. |
| `text` | `value` is a string constant | Usually safe to transfer as-is, EXCEPT when `paramName` matches the secret regex (see below). |
| `number` | `value` is `null` for inputs; for file/attachment params, holds a numeric file ID | If used as a file reference (look at upstream node's `fileId` input), the file ID is instance-specific — must be re-uploaded or zeroed for runtime input. |
| `object` | Hierarchical — has `children[]` | Recurse into children. |
| `boolean` | Safe constant | Transfer as-is. |

### Secret detection regex

If a `dataType: "text"` entry's `paramName` matches `/(?i)(secret|password|token|apikey|api[-_]?key|credential|auth|bearer|private[-_]?key)/`, treat as redacted:

- Set `value` to empty string in the cloned JSON.
- Emit a manual-task callout listing each redacted `paramName` for the user to re-enter on the target.

## `designElements` — the DAG

```json
[
  {
    "id": "<random-id>",
    "type": "rootNode" | "endNode" | "defaultEdge" | "AI_AGENT" | "serviceTaskNode" | "EMPTY",
    "position": { "x": 50, "y": 240 },
    "data": { /* type-specific */ }
  }
]
```

### Type-specific `data` payloads

**`rootNode` / `endNode` / `EMPTY`**: structural, no instance-specific references.

**`defaultEdge`**: edges between nodes, references node IDs (intra-document, no remap needed).

**`serviceTaskNode`**:
```json
{
  "data": {
    "title": "Text Generation",
    "metadata": { "packageId": "artificialIntelligence", "functionName": "TEXT_GENERATION" },
    "input":  { /* parameter wiring */ },
    "output": { /* parameter wiring */ },
    "taskType": "...",
    "usesStructuredOutputs": true
  }
}
```
- `metadata.packageId` may be a **friendly name** (e.g., `artificialIntelligence`) for built-in Domo platform packages — these exist on every instance, no remap needed.
- If `metadata.packageId` is a **UUID**, it's a custom Code Engine package. Must exist on target. Resolve via the `code-engine-create` / `code-engine-update` skills (or emit manual task).

**`AI_AGENT`**:
```json
{
  "data": {
    "title": "...",
    "agent": {
      "instructions": "...",
      "tools": [
        {
          "functionName": "IMAGE_TO_TEXT",
          "packageId": "3881a4a3-fc8d-5309-8182-995a71f2051c",
          "packageVersion": "1.0.0",
          "inputs":  [ /* parameter slots */ ],
          "output":  { /* parameter slot */ }
        }
      ],
      "context": {
        "datasets":    [ { "id": "<dataset-uuid>" } ],
        "directories": [],
        "files":       []
      }
    },
    "prompt": { /* slate-style rich text with variable refs */ },
    "result": { /* output schema */ }
  }
}
```

**Cross-instance surfaces in AI_AGENT:**
- `agent.context.datasets[].id` — dataset UUIDs. **Dataset bridging required.**
- `agent.context.files[]` — file IDs. Instance-specific; emit manual task if non-empty.
- `agent.context.directories[]` — directory IDs. Instance-specific.
- `agent.tools[].packageId` — same rule as serviceTaskNode: UUID = custom package, must exist on target.
- `agent.tools[].inputs[].value` — if a tool input has a literal `value` (e.g., `"model": "domo.domo_ai"`), it's transferable; the value `"domo.domo_ai"` is a model name not an instance ID.

**Slate prompt format**: the `prompt.value` is a Slate.js-style array of paragraphs/children. Variable references inside it look like:
```json
{ "type": "variable", "dataType": "number", "id": "<dataList-id>", "name": "Picture_of_Issue", "isList": false }
```
The `id` references a `dataList[]` entry by its `id` field — purely intra-document, no remap needed.

## Reference walking algorithm for cloning

```
function inventory_workflow_refs(savedJson):
    refs = []
    for d in savedJson.dataList:
        walk(d, path=f"dataList[{d.id}]")
    for el in savedJson.designElements:
        if el.type == "AI_AGENT":
            for ds in el.data.agent.context.datasets:
                refs.append({kind: "dataset", source_id: ds.id, alias: "agent_context", path: f"designElements[{el.id}].agent.context"})
            for tool in el.data.agent.tools:
                if is_uuid(tool.packageId):
                    refs.append({kind: "code_engine_package", source_id: tool.packageId, version: tool.packageVersion, path: f"…tools[{tool.id}]"})
        if el.type == "serviceTaskNode":
            if is_uuid(el.data.metadata.packageId):
                refs.append({kind: "code_engine_package", source_id: el.data.metadata.packageId, path: f"…serviceTaskNode[{el.id}]"})
    return refs

function walk(d, path):
    if d.dataType == "dataset" and d.value:
        refs.append({kind: "dataset", source_id: d.value, alias: d.paramName, path: path})
    if d.dataType == "person" and d.value:
        refs.append({kind: "person", source_id: d.value, alias: d.paramName, path: path})
    if d.dataType == "group" and d.value:
        refs.append({kind: "group", source_id: d.value, alias: d.paramName, path: path})
    if d.dataType == "text" and d.value and re.search(r"(?i)secret|password|token|apikey|credential|auth|bearer|private", d.paramName):
        refs.append({kind: "secret_text", source_id: f"env:{d.paramName}", alias: d.paramName, path: path})
    for child in d.children:
        walk(child, path + f".children[{child.id}]")
```

## Person/group resolution endpoints

Given a source user ID, get email:
```bash
curl -s "https://$SOURCE_HOST/api/content/v2/users/<USER_ID>" -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" | jq '{id, displayName, emailAddress}'
```

Search target by email:
```bash
curl -s -X POST "https://$TARGET_HOST/api/identity/v1/users/search" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" \
  -H "Content-Type: application/json" \
  -d '{"query": "<email>", "limit": 5}'  # endpoint shape TBD — verify via DevTools
```

If you cannot find a user/group on target, emit a manual task to map or remove the reference.

## Remap procedure (when applied to a workflow)

1. GET source version (`/api/workflow/v1/models/<id>/versions/<version>`).
2. `JSON.parse(response.savedJson)` into a JS object.
3. Run `inventory_workflow_refs()` → get the list of refs.
4. For each ref:
   - `kind: dataset` → bridge via [Section 3](../../skills/domo-cross-instance-clone.md#section-3--dataset-bridging). Rewrite the `value` at the recorded `path`.
   - `kind: person`/`group` → resolve and rewrite, or redact and emit manual task.
   - `kind: secret_text` → set `value` to `""` and emit manual task.
   - `kind: code_engine_package` → if it's a Domo built-in (non-UUID friendly name), do nothing; if UUID, check target → emit manual task if missing.
5. Strip identity fields: top-level `owner`, `createdBy`, `createdOn`, `updatedBy`, `updatedOn` should be removed (target will assign them).
6. `JSON.stringify` back into `savedJson`.
7. POST model shell on target (capture new `modelId`), PUT remapped definition to `versions/1.0.0/definition`, POST release.
8. Capture `version`, `startEventId`, `manualTriggerId` from the release response — pro-code bundles need them for `workflowsMapping[]`.

## Open investigation

- **Sub-workflow references** — the original sample workflow doesn't call other workflows. Add a sample that does, and document the reference shape.
- **manualTriggerId** is allocated server-side on release; pro-code apps that invoke workflows via the WorkflowClient may need it depending on the call shape.
