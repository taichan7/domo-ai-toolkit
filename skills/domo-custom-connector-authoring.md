# Domo Custom Connector Authoring (Connector Dev Studio JS SDK)

**Use this when** you are authoring — or reasoning about the mechanics of authoring — a **custom connector** or a **writeback connector** in Domo's browser-based **Connector Dev Studio** (builder URL `https://api.domo.com/builder/index.html`): its scriptable JavaScript SDK (`httprequest`, `datagrid`, `discovery`, `metadata`, `DOMO`, `auth`, `sql`, `aws`), the four-step build flow (icons → auth → reports → process-data), the report/parameter model, the publish-and-review gate, and the IDE's runtime limits. This is the **connector-DEFINITION authoring** surface — the code that *becomes* a connector.

**NOT for:**
- The stored **Account credential object**, the **Account API** (`/v1/accounts`), the **connector-CONFIG** stream body (`transport{CONNECTOR}`, `account.id`, `dataProvider.key`), the connector→account→DataSet **linkage**, running an already-built connector (`POST .../streams/{id}/executions`), Workbench, or the prebuilt-connector catalog → **`domo-accounts-connectors.md`**.
- Reading a **bound** account's secret at runtime from a Pro Code app / Workflow (`getAccount(id).properties`) — a different account object than this SDK's `metadata.account` → **`domo-code-engine.md`**.
- The REST **DataSet SQL query** API (`POST /api/query/v1/execute/{datasetId}`) — a different "query data" than the writeback SDK's `DOMO.queryData(...)` → **`domo-query-dataset.md`**.
- The **prebuilt Amazon S3 "Writeback"/Unload connector** (a Datacenter product connector with AssumeRole) — a different "writeback" than an *authored* Writeback Connector → **`domo-accounts-connectors.md` / `domo-export-to-s3.md`**.
- **DDX / Domo Bricks** code-app & viz authoring — **Domo Bricks (formerly DDX Bricks)**, whether authored in the in-product **Brick editor** (Monaco, *Card options → Edit Card*) or as a local-bundle **Pro Code app** (`domo publish`) → **`domo-procode-app.md` / `domo-procode-embedded-cards.md`**. (A different browser authoring surface than this Connector Dev Studio IDE.)

## What this skill OWNS vs DEFERS

| This skill OWNS | Defers to |
|---|---|
| The **Connector Dev Studio JS SDK** — the `httprequest` / `datagrid` / `discovery` / `metadata` / `DOMO` / `auth` / `sql` / `aws` namespaces used inside the auth, discovery, and process-data scripts (`[KB]`). | — |
| The **four-step build flow** (icon uploads → configure auth → configure reports / Advanced-Mode params → process data) and the **report/parameter model** (6 parameter types; discovery dropdown vs tree). | — |
| The **writeback connector** authoring shape (Domo-as-*source*: `DOMO.listDatasets/getDataset/queryData` + OAuth-2.0 back to Domo). | — |
| The **publish & review gate** as documented behavior (automated tests, security/perf/code review, self-publish eligibility). | — |
| The stored **Account credential**, Account API, connector-CONFIG stream body, connector→account→DataSet linkage, connector **execution**, Workbench, prebuilt catalog. | `domo-accounts-connectors.md` |
| Runtime read of a **bound** account's secret in a deployed app (`getAccount().properties`). | `domo-code-engine.md` |
| REST **DataSet SQL** `POST /api/query/v1/execute/{id}`. | `domo-query-dataset.md` |
| The **prebuilt S3 Unload / AssumeRole** "Writeback" product connector. | `domo-accounts-connectors.md` / `domo-export-to-s3.md` |
| **Domo Bricks (formerly DDX Bricks)** code-app / embedded-card authoring — in-product Brick editor **or** local-bundle Pro Code app. | `domo-procode-app.md` / `domo-procode-embedded-cards.md` |

## Evidence tiers

- `[DOC]` — reproduced from an official machine-readable OpenAPI spec / dev-portal reference.
- `[KB]` — documented product behavior from the doc-hub Connector-Dev-Studio pages (behavior, not a REST contract).
- `[REPO]` — observed only in this repository / on a live instance.
- `[INFER]` — reasoned, not sourced. Every universal negative is at best `[INFER]`.

**⚠ Whole-surface tier = `[KB]`, NOT `[DOC]`.** The Connector Dev Studio is a **browser-IDE scripting SDK with no mutating REST API of its own** — you author by typing JS into the builder, not by calling an endpoint. It is **absent from the `domo.com/docs/llms.txt` OpenAPI catalog**. Every SDK signature below is transcribed from the doc-hub prose/examples (`[KB]`); **none has been execution-verified** (zero connector runs were performed). A programmatic *create/edit-a-connector-definition* API is **not documented** — treat it as `[INFER]`, not "does not exist". A 404/405 while fetching a doc page is **MISSING evidence, never proof of absence**.

## Naming traps — READ FIRST

Four collisions send authoring tasks to the wrong surface. Resolve the term before reaching for a mechanism.

| You see | Reality | Owner | Tier |
|---|---|---|---|
| **`DOMO.queryData(datasetId, sql)`** (writeback SDK) | An in-IDE SDK call that runs SQL against a Domo DataSet while a *writeback* connector uses Domo as its source. **Not** the REST query API. | **THIS skill** | `[KB]` |
| REST **`POST /api/query/v1/execute/{datasetId}`** | The platform DataSet SQL endpoint — a real HTTP call, unrelated to the SDK method above. | `domo-query-dataset.md` | `[DOC]` |
| **"Writeback Connector"** (authored) | A connector you *build* in Dev Studio that reads Domo and writes to an external system. | **THIS skill** | `[KB]` |
| **"Writeback"/S3 Unload connector** (prebuilt) | A shipped Datacenter product connector (AssumeRole → S3). No authoring. | `domo-accounts-connectors.md` / `domo-export-to-s3.md` | `[KB]`/`[DOC]` |
| **"custom connector"** (authoring) | The Dev Studio connector-definition you write (this skill). | **THIS skill** | `[KB]` |
| **"custom connector"** (catalog pick) | Choosing an already-built connector in-product; its creds mint an Account object. | `domo-accounts-connectors.md` | `[KB]` |
| SDK **`metadata.account.{username,…}`** | The *authoring-time* credential object the IDE injects into your script from the auth config. | **THIS skill** | `[KB]` |
| **`getAccount(id).properties`** | The *runtime* read of a bound account's secret in a deployed CE/app — a different object entirely. | `domo-code-engine.md` | `[KB]` |

## The surface, in one line

You write **ES5 JavaScript** in a browser IDE; Domo runs it server-side and pipes whatever you push into `datagrid` into a DataSet. There is **no `XMLHttpRequest`** — all HTTP goes through the built-in `httprequest` object (https only). Auth-validation, discovery-parameter config, and data-processing are each their own script block sharing the same SDK. A connector defines one or more **reports** (endpoint/behavior choices the end-user picks); the chosen report name and any Advanced-Mode parameters arrive on the `metadata` object.

## The build flow (4 documented steps)

1. **Upload four brand images** — Icon *with* background 512×512 (png), Icon *no* background 512×512, Logo *with* background 512×512, Logo banner *no* background 1024×512.
2. **Configure authentication** — pick one of the schemes below; the IDE renders the credential form and injects entered values into `metadata.account`. An auth-validation script calls `auth.authenticationSuccess()` / `auth.authenticationFailed(msg)`.
3. **Configure reports** — each report is a named endpoint/behavior the end-user selects; the chosen name arrives as `metadata.report` (verbatim capitalization/spaces). Optionally **Enable Advanced Mode** to add custom parameters (⚠ once enabled it is **enabled forever**). Six parameter types: **String, Integer, Dropdown, Discovery, Text, Date selector**.
4. **Process data** — the JS that calls the API, parses the response, and writes rows via `datagrid`. Check **Create/Update Dataset** + **Run Script** to smoke-test into a real DataSet (⚠ that test DataSet is **unschedulable until the connector is published**).

## Authentication — the five documented schemes

`configure-authentication` enumerates **five** auth schemes (`[KB]`): **No authentication**, **Username & Password**, **API Key**, **OAuth 2.0**, and **Custom Account**. (⚠ `overview` says "four" and omits Custom Account — see contradictions below; prefer the five-enumeration but never bare-assert either count.)

- Entered credentials surface on `metadata.account` — documented keys seen across the examples include `username`, `password`, `apikey`, `clientKey`, `clientSecret`, `accesstoken`, `code`, `token`.
- **OAuth 2.0**: the IDE's redirect/callback is handled at `https://api.domo.com/builder/oauth.html`; the access token arrives as `metadata.account.accesstoken`. Self-publish is **not** available for OAuth-2.0 connectors (see gate).
- **API Key** flows can construct a JWT via `DOMO.jwtBuilder` / `DOMO.getJWT()` when the target API expects a signed token.

## Configure Reports & Advanced-Mode parameters

- A **report** is added by name; end-user selection arrives as `metadata.report`. Branch on it: `if (metadata.report == 'Opportunities') { … }`. The name is stored with the exact capitalization/spacing you type.
- **Advanced Mode** parameters arrive as `metadata.parameters["<<Parameter Name>>"]`. A **Date selector** parameter is read via `DOMO.getStartDate(metadata.parameters['Date'])` / `DOMO.getEndDate(...)`.
- **Discovery** parameter (an API call that populates the choices at config time):
  - **Dropdown** (single-select): `discovery.addOption(value[, label])`.
  - **Tree Menu** (multi-select checkboxes): `discovery.addNode(parentNode, name)` → returns a node, `discovery.addLeaf(parentNode, name)`, then `discovery.publishTree()` when done. The root parent is the constant **`discovery.tree`**. The user's selections arrive as a JS array on `metadata.parameters['<<Name>>']`.
  - ⚠ Self-publish is **not** available for connectors that use a discovery parameter (see gate).

## Process Data — the `datagrid` contract

For each report: compose the request → call the API via `httprequest` → parse → push rows.

- **Columns first:** `datagrid.addColumn(name, type)` where type ∈ `DATA_TYPE_STRING | DATA_TYPE_DOUBLE | DATA_TYPE_DATETIME | DATA_TYPE_DATE`.
- **Then rows, cell by cell:** `datagrid.addCell(value)` … and **`datagrid.endRow()` is required to close every row** (the single most-missed step in the docs' own examples).
- **Dates must be `yyyy-MM-dd'T'HH:mm:ss`.** A bare `yyyy-MM-dd` value needs a `'T00:00:00'` suffix before `addCell`.
- **Shortcut:** if the endpoint returns clean CSV/JSON/XML, `datagrid.magicParseCSV(str)` / `magicParseJSON(str)` / `magicParseXML(str)` parses *and* stores in one call — skipping the manual column/row loop.
- **Report error:** `datagrid.error(code, message)` fails a report gracefully (use it in the `else` branch when `metadata.report` is unrecognized).
- **Pagination:** loop `httprequest.get(...)` calls yourself; there is no built-in pager.

## The JS SDK namespaces (reference map — `[KB]`, signatures not execution-verified)

| Namespace | Key members (as documented) |
|---|---|
| `auth` | `authenticationSuccess()`, `authenticationFailed(message)` — called from the auth-validation script. |
| `httprequest` | `get(url)`, `post(url[, body])`, `put(url, body)`; `addHeader(k,v)`, `addParameter(k,v)`, `clearHeaders()`, `clearParameters()`, `getHeader(k)`, `getResponseHeader(k)`, `getStatusCode()`. **All URLs https; no `XMLHttpRequest`.** |
| `datagrid` | `addColumn(name,type)`, `addCell(value)`, `endRow()`, `error(code,msg)`, `magicParseCSV/JSON/XML(str)`; type constants `DATA_TYPE_STRING/DOUBLE/DATETIME/DATE`. |
| `discovery` | `tree` (root const), `addOption(value[,label])`, `addNode(parent,name)`, `addLeaf(parent,name)`, `publishTree()`. |
| `metadata` | `account{…}`, `report`, `days`, `parameters{}`, `baseurl` (writeback adds `parameters.datasetId`). |
| `DOMO` | `log(...)`, `sleep(ms)`, `getState()/setState()`, `parseXML(str)`, `getStartDate(p)/getEndDate(p)`, `b64EncodeUnicode/b64DecodeUnicode`, `hmacSHA1/hmacSHA256`, `md5`, `getJWT()`, `jwtBuilder{algorithm(HS256/RS256/ES256), authKey, issuer, subject, claims[], expiration}`. |
| `sql` | `createTable/select/insert/update/delete/export` — an in-connector store that **persists between runs only when "Save Database Between Runs" is checked**. |
| `aws` | `createClient(region, key, secret)`, `put(path, name, value)`, `get(path, name)`. |

The **`DOMO.log`/`console.log`/`alert`** helpers are debug aids — strip them before submit (see safety).

## Writeback connectors (Domo as the *source*)

A **writeback connector** (authored under `/Writeback-Connectors/`) inverts the flow: it *reads* a Domo DataSet and pushes to an external system. Extra SDK members (writeback-only, `[KB]`):

- `DOMO.listDatasets()` — enumerate accessible DataSets.
- `DOMO.getDataset(datasetId)` — metadata for one.
- `DOMO.queryData(datasetId, sqlQuery)` — run SQL against a DataSet **inside the IDE** (⚠ *not* the REST `/api/query/v1/execute/{id}` endpoint — see naming traps).
- The selected DataSet arrives as `metadata.parameters.datasetId`; auth back to Domo is OAuth-2.0 (Client Key / Secret). Because it egresses Domo data outward, treat a published writeback connector's run as a **data-egress execution** (human-gated).

## Publish & review gate (documented behavior — facts, not actions)

Submitting a connector runs it through a **review pipeline** (`[KB]`):

1. **Automated tests** — code must: use `httprequest.get/post` **not** `XMLHttpRequest`; **not** be minified; carry **no hard-coded credentials**; **not** redirect data to an external API.
2. **Security test** — Domo engineers verify security protocols.
3. **Performance test** — must process **> 1000 records / 5 min**.
4. **Code review** — a Domo developer reviews readability/cleanliness.

Visibility is **Shared-with-company** (private URL, not listed in Data Center) or **Public-to-all-companies**. **Self-publish is NOT available** for connectors that use **OAuth 2.0** or a **discovery** parameter. During review the process-data code is **View-Code read-only**; withdraw via **View Status → Withdraw**. OAuth-2 submissions must include a test username/password in *Additional Instructions* (⚠ human-gated: never paste real creds into a committed artifact).

## IDE-only limitations (do not carry into published behavior)

Per `ide-limitations` (`[KB]`) — these constrain the **in-browser IDE only**, not the published connector:

- Variables set in the **auth** section are not visible in the **process-data** section while testing in the IDE.
- "Show when" parameter conditions do not take effect inside the IDE.
- A response that is very large or slow can surface a **"500 proxying"** error in the IDE — paginate / narrow the test window.
- No response streaming in the IDE; `DOMO.log` output is capped — use `console.log` for heavy debugging (and strip all logging before submit).

## Three documented source-doc contradictions — do NOT silently resolve

The doc set contradicts itself in three places. Preserve each as a flagged conflict; never launder one side into a bare fact.

1. **Runtime engine — UNRESOLVED.** The `connector-dev-studio` landing page says **Java 17 GraalVM**; the `process-data` page says **Java 8 Nashorn**. Both agree on the **load-bearing** contract — code must be **ES5**, **no `XMLHttpRequest`**, HTTP via `httprequest` — which is what actually constrains your code. The underlying engine is a source-doc conflict; record it as **unresolved (`[KB]`)** and assert only the ES5/no-XHR invariant as fact.
2. **Auth-scheme count.** `configure-authentication` enumerates **five** (No-auth, Username+Password, API Key, OAuth 2.0, Custom Account); `overview` says **four** and omits Custom Account. Prefer the five-enumeration; state the discrepancy; never bare-assert a count.
3. **Trial vs review SLA.** The FAQ (`help-and-support`) gives a **14-day self-publish trial** and a **30-day review SLA**; `overview` and `publish-connector` sloppily call the self-publish trial "30 days" (conflating trial with SLA). Prefer the FAQ split, treat as **volatile policy** (hedge or omit), and never assert a "30-day self-publish trial".

## Do NOT claim as documented fact (hedge list)

The single failure mode is **over-claiming** — and wrongly declaring the surface "fully owned / exhausted" is an equally-bad under-claim. Everything below is `[KB]`/`[INFER]` and must be hedged:

1. **The whole surface is `[KB]`, not `[DOC]`** — no OpenAPI spec, absent from `llms.txt`; there is **no mutating REST API** for authoring.
2. **Every SDK signature here is transcription, not execution-verified** — zero connector runs were performed; treat member lists as documented-but-untested, and re-confirm arity/return against a live IDE before relying on it.
3. **Programmatic create/edit of a connector *definition*** — **not documented** (`[INFER]`); the studio is a browser IDE, not an API. Do not claim such an endpoint exists *or* that it definitively does not.
4. **No exhaustion / "fully owned" claim** — the doc set is non-exhaustive and the `reference` page is long; more members may exist. A 404/405 = MISSING evidence, not absence.
5. **The three contradictions** (engine / auth-count / trial-SLA) must stay flagged, never silently resolved.
6. **`sql` / `aws` / `DOMO.getState` persistence semantics** — `[KB]` and lightly documented; `sql` persists only with "Save Database Between Runs" checked, and the rest is best confirmed empirically.

## Secret & safety handling

This surface is **credential-adjacent and, once published, executes real HTTP + writes**. Documentation work here is inert (this skill runs nothing), but the reader's action-verbs are live executions — treat them as **human-gated**.

- **⚠ Do NOT reproduce the docs' own logging anti-pattern.** The official examples do `DOMO.log('metadata.account.password: ' + metadata.account.password)` (and `.username`, `.apikey`, `.clientSecret`). **`DOMO.log` leaks secrets** into IDE/console output — never write credential values to any log, and strip *all* debug logging before submit (the review's automated test also flags this).
- **Never hard-code credentials** in connector code; read them from `metadata.account` (authoring) / the bound account at runtime. Frame `metadata.account.{…}` as **runtime-injected values**, not literals to embed.
- **Reader action-verbs are human-gated EXECUTIONS**, not autonomous steps: submitting / self-publishing a connector, minting a JWT (`DOMO.getJWT`), any `httprequest` egress to a third party, `aws.put`, and writeback `DOMO.queryData` all *do something*. Document them; do not perform them without explicit human intent.
- **The publish/review pipeline is documented behavior, not an action you take here** — describe the gate; don't submit anything.
- **Never commit** real tokens, API keys, client secrets, OAuth codes, JWTs, or the OAuth test-user creds a submission requires — placeholders only.

## Companion skills

- **`domo-accounts-connectors.md`** — the stored Account credential, Account API, connector-CONFIG stream body, connector→account→DataSet linkage, connector **execution**, Workbench, and the prebuilt catalog. This skill hands off everything *around* an authored connector to it; it defers connector-*authoring* mechanics here.
- **`domo-code-engine.md`** — runtime read of a bound account's secret (`getAccount().properties`); a different account object than this SDK's `metadata.account`.
- **`domo-query-dataset.md`** — REST DataSet SQL (`/api/query/v1/execute/{id}`); the naming twin of writeback `DOMO.queryData`.
- **`domo-accounts-connectors.md` / `domo-export-to-s3.md`** — the prebuilt S3 "Writeback"/Unload product connector; the naming twin of an *authored* writeback connector.
- **`domo-procode-app.md` / `domo-procode-embedded-cards.md`** — **Domo Bricks (formerly DDX Bricks)** code-app & viz authoring, both the in-product Brick editor and the local-bundle Pro Code app (a different browser authoring surface than the Connector Dev Studio IDE).

**Reference memory:** the whole-surface-`[KB]` + fetch-failure-is-missing-evidence + preserve-source-contradictions methodology is the cycle standard; see `project-domo-surface-skillization-cycle`.
