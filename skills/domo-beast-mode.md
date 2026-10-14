# Domo Beast Mode API Skill

Use this when a task **reads, searches, locks/unlocks, or updates Beast Mode calculated fields** through
Domo's query API (`/api/query/v1/functions/...`), or when a Pro Code app needs to **consume** dataset Beast
Modes in its data reads. It covers the documented endpoint surface, auth (including the CE-tokenless path),
the `search`/`lock`/`update`/`get` operations, Beast Mode concepts, where-used/lineage, and the
internal/undocumented endpoints you must NOT present as a public contract. Companions: Code Engine auth +
mechanics in [`domo-code-engine.md`](domo-code-engine.md); standard cards in [`domo-cards.md`](domo-cards.md);
Magic ETL formula tiles (a different formula engine) in [`domo-magic-etl.md`](domo-magic-etl.md).

> **The documented Beast Modes API is small and stable, but the create/variable/lineage surface is NOT.**
> Domo publishes exactly **five** operations (search, statistics, get-by-id, update-expression, lock).
> Creating a Beast Mode, checking a variable name, and walking a Beast-Mode→Beast-Mode dependency graph are
> **internal/undocumented** — the documented way to create a dataset Beast Mode is the Analyzer / Beast Mode
> Editor UI, not a REST call. Treat anything tagged `[REPO]`/`[INFER]` as verify-live-first.

## Evidence tiers

Every path/shape/limit below carries a tier. Anything `[REPO]` or `[INFER]` must be re-verified against a
live instance before you depend on it.

```
[DOC]   Confirmed in Domo's official developer/API reference or the published OpenAPI
        spec (domo.com/docs, domo.com/docs/openapi/product/beastmodes.yaml). Safe to
        state as a public contract.
[KB]    Domo Knowledge Base / support / help articles (domo.com/docs/s/article/…,
        knowledge.domo.com). UI-level and behavioral guidance; authoritative for product
        behavior, not a REST contract.
[REPO]  Verified only from repo code or empirical observation against a live instance;
        absent from public docs. Present as internal/undocumented — verify live first.
[INFER] Reasoned from documented facts plus HTTP/product semantics (e.g. PUT idempotence,
        429 backoff, the `notvariable` filter effect); not stated verbatim. Flag as inference.
```

(Verified 2026-09-05 by a 19-agent research + adversarial-verify workflow cross-checking 14 repo-derived
claims against Domo public docs: **7 CONFIRMED, 3 REFUTED, 3 DOC-SILENT, 1 DOC-ADDS**. The 3 REFUTED items
are called out in the hedge list so they never get written as fact.)

## What a Beast Mode is

A Beast Mode is a Domo **calculated field** — a formula evaluated at query time. Two documented flavors, with
different reuse scope: `[DOC]` `[KB]`

- **Dataset-scoped** ("Save calculation to DataSet") — the calculation is *tied to the DataSet* and becomes
  *available to any other card that uses this DataSet*. Reusable across cards on that dataset, but not across
  datasets. `[KB]`
- **Card-level** (added in the Analyzer) — *tied to the Card*; applies only to that one card. `[KB]`

Other documented facts:

- **Variables** are a documented Beast Mode function *type* — "a value that functions inside of a Beast Mode,"
  with three data types (Number, String, Date). Created via the Beast Mode Editor UI. `[KB]`
- **Locking** restricts (does not absolutely prevent) editing: a locked calculation "can be edited or unlocked
  only by the owner, an Admin, or any users who have a role with the *Manage All Cards, Pages and Apps (App
  Studio)* and *Manage DataSets* grants." `[KB]`
- **The public object field for scope is `global`** (boolean); the statistics endpoint exposes `onDatasets` /
  `onCards` counts. The internal API layer uses a `persistedOnDataSource` boolean for the same dataset-vs-card
  distinction, but **that exact field name is not in Domo's public docs** — treat `persistedOnDataSource` as
  internal `[REPO]`; `global` is the documented one `[DOC]`.
- **`locked` IS a documented object field** (returned by get-by-id; set by the lock endpoint). `[DOC]`

**Not the same as Magic ETL Formula tiles.** Beast Mode (Analyzer/query engine) and the Magic ETL Formula tile
are *different formula engines* with different available functions — a formula that works in one may not
translate to the other. Keep them mentally separate; see [`domo-magic-etl.md`](domo-magic-etl.md). `[KB]`

## Documented endpoint surface

Domo's official Beast Modes API reference and the published OpenAPI spec (`beastmodes.yaml`) enumerate
**exactly five** operations, all under `/api/query/v1/functions/`. There is **no** create, delete, archive,
or validate endpoint — those absences are documented, not just unobserved. `[DOC]`

| Operation | Method + route | Body / params | Returns | Tier |
|---|---|---|---|---|
| Search / list | `POST /api/query/v1/functions/search` | `name`, `filters` (req.), `sort`, `limit` (req., **1–5000**), `offset` | `totalHits`, `results[]`, `hasMore`, `degraded` | `[DOC]` |
| Statistics | `GET /api/query/v1/functions/statistics` | — | aggregate counts incl. `onDatasets` / `onCards` | `[DOC]` |
| Get by id | `GET /api/query/v1/functions/template/{id}` | path `id` | full Beast Mode object (`id`, `name`, `owner`, `locked`, `global`, `expression`, `checkSum`, `dataType`, `status`, `archived`, `hidden`, `links`) | `[DOC]` |
| Update expression | `PUT /api/query/v1/functions/template/{id}` (Domo's docs render this inconsistently as `?strict=false` **or** a `/update` suffix) | `{"expression": "..."}` **only** | updated object incl. `status` (e.g. `"VALID"`) | `[DOC]` |
| Lock / unlock | `PUT /api/query/v1/functions/template/{id}` | `{"locked": true}` / `{"locked": false}` | updated object | `[DOC]` |

- **The `template/{id}` path supports only GET and PUT** — no DELETE verb exists anywhere in the spec. `[DOC]`
- The one genuine published concrete limit is `search` `limit` **1–5000**. Rate limits / HTTP 429 behavior are
  **not published** for any of these endpoints — treat retry/backoff as defensive coding, not documented. `[DOC]`/`[INFER]`
- `search` (find sets of functions) is distinct from the file-content `search`/`query` on FileSets — unrelated
  API; see [`domo-filesets.md`](domo-filesets.md) if you meant unstructured files.

## Auth

Two paths, both documented. Prefer the tokenless CE path when your code runs in Code Engine.

**1. Explicit dev token (server-to-server).** Every `/functions/` operation — including the writes (update,
lock) — authenticates with the **`X-DOMO-Developer-Token`** header; the base is `https://{instance}.domo.com`.
Domo's Beast Modes reference shows **no OAuth** for these endpoints. This is what `bm_bulk_lock.py` uses. `[DOC]`

**2. Code Engine — tokenless (preferred).** `codeengine.sendRequest(method, "/api/query/v1/functions/...")`
(Python: `codeengine.send_request(...)`) uses CE-runtime-injected auth: "we are making the request without any
credentials … Every sendRequest call is intercepted by the Code Engine service and injected with the
credentials of the authenticated user." No token is authored. `[DOC]`

- Caveat: the Code Engine doc *enumerates* DataSets, users/groups, and cards/dashboards as `sendRequest`
  targets and does **not** explicitly name the `/functions/` (Beast Mode) endpoint — so reaching Beast Modes
  this way is **documented-by-mechanism**, not spelled out for this exact path. Verify on your instance. `[DOC]`/`[INFER]`
- The general "prefer CE tokenless; fall back to a token only when the CE client can't do the job" rule lives
  in [`domo-code-engine.md`](domo-code-engine.md). Token source in CE = account-property keys read at runtime
  (never inline a token into a committed file).
- **"No SID / no session token" is the repo's chosen path, not a documented exclusivity.** OAuth Bearer is
  documented only for the public `api.domo.com` DataSet query API (not Beast Modes); a session token
  (`x-domo-authentication`) is a documented internal variant on some `/api/query/v1` endpoints. `[DOC]`

## `search` — list/find Beast Modes

`POST /api/query/v1/functions/search`. Paginated. `[DOC]`

Request body:

| Field | Req? | Meaning |
|---|---|---|
| `name` | optional | search by name (substring) |
| `filters` | **required** | array of `{field}` objects; the docs' own example is `[{"field": "notvariable"}]` |
| `sort` | required | `{field, ascending}` |
| `limit` | required | integer, **must be between 1 and 5000** |
| `offset` | optional | start record for paging |

Response: `totalHits`, `results[]` (Beast Mode objects), `hasMore` (boolean), `degraded` (boolean).

- **Paginate on `hasMore`**: loop, advancing `offset` by the batch size, until `hasMore` is false or a batch
  comes back empty. `bm_bulk_lock.py` is the working pattern. `[REPO]`
- **`notvariable` filter effect is inferred.** The value appears in Domo's example, but the docs do not state
  that it "excludes variable-type functions" — that reading is reasonable (objects carry a `variable` field)
  but is `[INFER]`, not documented. `[INFER]`

## `lock` / `unlock` — restrict editing

`PUT /api/query/v1/functions/template/{id}` with body `{"locked": true}` to lock, `{"locked": false}` to
unlock; returns the updated Beast Mode object. Documented on the dedicated "Lock Beast Mode" reference
page. `[DOC]`

```python
# Repo pattern (bm_bulk_lock.py): dev-token PUT; lock is idempotent (setting the same value is a no-op).
url = f"https://{instance}.domo.com/api/query/v1/functions/template/{beastmode_id}"
requests.put(url, headers={"X-DOMO-Developer-Token": token, "Content-Type": "application/json"},
             data=json.dumps({"locked": True}))   # False to unlock
```

- **Idempotent in practice** — repeating the same `locked` value yields the same state (follows from PUT
  semantics); "idempotent" is not a documented term. `[INFER]`
- Bulk locking many Beast Modes = `search` (paginate) → filter `locked` → PUT each. Parallelize with care:
  429/rate limits are **not documented**, so a modest worker count + backoff is defensive, not a stated
  requirement. `[REPO]`/`[INFER]`

## `update` — edit the formula ONLY

`PUT /api/query/v1/functions/template/{id}` with body **`{"expression": "..."}`** updates the formula and
validates it on save (response carries a `status`, e.g. `"VALID"`; accepts `?strict=false`). `[DOC]`

> **REFUTED — you CANNOT edit a Beast Mode's `name` or `dataSourceId` through this endpoint.** Domo's docs
> state the update body accepts **only** `expression`. Do not write "the same PUT can also rename / re-point
> a Beast Mode" — the docs explicitly exclude `name` and `dataSourceId`. `[DOC]`

- **The exact update verb/path is doc-inconsistent** (`?strict=false` vs a `/update` suffix across Domo's own
  pages), so update is *not* cleanly "the same bare PUT" as lock — pin the working spelling per instance. `[DOC]`
- **There is no separate validate/preview/compile/test endpoint** (REFUTED — see hedge list). The most direct
  API validation signal is this update call's response `status` (it still persists; it is not a
  non-destructive preview). Analyzer validates syntax at "Save Calculated Field." `[DOC]`

## `get` one Beast Mode by id

`GET /api/query/v1/functions/template/{id}` reads one Beast Mode by id and returns the full object (`id`,
`name`, `owner`, `locked`, `global`, `expression`, `checkSum`, `dataType`, `status`, `archived`, `hidden`,
`links`). Documented as "Get Beast Mode by ID"; auth = `X-DOMO-Developer-Token`. `[DOC]`

- **The repo never calls GET on this path** — `bm_bulk_lock.py` only issues PUT (lock) — but the read endpoint
  is real and documented; use it when you need one function's current `expression`/`locked`/`links` without a
  full `search`. `[DOC]`

## Consuming Beast Modes in a Pro Code app

A Pro Code app's data read can honor dataset Beast Modes by adding **`useBeastMode=true`** to the App
Framework Data API query. Repo example — `sales-os-portal/pro-code/app.js`:
`GET /data/v1/{alias}?useBeastMode=true&fields={beastModeAlias}`. `[DOC]` `[REPO]`

Documented caveats you must respect:

- **Reference by manifest alias, not by dataset Beast-Mode name.** The `beastModeAlias` is the alias mapped in
  the app **manifest**, requested through `fields=` — not the Beast Mode's display name. `[DOC]`
- **`useBeastMode=true` disables some built-in query functionality**, and **you must explicitly provide an
  aggregation whenever you use a `groupby` operator** while Beast Mode is enabled. `[DOC]`

## Where-used / lineage

**There is no server API that returns a Beast-Mode→Beast-Mode dependency graph.** The five documented
operations include no where-used/lineage/dependency endpoint. To trace which Beast Modes reference which
others (nested calculations), the only route is a **client-side walk** — parse the `DOMO_BEAST_MODE(id)`
tokens out of each `expression` string yourself. `[DOC]` (absence) / `[REPO]` (the walk)

Two things the docs DO add (DOC-ADDS) that a "purely client-side" framing misses:

- **The get-by-id response includes a `links` field** associating a Beast Mode with **cards / data sources** —
  a server-provided *partial* where-used at the card/dataset level (not BM→BM). `[DOC]`
- **Beast Mode Manager's Details → Cards tab** surfaces the same where-used in the UI (count of cards using it,
  the DataSets and Cards where it is found). `[KB]`
- Caveat: the **`DOMO_BEAST_MODE(id)` token form itself is undocumented** — the editor references nested calcs
  by *name*; the id-token form is `[REPO]`. Re-verify before relying on the regex. `[REPO]`

## Internal / undocumented endpoints (do not treat as a public contract)

These shapes match the documented `/functions/*` family, but Domo publishes **no** documentation for them.
They came back **DOC-SILENT** in the cross-check — the docs neither confirm nor refute them. Present each as
*internal/undocumented, observed only empirically against a live instance* — never as a supported API. `[REPO]`

| Would-be operation | Observed shape | Status |
|---|---|---|
| Create a function/template | `POST /api/query/v1/functions/template` (calculated field; or a **variable** when the body sets `variable:true` + an embedded control); response carries `templateId` / `function.id` | **Undocumented.** No public create endpoint exists. `[REPO]` |
| Create + attach to a dataset | `POST /api/query/v1/functions/template?strict=false` to mint a dataset-level Beast Mode so it appears in `datasources/{id}/schema/indexed` | **Undocumented; observed to FAIL to attach** (returned `templateId:null`). `[REPO]` |
| Variable-name uniqueness check | `GET /api/query/v1/functions/variables/uniqueName?name=<n>` before creating a variable | **Undocumented** (zero doc footprint anywhere). `[REPO]` |

- **The documented way to create a dataset-scoped ("Save calculation to DataSet") Beast Mode is the Analyzer /
  Beast Mode Editor UI, not a REST call.** The only documented *programmatic* touchpoints are
  search / statistics / get / update / lock of **already-existing** Beast Modes, plus query-time
  `useBeastMode` / `beastModeAlias` in the App Framework Data API. `[DOC]`
- If you must automate creation, capture the Beast Mode UI's own network calls against your target instance
  and treat whatever you find as private/undocumented — do not hardcode it into a distributed tool as if it
  were stable.

## Do NOT claim as documented fact (hedge list)

Mark these as *refuted*, *demoted*, or *repo-observed against a private API* — never as a public contract:

1. **Editing a Beast Mode's `name` or `dataSourceId`** via the update endpoint — **REFUTED.** The update body
   accepts `expression` only. Drop name/dataSourceId edits entirely.
2. **A DELETE / archive endpoint** (`DELETE /functions/template/{id}` or similar) — **REFUTED.** The spec has
   no DELETE verb; `template/{id}` is GET+PUT only. `archived` is a field, but archiving is a UI-only action.
3. **A dedicated validate / preview / compile / test endpoint** — **REFUTED.** Docs state none exists;
   validation is coupled to the update `status`.
4. **A public create / create-and-attach endpoint** and a **`variable:true` create body / embedded controls /
   `templateId` response** — DOC-SILENT / internal; observed create/attach failing (`templateId:null`).
5. **`functions/variables/uniqueName`** — internal; zero doc footprint.
6. **A BM→BM lineage/dependency API** and the **`DOMO_BEAST_MODE(id)` token form** — no graph API;
   token form undocumented (only card/datasource `links` are server-provided).
7. **The `persistedOnDataSource` field** — internal; the public field is `global` (+ `onDatasets`/`onCards`).
8. **The `notvariable` filter's "excludes variables" effect** — inferred; the value is shown but its effect
   is not stated.
9. **Rate limits / HTTP 429 on bulk template PUTs** — undocumented; retry/backoff is general defensive coding,
   not a Domo-documented behavior. (The `search` `limit` 1–5000 IS documented.)
10. **"No SID / no session token"** as an API rule — that's the repo's chosen auth path;
    `x-domo-authentication` is a documented internal variant, so exclusivity is not doc-stated.

## Safety / hygiene

- **Locking is not deletion, but it is a governance change.** A bulk lock/unlock over a `name`-substring
  filter can sweep far more Beast Modes than intended — run with a dry-run/count first (as `bm_bulk_lock.py`
  supports) and confirm the target count before issuing PUTs.
- **Never author a dev token into a committed file or into browser JS.** `bm_bulk_lock.py` reads the token
  from an environment variable (`DOMO_DEV_TOKEN`) and ships with it blank — keep it that way. In CE, read the
  token from account properties at runtime; prefer the tokenless `sendRequest` path.
- **On the shared validation instance (`maintenance-instance`)**, only lock/update/create Beast Modes **you** created
  and clearly named — never mutate a Beast Mode you did not create, and never bulk-lock someone else's fields.
- **Undocumented/BETA-adjacent surface = defensive coding.** Wrap create/variable/lineage calls so a
  shape change degrades gracefully, and log the route you actually hit so a break is diagnosable.

## Repo precedent

Working Beast Mode usage already lives in the repo — read these before writing new code (line numbers drift,
so grep the token, not the line): `[REPO]`

| Project | What it demonstrates |
|---|---|
| `beast-mode-manager/bm_bulk_lock.py` | The primary reference: dev-token `POST /functions/search` with `filters:[{field:"notvariable"}]` + `hasMore` pagination, then parallel `PUT /functions/template/{id}` `{"locked":…}` lock/unlock, with dry-run and `only_unlocked` filtering |
| `sales-os-portal/pro-code/app.js` | Consumption side: an App Framework Data API read with `useBeastMode=true&fields={beastModeAlias}` |

Companion skills: [`domo-code-engine.md`](domo-code-engine.md) (CE tokenless auth + mechanics),
[`domo-cards.md`](domo-cards.md) (standard cards that carry Beast Modes),
[`domo-magic-etl.md`](domo-magic-etl.md) (the separate Formula-tile engine).
