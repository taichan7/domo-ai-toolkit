# Domo Task Center

Use this skill to reason about — or drive via REST — **Domo Task Center**: a system that organizes **manual tasks into permissioned queues of work**, most often fed by **Workflows**. The object model is **queue → task (work-item) → its input/output fields**, plus per-queue **permissions**. **Read the naming-trap table below before anything else**: the word "task" alone points at *four* unrelated things across four APIs, and Task Center is the **mirror-opposite of Projects & Tasks** (rank-13) on host and auth — the two share nothing but that word. Conflation is the #1 hazard on this surface, not endpoint mechanics.

Task Center is a **two-world, fully-documented OpenAPI island** — the Pages/FileSets pattern, and the exact **inverse of rank-13 Projects & Tasks** (whose "two YAMLs" were one spec mirrored at two URLs). Here the two YAMLs are **two genuinely different functional worlds**:

- **World A — Product REST** `https://{instance}.domo.com/api/queues/v1/…`, auth **`X-DOMO-Developer-Token`** (apiKey header), OpenAPI **3.0.3**, **10 operations**, spec `openapi/product/task-center-api.yaml`.
- **World B — App-Framework in-app** `https://{instance}.domo.com/domo/queues/v1/…`, auth **`bearerAuth`** (HTTP bearer **JWT**), OpenAPI **3.0.0**, **6 operations = a strict subset** of World A, spec `openapi/framework/taskcenter.yaml`.

Same host, different path base (`/api` vs `/domo`), different auth, different op count. World B drops the four admin/transfer ops (move, assign, void, permissions) but — the surprise — **defines a full `Task` schema that World A leaves untyped**. So this skill is **disambiguation + a faithful map of two documented worlds that diverge in both directions**, guarded hard against over-claiming untested runtime behavior (zero calls were executed against either world).
## What this skill owns (and what it defers)

**Owns:** the Task Center object model (queue / task work-item / task input-output fields / queue permissions) and its **two** documented REST worlds — Product `{instance}.domo.com/api/queues/v1` (dev-token) and App-Framework `{instance}.domo.com/domo/queues/v1` (bearer).

**Defers:**
- **Where tasks come from.** Neither world has a create-task operation; tasks originate upstream — the framework `Task.sourceInfo` carries `workflowInstanceId`/`flowNodeId`/`deploymentId`. The **Workflow → Task-Center wiring** (how a Workflow User-Task/Email step lands a work-item in a queue) → `domo-workflow.md`. This skill maps how you *work* a task, not how one is *created*.
- **Domo Workflows** (the v2 automation engine, User-Task/Email-task steps, triggers) → `domo-workflow.md`.
- **Projects & Tasks** collaborative board (`api.domo.com/v1/projects`, OAuth Bearer) → `domo-projects.md`; here it is **disambiguated, not absorbed** (it is the mirror-opposite on host/auth).
- Identity of the string user/group-ids in `owner`/`createdBy`/`assignedTo`/`assignedBy` and in permission/assign entries → `domo-identity-access.md`.
- Minting the World-A developer token or the World-B bearer JWT (the "authentication flow" the spec names) → `domo-identity-access.md` / `domo-accounts-connectors.md`.
- **Task Center in the UI** ("My Tasks"/inbox, queue admin screens) — out of both specs; treat any UI-route claim as `[INFER]`.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo.com/docs/s/article/<12-digit> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall / 404) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting an untested runtime behavior, an inference-from-absence, or one world's detail as if it held in the other. This entire skill is `[DOC]`/`[INFER]` with **zero `[REPO]`**: no working code in this repo calls either world, and **no request was ever executed against Task Center** — every claim is read from the two specs, so treat all request/response *behavior* (auth acceptance, `/domo/` token-injection, PUT-vs-POST effects, filter semantics) as **documented-but-untested**.

**Verification provenance.** Written after verification Workflow `wf_0f9e3bb3-e94` (19 agents, 107 claims, 12 refuted, 0 errors: 6 spec-reading clusters → adversarial refute of the top over-claim-risk claims, each default-refuted-if-uncertain → completeness critic + island verdict → synthesizer), corroborated by **direct reads of both raw YAMLs**: `product/task-center-api.yaml` (612 lines, 19,309 bytes) and `framework/taskcenter.yaml` (474 lines, 13,851 bytes), each grepped for path roots, methods, schemas, and enum keywords. **The refute pass and a re-read materially corrected the draft:** the completeness critic asserted Task Center was a **single-world** island ("no framework spec — all 404"), but that was a probe for a `queues`-named framework spec; the real framework spec is named **`taskcenter.yaml`** and it exists (in `llms.txt`, 13,851 bytes, `openapi 3.0.0`). Per the tier rule — *a fetch failure is missing evidence, not proof of absence* — the primary fetch wins: **Task Center is two-world.** The critic's other findings held and are encoded below (no create-task op; naming collision is the dominant hazard; prose-only enums in World A; ZERO repo precedent → every op `[DOC]`, never `[REPO]`). 鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).
## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first.

| You see… | It actually is… | Host / auth | Owner |
|---|---|---|---|
| **task** (Task Center) | a **work-item in a queue** (save-progress / complete / move / assign / void) | `{instance}.domo.com` dev-token **or** bearer | **this skill** |
| **task** (Projects & Tasks) | a **card** inside a project **list** (Kanban) — a different feature, different API | `api.domo.com` OAuth Bearer | `domo-projects.md` |
| **task** (Workflow) | a **node/step** in the Workflows v2 engine (User Task / Email / automated) — where a work-item *originates* | Workflows engine | `domo-workflow.md` |
| **task** (Alert action) | "create a Task" **action** fired by an alert → opens a Projects & Tasks card | — | `domo-alerts.md` (action) → `domo-projects.md` (object) |
| **queue** (Task Center) | a **permissioned container of work-items** (`id`, `owner`, per-user/group permissions) | — | **this skill** |
| **queue** (elsewhere) | a message/job/dataflow-run queue — **unrelated infrastructure**, not a Task Center object | — | not a Domo Task Center object |
| **transferTask** (`/move`) | move a task **to another QUEUE** — path `{currentQueueId}`, target is a **required query param** `targetQueueId`, **no body** | World A only | **this skill** |
| **transferTaskToUser** (`/assign`) | assign a task **to a PERSON/group** — body `AssignTaskRequest`, path `{queueId}` | World A only | **this skill** |
| **the "two YAMLs"** | `product/task-center-api.yaml` (`/api`, dev-token, 10 ops) **vs** `framework/taskcenter.yaml` (`/domo`, bearer, 6 ops) = **two functional worlds** | `{instance}.domo.com` | **this skill** |
| **"Workflows"** in the docs | Task Center is *"often used in concert with Workflows"* — a usage note, **not** an OAuth scope; Task Center has **no OAuth scopes at all** (dev-token/bearer) | — | this skill (note) / `domo-workflow.md` |
| **My Tasks / inbox** | a UI surface — **out of both specs**; any route/behavior claim is `[INFER]` | — | this skill (as `[INFER]`) |

**The mirror-opposite framing (memorize this):** Projects & Tasks (rank-13) = `api.domo.com` + **OAuth Bearer** + a **"Workflow" OAuth scope**; Task Center (rank-14) = `{instance}.domo.com` + **dev-token / bearer-JWT** + **no OAuth scope**. They share only the word "task." Do not let a "task" in one API's docs pull you into the other.

## The headline — a two-world documented island `[DOC]`

Two specs, same feature, genuinely different worlds `[DOC]` — the FileSets/Pages pattern, and the inverse of Projects & Tasks (whose two YAMLs were one spec mirrored):

| axis | World A — Product | World B — App-Framework |
|---|---|---|
| spec | `openapi/product/task-center-api.yaml` | `openapi/framework/taskcenter.yaml` |
| OpenAPI version | **3.0.3** | **3.0.0** |
| title / version | "Domo Task Center API" / 1.0.0 | "Task Center API" / v1 |
| host + base | `{instance}.domo.com` **`/api/queues/v1`** | `{instance}.domo.com` **`/domo/queues/v1`** |
| auth | **`X-DOMO-Developer-Token`** (apiKey header, scheme `DeveloperToken`) | **`bearerAuth`** — HTTP bearer **JWT**, *"access token obtained via Domo's authentication flow"* |
| operations | **10** (3 GET / 4 POST / 3 PUT) | **6** (3 GET / 2 POST / 1 PUT) = **strict subset** |
| operationIds | present on all 10 | **none** (summary + tag only) |
| `Task` schema | **absent** — every task return is bare `type: object` | **present** — full ~26-field `Task` graph |
| tags | `Task Center API (Product)` | `Queues` / `Tasks` (+ `Task Center API`) |

**World B's op set is exactly the suffix-identical subset** {get-queues, get-queue, list-tasks, get-task, save-outputs, complete} — it **omits World A's four admin/transfer ops** (move, assign, void, permissions). Read it as the **operator's read-and-progress subset**; queue administration and task transfer live only in World A.

**"Same underlying feature, republished for the in-app context"** is `[INFER]` (the specs don't cross-reference each other), but strongly corroborated `[DOC]`: identical `info.description` prose, identical example UUIDs/task-ids, and a path-suffix-identical op subset. Whether the in-app runtime **auto-injects** the bearer (so `/domo/` calls feel tokenless) is `[INFER]` — the framework spec **explicitly requires a bearer JWT**, so do **not** describe World B as "tokenless."
## World A — the Product REST surface `[DOC]`

**10 operations across 10 paths** (3 GET / 4 POST / 3 PUT), base `/api/queues/v1`, auth `X-DOMO-Developer-Token`, all `[DOC]`. `queueId` is a UUID; `taskId` is a short code like `18OCT23_1JUTZM`.

- **Queues (2 GET):**
  - `GET /api/queues/v1` — **getQueues**. Returns all queues the caller can access (200 = array of `Queue`). Query: `combineAttributes` (bool, default true), `archived` (bool, default false).
  - `GET /api/queues/v1/{queueId}` — **getQueueById** (200 = `Queue`, 404).
- **Tasks — read (1 POST / 1 GET):**
  - `POST /api/queues/v1/tasks/list` — **getTasks**. *List-by-filter is a **POST**, body `TaskListFilters`; an empty `{}` body returns all accessible tasks.* Query: `render` (bool), `renderParts` (csv string, e.g. `NAME,DESCRIPTION,MAPPING,METADATA,VERSIONS`). 200 = **array of bare `type: object`** (World A does not type the task).
  - `GET /api/queues/v1/{queueId}/tasks/{taskId}` — **getTaskById**. Query `render` (bool). 200 = bare `type: object`, 404.
- **Tasks — progress (2, both write to the task's dynamic input/output fields):**
  - `PUT /api/queues/v1/{queueId}/tasks/{taskId}/outputs` — **saveTaskProgress**. Body = an **open object of the task's own field key→value pairs** (`additionalProperties: true`, e.g. `{"Suggested_Action_Items": "...", "Send_to_QA_Team": true}`). Save-without-complete.
  - `POST /api/queues/v1/{queueId}/tasks/{taskId}/complete` — **completeTask**. Same open-object body; query `version` (string, optional). Completes the task.
- **Tasks — transfer (2 PUT — World A only):**
  - `PUT /api/queues/v1/{currentQueueId}/tasks/{taskId}/move` — **transferTask**. Move to another **queue**. **Trap:** path var is **`{currentQueueId}`** (not `queueId`), the target is a **REQUIRED query param `targetQueueId`**, and there is **NO request body**.
  - `PUT /api/queues/v1/{queueId}/tasks/{taskId}/assign` — **transferTaskToUser**. Assign to a **person/group**. Body `AssignTaskRequest` (`type` USER|GROUP, `userId` = a user **or group** id, `tasksId` array). Named "…ToUser" but the enum admits GROUP.
- **Tasks — void (1 POST — World A only):** `POST /api/queues/v1/{queueId}/tasks/{taskId}/void` — **voidTask**. No body. 200 = the voided task.
- **Queue permissions (1 POST — World A only):** `POST /api/queues/v1/{queueId}/permissions` — **updateQueuePermissions**. Body = **array of `PermissionEntry`**. An entry with an **empty `permissions: []` removes all permissions** for that id — a silent revoke footgun.

**Verb inconsistency `[DOC]`:** save-progress and move are **PUT**; complete, void, list-tasks, and permissions are **POST**. There is no consistent "mutation = POST/PUT" rule — read each op. And **there is no create verb of any kind** (see the no-create section).

## World B — the App-Framework in-app surface `[DOC]`

**6 operations across 6 paths** (3 GET / 2 POST / 1 PUT), base `/domo/queues/v1`, auth `bearerAuth` (JWT), all `[DOC]` — a **strict subset** of World A with two schema upgrades. **No operationIds** (match by summary + path).

- `GET /domo/queues/v1` — Get Queues (200 = array of `Queue`).
- `GET /domo/queues/v1/{queueId}` — Get Queue by ID (200 = `Queue`, 404 = `ErrorResponse`).
- `POST /domo/queues/v1/tasks/list` — Get Tasks (body `TaskListFilters`; 200 = **array of the typed `Task`**, not bare object). `render` query defaults **true** here.
- `GET /domo/queues/v1/{queueId}/tasks/{taskId}` — Get Task by ID (200 = typed `Task`, 404 = `ErrorResponse`).
- `PUT /domo/queues/v1/{queueId}/tasks/{taskId}/outputs` — Save Task Progress (body `TaskOutputVariables`; 200 = typed `Task`).
- `POST /domo/queues/v1/{queueId}/tasks/{taskId}/complete` — Complete Task (body `TaskOutputVariables`; 200 = typed `Task`). **Trap vs World A:** `version` query param is **REQUIRED** here and typed **integer** (World A: optional string).

**What World B adds over World A `[DOC]`:** a real `ErrorResponse` schema on 404s, and — the big one — a **fully-typed `Task`** with sub-schemas (`Task_SourceInfo`, `Task_DisplayEntity`/`_Section`/`_Field`, `Task_Contract`). **What it lacks:** the four admin/transfer ops (move, assign, void, permissions) — those are World A only.
## The objects `[DOC]`

**`Queue`** (both worlds, 11 fields) `[DOC]`: `id` (string/uuid), `name` (string), `description` (string, nullable in B), `active` (bool), `taskLevelFiltersEnabled` (bool), `taskLevelFilters` (nullable — untyped in A, `object` in B), `owner` (string user-id), `createdBy` (string), `createdOn` (date-time), `updatedBy` (string), `updatedOn` (date-time). **User-ids on the queue are STRINGS here** (e.g. `owner: "8811501"`) — unlike Projects & Tasks, where user-ids are integers. Don't cross the two.

**`Task`** — the world-dependent field-shape trap `[DOC]`:
- **World A**: **there is no `Task` schema.** Every task-returning 200 is `type: object` with no properties. The task's field shape is **learned at runtime only** — for World A, task-field claims are `[INFER]`.
- **World B**: a **fully-typed `Task`** (~26 fields) `[DOC]`: `id`, `queueId` (uuid), `version` (integer), `status`, `displayType`, `assignedTo`/`assignedBy`/`assignedOn`, `completedBy`/`completedOn` (nullable), `lockedBy`/`lockedOn` (nullable), `assigneeType` (enum **`['USER']`** only), `createdBy`/`createdOn`/`updatedBy`/`updatedOn`, `tags`/`comments`/`attributes` (arrays), `sourceSystem`, `sourceInfo`, `displayId`, `displayEntity` (the render form — sections→fields), `contract` (`input`/`output` property lists), and `inputVariables`/`outputVariables` (open `additionalProperties: true` key→value maps). Use the **framework** spec, not the product spec, when you need to know a task's fields.

**`status` and `displayType` — closedness is world-dependent `[DOC]`/`[INFER]`:**
- Values are stable across both worlds: **`status` ∈ {OPEN, COMPLETED, VOIDED}**, **`displayType` ∈ {ENIGMA_FORM, EMAIL, UNKNOWN}** `[DOC]`.
- In **World B** they are **machine-readable closed `enum:`** (on `Task` and on `TaskListFilters`) `[DOC]`.
- In **World A** the same values are **prose-only** inside `TaskListFilters` descriptions (`type: string`, no `enum:` keyword) — so World-A machine-closedness is `[INFER]`; the value set itself is still `[DOC]`.

**`TaskListFilters`** (the `POST …/tasks/list` body) `[DOC]`: every property is an **array**, all optional, empty `{}` → all tasks. World A has **13** filters; the scalar-id filters are `queueId`, `displayType`, `status`, `assignedBy`, `assignedTo`, `createdBy`, `completedBy`, `version`; the **date-range** filters (`createdOn`, `assignedOn`, `updatedOn`, `completedOn`) are **arrays of `[start, end]` datetime pairs** (note the double-nesting: `[["2023-…Z","2024-…Z"]]`); plus an ordering array. **Name trap:** the ordering field is **`orderByString`** in World A but renamed **`orderBy`** in World B — the two worlds are **not** field-identical.

**`AssignTaskRequest`** (World A `/assign` body) `[DOC]`: required `type` (enum **USER|GROUP**) + `userId` (string, holds a user **or group** id); optional `tasksId` (array of string).

**`PermissionEntry`** (World A `/permissions` body items) `[DOC]`: required `id`, `permissions`, `name`, `type`. `type` ∈ enum **USER|GROUP**. `permissions` is an array over the **closed 11-value enum** `{ADMIN, SHARE, DELETE, WRITE, READ, CREATE_CONTENT, READ_CONTENT, UPDATE_CONTENT, DELETE_CONTENT, EXPORT, EXECUTE}`; an **empty array removes all permissions** for that id `[DOC]`.

## No create-task operation — where tasks come from `[DOC]` / `[INFER]`

**Neither world has an operation that creates a task or a queue.** The full mutation set is: save-progress, complete, move, assign, void (task) and permissions (queue) — every one addresses a task/queue that **already exists** `[DOC]` (documented-from-absence: exhaustive read of both specs' paths, so the *absence* is `[INFER]`, but well-founded). Work-items **originate upstream**:

- The `info.description` states Task Center queues are *"often used in concert with Workflows"* `[DOC]`.
- The framework `Task.sourceSystem` + **`Task.sourceInfo`** carry `workflowInstanceId`, `flowNodeId`, `deploymentId`, `modelId`, `modelVersion`, `instanceId`, `elementInstanceKey`, `taskKey` `[DOC]` — the task **records the Workflow node it came from**. That provenance is documented; the **creation *mechanism/endpoint* is not in either Task Center spec.**

So: **do not look for (or synthesize) a "create task" REST call here.** How a Workflow User-Task/Email step produces a queue work-item is **uncharted by this surface → defer to `domo-workflow.md`.** "Creation is Workflow-only / impossible via any REST" is `[INFER]` (documented-absence), not `[DOC]` fact.
## Projects & Tasks / Workflow / Alert tasks are different features — disambiguate, don't absorb

Task Center is the **mirror-opposite of Projects & Tasks** (rank-13) and shares nothing with it but the word "task." They diverge on five independent `[DOC]` axes — the reverse of every axis:

| axis | Task Center (this skill) | Projects & Tasks (`domo-projects.md`) |
|---|---|---|
| host | `https://{instance}.domo.com` | `https://api.domo.com` |
| auth | **dev-token** (World A) / **bearer JWT** (World B) — **no OAuth scope** | HTTP **Bearer** (OAuth) — requires a **"Workflow" scope** |
| path base | `/api/queues/v1` · `/domo/queues/v1` | `/v1/projects` |
| object model | **queue → task work-item** (complete/void/move/assign/outputs) | project → **list** (Kanban column) → **task card** → attachment/member |
| worlds | **two functional worlds** (product + framework) | **one** spec mirrored at two doc URLs |

- **Workflow "task"** is a **node/step** in the Workflows v2 engine — the *origin* of a Task Center work-item, not the work-item itself → `domo-workflow.md`.
- **Alert action "create a Task"** opens a **Projects & Tasks card**, not a Task Center queue item → `domo-alerts.md` (action) → `domo-projects.md` (object).
- Route all `/api/queues/v1` and `/domo/queues/v1` work here; route `/v1/projects` to `domo-projects.md`; route the Workflow engine and the create-mechanism to `domo-workflow.md`.

## Boundaries & orphans

- **The two worlds are not field-identical `[DOC]`.** Beyond the op-count and auth split: `orderByString` (A) vs `orderBy` (B); `complete`'s `version` is optional-string (A) vs required-integer (B); World B adds `ErrorResponse` and the typed `Task` graph that World A omits; `taskLevelFilters` is untyped (A) vs `object` (B). Don't assume a detail read in one world holds in the other.
- **Whether `/domo/` is tokenless is `[INFER]`** — the framework spec requires a bearer JWT; the in-app auto-injection is inferred, never executed. Don't hard-code "no token needed."
- **Whether World A rejects a bearer / World B rejects a dev-token is `[INFER]`** (spec-silence, never executed) — each spec declares one scheme; cross-acceptance is untested.
- **Task field shape in World A is `[INFER]`** (bare `object`) — use World B's typed `Task` for field names; do not assert World A returns those exact fields until observed.
- **`combineAttributes` / `render` / `renderParts` runtime effects are uncharted `[INFER]`** — the params are `[DOC]`, but what a "rendered" task or "combined attributes" payload actually contains was not executed.
- **Pagination is absent from both specs `[INFER]`** — `getTasks` has no offset/limit params; how large task lists are bounded is unknown. Do not invent a pager.
- **Task Center UI ("My Tasks", queue admin) is out of both specs `[INFER]`** — the board UI drives some internal route; don't document it as fact.
- **Scheduled Reports, Workflows, Projects & Tasks are neighbors, not parts** — disambiguate; do not absorb.

## Repo false friends `[REPO]`

**Repo precedent = ZERO** `[REPO]`. A full-tree grep (all `.py/.js/.mjs/.ts/.sh/.ipynb`, tracked + untracked) for `queues/v1`, `/api/queues`, `/domo/queues`, `task-center`, `taskcenter`, `getQueues`, `transferTaskToUser`, `voidTask`, `updateQueuePermissions` returns **no API caller** — the only file matching is this skill doc. **Therefore every operation stays `[DOC]`, never `[REPO]`,** and no request was ever executed. The near-miss false friend:

- Many apps send **`X-DOMO-Developer-Token`** — but every one targets a *different* API: `news-summary-app/code-engine/fileset_ops.py` and the `fileset-*` tools hit **FileSets** (`/api/files/v1`), the `*/scripts/provision_domo.py` set hit provisioning, `production-priority-app/dataflow/deploy_*.py` hit DataFlows, `beast-mode-manager/bm_bulk_lock.py` hits datasets. **Same auth header, unrelated surface.** The dev-token being ubiquitous is exactly why the queue-path needles (`queues/v1`) are the real test — and they are zero.
- No app-internal identifier named `queueId`, `targetQueueId`, `taskLevelFilters`, or `assigneeType` exists in repo code.

The FileSets product-vs-in-app split (`/api/files/v1` dev-token, seen in `fileset_ops.py`) is the **known Domo precedent** for the exact two-world pattern Task Center follows — that pattern's *existence* is `[REPO]`-anchored, even though no Task Center call is.
## Do NOT claim as documented fact

1. **Do NOT** call Task Center single-world — it is **two functional worlds** (product `/api` dev-token 10 ops vs framework `/domo` bearer 6 ops). (The verification critic's "single-world" was a mis-probe; the framework spec `taskcenter.yaml` exists.)
2. **Do NOT** claim a **create-task** (or create-queue) REST op exists — neither world has one; tasks originate upstream from Workflows. State creation-via-REST-is-impossible as `[INFER]`, and defer the mechanism to `domo-workflow.md`.
3. **Do NOT** say World-A tasks have specific fields — World A returns bare `type: object`; the typed `Task` lives **only in World B**. World-A task-field claims are `[INFER]`.
4. **Do NOT** present `status`/`displayType` as machine-enforced enums **in World A** — there they are prose-only `type: string`. They are closed `enum:` only in **World B**. (The value sets are `[DOC]`; World-A closedness is `[INFER]`.)
5. **Do NOT** describe World B (`/domo/`) as "tokenless" — the framework spec **requires a bearer JWT**; auto-injection by the in-app runtime is `[INFER]`.
6. **Do NOT** call `transferTask` (`/move`) a body-carrying or `queueId`-pathed op — it uses **`{currentQueueId}`**, a **required query param `targetQueueId`**, and **no body**. Sending a body or the wrong path var silently misfires.
7. **Do NOT** conflate `transferTask` (move to a **queue**) with `transferTaskToUser` (assign to a **person/group**) — different verbs, paths, and bodies.
8. **Do NOT** assume the two worlds are field-identical — `orderByString` (A) vs `orderBy` (B), `complete.version` optional-string (A) vs required-integer (B), and World B's extra schemas all diverge.
9. **Do NOT** state that World A rejects a bearer, or World B a dev-token, as fact — `[INFER]` from spec-silence, never executed.
10. **Do NOT** invent pagination — no offset/limit params exist on `getTasks` in either world; bounding behavior is unknown `[INFER]`.
11. **Do NOT** send a `PermissionEntry` with `permissions: []` casually — an empty array **removes all permissions** for that id.
12. **Do NOT** treat *"used in concert with Workflows"* as an OAuth scope — Task Center has **no OAuth scopes**; that phrase is a usage note (contrast Projects & Tasks, whose scope really is named "Workflow").
13. **Do NOT** frame any request/response **behavior** as "verified/works" — the whole skill is `[DOC]`/`[INFER]` with **zero `[REPO]`** and zero executed calls.

## Safety & hygiene

- **Never** write the World-A developer token or the World-B bearer JWT into source, handoffs, or commits — read from config at call time. Never log the token-exchange / auth flow.
- **`voidTask`, `transferTask`/`transferTaskToUser`, and `updateQueuePermissions` are state-changing on shared work** — a voided or moved task disappears from the current operator's view; a permissions write can lock people out (empty array = revoke-all). Confirm human intent before any mutation; do not act on a queue/task you don't own.
- **`completeTask` is terminal** — it closes the work-item with whatever field values you send. Save-progress (`/outputs`) first if unsure; don't complete a task you can't fill correctly.
- **`updateQueuePermissions` is replace-semantics on the submitted entries** — the array you send is authoritative for those ids; read the current permissions and send the full intended state, or you may silently revoke.
- **Probe read-only first** (`getQueues`, then `getTasks` with an empty `{}` body scoped by `queueId`) to confirm auth and access before any write. Prefer World B (`/domo/`) inside an in-app/CodeEngine context where the bearer is already present; prefer World A (`/api/`) for out-of-app automation and for the admin ops World B lacks.
- Keep the two worlds' auth straight: **`X-DOMO-Developer-Token` header for `/api/queues/v1`**, **`Authorization: Bearer <JWT>` for `/domo/queues/v1`**. Mixing them is the most likely 401.

## Companion skills

- `domo-workflow.md` — the Workflows v2 engine; **owns where a Task Center work-item comes from** (the create-mechanism this skill defers). The docs' *"used in concert with Workflows"* points here.
- `domo-projects.md` — the rank-13 **mirror-opposite**: Projects & Tasks (`api.domo.com/v1/projects`, OAuth Bearer, single mirrored world). The contrast case — same word "task", opposite host/auth/world-shape.
- `domo-alerts.md` — the alert **Action** "create a Task" (opens a Projects & Tasks card, not a Task Center queue item).
- `domo-identity-access.md` — the string user/group-ids in `owner`/`assignedTo`/`AssignTaskRequest`/`PermissionEntry`; minting the dev-token and the bearer JWT.
- `domo-pages.md` / FileSets — the other **two-world** (product-vs-in-app) surfaces; Task Center follows the same `/api` + `/domo` pattern.
