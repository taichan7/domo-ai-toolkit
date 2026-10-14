# Domo Workflows Skill

Use this when authoring, editing, or reasoning about **Domo Workflows** (the v2 automation engine: form/timer/webhook triggered flows with gateways, user tasks, AI-agent steps, and action steps). Full per-shape / per-action catalog: [`../docs/domo-workflow-reference.md`](../docs/domo-workflow-reference.md).

Do **not** confuse Workflows with Magic ETL DataFlows — different engine, different API, different purpose. ETL reshapes datasets on a schedule; Workflows orchestrate business logic/approvals/notifications, often triggered by app forms or events. For ETL see [`domo-magic-etl.md`](domo-magic-etl.md).

## The one architecture fact that saves hours

Most "Domo actions" you see in the Workflow builder (create/update a DataSet, run a DataFlow, AppDB CRUD, send Buzz/Slack/Teams (the Buzz *conversation surface* those messages post into → [`domo-buzz.md`](domo-buzz.md)), manage cards/pages/users) are **NOT dedicated native node types**. They are **Code Engine packages** surfaced as automated-task steps — each step is a function call into a CE package. Only a small set of shapes are truly native to the engine:

- Start (incl. form Start), End
- Gateways: Conditional / Exclusive, Parallel
- Wait, Timer
- User Task / Email task
- Sub Flow (call another workflow)
- AI Agent step

The engine is Camunda/Zeebe-style (the tell is **FEEL** expression syntax in conditions). Consequence for authoring: you cannot enumerate "all actions" from a fixed vocabulary — the action catalog is whatever CE packages are installed. When you need a specific action's exact step JSON, **GET a released workflow that already uses it** and copy the shape; do not invent step schemas.

## Authoring API — [REPO] UNDOCUMENTED internal endpoints (observed live on maintenance-instance, 2026-09-05)

> **Evidence tiers below:** `[DOC]` = in Domo's public API docs / OpenAPI spec; `[REPO]` = observed only on a live instance, **absent from public docs** — reverse-engineered, instance-/version-fragile, re-verify per instance before relying on it. Everything in this section is `[REPO]` unless marked `[DOC]`.
>
> **Domo's _documented_ public Workflows API is run/monitor/admin only** `[DOC]` — two OpenAPI specs cover it (verified 2026-09-06, `www.domo.com/docs/openapi/`, browser-UA fetch):
>
> - **Product** (`product/workflows-api.yaml`) — auth **`X-DOMO-Developer-Token`** (apiKey header); for calls **from outside Domo / another instance / a Jupyter-Workspace script**. `POST /instances/message` = **start by message** (body `{messageName, version, modelId, data{}}`); `POST /instances/{instanceId}/cancel` → `WorkflowInstanceDetailed` (adds `bpmnProcessId/Name`, `isTestRun` — confirms the BPMN engine); `POST /models/{modelId}/permissions` (body = **array** of `{id, type:USER|GROUP, permissions[]}`; enum `ADMIN|SHARE|DELETE|WRITE|READ|EXPORT|EXECUTE|UPDATE_CONTENT`). The spec lists paths **bare** — the `/api/workflow/v1` base is the wire prefix the `[REPO]` section observed.
> - **Framework** (`framework/workflows.yaml`) — auth **bearer JWT** access token; base prefix **`/domo/workflow/v1/models/`**. `POST .../{workflowAlias}/start` = **start by manifest alias** (free-form params keyed by the manifest `aliasName`; 404 = alias not found); `GET .../{workflowAliasedName}/overall` = **metrics** (`WorkflowMetrics` counts + `averageCycleTime`; query `limit/offset/after/until/status`); `GET .../{workflowAlias}/instance/{workflowInstanceId}` = **instance status**.
>
> **Two documented START paths:** product **message-start** keys on `modelId`+`version`+`messageName` (external/script callers); framework **alias-start** keys on the manifest alias (app callers). **No create-model, definition-write, or release endpoint is documented in _either_ spec** (verified against both bodies 2026-09-06); the create/edit/release lifecycle below is undocumented internal API observed on _one_ instance — do **not** rely on it for production without per-instance confirmation. (`automated-action/workflow.yml` is listed in `docs/llms.txt` but 404s on direct fetch = **MISSING**, not proof of absence.)

Auth: `X-Domo-Authentication: <SID>` was observed to authenticate both reads and writes on maintenance-instance — access follows the **caller's own Domo grants**; no separate admin PAT was needed there `[REPO]`. The SID header is **not** a documented auth method — the documented specs authenticate differently: the product spec via `X-DOMO-Developer-Token` (apiKey header), the framework spec via a **bearer JWT** access token `[DOC]`. So the SID is the internal/observed path; a documented external caller uses a Developer Token or access token instead.

**Reads (v1):**

- `GET /api/workflow/v1/models` — list models.
- `GET /api/workflow/v1/models/{id}` — one model + its versions.
- `GET /api/workflow/v1/models/{id}/versions/{ver}` — a version's full definition (copy shapes from here).

**Create / edit / release (v2)** `[REPO]` — undocumented internal endpoints observed to run end-to-end on **one** instance (maintenance-instance); the sequence may change or differ across instances/versions. Re-verify before relying on it:

1. **Shell:** `POST /api/workflow/v2/models` with `{name, description, versions:[{version:"1.0.0"}]}` → returns the model `id`.
2. **Definition:** `PUT /api/workflow/v2/models/{id}/versions/{ver}/definition` with the full definition object.
3. **Release:** `POST /api/workflow/v2/models/{id}/versions/{ver}/release` with `{}` → the version becomes active (observable via `active:true` + the version string in the response). The exact trigger-id field names (`manualTriggerId`/`startEventId`) are **not confirmed** — capture whatever the live release response returns rather than assuming those keys. Until released, a version is a draft and won't trigger.

**Minimal valid definition** `[REPO — observed shape, not documented]` (a released Start→End flow):

```jsonc
{
  "version": 2,
  "schema": { "inputs": {}, "outputs": {} },
  "dataList": [],
  "designElements": [
    { "id": "rootNode", "type": "rootNode", "index": 0,
      "position": {"x":50,"y":40},
      "data": { "title": "Start", "type": "Start", "_designNode": "rootNode",
                "isFormStart": false, "input": [], "output": [] } },
    { "id": "endNode", "type": "endNode", "index": 1,
      "position": {"x":50,"y":260},
      "data": { "title": "End", "_designNode": "endNode", "terminating": false } },
    { "id": "edge-rootNode-endNode", "type": "defaultEdge", "index": 2,
      "source": "rootNode", "target": "endNode", "arrowHeadType": "arrow",
      "data": { "sourcePosition": "right", "targetPosition": "left", "path": [], "title": "" } }
  ]
}
```

Build richer flows by inserting nodes between root and end and rewiring `defaultEdge`s. `isFormStart:true` on the root turns Start into a form (inputs become form fields). Real action/user-task/gateway/AI-agent node shapes are long and package-specific — copy them from a live released workflow (see the architecture fact above).

## Triggers / entry points

| Trigger | How it starts | Notes |
|---|---|---|
| Manual / form Start | User submits an app form or clicks a button; `manualTriggerId` from release. | Most common for app-embedded flows. |
| Timer | Schedule (cron-like). | Native Timer node. |
| Webhook / message | Inbound HTTP or Domo event/Buzz message. | Event-driven entry. |
| DataSet / alert | Alert or dataset-update event. | Ties automation to data changes. |
| Sub Flow call | Invoked by another workflow. | Composition. |

See the reference doc for the full trigger catalog and per-trigger config.

## Gotchas

- **Draft vs released:** editing a definition does nothing live until you `release`. Existing app cards/buttons are wired to a specific `triggerId` — a new release may mint a new trigger; re-check the wiring (mirrors the Code-Engine card-binding snapshot issue — see the inventory-app workflow-version-resolution reference).
- **Conditions are FEEL, not JS/SQL.** `=`/`!=`, `and`/`or`, no `===`. Test expressions in a scratch flow first.
- **Versioning:** models hold multiple versions; only one is active. Bump the version string for a new definition rather than overwriting a released one you may need to roll back to.
- **Action availability is instance-dependent** (installed CE packages). A step that exists on one instance may be absent on another — don't assume portability.
- **Long-running steps / sub-flows:** don't block a turn waiting for a workflow run to finish; poll out-of-band the same way as long ETL runs.

## Safety

- On shared instances (`maintenance-instance`), author only disposable, clearly-named test models (`zz-...-verify-*`), own them, and delete them when done. Never edit/release/delete models you did not create.
- Do not release or trigger production workflows without explicit confirmation.
- Never commit SID values, trigger IDs, session IDs, or **unsanitized** workflow definition exports. A **sanitized** definition mirror — secrets/trigger IDs/session IDs stripped — *is* committed for backup: see `domo-config-backup.md`.

## Validation

- Record the model ID, version, release response (`active`, `manualTriggerId`), and any run result when actually run.
- If a workflow was created but not executed end-to-end, say so.
