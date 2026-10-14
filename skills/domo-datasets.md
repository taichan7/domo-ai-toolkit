# Domo DataSets API Skill

Use this when a task **reads, queries, imports, deletes, or governs tabular DataSets** in Domo — from a
Pro Code app, Code Engine, Jupyter, or a server-to-server script. It covers the two read paths (in-app
proxy vs server SQL), the two import mechanisms (Stream API vs v3 uploads), the lifecycle/delete
endpoints, PDP row-policies, and — the part that trips everyone — **which host + auth pairing each
endpoint actually wants**. For *unstructured* files (documents/images) use
[`domo-filesets.md`](domo-filesets.md); for reshaping datasets on a schedule use
[`domo-magic-etl.md`](domo-magic-etl.md); for Code Engine auth mechanics see
[`domo-code-engine.md`](domo-code-engine.md).

## Evidence tiers

Every load-bearing line below carries a tier. Anything `[REPO]` or `[INFER]` must be re-verified live
before you depend on it.

```
[DOC]   Official Domo docs — the docs portal (domo.com/docs/portal),
        the developer API reference, or the machine-readable OpenAPI YAML.
[KB]    Domo Knowledge Base / support articles. Product behavior, limits, UI facts.
[REPO]  Verified only against this repo's working usage on a live instance
        (maintenance-instance) — NOT in public docs. Internal/undocumented; re-verify per instance.
[INFER] Reasoned from the documented model or Domo-adjacent (community) sources —
        plausible, not first-party documented.
```

(Verified 2026-09-05 by a 22-agent doc-cross-check + adversarial-verify workflow against Domo public
docs, OpenAPI specs, and this repo: **11 claims, each independently re-verified**. The single failure
mode this skill guards against is **over-claiming** — presenting a single-instance observation, or a
behavior documented for *one* endpoint, as a documented portable contract. Where the first pass and the
refute pass disagreed on tier, the more conservative tier is used below and the split is called out.)

(2026-09-06 — a 7-agent re-fetch + adversarial-refute workflow folded in **13 further `[DOC]` facts**
transcribed from the `platform/dataset.yaml` (55410 B) and `platform/stream.yaml` (31488 B) OpenAPI
bodies: the DataSet **create / update-details / CSV-export** ops, the **Stream read/manage half** +
`PATCH`-update + delete + upsert key, the List `sort`/`nameLike` grammar, the PDP `<255`-char values
limit and retrieve-one op, per-op 2xx codes, and the column-type list. **3 candidate folds were dropped
as over-claims** — a mislabeled 403 error envelope, a `dataCurrentAt`-in-responses claim, and one
already-present attach-limitation — and **5 planted negative controls were all rejected**, so the
additions below are spec-positive, not inferred.)

(2026-09-06 — an 8-agent re-fetch + adversarial-refute workflow re-examined the two error folds dropped
above and landed the **corrected** core (`## Error responses & response-shape gotchas`): the 403 `{status,
toe}` machine contract with `toe`="Thread of Execution", the 401 `WWW-Authenticate`-header-only shape, the
400 example-only-fields caveat, and `dataCurrentAt` as attribute-table-only. The over-claiming half of the
original 403 fold was dropped a second time — its own adjudication caught a residual over-claim (the 400
"four-field schema"), confirming those fields are `example:`-only, and **both planted negative controls
were rejected**.)

(2026-09-07 — a 5-agent adversarial-refute workflow field-mined the **WAF-lifted dev-portal
`API-Reference/Domo-APIs/DataSet-API.yaml`** render (HTTP 200; a spec **distinct** from the already-folded
`platform/dataset.yaml` above) and landed **2 `[DOC]` deltas**: the OAuth query endpoint (B)'s per-column
`metadata[]` shape `{type, dataSourceId, maxLength, minLength, periodIndex}` — correcting a prior "`{type}`-only"
cross-reference — and the PDP-create precondition that referenced users/groups must pre-exist. **2 further
net-new facts were held back as TRIVIA** (a `groups` response-type doc-artifact; an RFC-4180 CSV citation) and a
planted 2-part **negative control [a phantom `queryUuid` response field + a fabricated `MERGE` `updateMethod`
value] was refuted by all 4 lenses**. No example values reproduced.)

## Two worlds: match the host to the auth (the #1 mistake)

Almost every DataSet mistake is a **host/auth mismatch**. Domo has two distinct DataSet API families
with **separate, non-interchangeable credential systems** `[DOC]`:

| | **Platform API** (public/partner) | **Product API** (instance/internal) |
|---|---|---|
| **Host** | `https://api.domo.com` | `https://{instance}.domo.com/api/...` |
| **Auth** | OAuth 2.0 Bearer (client-credentials) | `X-DOMO-Developer-Token: <token>` or session SID |
| **Paths** | `/v1/datasets/...`, `/v1/streams/...` | `/api/data/v3/...`, `/api/query/v1/...`, `/api/data/v1/streams/...` |
| **Docs** | Stable, mostly `[DOC]` | Mirrors the UI; **partly documented, partly `[REPO]`** |

- **Get an OAuth token** (`data` scope) `[DOC]`: `POST https://api.domo.com/oauth/token?grant_type=client_credentials&scope=data`
  with `client_id:client_secret` sent as **HTTP Basic** auth (Base64), then send `Authorization: bearer <access_token>`
  on the dataset calls. Tokens expire in ~3600s. Other scopes: user, workflow, audit, buzz, account, dashboard.
- **A developer token / SID is NOT valid OAuth** — calling `api.domo.com/v1/datasets` with a dev-token/SID
  fails to authenticate (**observed as HTTP 401** in this repo `[REPO]`; the exact 401 code is not stated
  verbatim in docs). Conversely the **same developer token IS the correct credential** for the instance-side
  Product endpoints (`{instance}.domo.com/api/data/v3/...`, `/api/query/v1/execute/{id}`). Scope the rejection
  to `api.domo.com` specifically or it misleads.
- The word "SID" is a Domo-CLI/instance mechanism, not a documented `api.domo.com` concept `[REPO]`.

> **Rule of thumb:** `api.domo.com` ⇒ Bearer. `{instance}.domo.com/api/...` ⇒ dev-token/SID. In-app
> (Pro Code browser) ⇒ no auth header at all (the proxy injects the session). Never mix a path prefix
> with the wrong host or the wrong header.

## Reading data #1 — in-app proxy (Pro Code / Custom App) `[DOC]`

Inside a Pro Code / Custom App, read a mapped dataset through the **ryuu.js / domo.js proxy** — plain
same-origin calls, **no auth header**; the running card's Domo session is injected automatically.

```js
// Rows (default: array-of-objects). Query operators go on the query string.
domo.get('/data/v1/sales')
domo.get('/data/v1/sales?fields=amount&sum=amount')          // aggregate server-side
// SQL — body is a RAW string; FROM uses the manifest ALIAS, not the UUID.
domo.post('/sql/v1/sales', 'SELECT SUM(amount) FROM sales', { contentType: 'text/plain' })
```

- **`{alias}` comes from the manifest**, not from code. The current App Framework key is
  **`datasetsMapping`**; older developer.domo.com / Bricks docs call the same array **`mapping`** — both are
  official, identical shape `{ alias, dataSetId (UUID), fields }` (`fields` empty = all columns). The
  alias→UUID binding lives only in the manifest; app code never references the UUID for these two endpoints.
  Match the key name the target platform's tooling expects or the alias won't resolve. `[DOC]`
- **`GET /data/v1/{alias}` query operators** `[DOC]`: `fields, filter, groupby, orderby, limit, offset, sum,
  avg, count, min, max, unique, dategrain, calendar` (the `calendar` op also governs `todate`/`last`).
  Semantics the name-list alone doesn't convey `[DOC]`:
  - `groupby` and `dategrain` default to **numeric columns summed / non-numeric columns unique-counted**;
    combine an explicit aggregation (`sum`/`avg`/…) to override that default.
  - `dategrain` performs a group-by on a predefined date grain and **adds** a column: week/month/quarter →
    `CalendarXXXX` (e.g. `CalendarMonth`), day → `Date`, year → `Year`. A pre-existing same-named column is
    overridden, and the original grained column is dropped under its original name.
  - `orderby` **cannot order on an aggregation** (defaults ascending; comma-delimit for multi-column).
  - `fields` accepts either the manifest **alias** or the **original column name** (when no alias was defined).
- **Output format** `[DOC]`: from **domo.js**, a 2nd-arg options object
  `{ format: 'array-of-objects' | 'array-of-arrays' | 'csv' | 'excel' }` (client-lib sugar; default is
  `array-of-objects`). Beneath it, the raw-HTTP contract is **`Accept`-header content negotiation** on the GET:
  `application/json` → the detailed envelope below (rows as arrays-of-arrays); `array-of-objects` → an array of
  row objects; `text/csv` → CSV text; `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` → an
  XLSX binary. Direct (non-domo.js) callers set `Accept`; the `{format}` sugar maps onto these.
- **The SQL API has hard limits** `[DOC]`: **no JOINs, no trigonometric functions, and page filters are not
  applied.** Multi-dataset joins are impossible here — reshape upstream in Magic ETL instead.
- **Alias-endpoint response envelope** `[DOC]`: both `GET /data/v1/{alias}` and `POST /sql/v1/{alias}` return
  the same **detailed JSON** shape on 200 (the SQL API's 200 is explicitly the "Detailed JSON" format):
  `{columns:[…], datasource, device, duration, fromcache, metadata:[{dataSourceId, type}], numColumns, numRows,
  queryUrl, rows:[[…]]}`. This retires the older `[REPO]` hedge — the previously repo-observed
  `{columns, numColumns, numRows, rows}` is a strict subset of this now-documented shape. **Scope guard:** this
  is the *alias* (in-app proxy) envelope; it is **not** the same shape as the OAuth public endpoint (B) below,
  which carries a **richer** per-column `metadata:[{type, dataSourceId, maxLength, minLength, periodIndex}]` object
  (`[DOC]`, see (B) below) but **no** `device`/`duration`/`queryUrl`. Do not migrate *those three* fields onto B.
- **Error body** `[DOC]`: both alias endpoints return `{message: <string>}` on `400` (bad request / invalid query
  params or SQL syntax), `401` (unauthorized), `404` (alias not found). Documented statuses are **only**
  `200/400/401/404` — no `500`/`stackTrace` shape. (Distinct from the DataSet import-PUT error block later in this
  file, which is a different spec with `400/401/403`.)
- One doc typo: the developer.domo.com guide's prose mislabels the SQL example as "POST /data/v1/sales",
  but the code correctly uses `/sql/v1/sales` — trust the code. In Bricks (DDX) the alias is `dataset0` /
  `window.datasets[0]`; in a named Pro Code manifest it's whatever you named it.

## Reading data #2 — server-side SQL (two documented endpoints — do NOT conflate)

There are **two** officially-documented ways to run SQL against one dataset server-side. They differ in
host, auth, the FROM-name the docs show, and the response shape. Getting these crossed is the classic
over-claim trap.

**(A) Instance endpoint — dev-token/SID auth** `[DOC]` skeleton:

```
POST https://{instance}.domo.com/api/query/v1/execute/{datasetId}
X-DOMO-Developer-Token: <token>          # SID (X-Domo-Authentication) also works [REPO]
Content-Type: application/json
{"sql": "SELECT ... FROM table WHERE ..."}
```

- The dataset comes from the **path** `{datasetId}`; the FROM-name is just a placeholder. The official
  example writes **`your_table`** (`SELECT * FROM your_table WHERE column = 'value'`), and the docs describe
  the response as **"a list of objects"** (array of row objects). `[DOC]`
- That **`FROM table`** (the literal word `table`) also resolves here, and that this endpoint returns the
  **column-oriented `{columns, rows, metadata, numRows, numColumns}` envelope** in practice, are **`[REPO]`**
  observations for *this* endpoint — the instance docs show `your_table` + a list-of-objects response. SID
  auth working here is also `[REPO]`.

**(B) Public developer endpoint — OAuth Bearer auth** `[DOC]` (full behavior, including the envelope):

```
POST https://api.domo.com/v1/datasets/query/execute/{datasetId}
Authorization: bearer <oauth-token>
{"sql": "SELECT * FROM table"}           # literal `table` is DOCUMENTED here
```

- Documented 200 response **IS** the columns/rows envelope:
  `{datasource, columns:[string], metadata:[{type, dataSourceId, maxLength, minLength, periodIndex}], rows:[[…]], numRows, numColumns, fromcache}`. `[DOC]` — each `metadata[]` item is a **per-column descriptor** (`type`/`dataSourceId` strings; integer `maxLength`/`minLength`/`periodIndex`), a **superset** of the alias endpoint's 2-field `{dataSourceId, type}` metadata — endpoint (B) is **not** `{type}`-only.

> **Net / over-claim guard:** the literal `FROM table` **and** the columns/rows envelope are `[DOC]` **only
> for the OAuth public endpoint (B)**. On the dev-token/SID instance endpoint (A) they are `[REPO]`, and the
> instance docs actually show `your_table` + a list-of-objects response. Never tag "the dev-token instance
> endpoint returns a columns/rows envelope using `FROM table`" as `[DOC]`.

- `LIMIT 0` for schema-only discovery and backtick-escaping of spaced column names are `[REPO]`/`[INFER]`
  conventions, not stated in docs.

## Lifecycle — create / get / list / update / export / delete (again, two APIs)

**[DOC] Public DataSet API** (`api.domo.com`, OAuth Bearer) — the documented, supported contract. The
create / update / delete rows **mutate data** and are **EXECUTION-gated** (document them; never auto-invoke
from the cycle — see Safety):

| Operation | Call | Notes | Tier |
|---|---|---|---|
| Create | `POST https://api.domo.com/v1/datasets` | Body **required** `{name, schema}`; `schema.required:[columns]`, each column `{type, name}` (both required). Returns **201** (a DataSet object). **EXECUTION-gated.** | `[DOC]` |
| Create (from name) | `POST https://api.domo.com/v1/json` | **Simple API** — creates an empty DataSet from a **name** alone, **no schema** (schema is inferred later, on first JSON import). `name` **required** + `description` optional, documented **both** as query params **and** as a `{name, description}` JSON body (which takes precedence is unspecified — `[INFER]`). Returns **201** with the full DataSet object (`id`, `name`, `description`, `rows`, `columns`, `owner{id,name}`, `createdAt`, `updatedAt`, `pdpEnabled`, `policies[]`; `id`/timestamps are plain `string` in-schema — uuid/ISO shapes are example-only). A **distinct** create mechanism from the schema-based `POST /v1/datasets` above, not a replacement or the canonical one. **EXECUTION-gated.** See § *JSON-native load* for the paired import path. | `[DOC]` |
| Retrieve details | `GET https://api.domo.com/v1/datasets/{id}` | A deleted id returns a **subset with `deleted:true`** | `[DOC]` |
| List | `GET https://api.domo.com/v1/datasets` | `limit` **default 50 and MAXIMUM 50** (>50 rejected); paginate with `offset`. Also `sort` (`DataSourceListOrderBy`, below) + `nameLike` (case-insensitive substring). | `[DOC]` |
| Update details | `PUT https://api.domo.com/v1/datasets/{id}` | Body `name`/`description`/`pdpEnabled`/`schema.columns[{name,type}]` — **all optional, no `required` block**; returns **200**. This **platform** PUT *does* accept a **name change**. **EXECUTION-gated.** | `[DOC]` |
| Export data | `GET https://api.domo.com/v1/datasets/{id}/data` | Raw **`text/csv`** (CSV is the only documented export type); query `includeHeader` (bool, default `false`) + `fileName` (string); **200**. Read-only. | `[DOC]` |
| Delete | `DELETE https://api.domo.com/v1/datasets/{id}` | "Destructive and cannot be reversed"; works for **all** datasets, not just API-created ones. Returns **204** (empty). **EXECUTION-gated.** | `[DOC]` |

- **`sort` values** (`DataSourceListOrderBy`, a 15-value enum) `[DOC]`: `name`, `nameDescending`, `lastTouched`,
  `lastTouchedAscending`, `lastUpdated`, `lastUpdatedAscending`, `createdAt`, `createdAtAscending`, `cardCount`,
  `cardCountAscending`, `cardViewCount`, `cardViewCountAscending`, `errorState`, `errorStateDescending`,
  `dataSourceId`. `sort`/`nameLike` are additive to the List op and do **not** relax the 50-cap above.
- **Column `type` values** `[DOC]`: `STRING`, `DECIMAL`, `LONG`, `DOUBLE`, `DATE`, `DATETIME`. ⚠ This set is
  stated in **prose** (the Attributes description + the create/update body `type` descriptions), **not** as an
  OpenAPI schema `enum` — the only two real `enum`s in the DataSet spec are `DataSourceListOrderBy` and the
  Stream `updateMethod` (REPLACE/APPEND). Treat it as the documented set, not a machine-enforced closed enum.
- **Per-op success codes (don't guess)** `[DOC]`: create-dataset **201**, update-details **200**, delete **204**
  (PDP create **201** / update **200** / delete **204**, below; Stream create & delete both **200**, below). A
  create-stream **200** still creates the resource (it returns the DataSet object) — do **not** read
  "200-not-201" as "nothing was created".
- ⚠ **Export vs SQL-export**: this platform `GET /v1/datasets/{id}/data` (CSV, OAuth, `api.domo.com`) is a
  **different endpoint** from the instance SQL-based export in [`domo-query-dataset.md`](domo-query-dataset.md)
  (`/api/query/v1/execute/export/...`, dev-token) — both name `includeHeader`, but differ in host / auth / path.
- ⚠ The platform **PUT `/v1/datasets/{id}`** (name change accepted) is a **different endpoint** from the
  instance **PUT `/api/data/v3/datasources/{id}`**, which returns **405 — rename unsupported** (`[REPO]`, below).
  Additive, not a contradiction: match the host to the operation.

**[REPO] Instance API** (`{instance}.domo.com`, SID / dev-token) — what this repo actually uses; **NOT in
Domo public docs, verify live**:

| Operation | Call | Observed behavior | Tier |
|---|---|---|---|
| Get metadata | `GET /api/data/v3/datasources/{id}` | `?part=core,permission,status,pdp,rowcolcount,certification,functions` | `[REPO]` |
| List | `GET /api/data/v3/datasources?limit=50&offset=0` | Same **50 cap** (>50 → 400) | `[REPO]` |
| Delete | `DELETE /api/data/v3/datasources/{id}` | **200** on datasets confirmed `cardCount:0`; **404** on nonexistent id; **403** Access Denied on an orphaned dataset (no longer a live dataflow output). **A 403 alone is NOT proof of deletion.** | `[REPO]` |
| Rename | `PUT /api/data/v3/datasources/{id}` | **405 — rename unsupported** | `[REPO]` |

- **Delete requires** DataSet owner OR Admin / "Manage DataSets" privilege; deletion is permanent `[KB]`.
- **Gate destructive deletes** on a `cardCount:0` (or dependency) check first — the instance DELETE is real
  and exercised in this repo, but is `[REPO]`, never `[DOC]`.
- Do not conflate with `/api/query/v1/datasources/{id}/partition/...` (that's partition management).
- **Schema read**: the documented path is `GET /api/query/v1/datasources/{id}/schema/indexed?includeHidden=false`
  (returns columns/types/metadata) `[DOC]`. **The bare `GET /api/query/v1/datasources/{id}/schema` returns
  403 for FEDERATED datasets** even with a valid token `[REPO]` (doubly attested in-repo) — the fallback that
  works on federated sources is **`GET /api/data/v3/datasources/{id}/schema`**. Scope the wording narrowly:
  federated datasets *do* expose their schema (the KB says a federated DataSet "displays row counts and the
  schema"; the v3 endpoint returns it) — only that **one** `query/v1` bare-schema path 403s. Treat any non-200
  on the `query/v1` path as "read schema via the v3 endpoint instead"; the exact status code may vary by
  instance/permissions.
- **Schema read (4th path)**: a first-party OpenAPI spec documents `GET /api/data/v2/datasources/{id}/schemas/latest`
  — distinct from the three paths above (note the `v2` root vs `v1`/`v3`, the plural `schemas`, and the `/latest`
  suffix). It returns a `{schema:{columns:[…]}}` envelope where each column carries `type`/`name`/`id`/`visible`
  plus a `metadata` object (`colLabel`/`colFormat`/`isEncrypted`); only `200`/`401`/`404` are documented, and it
  takes **no query params (no `includeHidden` analog) and no request body** `[DOC]` (rendered content mirror only
  — NOT byte-verified; the spec has no `enum` on `type`, no `required` arrays, and no `additionalProperties:false`,
  so treat `type` as an open string and the field set as non-exhaustive). Its backend relationship to the charted
  `query/v1 .../schema/indexed` and `data/v3 .../schema` paths is unverified — zero repo callers, no behavior
  comparison — so do **not** treat it as an alias or normalize `v2`→`v3`, and its federated behavior is untested
  (a `≥403` by sibling precedent is only inferred) `[INFER]`.

## Importing data — four documented mechanisms

Pick by size and by which world you're in.

### Small one-off load — `updateMethod` on the data endpoint `[DOC]`

```
PUT https://api.domo.com/v1/datasets/{datasetId}/data?updateMethod=REPLACE|APPEND
Authorization: Bearer <token>
Content-Type: text/csv
```

- Exactly **two documented values**, default **`REPLACE`** `[DOC]`:
  - **`REPLACE`** — removes ALL existing rows and replaces them with the incoming batch (schema must match).
  - **`APPEND`** — adds incoming rows to the bottom, "with no consideration for whether data has been
    updated" (no dedup/merge; duplicates possible).
- **Case-sensitive, must be UPPERCASE**; an **invalid value silently falls back to `REPLACE`**. CSV only; the
  CSV schema must match the DataSet schema **even for REPLACE**; success = **HTTP 204** (empty body). `[DOC]`
- Domo's KB defines Merge/Upsert and Partition as additional product-level accumulation methods, but this
  REST param accepts **only** REPLACE/APPEND — Merge/Partition are connector/pipeline features, not values here.
- `updateMethod` **also appears as a body field** (REPLACE/APPEND) when creating a Stream (below) — don't
  conflate the query param with the Stream body field.
- Community-reported gotcha (NOT documented, `[REPO]`): `?updateMethod=APPEND` sometimes still replaces when
  columns/schema mismatch — verify APPEND live before relying on it in production.

### JSON-native load — Simple API `[DOC]`

The **fourth** documented ingestion path — the only one that accepts **JSON directly** (Domo converts the
array to CSV server-side before storing). Source: `platform/simple.yaml` (Simple API, `api.domo.com`, OAuth
Bearer). Pairs with `POST /v1/json` (§ *Lifecycle → Create (from name)*).

```
PUT https://api.domo.com/v1/json/{DATASET_ID}/data?updateMethod=REPLACE|APPEND
Authorization: Bearer <token>
Content-Type: application/json

[ { … }, { … } ]        ← an ARRAY of flat JSON objects (min 1 item)
```

- **Body = an array of JSON objects**, each `additionalProperties:true` (arbitrary keys). Domo **converts the
  array to CSV** and stores it; success = **HTTP 204** (empty body). To pass CSV directly, use the DataSet-API
  `PUT /v1/datasets/{id}/data` above instead.
- **`updateMethod`** here is the **same** REPLACE (default) / APPEND **query param** contract charted for the CSV
  data endpoint above (§ *Small one-off load* — uppercase-only, invalid value falls back to REPLACE): **cross-
  ref, not re-specified.** Only its application to this JSON path is net-new.
- **Row/shape behaviors documented for THIS endpoint** `[DOC]` (do **not** assume they equal the CSV endpoint's
  rules — this is the Simple-API requestBody's own prose):
  - **Array / nested values render as the literal string `"List"`** in the resulting DataSet — flatten them to
    scalar properties first, or use a JSON connector, if you need the elements as columns.
  - On **REPLACE**, objects **MAY omit properties** that other objects have → those cells land **empty**. This
    *contrasts* the CSV data endpoint above, whose schema must match **even for REPLACE**.
  - On **APPEND**, the **schema must match** the existing schema; to omit a field, send its key with an empty
    string `""` or `null` — don't drop the key.
- **Errors:** the **same** three-status block (**400** `text/plain` / **401** `WWW-Authenticate`-header-only /
  **403** `{status, toe}`) charted under § *Error responses* below applies to this path too — see that section,
  don't re-derive it. **As listed, not exhaustive**: a live 404 / 409 / 429 / 5xx is `[INFER]`.

### Large / partitioned load — Stream API v1 `[DOC]`

Four-step mechanism: **create a stream → open an execution → upload parts → commit** (Domo aggregates parts
server-side). Documented on **two surfaces** — pick one and match its auth:

**(A) Public server-to-server** — `https://api.domo.com`, OAuth Bearer (`data` scope):
1. `POST /v1/streams` — body `{"dataSet":{"name","description","schema":{"columns":[{"type","name"}]}}, "updateMethod":"REPLACE"|"APPEND"}`. Returns **200** (a DataSet object). For an **Upsert** dataset add **`keyColumnNames`** (array of column names — a create-body field *sibling* to `updateMethod`) and set `updateMethod:"APPEND"`; Stream Upsert is `APPEND` **+** `keyColumnNames`, **not** a third `updateMethod` value.
2. `POST /v1/streams/{streamId}/executions` — open an execution
3. `PUT /v1/streams/{streamId}/executions/{executionId}/part/{partNum}` — upload each CSV part (gzip-compressible, parts uploadable in parallel)
4. `PUT /v1/streams/{streamId}/executions/{executionId}/commit` — commit (`.../abort` to cancel)

**(B) Instance surface** — `{instance}.domo.com/api/data/v1/streams`, `X-DOMO-Developer-Token`. **Not an
identical mirror**: the instance `POST /api/data/v1/streams` is documented for **CONNECTOR** streams
(transport/configuration/dataProvider body), distinct from surface A's dataSet+schema body. Execute via
`POST .../executions {"action":"MANUAL"}`; `GET .../history/aggregate`. ⚠ **Field name DISPUTED (re-verify
live before relying on it):** the dedicated Connectors API spec `product/connectors.yaml` (re-fetched
2026-09-07, HTTP 200) declares this *same* endpoint's body as **`{"runType":"MANUAL"}`** — property
`runType`, `required`, enum `[MANUAL]`, with `action` **absent** — for the identical
`POST /api/data/v1/streams/{id}/executions`. Two `[DOC]` sources thus conflict on the field name; a single
live connector-run is the authoritative tie-breaker (surfaced rank-46, still unresolved). The instance surface's raw-CSV
equivalent of part/commit is the **separate v3 uploads flow** (below), not v1 stream parts.

- Documented limit: a stream execution can be committed **at most ~once per 15 minutes** `[DOC]`.
- A stream **attaches to a NEW dataset** — streams can't be attached to a dataset created by the DataSet API. `[DOC]`

**Read & manage a stream** (public `api.domo.com`, OAuth Bearer) — the read/manage half the four-step
create flow omits `[DOC]`:

| Operation | Call | Notes | Tier |
|---|---|---|---|
| Retrieve | `GET /v1/streams/{id}` | `?fields=all` or a subset. If the underlying DataSet was **deleted**, returns a subset with **`deleted:true`**. | `[DOC]` |
| List | `GET /v1/streams` | `limit` default 50 **MAX 500** (⚠ NOT the DataSet-List 50-cap), `offset`; each entry's `dataSet` is a **subset `{id, pdpEnabled}`**. | `[DOC]` |
| Search | `GET /v1/streams/search?q=...` | `q` **required**; qualifiers `dataSource.id` or `dataSource.owner.id` (e.g. `q=dataSource.id:<uuid>`). No `dataSource.name` qualifier. | `[DOC]` |
| Retrieve execution | `GET /v1/streams/{id}/executions/{execId}` | Execution object (below). | `[DOC]` |
| List executions | `GET /v1/streams/{id}/executions` | `limit` default 50 **MAX 500**, `offset`. | `[DOC]` |
| Update (metadata) | **`PATCH`** `/v1/streams/{id}` | ⚠ **PATCH, not PUT.** Required **query** param `updateMethod` + body `{updateMethod:"REPLACE"|"APPEND"}`; returns a full DataSet object (**200**). **EXECUTION-gated.** | `[DOC]` |
| Delete | `DELETE /v1/streams/{id}` | ⚠ Deletes the Stream but **NOT the associated DataSet** (the *opposite* of `DELETE /v1/datasets/{id}`). Destructive/irreversible. **EXECUTION-gated.** | `[DOC]` |

- **Execution object shape** `[DOC]`: `{id (int), startedAt, currentState, createdAt, modifiedAt}`. Only
  `ACTIVE` appears in the spec examples; the full `currentState` enum is **undocumented** (don't enumerate
  states you haven't observed).
- ⚠ The Stream List / executions-List `limit` **maximum is 500**, a *different* cap from the DataSet-List
  maximum of **50** (`/v1/streams` vs `/v1/datasets`) — don't conflate them.

### Instance raw-CSV upload — v3 uploads flow `[DOC]`

Instance host (`{instance}.domo.com/api/data/v3/...`), dev-token/SID:
1. **START** — `POST /api/data/v3/datasources/{datasetId}/uploads` (body `{"action":null,"appendId":null}`;
   optional `?restateDataTag={partitionId}`) → returns an `uploadId`.
2. **PART** — `PUT /api/data/v3/datasources/{datasetId}/uploads/{uploadId}/parts/{partNumber}`,
   `Content-Type: text/csv`, raw CSV body; part numbers start at **1**, parallel-uploadable.
3. **COMMIT** — `PUT /api/data/v3/datasources/{datasetId}/uploads/{uploadId}/commit`, JSON body
   `{"action":"APPEND"|"REPLACE", "index":true, "restateDataTag":"{partitionId}"?}`.

> **Correction to the common mental model:** indexing is **NOT a separate 4th step** — it happens inside the
> commit call via the `index` field. Domo's own examples are inconsistent on its type (`"index":"true"` string
> vs `"index":true` boolean); the parameter table says boolean, so **use boolean `true`**. `[DOC]`

- This v3 flow is **instance/internal-auth** (dev-token/SID), distinct from the OAuth Stream API. Both are
  officially documented on the portal.

## PDP — Personalized Data Permissions (row policies) `[DOC]`

Row-level filter policies live on the **Platform (OAuth) DataSet API** at `api.domo.com` — **not** the
instance API, and **not** a developer token (use OAuth Bearer, `data` scope). CRUD under
`/v1/datasets/{dataset_id}/policies`:

| Operation | Call | Tier |
|---|---|---|
| Create | `POST   https://api.domo.com/v1/datasets/{dataset_id}/policies` | `[DOC]` |
| List | `GET    https://api.domo.com/v1/datasets/{dataset_id}/policies` | `[DOC]` |
| Update | `PUT    https://api.domo.com/v1/datasets/{dataset_id}/policies/{pdp_id}` | `[DOC]` |
| Delete | `DELETE https://api.domo.com/v1/datasets/{dataset_id}/policies/{pdp_id}` | `[DOC]` |
| Retrieve one | `GET    https://api.domo.com/v1/datasets/{dataset_id}/policies/{pdp_id}` | `[DOC]` — the platform DataSet spec has its own path key + a formal 200 schema `{id, type, name, filters[{column, values, operator, not}], users, groups}` |

- **Body / DataSet object** `[DOC]`: the DataSet carries `pdpEnabled` (bool) and `policies[]`. Each policy =
  `{ id, name, type ("user"|"system"), filters:[{ column, values:[...], operator (e.g. "EQUALS"), not:bool }],
  users:[userId...], groups:[groupId...] }`.
- **Create precondition** `[DOC]`: the referenced **users and groups must already exist** before a PDP policy can
  be created — the create op needs resolvable user/group IDs, so provision membership first, then the policy.
- This governs **ROW** (entitlement/filter) policies. **COLUMN-masking** policies are a separate, newer,
  UI/DomoStats-managed feature (KB cites a cap of **up to 20 column policies per DataSet**) and are **NOT**
  part of this REST API `[KB]`.
- The doc example only shows operator `EQUALS`; the broader operator set (greater_than, less_than, between,
  begins_with, dynamic/trusted-attribute) surfaces in the UI / Governance-Toolkit — **don't assume every UI
  operator is accepted verbatim** by the raw REST body without testing `[KB]`.
- **Values-length limit** `[DOC]`: for a single policy the **list of values** (including one delimiter
  character per value) must be **< 255 characters** — an aggregate string-length cap on the values list,
  **not** a per-value limit and **not** a policy-count cap (the 20-*column*-policy cap above is a separate
  `[KB]` feature).
- The **"All Rows" / open filter group policy CANNOT be deleted** — `DELETE` returns 400 "Cannot delete the
  open filter group" `[KB]`. Deletion is destructive/irreversible (back up policies first).
- In some SDKs `not` must be set as a dict key (`filter['not']=True`) because `not` is a reserved word `[REPO]`.
- The the original workspace repo does **not** call this API (grep: zero executable-code hits for `/policies` or SDK pdp
  helpers) — PDP appears only as conceptual prose in a few skills/reference docs `[REPO]`.

## Reading from Code Engine — tokenless, as the invoking user `[DOC]` mechanism

From Code Engine, read a dataset **without authoring any credentials**: `codeengine.sendRequest` (JS)
intercepts the call and **injects the credentials of the authenticated (invoking) user**, so it runs as
that user under their own permissions/PDP. `[DOC]` (KB 000005173 "Code Engine": sendRequest "can call into
various Domo APIs like DataSets," made "without any credentials," "injected with the credentials of the
authenticated user who is making the request.")

- **Use a RELATIVE path with NO leading slash.** The documented DataSets example is metadata:
  `codeengine.sendRequest("GET", "api/data/v3/datasources/{id}?part=...")` — relative, no leading slash. `[DOC]`
- **The SQL endpoint `api/query/v1/execute/{id}` (body `{sql}`) is itself a documented Domo API path** `[DOC]`
  — but documented for **token-based external callers**, and **no official doc shows it as a CE sendRequest
  target**. So calling `api/query/v1/execute/{id}` *via CE* is **`[INFER]`** (documented endpoint + documented
  "sendRequest can call DataSets" + documented credential injection), or **`[REPO]`** where this repo does it —
  **NOT `[DOC]`**. Write it relative (`api/query/v1/execute/{id}`), not `/api/...` — a leading slash breaking
  sendRequest is `[REPO]`/`[INFER]`, not stated in docs.
- The **Python `send_request`** name/signature/return shape is **`[INFER]`/`[REPO]`** — only the JS
  `sendRequest(method, url, body?, headers?, contentType?)` is documented (Python CE support exists per
  community forum, but its call naming is not in official docs). Probe both `send_request`/`sendRequest` and
  `get_execution_information`/`getExecutionInformation` casings; the client is exposed as `codeengine` and may
  be absent (`ce = globals().get("codeengine")`).
- "Authenticated user" = the executing user (not the package owner / a service account). Per-context principal
  resolution for scheduled Workflow / embedded-app runs is **undocumented** — verify empirically if identity
  matters. No documented rate limit / 429 / payload cap on CE-issued calls (only the 1GB / 5-min / single-output
  function envelope is documented). `[REPO]`

See [`domo-code-engine.md`](domo-code-engine.md) for the general "prefer CE tokenless; fall back to a token
only when the CE client can't do the job" rule, and [`domo-filesets.md`](domo-filesets.md) for the FileSet
slice of the same auth model.

## Finding a dataset by name — Search API returns the UUID in `databaseId` `[REPO]`

To resolve a dataset UUID from a name, use the internal Search API:

```
POST /api/search/v1/query
{"entities":["DATASET"], "query":"<name>", "count":25}
```

- **Read the UUID from each `searchObjects[]` entry's `databaseId` field, not `.id`** (the sibling `id` is a
  different value). `[REPO]`
- **Tier split (over-claim guard):** `databaseId` is the **documented term-FILTER field** for this endpoint
  (`{"filterType":"term","field":"databaseId","value":"<uuid>"}`) `[DOC]`. But the official 200 example shows
  an **empty `searchObjects[]`**, so the docs **never** state that response entries return the UUID under
  `databaseId` (or that a sibling `id` differs). That the *results* expose the UUID under `databaseId` is
  confirmed only by working repo code (verified 2026-05-11) + third-party domolibrary → **`[REPO]`, never
  `[DOC]`.** Verify live before relying on `.id` being the wrong field.
- **This is a search-results rule, NOT a listing rule.** The standard list/retrieve endpoints return the UUID
  in **`id`**: public `GET api.domo.com/v1/datasets[/{id}]` returns `"id":"<uuid>"` (no `databaseId`), and the
  instance v3 endpoints address datasets by `{datasetId}` in the path. Don't generalize "databaseId not id"
  beyond the Search API.
- **Payload key varies by source/version** `[REPO]`: this repo uses `entities:["DATASET"]` while an official
  example uses `entityList:[["dataflow"]]` — confirm the accepted shape on the target instance. `/api/search/v1/query`
  is an instance API (same APIs the UI uses), not part of the stable public contract.

## Error responses & response-shape gotchas `[DOC]`

Source: `platform/dataset.yaml` (HTTP 200, 55410 B — the same body charted above). The **only** operation
that documents error responses is the **import PUT** (`PUT /v1/datasets/{id}/data`); its `responses` block
declares exactly **three** error statuses — **400, 401, 403** — and each has a *different* documented shape.
No other operation in this spec documents any error response, and **no 404 or 5xx is documented anywhere**
in it. Frame those absences as "not documented in this spec", **never** as "cannot happen" — MISSING evidence
is not proof of absence (a live instance can still return a 404/500).

- **403** — the machine contract. Its `content` schema has a real `properties:` block carrying exactly
  **`{status, toe}`** — nothing else. `toe` is documented (via the property's own `description`) as
  **"Thread of Execution — a way Domo Support can track down a problem"** (an opaque support-trace id, not a
  field you branch on). **Do NOT claim 403 returns `statusReason` or `message`** — it does not.
- **401** — has **no response body schema at all**. Its only structured payload is a **`WWW-Authenticate`
  response header** (`schema: type: string`). Read a 401 by its status + that header, not by parsing a body.
  **Do NOT attribute any body field to a 401.**
- **400** — its schema is a **bare `type: object` with NO `properties:` block**. The four fields
  `status` / `statusReason` / `message` / `toe` appear **only inside an inline `example:` payload**, so they
  are illustrative, **not a declared machine contract**. Treat a 400 body as best-effort/example-shaped: read
  it for humans, don't code against those keys as if the schema guaranteed them.
- **`dataCurrentAt`** is documented **only** in the `info.description` `### Attributes` markdown table (spec
  line 38) — it appears in **no** response-body schema or example anywhere in this spec. Do **not** imply a
  GET/import response returns a `dataCurrentAt` field; if you need "data freshness", confirm the actual payload
  on the target instance rather than assuming this attribute is echoed back.

This is one operation's error block in one spec — do **not** read it as the shape of Domo error envelopes in
general, nor as OpenAPI-catalog exhaustion.

## Do NOT claim as documented fact (hedge list)

The verification's whole point was to keep these from being written as `[DOC]`. Do **not** state any of
these as a documented, portable Domo contract:

1. **That the dev-token/SID instance endpoint `POST /api/query/v1/execute/{id}` returns a columns/rows
   envelope using `FROM table`.** That exact composite is `[REPO]`; the instance docs show `your_table` + a
   "list of objects" response. The `[DOC]` `FROM table` + envelope path is the **OAuth** endpoint
   `api.domo.com/v1/datasets/query/execute/{id}`.
2. **That `/api/data/v3/datasources/{id}` (get/list/DELETE/rename) is a documented public contract.** It's the
   instance-internal API — `[REPO]`. The documented lifecycle contract is `api.domo.com/v1/datasets/{id}`.
   (The instance DELETE is real and repo-exercised, but still `[REPO]`.)
3. **That a 403 on delete = deleted.** 403 on an orphaned dataset is Access-Denied, not proof of deletion;
   `PUT`-rename returns 405. `[REPO]`
4. **That the Search API *returns* the UUID in `databaseId`.** Documented only as a term-FILTER field; the
   result-field behavior is `[REPO]`.
5. **That the bare `/api/query/v1/datasources/{id}/schema` path or its federated-403 behavior is documented.**
   The documented schema path is `.../schema/indexed`; the bare path + federated-403 + v3 fallback are `[REPO]`.
6. **That `api/query/v1/execute` works as a CE `sendRequest` target, or that Python `send_request` is the API
   name.** Both are `[INFER]`/`[REPO]` — only the JS `sendRequest` + the metadata `api/data/v3/datasources/{id}`
   example are `[DOC]` for CE.
7. **That a dev-token/SID is rejected everywhere, or that "401" is documented.** The rejection is specific to
   `api.domo.com`; the same dev-token is correct for instance Product endpoints. The 401 code is `[REPO]`.
8. **That the SQL API supports JOINs or trig functions** — it documents the opposite (no JOINs, no trig, page
   filters not applied). `[DOC]`
9. **That the instance `/api/data/v1/streams` is an identical mirror of `api.domo.com/v1/streams`** — the
   instance path is documented for *connector* streams (different body); the raw-CSV instance equivalent is the
   separate v3 uploads flow.
10. **That `updateMethod` accepts Merge/Upsert/Partition** — this REST param (data-endpoint query param and
    Stream-create body field) takes only REPLACE/APPEND; Merge/Partition are separate product features.
    **Stream Upsert** is achieved with `updateMethod:"APPEND"` **plus** a `keyColumnNames` create-body array —
    a distinct field, **not** a third `updateMethod` value.
11. **That PDP column-masking is part of the `/policies` REST API** — it's a separate UI/DomoStats feature
    (20-policy cap is `[KB]`).

## Safety / hygiene

- **Deletes are destructive and irreversible.** On the shared validation instance (`maintenance-instance`) only
  delete DataSets **you created** and clearly named (`zz-*`/`test-*`); verify ownership + `cardCount:0` (and
  no dependent dataflows) before any delete. Never delete or inventory a dataset you did not create. A 403 is
  Access-Denied, not a completed delete.
- **REPLACE overwrites everything.** `updateMethod=REPLACE` (and Stream/v3 REPLACE) wipes all existing rows —
  double-check the target id and that the CSV schema matches before a REPLACE against a real dataset.
- **Never commit** SIDs, developer tokens, OAuth client secrets/Bearer tokens, or raw query results. Dataset
  rows carry real customer column names/values — summarize, don't paste into commits/handoffs/PRs.
- **Match host to auth** (see the two-worlds table) — a leaked dev-token used against `api.domo.com` fails
  anyway (401), but the discipline of never mixing them is what keeps credentials scoped correctly.

## Repo precedent

Working DataSet usage already lives in the repo — grep the token, not the line (line numbers drift): `[REPO]`

| Where | What it demonstrates |
|---|---|
| `../docs/api-reference.md` | The read/query methods (in-app proxy, server SQL, list/get) and the "dev tokens 401 against api.domo.com" note |
| `../docs/reference/dataset-bridging.md`, `domo-cross-instance-clone.md` | Search-API `databaseId` resolution; federated bare-`/schema` 403 → v3 `/schema` fallback |
| `equipment-analytics-app/scripts/provision_domo.py` | `updateMethod=REPLACE` import against a real dataset |
| `internal-apps/**` (j-quants, portfolio-snapshot, feature-label) | pydomo `write_dataframe(update_method=...)` exercising APPEND / UPSERT |

Companion skills: [`domo-code-engine.md`](domo-code-engine.md) (CE auth mechanics),
[`domo-magic-etl.md`](domo-magic-etl.md) (reshape datasets on a schedule),
[`domo-filesets.md`](domo-filesets.md) (unstructured files, same two-surface auth model),
[`domo-procode-app.md`](domo-procode-app.md) (manifest `datasetsMapping` wiring).
