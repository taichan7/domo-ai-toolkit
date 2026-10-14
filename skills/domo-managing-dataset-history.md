# Domo Managing Dataset History

Operating notes for the **Domo "Managing Dataset History API"** — a tiny 2-operation surface that lists a DataSet's stored **data versions** (`GET`) and **destructively, irreversibly prunes** specific versions (`DELETE`). Read this before touching any `/api/data/v2/datasources/{datasetId}/dataversions` call, or any code mentioning `DataVersion`, `dataversions`, `DataVersionDeleteRequest`, `uploadStatus`, `schemaId`/`dataId`, `numRows`/`numBytes`, `recordedDate`/`uploadCompletedDate`, or the delete-time `index=true` (Adrenaline purge) parameter. The `DELETE` **"is a destructive operation and cannot be undone"** — treat every invocation as HIGH-SENSITIVITY (see Safety & hygiene).

## What this skill owns (and defers)

- **Owns**: the REST **Managing Dataset History API** surface — the first-party spec artifact `managing-dataset-history-api.yaml` (info.title "Managing Dataset History API", info.version 1.0.0), host `https://{instance}.domo.com`, auth `X-DOMO-Developer-Token`, the single path `/api/data/v2/datasources/{datasetId}/dataversions` with its 2 ops (GET Listing Dataset Versions, DELETE Deleting Dataset Versions), and the `DataVersionList` / `DataVersion` / `DataVersionDeleteRequest` schemas.
- **Defers**: **version CREATION** — this API never creates versions; new data versions are minted by the **v3 Upload API** (`POST /api/data/v3/datasources/{id}/uploads` → PUT parts → PUT commit → POST `/indexes`) and the **v1 Stream API** (`POST /api/data/v1/streams/...` → executions → part → commit) → `domo-datasets.md`. **Whole-dataset delete** (`DELETE /api/data/v3/datasources/{id}`, NO body — a FALSE FRIEND, see traps) and dataset **list / metadata / schema** (`/api/data/v3/datasources`) → `domo-datasets.md`. **Files API** (`/api/data/v1/data-files`, rank-18) → `domo-files.md`. **AppDB** (`/api/datastores/...`, a DIFFERENT service root) → its own skill. **Adrenaline indexing** (`POST /api/data/v3/datasources/{id}/indexes`) and **partition-tag delete** (`DELETE /api/query/v1/datasources/{id}/tag/{id}/data`) are ADJACENT "data version" ops on OTHER paths (see naming traps), not this surface.

## Evidence tiers

Every claim below carries a tier. Do not silently upgrade a tier.

```
[DOC]  = developer.domo.com page / OpenAPI YAML under domo.com/docs/openapi / dev-portal API-Reference page / first-party SDK.
         (A domo-support.domo.com/s/article/<digits> = Salesforce KB = [KB], NOT [DOC].)
[KB]   = Domo Knowledge Base article / documented product behavior.
[REPO] = verified against this repo's actually-running code (a real caller, not dead scaffolding).
[INFER]= reasoned / inference-from-absence / spec-author-assumed.
```

Rules: a fetch FAILURE (405 / JS-gated / login-wall / 404 / timeout) is MISSING evidence, NOT proof of absence. Universal negatives ("no other ops exist", "the enum is closed", "SID is rejected") are `[INFER]` unless a doc positively says so. Prefer positive phrasing. The single guarded failure mode is **over-claiming** — presenting a spec quirk or an unverified assumption (the DELETE-body id-type, enum closedness, error codes, `index` semantics, auth exclusivity) as documented Domo fact.

Claim-level tier census for this skill: **`[DOC]` 22 / `[KB]` 4 / `[REPO]` 7 (all "none / false-friend") / `[INFER]` 13.** Distinctively for this cycle this is the **best-documented island so far**: the candidate is byte-identical to Domo's published product YAML AND rendered on two consistent first-party HTML pages, so base path, both ops, all 7 GET fields, the enum values, auth, and host are all `[DOC]`-confirmed. The residual `[INFER]` concentrates on the **DELETE-body identifier**, the error surface, enum closedness, and paging completeness.

## Verification provenance

Verified before authoring via the Workflow tool, run `wf_73f82001-cb0` (**15 agents, all 15 succeeded / 0 errored**, ~1.29M tokens): 5 spec-reading cross-check clusters (ops/paths/shape, doc-corroboration+mirror-pair, auth/host/base-path/error-codes, schemas/quirks/delete-semantics, semantics/traps/repo-precedent) → adversarial refutation of the 9 highest over-claim-risk claims (each default-refuted-if-uncertain) → a synthesizer/island-verdict. Primary sources: the raw candidate YAML (`/tmp/cand-managing-dataset-history-api.yaml`, 135 lines, read line-by-line); **Domo's published product spec `www.domo.com/docs/openapi/product/managing-dataset-history-api.yaml`** (the candidate is **byte-identical** to it, 4726 bytes, SHA-256 `31f5d47a…796dd402` — a first-party `[DOC]` artifact, live-diffed to ZERO lines); and the **two live dev-portal HTML reference pages** (`.../docs/api-reference/managing-dataset-history-api/{listing,deleting}-dataset-versions`, both HTTP 200, both citing that same YAML as source). **No HTTP request was executed against the live surface — DOCUMENTATION-ONLY; the DELETE is destructive, so zero calls were made.**

The nine returned adversarial verdicts (**3 REFUTED, 4 PARTIAL, 2 CONFIRMED** — all folded into the Do-NOT list below). The two CONFIRMED are the base path and the single-world/byte-identical-mirror characterization:

| # | claim | verdict | encoded as |
|---|---|---|---|
| 1 | `X-DOMO-Developer-Token` is the definitive/ONLY auth (no SID) | **PARTIAL → [DOC/INFER]** | dev-token IS the documented auth `[DOC]`; exclusivity is an unsupported universal negative + family precedent leans toward SID also working → claim NEITHER (Do-NOT #5) |
| 2 | `uploadStatus` is a CLOSED enum `[success,error,processing]` | **PARTIAL → [DOC/INFER]** | the 3 values are documented (enum keyword + prose) `[DOC]`; closedness rests on one source + 0 GETs → `[INFER]` (Do-NOT #2) |
| 3 | the DELETE-body integers ARE `dataId` (identity documented) | **REFUTED → [INFER]** | identity is UNSPECIFIED (both pages decline to map it); example `[2]` matches neither GET `dataId`(3,4) nor `schemaId`(5,7) → do NOT hard-code (Do-NOT #1) |
| 4 | `index=true` purge is guaranteed + omission on active data is safe | **REFUTED → [DOC/INFER]** | the `index=true` EFFECT is `[DOC]`; the omission outcome is explicitly undocumented + leans UNSAFE `[INFER]` (Do-NOT #3) |
| 5 | base path is authoritative + no Export/Files/query collision | **CONFIRMED → [DOC]** | 3 independent first-party renderings agree; siblings share only the `/api/data/` ROOT, ZERO literal collision |
| 6 | `{GET,DELETE}` is exhaustive for dataset-version HISTORY | **PARTIAL → [DOC/INFER]** | exhaustive ON THIS EXACT PATH `[DOC]`; "for the history domain" is `[INFER]` (create/hydrate/detail ops live on OTHER paths) |
| 7 | GET returns ALL versions, no truncation | **PARTIAL → [DOC/INFER]** | "no paging params, bare array" is `[DOC]`; "returns ALL / no server cap" is `[INFER]` (sources decline the assurance) |
| 8 | single-world, NO divergent mirror (unlike rank-20) | **CONFIRMED → [DOC]** | byte-identical convergent mirror; the absolute "exists nowhere" fringe stays `[INFER]` (legacy Stoplight 405) |
| 9 | the response set is fully documented (only 200, nothing to hedge) | **REFUTED → [DOC/INFER]** | "only 200 documented" is `[DOC]`; that ≠ "no failures" — the 4xx/5xx surface is UNCHARTED `[INFER]`, hedging HEIGHTENED for the destructive DELETE (Do-NOT #7) |

鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).

## Naming traps (read first)

Conflation is the #1 hazard: `/api/data/` is a heavily-shared root spanning versions AND resources, and "data version" is overloaded across at least three id schemes.

| you see | reality |
|---|---|
| this DELETE **and** `DELETE /api/data/v3/datasources/{id}` | **DIFFERENT operations.** This prunes specific VERSIONS while keeping the dataset (`v2`, `/dataversions` suffix, REQUIRED array body); the v3 one deletes the **WHOLE dataset** (NO body). Same `datasources/{id}` base — distinguished only by the `/dataversions` suffix, the v2-vs-v3 version, and the body. The sharpest false friend. `[REPO]` |
| `/api/data/` belongs to one API | **Shared across VERSIONS + resources**: v1 (Files `data-files` rank-18; Stream `streams`; `lineage`), v2 (this API's `{id}/dataversions` AND the DataSets API "Create Dataset Copy" `POST /api/data/v2/datasources`), v3 (`datasources` metadata/list/schema/uploads/indexes). **ZERO literal path collision** — method+full-path templates all differ. `[DOC/REPO]` |
| `datasources` should be normalized to one version | It is **versioned PER-OPERATION**: the same resource lives at v2 (copy, dataversions) AND v3 (metadata, list, schema). Do NOT rewrite `/api/data/v2/.../dataversions` to v3. `[DOC]` |
| the DELETE-body integer is a `dataId` | **UNSPECIFIED.** The body is a bare `array<integer>` labelled only "List of data versions"; neither the spec nor the live pages map it to `dataId`, `schemaId`, or an ordinal. `dataId` is a plausible `[INFER]` (via the adjacent `/indexes` `{dataIds}` = "data version IDs"), but a THIRD sibling IDs versions by `dataset_partition_id` — Domo uses ≥2 id schemes. Verify live. `[INFER]` |
| "data version" means one thing | **Overloaded** into ≥3 id schemes: `dataId` (the `/api/data/v3/.../indexes` `{dataIds}` body), `schemaId` (per-version schema snapshot — can repeat across uploads), `dataset_partition_id` (the `/api/query/v1/.../tag/{id}/data` delete). Never assume the DELETE body maps to one. `[DOC]` |
| Vault and Adrenaline are synonyms | **Two tiers.** Vault = durable STORAGE (Magic ETL `LoadFromVault`/`PublishToVault` `[REPO]`); Adrenaline = the active hot columnar QUERY/INDEX engine (dataset `cryoStatus` ADRENALINE=active vs CRYO=archived `[KB]`). Plain DELETE removes from Vault; `index=true` ADDITIONALLY purges Adrenaline. `[DOC]` |
| `index` is one concept | Overloaded: the DELETE query param `index=true` (Adrenaline PURGE) vs the upload flow's `POST /api/data/v3/.../indexes` with `{index:true}` (Adrenaline INDEXING toggle after a commit `{index:false}`) — parallel semantics, DIFFERENT calls. Don't cross-wire them. `[REPO]` |
| info.version `1.0.0` is the API path version | It is the **SPEC document's version**; the callable path version is **v2** (in `/api/data/v2/`). Do not confuse or "upgrade" it. `[DOC]` |
| top-level tag "Dataset History" | The top-level `tags:[{name:'Dataset History'}]` is **never used**; both ops self-tag `[Managing Dataset History API]`, matching the live doc slug. Cosmetic first-party spec quirk (present in the byte-identical published YAML, so genuine — not a transcription artifact), no runtime meaning — don't treat either string as an API contract. `[DOC]` |
| header `X-DOMO-Developer-Token` vs prose "access token" | Same credential. The "Developer"-vs-"access token" split is benign boilerplate reused across Domo dev-portal specs (same as the federated skill), not two different tokens. `[KB]` |

## The surface, in one line

A **single-world small island** (1 path `/api/data/v2/datasources/{datasetId}/dataversions`, 2 ops, 1 host `{instance}.domo.com`, 1 auth `X-DOMO-Developer-Token`) that is distinctively the **best-documented rank of this cycle**: a **byte-identical CONVERGENT (non-divergent) first-party MIRROR** — the candidate is SHA-256-identical to Domo's published `product/managing-dataset-history-api.yaml` and is ALSO rendered as two consistent HTML dev-portal pages citing that same YAML (one source, three renderings, zero contest). So base path, both ops, all 7 GET fields, the enum values, auth, and host are all `[DOC]`-confirmed (auth is RESOLVED, base path AUTHORITATIVE — unlike the reverse-engineered rank-18 Files / rank-19 Remote-DomoStats islands). **This is the EXACT OPPOSITE of the rank-20 Export divergent mirror-pair** (whose second spec contested auth/host/enum/body) and STRONGER than the rank-13 Projects mirror (equivalent, not byte-identical). Functionally it is a **read-then-destructively-prune** surface whose defining hazard is the irreversible DELETE + its ambiguous version identifier. Zero-caller-in-repo → all RUNTIME behavior is `[DOC]`/`[INFER]`-never-`[REPO]`, 0 executed calls.

## Operations (1 path, 2 ops — both `[DOC]`, exhaustiveness CONFIRMED on-path)

| # | op | method + path | request | 200 body | error codes |
|---|---|---|---|---|---|
| 1 | Listing Dataset Versions | `GET /api/data/v2/datasources/{datasetId}/dataversions` | path param `datasetId`; NO query params, NO body, NO paging | a **BARE ARRAY** `DataVersionList` = `array<DataVersion>` | only `200` documented |
| 2 | Deleting Dataset Versions | `DELETE /api/data/v2/datasources/{datasetId}/dataversions` | path param `datasetId`; optional query `index` (bool); **REQUIRED body** `array<integer>` (`DataVersionDeleteRequest`, example `[2]`) | **EMPTY** body | only `200` documented |

Base path + the 2-op set are CONFIRMED authoritative/exhaustive **on this exact path** by three first-party renderings `[DOC]` — but that is NOT a metaphysical guarantee that no op exists elsewhere for the version-history *domain* (create/hydrate/detail ops live on OTHER paths → `[INFER]` for section-completeness). The GET→DELETE response-shape contrast is real: **GET returns a bare array, DELETE returns an empty body.** Only `200` is documented for BOTH ops; the 4xx/5xx surface is UNCHARTED (Do-NOT #7).

## Schemas (shapes `[DOC]`; the guards are `[INFER]`)

- **`DataVersionList`** — a top-level **bare array** of `DataVersion` (NOT an envelope/wrapper). GET returns this directly.
- **`DataVersion`** (7 fields, all `[DOC]` from listing-page prose): `schemaId` (int — "the schema associated with the data"; can repeat across versions, the example shows 5 then 7 as the schema evolves), `dataId` (int — **the ONE field with NO prose description**, which is exactly why the delete-key mapping cannot be doc-confirmed as `dataId`), `uploadStatus` (enum `[success, error, processing]` — values `[DOC]`, closedness `[INFER]`), `recordedDate` (date-time — "time the data was made available"), `uploadCompletedDate` (date-time — "time the upload finished"), `numRows` (int), `numBytes` (int).
- **`DataVersionDeleteRequest`** — a bare `array<integer>` labelled only "List of data versions" (example `[2]`). **No `minItems`/`maxItems`** → empty-array behavior undefined `[INFER]`. **The integer's identity (dataId vs schemaId vs ordinal) is UNSPECIFIED** — the *fact that it is unspecified* is `[DOC]` (both live pages decline to map it); any concrete mapping is `[INFER]` (see traps + Do-NOT #1).
- **`index`** query param (DELETE) — optional bool; `index=true` also removes the versions from Adrenaline "as well" `[DOC]`. Default-when-omitted is **unstated** `[INFER]`; the consequence of omitting it on active/indexed data is **explicitly undocumented** and leans unsafe `[INFER]` (Do-NOT #3).

## Auth & host (RESOLVED `[DOC]` — but do not over-close)

Unlike the contested rank-18/19/20 islands, this surface's auth and host are documented and cross-corroborated:

- **Auth**: apiKey header **`X-DOMO-Developer-Token`** (`securityScheme` `DomoDeveloperToken`) — the single declared scheme, confirmed VERBATIM in both live dev-portal curl examples `[DOC]`. It sits in the dev-portal **Product APIs** family (instance dev-token native), NOT the Platform/OAuth (Bearer/`api.domo.com`) or App-Framework (JWT/`/domo/`) families. **Do NOT assert dev-token EXCLUSIVITY** (no doc positively excludes a session SID; instance-world Product-API family precedent — `domo-datasets.md`: dev-token OR SID, SID `[REPO]` on sibling `/api/query/v1/execute` + v3 — LEANS toward SID also working here) **and do NOT assert SID works here** (this exact path has zero callers). Hard-code dev-token; claim neither. `[DOC/INFER]` (verdict 1 PARTIAL)
- **Host / base path**: `https://{instance}.domo.com` + `/api/data/v2/datasources/{datasetId}/dataversions` — confirmed verbatim in the spec server block AND the live curl examples `[DOC]`, AUTHORITATIVE (not a spec guess). Do NOT normalize v2→v3.
- **KB scope**: `info.description` embeds KB `360042934494` = the generic **"Manage Access Tokens"** article `[KB]` (token issuance/revocation only — the same article `domo-federated.md` already tags). It documents NOTHING about dataversions semantics, `index=true`, id-type, or error codes — do NOT cite it as evidence for any endpoint behavior.

## Repo precedent = ZERO

Executed-call count = **0**. No running code in this workspace calls `/api/data/v2/.../dataversions` or references any `DataVersion` field (`schemaId`/`dataId`/`uploadStatus`/`numRows`/`numBytes`/`recordedDate`/`uploadCompletedDate`). False friends: (1) **whole-dataset delete** `DELETE /api/data/v3/datasources/{id}` (no body — inventory / asset-lifecycle `provision_domo.py`, guarded by `cardCount==0`) — the sharpest; (2) **dataset list/query** `GET /api/data/v3/datasources?limit=` (`list-datasets.sh`, `../scripts/appdb-prune-latest.py:247`) — shared root, different version + resource; (3) **version CREATORS** — v3 uploads (`soccer` `formation_save_service.js`, `brokerage_broker.py`) + v1 streams (`equipment-analytics` `provision_domo.py`) mint versions this API observes/prunes; (4) **Files** `/api/data/v1/data-files` (rank-18, `asset-lifecycle` e2e) + **lineage** `/api/data/v1/lineage` — shared `/api/data/` root, different resource; (5) **AppDB** `/api/datastores/v1|v2/...` — a DIFFERENT service ROOT entirely. A 2026-07 marketdata handoff probed `/api/data/v2/datasources/<id>` (view metadata, WITHOUT the `/dataversions` suffix) — a failed exploration note, not a caller. Every op is `[DOC]`/`[INFER]`-never-`[REPO]`.

## Do NOT claim as documented fact

1. Do NOT hard-code the DELETE-body integer as `dataId` (or `schemaId`, or a positional ordinal) — genuinely UNSPECIFIED `[INFER]`; the example `[2]` matches neither GET `dataId`(3,4) nor `schemaId`(5,7). Resolve it by a live probe on a non-prod throwaway dataset before any real delete. (verdict 3 REFUTED)
2. Do NOT call `uploadStatus` a documented CLOSED enum. The three values `[success,error,processing]` are documented `[DOC]` (enum keyword + field prose), but closedness rests on one source (the byte-identical YAML + its HTML renderings are the SAME source) with zero executed GETs → `[INFER]`; treat unknown status strings defensively. (verdict 2 PARTIAL)
3. Do NOT present `index=true`'s Adrenaline purge as a GUARANTEE, nor claim omitting `index` on active data has a known/safe outcome. The EFFECT is `[DOC]` (but framed as a `required:false` "you should include" recommendation, with only 200 documented); the omission outcome is explicitly undocumented `[INFER]` and leans UNSAFE (Vault version gone, a stale copy may stay queryable in Adrenaline); the default-when-omitted is unstated. (verdict 4 REFUTED)
4. Do NOT claim GET "returns ALL versions with no truncation." "No paging params documented; returns a bare array" is `[DOC]`; both first-party sources explicitly decline any completeness assurance, and absence of `limit`/`offset` is not a no-cap guarantee → unbounded return is `[INFER]`; verify on a large-history dataset. (verdict 7 PARTIAL)
5. Do NOT assert dev-token EXCLUSIVITY, and do NOT assert session-SID works, on this path — both are unsupported for `/dataversions` (dev-token is `[DOC]`; exclusivity + SID-here are `[INFER]`). Hard-coding dev-token for a call is safe; asserting either negative or SID-support is the over-claim. (verdict 1 PARTIAL)
6. Do NOT claim `{GET,DELETE}` is exhaustive for the version-history DOMAIN. It is exhaustive ON THIS EXACT PATH `[DOC]` (closed-document read of a byte-identical YAML); section/domain completeness is inference-from-absence `[INFER]` — version create/hydrate/detail ops demonstrably live on OTHER paths (Stream/Upload APIs, `POST /api/dataprocessing/v2/dataflows/data-version-hydrate`, v3 `/dataversions/details`). (verdict 6 PARTIAL)
7. Do NOT read "only HTTP 200 is documented" as "the response set is fully documented / nothing to hedge." That is the guarded over-claim — the 4xx/5xx surface is UNCHARTED `[INFER]`, not guaranteed-absent: 401 (bad/missing token, `[KB]`-standard), 404 (unknown datasetId, `[REPO]` by v3 sibling analogy), 403 (missing Manage-DataSets privilege), 400 (malformed body) are near-certain but undocumented. Hedging is HEIGHTENED, not eliminated, for the destructive DELETE. (verdict 9 REFUTED)
8. Do NOT trust the empty-200 DELETE response to know WHAT was deleted — atomicity / partial-success on a multi-id array is undocumented `[INFER]`; re-GET the version list to confirm the outcome.
9. Do NOT assert a divergent mirror "exists nowhere" as fact — the single-world / byte-identical-mirror characterization is `[DOC]`, but the legacy `developer.domo.com` Stoplight portal returned 405 (missing evidence, not proof of absence), so scope the claim to the CURRENT published YAML + HTML. (verdict 8 CONFIRMED, fringe `[INFER]`)
10. Do NOT normalize/rewrite the v2 path to v3, conflate this DELETE with whole-dataset delete (v3, no body) or with Files / AppDB / lineage false friends, cite KB `360042934494` for any endpoint semantics, or tag any part of this surface `[REPO]` (zero executed calls exist).

## Safety & hygiene

**HIGH-SENSITIVITY — gate on explicit human intent; this is NOT eligible for any autonomous / all-automatic loop.**

- **Destructive + irreversible**: the DELETE "is a destructive operation and cannot be undone" `[DOC]` — it removes data versions from Vault permanently. Confirm the human means to delete THESE specific versions of THIS specific dataset, every time.
- **Ambiguous-identifier footgun**: the delete-body integer's meaning is unspecified and the example `[2]` matches neither GET id — a wrong integer permanently deletes the WRONG version. Before any real delete: GET the list, then live-probe the id scheme on a NON-PROD throwaway dataset. Never guess `dataId`.
- **`index=true` / Adrenaline footgun**: omitting `index` when deleting active/indexed data may drop the Vault version while leaving a STALE indexed copy queryable (undocumented, leans unsafe `[INFER]`); `index=true` purges the query engine "as well" `[DOC]`. Decide `index` deliberately — its default-when-omitted is unstated.
- **Uncharted failure surface**: only 200 is documented `[DOC]`; behavior on an invalid/nonexistent id, an unknown datasetId, deleting the sole/active version, an empty-array body, or a partial-batch is `[INFER]`. Probe live on non-prod first; the empty 200 does not confirm which of N versions were removed — re-GET to verify.
- **Blast-radius scoping**: this prunes VERSIONS while keeping the dataset — do not confuse it with whole-dataset delete (v3, no body). Still destructive at the version level; a mis-scoped call can wipe production history that feeds live cards/dataflows.
- **Zero executed calls**: no repo caller has ever exercised this endpoint — every runtime/response-shape/error-code claim is `[DOC]`/`[INFER]`, NEVER `[REPO]`. Any first real use MUST be preceded by a non-prod dry run (GET, then a DELETE on a disposable dataset). Never commit a real dev token / SID / dataset GUID / instance hostname — use `<dataset-id>` / `<instance>.domo.com` placeholders.

## Companion skills

`domo-datasets.md` (the DataSet whose versions these are; version CREATION via the v3 Upload / v1 Stream APIs; whole-dataset delete + list/metadata/schema at v3; the dev-token-OR-SID family auth) · `domo-files.md` (`/api/data/v1/data-files`, the rank-18 shared-`/api/data/`-root false friend) · `domo-magic-etl.md` (`LoadFromVault`/`PublishToVault` — the Vault storage tier this DELETE prunes).
