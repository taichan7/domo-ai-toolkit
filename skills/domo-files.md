# Domo Files

Use this skill to reason about — or drive via REST — **Domo's Data File Service** (the "Files API"): uploading a standalone file into a Domo instance, versioning it (revisions), reading its metadata, downloading its bytes, copying/duplicating it, and setting per-user/per-group permissions on it. **Read the naming-trap table below before anything else**: this surface is constantly conflated with the **FileSets API** (a *different* API owned by `domo-filesets.md`), and it exists in **two worlds** (a Product REST world and an App-Framework/Code-Engine world) that document **opposite defaults** for the same operation. Sending a Files-API call to a FileSets path (or vice-versa), or using one world's default in the other, is the classic silent misfire.

Files is a **two-world, multi-operation island** whose defining feature is unusual and must be guarded hard: **the Product OpenAPI spec (`files.yaml` / the candidate `cand-files.yaml`) is self-annotated as reverse-engineered** — it carries 12+ inline confessions of uncertainty (`"Assumed based on similar APIs"`, `# Added based on download logic`, `# Corrected ... based on code example structure`, `# Changed from 'fileName' based on common practice`, `# Assuming empty OK`, `# Assuming GROUP is also possible`). A large fraction of that spec's detail is **spec-author assumption, not documented Domo contract**, and must be tiered `[INFER]` unless the authoritative human-readable dev-portal page independently confirms it. The acute failure mode here is presenting a spec-author *guess* as a documented fact. **Zero calls were executed** against either world; every claim is read from the two dev-portal pages + the two YAMLs, cross-checked and adversarially refuted.

## What this skill owns (and what it defers)

**Owns:** the **Data File Service** = resource **`data-files`** — its two worlds (**Product** base `/api/data/v1/data-files`; **App-Framework/Code-Engine** base `/domo/data-files/v1`), the file/revision/metadata/download/copy/duplicate/permissions operations, and the `FileMetadataSchema` / `FileRevisionSchema` / `FilePermissionsSchema` shapes.

**Defers:**
- **FileSets API** (resource `filesets`, base `/api/files/v1/filesets` and `/domo/files/v1/filesets`) → `domo-filesets.md`. A **completely different** surface for unstructured-document/RAG storage — the #1 false friend (both contain the word "files"). The repo uses FileSets heavily and this Files API almost not at all.
- **The App-Framework SDK request model** (`domo.post/get/put/delete`, tokenless in-app auth) and the Code-Engine `sendRequest` path → `domo-code-engine.md`. World B is *reached through* that model; how the SDK/CE mints and carries auth is owned there.
- **Minting the developer/access token or session id, and the role/grant that gates file operations** → `domo-identity-access.md`.
- **The DataSet import/Stream file-upload path** (`/api/data/v1/streams/...`, `PUT .../uploads/...`) → `domo-datasets.md`. Uploading rows into a DataSet is not the Data File Service.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo-support.domo.com/s/article/<digits> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall / 404) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting a spec self-annotation, an inference-from-absence, or an illustrative `example:` value as a documented contract. Because the Product spec is self-hedged, this skill tiers a claim `[DOC]` **only** when the authoritative dev-portal page (`files-api-product.md`) or the framework page (`files-api-framework.md`) independently confirms it; a fact resting **solely** on the self-annotated YAML is `[INFER]`. Tier census of this skill's claims: **`[DOC]` 33 / `[KB]` 0 / `[REPO]` 7 / `[INFER]` 18** — and **zero `[KB]`**: no Knowledge Base article was consulted, and **no request was ever executed** against either world, so treat all request/response *behavior* (does a bad token 401; what a delete returns; which auth header the product world actually wants; the real GET-permissions path) as **documented-but-untested**.

**Verification provenance.** Written after verification Workflow **`wf_44ea2ea3-ec6`** (13 agents, 0 errors: 5 spec-reading cross-check clusters — ops/paths, doc-corroboration + repo + two-world, upload/download/revision semantics, auth + response-codes + self-annotation census, schemas + permissions — → adversarial refute of the 7 highest over-claim-risk claims, each default-refuted-if-uncertain → synthesizer/island-verdict), cross-read against **four authoritative sources**: the dev-portal **Product** page (`files-api-product.md`, the strongest corroboration), the dev-portal **App-Framework** page (`files-api-framework.md`), and both OpenAPI YAMLs (`cand-files.yaml` product, `files-framework.yaml` framework). **The 7 adversarial verdicts, all folded into the hedge list:**

| claim | verdict | corrected tier |
|---|---|---|
| auth is `X-DOMO-Developer-Token` (documented fact) | **REFUTED** | `[INFER]` — self-hedged "Assumed"; page documents no auth; the one repo caller uses `X-Domo-Authentication` session-id |
| `entityType` enum is *exactly* `[USER, GROUP]` | **PARTIAL** | `[INFER]` — only `USER` attested; `GROUP` token + closedness are spec-assumed |
| uploads default to **public** unless `public=false` | **PARTIAL** | `[DOC]` — **true for Product**, **FALSE for App-Framework** (opposite defaults per world) |
| single-world island (no app-framework world) | **REFUTED** | `[DOC]` — it is **TWO-WORLD**; a standalone authoritative framework page exists |
| download-revision path is `{fileId}/revision/{revisionId}` (singular, `{fileId}`) | **CONFIRMED** | `[DOC]` — a genuine authoritative surface inconsistency, not a YAML artifact |
| `GET /{dataFileId}` downloads current-revision bytes | **CONFIRMED** | `[DOC]` — via the download section's `revisionId`-null branch (but not a *titled* standalone endpoint) |
| 11 paths / 14 ops + `{200,401,404}` is the complete code set | **PARTIAL** | `[INFER]` — count accurate for the Product spec, but only `200` is `[DOC]`; `401`/`404` are spec-author additions |

鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).

## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first.

| You see… | It actually is… | Owner |
|---|---|---|
| **`/api/data/v1/data-files`** or **`/domo/data-files/v1`**, `dataFileId`, `FileMetadataSchema` | the **Data File Service** (this API) | **this skill** |
| **`/api/files/v1/filesets`** or **`/domo/files/v1/filesets`**, `filesetId`, FileSet `upload`/`search`/`query` | the **FileSets API** (unstructured docs / RAG) — a **different** surface | `domo-filesets.md` |
| **`metadataFileId`** / a var named `…dataFileId…` inside a `filesets/.../download` call | a **FileSet** download — the substring `dataFileId` is a **FALSE FRIEND**, not a Files-API call | `domo-filesets.md` |
| **`/api/data/v1/streams/...`**, `PUT .../uploads/...` (upload *rows* into a DataSet) | **DataSet import / Stream API** | `domo-datasets.md` |
| **`X-DOMO-Developer-Token`** on any of the above | the **same header, unrelated surface** — the header does not identify the API | (per-API) |

**Internal traps — all *within* the Data File Service itself:**
- **PRODUCT world (`/api/data/v1/data-files`) vs APP-FRAMEWORK world (`/domo/data-files/v1`).** Same resource, two distinct authoritative pages, **NOT byte-identical mirrors.** They diverge on **base path, auth model, get-all params, delete granularity, upload body, default `public`, and whole op families** (copy/duplicate/get-all-revisions/file-level-delete = **Product-only**; the Multi-part upload family = **Framework-only**). See the two-world section.
- **Download-revision path spelling is a real inconsistency.** The Product download-revision op is `/api/data/v1/data-files/{fileId}/revision/{revisionId}` — param **`{fileId}`** (not `{dataFileId}`) and **`revision` SINGULAR** — while every sibling uses `{dataFileId}/revisions/…` (PLURAL). This is **authoritatively confirmed** (`files-api-product.md` endpoint header + param table), not a YAML typo. **Do NOT "normalize" it** to the plural form. (The Framework world uses PLURAL `/revisions/` for its download — so the singular is Product-specific.)
- **Get-File-Permissions base path contradicts itself inside the one authoritative page.** `files-api-product.md` shows the endpoint header `/domo/data-files/v1/{fileId}/permissions` (a framework-style path) while the same section's code example and `cand-files.yaml` use `/api/data/v1/data-files/{dataFileId}/permissions`. The `[DOC]` source disagrees with itself; **the true Product GET-permissions path is UNRESOLVED** — assert neither, verify live.
- **Copy vs Duplicate are different operations.** `POST /copy/{source}/revisions/current/{target}` copies the source's current revision to **REPLACE an EXISTING target** (destructive to the target, source intact — the target must already exist) → returns a `revisionId`. `POST /{dataFileId}/duplicate` creates a **brand-new file object** (new `dataFileId`) → returns full `FileMetadata`. Do not treat them as synonyms.
- **The revision id has two different field names.** Write/copy responses return it as **`revisionId`**; the revision **metadata** object carries it as **`dataFileRevisionId`**. Same concept, different key.
- **`public` default flips between worlds** (Product `true` = all instance users; Framework `false` = uploader only), and **both code examples hard-code the client-helper arg `public=false`** — so anyone copying a sample verbatim sends a private file regardless of server default.
- **Upload params are QUERY params, not a body.** `POST /api/data/v1/data-files?name=…&description=…&public=…` — `name` is **required**; the request **body** is the raw file bytes, not JSON.

## The headline — a two-world, multi-op island `[DOC]`

The Data File Service is documented as **two distinct worlds** of the same resource:

- **World A — PRODUCT.** Base `/api/data/v1/data-files`, host `{instance}.domo.com`. Documented by `files-api-product.md` (authoritative) + the self-annotated `cand-files.yaml`. Reached with raw `fetch(url)` calls (ambient session/cookie context in the examples). **11 path templates / 14 verb operations** (13 are titled endpoint sections on the page; the 14th — bare-path GET download-current — is derivable from the download section, not separately titled). Product-only op families: **Copy/Move, Duplicate, Get-All-Revisions, Get-Revision-Metadata-by-ID, file-level Delete.** `[DOC]`
- **World B — APP-FRAMEWORK / Code-Engine.** Base `/domo/data-files/v1`. Documented by `files-api-framework.md` + `files-framework.yaml`. Reached through the **App-Framework SDK** (`domo.post/get/put/delete`, not raw fetch); the framework YAML declares **HTTP bearer JWT** auth. Carries a **framework-only Multi-part upload family** (create session, create-update session, upload part, commit, abort) that is wholly absent from World A. Note: **"Domo Bricks do not support the Files API."** `[DOC]`

Both are the **same** Data File Service (shared `dataFileId`/`revisionId` vocabulary, shared metadata/permission schemas) — this is a two-world split like Pages (rank-11) / Task Center (rank-14b), **not** a mirror pair and **not** two unrelated APIs. The distinctive twist is the self-annotated Product spec (see the intro): treat its unconfirmed detail as `[INFER]`.

## World A (PRODUCT) — the surface `[DOC]`

Host `{instance}.domo.com`, base `/api/data/v1/data-files`. **11 paths / 14 ops.** Only three ops carry a request body (POST upload = raw bytes; PUT revision = raw bytes; PUT permissions = JSON); every GET/DELETE/copy/duplicate takes **no body**.

| # | Method · Path (relative to base) | Purpose | Body | Returns |
|---|---|---|---|---|
| 1 | `POST /` `?name=&description=&public=` | Upload a File (`name` **required** query param; `description`/`public` optional) | raw file bytes | `DataFileIdResponse {dataFileId}` |
| 2 | `PUT /{dataFileId}` | Upload a File Revision | raw file bytes | `RevisionIdResponse {revisionId}` |
| 3 | `GET /{dataFileId}` | **Download current-revision BYTES** (Content-Type = the file's own mime) — the `revisionId`-null branch of the download op; **not a titled standalone endpoint** | — | file bytes |
| 4 | `DELETE /{dataFileId}` | Delete a File (**permanent**) | — | (body `[INFER]`) |
| 5 | `GET /details` `?userId=&expand=&dataFileIds=` | Get All Files Metadata — all three are optional **query** params (page mislabels `userId`/`expand` as path — ignore that) | — | array of `FileMetadataSchema` |
| 6 | `GET /{dataFileId}/details` `?expand=` | Get File Metadata by ID | — | `FileMetadataSchema` |
| 7 | `GET /{dataFileId}/revisions/{revisionId}/details` | Get Revision Metadata by ID (**revisions** plural) | — | `FileRevisionSchema` |
| 8 | `GET /{dataFileId}/revisions/details` | Get All File Revisions (**revisions** plural) | — | array of `FileRevisionSchema` |
| 9 | `GET /{fileId}/revision/{revisionId}` `?filename=` | **Download a File Revision** — param **`{fileId}`**, **`revision` SINGULAR** (genuine surface inconsistency — do NOT normalize) | — | file bytes |
| 10 | `POST /copy/{sourceDataFileId}/revisions/current/{targetDataFileId}` | Copy/Move — replace an **existing** target with source's current revision (destructive to target) | — | `RevisionIdResponse {revisionId}` |
| 11 | `POST /{dataFileId}/duplicate` | Duplicate — create a **new** file object | — | `FileMetadataSchema` (new `dataFileId`) |
| 12 | `DELETE /{dataFileId}/revisions/{revisionId}` | Delete a File Revision (**revisions** plural) | — | (body `[INFER]`) |
| 13 | `GET /{dataFileId}/permissions` | Get File Permissions — **base path UNRESOLVED** (see naming traps) | — | `FilePermissionsSchema` |
| 14 | `PUT /{dataFileId}/permissions` | Update file permissions | `FilePermissionsSchema` (JSON) | (body `[INFER]`) |

`expand` takes comma-separated values `revisions`, `metadata`, or both `[DOC]`.

## World B (APP-FRAMEWORK / Code-Engine) — how it differs `[DOC]`

Base `/domo/data-files/v1`, reached via the App-Framework SDK (`domo.*`), bearer-JWT per its YAML. It is a **near-mirror with deliberate divergences** — do not assume World-A shapes:

- **Auth:** framework YAML declares **HTTP bearer JWT** (vs Product's assumed/session auth). In-app the SDK supplies it; token handling → `domo-code-engine.md`.
- **Upload body:** **multipart FormData with a `file` field** (`[DOC]` here) — **not** the raw octet-stream body World A uses.
- **Default `public`:** **`false`** (the App Framework secures the file to the uploader unless `public=true` is passed) — the **opposite** of Product's `true`.
- **Get-all params:** `limitToOwned` + `ids` (vs Product's `userId` + `dataFileIds`).
- **Delete granularity:** **revision-only** delete is documented (file-level delete is *not* documented here — absence ≠ proof).
- **Multi-part family (Framework-only):** create session `POST /domo/data-files/v1/multipart`, create-update session, upload part, commit, abort — a whole op family absent from World A.
- **`datetime*` polymorphism:** framework get-by-id returns **ISO-8601 strings** (`"2019-03-04T21:41:01.000+0000"`); the framework YAML models `oneOf int | date-time`. (Product examples show epoch-millis ints.) Do not assume one representation.
- Whether World A also supports multipart, or World B supports Copy/Duplicate/Get-All-Revisions/file-delete, is **unverified** (absent from the respective docs — missing evidence, not proof).

## Schemas `[DOC]` (Product spec; framework twin diverges where noted)

- **`DataFileIdResponse`** = `{ dataFileId: integer }`. **`RevisionIdResponse`** = `{ revisionId: integer }`.
- **`FileRevisionSchema`** = `{ dataFileRevisionId, dataFileId, contentType (mime), uploadUserId, sizeBytes, uploadTimeMillis, md5Hash, sha256HashValue, scanState, datetimeUploaded }`. **`uploadTimeMillis` is a DURATION** (tiny values like 199/216/297 — a processing time, not a wall-clock timestamp). `scanState` only ever shows **`SAFE`** in examples. Note the revision id here is **`dataFileRevisionId`**, not `revisionId`.
- **`FileMetadataSchema`** = `{ dataFileId, name, responsibleUserId, datetimeCreated, currentRevision (a `FileRevisionSchema`, populated conditionally / via `expand`), revisions (array; `[]` in all examples), existing (boolean — always `false` in examples, meaning **undefined**) }`.
- **`FilePermissionEntrySchema`** = `{ entityType, entityId, grant, pass }`. `entityType` = **`USER`** (attested); `GROUP` is spec-assumed (`# Assuming GROUP is also possible`). `entityId` is a string ("IDs can be strings or numbers"). Only attested values: `grant = 'READ_WRITE_DELETE_SHARE_ADMIN'`, `pass = 'NONE'` — other tokens undocumented.
- **`FilePermissionsSchema`** = `{ publicAccess: boolean, entries: [FilePermissionEntrySchema] }`.

## Auth line — the load-bearing unresolved `[INFER]`/`[REPO]`

There is **no confirmed Product auth header.** The three data points disagree:
- The Product spec's securityScheme is **`X-DOMO-Developer-Token`** — but its own description self-hedges it `"(Assumed based on similar APIs)"`, so it is **`[INFER]`, not documented.**
- The authoritative Product page documents **no auth at all** — every code example is a bare `fetch(url)` implying ambient session/cookie context.
- The **only genuine in-repo caller** authenticates with the **session-id header `X-Domo-Authentication`** (built from OAuth2 refresh → access-token → `/api/oauth2/sid`), **not** a developer token `[REPO]` — actively contradicting the assumed header.
- World B declares **bearer JWT** (framework YAML).

**Do not hard-code the auth header — verify against the running instance.** And the **host is `{instance}.domo.com`, NOT `api.domo.com`** `[REPO]`: the spec's server-variable default `'api'` is a misleading placeholder that contradicts its own description ("Your specific Domo instance name"). Token/SID minting + the file-op grant → `domo-identity-access.md`; the token/SID is a **secret** (never log or commit).

## Repo precedent — near-zero (load-bearing) `[REPO]`

The **only** genuine Files-API reference in the workspace is the Product-world **DELETE** path in `asset-lifecycle-app/scripts/e2e_delete_assets.py:267` (`api/data/v1/data-files/{id}`) — and it is **dead scaffolding**: it is guarded by `created.get('data_file_id')`, which the script **never assigns**, so the call never fires. Plus `dataFileId` appears as one fallback id-key in the same script's `_id()` helper (line 57). **Executed-call count for the entire surface is ZERO** — so **every operation stays `[DOC]`/`[INFER]`, never `[REPO]`-validated.**

By contrast the **FileSets** API (the false-friend surface) is heavily used — **~10 repo files** call `files/v1/filesets`, dwarfing this API's single dead reference. The `u2s-doc-summary-app` `metadataFileId` hits are **FileSets download calls** whose variable name merely contains the substring `dataFileId` — false friends, not Files-API callers. (The repo does authenticate its data-files call with `X-Domo-Authentication` session-id, per the auth section — `[REPO]` about auth, not about any op succeeding.)

## Do NOT claim as documented fact

Every item below is an over-claim the verification workflow REFUTED or re-tiered, or a self-annotation/gap it flagged. Guard them:

1. **Do NOT** claim **`X-DOMO-Developer-Token` is the documented/required auth header.** It appears only in the self-annotated YAML with the hedge "Assumed based on similar APIs" (`[INFER]`); the authoritative page documents no auth (bare `fetch(url)`); the one repo caller uses the session-id header `X-Domo-Authentication`. *(REFUTED → `[INFER]`)*
2. **Do NOT** claim **`application/octet-stream` is the documented upload content-type.** The page says only "the file to upload" and names no Content-Type; octet-stream is a self-hedged YAML choice (with multipart listed commented-out). The **Framework** world *does* document multipart FormData `file` (`[DOC]` there).
3. **Do NOT** claim **`401` or `404` are documented Product response codes.** Only **`200`** is `[DOC]`-corroborated (bare "HTTP/1.1 200 OK" per op). The `401`/`404` on ops are spec-author additions (`[INFER]`); the `401`/`404` seen on the page are illustrative JSON **id values**, not status codes. *(PARTIAL → `[INFER]`)*
4. **Do NOT** claim the response-code set is a **closed `{200,401,404}`** with no `400`/`403`/`429`/`5xx`. That is an unproven universal negative — a required-`name` upload plausibly `400`s, the permissions model plausibly `403`s. Absence in docs is missing evidence.
5. **Do NOT** claim **DELETE-file / DELETE-revision / PUT-permissions return an empty `{}` body.** The page shows only a bare "200 OK" with vague prose; the `{}` schema is self-hedged `# Assuming empty OK`. `response.json()` on a truly empty body may throw.
6. **Do NOT** call `entityType` a **closed enum `[USER, GROUP]`** or treat `GROUP` as a confirmed literal token. Only `USER` is attested; prose confirms group access as a *capability* but never the enum string. `GROUP` + closedness rest solely on self-hedged YAML. *(PARTIAL → `[INFER]`)*
7. **Do NOT** claim the **`grant`/`pass` value vocabularies.** They are opaque strings; the only attested values are `grant='READ_WRITE_DELETE_SHARE_ADMIN'` and `pass='NONE'`. Other tokens (and `pass`'s meaning) are undocumented.
8. **Do NOT** claim **`scanState` is a virus/malware scan** or enumerate its values. Only `SAFE` is attested; no prose describes the field. Scan semantics and any pending/infected states are name-based inference.
9. **Do NOT** claim **`datetimeUploaded`/`datetimeCreated` are always epoch-millis integers.** They are polymorphic across worlds (Product = epoch-millis ints; Framework = ISO-8601 strings; framework YAML = `oneOf int|date-time`). And do **not** confuse **`uploadTimeMillis`** (a tiny **duration**) with a wall-clock timestamp.
10. **Do NOT** "normalize" the download-revision path **`{fileId}/revision/{revisionId}`** (singular, `{fileId}`) to `{dataFileId}/revisions/{revisionId}`. The singular form is authoritatively confirmed and is a **genuine surface inconsistency**, not an error to fix. *(CONFIRMED)*
11. **Do NOT** assert the download **query-param casing.** `filename` (lowercase) vs `fileName` (camelCase) is inconsistent within the authoritative page. Unresolved; verify live.
12. **Do NOT** assert the Product **GET-permissions base path.** The authoritative page contradicts itself (`/domo/data-files/v1/{fileId}/permissions` header vs `/api/data/v1/data-files/{dataFileId}/permissions` code + YAML). Unresolved.
13. **Do NOT** count **`GET /api/data/v1/data-files/{dataFileId}`** (download current revision) as a **titled standalone endpoint** in an op-count. It **exists** and downloads current-revision bytes (`[DOC]`, via the download section's `revisionId`-null branch) but is a spec-author addition (`# Added based on download logic`) — the page documents **13** titled sections; the YAML models **14** ops. *(CONFIRMED existence; count caveat)*
14. **Do NOT** claim the **repo EXERCISES any Files-API operation.** The sole reference (`e2e_delete_assets.py:267` DELETE) is guarded by a key the script never assigns — dead code. Executed-call count is ZERO; the repo evidences the DELETE path **shape** only.
15. **Do NOT** treat the **two worlds as byte-identical mirrors.** They diverge on base path, auth, get-all params, delete granularity, upload body, default `public`, and whole op families (copy/duplicate/revisions-list/file-delete = Product-only; multipart = Framework-only). *(REFUTED single-world → `[DOC]` two-world)*
16. **Do NOT** claim the server host is **`api.domo.com`.** The spec's server-variable default `'api'` is a misleading placeholder contradicting its own description and the repo's per-instance host `https://{instance}.domo.com`.
17. **Do NOT** claim uploaded files **default to public universally.** Product world defaults `public=true` (`[DOC]` prose); the App-Framework world defaults `public=false` (`[DOC]`). Opposite per world. Both code examples also hard-code the helper arg `public=false`, so verbatim sample use sends a private file. *(PARTIAL → `[DOC]` per-world)*
18. **Do NOT** define the **`existing`** boolean. It is always `false` in examples and undefined in prose — do not infer it means "the file exists."
19. **Do NOT** trust the download code example's **response shape.** It buggily destructures `const {revisionId} = await response.json()` from a **binary** download whose real response is raw bytes (`Content-Type` = the file's own mime). The Copy/Duplicate examples also omit `{method:'POST'}` (defaulting to GET) — do not copy verbatim.

## Safety & hygiene

- **The auth token/SID is a secret** — never write it into source, handoffs, or commits; read it from config at call time (repo convention: macOS Keychain / `~/.config/domo-utils/`). Never log it. Do not hard-code the *header name* either — it is unresolved (see auth line).
- **Mutations here are high-blast-radius and often irreversible.** `DELETE /{dataFileId}` is **permanent**; **Copy/Move REPLACES an existing target file** (destructive to the target's current revision); `PUT /permissions` can silently expose a private file (`publicAccess:true`) or revoke access. Confirm human intent before any delete/copy/permissions write, and never guess the target id.
- **Public-by-default is a Product-world exposure trap.** A Product upload with no `public` param defaults to **all instance users can access the file.** Pass `public=false` unless instance-wide access is intended — but know the Framework world defaults the other way.
- **Verify the path and auth against the running instance before scripting.** The GET-permissions base path, the download filename casing, and the real auth header are all unresolved between `[DOC]` sources; a wrong path is a silent misfire (404, not a validation error).
- **Do not conflate with FileSets.** Before touching any "file" call in this repo, check the base: `data-files` = this API (near-zero repo use); `filesets` = `domo-filesets.md` (heavy repo use). A `metadataFileId`/`dataFileId` substring inside a `filesets` call is a false friend.
- **Do not trust result fields you have not seen live.** `existing`, `scanState` beyond `SAFE`, the `grant`/`pass` vocab, and delete/permissions response bodies are all uncharted — read a live response before depending on them.

## Companion skills

- `domo-filesets.md` — the **FileSets API** (`filesets` resource, RAG/unstructured-doc storage) — the #1 false friend; the heavily-used sibling this API is constantly confused with.
- `domo-code-engine.md` — the **App-Framework SDK / CE `sendRequest`** request model that World B (`/domo/data-files/v1`) rides on, and the tokenless in-app auth.
- `domo-datasets.md` — the **DataSet import / Stream** file-upload path (`/api/data/v1/streams/…`), a different "upload a file" that lands tabular rows, not a Data File.
- `domo-identity-access.md` — minting the developer token / session id and the role/grant that gates file operations; the `USER`/`GROUP` entity ids in a `FilePermissionEntry`.
- `domo-pages.md` / `domo-task-center.md` / `domo-projects.md` / `domo-scheduled-reports.md` / `domo-certified-content.md` / `domo-federated.md` / `domo-search.md` — sibling documented islands for shape contrast; **Pages** and **Task Center** are the other **two-world** surfaces (this one adds the self-annotated-reverse-engineered-spec twist).
