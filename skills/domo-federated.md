# Domo Federated Migration

Use this skill to reason about — or drive via REST — **Domo federated-datasource migration between federation generations**: moving a datasource **Federated V1 → Federated V2**, and **Federated (V2) → Cloud Amplifier**, plus the **reverse** of each hop. **Read the naming-trap table below before anything else**: "Federated" and "Cloud Amplifier" are among the most overloaded words in the Domo platform, and this skill owns **only the migration verb** (`/api/query/migration/…`) — **not** federated-dataset querying, **not** the Magic ETL Cloud Amplifier pushdown-compute face, **not** the Federated V2 account credential, **not** identity federation. Getting the sense wrong sends you to the wrong skill.

Federated migration is a **single-world, fully-inventoried, `[DOC]`-only two-spec island** — **two DISTINCT sequential migration specs, 11 operations total** (`federatedv1.yaml` = V1→V2, **5 ops**; `federatedv2.yaml` = V2→Amplifier, **6 ops**) charting the **two hops of one 3-generation lineage** (V1 → V2 → Amplifier). The two specs share one host (`{instance}.domo.com`), one auth (`X-DOMO-Developer-Token`), and one `/api/query/migration/` base — but have **zero overlapping paths, zero shared operationIds, and disjoint schema sets**. They are pipeline **stages**, **not** a mirror pair (contrast rank-13 Projects: one spec at two doc URLs), and **not** a two-world split (contrast rank-11 Pages / rank-14b Task Center: the *same* object through two host/auth worlds). This skill is a faithful map of those 11 ops + a heavy disambiguation layer, guarded hard against over-claiming (**zero calls were executed** against either API).

## What this skill owns (and what it defers)

**Owns:** the **migrate / reverse verb** across both hops — discover integration *types* → *accounts*/*integrations* → *candidate* datasources → **migrate** (or **reverse**) — under `{instance}.domo.com/api/query/migration/…`, `X-DOMO-Developer-Token`.

**Defers:**
- **Querying / reading an existing federated dataset** (runtime schema fetch; the `/api/data/v3/…/schema` works vs `/api/query/v1/…/schema` 403 quirk) → `domo-datasets.md` / `ai/toolkit`. That reads a federated dataset; it never migrates one.
- **"Federated datasets cannot be a Magic ETL input"** (the LoadFromVault authoring constraint) → `domo-magic-etl.md`.
- **The "Cloud Amplifier" PUSHDOWN compute cloud** (author transforms in Magic ETL, execute them on Snowflake/BigQuery/Databricks) → `domo-magic-etl.md`. Same **brand** as this skill's migration *destination*, a **different surface** (compute face vs migration verb); `[INFER]` whether they are the same backing system.
- **The Federated V2 ACCOUNT / Cloud Amplifier INTEGRATION credential object** (created in the Datacenter UI) → `domo-accounts-connectors.md`. The migration ops **consume/associate** an account/integration but **never create** one.
- **`transportType=FEDERATED`** (a static enum label on a dataset object), **Databricks ADC "federate catalog tables as datasets"** bridging, and **workload identity federation** (OIDC for Bedrock/Vertex) — all homonyms of different features (see the naming-trap table).
- **Minting the developer/access token** and the role/grant model → `domo-identity-access.md`.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo-support.domo.com/s/article/<digits> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall / 404) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting an untested runtime behavior, an inference-from-absence, or a `[KB]` product fact as an API contract. This entire skill is `[DOC]`/`[KB]`/`[INFER]` with **zero `[REPO]`**: no working code in this repo calls either migration API, and **no request was ever executed** against them — so treat all request/response *behavior* (does a bad token 401; does an unknown id 404; is a re-run idempotent; what an in-flight migration looks like) as **documented-but-untested**.

**Verification provenance.** Written after verification Workflow **`wf_a08af167-479`** (16 agents, 0 errors: 6 spec-reading cross-check clusters → adversarial refute of the 8 highest over-claim-risk claims, each default-refuted-if-uncertain → completeness critic + island verdict → synthesizer), corroborated by a **direct full read of the raw YAMLs** `/tmp/federatedv1.yaml` (362 lines) and `/tmp/federatedv2.yaml` (368 lines), fetched fresh via `curl` from `domo.com/docs/openapi/product/federatedv{1,2}.yaml` and read line-by-line this session. **All 8 adversarial verdicts were caught and folded into the hedge list** (7 REFUTED + 1 RETIER) — the guarded failure mode working as designed: the closed-enum-platform-guarantee claim → **RETIER** to an instance-scoped `[DOC]` fact; mirror-pair/two-world, 401/404-error-surface, v2-migrate-takes-a-body, `toe`-is-a-poll-handle, lossless-reverse, arbitrary/certified-enumeration, and token-identity-certainty → all **REFUTED**. 鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).

## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first.

| You see… | It actually is… | Owner |
|---|---|---|
| **`/api/query/migration/…`** | the generation **MIGRATION verb** (V1→V2; Federated↔Amplifier + reverse) | **this skill** |
| **"Federated" + `/schema` 403 / `/api/data/v3` schema read** | reading an **existing** federated dataset at runtime | `domo-datasets.md` (`[REPO]`) |
| **"Federated datasets can't be a Magic ETL input"** | an **ETL authoring** constraint | `domo-magic-etl.md` (`[REPO]`) |
| **"Cloud Amplifier" as pushdown COMPUTE** (run ETL on SF/BQ/Databricks) | the **compute face** of the Cloud Amplifier brand | `domo-magic-etl.md` (`[REPO]`) |
| **Databricks ADC "federate catalog tables AS datasets"** | a **Dataflow-clone** prereq bridging | `ai/toolkit` (`[REPO]`) |
| **`transportType=FEDERATED`** | a static **enum label** on the dataset object | `domo-datasets.md` (`[REPO]`) |
| **`FederatedV2Account` / `CloudAmplifierIntegration`** | the **credential** object the migration consumes (built in Datacenter UI) | `domo-accounts-connectors.md` |
| **"workload identity federation"** (OIDC for Bedrock/Vertex) | an unrelated **homonym** | cloud-agents / `.github` |

**Internal traps — all *within* this skill's own two specs:**
- **`Federated` in `federatedv2.yaml` means the V2 generation, NOT V1** — there are three points on a two-hop chain (V1 → V2 → Amplifier); the word "Federated" alone never tells you which generation.
- **The credential noun flips across the hop:** `FederatedV2Account` (v1 spec) vs `CloudAmplifierIntegration` (v2 spec).
- **Three non-interchangeable `type` vocabularies:** v1 `/types` = free-form lowercase-hyphen (`mysql-federated`, `snowflake-federated`, **no enum**); v2 `/types` = **UPPERCASE enum** (`BIGQUERY`, `SNOWFLAKE`), and its `{integration-type}` path param is documented **case-insensitive**; `MigrationCandidate.type` = lowercase-hyphen again (`bigquery-federated`). The `-federated` suffix appears in **both** v1 types and v2 candidates, so it does **not** distinguish generation.
- **`Standard` vs `Agent` Federated V2 architecture** `[DOC]` (prereq prose): `Agent` = an on-prem network agent (`domo-federated-agent-v2`), **NOT** an AI agent.

## The headline — a single-world, two-spec `[DOC]` island

Two OpenAPI specs, both **3.0.0**, both version **1.0.0**, both host **`https://{instance}.domo.com`**, both global-secured by the one apiKey scheme `DeveloperToken` (header `X-DOMO-Developer-Token`), both under `/api/query/migration/`. `[DOC]`

| axis | `federatedv1.yaml` | `federatedv2.yaml` |
|---|---|---|
| title | "Federated V1 to V2 Migration APIs" | "Federated V2 to Amplifier Migration APIs" |
| hop | Federated **V1 → V2** (+ reverse V2→V1) | Federated (V2) **→ Cloud Amplifier** (+ reverse Amplifier→Federated) |
| ops | **5** (3 GET / 2 POST) | **6** (3 GET / 3 POST) |
| base prefix | `/api/query/migration/federated/v1/to/v2/` | `/api/query/migration/` (mixed `integrations/…`, `candidates/…`, `federated/to/amplifier/…`, `amplifier/to/federated/…`) |
| direction enum(s) | `V1_TO_V2` / `V2_TO_V1` (two single-value response schemas) | `FEDERATED_TO_CLOUD_AMPLIFIER` / `CLOUD_AMPLIFIER_TO_FEDERATED` (one unified `MigrationResult`) |
| ids | plain **untyped strings** (accounts `'1'`/`'2'`) | strictly `format: uuid` |
| repo precedent | **ZERO** | **ZERO** |

**Single-world, established positively (not from a failed fetch) `[INFER]`:** the reached catalog `domo.com/docs/llms.txt` lists **exactly two** `federat*` entries — `federatedv1` and `federatedv2` — **both under Product** (instance-host). There is no second host, no second auth world, no App-Framework (`/domo/`) mirror. That positive two-line enumeration is the single-world proof.

**Why NOT a mirror pair (contrast rank-13 Projects):** rank-13 was ONE spec at two doc URLs describing the SAME 21 ops. Here the two files have **zero overlapping paths, zero shared operationIds, and disjoint schema sets** (v1: `MigrationResponse`/`MigrationReversalResponse`/`MigrationCandidateDatasource`/`MigrationRequest`; v2: `MigrationResult`/`MigrationCandidate`/`CloudAmplifierIntegration`). Different ops, not one op mirrored. `[DOC]`

**Why NOT a two-world split (contrast rank-11 Pages / rank-14b Task Center):** the two-world pattern surfaces the *same* object through two host/auth/framework worlds. Here both specs live in the **identical** world (same host, same `DeveloperToken` scheme, same namespace, same OpenAPI/version) and describe **different objects at different pipeline stages**. Sameness-of-world + difference-of-operation is the exact inverse of a two-world split. `[DOC]`

**Chartedness — fully-inventoried, runtime uncharted `[DOC]`/`[INFER]`:** all **11/11** ops carry paths, methods, operationIds, params, request/response schemas, enums, and HTTP `x-codeSamples` — the op catalog and schemas are `[DOC]`-complete. But this is a **"fully inventoried ≠ fully charted"** island: every op documents **only a `200`** (no 4xx/5xx, no `default`), and runtime behavior (HTTP error codes, sync/async, idempotency, execute-permission, collision-at-migrate-time, cross-generation eligibility, Cloud-Amplifier-brand identity) is **uncharted → rides `[INFER]`/`[KB]`**. Every op is **`[DOC]`-never-`[REPO]`, zero executed calls**.

## The surface — 11 operations across 2 specs `[DOC]`

Every op documents **only `200`** (no 4xx/5xx, no `default`). The discovery chain is **bootstrappable from a bare token**: the no-id `types` op → the type-keyed `accounts`/`integrations` op (returns ids) → the per-account/per-integration `candidates` op → `migrate`/`reverse`. You must hold the account-id (v1) or integration-id (v2) in the path to list candidates; the account listing is scoped to what the calling user's permissions allow. There is **no** op that enumerates arbitrary datasources.

### `federatedv1.yaml` — Federated V1 → V2 (base `/api/query/migration/federated/v1/to/v2/`), all tag *Federated V1 to V2 Migration* `[DOC]`

| # | Method | Path (after base) | operationId | Body? | 200 response | Tier |
|---|---|---|---|---|---|---|
| 1 | GET | `types` | `list-federated-integration-types` | none | array of **`string`** (free-form, **no enum**; ex `mysql-federated`, `snowflake-federated`) | `[DOC]` |
| 2 | GET | `accounts/{integration-type}` | `list-federated-v2-accounts-by-integration-type` | none | array of `FederatedV2Account` `{id,type,name}` (all string, no `required`); **scoped to the caller's permissions** | `[DOC]` |
| 3 | GET | `candidates/{account-id}` | `list-federated-v1-migration-candidate-datasources-by-account` | none | array of `MigrationCandidateDatasource` `{id,name,migrated,migrationDate?}` | `[DOC]` |
| 4 | POST | `{datasource-id}/accounts/{account-id}` | `migrate-federated-v1-datasource-to-v2` | **REQUIRED** `MigrationRequest` `{catalog,schema,table}` (all required, **case-sensitive**) | `MigrationResponse` (`direction` single-value enum `V1_TO_V2`) | `[DOC]` |
| 5 | POST | `{datasource-id}/reverse` | `reverse-federated-v1-to-v2-datasource-migration` | **none** | `MigrationReversalResponse` (`direction` single-value enum `V2_TO_V1`) | `[DOC]` |

### `federatedv2.yaml` — Federated V2 → Cloud Amplifier (base `/api/query/migration/`) `[DOC]`

| # | Method | Full path | operationId | Tag | Body? | 200 response | Tier |
|---|---|---|---|---|---|---|---|
| 6 | GET | `integrations/types` | `listCloudAmplifierIntegrationTypes` | Cloud Amplifier Integration | none | array of **`string` enum [`BIGQUERY`, `SNOWFLAKE`]** (**instance-scoped**, see hedge #3) | `[DOC]` |
| 7 | GET | `integrations/{integration-type}` | `listCloudAmplifierIntegrationsByType` | Cloud Amplifier Integration | none | array of `CloudAmplifierIntegration` `{id(uuid),name,type(string,no enum),authMethod enum[OAUTH,SERVICE_ACCOUNT]}`; `{integration-type}` is **case-insensitive** | `[DOC]` |
| 8 | GET | `candidates/federated/to/amplifier/integrations/{integration-id}` | `listDatasourceMigrationCandidates` | Migration | none | array of `MigrationCandidate` (ex `migrated:false`) | `[DOC]` |
| 9 | POST | `federated/to/amplifier/{datasource-id}/integrations/{integration-id}` | `migrateDatasourceToAmplifier` | Migration | **none** (two uuid path params only) | `MigrationResult` (`direction` = `FEDERATED_TO_CLOUD_AMPLIFIER`) | `[DOC]` |
| 10 | GET | `candidates/amplifier/to/federated/integrations/{integration-id}` | `listDatasourceReverseMigrationCandidates` | Migration | none | array of `MigrationCandidate` (ex `migrated:true` + `migrationDate`) | `[DOC]` |
| 11 | POST | `amplifier/to/federated/{datasource-id}` | `reverseDatasourceMigration` | Migration | **none** (one uuid path param; **no** `integration-id` segment) | `MigrationResult` (`direction` = `CLOUD_AMPLIFIER_TO_FEDERATED`) | `[DOC]` |

**The sharpest cross-spec fact — the migrate body contract is OPPOSITE across the two hops `[DOC]`:** the V1→V2 migrate (#4) **requires** a JSON `MigrationRequest` body (`catalog`/`schema`/`table`), while the V2→Amplifier migrate (#9) declares **NO `requestBody`** — its inputs are the two uuid path params only, and `catalogName`/`schemaName`/`tableName` are carried on the pre-fetched `MigrationCandidate` (resolved via `datasource-id`). Both **reverse** ops (#5, #11) have **no body**. Do not assume #9 takes a body like #4.

**Sync-vs-async is `[INFER]`, not `[DOC]`:** every migrate/reverse `200` body already carries a **terminal** `state` (enum has no IN_PROGRESS/PENDING value) with both `startTime` **and** `endTime` populated in every example, and **no poll/status op exists** in either spec — so it *reads as* synchronous/blocking, but the word "synchronous" is never written. Carry as `[INFER]`. Corollary: **`toe` is NOT a job handle to poll** — v2 defines it as *"Unique request identifier … used by Domo support to retrieve additional information for failed migration attempts"* `[DOC]`; no op accepts `toe` as input.

## The objects `[DOC]`

**v1 schemas** `[DOC]`:
- **`FederatedV2Account`** `{id, type, name}` — all `string`, no `required` list.
- **`MigrationCandidateDatasource`** `{id(string), name(string), migrated(bool), migrationDate(date-time, nullable)}` — no `required` list. (ids are plain untyped strings; one example candidate id starts with `F` — the spec never explains this, so **do not assert its meaning**.)
- **`MigrationRequest`** (the ONLY schema with a `required` list): `required [catalog, schema, table]`, all `string`, all documented **case-sensitive** names of the DB catalog / schema / table the V1 datasource references. **`schema` may be the literal string `"NULL"`** if the database does not use schemas — that is the string `"NULL"`, **not** JSON `null`.
- **`MigrationResponse`** `{toe, datasourceId, direction(enum single V1_TO_V2), startTime, state, errorMessage?(nullable), endTime}` — no `required` list.
- **`MigrationReversalResponse`** — same shape as `MigrationResponse` but `direction` enum is single-value `V2_TO_V1`.

**v2 schemas** `[DOC]`:
- **`CloudAmplifierIntegration`** `{id(uuid), name, type(string, NO enum), authMethod(enum [OAUTH, SERVICE_ACCOUNT])}`.
- **`MigrationCandidate`** `{id(uuid), name, type(string, ex bigquery-federated), catalogName, schemaName, tableName, collision(bool), collidingDatasourceId?(uuid,nullable), collidingDatasourceName?(nullable), migrated(bool), migrationDate?(date-time,nullable)}`.
- **`MigrationResult`** `{toe, datasourceId(uuid), direction(enum [FEDERATED_TO_CLOUD_AMPLIFIER, CLOUD_AMPLIFIER_TO_FEDERATED]), startTime, state, errorMessage?(nullable), endTime}` — v2 **unifies into this one schema** what v1 split across `MigrationResponse` + `MigrationReversalResponse`.

**The `state` enum (both specs)** `[DOC]` = `[COMPLETE, INCOMPLETE, ABORTED]`, documented as the migration's **final** state — only `COMPLETE` is success:
- **`COMPLETE`** — completed successfully.
- **`INCOMPLETE`** — failed *after* some datasource changes were made; content powered by the datasource **may remain unavailable/non-functional until the migration is re-attempted and completes**. Detail in `errorMessage`.
- **`ABORTED`** — aborted *before* any changes were made. Detail in `errorMessage`.

**`collision` is a read-time pre-flight field on `MigrationCandidate` ONLY** `[DOC]`: `collision:true` means a different datasource matching this candidate's catalog/schema/table already exists in the destination integration — the spec states **the migrate WILL FAIL** and that content associated with the candidate must instead be moved to the colliding datasource. `collision` is **not** on `MigrationResult`, so at migrate time a collision surfaces as `state:INCOMPLETE/ABORTED` + `errorMessage` `[INFER]`. The remediation (bulk "switch cards to a different DataSet") is a general product capability `[KB]`, not part of these APIs.

## Auth line `[DOC]`/`[KB]`/`[INFER]`

- **Token provenance:** a Domo **access token generated in the instance ADMIN PANEL** (`More > Admin > Access tokens`); user-scoped, granting the same access as its owning user. **`[DOC]`** for the admin-panel provenance (v1:5,241; v2:5,261); **`[KB]`** (article `360042934494`, "Manage Access Tokens") for the flow + user-scoping.
- **Header:** `X-DOMO-Developer-Token` — securityScheme `DeveloperToken`, `type: apiKey`, `in: header`, applied globally (`security: [ - DeveloperToken: [] ]`), no per-op override. **`[DOC]`** (v1:31-32,236-241; v2:13-14,256-261).
- **Scheme/prose split:** the scheme name/header/placeholder say "Developer" while the prose + KB say "access token" — **one** admin-panel per-user instance token, **not** two credentials. `[DOC]` naming + `[KB]` identity.
- **No OAuth:** neither spec declares an `oauth2` scheme or any scope; the sole server is `{instance}.domo.com`. **`[DOC]`**
- **No `api.domo.com` / Bearer twin:** neither spec references `api.domo.com`, Bearer, or scopes, and `llms.txt` lists only the two Product entries → **`[INFER]`** ("no OAuth-Bearer twin **listed** in the reached catalog"), never "no twin exists."
- **Same-as / different-from a developer.domo.com portal token?** The specs are **silent** on the comparison → **`[INFER]`; do NOT assert either "same" or "different" as documented.** The header's "Developer" naming is the instance-token convention, not evidence of a portal credential. (Repo convention: `domo-auth.md` treats `X-DOMO-Developer-Token: $DOMO_TOKEN` as the "Developer token" method, distinct from Public-API OAuth Bearer `[REPO]`.)
- **Prereq (`[DOC]` prose):** V1→V2 migration requires that **Federated V2 be enabled in the instance by a Domo account representative** and that matching-integration-type Federated V2 accounts be created in the Datacenter UI **before** migrating (federatedv1:15-23).

## Boundaries & orphans

- **The lineage is a 3-generation chain, charted as two hops `[DOC]`.** V1 → V2 (federatedv1) then V2/Federated → Cloud Amplifier (federatedv2). Whether a **V1** datasource is *directly* Amplifier-eligible (vs must go V1→V2 first) is **not resolved** by the specs: federatedv2's title says "V2," but every wire string is the generic `federated`, and eligibility is delegated server-side to `listDatasourceMigrationCandidates` (#8). Treat cross-generation eligibility as `[INFER]`; do **not** assert a documented V1-ineligibility rule.
- **Cloud Amplifier here (migration destination) vs Cloud Amplifier in `domo-magic-etl.md` (pushdown compute) `[INFER]`.** Same product **brand**, overlapping warehouses, but the surfaces differ (migration `/types` = `BIGQUERY`/`SNOWFLAKE` only `[DOC]`; the ETL compute face additionally lists Databricks `[REPO]`) and no reached source proves they are the same backing system. Present as two faces of one brand `[INFER]`; do **not** claim the migration API can target Databricks.
- **Idempotency / re-run safety is uncharted `[INFER]`.** `migrated`/`migrationDate` are read-time candidate flags; the spec never states what a second migrate on an already-migrated datasource does, nor whether reverse-then-migrate is safe. No documented idempotency.
- **Execute-permission gate is `[INFER]`/`[KB]`.** Only account **listing** is documented as permission-scoped `[DOC]`; the specific role/grant to **execute** a migrate/reverse (vs merely list) is undocumented.
- **The credential objects are orphan-adopted from `domo-accounts-connectors.md`.** `FederatedV2Account` / `CloudAmplifierIntegration` are created in the Datacenter UI (not by these ops); the migration verb only associates/consumes them. The seam is the `{account-id}` / `{integration-id}` path segment.
- **Error surface is `200`-only `[DOC]` → real HTTP errors are `[INFER]`.** No 4xx/5xx or `default` is documented on any of the 11 ops. Failure is expressed **in-band**: read the `200` body `state` (`INCOMPLETE`/`ABORTED`) + `errorMessage`, not just the HTTP code. A real 401 (bad token) / 404 (unknown id) is plausible from dev-token convention but stays `[INFER]`.

## Repo false friends `[REPO]`

**Repo precedent = ZERO** `[REPO]`. A full-tree grep (all `.py/.js/.mjs/.ts/.sh/.ipynb`, tracked + untracked) for `api/query/migration`, the 11 operationIds, and the migration paths returns **no API caller** — the only file that will match is this skill doc. **Therefore every one of the 11 ops stays `[DOC]`, never `[REPO]`,** and no request was ever executed. Every in-repo `federated`/`amplifier` hit is a false friend of a different feature:

- **runtime federated-dataset schema read** (`/api/data/v3/…/schema` works vs `/api/query/v1/…/schema` 403) — reads an existing federated dataset; never migrates → `domo-datasets.md` / `ai/toolkit`.
- **"Federated datasets cannot be a Magic ETL input"** — an ETL LoadFromVault authoring constraint → `domo-magic-etl.md`.
- **"Cloud Amplifier" pushdown compute** (author in ETL, execute on SF/BQ/Databricks) — the compute face of the brand → `domo-magic-etl.md`.
- **Databricks ADC "federate catalog tables as datasets"** — a Dataflow-clone prereq bridging → `ai/toolkit`.
- **`transportType=FEDERATED`** — a static enum label on the dataset object → `domo-datasets.md`.
- **"workload identity federation"** (OIDC for Bedrock/Vertex/Foundry) — an unrelated homonym → cloud-agents / `.github`.
- The ubiquitous in-repo **`X-DOMO-Developer-Token`** is all FileSets / provisioning / DataFlow deploy — **same header, unrelated surface.** The `api/query/migration` needle is the real test, and it is **zero**.

## Do NOT claim as documented fact

Every item below is an over-claim the verification workflow REFUTED or RETIER'd, or a completeness gap it flagged. Guard them:

1. **Do NOT** say the **documented error surface is 401/404** (or any 4xx/5xx). All 11 ops document **only `200`**; failure is in-band via the body `state` (`INCOMPLETE`/`ABORTED`) + nullable `errorMessage`. HTTP 401/404 behavior is `[INFER]` from dev-token convention. *(REFUTED)*
2. **Do NOT** say **migration is asynchronous** or that **`toe` is a pollable job handle**. It *reads as* synchronous (terminal `state` + populated `startTime`/`endTime`, no poll op) but "synchronous" is never written → `[INFER]`. `toe` = a "unique request identifier … used by Domo support for failed attempts" `[DOC]`; **no op accepts it as input**. *(REFUTED)*
3. **Do NOT** say **Cloud Amplifier types are limited to `BIGQUERY`/`SNOWFLAKE`** as a closed platform guarantee. The enum is real `[DOC]` but the op returns "types matching integrations that **exist in the Domo instance**" — an instance-provisioned, point-in-time list. `CloudAmplifierIntegration.type` is a bare string; `MigrationCandidate.type` uses `bigquery-federated`; product KB lists more backends (Databricks, Redshift, Dremio, Oracle…) `[KB]`. Phrase as an **instance-scoped** list, not a platform ceiling. *(RETIER → `[DOC]` instance-scoped)*
4. **Do NOT** claim **v2 migrate takes a body like v1**. v1 migrate (#4) **requires** `MigrationRequest {catalog,schema,table}`; **v2 migrate (#9) declares NO `requestBody`** (two uuid path params only; catalog/schema/table live on the pre-fetched `MigrationCandidate`). Opposite body contract. `[DOC]` *(REFUTED)*
5. **Do NOT** claim a **reverse migration losslessly/fully restores with no downstream impact**. Reverse returns the same 3-state enum (success not guaranteed); no losslessness statement exists; v2 migrate positively documents in-flight unavailability, and `INCOMPLETE` means content may stay non-functional until re-attempted. `[DOC]` refutes it. *(REFUTED)*
6. **Do NOT** say these APIs **enumerate arbitrary or "certified" datasources without holding ids**. No "certified" concept exists in either spec. Candidate listing REQUIRES an account-id (v1) / integration-id (v2) in the path; account listing is permission-scoped. The only truth: ids are **bootstrappable** via no-id `types` → type-keyed `accounts`/`integrations` → `candidates`. `[DOC]` *(REFUTED)*
7. **Do NOT** call the two YAMLs a **mirror pair or two-world split**. Zero shared paths/operationIds; disjoint schema sets; identical world — they are sequential pipeline **stages** of one lineage. `[DOC]` *(REFUTED)*
8. **Do NOT** assert the **migration-destination Cloud Amplifier IS provably the Magic-ETL-pushdown Cloud Amplifier**. Same brand, overlapping warehouses, but no reached source proves identity and the surfaces differ. Two faces of one brand → `[INFER]`; do **not** claim the migration API can target Databricks.
9. **Do NOT** assert **V2→Amplifier accepts a V1 datasource directly (or forbids it)**. Title says "V2"; wire strings are generic `federated`; eligibility is delegated server-side to `listDatasourceMigrationCandidates`. Unresolved → `[INFER]`.
10. **Do NOT** claim **re-running migrate is idempotent / reverse-then-migrate is safe**. `migrated`/`migrationDate` are read-time flags; re-run semantics are uncharted → `[INFER]`.
11. **Do NOT** claim a **specific role/grant to EXECUTE migrate/reverse is documented**. Only account-**listing** is stated permission-scoped `[DOC]`; execute-grant is `[INFER]`/`[KB]`. The "Federated V2 must be enabled by a Domo account representative" prereq IS `[DOC]` (v1:15).
12. **Do NOT** claim **`collision` is reported on `MigrationResult`**. `collision`/`collidingDatasource*` are read-time pre-flight fields on `MigrationCandidate` **only** `[DOC]`; at migrate time a collision surfaces as `state:INCOMPLETE/ABORTED` + `errorMessage` `[INFER]`. Remediation is a general product capability `[KB]`.
13. **Do NOT** send JSON **`null` where the spec says the literal string `"NULL"`** — v1 `MigrationRequest.schema` "may be the literal 'NULL' if the database does not utilize schemas." `[DOC]` (V1→V2 hop only; v2 has no body).
14. **Do NOT** treat **`direction` as a caller-chosen request parameter**. It is a fixed single-value RESPONSE enum in v1 (`V1_TO_V2` / `V2_TO_V1`) and a 2-value RESPONSE enum in v2 `MigrationResult`; never a request toggle. `[DOC]`
15. **Do NOT** impose **uuid validation on v1 ids** — v1 ids are plain untyped strings; the `F…`-prefixed candidate example is unexplained (do **not** assert its meaning). Only v2 ids are `format: uuid`. `[DOC]`
16. **Do NOT** treat the **example `startTime`→`endTime` deltas (~2–8 s)** as a performance or downtime-duration guarantee — illustrative example payloads only → `[INFER]`.
17. **Do NOT** frame ANY of the 11 ops as **`[REPO]`-verified or "works"** — zero repo callers of any `/api/query/migration/…` path; every in-repo `federated`/`amplifier` hit is a false friend. All 11 ops are `[DOC]`-never-`[REPO]`, **zero executed calls**.

## Safety & hygiene

- **`X-DOMO-Developer-Token` is a secret** — never write it into source, handoffs, or commits; read it from config at call time (repo convention: macOS Keychain / `~/.config/domo-utils/`). Never log the token.
- **Migration mutates production data plumbing.** A migrate re-points a live datasource to a new backing integration; the spec itself warns content "will be unavailable and/or non-functional while the migration is ongoing," and an `INCOMPLETE` outcome can leave it broken until re-attempted. **Confirm human intent before any migrate/reverse**, and do not migrate datasources you don't own or aren't authorized to change.
- **Probe read-only first** — walk the discovery chain (`types` → `accounts`/`integrations` → `candidates`) and inspect the candidate's **`collision`** flag *before* any POST. `collision:true` means the migrate will fail; resolve the destination collision first.
- **Read the body `state`, not the HTTP code** — a `200` can still carry `state:INCOMPLETE`/`ABORTED`. Branch on `state`; surface `errorMessage`; keep the `toe` for a Domo support ticket if a migration fails.
- **Mind the opposite body contract** — V1→V2 migrate needs a `{catalog,schema,table}` body (with the literal-`"NULL"` schema caveat); V2→Amplifier migrate and both reverses take **no body**. Sending a body to a no-body op, or omitting it on #4, is the most likely silent misfire.
- **Reverse is a real, documented escape hatch — but not a guaranteed undo.** It returns the same 3-state enum; plan for an `INCOMPLETE`/`ABORTED` reverse.

## Companion skills

- `domo-datasets.md` — reading an **existing** federated dataset (runtime schema fetch, the `/schema` 403 quirk, `transportType=FEDERATED`); what a datasource is. The migration verb here never reads dataset rows.
- `domo-magic-etl.md` — the **other** "Cloud Amplifier" (pushdown compute) and the "federated datasets can't be an ETL input" constraint — both false friends of this migration destination.
- `domo-accounts-connectors.md` — the **`FederatedV2Account` / `CloudAmplifierIntegration` credential** objects these ops consume but never create (built in the Datacenter UI).
- `domo-identity-access.md` — minting the admin-panel access token and the role/grant model (the execute-permission gate is `[INFER]`/`[KB]` here).
- `domo-projects.md` / `domo-scheduled-reports.md` / `domo-certified-content.md` — sibling **single-world documented islands** for shape contrast (this one is the first **two-spec sequential-hop** variant).
