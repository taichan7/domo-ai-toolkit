# Domo Search

Use this skill to reason about — or drive via REST — **Domo's cross-entity Search**: the one `searchQuery` operation that takes a query string plus a rich filter/sort/facet grammar and returns matching Domo entities (datasets, cards, dataflows, pages, users, …). **Read the naming-trap table below before anything else**: "query" and "search" are among the most overloaded verbs in the Domo platform, and this skill owns **only the entity-Search endpoint** — **not** AppDB `documents/query`, **not** the DataSet SQL `/api/query/v1/execute`, **not** Beast Mode `/query/v1/functions`, **not** the FileSet `/query`. Sending a Search body to any of those (or vice-versa) is the classic silent misfire.

Search is a **single-world, single-operation island** — one OpenAPI spec, one developer-token POST — that is distinctively **input-heavy and output-opaque**: its lone operation carries a disproportionately rich REQUEST grammar (a 9-subtype discriminated `Filter` union, three filter-combination arrays, phonetic matching, faceting, field-sorting) yet **every RESULT container bottoms out in a bare `type: object` with no declared properties**. You can construct a query with full type-safety; you cannot, from the spec alone, know the shape of a single result row. This skill is a faithful map of that one op + a heavy disambiguation layer, guarded hard against over-claiming (**zero calls were executed** against the API).

## What this skill owns (and what it defers)

**Owns:** the **entity-Search verb** — `POST` `searchQuery` (spec models it at `{instance}.domo.com/query`; the dev portal routes it as `/api/search/v1/query` — see the headline for this unresolved discrepancy), `X-DOMO-Developer-Token` — its `SearchRequest` grammar (query, `entityList`, `filters`/`orFilters`/`notFilters`, the 9-subtype `Filter` union, `Sort`, faceting, `includePhonetic`, `fieldsToReturn`, `count`/`offset` paging) and its `SearchResponse` envelope.

**Defers:**
- **AppDB `documents/query`** (query an AppDB collection's JSON documents; `/api/datastores/v2/collections/{id}/documents/query` dev-token or `/domo/datastores/v1/...` JWT) → `domo-code-engine.md` / the AppDB helpers. A **different** `query` verb over a **different** store — the #1 in-repo false friend.
- **DataSet SQL query** (`/api/query/v1/execute/{datasetId}`, `/sql/v1/...`, in-app `domo.post('/sql/...')`) → `domo-datasets.md`. Runs SQL against one DataSet's rows; unrelated to entity search.
- **Beast Mode functions** (`/api/query/v1/functions/...` search/get/update) → `domo-beast-mode.md`. Same `/api/query/v1/` prefix, **different** resource (calculated fields, not entity search).
- **FileSet content `query`** (`/domo/files/v1/filesets/{id}/query` — semantic/RAG retrieval over uploaded documents) → `domo-filesets.md`. FileSets also expose a `search` op; neither is this entity-Search endpoint.
- **The per-entity object shape a result row denotes** (a card's fields, a dataset's fields, …) → each entity's own skill (`domo-cards.md`, `domo-datasets.md`, `domo-pages.md`, `domo-identity-access.md`, …). Search returns **untyped** result objects; it does not define what a "card" or "dataset" looks like.
- **Minting the developer/access token** and the role/grant model → `domo-identity-access.md`.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo-support.domo.com/s/article/<digits> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall / 404) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting an untested runtime behavior, an inference-from-absence, or an illustrative `example:` value as a documented contract. This entire skill is `[DOC]`/`[INFER]` with **only two `[REPO]` facts** (both about what Search is *not* — see repo false friends) and **zero `[KB]`**: no working code in this repo calls the Search API, and **no request was ever executed** against it — so treat all request/response *behavior* (does a bad token 401; what a result row contains; does `/query` vs `/api/search/v1/query` resolve; does deep pagination hit the 10,000 wall) as **documented-but-untested**. Tier census of this skill's claims: **`[DOC]` 51 / `[INFER]` 16 / `[REPO]` 2 / `[KB]` 0.**

**Verification provenance.** Written after verification Workflow **`wf_24a9e7eb-887`** (14 agents, 0 errors: 5 spec-reading cross-check clusters — op/auth/limits, request body, filter union, response/sort, entity vocabulary — → adversarial refute of the 6 highest over-claim-risk claims, each default-refuted-if-uncertain → completeness critic + island verdict → synthesizer), corroborated by a **direct full read of the raw YAML** `/tmp/search-api.yaml` (473 lines), fetched fresh via a browser-User-Agent `curl` from `domo.com/docs/openapi/product/search-api.yaml` (a plain `curl` **405**s — the host is UA-gated; a 405 is MISSING evidence, not absence) and read line-by-line this session. **All 6 adversarial verdicts were caught and folded into the hedge list** (2 REFUTED outright + 4 PARTIAL/re-tier) — the guarded failure mode working as designed: the typed-per-entity-result claim and the authoritative-field-catalog claim → **REFUTED** to `[DOC]`; entity-closedness, only-way-to-search, hard-120-rpm-limit, and complete-failure-set → **PARTIAL/re-tier** to `[INFER]`. 鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).

## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first. **"query" is a path segment on at least five unrelated Domo APIs** — the endpoint you want is the entity-Search one, and the others take incompatible bodies.

| You see… | It actually is… | Owner |
|---|---|---|
| **`searchQuery` / `POST /query` (spec) / `POST /api/search/v1/query` (portal)** with `entityList` + `filters` | the **entity-Search verb** (this API) | **this skill** |
| **`/api/datastores/v2/collections/{id}/documents/query`** (or `/domo/datastores/v1/...`) | **AppDB** document query (MongoDB-style over a collection) | `domo-code-engine.md` |
| **`/api/query/v1/execute/{datasetId}`**, `/sql/v1/...`, `domo.post('/sql/...')` | **DataSet SQL** query (SQL over one DataSet's rows) | `domo-datasets.md` |
| **`/api/query/v1/functions/...`** (search / get / update-expression) | **Beast Mode** calculated-field ops | `domo-beast-mode.md` |
| **`/domo/files/v1/filesets/{id}/query`** (and FileSet `search`) | **FileSet** content retrieval (semantic/RAG over uploaded docs) | `domo-filesets.md` |
| **`X-DOMO-Developer-Token`** on any of the above | the **same header, unrelated surface** — the header does not identify the API | (per-API) |

**Internal traps — all *within* Search's own single spec:**
- **`entityList` is an array-of-ARRAYS, not a flat list** — 2-D: the outer array groups, the inner array holds entity name strings. The example is `[['dataflow']]`, **not** `['dataflow']`. Grouping (`[['card','dataset'],['user']]`) mirrors into `searchResultsMap`.
- **The 12 valid entities are prose, not a formal enum** — they live in the `entityList` *description* introduced by the word **"include"** (items are a bare `type: string`); there is NO OpenAPI `enum`. The 12-name list is `[DOC]`; its **closedness is `[INFER]`** — do not present it as the authoritative complete set of server-accepted values.
- **Three filter arrays + a per-filter `not`** — `filters`=match **ALL** (AND), `orFilters`=match **ANY** (OR), `notFilters`=match **NONE** (NOT), all request-level. Independently, a per-filter `not:true` flag exists on **only 4 of 9** subtypes (`term`, `dateRange`, `numeric`, `missing`). Double-negation (a per-filter `not` inside `notFilters`) is unspecified.
- **`searchObjects` vs `searchResultsMap` vs `facetMap` — all untyped.** `searchObjects` = a flat array of bare objects; `searchResultsMap` = a keyed map of arrays of bare objects (grouped by `entityList`); `facetMap` = a keyed map of bare objects. None declare any properties, and **which container is populated is unspecified**.
- **`count` is `integer`, `offset` is `number`** — a real type asymmetry in the schema. The **10,000 limit is a COMBINED `count`+`offset` reachable-record ceiling** (deep pagination past 10,000 total is blocked), NOT a per-page `count` maximum; no `maximum` keyword bounds `count` itself.
- **`includePhonetic` has NO default** — the request *example* sets it `true`, but an example is not a `default:`; effective behavior when omitted is undocumented. Asserting "defaults to true" is over-claiming.
- **`count` example 20 vs schema default 10** — the requestBody `example` sets `count:20` (and `sort:{}`), but the schema `default` for `count` is **10**. Codegen and effective omitted-value behavior follow the schema `default:`, not the illustrative example.
- **`value` means three different things** — `TermFilter.value` = an OPTIONAL string term; `DateBucketFilter.value` = a REQUIRED 4-value enum; `BooleanFilter.value` = a REQUIRED boolean. Requiredness, type, and enum differ per subtype.
- **`DateRangeFilter` vs `RangeFilter`** — both have `from`/`to`, but `DateRangeFilter`'s are `date-time` strings and it carries a `not` flag; `RangeFilter`'s are plain numbers and it has **NO** `not`. Date-field vs numeric-field respectively.
- **`Sort` (request) vs `SortResponse` (response) are different schemas** — the `sort` you send (`{fieldSorts, isRelevance}`) is NOT the `sort` you get back (`{fieldSorts(nullable), activity, activitySortType, metricAction, isHotness, isRelevance}`). The response sort is not round-trippable into a request sort.
- **`dateBucket.value` is a closed 4-value enum** — `[LAST_DAY, LAST_WEEK, LAST_MONTH, LAST_QUARTER]`. No `LAST_YEAR`, `LAST_HOUR`, or custom bucket. (Whether instance-extensible at runtime is not positively asserted.)

## The headline — a single-world, single-operation island

One OpenAPI spec — `search-api.yaml`, **OpenAPI 3.0.3**, `info.version` **1.0.0**, title **"Domo Search Product API"** — with **exactly one path and one operation**: `POST /query`, `operationId` **`searchQuery`**, tag "Search Product API". One server `https://{instance}.domo.com`, one global securityScheme `DeveloperToken` = apiKey header **`X-DOMO-Developer-Token`** (no OAuth, no scope). `[DOC]`

**The URL discrepancy `[DOC]` vs `[DOC]` — unresolved.** The spec models the operation at bare **`{instance}.domo.com/query`** (server + path). The dev-portal overview page documents it as **`POST /api/search/v1/query`**. Both are first-party `[DOC]`, and a **live call was not made** to arbitrate — so **do not hard-code `/query` alone**; the portal's `/api/search/v1/query` is the likelier real route (bare `/query` may 404). Carry both; verify against the running instance before trusting either.

**Why single-world, single-operation (the island verdict) `[DOC]`/`[INFER]`:** the spec's `paths` object contains exactly one path with one method (count = 1 path / 1 op). There is one host, one auth scheme, no `/domo/` App-Framework twin declared, no OAuth `api.domo.com` twin declared. It is **not** a two-world split (contrast rank-11 Pages / rank-14b Task Center) and **not** a mirror pair (contrast rank-13 Projects) — it is a lone POST. The absolute "no other search surface exists anywhere in Domo" is **`[INFER]` and refuted** (see hedge #2): other `/query` verbs exist for other stores. What is `[DOC]` is narrower: *within this spec* there is one operation.

**Documented limits `[DOC]`/`[INFER]`:**
- **Max records: 10,000** — a **combined `count`+`offset`** reachable-record ceiling (`offset` description: "Count and offset can only return a total of 10,000 records"). Deep pagination past 10,000 total results is blocked; this is **not** a per-page `count` cap.
- **Rate: "Recommended not to exceed 120 requests per minute (may vary by instance)"** — **advisory, per-instance guidance, NOT a hard platform cap** (see hedge #5). What is `[DOC]` is only that *some* rate limiting exists (429 is documented); the specific "120" number is a soft recommendation that varies by instance.

**Documented response codes: `200` / `400` / `401` / `429` `[DOC]`.** Only `200` carries a schema (`SearchResponse`); `400` (Bad request), `401` (Unauthorized), `429` (Too many requests) are description-only. **`403`/`404`/`5xx`/`default` are ABSENT** — so the documented failure set is `[DOC]` but its **completeness is `[INFER]` and likely false** (no 5xx documented; see hedge #6). (Note: unlike the Federated island's 200-only specs, Search *does* document three failure codes — but still not a complete set.)

## The surface — one operation `[DOC]`

| Method | Path (spec / portal) | operationId | Body | Success | Documented failures | Tier |
|---|---|---|---|---|---|---|
| POST | `/query` (spec) · `/api/search/v1/query` (portal) | `searchQuery` | **REQUIRED** `SearchRequest` (application/json) | `200` → `SearchResponse` | `400` / `401` / `429` (description-only) | `[DOC]` |

`requestBody.required: true` — the body is mandatory. The only success schema is `SearchResponse`. There is **no** GET, no list op, no facet-only op, no autocomplete op, no second path — the entire API is this one POST.

## The request grammar — input-heavy `[DOC]`

`SearchRequest` is `type: object`, **`required: [query, entityList]`**, with **13 properties**. `[DOC]`

| Property | Type | Default | Req? | Notes |
|---|---|---|---|---|
| `query` | string | — | **REQUIRED** | The query term. **Use `*` for wildcard.** |
| `entityList` | **array of array of string** | — | **REQUIRED** | 2-D: outer=groups, inner=entity names. Example `[['dataflow']]`. See the 12-entity list + closedness caveat. |
| `count` | **integer** | **10** | no | How many results to return. (Example sets 20; schema default is 10.) No `maximum`. |
| `offset` | **number** | 0 | no | Results offset. `count`+`offset` can return at most **10,000** total. |
| `filters` | array of `Filter` | `[]` | no | Results must match **ALL** (AND). |
| `orFilters` | array of `Filter` | `[]` | no | Results must match **ANY** (OR). |
| `notFilters` | array of `Filter` | `[]` | no | Results must match **NONE** (NOT). |
| `sort` | `$ref Sort` | — (relevance) | no | Defaults to relevance sorting. Request-side `Sort`, not `SortResponse`. |
| `facetValuesToInclude` | array of string | `[]` | no | Facets (groupings) to include in results. |
| `facetValueLimit` | number | 0 | no | How many facet values to return. |
| `facetValueOffset` | number | 0 | no | Facet value offset. |
| `includePhonetic` | boolean | **NONE** | no | Phonetic matching. Example sets `true`, but there is **no `default:`** — omitted behavior undocumented. |
| `fieldsToReturn` | array of string | — (all fields) | no | Which fields to return; defaults to all. **No field vocabulary is enumerated anywhere.** |

**The 12 entities `entityList` names `[DOC]` (closedness `[INFER]`):** `account`, `alert`, `app`, `beast_mode`, `card`, `connector`, `data_app`, `dataset`, `dataflow`, `group`, `page`, `user`. They appear in the `entityList` description prose introduced by "**include**" — a bare `type: string`, **no OpenAPI enum** — so the list is documented but its closedness (that no other value is server-accepted) is inference, **not** fact. `fieldsToReturn` and every filter's `field` are **free-form strings** with no documented vocabulary — the queryable field names for any entity are uncharted (`[INFER]`; see hedge #4).

## The Filter discriminated union — 9 subtypes `[DOC]`

Each element of `filters`/`orFilters`/`notFilters` is a `Filter` = a **`oneOf` of 9 subtypes**, selected by a **`discriminator` on `filterType`**. Every subtype requires `filterType` + `field` (a **free-form string** field name — see hedge #4). `[DOC]`

| `filterType` | Subtype | Also required | Value fields | Enum / notes | per-filter `not`? |
|---|---|---|---|---|---|
| `term` | TermFilter | — | `value` (string) **OR** `values` (array of string) | exact-match; use one of value/values | **yes** (default false) |
| `wildcard` | WildcardFilter | `query` | `query` (string) | **use `*` for wildcard** | no |
| `queryString` | QueryStringFilter | `queryString` | `queryString` (string) | Lucene-ish, ex `revenue AND sales` | no |
| `dateBucket` | DateBucketFilter | `value` | `value` (string) | **enum `[LAST_DAY, LAST_WEEK, LAST_MONTH, LAST_QUARTER]`** (closed 4) | no |
| `dateRange` | DateRangeFilter | — | `from` / `to` (**date-time**) | date-field range | **yes** (default false) |
| `numeric` | NumericFilter | `operator` | `longNumber` (int64) **OR** `floatNumber` (float) | **operator enum `[LT, LTE, EQ, GT, GTE]`** (no not-equal) | **yes** (default false) |
| `range` | RangeFilter | — | `from` / `to` (**number**) | numeric-field range | no |
| `boolean` | BooleanFilter | `value` | `value` (**boolean**) | — | no |
| `missing` | MissingFilter | — | — | matches when `field` exists (invert to find missing) | **yes** (default false) |

**Two negation mechanisms, do not conflate:** the request-level `notFilters` array negates **any** filter; the per-filter `not:true` flag exists on **only** `term`/`dateRange`/`numeric`/`missing`. The other five (`wildcard`, `queryString`, `dateBucket`, `range`, `boolean`) negate **only** via `notFilters`. A subtype's `required[]` is not a guarantee of a semantically complete filter (e.g. `TermFilter` requires only `filterType`+`field` but is meaningless without `value`/`values`).

## Sort vs SortResponse `[DOC]`

**Request-side `Sort`** `[DOC]` = `{ fieldSorts: [FieldSort], isRelevance: boolean }`. `FieldSort` = `{ field (string), sortOrder }`, **`required: [field, sortOrder]`**, where **`sortOrder` is a closed enum `[ASC, DESC]`** — the only closed enum in the sort schemas. `isRelevance` toggles relevance-to-user ordering.

**Response-side `SortResponse`** `[DOC]` = a **different** schema: `{ fieldSorts (array of FieldSort, nullable), activity, activitySortType, metricAction, isHotness (bool), isRelevance (bool) }`. **`activity`, `activitySortType`, and `metricAction` are declared `nullable: true` with NO `type`** — shape uncharted. The response `sort` echoes what sort the server actually applied; it is **not round-trippable** back into a request `Sort` (extra untyped fields, no shared schema). Do not assume you can feed a `SortResponse` back as a request `Sort`.

## The response — output-opaque `[DOC]`

`SearchResponse` is `type: object` with **7 properties, NONE required**. `[DOC]` This is the output-opaque half of the island: the envelope is typed at the top level, but **every result-bearing container bottoms out in a bare `type: object` with no declared properties.**

| Property | Type | Notes |
|---|---|---|
| `totalResultCount` | integer | Total matches for the query (example `1865`). |
| `queryUuid` | string | Server-generated id for this query (example a uuid). |
| `hideSearchObjects` | boolean | Example `false`. Semantics uncharted. |
| `sort` | `$ref SortResponse` | The sort the server used — **`SortResponse`, not request `Sort`** (see above). |
| `facetMap` | object → `additionalProperties: {type: object}` | The requested facet groupings. **Facet object shape undeclared.** |
| `searchObjects` | array → `items: {type: object}` | Flat list of all results. **Each result object has NO declared properties.** |
| `searchResultsMap` | object → `additionalProperties: {type: array of {type: object}}` | Results grouped as defined by `entityList`. **Same untyped result objects, keyed.** |

**All three result containers are UNTYPED `[DOC]`.** There is **no per-entity result schema anywhere in the spec** — nothing tells you what fields a card-result vs a dataset-result carries, nor **which** container (`searchObjects` vs `searchResultsMap`) is populated for a given request (unspecified — see hedge #3). To learn a result's real shape you must inspect a live response or consult the entity's own skill; the Search spec will not tell you.

## Auth line `[DOC]`/`[INFER]`

- **Header:** `X-DOMO-Developer-Token` — securityScheme `DeveloperToken`, `type: apiKey`, `in: header`, applied globally (`security: [ - DeveloperToken: [] ]`), no per-op override. `[DOC]`
- **No OAuth:** the spec declares no `oauth2` scheme and no scope; the sole server is `{instance}.domo.com`. This is a Product-host dev-token API, **not** the Platform OAuth `api.domo.com` Bearer world. `[DOC]`
- **Same-as / different-from other Domo dev-token APIs?** The spec is **silent** on whether this is the same admin-panel access token used by other `X-DOMO-Developer-Token` APIs or a search-specific one → **`[INFER]`; do not assert either.** The ubiquitous in-repo `X-DOMO-Developer-Token` is all FileSets/provisioning/DataFlow — same header, unrelated surfaces.
- **Token minting + the role/grant to search** → `domo-identity-access.md`. Whether a specific grant gates search (vs any valid token) is undocumented → `[INFER]`.

## Boundaries & orphans

- **The URL is unresolved between two `[DOC]` sources.** Spec = bare `/query`; portal = `/api/search/v1/query`. No live call arbitrated. Treat the portal path as the likelier route, keep both, verify against the instance.
- **Result-object shapes are orphaned to the entity skills.** Search returns untyped objects; what a "card" or "dataset" result contains is owned by `domo-cards.md` / `domo-datasets.md` / `domo-pages.md` / `domo-identity-access.md` / etc. Search never defines them.
- **Queryable-field vocabulary is uncharted `[INFER]`.** Every filter `field` and `fieldsToReturn` entry is a free-form string; the spec's example field names (`databaseId`, `name`, `createDate`, `rowCount`, `description`, `isActive`) are **illustrative `example:` values, not a catalog** (hedge #4). Which fields are queryable per entity is not documented.
- **Which result container fills, and facet payload shape, are `[INFER]`.** `searchObjects` vs `searchResultsMap` population rule, and the `facetMap` value object shape, are unspecified.
- **Runtime behavior is `[INFER]` throughout.** Sync (it reads synchronous — a single POST returning results), pagination past 10,000, empty-`entityList` behavior, `*`-only query, phonetic-off default, error bodies for 400/401/429, and any 403/404/5xx — all untested. Zero executed calls.
- **The 10,000 ceiling is a hard product limit `[DOC]`** but its enforcement mechanism (silent truncation? error? which code?) is `[INFER]`.

## Repo false friends `[REPO]`

**Repo precedent = ZERO** `[REPO]`. A full-tree grep (all `.py/.js/.mjs/.ts/.sh/.ipynb`, tracked + untracked) for the 8 distinctive Search tokens — `searchQuery`, `entityList`, `facetValuesToInclude`, `orFilters`, `notFilters`, `includePhonetic`, `searchObjects`, `searchResultsMap` — returns **no caller**; the only file that will match is this skill doc. **Therefore the `searchQuery` op stays `[DOC]`, never `[REPO]`,** and no request was ever executed.

The **two `[REPO]` facts** this skill carries are both about what Search is *not* — the in-repo `/query`-family calls are all **different APIs**:

- **AppDB `documents/query`** — `/api/datastores/v2/collections/{id}/documents/query` (dev-token) in `provision_domo.py`, `support_service.py`, `fileset_ops.py`, `inventory_service.py`, `asset_lifecycle_service.py`, pl-summary, news-summary; and `/domo/datastores/v1/collections/{name}/documents/query` (JWT) in the marketdata pro-code app. **`[REPO]`** — MongoDB-style query over an AppDB collection, not entity search → `domo-code-engine.md`.
- **DataSet SQL / Beast Mode / FileSet `query`** — `/api/query/v1/execute/{id}` (DataSet SQL), `/api/query/v1/functions/...` (Beast Mode), `/domo/files/v1/filesets/{id}/query` (FileSet retrieval) appear across the repo as their own verbs. **`[REPO]`** that **`POST /query` is NOT the platform's only query surface** — this directly refutes any "only way to search/query in Domo" claim (hedge #2).

The ubiquitous in-repo **`X-DOMO-Developer-Token`** is all FileSets/provisioning/DataFlow — **same header, unrelated surface.** The distinctive Search tokens are the real test, and they are **zero**.

## Do NOT claim as documented fact

Every item below is an over-claim the verification workflow REFUTED or re-tiered, or a completeness gap it flagged. Guard them:

1. **Do NOT** say the **12 entities form a closed enum**. The 12-name list (`account, alert, app, beast_mode, card, connector, data_app, dataset, dataflow, group, page, user`) is `[DOC]`, but it lives in the `entityList` description prose introduced by "**include**" with items typed as a bare `string` — **no OpenAPI enum**. Closedness (that no other value is accepted) is `[INFER]`. Phrase as "the 12 entities the spec names," not "the only accepted values." *(PARTIAL)*
2. **Do NOT** say **`POST /query` is the only way to search/query in Domo**. "The only operation *in this spec*" is `[DOC]`; platform-wide exclusivity is `[INFER]` and **refuted** — AppDB `documents/query`, DataSet SQL `/api/query/v1/execute`, Beast Mode `/query/v1/functions`, and FileSet `/query` are separate query surfaces (`[REPO]`). *(PARTIAL / refuted by repo)*
3. **Do NOT** claim **`searchObjects`/`searchResultsMap`/`facetMap` have a typed, per-entity result schema** a caller can rely on. All three bottom out in a bare `type: object` (or array of bare object) with **no declared properties**; there is no per-entity result schema anywhere, and which container populates is unspecified. `[DOC]` refutes it. *(REFUTED → `[DOC]`)*
4. **Do NOT** treat the **filter example field names** (`databaseId`, `name`, `createDate`, `rowCount`, `description`, `isActive`) **as the authoritative catalog of queryable fields**. They are OpenAPI `example:` values on a **free-form `type: string` `field`** — illustrative, non-exhaustive, not entity-scoped. The real per-entity field vocabulary is uncharted `[INFER]`. `[DOC]` refutes it. *(REFUTED → `[DOC]`)*
5. **Do NOT** state **120 requests/minute as a hard, enforced, platform-wide limit**. The spec says "**Recommended** not to exceed 120 requests per minute (**may vary by instance**)" — soft, per-instance guidance. Only "some rate limiting exists (429 is documented)" is `[DOC]`. *(REFUTED → `[DOC]` advisory)*
6. **Do NOT** claim **400/401/429 are the complete failure set**. That documented list is `[DOC]`, but completeness is `[INFER]` and likely false — no `403`/`404`/`5xx`/`default` is documented, and a real server surely returns some. Present them as "the documented codes," not "all possible failures." *(PARTIAL)*
7. **Do NOT** send **`entityList` as a flat array**. It is an **array of arrays** (`[['dataflow']]`); a flat `['dataflow']` is the wrong shape. `[DOC]`
8. **Do NOT** hard-code the URL as bare **`/query`**. The spec models `{instance}.domo.com/query` but the portal documents `/api/search/v1/query`; both `[DOC]`, unarbitrated by a live call. Carry both, prefer the portal path, verify live. `[INFER]` which resolves.
9. **Do NOT** assert **`includePhonetic` defaults to `true`**. It has **no `default:`**; the example's `true` is not a default. Omitted behavior is undocumented `[INFER]`.
10. **Do NOT** assume **`count` defaults to 20**. The schema `default` is **10**; the requestBody example's `count:20` is illustrative only. `[DOC]`
11. **Do NOT** treat **`count` and `offset` as the same type**. `count` is `integer`, `offset` is `number` — a real schema asymmetry. `[DOC]`
12. **Do NOT** read the **10,000 limit as a per-page `count` cap**. It is a **combined `count`+`offset`** reachable-record ceiling (deep pagination past 10,000 total is blocked); no `maximum` bounds `count` itself. `[DOC]`
13. **Do NOT** treat **`value` as one consistent field** across filter subtypes. `TermFilter.value` = optional string; `DateBucketFilter.value` = required 4-value enum; `BooleanFilter.value` = required boolean. `[DOC]`
14. **Do NOT** give **every filter a `not` flag**. Only `term`/`dateRange`/`numeric`/`missing` (4 of 9) declare per-filter `not`; the other five negate only via request-level `notFilters`. `[DOC]`
15. **Do NOT** feed a **`SortResponse` back as a request `Sort`**. They are different schemas — the response adds untyped `activity`/`activitySortType`/`metricAction` and a nullable `fieldSorts`; not round-trippable. `[DOC]`
16. **Do NOT** invent **date buckets or numeric operators**. `dateBucket.value` is the closed enum `[LAST_DAY, LAST_WEEK, LAST_MONTH, LAST_QUARTER]` (no LAST_YEAR/LAST_HOUR/custom); `numeric.operator` is `[LT, LTE, EQ, GT, GTE]` (**no not-equal** — use `not:true` to invert `EQ`). `[DOC]`
17. **Do NOT** frame the `searchQuery` op as **`[REPO]`-verified or "works"** — zero repo callers of any Search token, zero executed calls. It is `[DOC]`-never-`[REPO]`.

## Safety & hygiene

- **`X-DOMO-Developer-Token` is a secret** — never write it into source, handoffs, or commits; read it from config at call time (repo convention: macOS Keychain / `~/.config/domo-utils/`). Never log the token.
- **Search is read-only, but the query itself is data-exfiltration surface.** A broad `entityList` + wildcard `query` can enumerate an instance's assets (dataset names, card titles, user records). Scope `entityList` and `filters` to intent; do not dump the whole instance inventory casually. Results respect the calling token's permissions `[INFER]` — do not assume otherwise, and do not assume they do (untested).
- **Verify the URL against the running instance before scripting it.** Bare `/query` (spec) may 404; `/api/search/v1/query` (portal) is the likelier route. A wrong path is a silent misfire (404, not a validation error).
- **Get the request shape right — three silent traps:** `entityList` must be an **array of arrays**; a filter's `filterType` must match one of the 9 discriminator values exactly; a per-filter `not` only exists on 4 subtypes (use `notFilters` for the rest). A malformed body surfaces as `400` with an uncharted body.
- **Mind the 10,000 ceiling for pagination loops.** Paging with `offset` cannot reach beyond 10,000 total records; a loop that assumes unbounded `offset` will silently stall or error at the wall. Narrow with `filters` instead of deep-paging.
- **Do not trust result-object fields you have not seen.** The spec types results as bare objects; read a live response (or the entity's own skill) before depending on any result field name.

## Companion skills

- `domo-code-engine.md` — **AppDB `documents/query`** (the #1 in-repo `query` false friend) and the tokenless in-app request model.
- `domo-datasets.md` — **DataSet SQL query** (`/api/query/v1/execute`) and the object shape behind a `dataset`/`data_app` search result; the Platform-vs-Product host/auth split.
- `domo-beast-mode.md` — **Beast Mode `/api/query/v1/functions`** (same `/api/query/v1/` prefix, different resource) and the `beast_mode` entity's real shape.
- `domo-filesets.md` — the **FileSet `search`/`query`** content-retrieval ops (semantic/RAG over uploaded docs) — a different search than this entity Search.
- `domo-cards.md` / `domo-pages.md` / `domo-identity-access.md` / `domo-accounts-connectors.md` / `domo-alerts.md` — the **object shapes** behind `card`/`app`/`page`, `user`/`group`, `account`/`connector`, and `alert` search results, which this untyped-result API never defines. `domo-identity-access.md` also owns token minting + the (uncharted) search grant.
- `domo-projects.md` / `domo-task-center.md` / `domo-scheduled-reports.md` / `domo-certified-content.md` / `domo-federated.md` — sibling **single-world documented islands** for shape contrast (this one is the first **single-operation, output-opaque** variant).
