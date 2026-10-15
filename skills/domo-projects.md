# Domo Projects & Tasks

Use this skill to reason about — or drive via REST — a Domo **Projects & Tasks** board: a collaborative work board (Domo Engage) with the hierarchy **project → lists (Kanban columns) → tasks (cards) → attachments**, plus project **members**. **Read the naming-trap table below before anything else**: the word "task" alone points at *four* unrelated things across three APIs, and the OAuth scope this API requires is literally named **"Workflow"** — which is *not* the Domo Workflows product. Conflation is the #1 hazard on this surface, not endpoint mechanics.

The surface is a **single-world, fully-documented OpenAPI island**. Everything lives in one place — `POST/GET/PUT/DELETE https://api.domo.com/v1/projects/…`, OAuth Bearer, **21 operations** (10 GET · 3 POST · 5 PUT · 3 DELETE), every op `[DOC]`, **zero repo precedent**. Unlike classic Pages (rank-11), there is **no** Platform-vs-Product two-world split here: the "two YAMLs" you'll find in the catalog (`openapi/platform/projects.yaml` and portal `Projects-And-Tasks-API.yaml`) are **one spec republished at two doc URLs — a documentation mirror pair, not two functional worlds**. The only genuine *second* surface is **Task Center** — a wholly separate feature that shares nothing with this one but the word "task" (different host, auth, path base, and object model). So this skill is mostly **disambiguation + a faithful map of one documented island**, guarded hard against over-claiming untested runtime behavior.

## What this skill owns (and what it defers)

**Owns:** the Projects & Tasks board object model (project / list / task / attachment / member) and its one documented REST surface on `api.domo.com/v1/projects`.

**Defers:**
- Domo **Workflows** (the v2 automation engine, User-Task/Email-task steps, inbound HTTP triggers) → `domo-workflow.md`. The OAuth scope name "Workflow" is a **trap**, not a link to that product.
- **Task Center** work-queues (`/api/queues/v1`) → its own future skill; here it is **disambiguated, not absorbed**.
- Identity of the integer user-ids in `members`/`createdBy`/`ownedBy`/`contributors` → `domo-identity-access.md`.
- The Alert **Action** "create a Task" (which opens a P&T task when an alert fires) → `domo-alerts.md` owns the action side; the created object is a P&T task owned here.
- OAuth client/token minting and scopes → `domo-identity-access.md` / `domo-accounts-connectors.md`.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo.com/docs/s/article/<12-digit> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting a repo convenience, an untested runtime behavior, or an inference-from-absence as a documented contract. This entire skill is `[DOC]`/`[INFER]` with **zero `[REPO]`**: no working code in this repo calls this API, and **no request was ever executed against it** — every claim is read from the spec, so treat all request/response *behavior* (auth acceptance, PUT merge-vs-replace, path routing, pagination) as **documented-but-untested**.


## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first.

| You see… | It actually is… | Host / auth | Owner |
|---|---|---|---|
| **"Workflow" scope** | the OAuth **scope name** this API requires — *not* the Domo Workflows product | (scope on the OAuth client) | this skill (requirement); `domo-identity-access.md` (client/scopes) |
| **task** (P&T) | a card inside a project **list** (attachments, contributors, priority) | `api.domo.com` OAuth Bearer | **this skill** |
| **task** (Task Center) | a work-item in a **queue** (complete/void/move/assign/outputs) | `{instance}.domo.com` dev-token | Task Center (future skill) |
| **task** (Workflow) | a **node/step** in the Workflows v2 engine (User Task / Email / automated-task) | Workflows engine | `domo-workflow.md` |
| **task** (Alert action) | "create a Task" **action** fired by an alert → opens a P&T task | — | `domo-alerts.md` (action) → this skill (object) |
| **list** (object) | a Kanban **column** on the board (`type` TODO/WORKING_ON/COMPLETED) | — | **this skill** |
| **list** (verb) | the `retrieve-all-*` **GET** operations — the HTTP verb, unrelated to the List object | — | **this skill** |
| **board** | Domo UI/marketing name for a project's Kanban view — the API resource is **`project`** | — | **this skill** |
| **project** (`me`) | magic self-reference id → the caller's **personal** project; not an enumerable real id | — | **this skill** |
| **project** (repo/ETL/Jupyter) | workspace folders, `tasks/`, "Jupyter Workspaces", ETL DataFlows — **not** a Domo object | — | the repo / other skills |
| **member** | an **integer user-id** in `members[]` / `/members` — not a group member, not PDP membership | — | this skill; identity → `domo-identity-access.md` |
| **the "two YAMLs"** | `platform/projects.yaml` ≡ portal `Projects-And-Tasks-API.yaml` = **one spec at two doc URLs** (mirror pair), not two APIs | `api.domo.com` | **this skill** |

## The headline — a single-world documented island `[DOC]`

`https://api.domo.com/v1/projects/…` — **OpenAPI 3.1.0, title "Projects and Tasks API"**, one server (`https://api.domo.com`), auth **HTTP Bearer** (an OAuth access token) `[DOC]`. **A "Workflow" OAuth scope is required** — stated verbatim in `info.description`: *"You will need to ensure that your client application has access to the Workflow scope in order to access the Projects and Tasks endpoints."* `[DOC]`. That requirement is **prose-only**: the machine-readable `securitySchemes` block declares only `bearerAuth` (bare `http`/`bearer`, no `flows`/`scopes`), so tooling will **not** enforce the scope for you — a client missing it fails at call time, not at build time `[INFER]`.

There is **no documented Product-side (`{instance}.domo.com`) API for the collaborative board** — but state that as `[INFER]`, never as fact: a universal negative can't be `[DOC]`, and the board UI must drive *some* internal `{instance}/api/` route (the World-A/World-B pattern seen on Pages). A raw `X-DOMO-Developer-Token` against `api.domo.com/v1/projects` almost certainly 401s, but that too is `[INFER]` (spec-silence, never executed) — don't hard-code a claim that dev-token is rejected.

## The Projects & Tasks REST surface `[DOC]`

**21 operations** (10 GET, 3 POST, 5 PUT, 3 DELETE), all `[DOC]`. Base `/v1`. Hierarchy: `projects` → `members` → `lists` → `tasks` → `attachments`. **Path-key count is representation-dependent `[DOC]`** — **11** in the platform mirror, **12** in the dev-portal spec (which bakes the two task-list pagination query-strings `?offset={OFFSET}&limit={LIMIT}` *into* their path keys, splitting create-task `PUT` onto its own bare `…/lists/{LIST_ID}/tasks` key); the **21-operation** total is stable across both. Do **not** additively sum the mirror pair.

- **Projects (5):** `GET /v1/projects` (retrieve-all) · `POST /v1/projects` (create) · `GET /v1/projects/{PROJECT_ID}` · `PUT /v1/projects/{PROJECT_ID}` (update) · `DELETE /v1/projects/{PROJECT_ID}`.
- **Members (2):** `GET /v1/projects/{PROJECT_ID}/members` · `PUT /v1/projects/{PROJECT_ID}/members` (update — replaces membership).
- **Lists (5):** `GET …/lists` · `POST …/lists` (create) · `GET …/lists/{LIST_ID}` · `PUT …/lists/{LIST_ID}` (update) · `DELETE …/lists/{LIST_ID}`.
- **Tasks (5):** `GET …/tasks` (all tasks in project) · `GET …/lists/{LIST_ID}/tasks` (all tasks in list) · **`PUT …/lists/{LIST_ID}/tasks` (create — a PUT to the *collection*, not POST)** · `GET …/lists/{LIST_ID}/tasks/{TASK_ID}` · `PUT …/lists/{LIST_ID}/tasks/{TASK_ID}` (update).
- **Attachments (4):** `GET …/tasks/{TASK_ID}/attachments` (list) · `POST …/tasks/{TASK_ID}/attachments` (add) · `GET …/tasks/{TASK_ID}/attachments/{ATTACHMENT_ID}` (download) · **`DELETE /v1/project/{PROJECT_ID}/tasks/{TASK_ID}/attachments/{ATTACHMENT_ID}` (delete).**

**Two verb traps, both `[DOC]`:**
1. **Create-a-task is `PUT` to the `…/tasks` collection**, while create-a-list is `POST` and create-a-project is `POST`. The creation verbs are inconsistent across sibling resources. "No POST **creates** a task; task creation is PUT-to-collection" is the precise claim — do **not** say "no POST on any task URL" (add-attachment is a POST on a `…/tasks/{TASK_ID}/attachments` URL).
2. **The delete-attachment path is anomalous, doubly:** singular **`/v1/project/`** (every other attachment path is plural `/v1/projects/`) **and it omits the `/lists/{LIST_ID}` segment**. This is documented **as written**, but **untested** — do **not** assert that either the malformed path *or* a "corrected" plural/`/lists/` path is the route that actually works. Only an executed `DELETE` settles it.

**Pagination** (task-list GETs) `[DOC]` values with a **silent trap:** the descriptions say offset defaults to 0, limit defaults to 10, max 50 — but the numbers are **prose-only** (no `default:`/`maximum:` keywords) **and the parameter names are swapped against their descriptions**: the param literally named `OFFSET` carries the *limit* description and the param named `LIMIT` carries the *offset* description, in both task endpoints. Which name governs which at runtime is **unverified** — probe before trusting either. (These are 10/50, distinct from other Domo APIs' figures.)

## The objects `[DOC]`

`components.schemas` is **empty (`{}`)** `[DOC]` — there is no reusable canonical schema. Each object shape is defined **twice and divergently**: (a) inline per-endpoint schemas, and (b) a prose attribute table in `info.description`. The fields below are the union; where they disagree, that's a silent trap.

- **Project** — inline response (6): `id`=**string**, `name`=string, `members`=array of integer (user-ids), `createdBy`=integer, `createdDate`=string, `public`=boolean. Prose adds `description` and `dueDate` — **but these are create/update *query params*, never present in any inline response schema**; do not list them as returned fields `[DOC]`.
- **List** — 4 fields, consistent: `id`=string, `name`=string, `type`=**string**, `index`=integer. `type`'s values `TODO` / `WORKING_ON` / `COMPLETED` are the **default swim-lane categories**, introduced in prose with "i.e." — there is **no `enum:` keyword** anywhere and users can create custom lists, so treat this as an **open, illustrative set `[INFER]`**, not a closed documented enum. (Only the update-list param uses closed-set wording; the object table and create-list param use "i.e.")
- **Task** — fullest inline schema (create/update/individual-GET), 13 fields: `id`=**string**, `projectId`=string, `projectListId`=string, **`taskName`** (NOT `name` — Task has no `name` field), `createdDate`=string, `updatedDate`=string, `priority`=integer, `createdBy`=integer, `ownedBy`=integer, `contributors`=array of integer, `attachmentCount`=integer, `tags`=**array of object (shape undocumented — `properties {}`)**, `archived`=boolean. The list/get-all response **omits `updatedDate`** (12 fields). Prose adds `description`/`dueDate` (query-param only) and **mislabels `tags` as "String"** and carries literal typos (`projectListId` "tring", `createdDate` "ate").
- **Attachment** — inline response (6 fields), schematized **identically** in both the list-attachments and add-attachment `200` responses `[DOC]`: `id`=**integer**, `taskId`=**integer**, `createdDate`=string, `createdBy`=integer, `fileName`=string, `mimeType`=string. Note `attachment.id`/`taskId` are **integer** — a *second* integer-id family (object-ids), distinct from both the string `id` on Project/Task and the integer *user*-id family.

**The label-field divergence is a silent trap `[DOC]`:** **Project and List use `name`; Task uses `taskName`** (there is no `Task.name`). Sending `name` where `taskName` is expected fails silently. `id` is a **string** on Project and Task (but **integer** on Attachment — object-ids are their own family), while user-ids (`members`/`createdBy`/`ownedBy`/`contributors`) are the **integer** family (prose calls them "Long"). Don't document a writable `tags` structure — its shape is `[INFER]` at best.

**Writes are documented twice — and the two forms diverge `[DOC]`.** The spec carries **7 `requestBody` blocks** (create/update project, update-members, create/update list, create/update task) whose writable-field sets **differ from the same op's query-param sets**: e.g. the create-task **body** carries `id`/`projectId`/`projectListId`/`archived` that the query params lack, while the **params** carry `description`/`dueDate`/`ownedBy` the body lacks; update-a-project's body is **only `name`**; update-members' body is a **bare integer array**. Two **type** divergences ride along: `public` is **boolean** as a create-project query param and in the response but a **string** (uppercase boolean literal) in the request body; and task `priority`/`ownedBy`/`contributors` are **integer** in create-task params but **string** in update-task params. ⚠ `[REPO]`=0 (no call ever executed) — these are documented-but-untested inconsistencies; do **not** assert which representation the runtime honors or how it coerces types (**runtime precedence/coercion `[INFER]`**).

## Task Center is a different feature — disambiguate, don't absorb

**Task Center is a wholly separate feature — disambiguate, do not absorb.** It shares nothing with Projects & Tasks but the word "task"; it diverges on **five independent `[DOC]` axes**:

| axis | Projects & Tasks (this skill) | Task Center (other) |
|---|---|---|
| host | `https://api.domo.com` | `https://{instance}.domo.com` |
| auth | HTTP **Bearer** (OAuth) | **`X-DOMO-Developer-Token`** (apiKey header) |
| path base | `/v1/projects` | `/api/queues/v1` |
| object model | project → **list** (Kanban column) → **task card** → attachment/member | **queue** → **task work-item** (complete / void / move / assign / outputs) |
| catalog | `platform/projects.yaml` (+ portal mirror) | `product/task-center-api.yaml` (+ `framework/taskcenter.yaml`, server `{instance}`, `/domo/queues/v1/…`) |

Task Center is *"often used in concert with Workflows"* `[DOC]` — it is where a Workflow **User-Task / Email-task** step plausibly lands for a human to action, but that Workflow↔Task-Center relationship is `[INFER]`, state it as unverified. Route all `/api/queues/v1` work to the Task Center cluster; it gets its own skill.

## Boundaries & orphans

- **The "two YAMLs" are one API.** `openapi/platform/projects.yaml` and portal `Projects-And-Tasks-API.yaml` are a **mirror pair** — same host, same 21 ops, same auth model `[DOC]`. They are **not byte-identical**: the root security-scheme *label* diverges (`bearerAuth` vs `API Key - 1`) `[DOC]`. Do not present them as two functional worlds (the Pages Platform-vs-Product split does **not** recur here) and do not claim byte-identity.
- **No documented Product-side board API** `[INFER]` (universal negative; see headline). The board UI drives some internal `{instance}/api/` route, undocumented.
- **PUT semantics unread** `[INFER]`: whether `PUT` full-replaces or merges was not verified for update-project / update-members / update-list / update-task / create-a-task. Treat `PUT`/`update-members` as **potentially replace-semantics** (the classic Domo footgun, cf. Pages `owners`/`collectionIds`) until probed.
- **`members` vs `PUT …/members` — reconciled `[DOC]`.** update-a-project documents `id`/`members`/`createdBy`/`createdDate` as **read-only** (*"cannot be updated with this request"*), exposes **no `members` param**, and carries a request body of **only `name`** — so membership is set at **create** and changed only via the dedicated **`PUT …/members`** endpoint, never silently through update-a-project. ⚠ This reconciliation is scoped to **update-a-project**; the general `PUT` full-replace-vs-merge question for *writable* fields stays `[INFER]` (spec silent) — the lists/tasks replace-semantics footgun is unaffected.
- **Attachment I/O — partly documented, partly unread.** The add-attachment `POST` is documented as a **multipart form** upload `[DOC]` (*"Add a multipart form file to a task item as an attachment"*) — so it is **not** a raw-binary body; but the op carries **no `requestBody` schema**, so the exact Content-Type / multipart boundary / form-field name stay **unspecified** `[INFER]` (unspecified ≠ absent — invent no media type). The download `GET` is documented to *"return the downloaded bytes of the attachment on the response body"* `[DOC]`, but its `200` has **no `content:` node**, so the response **Content-Type is undocumented** `[INFER]`.
- **Scheduled Reports / Task Center** are neighbors, not parts — see the disambiguation table and the Task Center section; do not absorb either.

## Repo false friends `[REPO]`

**Repo precedent = ZERO** `[REPO]`. A full-tree grep (all `.py/.js/.mjs/.ts/.sh/.ipynb`, tracked + untracked) for `/v1/projects`, `projects/…/lists`, `…/members`, `/api/queues`, `task-center`, `taskcenter` returns **no API caller** — the only file matching is this skill doc. Therefore **every operation stays `[DOC]`, never `[REPO]`.** Unlike `domo-alerts.md` (which had dangerous code-level false friends like `ALERT_HISTORY`), the false friends here are all **non-Domo-object** noise:

- `safety-command-center/app.js` uses **"projects"** as a construction-site data dimension.
- inventory tests use **"re-projects"** (balance re-projection).
- `brokerage/main.py` has a `flask.palletsprojects.com` URL in a comment.
- `../scripts/validate-workspace.sh` / `list-projects.sh` parse the **`tools.json` "projects"** catalog array (workspace metadata).
- the repo's **`tasks/`** directory (`in-progress.md`, `backlog.md`) = cross-agent work notes, referenced by several scripts and `asset_lifecycle_service.py`.
- marketdata `ml_pipeline` test uses `kwargs['tasks']` for ML training tasks.

None of these are the Domo Projects & Tasks object. No app-internal identifier named `projectId`/`projectListId`/`taskName` exists in repo code.

## Do NOT claim as documented fact

1. **Do NOT** call `List.type` a closed/documented **enum** — it is `type: string` with no `enum:` keyword; `TODO/WORKING_ON/COMPLETED` are illustrative ("i.e.") defaults, custom lists exist → `[INFER]`.
2. **Do NOT** present the clean pagination mapping (OFFSET=0, LIMIT 10/max 50) as documented — the param **names are swapped** against their descriptions and the numbers are prose-only; the runtime mapping is untested.
3. **Do NOT** state that a developer token is rejected / that OAuth Bearer is mandatory as **fact** — that's `[INFER]` from spec silence, never executed. (The scope requirement *is* `[DOC]` prose; dev-token rejection is not.)
4. **Do NOT** assert that the anomalous delete-attachment path (singular `/v1/project/`, no `/lists/`) **works**, nor that a "corrected" plural/`/lists/` path works — documented-as-written but unverified; only an executed `DELETE` settles it.
5. **Do NOT** say "there is no POST on any task URL" — add-attachment is a POST. The safe claim: **no POST *creates* a task; creation is PUT-to-collection.**
6. **Do NOT** call the platform and portal YAMLs byte-identical mirrors — the auth **model** is identical, the security-scheme **label** is not (`bearerAuth` vs `API Key - 1`).
7. **Do NOT** list `description`/`dueDate` as returned object fields — they exist only as create/update **query params**, never in any inline response schema.
8. **Do NOT** document a writable `tags` structure — the object shape is undocumented (`properties {}`); prose mislabels it "String".
9. **Do NOT** imply the "Workflow" scope is machine-enforced — it is **prose-only** in `info.description`, absent from `securitySchemes`.
10. **Do NOT** state a blanket "instance hosts are not allowed" — the host `api.domo.com` is `[DOC]`, but the corollary is `[INFER]`, and **Task Center does use the instance host**, so an unhedged version is doubly misleading.
11. **Do NOT** assert "no Product-side Projects & Tasks board API exists" as fact — universal negative, `[INFER]` only.
12. **Do NOT** frame any request/response **behavior** as "verified/works" — the whole skill is `[DOC]`/`[INFER]` with **zero `[REPO]`** and zero executed calls.
13. **Do NOT** treat the OAuth scope name "Workflow" as evidence that Projects & Tasks is part of Domo Workflows — it is only a scope label.

## Safety & hygiene

- **Never** write the OAuth Bearer token / client secret / dev-token into source, handoffs, or commits — read from config at call time. Never log the `/oauth/token` exchange.
- **`DELETE /v1/projects/{PROJECT_ID}` is high-blast-radius** — it removes a shared collaborative board (lists, tasks, attachments, membership) for everyone. Same for `delete-a-list` (drops its tasks). Confirm human intent before any destructive call; do not delete a board you did not create.
- **`PUT …/members` and writable `PUT` updates may be replace-semantics** (unverified `[INFER]`) — read the current object first and send the full intended state, or you may silently drop members/fields. (Members specifically **cannot** be dropped via *update-a-project* — they are read-only there `[DOC]`; the replace-semantics caution is about `PUT …/members` and other writable-field updates.)
- **`me` is a magic project id** (the caller's personal project) — do not treat it as an enumerable real id when iterating.
- Probe read-only first (`GET /v1/projects`) to confirm auth/scope before any write, since scope enforcement is call-time only.

## Companion skills

- `domo-workflow.md` — the Workflows v2 engine (the "Workflow" **scope name** points at the OAuth scope, not this product; Workflow User/Email tasks are a different "task").
- `domo-alerts.md` — the alert **Action** "create a Task" that opens a P&T task.
- `domo-identity-access.md` — the integer user-ids in `members`/`createdBy`/`ownedBy`; OAuth client/scope minting.
- `domo-accounts-connectors.md` — OAuth client credential object / token minting.
- `domo-pages.md` — the rank-11 sibling and the contrast case: Pages **is** a two-world (Platform vs Product) object; Projects & Tasks is **not** (single documented world + a same-word-different-feature collision).
- Task Center (`/api/queues/v1`) — a distinct feature awaiting its own skill; disambiguated here.
