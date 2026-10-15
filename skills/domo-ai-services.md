# Domo AI Services API Skill

Use this when a task **calls Domo's built-in LLM/AI operations** — text generation, summarization,
text-to-SQL, Beast-Mode generation, sentiment/classification, entity extraction, chat/tool-use, image-to-text
(OCR/vision), or text/image **embeddings** — whether from a Pro Code app, a Code Engine function, a server
script, or the direct REST API. Unlike most surfaces this cycle has skill-ized, Domo AI Services is a **large,
genuinely documented island**: the "AI Services API" ships as a first-party OpenAPI spec. But it is
documented across **two API worlds** that differ in host, auth, **and the response field you must read**, and
the single most damaging mistake is issuing the same `text/generation` call in one world and parsing the
response as if you were in the other (you get `undefined` and a silent fallback, not an error). Around that
documented island sits a `[REPO]` sea this repo actually leans on — a Code-Engine OCR path, an undocumented
AI-readiness data-dictionary, an MCP-toolkit path — plus an **Agent Catalyst** feature that has **no
documented REST CRUD/run API at all**. This skill keeps the worlds apart, marks exactly where the documented
island ends, and stops the tempting over-claims (that the `:anthropic` model suffix is a documented privacy
contract, that there's a model-list or agents REST endpoint, that a fixed credit-per-op number is published).

Scope boundaries — use the neighbor skill instead when:

- it's the **Magic ETL `TextGeneration` (Text/AI) tile** inside a dataflow (the in-ETL AI node, its
  `structuredOutput`/`outputColumns`, the 100-row batch behavior) → [`domo-magic-etl.md`](domo-magic-etl.md)
  **owns that**. It is a *separate surface* from the REST/proxy AI Services this skill covers — cross-ref
  only, below;
- it's authoring or running an **AI Agent** (Agent Catalyst): the agent is **UI-authored in the Workflow
  builder** and runs as a **Workflow step** → [`domo-workflow.md`](domo-workflow.md). There is **no agent
  REST API** (see the Agent Catalyst section);
- it's driving Domo's hosted **MCP toolkits** (agent-side tools, `assistant/mcp/toolkits`) →
  [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md);
- it's the **Code Engine auth mechanic** — the tokenless `send_request`/`sendRequest` that the in-repo
  server-side AI calls ride on → [`domo-code-engine.md`](domo-code-engine.md);
- it's **RAG grounding over unstructured files** (upload/search/query documents, then feed the AI) →
  [`domo-filesets.md`](domo-filesets.md) owns the file side; this skill owns the generation/embedding call.

## Evidence tiers

Every load-bearing line below carries a tier. Anything `[REPO]`, `[KB]`, or `[INFER]` must be re-verified
live against the target instance and the current docs before you depend on it — model IDs, admin-enabled
providers, credit rates, and per-endpoint body fields are instance-config-, plan-, and version-dependent.

```
[DOC]   Official Domo docs — the docs portal (domo.com/docs/portal), the App Framework
        API reference, or the machine-readable AI-Services OpenAPI YAML in Domo's own
        doc-hub (linked from domo.com/docs/llms.txt). Two DOC sub-classes below:
        /docs/portal/ + the OpenAPI (developer API) vs /docs/s/article/ KB pages ([KB]).
[KB]    Domo Knowledge Base / support help center. Product behavior: which features
        exist, AI-model management UI, Agent-builder framing, limits. Not the API ref.
[REPO]  Verified only against this repo's working usage on a live instance — NOT in
        public docs. Undocumented; re-verify per instance/version. (AI Services has
        heavy repo usage — CE OCR, readiness dictionary, ETL tiles — so this tier is
        richly populated.)
[INFER] Reasoned from the documented model, community sources, marketing/press, or the
        ABSENCE of a documented endpoint — plausible, not first-party. Verify live.
```


**Amended 2026-09-06 (rank-64 — pending-fold application, `[DOC]`).** The four AI-Service-family *subset*
specs (`product/service.yaml` 540ln, `framework/service.yaml` 337ln, `product/aiservices.yaml` +
`product/iaservices.yaml` 333ln each) were re-fetched byte-stable and adversarially re-verified (11-agent
workflow; all 4 negative controls refuted). **7 of 8** candidate folds were applied — 5 full/tier-upgrade, 2
trimmed — and **1 dropped**: a framework spec *omitting* a security block is auth-**unspecified** in OpenAPI,
**not** positive documentation of tokenlessness (World-B tokenlessness is already `[DOC]` here). The applied
material lives in the **Image-to-text** row (base64-only), the **"Request-body details from the subset specs"**
subsection, and the **name-collision** guard. These subset specs are a strict endpoint SUBSET of the
capitalized `AI-Services.yaml` — they refine request-body machinery, they do **not** supersede its 13-endpoint
set.

## The headline: two documented API worlds + a server-side [REPO] sea

Domo AI Services is documented — the `AI-Services.yaml` OpenAPI (linked from `domo.com/docs/llms.txt`)
enumerates **13 endpoints** under `/api/ai/v1/…`. The island is large; the trap is not "does an API exist"
but **which of two worlds you are in**, because the *same operation* (`text/generation`, `text/sql`,
`image/text`) is documented in both — with a different path prefix, a different credential, **and a different
response field to read**.

- **World A — Product / Direct REST `[DOC]`.** `POST https://{instance}.domo.com/api/ai/v1/…`, auth
  `X-DOMO-Developer-Token` (OpenAPI security scheme `domo-developer-token`). Response is `TextAIResponse` —
  the populated field is **`output`** (top-level). `choices` is present but **`deprecated: true`**. This is
  the world for server scripts and Code Engine.
- **World B — App Framework "AI Service Layer" `[DOC]`.** In-app `domo.post('/domo/ai/v1/…')`, **tokenless**
  (rides the iframe session). Response is `{prompt, choices:[{output}], modelId, isCustomerModel}` — the
  populated field is **`choices[0].output`**; top-level `.output` is empty/undefined on this proxy (a
  `[REPO]` behavior detail, below). This is the world for a Pro Code app's front-end.

Then the **`[REPO]` sea** the repo actually leans on (undocumented, re-verify): a Code-Engine OCR call to a
**bare** `api/ai/v1/image/text` (no leading slash, no `/domo/`), an **AI-readiness data-dictionary**
(`/api/ai/readiness/v1/data-dictionary/…`, absent from the AI-Services spec), and an **MCP toolkit** path
(`/api/ai/v1/assistant/mcp/toolkits/…`, single-instance).

And the **guards** (`[INFER]`/`[KB]`): **Agent Catalyst has no REST CRUD/run API** (agents are UI-authored,
run as Workflow steps); there is **no model-list REST endpoint** (model management is a settings UI); the
**`:anthropic` model suffix is not a documented privacy/routing contract**; and there is **no published
credit-per-operation number** you can quote as fact.

The one-sentence anchor: **same call, two worlds — World A reads `output`, World B reads `choices[0].output`;
read the wrong one and you get `undefined` and a silent canned fallback, not an error.**

## Two worlds: match host + auth + response field (the #1 mistake)

Read this table before writing any AI call. The response-field column is the part that silently bites.

| World | Path prefix | Host | Auth | Read the answer at | Tier |
|---|---|---|---|---|---|
| A — Product / Direct REST | `POST /api/ai/v1/…` | `{instance}.domo.com` | `X-DOMO-Developer-Token` (OpenAPI scheme `domo-developer-token`) | **`resp.output`** (top-level; `choices` is `deprecated:true`) | `[DOC]` |
| B — App Framework proxy | `domo.post('/domo/ai/v1/…')` | in-app (iframe) | **tokenless** (session) | **`resp.choices[0].output`** (`resp.output` is empty on this proxy) | `[DOC]` shape / `[REPO]` the empty-`.output` |
| C — Code Engine server | `ce.send_request('POST','api/ai/v1/…')` | in-app CE runtime | **tokenless** (`send_request`) | parse **defensively** (`text`/`output`/`content`) | `[REPO]` |

Rules that fall out of the table:

- **Host is `{instance}.domo.com`, never `api.domo.com`.** The AI-Services OpenAPI server is
  `https://{subdomain}.domo.com`. There is **no AI endpoint documented on `api.domo.com`** (the Platform-OAuth
  host) — that "AI can't run on `api.domo.com`" statement is `[INFER]` from absence, so phrase it as *not
  documented there*, not *impossible*.
- **Path prefix decides auth.** `/api/ai/v1/…` = World A (dev-token). `/domo/ai/v1/…` = World B (tokenless
  iframe). A Code Engine call uses the World A path **without** a leading slash and **without** a token
  (`send_request` runs as the invoking user) — that's World C, `[REPO]`.
- **The response field is world-specific.** World A populates `output`; World B populates `choices[0].output`
  and leaves `output` empty. Do **not** assume one shape across worlds — see the response-shape trap.
- **`choices` is deprecated, not fake.** It *is* in the OpenAPI (`deprecated: true`). Earlier lore that "the
  proxy invented `choices`" is wrong — the narrow true fact is only that World B's proxy fills `choices`, not
  `output`.

## Documented surface #1 — Product/Direct REST on `{instance}.domo.com` (dev-token) `[DOC]`

The first-party "AI Services API". Host `https://{instance}.domo.com`, header `X-DOMO-Developer-Token`,
`Content-Type: application/json`. OpenAPI: `domo.com/docs/openapi/product/AI-Services.yaml` (indexed by
`domo.com/docs/llms.txt`). The spec enumerates **13 POST endpoints** — all `[DOC]` by existence, host, and
auth; treat per-endpoint **body field required/optional** as re-confirm-against-live-YAML:

| Op | Endpoint | Body highlights (re-confirm field-level) | Tier |
|---|---|---|---|
| Text generation | `POST /api/ai/v1/text/generation` | `input` (the prompt); `model` optional (admin default when omitted); `system`/`modelConfiguration` (temperature/max-tokens) — exact names re-verify | `[DOC]` |
| Text summarize | `POST /api/ai/v1/text/summarize` | `input` + `outputStyle` (`BULLETED`/`NUMBERED`/`PARAGRAPH`) + `outputWordLength {min,max}` | `[DOC]` |
| Text-to-SQL | `POST /api/ai/v1/text/sql` | `input` + `dataSourceSchemas[]` `{dataSourceName, description, columns:[{type,name,description}]}`; **World-A `dataSourceSchemas` is REQUIRED** (`APITextToSQLRequest.required = [input, dataSourceSchemas]`), soft/optional in-app — see the subset-spec note below | `[DOC]` |
| Text-to-Beast Mode | `POST /api/ai/v1/text/beastmode` | generates a Beast Mode formula from NL — this endpoint **is** in the spec (not marketing) | `[DOC]` |
| Sentiment | `POST /api/ai/v1/sentiment` | classify sentiment | `[DOC]` |
| Targeted sentiment | `POST /api/ai/v1/targeted-sentiment` | aspect/entity-level sentiment | `[DOC]` |
| Classification | `POST /api/ai/v1/classification` | classify text into labels | `[DOC]` |
| Extract | `POST /api/ai/v1/extract` | structured entity extraction | `[DOC]` |
| Chat | `POST /api/ai/v1/messages/chat` | Anthropic-messages-style **multi-turn chat** — existence `[DOC]`; body/response shape not captured this pass | `[DOC]` (existence) |
| Tool use | `POST /api/ai/v1/messages/tools` | messages + **tool-use**; existence `[DOC]`; shape re-verify | `[DOC]` (existence) |
| Image-to-text | `POST /api/ai/v1/image/text` | vision/OCR; `ImageToTextRequest` required `{input,image,model}`; `image` = an `ImageData` object — **base64-only** (`mediaType` one of image/png, image/jpeg, image/jpg, image/gif, image/webp; `type`=base64; `data`=base64 **without** a `data:` URL prefix — no URL-input option in the subset specs) | `[DOC]` |
| Text embedding | `POST /api/ai/v1/embedding/text` | returns `EmbeddingAIResponse {embeddings:[[float]], modelId, modelProviderUsage}` | `[DOC]` |
| Image embedding | `POST /api/ai/v1/embedding/image` | image vector embeddings | `[DOC]` |

**`TextAIResponse` (text ops) `[DOC]`** — fields: `prompt`, `choices` (**`deprecated: true`**), `modelId`,
`sessionId`, `output`, `modelProviderUsage`. Read **`output`** in this world. `sessionId` and
`modelProviderUsage` (token counts) **are** documented response fields — but a portable multi-turn session
built by threading `sessionId` back in is **not** confirmed; for real chat use the `messages/chat` endpoint,
and hedge `sessionId` reuse (`[INFER]`).

**`isCustomerModel`** appears on the App-Framework response; docs state only the true-direction ("if a model
was specified, `isCustomerModel` is true") — the complement (default ⇒ false) and "customer vs Domo model"
reading are `[INFER]`.

Notes: the two `messages/*` and the `embedding/*` endpoints are **unused in this repo** — they're documented
but unproven here, so verify shapes live before depending on them.

### Request-body details from the AI-Service *subset* specs `[DOC]`

The capitalized `AI-Services.yaml` above is the 13-endpoint World-A source. Three **smaller** first-party specs
add request-body machinery its summarizer read did not surface — `product/service.yaml` (540ln, "Domo AI
Services API", **both worlds**), `framework/service.yaml` (337ln, "AI Service Layer API", **World-B only**), and
the World-A subset `product/aiservices.yaml` (333ln). All `[DOC]`, transcribed byte-level from those bodies:

- **`promptTemplate` + `parameters` (template substitution).** A `PromptTemplate` schema `{template: string}`
  whose template string carries `${input}`, `${system}`, and named `${…}` placeholders, plus a sibling
  `parameters` map (`type: object`, `additionalProperties: {type: string}`) that fills them (e.g.
  `parameters: {language: "Japanese"}`). Documented on **generation and text/sql in BOTH worlds**;
  **`summarize` is World-A-only** — `framework/service.yaml` has **no** summarize endpoint at all (so there is
  no in-app `/domo/ai/v1/text/summarize`; do **not** claim the template mechanism on an in-app summarize).
- **`modelConfiguration` + `system` — a documented World-A/World-B request-shape split.** The World-A
  `APITextGenerationRequest` / `APITextToSQLRequest` / `TextSummarizationRequest` declare `modelConfiguration`
  (`type: object`, `additionalProperties: true` — "e.g. temperature, max_tokens") and a `system` field; the
  World-B `AppTextGenerationRequest` / `AppTextToSQLRequest` variants declare **neither**. Read this as a
  *documented per-spec request-shape difference*, **not** as "you cannot set temperature in-app" (a field's
  absence from the App request schema ≠ a capability impossibility — re-verify live before concluding either).
- **`dataSourceSchemas` is REQUIRED for World-A text/sql** (`APITextToSQLRequest.required = [input,
  dataSourceSchemas]`), but the World-B `AppTextToSQLRequest` requires only `input`. (Resolves the surface-#1
  `[INFER]` "whether `dataSourceSchemas` is required is soft" hedge: required for World A, soft/optional in-app.)
- **`DataSourceColumn.type` — TWO conflicting enum sets; do NOT canonicalize.** `product/service.yaml` uses
  UPPERCASE `[STRING, LONG, DECIMAL, DOUBLE, DATE, DATETIME]`; `framework/service.yaml` uses lowercase
  `[string, number, date, datetime, boolean]` (note `number`/`boolean`, which have no uppercase counterpart).
  Record both; do not present either as *the* single canonical column-type enum.

## Documented surface #2 — App Framework "AI Service Layer" in-app `/domo/ai/v1` (tokenless) `[DOC]`

The in-app world a Pro Code app's front-end uses. Documented on the App Framework "AI Service Layer API"
reference page. Call via `domo.post('/domo/ai/v1/…', body)` — **tokenless** (the SDK rides the iframe's
session; no `X-DOMO-Developer-Token`, no `client_secret`). This is the correct surface for browser-side code
and the one every Pro Code app in this repo uses.

**Documented in-app endpoints `[DOC]`** (the ones the AI-Service-Layer page shows + the repo exercises):

| Op | In-app call | Tier |
|---|---|---|
| Text generation | `domo.post('/domo/ai/v1/text/generation', {input, model?})` | `[DOC]` |
| Text-to-SQL | `domo.post('/domo/ai/v1/text/sql', {input, dataSourceSchemas?})` | `[DOC]` |
| Image-to-text | `domo.post('/domo/ai/v1/image/text', {…})` | `[DOC]` |

**In-app response `[DOC]`:** `{prompt, choices:[{output}], modelId, isCustomerModel}` (the subset specs name
this schema **`AppAIResponse`**; their leaner World-A response schema is **`AIResponse`** — distinct from the
capitalized `AI-Services.yaml`'s richer `TextAIResponse`; the names are cited here, the shape is unchanged) — read
**`choices[0].output`**. (The Product-REST top-level `output` field is **empty/undefined** through this
proxy — see the trap.)

**Do NOT assume the full 13-endpoint set is proxied under `/domo/`.** The AI-Service-Layer page firmly
documents generation / sql / image-text; whether `summarize`, `beastmode`, `sentiment`, `messages/*`,
`embedding/*` are also reachable at `/domo/ai/v1/…` is **`[INFER]`** — re-verify per endpoint before calling
it in-app. The 13-endpoint list is confirmed for **World A** (`/api/ai/v1/…`), not automatically for World B.

**`chatContext` `[KB]`.** The AI-Service-Layer / Workflow-AI-function docs describe a `chatContext`
(conversation-history) request field for multi-turn — that's the documented multi-turn hook at the
app/workflow layer. Treat its exact placement as `[KB]`/re-verify; do not assume it on the bare
`/api/ai/v1/text/generation` REST body.

## The response-shape trap: `output` vs `choices[0].output`

This is the highest-frequency real bug on this surface, and it is **silent** — a wrong read yields
`undefined`, which most code turns into a canned fallback string, so it *looks* like the model returned
boilerplate rather than erroring.

- **World A (Product REST, dev-token):** answer is at **`resp.output`**. `resp.choices` exists but is
  `deprecated`.
- **World B (in-app `/domo/` proxy):** answer is at **`resp.choices[0].output`**. `resp.output` is
  **empty/undefined** here — this is the `[REPO]`-observed proxy behavior.
- **World C (CE `send_request`):** the repo reads **defensively** — e.g. `resp.get('text') or
  resp.get('output') or resp.get('content')` — because the bare-path/tokenless response shape is not
  doc-guaranteed for this path.

**Robust parse for code that might run in either world:**

```js
// works whether output (World A) or choices[0].output (World B) is populated
const text = resp.output || resp.choices?.[0]?.output || resp.text || resp.content || '';
if (!text) { /* real error path — do NOT silently fall back to canned copy */ }
```

**Known latent bug to watch for `[REPO]`:** `u2s-doc-summary-app/pro-code/app.js` reads `response.output`
against the **in-app** proxy — where `.output` is empty — so it lands on its canned fallback. If you see an
in-app AI call always returning boilerplate, check for a bare `.output` read; switch to `choices?.[0]?.output
?? output`. Do not copy the bare-`.output` pattern from that app.

## Models & model IDs — instance-config, Admin-enabled, drift-prone

**`model` is optional.** Omit it and the endpoint uses the instance's admin-configured default. Supply it to
pin a specific model — but a hardcoded model ID may `4xx` if an Admin has not enabled it on that instance.

**Documented example model IDs `[DOC]`** (as *examples* in the docs — not a guaranteed catalog):
`domogpt-chat-small-v1`, `domogpt-summarize-v1`, `domogpt-sql-v1:anthropic`, and the image example
`domo.domo_ai.domogpt-chat-medium-v1.1:anthropic`.

**Repo-used IDs `[REPO]`** (in dataflow tiles / configs, re-verify per instance):
`domogpt-medium-v2.1:anthropic`, `domogpt-medium-v2.2:anthropic`, `domogpt-chat-medium-v1.1`.

**Do NOT generalize a portable `domogpt-<role>-v<N>` pattern** as documented — only the literal example IDs
are `[DOC]`; the naming *scheme* is `[INFER]`. Model IDs **drift** across instances and dates and are
**Admin-enabled**; treat any specific ID as instance/date-scoped config, not a constant.

**The `:anthropic` (and similar provider) suffix is a provider tag, not a documented privacy/routing
contract.** "Your prompt is sent to Anthropic/Claude" is `[INFER]` from the suffix — the KB pages fetched
during verification carried **no** data-residency/provider-routing statement. Never present provider routing
or data handling as a documented guarantee to a customer.

**There is no model-list REST endpoint in the AI Services spec `[DOC-absence]`.** The community-cited
`/api/ai/v1/settings/services/{service}/models` is `[INFER]` (forum-only), and model management is an **admin
settings UI** ("Manage AI Models and Projects") `[KB]`, not a REST catalog you enumerate. BYO/customer models
(e.g. OpenAI, Hugging Face, a Domo-hosted Jupyter model) are configured there `[KB]`; the exact provider list
is `[KB]`/re-verify.

## Agent Catalyst — no documented REST CRUD/run API

"Agent Catalyst" is Domo's **brand/marketing name** for building AI agents — it is **not an API namespace**,
and this is the highest-value guard on the surface: **do not invent `/api/ai/v1/agents` or an agent-run REST
endpoint.** The `AI-Services.yaml` spec defines **no** agent CRUD and **no** model-list endpoint (confirmed
by directly enumerating the spec's paths).

How agents actually work:

- **Authored in the UI `[KB]`.** Agents are built inside the **Workflow builder** ("Add action > AI Agent
  Task"), configured with instructions / knowledge / tools — a UI flow, not a REST payload. Framing and the
  four-step build are `[KB]`/marketing (`[INFER]` for specifics).
- **Run as a Workflow step.** An agent executes inside the enclosing Workflow; you start the *workflow* via
  the documented Workflows API `POST /api/workflow/v1/instances/message` (`[DOC]`, owned by
  [`domo-workflow.md`](domo-workflow.md)) — but "trigger the workflow = run the agent" is `[INFER]`; there is
  no documented endpoint that runs *an agent* directly.
- **Execution limit `[KB]`:** an agent/Workflow step has an execution time limit (≈1 hour) — re-verify the
  current number.
- **"No agents REST API" is `[INFER]` from absence** (plus confirmed absence from the AI-Services spec).
  Phrase it as *none is documented*, and cross-ref [`domo-workflow.md`](domo-workflow.md) /
  [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md) for the surfaces that *do* have contracts.

The repo has AI-Agent **provisioning concepts** in Workflow definitions (e.g. `aiAgentEmailToolCount`,
`aiAgentDatasetContextCount` assertions in `inventory-management-app/tests/test_provisioning.py`) — that is
Workflow-node config `[REPO]`, not an AI-Services API.

## The server-side `[REPO]` sea — what this repo actually calls

Around the documented island, this repo relies on three undocumented AI-namespaced paths. All are `[REPO]`:
undocumented, re-verify per instance/version, **never cite as a documented contract**.

| Path | Where it's called | What it does / gotcha | Tier |
|---|---|---|---|
| `POST api/ai/v1/image/text` (**bare** — no leading `/`, no `/domo/`) | `news-summary-app/code-engine/fileset_ops.py` (~L3633; comments L2904/L3597) via `ce.send_request("POST", …)` | server-side OCR/vision from Code Engine, **tokenless** (invoking user). The bare-path form + tokenless-CE behavior is a CE mechanic, not the documented World-A shape. | `[REPO]` |
| `GET`/`PUT api/ai/readiness/v1/data-dictionary/dataset/{id}` | `ai-metadata-generator-app/code-engine/ai_metadata_utils.py` (L22 const, GET L154, PUT L256) | read/write a dataset's AI **data dictionary** (column descriptions for AI readiness). **Absent from `AI-Services.yaml`** → undocumented. **PUT must NOT wrap the body in a `dataDictionary` key** (else `400`). | `[REPO]` |
| `api/ai/v1/assistant/mcp/toolkits/{toolkit}` (header `X-Domo-Authentication` SID) | single-instance (maintenance-instance) MCP work → [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md) | drive a hosted MCP toolkit. `assistant/mcp` is AI-namespaced but `[REPO]`/instance-specific. | `[REPO]` |

The "AI Readiness / data dictionary" **feature** is `[KB]` (it exists as a product capability), but the
`/api/ai/readiness/v1/…` **endpoint shape** is `[REPO]` only — proven here, not in the doc-hub. When the
first documented readiness endpoint appears, promote it and drop the "undocumented" label.

## Magic ETL AI tiles are a separate surface (cross-ref `domo-magic-etl.md`)

The Magic ETL **`TextGeneration` (Text/AI) tile** is a *different surface* from the REST/proxy AI Services
above — it runs AI **inside a dataflow** as a node, not as an HTTP call you issue. Full mechanics live in
[`domo-magic-etl.md`](domo-magic-etl.md); this section is only the cross-ref + the tier correction.

- **Tile shape `[REPO]`:** `modelId` (a **UUID**, not a `domogpt-*` string), `temperature`, `instructions`,
  `prompt`, `structuredOutput`, `outputColumns`, and a `TEMP_VIEW` input. See
  `inventory-management-app/scripts/provision_domo.py` (~L517) and `pl-summary-app/scripts/provision_domo.py`
  (L363/L378).
- **Dataflow `modelId`s `[REPO]`:** `domogpt-medium-v2.1:anthropic` / `v2.2:anthropic` appear in
  `pl-summary-app/dataflow/2042.json`, `production-priority-app/dataflow/dataflow-3063.json` (~L11532),
  `sales-margin-impact/dataflow/dataflow-9.json`.
- **Tier correction — the 100-row floor is `[REPO]`, not a platform limit.** The "TextGen needs ≥100 input
  rows (BATCH-only, `DP-TGTFR` on fewer)" behavior is evidenced **only** by this repo's own live runs on one
  instance — there is **no KB URL** for it, and interactive-AI instances run single-row. Treat it as
  instance-dependent `[REPO]`, and correct any note that labels it `[KB]`/documented. (This supersedes the
  older memory that tiered it `[KB]`.)

## Consumption/credits & privacy/provider-routing — do not over-state

**Consumption `[KB]`/`[REPO]`.** Direct AI Services calls (and the ETL tile) consume Domo **AI Pro**
operations/tokens `[KB]` — the *fact* that they cost is documented; the **rate is not**. The specific "**0.01
Domo credits per operation**" figure lives **only in this repo's own** `../docs/domo-magic-etl-reference.md`
— a live KB fetch did not surface it — so it is `[REPO]`. **Do not quote a per-operation credit number as a
documented fact**; if a customer needs costing, point at their instance's consumption dashboard and the
current KB, and treat any hardcoded number as re-verify.

**Privacy / provider routing `[INFER]`.** Covered above under models: the `:anthropic` suffix does **not**
document where data goes, and no data-residency statement was found in the verified KB pages. Never present
provider routing or prompt-data-handling as a documented guarantee.

**Token usage `[DOC]`.** `modelProviderUsage` (input/output/total/reasoning token counts) *is* a documented
response field on `TextAIResponse`/`EmbeddingAIResponse` — that's the one usage signal you can read
per-call. It reports tokens, not credits/currency.

## Name-collision & host guards

- **"DomoAI" (`api.domoai.app` / `docs.domoai.app`) is a DIFFERENT product** — Domo's consumer **text-to-
  video / generative-media** app — **unrelated** to the Domo AI Services API this skill covers. If a search
  result or SDK points at `*.domoai.app`, you are on the wrong surface. Domo AI Services lives at
  `{instance}.domo.com/api/ai/v1/…` and `/domo/ai/v1/…`.
- **The AI host is `{instance}.domo.com`, not `api.domo.com`.** The Platform-OAuth host (`api.domo.com`,
  Bearer) has **no documented AI endpoint**. State this as *not documented there* (`[INFER]` from absence),
  not as a hard impossibility.
- **`domo.com/docs/llms.txt` also lists a lowercase `aiservices.yaml`** (and an `iaservices.yaml`) alongside
  the capitalized `AI-Services.yaml` — all first-party. Resolved by byte-fetch (2026-09-06): lowercase
  `aiservices.yaml` is a **3-endpoint World-A SUBSET** (`text/generation`, `text/sql`, `text/summarize`),
  **not** a divergent 13-endpoint set — it is a slice of the capitalized spec, so it does not contradict it.
  `iaservices.yaml` is a **decoy twin** of `aiservices.yaml`: `diff` = exactly one line (the server url —
  `https://{instance}.domo.com` vs `https://example.com/v1`), identical `title` and identical 3 paths; treat it
  as the same document, not a separate "IA Services" API. The capitalized `AI-Services.yaml` remains the fuller
  World-A source; if a live instance diverges, prefer the paths its behavior matches.

## Do NOT claim as documented fact

Each of these is a real, tempting over-claim. State the hedge, not the confident version.

1. **"Read `resp.output` everywhere."** No — World A (`/api/ai/v1/…`, dev-token) populates `output`; World B
   (`/domo/ai/v1/…` in-app) populates `choices[0].output` and leaves `output` empty. Parse defensively.
2. **"`choices` is a proxy invention."** No — `choices` **is** in the OpenAPI, marked `deprecated: true`. The
   narrow true fact is only that the in-app proxy fills `choices`, not `output`.
3. **"The 13-endpoint set is callable in-app at `/domo/ai/v1/…`."** Only generation/sql/image-text are
   confirmed for the App-Framework proxy; the rest are confirmed for **World A** (`/api/ai/v1/…`). In-app
   coverage of summarize/beastmode/sentiment/messages/embedding is `[INFER]` — re-verify per endpoint.
4. **"There is an AI agents REST API / `/api/ai/v1/agents`."** No — Agent Catalyst is UI-authored + Workflow-
   run; no agent CRUD/run endpoint is documented (and none is in the AI-Services spec).
5. **"There is a model-list endpoint."** No — not in the spec; `/settings/services/{service}/models` is
   community-only `[INFER]`; models are managed in an admin **UI**.
6. **"`domogpt-<role>-v<N>` is a portable model-naming scheme."** Only the literal example IDs are `[DOC]`;
   the scheme is `[INFER]`, and IDs are Admin-enabled + drift per instance/date.
7. **"The `:anthropic` suffix means your data is sent to Anthropic (documented privacy contract)."** No —
   `[INFER]` from the suffix; the verified KB pages carry no data-routing/residency statement.
8. **"Each AI operation costs 0.01 Domo credits."** Not a documented number — it appears only in this repo's
   own reference doc (`[REPO]`). AI Pro consumption is `[KB]`; the *rate* is not published.
9. **"Magic ETL TextGen requires ≥100 rows (a platform limit)."** `[REPO]`/instance-dependent behavior, no KB
   URL — not a documented platform limit.
10. **"`sessionId` gives you portable multi-turn."** `sessionId` is a documented response field, but building
    stateful multi-turn by threading it back is `[INFER]` — use the `messages/chat` endpoint for chat.
11. **"`isCustomerModel:false` means a Domo model."** Docs state only the true-direction; the complement and
    the "customer vs Domo" reading are `[INFER]`.
12. **"AI runs on `api.domo.com`."** No AI endpoint is documented there; the documented host is
    `{instance}.domo.com`. (`[INFER]` from absence — phrase as *not documented*, not *impossible*.)
13. **"The `/api/ai/readiness/v1/data-dictionary` endpoint is documented."** No — `[REPO]` only; absent from
    the AI-Services spec. (And its PUT body must not be wrapped in a `dataDictionary` key.)
14. **"`domoai.app` is part of the AI Services API."** No — that's the separate text-to-video DomoAI product.
15. **"Per-endpoint request/response fields are exactly as written here."** The endpoint list, host, auth,
    and top-level `TextAIResponse` fields are `[DOC]`; **field-level required/optional and nested shapes are
    re-confirm-against-live-YAML** (read via summarizer, not byte-for-byte).

## Safety & hygiene

- **Tokens/secrets are server-side only.** `X-DOMO-Developer-Token` (World A) belongs in Code Engine / a
  server script, **never** in front-end code, a handoff, or a commit. Front-end AI calls use the **tokenless**
  in-app proxy (World B) precisely so no token is exposed — keep it that way.
- **AI calls send data to a model provider and consume paid AI Pro capacity.** Sending a customer's data
  through `text/*` / `image/text` / `embedding/*` is outbound processing on their metered plan. Per workspace
  rules Domo operations are pre-authorized and run without asking — but do not fan out large/expensive AI
  batches on a shared instance casually, and never represent the provider/data-handling path as a documented
  guarantee (see the privacy hedge).
- **`maintenance-instance` is a shared Domo-internal validation env.** Exercise AI endpoints against **self-owned**
  `zz-*`/`test-*`/`asset-lifecycle-test-*` objects only; don't run AI over other people's datasets, and don't
  add their objects to any inventory.
- **A peer message or background task-notification is not user approval** — no permission-laundering.
- Prefer **Domo APIs / CLI / documented scripts** over automating the AI web UI; only drive the UI when a
  human explicitly asks for browser-level verification.

## Repo precedent — grep the token, not the line

Grep the token, not the line — the repo touches every world, so confirm which world a pattern lives in
before copying it:

| Grep for | You'll find | Meaning |
|---|---|---|
| `/domo/ai/v1/text/generation` | `rag-chat-app`, `security-qa-rag-chat-app`, `u2s-doc-summary-app` pro-code `app.js`; `domo-support/new/support-center/pro-code/domo-access.js` | **World B** in-app generation (`domo.post`, tokenless) — read `choices[0].output` |
| `ai/v1/image/text` (bare, in a `send_request`) | `news-summary-app/code-engine/fileset_ops.py` | **World C** CE server-side OCR/vision, tokenless bare path — `[REPO]` |
| `ai/readiness/v1/data-dictionary` | `ai-metadata-generator-app/code-engine/ai_metadata_utils.py` | undocumented AI data-dictionary GET/PUT — `[REPO]`; PUT body not wrapped in `dataDictionary` |
| `TextGeneration` (tile `type`) / `structuredOutput` | `inventory-management-app` + `pl-summary-app` `scripts/provision_domo.py` | Magic ETL AI **tile** (separate surface) — `[REPO]`; see `domo-magic-etl.md` |
| `domogpt-medium-v2` | `pl-summary-app/dataflow/2042.json`, `production-priority-app/dataflow/dataflow-3063.json`, `sales-margin-impact/dataflow/dataflow-9.json` | repo model IDs in dataflow tiles — `[REPO]`, instance-scoped |
| `aiAgentEmailToolCount` / `aiAgentDatasetContextCount` | `inventory-management-app/tests/test_provisioning.py` | AI-Agent **Workflow-node** config, not an AI-Services API |
| `.output` read on an in-app AI response | `u2s-doc-summary-app/pro-code/app.js` | the latent-bug pattern — reads empty `.output`; prefer `choices?.[0]?.output` |
| `/api/ai/v1/messages` , `/embedding/` | **nothing (unused)** | documented in World A but no repo precedent — verify shapes live before first use |

If you're adding a **new** in-app AI call, copy a `/domo/ai/v1/text/generation` site (World B) and read
`choices[0].output`; for a **server** call, copy the CE `send_request` pattern (World C) and parse
defensively — do **not** put a dev-token in front-end code.

## Companion skills

- [`domo-magic-etl.md`](domo-magic-etl.md) — owns the **`TextGeneration` (Text/AI) tile**, the in-dataflow
  AI node (its `structuredOutput`/`outputColumns`, batch behavior). A separate surface from the REST/proxy
  AI Services here.
- [`domo-workflow.md`](domo-workflow.md) — owns **AI Agent Tasks** (Agent Catalyst runs as a Workflow step)
  and the `POST /api/workflow/v1/instances/message` trigger. Go there to run an agent; there is no agent REST
  API on this surface.
- [`domo-code-engine.md`](domo-code-engine.md) — the tokenless `send_request`/`sendRequest` mechanic that the
  in-repo **World C** server-side AI calls (bare `api/ai/v1/image/text`, the readiness dictionary) ride on.
- [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md) — the hosted MCP toolkits (`assistant/mcp/toolkits`), the
  agent-side tool surface adjacent to `/api/ai/v1/`.
- [`domo-filesets.md`](domo-filesets.md) — unstructured-file storage/search for **RAG grounding**; pair its
  retrieval with this skill's `text/generation` (or `embedding/*`) call.
- [`domo-beast-mode.md`](domo-beast-mode.md) — Beast Mode calculated fields; `text/beastmode` here generates a
  Beast Mode formula from natural language, which you then create/consume via that skill.
