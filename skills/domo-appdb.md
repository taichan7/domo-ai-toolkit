# Domo AppDB / DataStore API — the two-world JSON-document store

Use when: reading/writing **AppDB documents** (Domo's NoSQL JSON-document store, a.k.a. DataStore / Collections), defining a **collection schema**, wiring a collection's **standard-sync to a DataSet**, exporting/downloading/importing documents, or reasoning about the **two distinct API worlds** (Product REST vs App-Framework in-app) an AppDB collection is reachable through. This is a **documentation skill** — verification-only, zero-instance-call — but the destructive ops it charts (DELETE datastore/collection cascades, bulk delete) **gate on explicit human intent, NOT the autonomous loop**.

Every claim below carries an evidence tier: `[DOC]` = first-party Domo OpenAPI YAML (`domo.com/docs/openapi/{product,framework}/appdb.yaml`); `[KB]` = Domo KB/community; `[REPO]` = verified against this repo's running code; `[INFER]` = reasoned / inference-from-absence. **A fetch failure is missing evidence, never proof of absence; a universal negative is at best `[INFER]`.** The single guarded failure mode is **over-claiming** — do not present a repo convenience, a UI-only fact, or an inference as a documented contract.

Verified via Workflow `wf_*` (15 agents, all succeeded; 5 spec-reading cross-check clusters → adversarial refute of the 9 highest over-claim-risk claims → synthesizer/island-verdict = **SKILL**; verdicts **0 CONFIRMED / 2 PARTIAL / 7 REFUTED**, every refuted claim folded verbatim into the DO-NOT guards below) cross-read against both raw candidate specs (`product/appdb.yaml` "App DB API", sha `0816d52c…`, 2167 lines; `framework/appdb.yaml` "Domo AppDB API", sha `fcf3d3b1…`, 3451 lines — **re-fetched browser-UA, each byte-identical to its `/tmp` copy**) plus `[REPO]` facts from `../scripts/appdb-prune-latest.py`, `../docs/domo-workflow-reference.md`, `domo-cross-instance-clone.md`, and `appdb-cleanup.md`. Tier census: `[DOC]` 34 / `[KB]` 3 / `[REPO]` 11 / `[INFER]` 8 (rank-70 folded +4 `[DOC]` facts — per-document 2 MB bulk-op cap, partial-update operator whitelist + `$setOnInsert` no-op, permission-token enums, nested-object JSON-string sync — plus a `[DOC]` World-B `export`-path drift correction, all re-verified against `product|framework/appdb.yaml`).

---

## 1. Purpose & scope

**AppDB** is Domo's per-instance NoSQL JSON-document store. A **document** = a JSON blob the app owns (`content`) wrapped in a system-assigned `envelope`; documents live in a **collection**; collections live in a **datastore**. A collection with `syncEnabled` **materializes its documents' top-level `content` keys into a linked Domo DataSet** (`datasourceId`), making AppDB data queryable as a normal dataset.

This skill **OWNS**: the two-world API contract, the envelope-vs-content model, Collection/Datastore schemas, document CRUD + bulk + query, the **export(=sync trigger) / download(=≤100 egress) / import(=upsert restore)** false-friend resolution, the permission model, versioning/deprecation, the response-code shape, and the destructive-op human-gate.

It **DEFERS** (cross-ref only, do not re-own): the recurring document-**PRUNE** workflow + fast script → `appdb-cleanup.md`; the **tokenless CE client** (`api/content/v1/datastores`) + the actor-into-content audit rule → `domo-code-engine.md`; the standard-sync **DataSet name-lock** (`{collectionName}_{datastoreName}_APP_DB`) + DataSet lifecycle/history → `domo-datasets.md` (+ `domo-managing-dataset-history.md`); the `documents/query` naming-trap alignment → `domo-search.md`.

---

## 2. The two worlds at a glance

AppDB is exposed through **two distinct first-party OpenAPI worlds** on `{instance}.domo.com`. They are **NOT mirrors** and **NOT auth-interchangeable** — different SHA-256, different op counts, disjoint bases, UUID-vs-name keying.

| Aspect | **World A — Product REST** | **World B — App-Framework in-app** |
|---|---|---|
| Spec file | `product/appdb.yaml` ("App DB API") | `framework/appdb.yaml` ("Domo AppDB API") |
| Base path | `/api/datastores/v{1,2}/` | `/domo/datastores/v{1,2}/` |
| Auth | documented `apiKey` header `X-DOMO-Developer-Token` `[DOC]`; repo also uses `X-Domo-Authentication:$SID` + tokenless CE relative-path `[REPO]` | spec declares **NO** `securityScheme` → App-Framework injects the browser-session identity `[DOC-structural]`; **not** SID-accessible (returns HTML login) `[REPO]` |
| Key | `collectionId` (UUID) + `datastoreId` (UUID — use the `id` field, not numeric `datastore_id`) | `collectionName` (manifest name, **case-sensitive**; `collectionsMapping` routes by the ORIGINAL manifest name even after rename) |
| Op count | **35** | **27** |
| Has | datastore CRUD, permission CRUD, **download**, **import** | — (none of those) |
| Documents | v1 (all `deprecated:true`) + v2 (current) | v1 + v2, **neither deprecated** |

**A third prefix exists but is in NEITHER spec:** `api/content/v1/datastores` = the **tokenless Code Engine proxy** family, owned by `domo-code-engine.md`. Keep all three distinct: `/api/datastores` (World A), `/domo/datastores` (World B), `api/content/v1/datastores` (CE proxy). `[REPO]`

---

## 3. Auth reality (documented vs repo-observed)

- **World A documented auth** = global `apiKey` header **`X-DOMO-Developer-Token`** `[DOC]`. This documents dev-token as **A** valid scheme — it is **NOT** a positive statement that SID/session is rejected.
- **World A repo reality** `[REPO]`: `../scripts/appdb-prune-latest.py` sends BOTH `X-DOMO-Developer-Token` **and** `X-Domo-Authentication:$SID` against `/api/datastores/v2/collections/…`; Code Engine reaches the **same** v2 paths **tokenless** via relative-path `codeengine.sendRequest` (`../docs/domo-workflow-reference.md`). So dev-token is one working auth, not the only one.
- **World B auth** = the Framework spec declares **no** `securitySchemes` and **no** `security` block anywhere `[DOC-structural]`. The caller authors no token because the App-Framework injects the logged-in app user's **browser-session identity**. The label "injected bearer JWT / tokenless" is a reasoned `[INFER]`/`[KB]` gloss — **the spec never names JWT/bearer**. It is **NOT "no auth required"**: the spec tracks `owner`/permissions and returns `403 "user does not have … permission"`, and `[REPO]` shows `/domo/…` under a raw SID returns an **HTML login page** (`appdb-cleanup.md`).

**Guard:** do not hard-code "dev-token only" for World A, and do not describe World B as "no auth."

---

## 4. The envelope-vs-content model

One document = a **system-assigned envelope** + an **app-writable `content`** object. **The app writes only `content`.** `[DOC]`

World-A v2 envelope: `{id, datastoreId, collectionId, syncRequired, owner, createdBy, createdOn, updatedOn, updatedBy}` + `content`. This is **NOT a closed 9-field set** `[INFER]`: the schema sets no top-level `additionalProperties:false` and no `required` array; `content` is the 10th property; and **World-A v1 returns a STRIPPED envelope** (omits `createdBy`; `owner`/`updatedBy` are numeric integers, not strings).

- `syncRequired`/`syncEnabled`/`fullReplaceRequired`/`cdcEnabled` are **envelope/system fields**, not content. `cdcEnabled` appears only on the **World-B** Collection schema; the **Datastore** schema exists only in **World A**. `[DOC]`
- `syncEnabled` → materializes top-level `content` keys into the linked DataSet via `datasourceId`. **Only top-level content keys map to columns** — column names must be top-level keys of the document's `content` object; **dot notation does NOT traverse nested objects during sync**. To include a nested object, use its top-level key name — the synced value is the **JSON-string representation** of that object (one top-level key = one column). `[DOC]`
- **`[REPO]` exceptions to "write only content":** the `actor` field is a CE-verified value written **into** `content`; standard-sync writes time columns into `content` intentionally. See `reference-domo-appdb-document-envelope`. Because envelope `createdBy`/`updatedBy` can be a CE service identity (and v1 strips/int-types them), the actor-into-content audit rule is owned by `domo-code-engine.md`.

---

## 5. Schemas — Collection & Datastore

**Collection schema** `[DOC]`:
- The canonical field is **`schema`**; legacy **`schemaJson`** is also accepted on Collection update (Product spec only).
- Column-type enum = **`STRING | LONG | DECIMAL | DOUBLE | DATE | DATETIME`**. `NUMBER`/`INTEGER` are the common mistake — **not valid**.
- `syncEnabled` + `datasourceId` = the join point to the linked DataSet (see §7). `cdcEnabled` is **World-B only**.

**Datastore schema** `[DOC]`: **World-A only** — World B has one auto-created datastore and no datastore schema/CRUD.

**Do NOT** re-own or tag `[DOC]` the standard-sync DataSet **name** `{collectionName}_{datastoreName}_APP_DB` — that string is in **neither** spec (zero hits); it stays `[KB]`/`domo-datasets.md`. What IS `[DOC]`: the `datasourceId` link, top-level-content-only sync, and the column-type enum.

---

## 6. Document operations

Both worlds share the same document verb set (World A under `/api/datastores/v2/collections/{collectionId}/…`, World B under `/domo/datastores/v{1,2}/collections/{collectionName}/…`):

- **Create** `POST …/documents` (single); **Get** `GET …/documents/{documentId}`; **List** `GET …/documents` (limit/offset); **Delete** `DELETE …/documents/{documentId}`.
- **Replace** `PUT …/documents/{documentId}` = **FULL replace** of `content`.
- **Partial update** `PUT …/documents/update` = MongoDB-style `{query, operation}`; returns an **integer count**; **0-match = success**; performs **NO upsert**. Do not conflate with Replace. **Supported update operators (closed whitelist):** `currentDate, inc, min, max, mul, rename, set, unset, addToSet, pop, pull, pullAll, push`; **`$setOnInsert` has no effect** because AppDB partial updates do not upsert. (This is the update-**operator** allow-list — distinct from the `documents/query` **filter** blacklist below.) `[DOC]`
- **Query** `POST …/documents/query` = a **raw MongoDB-style filter object** — **open** (`additionalProperties:true`), delegating to the external MongoDB predicate grammar **minus a 3-operator blacklist (`$where`/`$near`/`$nearSphere` unsupported)**; pagination/aggregation (groupby/count/avg/min/max/sum/unwind/orderby/limit/offset) are query-string params. **NOT a closed grammar.** The `{query,operation}` wrapper belongs to partial-update, **not** to `/query`. `[DOC]`
- **Bulk create** `POST …/documents/bulk` → `{Created}`; **Bulk upsert** `PUT …/documents/bulk` = match on `id` else create → `{Updated, Created}`; **Bulk delete** `DELETE …/documents/bulk?ids=…` (see §13 for URL caps). **Each document in a bulk request is capped at 2 MB** — the spec states this per-document ceiling on the bulk add/create + bulk upsert ops in both worlds. `[DOC]`
- **Import** (World A v2 only) `PUT …/documents/import` = **upsert-by-id preserving `id`/`createdOn`/`owner`**; documents **not** in the payload are **left untouched** — it does **NOT** wipe the collection. Restore counterpart to `download` (§7). `[DOC]`

## 7. export / download / import — the false-friend resolution

Three similarly-named ops do **three unrelated things.** Getting this wrong is the highest-consequence AppDB mistake (a caller expecting `export` to hand back documents gets an empty 200; a caller expecting `import` to be a fresh load silently upserts).

| Op | What it actually does | Egress? |
|---|---|---|
| **`POST /api/datastores/v{1,2}/export/{datastoreId}`** (World A) / **`POST /domo/datastores/v1/export`** (World B) | **Sync trigger** — recomputes the linked DataSet(s) from current documents. Returns an **empty 200 body** (v2 optional body = shared-collection UUIDs; World-B `includeRelatedCollections` query param; World B may return **`423 LOCKED`** if a sync is already in progress). **This is NOT "export the documents."** `[DOC]` | **No** |
| **`GET /api/datastores/v2/collections/{collectionId}/download`** (World A only) | **The one real READ egress** — streams matching documents as a JSON attachment. **HARD cap ≤100 documents, silently truncated** (no error, no next-page token beyond the cap). `[DOC]` | **Yes (≤100)** |
| **`PUT /api/datastores/v2/collections/{collectionId}/documents/import`** (World A only) | **Restore** — upsert-by-`id` preserving `id`/`createdOn`/`owner`; documents absent from the payload are **left untouched** (does NOT wipe). Counterpart to `download`. `[DOC]` | No (write) |

`export`(=Sync) is the standard-sync trigger `domo-datasets.md`/`appdb-cleanup.md` care about; `download`(=egress READ) is the data-out path `domo-export-to-s3.md` + `domo-query-dataset.md` should **defer here** rather than re-owning. Bulk read of a whole large collection is **not** a documented single call — `download` caps at 100 and `documents/query` paginates; there is no attested "dump everything" op `[INFER]`.

---

## 8. Collections & Datastore management

- **Datastore CRUD (World A only)** `[DOC]`: `POST /api/datastores/v1` (create), `GET /api/datastores/v1` (list), `GET .../v1/{datastoreId}` (get), `DELETE .../v1/{datastoreId}` (**cascade delete of all collections + documents, "cannot be undone"** — see §13). World B has **no** datastore CRUD (one implicit datastore).
- **Collection CRUD (both worlds)** `[DOC]`: create / list / get / update / delete. Update can **rename**, change **schema** (`schema`; legacy `schemaJson` on World A), and toggle **`syncEnabled`**.
- **Query Collections (World A)** `POST /api/datastores/v1/collections/query` `[DOC]` — `filterType` one of `datastorename | ownedby | createddate | nameof`. (Distinct from `documents/query`, which filters documents inside one collection.)
- **World-B rename routing trap** `[DOC]`: after a World-B collection rename, routing is **still by the ORIGINAL manifest name** (`collectionsMapping`) — a `PUT /domo/datastores/v1/collections/{collectionName}` uses the manifest name, not the new display name. Do not assume the new name routes.

---

## 9. Permission model (World A `[DOC]`)

`PUT /api/datastores/v1/collections/{collectionId}/permission/{entity}/{entityId}` grants/updates; `DELETE …` revokes (**idempotent**); `GET .../permission` lists; `GET .../permission/user` returns a boolean check.

- **`entity` enum = `USER | GROUP | RYUU_APP`** — `RYUU_APP` grants a *design/app* (not a person/group) access; this is the mechanism a published app uses its own collection. `[DOC]`
- **`READ` is always included** — you cannot grant a permission set that omits READ. `[DOC]`
- **Permission tokens `[DOC]`:** the per-grant `permissions` array draws from a closed **lowercase** set — `admin, write, read, share, delete, create_content, update_content, read_content, delete_content`. The Collection-create **`defaultPermissions`** field takes the same set **uppercased** (`ADMIN, SHARE, DELETE, WRITE, READ, CREATE_CONTENT, READ_CONTENT, UPDATE_CONTENT, DELETE_CONTENT`), **always appends `READ`** even if omitted, and when null/blank defaults to `READ,CREATE_CONTENT,READ_CONTENT,UPDATE_CONTENT,DELETE_CONTENT`. (The "always-append + default-list" behavior is scoped to `defaultPermissions`, not the per-grant array.)
- Grant body carries an **overwrite mode** (merge vs replace); pick deliberately — replace drops existing grants. `[DOC]`
- **World-B permission ops** `[DOC]`: `PUT/DELETE /domo/datastores/v1/collections/{collectionName}/permission/{entity}/{entityId}` — the spec warns **"removing all permissions leaves only Manage-AppDB grantees"** with access. World B has **no** list/check-permission ops.

---

## 10. Versioning & deprecation

- **Exactly 8 World-A ops carry `deprecated:true`** — the entire v1 **documents** family (List, Create, Get, Update, Delete, Bulk-Delete, Partial-Update) **plus `POST /api/datastores/v1/export`**. `[DOC]`
- **Do NOT generalize to "all v1 is deprecated."** v1 **collections**, **datastore**, **permission**, and **collections/query** ops are v1 and are **NOT** flagged deprecated. `[DOC]`
- **World-B versions:** documents exist at both v1 and v2 and **neither is deprecated**; `documents/query` is `x-excluded` at v1, active at v2. Collections/export/permission live at v1 only. `[DOC]`
- Current best practice = **World-A v2** for documents (query/bulk/import/download all v2-only). `[INFER]` from the deprecation flags — not a stated migration mandate.

---

## 11. Response codes & errors

Observed across both specs `[DOC]`: `200`, `201`, `202` (async accepts — bulk delete returns `202 {Deleted}`), `204`, `400`, `403` ("user does not have … permission"), `404`, plus **World-B `423 LOCKED`** (sync already in progress).

**This set is NOT exhaustive `[INFER]`:** neither spec declares `401`, `429`, or any `5xx`, and there is **no `default:` response** — real callers will encounter auth-expiry / rate-limit / server errors the spec does not enumerate. Do not present the documented codes as the complete error contract.

## 12. Full operation inventory

### World A — Product REST (`/api/datastores/…`), 35 ops `[DOC]`

| # | Method + path | Op | Destructive |
|---|---|---|---|
| 1 | `POST /api/datastores/v1` | Create Datastore | — |
| 2 | `GET /api/datastores/v1` | List Datastores | — |
| 3 | `GET /api/datastores/v1/{datastoreId}` | Get Datastore | — |
| 4 | `DELETE /api/datastores/v1/{datastoreId}` | Delete Datastore | **Y** (cascade: all collections + documents; "cannot be undone") |
| 5 | `POST /api/datastores/v1/collections` | Create Collection | — |
| 6 | `GET /api/datastores/v1/collections` | List Collections | — |
| 7 | `POST /api/datastores/v1/collections/query` | Query Collections (`filterType` datastorename\|ownedby\|createddate\|nameof) | — |
| 8 | `GET /api/datastores/v1/collections/{collectionId}` | Get Collection | — |
| 9 | `PUT /api/datastores/v1/collections/{collectionId}` | Update Collection (rename/schema/syncEnabled; `schemaJson` legacy accepted) | — |
| 10 | `DELETE /api/datastores/v1/collections/{collectionId}` | Delete Collection | **Y** (cascade: all documents) |
| 11 | `PUT …/v1/collections/{collectionId}/permission/{entity}/{entityId}` | Grant/Update Permissions (entity USER\|GROUP\|RYUU_APP; merge/replace; READ always included) | — |
| 12 | `DELETE …/v1/collections/{collectionId}/permission/{entity}/{entityId}` | Revoke Permissions (idempotent) | — |
| 13 | `GET …/v1/collections/{collectionId}/permission` | List Permissions | — |
| 14 | `GET …/v1/collections/{collectionId}/permission/user` | Check User Permission (boolean) | — |
| 15 | `POST /api/datastores/v1/export/{datastoreId}` | Sync Datastore (**DEPRECATED**; sync trigger, NOT egress) | — |
| 16 | `POST /api/datastores/v2/export/{datastoreId}` | Sync Datastore (empty 200; optional body = shared-collection UUIDs) | — |
| 17–23 | `…/v1/collections/{collectionId}/documents…` | **v1 documents family — all DEPRECATED**: List (stripped envelope), Create, Get, Update, Delete (**Y**), Bulk Delete `?ids=` (**Y**), Partial Update `documents/update` | Delete + Bulk-Delete **Y** |
| 24–33 | `…/v2/collections/{collectionId}/documents…` | **v2 documents family (current)**: Query `POST …/query` (raw MongoDB filter), List, Create, Get, Replace `PUT …/{id}` (FULL replace), Delete (**Y**), Bulk Create `POST …/bulk` → {Created}, Bulk Upsert `PUT …/bulk` → {Updated,Created}, Bulk Delete `DELETE …/bulk?ids=` → 202 {Deleted} (**Y**), Partial Update `PUT …/update` ({query,operation}, integer count, 0-match=success, no upsert) | Delete + Bulk-Delete **Y** |
| 34 | `GET /api/datastores/v2/collections/{collectionId}/download` | Download Documents (JSON attachment, **HARD ≤100, silent truncation** — the only egress READ) | — |
| 35 | `PUT /api/datastores/v2/collections/{collectionId}/documents/import` | Import Documents (upsert-by-id preserving id/createdOn/owner; absent docs untouched) | — |

### World B — App-Framework in-app (`/domo/datastores/…`), 27 ops `[DOC]`

Compressed by verb family (`v{1+v2}` = present at BOTH v1 and v2, neither deprecated):

| Method + path | Op | Notes |
|---|---|---|
| `GET\|POST\|GET\|PUT\|DELETE /domo/datastores/v{1+v2}/collections/{collectionName}/documents(+/{documentId})` | List / Create / Get / Update(v1)\|Replace(v2) / Delete | DELETE = **Y** |
| `POST …/documents/query` | Query Documents (MongoDB; **v1 `x-excluded`, v2 active**) | open filter |
| `PUT …/documents/update` | Partial Update | {query,operation} |
| `POST …/documents/bulk` / `PUT …/documents/bulk` / `DELETE …/documents/bulk?ids=` | Bulk Create / Bulk Upsert / Bulk Delete | Bulk-Delete `<Danger>` "cannot be reversed" (**Y**); ~700 UUID / ~26KB URL cap |
| `POST /domo/datastores/v1/collections` | Create Collection | v1 only |
| `GET /domo/datastores/v1/collections` | List Collections | v1 only |
| `PUT /domo/datastores/v1/collections/{collectionName}` | Update Collection | routes by ORIGINAL manifest name after rename |
| `DELETE /domo/datastores/v1/collections/{collectionName}` | Delete Collection | `<Danger>`, cascade (**Y**) |
| `POST /domo/datastores/v1/export` | Sync Collections | 200, or **423 LOCKED** if in progress; `includeRelatedCollections` query param |
| `PUT …/v1/collections/{collectionName}/permission/{entity}/{entityId}` | Modify Permissions | — |
| `DELETE …/v1/collections/{collectionName}/permission/{entity}/{entityId}` | Delete Permissions | "removing all leaves only Manage-AppDB grantees" |

World B has **no** datastore CRUD, **no** download, **no** import, **no** list/check-permission, **no** collections/query.

---

## 13. Destructive ops & the human-gate

These AppDB ops are **irreversible** and are **NOT autonomous-loop-eligible** — they gate on **explicit human intent** (mirrors the `domo-managing-dataset-history.md` DELETE precedent and the `appdb-cleanup.md` prune gate):

- **`DELETE /api/datastores/v1/{datastoreId}`** — cascades to **every collection + document** in the datastore; spec says "cannot be undone."
- **`DELETE …/collections/{collectionId}`** (both worlds) — cascades to **all documents**; World B tags it `<Danger>`.
- **`DELETE …/documents/{documentId}`** and **`DELETE …/documents/bulk`** (both worlds) — permanent. World-A v2 bulk delete: `?ids=` **comma-separated, ~800-UUID URL cap**, returns `202 {Deleted}`. World-B bulk delete: `?ids=` query param, **~700-UUID / ~26KB cap**, `<Danger>` "cannot be reversed."

**Do NOT hard-code any `datastoreId`/`collectionId` for a delete** (the same lesson as the dataset-history DELETE-body-integer footgun). `import` and `bulk-upsert` are **non**-destructive (upsert, do not wipe) — but `Replace` (`PUT …/{id}`) fully overwrites one document's `content`, so it is lossy per-document.

---

## 14. Naming-trap table

| Looks like | Actually is | Owner |
|---|---|---|
| `export` | **Sync trigger** (recompute linked DataSet), empty 200 — NOT document egress | this skill / `appdb-cleanup.md` |
| `download` | The **only** document **egress** READ (≤100, silent truncation) | this skill (defer here from export-to-s3 / query-dataset) |
| `import` | **Restore** = upsert-by-id, absent docs untouched — NOT a fresh load/wipe | this skill |
| `documents/query` | Filter **documents in one collection** (raw MongoDB, open) | this skill (align w/ `domo-search.md`) |
| `collections/query` | Find **collections** by `filterType` (World A) | this skill |
| `{query,operation}` | **Partial-update** wrapper — NOT the `/query` body | this skill |
| `api/content/v1/datastores` | Tokenless **CE proxy** — NOT World A `/api/datastores` nor World B `/domo/datastores` | `domo-code-engine.md` |
| `{collectionName}_{datastoreName}_APP_DB` | Standard-sync **DataSet name** (Domo-managed, API-rename-locked) — in NEITHER spec | `domo-datasets.md` `[KB]` |

---

## 15. Ownership map & cross-references

**This skill OWNS** (per the rank-26 workflow `ownership_recommendation`): two-world contract, envelope-vs-content, Collection/Datastore schemas, document CRUD/bulk/query, export/download/import resolution, permission model, versioning/deprecation, response-code shape, destructive human-gate.

**Repoint existing defers here:**
- `domo-export-to-s3.md` + `domo-query-dataset.md` — the AppDB document-egress path is `GET …/download` (≤100), documented in §7 here; defer to this skill rather than re-owning.

**This skill DEFERS (cross-ref only — do NOT edit those peer files from this lane):**
- Recurring document-**PRUNE** workflow + `../scripts/appdb-prune-latest.py` → **`appdb-cleanup.md`**.
- Tokenless CE client (`api/content/v1/datastores`) + the actor-into-content audit rule (`reference-domo-appdb-document-envelope`, `reference-domo-codeengine-*`) → **`domo-code-engine.md`**.
- Standard-sync DataSet name-lock (`{…}_APP_DB`) + DataSet lifecycle/history → **`domo-datasets.md`** (+ `domo-managing-dataset-history.md`), `[KB]`.
- `documents/query` naming-trap alignment → **`domo-search.md`**.

---

## 16. DO-NOT — over-claim guards (verbatim from the refute pass; the 7 REFUTED claims)

1. Do **NOT** call the two specs byte-identical or "mirrors" — different SHA-256 (`0816d52c…` product vs `fcf3d3b1…` framework), different op counts (35 vs 27), disjoint bases, UUID-vs-name keys. `[DOC]`
2. Do **NOT** state World A is "dev-token-only" — SID and tokenless CE reach the same v2 paths (`appdb-prune-latest.py`; CE relative-path). Dev-token is one documented scheme, not the only auth. `[REPO]`
3. Do **NOT** describe World B as "no auth" — it is `[INFER]`/`[KB]` injected browser-session identity (spec names no JWT/bearer); owner/permission machinery + `403` + SID→HTML-login prove auth is enforced. `[REPO]`/`[INFER]`
4. Do **NOT** call `export` an egress/document-dump — it is a **Sync trigger** (empty 200). `download`=≤100 egress; `import`=restore. `[DOC]`
5. Do **NOT** generalize "v1 is deprecated" — exactly **8** World-A ops carry `deprecated:true` (the v1 documents family + `v1/export`); v1 collections/datastore/permission/collections-query are NOT deprecated. `[DOC]`
6. Do **NOT** present the envelope as a closed 9-field set — no `additionalProperties:false`, no `required`; `content` is a 10th property; World-A v1 returns a **stripped** envelope (omits `createdBy`; `owner`/`updatedBy` numeric ints). `[INFER]`
7. Do **NOT** treat `documents/query` as a closed grammar — it is open MongoDB (`additionalProperties:true`) minus the `$where`/`$near`/`$nearSphere` blacklist; the `{query,operation}` wrapper is **partial-update**, not `/query`. `[DOC]`
8. Do **NOT** claim `import`/bulk-upsert wipe the collection — both upsert; absent docs untouched. `[DOC]`
9. Do **NOT** state World-B absences (no download/import/datastore-CRUD) as proven — they are `[INFER]` from the fetched spec (fetch-limited). `[INFER]`
10. Do **NOT** conflate the three `datastores` prefixes — `/api/datastores` (World A) vs `/domo/datastores` (World B) vs `api/content/v1/datastores` (CE proxy). `[REPO]`
11. Do **NOT** re-own or tag `[DOC]` the `{collectionName}_{datastoreName}_APP_DB` DataSet name — `[KB]`/`domo-datasets.md`; and the column-type enum is `STRING|LONG|DECIMAL|DOUBLE|DATE|DATETIME` — **`NUMBER`/`INTEGER` are the common mistake**. `[DOC]`/`[KB]`
12. Do **NOT** claim this is the complete AppDB surface — it is the two fetched first-party specs + repo facts; other internal endpoints may exist. `[INFER]`
13. Do **NOT** present the response codes (200/201/202/204/400/403/404 + World-B 423) as exhaustive — no 401/429/5xx, no `default:` declared. `[INFER]`
14. Do **NOT** cross-apply world-scoped fields — `cdcEnabled` is **World-B Collection only**; the Datastore schema is **World-A only**. `[DOC]`
