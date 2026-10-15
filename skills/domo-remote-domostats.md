# Domo Remote DomoStats

Operating notes for the **Domo Remote DomoStats API** — a tiny 3-operation Product surface that lists DomoStats "applications", reads one application's job details, and PUT-updates a job's configuration. The job it updates is the one that **materializes another Domo instance's DomoStats data into a local metrics DataSet** (`remoteInstance` → `metricsDatasetId`) — the likely API face of the Governance-Toolkit / Observability-Metrics cross-instance DomoStats pull. Read this before touching any `/v1/applications` or `/v2/applications/.../jobs` call, or any code mentioning `session_token`, `subscriberJobId`, `remoteInstance`, or `metricsDatasetId`.

## What this skill owns (and defers)

- **Owns**: the Remote DomoStats API surface — catalog artifact `remote-datastats-api.yaml` (info.title "Domo Remote Domostats API", v1.0.0), host `https://{instance}.domo.com`, the 3 ops `getApplications` / `getJobsList` / `updateJob`, and the `Application` / `JobDetails` / `JobUpdateRequest` / `ExecutionPayload` schemas.
- **Defers**: the **DomoStats datasets themselves** and Governance-Toolkit content → `domo-governance-datasets.md`. **Federated migration** (`/api/query/migration/...`, V1→V2→Amplifier) → `domo-federated.md`. **Publish / embed** (Domo Everywhere) → `domo-everywhere.md`. **App Studio / Pro-Code apps** (DataApps) → `domo-appstudio.md` / `domo-procode-app.md`. The word "applications" here does NOT mean any of those (see naming traps).

## Evidence tiers

Every claim below carries a tier. Do not silently upgrade a tier.

```
[DOC]  = developer.domo.com page / OpenAPI YAML under domo.com/docs/openapi / dev-portal API-Reference page / first-party SDK.
         (A domo-support.domo.com/s/article/<digits> = Salesforce KB = [KB], NOT [DOC].)
[KB]   = Domo Knowledge Base article / documented product behavior.
[REPO] = verified against this repo's actually-running code (a real caller, not dead scaffolding).
[INFER]= reasoned / inference-from-absence / spec-author-assumed.
```

Rules: a fetch FAILURE (405 / JS-gated / login-wall / 404 / timeout) is MISSING evidence, NOT proof of absence. Universal negatives ("no other ops exist", "the enum is closed") are `[INFER]` unless a doc positively says so. Prefer positive phrasing. The single guarded failure mode is **over-claiming** — presenting a spec quirk or an unverified assumption as documented Domo fact.


## Naming traps (read first)

| you see | reality |
|---|---|
| "applications" | DomoStats DATA-producing artifacts — `displayType`/`type` example `'DataFlow'`, with `rowCount`/`columnCount`/`cardInfo`/Beast-Mode `formulas`. **NOT** App Studio DataApps or Pro-Code apps (`domo-appstudio.md` / `domo-procode-app.md`). `[DOC from example]` |
| "Remote" / "Federated" | **NOT** `domo-federated.md` (rank-16), which owns only the migration verb `/api/query/migration/...`; different base path and purpose. `[DOC]` |
| `remoteInstance` + `subscriberJobId` (publisher/subscriber vocab) | **NOT** Domo Everywhere Publish (which PUSHES content, no documented mutating API); this PULLS metrics and HAS a documented `PUT`. Vocab overlap is real but the surface is separate. `[DOC]` |
| "DomoStats" | **NOT** the DomoStats datasets themselves (`domo-governance-datasets.md`); this is the JOB that materializes a remote instance's DomoStats into `metricsDatasetId`. `[DOC/INFER]` |
| catalog `remote-datastats` vs title "Remote Domostats" | ONE surface, two first-party spellings — do NOT treat as a typo of a different API, do NOT normalize. `[DOC]` |
| declared param names `Application_Id`/`Job_Id` | do NOT match templates `{applicationId}`/`{jobId}` — OpenAPI-invalid labels. Build the URL from the camelCase **template tokens**. `[DOC observation; casing INFER]` |
| bare paths `/v1/applications` under `{instance}.domo.com` | no `/api/` service namespace; two first-party renderings DISAGREE (bare vs `/api/executor/...`). Base path UNRESOLVED — verify live, prepend nothing blindly. `[INFER]` |
| `UpdateResponse.code = 200` | an IN-BAND response-body field, NOT the HTTP transport status code. `[DOC]` |
| `Application.status 'SUCCESS'` vs `UpdateResponse.status 'OK'` | different fields, different value spaces — do not conflate. `[DOC]` |
| repo `X-DOMO-Developer-Token` / `cloudId` hits | FALSE FRIENDS — FileSets provisioning code and Magic-ETL DataFlow tile JSON (`dataSource.cloudId:'domo'`), never this API. `[REPO]` |

## The surface, in one line

A **single-world small island with a documented intra-surface version split** (`v1` applications-list & job-update, `v2` jobs-list): one host, one declared auth scheme, exactly 3 ops over an `application → jobs` hierarchy. It reads as a reverse-engineered facade over Domo's job "executor". Conceptually it is the likely API face of the Governance-Toolkit **Observability Metrics** cross-instance DomoStats pull `[KB conceptual]`; the community `domolibrary` `DomoJob_RemoteDomoStats` uses the identical example `applicationId` `[INFER/SDK corroboration]`.

## Operations (3 ops, 3 paths, one method each — all `[DOC]`)

| # | op | method + path | ver | 200 body | notes |
|---|---|---|---|---|---|
| 1 | `getApplications` | `GET /v1/applications` | v1 | `Application` (SINGULAR object, despite "list") | **ONLY op with `session_token`** (query, required). `offset`/pagination NOT modeled here. |
| 2 | `getJobsList` | `GET /v2/applications/{applicationId}/jobs` | **v2** | `JobDetails` (SINGULAR; `allOf[Application, +7]`) | query `offset` (int, default 0); **no `limit`/total** modeled. Declared param `Application_Id` ≠ template `{applicationId}`. |
| 3 | `updateJob` | `PUT /v1/applications/{applicationId}/jobs/{jobId}` | v1 | `UpdateResponse {status:'OK', code:200 (in-band), message}` | body `JobUpdateRequest` requires only `jobId`+`jobName`. Declared params `Application_Id`/`Job_Id` ≠ templates. |

Send **v2** for the jobs list and **v1** for the other two — do not normalize `[DOC]`. Base path is written bare (no `/api/` prefix) but is CONTESTED (see hedge #8). Only a `200` is documented for each op `[DOC]`; every error code is uncharted `[INFER]`.

## Schemas (all shapes `[DOC]` as modeled; the guards are `[INFER]`)

- **`Application`** (12 props): `id`, `displayType`, `type` (example `'DataFlow'`), `name`, `owner` (`{id,name,type,group}`), `status` (example `'SUCCESS'`), `created`/`lastTouched` (int64 — 13-digit examples read as epoch **milliseconds**, but the spec says only "timestamp" → unit `[INFER]`), `rowCount`, `columnCount`, `cardInfo` (`{cardCount,cardViewCount}`), `properties.formulas` (map of Beast-Mode `Formula`). No `required` list declared.
- **`JobDetails` = `allOf[Application, {…}]`** — a job IS an application plus: `lastUpdated`, `validConfiguration:bool`, `validAccount:bool`, `adc:bool` (unexplained), `cloudId` (example `'domo'`), `permissions` (a **free string** example `'READ_WRITE_DELETE_SHARE_ADMIN'` — NOT a closed enum, do not decompose the underscores into grants), and **`tags` = a STRING holding stringified JSON** (`'["domoStats",...]'`) — `JSON.parse` it, it is not an array.
- **`JobUpdateRequest`** — required `jobId`+`jobName` only. `executionTimeout` (seconds), `executionPayload` (below), `executionResponse` (opaque `additionalProperties:true`, example `{}` — shape unknown), `accounts` (array of integer IDs), `resources.requests`/`limits` each exposing **only `memory`** (no `cpu` modeled), `triggers` (array of empty objects, example `[]` — shape unknown).
- **`ExecutionPayload`** — `remoteInstance` (a `*.domo.com` URL), `subscriberJobId`, `policies`, `metricsDatasetId`. **`policies`** is modeled as a fixed 6-property struct (`AccessTokens`/`DomainWhitelist`/`IPWhitelist`/`OIDC`/`SAML`/`DirectSignOn`), each a **policy-ID (UUID) string, not a boolean** — treat it as an OPEN name→UUID map (community data shows a `People` key too); the 6 keys are examples, closedness is `[INFER]`.

## Auth (genuinely unresolved — do not hard-code)

The spec declares global `security: DeveloperToken` = apiKey header `X-DOMO-Developer-Token` `[DOC-declared]`, but `getApplications` *additionally* declares a required `session_token` **query** param described as "the authentication token" — and only that op declares it. So for THIS surface the auth is self-contradictory: header vs query token, and per-op. That the header is the live auth, and what `session_token` actually is (dev token? session cookie/JWT? how obtained?), are both `[INFER]`. **Verify live before hard-coding anything.** Note a `session_token` in the query string is a credential-in-URL leakage risk `[INFER]`.

## Repo precedent = ZERO

No running code in this workspace calls any of the 3 ops or uses `session_token` / these paths / these `operationId`s / the payload fields. Grep hits are FALSE FRIENDS: repo `X-DOMO-Developer-Token` occurrences are FileSets provisioning code; `cloudId` occurrences are Magic-ETL DataFlow tile JSON (`dataSource.cloudId`); DomoStats artifacts in-repo are exported KB CSV text. The only mentions of this spec are unowned-catalog handoff notes. Executed-call count for the entire surface is **0** → every op stays `[DOC]`/`[INFER]`, never `[REPO]`-validated `[REPO=none]`.

## Do NOT claim as documented fact

1. Do NOT claim `X-DOMO-Developer-Token` is the documented/required auth for THIS API `[INFER]` — the header is `[DOC]` only as Domo's *general* Product-API convention; here it is spec-declared and self-contradicted (`getApplications` requires a `session_token` query param called "the authentication token"). Auth is unresolved — verify live, do not hard-code the header as THE auth.
2. Do NOT claim `session_token` is a general/API-wide required param — it is declared required on `GET /v1/applications` ONLY (absent from `getJobsList`/`updateJob`); the single-op query-param requirement is a spec-author artifact `[INFER]`, unverified at runtime, unused in this repo.
3. Do NOT claim the GET ops return a single object — the 200 schemas are modeled SINGULAR (`Application` / `JobDetails`) but the operationIds/descriptions say "list" and `getJobsList` carries an `offset` param, so the real response is very likely an array / paged envelope `[INFER]`; the singular shape is an unverified spec quirk.
4. Do NOT call the v1/v2/v1 split "intentional/authoritative design" — the per-op version prefixes ARE documented and must be honored (v2 for jobs-list, v1 for the other two; do NOT normalize) `[DOC]`, but no rationale is given; deliberate design vs incidental version drift is `[INFER]`.
5. Do NOT state the path params are named `Application_Id`/`Job_Id` as fact — those are only the spec's `parameters[].name` LABELS and they contradict the templates `{applicationId}`/`{jobId}` (an OpenAPI defect); build the URL from the camelCase template tokens. Effective casing is unverified `[INFER]`.
6. Do NOT claim 200 is the only outcome or that the response-code set is closed — only a 200 per op is documented (happy-path only) `[DOC]`; error codes (400/401/403/404/429/5xx) are undocumented here, NOT proven absent, and `UpdateResponse`'s own `status`/`code`/`message` triple implies non-200 outcomes exist `[INFER]`.
7. Do NOT claim Remote DomoStats is a wholly distinct API with NO overlap `[INFER]` — the portal lists it as its own API-Reference section `[DOC]`, but its payload (`remoteInstance`+`subscriberJobId` = Publish publisher→subscriber vocab; example `"DomoStats People with Activity Log"` + `domoStats` tags = Governance-DomoStats content) overlaps those surfaces by construction; the "no overlap" universal negative is unproven.
8. Do NOT tell a caller to invoke the BARE paths (`/v1/applications`) as-is — they carry no `/api/` namespace and two first-party renderings DISAGREE (bare vs `/api/executor/...`); the base path is UNRESOLVED `[INFER]` — verify live, and do NOT blindly prepend `/api/` either.
9. Do NOT describe `policies.*` as on/off booleans or a CLOSED set — they are policy-ID (UUID) STRINGS in an open map (community data shows a `People` key) `[DOC for the 6 modeled; closedness INFER]`.
10. Do NOT treat `JobDetails.tags` as a JSON array — it is a STRING holding stringified JSON; a consumer must `JSON.parse` it first `[DOC]`.
11. Do NOT invent fields for `executionResponse` (opaque, `additionalProperties:true`, example `{}`) or `triggers[]` (array of empty objects, example `[]`) — their runtime shapes are unknown `[DOC that they are unschematized]`.
12. Do NOT present `'READ_WRITE_DELETE_SHARE_ADMIN'` as one of a closed permission enum — `permissions` is a FREE string `[DOC]`; its underscore decomposition into grants is `[INFER]`.
13. Do NOT read `UpdateResponse.code` (200 in the body) as the HTTP status code — it is an in-band envelope field `[DOC]`.
14. Do NOT claim these 3 are the ONLY operations on the surface — only 3 are modeled; exhaustiveness is `[INFER]` (the mixed v1/v2 hints at an evolving, partially-charted surface).
15. Do NOT treat repo `X-DOMO-Developer-Token` or `cloudId` hits as precedent for this API — false friends (FileSets provisioning; Magic-ETL DataFlow tiles) `[REPO]`.
16. Do NOT read the remote-pull / cross-instance purpose from `info.description` — it is generic and never says "remote"; purpose is carried only by the title + `executionPayload` fields + example names `[DOC facts]`; the cross-instance interpretation is `[INFER/KB]`.
17. Do NOT treat `created`/`lastTouched`/`lastUpdated` as epoch SECONDS — the 13-digit examples read as MILLISECONDS, but the spec says only "timestamp" so the unit is `[INFER]`.
18. Do NOT infer a page size, max offset, or total-count contract for `getJobsList` — `offset` is present but NO `limit` param and NO total/count field are modeled `[INFER from absence]`.

## Safety & hygiene

- `updateJob` is a **mutating PUT** that rewrites a job's execution config (timeout, resource limits, the auth-policy map, the target `metricsDatasetId`, the `remoteInstance` it pulls from). High blast radius — gate on explicit human intent; never fire it speculatively against a shared instance.
- The `PUT` body carries **policy UUIDs, account IDs, a `subscriberJobId`, and a remote-instance hostname**. These are references, not secrets, but do NOT paste real values from any instance into committed artifacts — use `<uuid>` / `<instance>.domo.com` placeholders. Never commit a real `session_token` / developer token / bearer JWT.
- Live-verify these before asserting an invocation URL or a response shape: (a) the **base path** (bare vs `/api/...`); (b) **auth** for `getApplications` (header, `session_token`, or both — and what `session_token` is); (c) the **real 200 shape** of both GETs (object vs array vs paged envelope); (d) whether **more ops** exist; (e) the **error-code** surface; (f) effective **path-param casing**; (g) `getJobsList` **pagination** (limit / page size / max offset); (h) whether these ops require an **Admin** role (the base DomoStats Connector is Admin-gated per KB).

## Companion skills

`domo-governance-datasets.md` (the DomoStats datasets this job produces) · `domo-federated.md` (the migration API — different "remote") · `domo-everywhere.md` (Publish/embed — the publisher/subscriber neighbor) · `domo-datasets.md` (`metricsDatasetId` target) · `domo-magic-etl.md` (the DataFlow-type "application" model).
