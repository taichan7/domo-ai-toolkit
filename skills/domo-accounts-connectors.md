# Domo Accounts & Connectors

**Use this when** you are reasoning about a Domo **Account** (a stored *connector credential* object — the thing created on the Accounts tab when you enter a data source's credentials), a **connector** (a prebuilt or custom integration that pulls a third-party system and lands a DataSet), the **connector→account→DataSet linkage**, or *where* connectors come from (Connector Dev Studio, Workbench, DDX). It also disambiguates the dozen-plus other "account"/"connector"/"connection" things. (**Authoring** a custom or writeback connector in the Connector Dev Studio JS SDK is its own skill → `domo-custom-connector-authoring.md`.)

**NOT for:** raw-CSV upload / Stream-API mechanics / `updateMethod` / query-read / dataset lifecycle / PDP → `domo-datasets.md`. Reading a bound account's secret at runtime (`getAccount().properties`, the tokenless-vs-token "one rule") → `domo-code-engine.md`. Human login identities, OAuth clients, OAuth scopes → `domo-identity-access.md`. Publishing a Pro Code bundle with `domo publish` → `domo-procode-app.md` (the CLI is the single biggest false friend here — it is **not** a data connector).

## Surface shape at a glance

A **large documented REST island** (Account / Stream / DataSet OpenAPI YAML, reproduced verbatim) ringed by a **`[KB]`-only connector-authoring periphery** (connector catalog, Dev Studio, Workbench, DDX, scheduling grammar, publish flow):

- **REST core `[DOC]`** — the Platform **Account API** (`api.domo.com/v1/accounts`, 8 ops), and (deferred, but part of the same picture) the Platform Stream API (12 ops) and DataSet API (13 ops). Plus product-tier specs: Connectors API (1 exec op), Data Accounts API (4 ops), Datasets API (~31 ops).
- **Authoring/behavior periphery `[KB]`** — *how* a connector is chosen, configured, scheduled, built (Dev Studio / No-Code JSON / DDX), and how Workbench uploads from behind a firewall. None of this has a documented mutating REST API of its own.

The one genuinely **orphaned** first-class object charted here is the **Account (connector credential)** — no other skill owns "what an Account object *is* and how `/v1/accounts` manages it." The DataSet a connector *produces*, and how that DataSet is imported/read/governed, stays in `domo-datasets.md`.

## What this skill OWNS vs DEFERS

| This skill OWNS | Defers to |
|---|---|
| The **Account object** + **Account API** on `api.domo.com/v1` — accounts CRUD, `/account-types` discovery, `/{id}/shares`. The credential-object lifecycle nothing else charts. | — |
| The **connector-CONFIG** side of an instance stream — the `transport{type:CONNECTOR}`, `configuration[]`, `account{id}`, `dataProvider{key}`, `dataSource`, `advancedScheduleJson` body only. | — |
| The **connector→account→DataSet linkage seam** and the **`ACCOUNT`-typed manifest binding** (`[REPO]`). | — |
| **Connector catalog / Workbench / DDX** product behavior, and the connector→account→DataSet framing of a *custom* connector (`[KB]`). | **Authoring** a custom/writeback connector (the Dev Studio JS SDK, build flow, publish gate) → `domo-custom-connector-authoring.md` |
| The accounts/connectors **host↔auth "worlds" table**. | — |
| Raw-CSV **Stream API** (v1 `create→execution→part→commit`), v3 `/api/data/v3/.../uploads` START/PART/COMMIT, **`updateMethod=REPLACE\|APPEND`** query-param contract, query/read API, dataset get/list/delete lifecycle, **PDP**. | `domo-datasets.md` |
| **Connector execution / history / throttle** — `POST .../streams/{id}/executions {"action":"MANUAL"}`, `GET .../history/aggregate`, the ~15-min commit throttle. **Datasets already documents these** — link back, do not restate. | `domo-datasets.md` |
| Runtime **credential read** — `getAccount(id).properties`, property-key order, the CE-relative `expand=properties` fallback, the tokenless-`sendRequest`-vs-`getAccount` "one rule". | `domo-code-engine.md` |
| Human **login accounts**, **OAuth clients**, **OAuth scopes**, **audit**. | `domo-identity-access.md` |

**The linkage in one line:** a *connector* is configured with credentials → those credentials are stored as an *Account object* (`/v1/accounts`) → the connector *runs as a stream* (execution owned by datasets) → it *produces a DataSet* (owned by datasets). This skill owns the middle (the Account) and the connector-config body; the transport and the output are datasets'.

## Evidence tiers

- `[DOC]` — reproduced verbatim from an official machine-readable OpenAPI spec or an official docs page.
- `[KB]` — product behavior from a knowledge-base / product-docs article (behavior, not a REST contract).
- `[REPO]` — observed only in this repository or on a live instance; instance-internal, **not** a published contract.
- `[INFER]` — reasoned, not sourced. **Every universal negative on this surface ("there is no X endpoint") is at best `[INFER]`.**

**On disagreement, choose the more conservative claim.** A **fetch failure** (`developer.domo.com` 405 / JS-gated / 404 landing page) is **MISSING evidence, never proof of absence** — resolve it by fetching the machine-readable spec, not by declaring the feature nonexistent. (The `api.domo.com` Account API is confirmed via `accounts.yaml`, *not* via the reference pages that 405'd.)

## Verification provenance

Doc-cross-check + adversarial-verify workflow (`wf_7ede0b13-162`, 13 agents: 6 verify clusters — openapi-catalog, accounts-api, connector-framework, boundary-datasets/CE, naming-traps, repo-precedent — each with an adversarial refute pass, then a completeness critic). 鉄則 satisfied (verify **before** writing).

Reproduced **verbatim from OpenAPI YAML** (so these endpoint *sets* are `[DOC]`): `platform/accounts.yaml`, `platform/stream.yaml`, `platform/dataset.yaml`, `product/connectors.yaml`, `product/data-accounts.yaml`, `product/data-sets.yaml` (all reachable from `domo.com/docs/llms.txt`). Present in the catalog but **body never fetched** (endpoint sets uncharted): `dataschema.yaml`, `managing-dataset-history-api.yaml`, `query-dataset-api.yaml`, `framework/data.yaml`, the portal DataSet/Stream duplicates, `S3-Export-API.yaml`, and the files/filesets/export/framework specs. Pages that 405'd / JS-gated: the `developer.domo.com` account & connector reference pages, and the `docs/portal/Connectors/connectors` category landing (404). The **account** create/update/share request-body **envelopes** ARE machine-readable in `platform/accounts.yaml` — so their envelope shapes (`{name, type:{id, properties}}`, share `{user:{id}}`) are `[DOC]`; what stays `[KB]`/re-verify-live is the **connector-stream config body** and the **inner per-connector `type.properties` key set** (per-Account-Type, not portable).

## Naming-trap table — READ FIRST

"Account"/"connector"/"connection" collide across ~18 senses; conflation is the #1 hazard. Resolve the term **before** reaching for a mechanism.

| Term (as seen) | What it actually is | Owner | Tier |
|---|---|---|---|
| **account** (login / member) | A human/member identity in the instance (who-exists CRUD). **Not** a credential store. | `domo-identity-access.md` | `[DOC]` |
| **Account OBJECT** (Accounts tab) | A stored **connector credential**, created when you enter a connector's credentials; managed by the Platform **Account API** (`/v1/accounts`). Endpoint existence `[DOC]`; request-body **envelopes** `[DOC]`, inner per-connector property keys `[KB]`/re-verify. | **THIS skill** (orphan today; the DataSet it yields → `domo-datasets.md`) | `[DOC]` |
| **OAuth CLIENT** | `client_id`+`client_secret` minted at *Manage Clients*, used for `grant_type=client_credentials` to get a Bearer token. | `domo-identity-access.md` | `[DOC]` |
| **`account` SCOPE** | An OAuth token scope (a token permission, not an object). The token page's enum lists six (`account`/`audit`/`buzz`/`dashboard`/`data`/`user`); `workflow` is a **real seventh**, absent from that enum — see `domo-identity-access.md`. | `domo-identity-access.md` | `[DOC]` |
| **service account** | A *convention* (a normal user / integration owner used as a machine identity), **not** a distinct Domo object type. | `domo-identity-access.md` (+ `domo-magic-etl.md` for Snowflake pass-through owner) | `[KB]` |
| **broker / trading account (口座)** | External broker state (marketdata `account_id`, brokerage margin/nisa/specific) — **zero** relation to any Domo account; same word, opposite meaning. | marketdata / brokerage app `AGENT.md` | `[REPO]` |
| **Workflow "Account" DATA TYPE** | A workflow step input typed `Account`, mapped to an Account object shared-with/created-by the running user; the account service injects creds over HTTPS. | `domo-workflow.md` | `[KB]` |
| **connector** (data connector) | A prebuilt cloud connector that pulls a 3rd-party system and lands a DataSet; its configured creds become an Account object. | **THIS skill** (catalog orphan); resulting DataSet/stream → `domo-datasets.md` | `[KB]` |
| **custom connector** | A connector authored in the browser Connector Dev Studio / IDE — ES5 JS (docs disagree on the engine: GraalVM vs Nashorn — unresolved); **five** documented auth schemes incl. a no-auth option; distinct from prebuilt connectors and DDX. | `domo-custom-connector-authoring.md` | `[KB]` |
| **ryuu / `domo publish` CLI** | A **publish/deploy** tool for Pro Code app bundles — the biggest false friend; **NOT** a data connector. (`ryuu.js` browser SDK for filters/variables is a separate library again.) | `domo-procode-app.md` (+ `domo-auth.md`) | `[REPO]` |
| **MCP toolkit "connector"** | A hosted Model-Context-Protocol server toolkit (`{instance}/api/ai/v1/assistant/mcp/toolkits/{toolkit}`); observed-only, not a data-ingestion connector. | `domo-mcp-toolkits.md` | `[REPO]` |
| **connection** (Workflow canvas) | Flow-connector **wiring** drawn between shape tiles — distinct from the Workflow "Account" data type (the claimed equivalence is `[INFER]`). | `domo-workflow.md` | `[INFER]` |
| **connection status** (FE) | A UI data-source status flag (connected/demo/error) + DomoStats lineage edges — **not** a connector account. | repo apps (inventory-management, safety-command-center, asset-lifecycle) | `[REPO]` |
| **governance connectors** (DomoStats / Governance Datasets) | Two Domo-native metadata connectors; access path is connector→DataSet→query API. | `domo-governance-datasets.md` | `[KB]` |
| **pipeline** | Domo's transform surface is Magic ETL / DataFlow, not an ingestion "pipeline"; "pipeline" also appears only as a disallowed `updateMethod` family label (Merge/Partition). | `domo-magic-etl.md` | `[KB]` |
| **`gl_account_id` / `GL_ACCOUNTS`** | Accounting general-ledger accounts in a demo data generator — nothing to do with Domo Accounts. | `pl-summary-app` (repo demo) | `[REPO]` |
| **DDX / Domo Bricks** | **Domo Bricks (formerly DDX Bricks)** — custom code-app / advanced-viz objects (HTML/CSS/JS). **Two distinct entry points:** the in-product **Brick editor** (Monaco, *Card options → Edit Card*, no manifest tab, cannot call CE) **and** the local-bundle **Pro Code app** (`domo publish` CLI + full manifest + CE binding). A Pro-Code authoring surface, **not** a data connector or the Custom-Connector IDE. | `domo-procode-app.md` (both entry points) / `domo-procode-embedded-cards.md` | `[KB]` |
| **Workbench** | A **free Windows on-prem data-ingestion desktop agent** that uploads DataSets from behind the firewall (ODBC/CSV/Excel/Jira); a client-side tool, **not** a REST endpoint. **Not** an IDE, **not** the paid **Workbench Enterprise** server (its JWT `/Api/Jobs/{jobId}/Execute` remote job-*execution* endpoint is a separate REST surface, dispositioned rank-38), **not** the stream-side `transportType:WORKBENCH` marker. | **THIS skill** — authoring/scheduling → the *Workbench authoring-UX* section (`[KB]`); output lands as DataSets → `domo-datasets.md` | `[KB]` |

## The three host↔auth "worlds" — pick the row before you write a call

Account/connector operations live in **three different API worlds** with different hosts, different auth headers, and different object shapes. Using the right path against the wrong host/credential is the #2 footgun (after naming). This mirrors the same three-worlds hazard already documented for `domo-identity-access.md` and `domo-ai-services.md`.

| World | Host | Auth | Account surface it exposes | Tier |
|---|---|---|---|---|
| **Platform (public API)** | `api.domo.com` | **OAuth Bearer** (`grant_type=client_credentials`, scope `account`) — a **dev token will 401 here** | `/v1/accounts` CRUD + `/v1/account-types` + `/{id}/shares` (8 ops) | `[DOC]` |
| **Product (instance API)** | `{instance}.domo.com` | **`X-DOMO-Developer-Token`** header | `/api/data/v1/accounts` (list/get/create — 4 ops incl. `/api/search/v1/query`); connector run `POST /api/data/v1/streams/{streamId}/executions` | `[DOC]` endpoint set / `[KB]` bodies |
| **In-app / runtime (CE + App Framework)** | tokenless, same-origin | injected session (no header you write) | read a **bound** account's secret via CE `getAccount(id).properties`; connector-stream config edited via the product stream API | `→ domo-code-engine.md` / `→ domo-datasets.md` |

Rules of thumb:
- **`api.domo.com` ⇒ OAuth only.** Never send `X-DOMO-Developer-Token` there; never send a Bearer client token to `{instance}.domo.com`. The `account` OAuth scope is required for the Platform Account API.
- The **Platform** `/v1/accounts` and the **Product** `/api/data/v1/accounts` are **different endpoints returning different shapes** — do not assume a field seen in one exists in the other; re-verify per world.
- **Secrets are never in a response.** Neither world returns credential values on read/create; runtime secret access is CE-only (`getAccount().properties`) and is `domo-code-engine.md`'s contract, not this skill's.

## Platform Account API — `api.domo.com/v1` (the documented core)

Reproduced from `platform/accounts.yaml` (OpenAPI), so the **endpoint set** is `[DOC]`. Auth = OAuth Bearer, scope `account`.

| Op | Method + path | Notes |
|---|---|---|
| List accounts | `GET /v1/accounts` | paged — `limit` default **50**, max **500**; `offset` (`[DOC]`); returns account objects **without** secret property values |
| Create account | `POST /v1/accounts` | body carries the credential `properties`; response omits secrets |
| Get an account | `GET /v1/accounts/{ACCOUNT_ID}` | |
| Update an account | `PATCH /v1/accounts/{ACCOUNT_ID}` | partial; body **envelope** `{name, type:{id, properties}}` schematized in `accounts.yaml` → `[DOC]` and `type.id` **required**; inner per-connector `properties` keys per-type `[KB]` |
| Delete an account | `DELETE /v1/accounts/{ACCOUNT_ID}` | |
| List account types | `GET /v1/account-types` | discover which connector credential shapes exist; paged — `limit` default **50**, max **500**; `offset` (`[DOC]`) |
| Get an account type | `GET /v1/account-types/{ACCOUNT_TYPE_ID}` | yields the property template (see object model below) |
| **Share** an account (⚠ `GET` that **writes**) | `GET /v1/accounts/{ACCOUNT_ID}/shares` | documented as "Share an Account with a User" — a share **mutation** (`requestBody {user:{id}}` → `200 "No Content"`), **not** a read; see the safety note below |

- ⚠ **`GET /v1/accounts/{id}/shares` is a share MUTATION, not a read** — the spec keys it under `GET`, but documents it as "Share an Account with a User" with a `requestBody {user:{id}}` returning `200 "No Content"`. Do **not** treat it as a benign read probe: sharing a credential is a write that widens who can use it. (Whether the runtime verb is truly a body-carrying `GET` or the spec mis-keys a `POST` is `[INFER]` — re-verify live before calling; either way it **writes**.) There is **no** documented op that *lists* who an account is shared with (`[INFER]` for any such read).
- **Reads are access-scoped `[DOC]`** — `GET /v1/accounts` returns only accounts you **own** or that have been **shared with you** (spec `info.description`); a listing is **not** instance-global. An account you cannot see may still exist — do not read a short list as "these are all the accounts."
- **Request-body ENVELOPES are `[DOC]`; inner per-connector property keys are `[KB]`.** `accounts.yaml` carries machine-readable `requestBody` schemas: create `{name, type:{id, properties}}`, update (same envelope, with `type.id` **required**), and share `{user:{id: integer}}` — so the **envelope shapes** are `[DOC]` (this refines the earlier "single-source prose" note). What stays `[KB]`/per-type is the **inner `type.properties` key set** (the credential fields a given connector needs), which the spec's own create description says **varies per Account Type** — fetch `/v1/account-types/{id}` live; never hard-code them. Still prefer a **read-only `GET /v1/accounts` probe first** to confirm auth+scope before any write.
- **Do NOT claim a `POST /v1/accounts/{id}/validate` or a "test connection" endpoint as documented** — not present in the reproduced spec; any such op is `[INFER]` until re-fetched.
- Product-tier twin (**different world, do not conflate**): `GET|POST /api/data/v1/accounts`, `GET /api/data/v1/accounts/{account_id}`, `POST /api/search/v1/query` on `{instance}.domo.com` with `X-DOMO-Developer-Token` (4 ops, `[DOC]` endpoint set).

## Account object model & the account-type property template

**Account object** (from the spec, `[DOC]` shape):

```
{ "id": <string>, "name": <string>, "valid": <boolean>,
  "type": { "id": <string>, "properties": { ... } } }
```

- **`id` is a String** (spec `type: string`; quoted in every example) — the top-level account `id` is **not** numeric; this matches the `[REPO]` `"type":"ACCOUNT"` manifest binding whose `"id"` is a quoted string. (`type.id` below is the account-type key, also a string.)
- `valid` reflects whether the stored credentials passed their last check — it is a **status flag on the object, not proof of a live validate call you can trigger via a documented endpoint**.
- `type.id` names the account-type (connector credential shape). `type.properties` carries the credential fields — **secret values are absent on read and on the create response** (write-only).

**Account-type template** (`GET /v1/account-types/{id}`) exposes the form Domo renders when a human enters credentials:

```
_templates.default.properties[] = { name, prompt, required, regex }
```

- Use it to learn **which fields a given connector's credential needs** and their validation regex before constructing a `POST /v1/accounts` body — do not hard-code property names per connector.
- **Do NOT claim the full enumeration of account-types or their properties as documented fact** — the template is per-type and instance-dependent; fetch it live rather than asserting a fixed list.

## Connector-stream CONFIG body — the part this skill owns

A prebuilt/custom connector runs as an **instance stream**. Two halves, two owners:
- **CONFIG** (what connector, which account, which data source, schedule) — **this skill**.
- **EXECUTION / history / throttle** (kick a run, read run history, the ~15-min commit floor) — **`domo-datasets.md`** (do not restate; link back).

The connector-stream CONFIG body (single-source docs → `[KB]`, **re-verify live**):

```
{ "transport":   { "type": "CONNECTOR" },
  "configuration": [ ... ],            // connector-specific settings
  "account":     { "id": <account_id> },   // ← the Account object from /v1/accounts
  "dataProvider":{ "key": "<connector-key>" },
  "dataSource":  <connector-specific>,
  "advancedScheduleJson": <schedule grammar> }
```

- `account.id` is the seam: the stored **Account object** (this skill) is bound into the stream config here.
- `transport.type: "CONNECTOR"` distinguishes a connector-backed stream from an API/CSV-upload stream — the latter's transport + `updateMethod` + upload flow is **`domo-datasets.md`**'s.
- **Do NOT treat this body as a portable `[DOC]` contract** — it is single-source and connector-shaped; construct it against a live example, not from memory.
- **`advancedScheduleJson` grammar is `[KB]` and uncharted here** — do not invent cron/frequency fields; capture from a working stream.

## The connector→account→DataSet linkage & the `ACCOUNT` manifest binding

**End-to-end seam** (this skill owns the middle two hops; datasets owns the last):

```
connector (catalog choice)  →  credentials entered  →  Account object (/v1/accounts)
   →  bound into stream config (account.id, transport CONNECTOR)  →  stream EXECUTION  →  DataSet
        └── THIS SKILL ──────────────────────────────────────┘   └──── domo-datasets.md ────┘
```

**Pro Code manifest binding** (`[REPO]`, grounded): a package parameter typed `"type":"ACCOUNT"` is how a Pro Code app declares "I need a bound account at runtime." Observed in `news-summary-app/pro-code/manifest.json` (`"type":"ACCOUNT"` params paired with an `"id"` value).

- ⛔ **The `"id"` value is instance-specific** (e.g. news-summary-app's `"id":"865"`) — it is a live-instance account id, **NOT a generic/portable value**. Never copy an account id into a generic artifact or commit it as a shared constant; re-resolve per instance.
- At runtime the app reads that bound account's secret via CE `getAccount(id).properties` — **that read is `domo-code-engine.md`'s contract**, not this skill's. This skill owns *that the binding exists and how the account is created/managed*, not the tokenless-vs-token read rule.
- **Do NOT claim the manifest `ACCOUNT` binding is an official documented schema** — it is `[REPO]` (observed in this workspace's app bundles); the authoritative manifest schema lives with `domo-procode-app.md`.

## Connector-authoring periphery (`[KB]` — behavior, no mutating REST API of its own)

None of these have a documented mutating REST endpoint; they are product-behavior facts. Charted here so the reader knows *where* a connector comes from, not so they can script it.

- **Connector catalog** — prebuilt cloud connectors chosen in-product; picking one and entering credentials is what mints an Account object. The catalog itself is not a documented API surface.
- **Custom connector (Connector Dev Studio / IDE)** — author a connector in the browser: ES5 JS (engine unresolved in the docs — GraalVM vs Nashorn), **five** documented auth schemes incl. a no-auth option. The full authoring surface (JS SDK, build flow, publish/review gate) is its own skill → **`domo-custom-connector-authoring.md`**. Distinct from prebuilt connectors and from DDX/Bricks (DDX = a Pro-Code *app/viz* surface, `domo-procode-app.md`, **not** the connector IDE).
- **Workbench** — a **Windows on-prem agent** that uploads DataSets from behind the firewall (ODBC / CSV / Excel / Jira, etc.). A client-side ingestion **tool**, not a REST endpoint; its output lands as DataSets → `domo-datasets.md`. **How you author, transform, update-method and schedule a Workbench job in the client is charted in full below → the *Workbench authoring-UX* section.**
- **Scheduling** — `advancedScheduleJson` (see stream config) plus in-product schedule UI; grammar is `[KB]`/uncharted, capture from a live stream.
- **Do NOT** claim any of these expose a documented CRUD API. If a task needs to *create/edit a connector definition* programmatically, that path is **not documented** (`[INFER]`); the documented programmatic surface stops at the Account object + stream config + execution. (Authoring a connector *by hand* in the Dev Studio IDE is covered by `domo-custom-connector-authoring.md` — that too is a browser SDK, not a programmatic definition API.)

## Workbench authoring-UX — building an on-prem ingestion job (`[KB]`)

**Disambiguation first (read before routing).** "Workbench" here = Domo's **free Windows on-prem data-ingestion desktop agent** — it installs behind the firewall and *pushes* DataSets up to the cloud. It is **NOT** an IDE (a VS Code "workbench" shell / MySQL Workbench / Eclipse), **NOT** the paid **Workbench Enterprise** server product (whose JWT `PUT|GET /Api/Jobs/{jobId}/Execute` remote job-*execution* endpoint is a separate surface that *does* expose REST — dispositioned rank-38), and **NOT** the stream-side `transportType:WORKBENCH` marker on a DataSet (→ `domo-datasets.md`). This section owns **how you author a Workbench job in the client**; the DataSet it produces + its `updateMethod` REST contract stay in `domo-datasets.md`.

**No authoring REST API `[INFER]`.** Building / configuring / scheduling a standard Workbench job is a **desktop-client-UI-only** act — no `workbench.yaml`/`jobs.yaml` in the OpenAPI catalog, and the reference pages 404'd (MISSING evidence, *not* proof of absence). The only callable Workbench surface anywhere is WB-Enterprise's execute endpoint (above). Everything below is `[KB]` product behavior — re-verify against a live client before scripting any UI assumption.

- **Job / provider types (WB5)** — create a job via **`+`** in the Jobs pane; pick a **transport** (Local File / ODBC Connection / External-Process File Provider) + a **data-reader** source (CSV/delimited, Excel, JIRA, JSON, XML, ODBC/OLAP system-DSN, QuickBooks, SAP HANA via CData plugin, OLAP Cube, on-prem SharePoint plugin, Writeback-to-ODBC). ⚠ **only the DataSet name is editable after creation — any other change requires a NEW job.**
- **In-client transforms & value-mapping** ("Add a transform") — Search/Replace (**"Replace a Column Value"** = the value-mapping mechanism, with a Regular-Expression Builder), Create-Columns-Using-Calculations, Filter Columns, Custom Date Format, Set Time Zone, Encrypt/Decrypt/Hash columns, Combining DataSets (join). Custom transforms buildable as **`.dwp` plugins** via the WB SDK.
- **Update-method chosen at author time** — **Replace** and **Append** offered directly; **Upsert/Merge** = set Append then pick an **Upsert Key** on the Schema tab (⚠ must be enabled per-DataSet by Support; a new job must run **once on Replace first**); **Partition** via a partition key (WB5.1). Gotchas: switching Upsert→Replace **un-protects** the schema; a null in a partition key **errors the job**. These resolve to the DataSet-level `updateMethod` contract — **the REST param exposes only `REPLACE|APPEND`; Merge/Partition are product-level** → `domo-datasets.md`.
- **Scheduling grammar `[KB, volatile]`** — WB4 = a basic frequency list (once/day, once/week; workaround = Windows Task Scheduler) + Watch-File (WB4.5). **WB5 Advanced Scheduling** = exact time, days-of-week/month, months, intra-day intervals, watch-file; **Group Scheduling** = shared schedule + job dependencies / run-as-group / stop-subsequent-on-failure. Also launchable from the command line or as an ETL-package task. Scheduled runs use the **local system account** (impersonation for network files).
- **Versions & drift `[KB, volatile]`** — WB5 current; **5.2** latest (adds job Duplication + Cloud Integrations / Cloud Amplifier); 5.1 added schema protection, Upsert, Partition, Bulk Actions, simplified server migration; **WB4 is DEPRECATED** (no further feature/security updates, still troubleshot) — ⛔ **no published hard EOL date (asserting one = `[INFER]`)**; auto-update stays **within** a major version (WB4 is *not* auto-upgraded to WB5); installer from **Admin → Tool Downloads**.
- **Desktop-agent auth shape** (distinct from the rank-38 Enterprise JWT) — **WB5 = OAuth** (no access tokens surfaced; the token does not expire but a **user password change invalidates it**; ~**50 refresh tokens/user** ⇒ ~50 concurrent WB machines per user). WB4-era = Developer Client ID + Secret / Auth Token (access-token model). *Shape only — never capture the values.*
- **Proxy / firewall / security** — uses the **Windows system proxy** on first connect (editable at Settings → Proxy); credentials stored **AES-256/RSA** with a **locally-held key**; three schema-protection types + an "Allow schema changes" toggle; **job impersonation** (run as an AD user); Support supplies an **outbound IP to whitelist** (may change without notice); **ODBC needs a SYSTEM DSN** (WB runs as a service and cannot see user DSNs).
- **Install / agent / on-prem model** — a Windows **application** *plus* a **"Domo Workbench" Windows service** (auto-starts; start/stop/restart), default local-system account; requires **.NET 4.8**; 32- and 64-bit ODBC concurrent; **jobs are stored in the CLOUD tied to a login (not saved on the box)**, backed up via **export/import** (mass import/export in WB4.5.1); **Simplified Server Migration** = export/import the Workbench **Registry + Encrypted Key**; WB5 adds **Direct Upload**.

**Safety (documenting is autonomous-eligible; the live reader actions below are human-gated).** RUN/EXECUTE a job = **data egress** (on-prem → cloud) — desktop "run now", command-line launch, ETL-package task, and rank-38's `PUT /Api/Jobs/{jobId}/Execute`; a **Replace-method run is a destructive full-DataSet overwrite** (incl. the "run once on Replace first" step and Upsert→Replace, which un-protects the schema); create/edit/delete a live job mutates the ingestion pipeline; credential **mint/revoke** (WB-Enterprise "Create New JWT"/"Invalidate"; WB5 OAuth password-change invalidation); install/update/repair + service start/stop/restart on a customer machine; **server migration moves the local encryption key**; job export/import + Direct Upload. **Never commit** (placeholders only): WB5 OAuth access/refresh tokens (the ~50/user *limit* is fine to state), WB4 Client ID/Secret/Auth Token, WB-Enterprise JWTs + host, ODBC/system-DSN + source-DB passwords, the Workbench **Encrypted Key** file (treat as a private key), `.pem` keys (SFTP-Push sibling), instance host / job IDs / account IDs / AD impersonation creds. ⛔ **Do not declare the Workbench KB tree exhausted** — several WB5 article bodies were characterized from titles + snippets, not read end-to-end.

## Route-this-task guide (boundary decisions)

When a task mentions "account" or "connector", route it before acting:

| The task is really about… | Go to |
|---|---|
| Create/list/get/delete a **stored connector credential**, discover account-types, share an account | **THIS skill** → Platform `/v1/accounts` (OAuth) or Product `/api/data/v1/accounts` (dev-token) |
| **Configure** which connector + account + data source a stream uses | **THIS skill** → connector-stream CONFIG body |
| **Build / transform / choose the update-method / schedule** a **Workbench** on-prem ingestion job (desktop client) | **THIS skill** → *Workbench authoring-UX* § (`[KB]`, client-UI only, **no REST API**; the DataSet it lands + `updateMethod` → `domo-datasets.md`) |
| **Remotely *execute*** a **Workbench Enterprise** job by JWT (`/Api/Jobs/{jobId}/Execute`) | a separate REST surface, rank-38 — **not** the desktop-agent authoring here |
| **Run** a connector / read its run history / hit the commit throttle | `domo-datasets.md` → `POST .../streams/{id}/executions`, `GET .../history/aggregate` |
| Land raw CSV, choose `updateMethod`, read/query/delete a DataSet, PDP | `domo-datasets.md` |
| **Read a bound account's secret at runtime** in Code Engine | `domo-code-engine.md` (`getAccount().properties`, tokenless-vs-token rule) |
| A **human login**, an **OAuth client**, an **OAuth scope**, an audit trail | `domo-identity-access.md` |
| Publish a Pro Code bundle with **`domo publish` / ryuu CLI** | `domo-procode-app.md` |
| A **Workflow "Account" data-type input** or canvas **connection** | `domo-workflow.md` |
| DomoStats / Governance metadata **connectors** (metadata, not credentials) | `domo-governance-datasets.md` |

Tie-breaker: if the object being CRUD'd is a **credential**, it's this skill; if it's the **DataSet the connector produced** or the **run**, it's datasets; if it's a **person/token identity**, it's identity-access.

## Repo false friends (`[REPO]` — what a grep will surface that is NOT a Domo Account/connector)

If you grep this workspace for `account`/`connector`/`connection`, most hits are unrelated. All of the following are `[REPO]` and touch **no** platform Account/connector API:

- **`gl_account_id` / `GL_ACCOUNTS`** — general-ledger accounts in a `pl-summary-app` demo data generator.
- **Broker/trading "口座"** — marketdata `account_id`, brokerage margin/nisa/specific state; external broker objects, opposite meaning of a Domo account.
- **`connection status` FE flags** — `connected`/`demo`/`error` data-source UI state in inventory-management / safety-command-center / asset-lifecycle apps; a display flag, not a connector account.
- **`ryuu` / `domo publish`** — the Pro Code **publish** CLI (biggest false friend). `ryuu.js` (browser SDK for filters/variables) is yet another distinct thing.
- **DDX / Domo Bricks** — **Domo Bricks (formerly DDX Bricks)** code-app / viz objects (the in-product **Brick editor** *or* the local-bundle **Pro Code app**), not the connector IDE.
- **`window.alert()` / `role="alert"` / MCP "connector"** — UI noise and MCP toolkits; unrelated senses.
- **Governance `connectors`** (DomoStats / Governance Datasets) — Domo-native *metadata* connectors; access is connector→DataSet→query, owned by `domo-governance-datasets.md`.

**Verified in-repo:** no code in this workspace calls the platform `/v1/accounts` or `/api/data/v1/accounts` endpoints; the only grounded platform-account artifact is the `"type":"ACCOUNT"` **manifest binding** (news-summary-app). So "this repo doesn't exercise the Account API at runtime" is `[REPO]`-true; "the Account API doesn't exist / has no other ops" would be `[INFER]` — **do not** conflate repo-absence with API-absence.

## Do NOT claim as documented fact (hedge list)

The single failure mode for this skill is **over-claiming** — presenting a repo convenience or a reasoned guess as a documented contract. Everything below is `[INFER]`/`[KB]` and must be hedged or re-verified, never stated as fact:

1. **"There is no X account/connector endpoint"** — every universal negative here is at most `[INFER]` (catalog is non-exhaustive; `developer.domo.com` pages 405'd; Domo ships undocumented `/api/*`). State positively: "no documented X endpoint was reached."
2. **A `validate` / `test-connection` endpoint** on `/v1/accounts` — not in the reproduced spec; `[INFER]`.
3. **Inner per-connector `type.properties` keys + the connector-stream-config request body** — `[KB]`, re-verify live (they vary per Account Type / per connector). ⚠ The account create/update/share body **envelopes** (`{name, type:{id, properties}}`, `type.id` required on PATCH, share `{user:{id}}`) ARE schematized in `accounts.yaml` → `[DOC]`; only the *payload interiors* are not.
4. **`advancedScheduleJson` / schedule grammar** — `[KB]`, uncharted; capture from a live stream.
5. **The full list of account-types or their properties** — per-type, instance-dependent; fetch `/v1/account-types` live.
6. **OAuth scope enumeration** — the token-page enum lists six (`account`/`audit`/`buzz`/`dashboard`/`data`/`user`) `[DOC]`, but it is **not a closed set**: `workflow` is a real seventh scope (required by the `projects.yaml` prose `[DOC]`; returned in live token grants `[KB]`) that the enum omits. Do not state "exactly six." (Scopes belong to `domo-identity-access.md`.)
7. **The OAuth token endpoint** (`~api.domo.com/oauth/token`) — prose-only; exact method/params unsettled. **Never log it** (carries scope + Basic client creds). `[INFER]` on specifics.
8. **The manifest `"type":"ACCOUNT"` binding as an official schema** — `[REPO]`; the schema authority is `domo-procode-app.md`.
9. **Any account `id` as a portable value** (e.g. `865`) — instance-specific `[REPO]`; never a generic constant.
10. **Custom-connector / Workbench / DDX having a CRUD REST API** — `[KB]` behavior; no documented mutating endpoint.
11. **Product vs Platform field parity** — the two `accounts` worlds return different shapes; do not assume a field crosses over.
12. **Connector "connection" ≡ Workflow "Account" data type** — `[INFER]`; distinct senses, do not merge.
13. **Secrets readable via any Account API** — false; secret values are write-only in both worlds, runtime read is CE-only.

## Secret & safety handling

This surface is credentials-adjacent — the whole point of an Account object is to hold a secret. Handle accordingly:

- **Never log the OAuth token endpoint or its request** — the `client_credentials` call carries the client id+secret (Basic auth) and requested scope. Redact `Authorization` and body.
- **Never echo a dev token, Bearer token, or `client_secret`.** Pass auth via header/env only; verification code reads from `os.environ` or a curl header, never argv.
- **Secrets are write-only.** Do not attempt to read credential values back through any Account API — reads/creates omit them by design. Runtime access is CE `getAccount().properties` only (and stays in `domo-code-engine.md`).
- **Probe read-only first.** Before any account write, confirm auth+scope with a `GET /v1/accounts` (or product `GET /api/data/v1/accounts`) so you fail on a harmless read, not a mutation.
- **Account ids are instance-specific `[REPO]`** — never commit one as a generic value or into a shared artifact.
- **Prefer no destructive default.** `DELETE /v1/accounts/{id}` removes a shared credential that other assets may depend on; treat account deletion as high-blast-radius and gate it behind explicit human intent (mirrors the maintenance-instance "delete only self-owned test assets" rule).
- **Workbench (on-prem agent) is its own gated cluster.** RUNning a job is on-prem→cloud **data egress**; a Replace-method run is a destructive full-DataSet overwrite; and job create/edit/delete + credential mint/revoke + install/service-control + server-migration (which moves the local encryption key) are all human-gated. The full verb list and the never-commit set (WB5 OAuth tokens, WB4 Client ID/Secret, WB-Enterprise JWTs, ODBC/system-DSN passwords, the **Encrypted Key** file) live in the *Workbench authoring-UX* section above.

## Companion skills

- **`domo-custom-connector-authoring.md`** — *authoring* a custom/writeback connector in the Connector Dev Studio (the JS SDK, four-step build flow, report/parameter model, publish/review gate). This skill owns the Account credential + config + linkage + execution *around* a connector; it defers the connector-definition authoring mechanics there.
- **`domo-datasets.md`** — the DataSet a connector produces; Stream API (v1/v3), `updateMethod`, connector **execution** (`POST .../streams/{id}/executions`), run history, 15-min commit throttle, query/read, PDP. This skill hands off *the output and the run* here.
- **`domo-code-engine.md`** — runtime read of a bound account's secret (`getAccount().properties`, tokenless-`sendRequest`-vs-`getAccount` "one rule").
- **`domo-identity-access.md`** — human login accounts, OAuth **clients**, OAuth **scopes**, audit. The three-worlds host/auth pattern originates here.
- **`domo-procode-app.md`** — the manifest `"type":"ACCOUNT"` binding's schema authority; the `domo publish` / ryuu CLI (the top false friend).
- **`domo-workflow.md`** — the Workflow "Account" data-type input and canvas "connection" wiring.
- **`domo-governance-datasets.md`** — DomoStats / Governance metadata *connectors* (connector→DataSet→query path).
- **`domo-sandbox.md`** — a **connector** (its definition, not its data) is a promotable **content type** in the Governance Sandbox; that skill owns cross-instance/dev→prod promotion of content objects. This skill owns the Account credential + config + linkage + execution; promoting the connector definition between instances defers there. `[KB]`
- **`domo-beast-mode.md` / `domo-variables-filters.md`** — sibling client-side/definition surfaces sharing the same evidence-tier + naming-trap methodology.

**Reference memory:** the reproduced-spec + fetch-failure methodology (fetch failure = missing evidence, resolve via machine-readable spec) is the same one applied in ranks 7–10; see `project-domo-surface-skillization-cycle`.
