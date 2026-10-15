# Domo Code Engine Skill

Use this when editing Code Engine functions, package mappings, or prompt instructions that call Code Engine.

## Auth — calling Domo APIs from Code Engine

Every fact below carries an evidence tier. Anything `[REPO]`/`[INFER]` must be re-verified against a live
instance before you depend on it.

```
[DOC]   Stated in Domo's official developer/API docs, KB article 000005173 "Code Engine",
        the docs-portal "JavaScript Libraries" page, or a published OpenAPI spec. Safe to
        state as a public contract.
[KB]    Domo Knowledge Base / support / help articles. Authoritative for product behavior,
        not a REST contract.
[REPO]  Verified only from this repo's working code on a live instance; absent from public
        docs. Present as internal/undocumented — verify live first.
[INFER] Reasoned from documented facts plus HTTP/product semantics; not stated verbatim.
```


**The one rule.** For calls to Domo's **own internal APIs**, use the tokenless CE client
(`sendRequest` / `send_request`) and author **no** credentials — the call runs as the invoking user. `[DOC]`
Reach for an explicit credential only when the target is **external** to Domo (use a connected Domo Account
via `getAccount().properties`), or when the tokenless CE client **demonstrably cannot** perform a specific
internal call (some multipart/binary cases in this repo) — and when you do, label that fallback as `[REPO]`
behavior, **not** a documented limitation.

### Tokenless internal calls (preferred)

A CE function calls Domo's internal REST APIs through a built-in client and authors no token: `[DOC]`

- **JavaScript:** `codeengine.sendRequest(method, url, body?, headers?, contentType?)` — documented on the
  docs-portal "JavaScript Libraries" page and KB article 000005173. `[DOC]`
- **Python:** `codeengine.send_request(method, path, body?)` — used throughout this repo's production CE code,
  same method-first shape and relative-path convention. **Domo's official library docs are JavaScript-only**
  (the `python-libraries` page 404s), so the Python name/signature/return shape is `[REPO]`, not `[DOC]`. `[REPO]`

Key documented facts:

- **The path is Domo-RELATIVE, not an absolute hostname** — e.g. `api/data/v3/datasources/{id}?part=...`. `[DOC]`
- **Auth is injected by the runtime.** Per KB 000005173, verbatim: *"Every `sendRequest` call is intercepted
  by the Code Engine service and injected with the credentials of the authenticated user who is making the
  request."* You set no `Authorization`, no access token, and no `X-DOMO-Developer-Token` in code. `[DOC]`
- `X-DOMO-Developer-Token` is documented **only** for the opposite direction — *invoking* a CE function from
  **outside** Domo via the Product API — so do not treat it as part of the in-function call path. That invoke
  direction is now charted below in [**Invoking a CE function**](#invoking-a-ce-function-the-opposite-direction--the-run-function-api). `[DOC]`

```python
# Preferred CE pattern: tokenless, relative path, runs as the invoking user.
# The client may be exposed as `codeengine` and can be absent under some runtimes,
# so resolve defensively and probe both method-name casings.
ce = globals().get("codeengine")
send = getattr(ce, "send_request", None) or getattr(ce, "sendRequest", None)
resp = send("GET", "api/content/v1/datastores")   # no token authored
```

### Which identity a tokenless call runs as

The injected principal is **"the authenticated user who is making the request"** — the executing user,
**NOT** the package owner and **NOT** a separate service account. `[DOC]`

- It follows that the call runs under **that user's own Domo permissions** — a tight inference from
  "credentials of the authenticated user," not a separately-documented scope statement. `[INFER]`
- **The docs do not spell out how "the authenticated user" resolves in every context** — e.g. a scheduled
  Workflow run or embedded-app execution — nor the exact PDP/governance scope. Treat per-context principal
  resolution as undocumented beyond the general rule; if identity matters for a scheduled/embedded path,
  verify empirically on the target instance. `[INFER]`

### The three documented auth categories

Domo's API Reference overview defines **three** auth categories — useful for knowing which host/token a
non-tokenless path needs. `[DOC]`

| Category | How it authenticates | Host | Coverage / lifetime |
|---|---|---|---|
| **App Framework** | Handled automatically via `domo login` (Apps CLI), or inherited by developing from within your Domo instance | your instance | The closest **documented** analog to "CE-injected" auth |
| **Platform / OAuth** | OAuth 2.0 client-credentials: `client_id`/`client_secret` → bearer token from `api.domo.com/oauth/token` (HTTP Basic), then `Authorization: bearer <token>` | `api.domo.com` | Scoped (account/audit/buzz/dashboard/data/user); short-lived, refreshed |
| **Product** | `X-DOMO-Developer-Token` header (token minted in Admin › Authentication › Access Tokens) | your instance host | Full "anything you can do in the UI"; long-lived; CORS-restricted → server-side only |

- Domo explicitly lists **"Writing Code Engine Functions"** as a use case for developing *outside* the App
  context, directing it to the Platform (OAuth) or Product APIs above. `[DOC]`
- **"CE injects credentials" is documented only for the internal `sendRequest` path** (above) — it is **not**
  published as a general auth "contract" you can contrast point-for-point with OAuth/dev-token. When you must
  describe CE auto-auth, the nearest *documented* concept is the App Framework "automatic/inherited"
  category — don't cite a doc for a standalone "CE injection" mechanism. `[DOC]`/`[INFER]`

### When a CE function DOES need an explicit credential

When a CE function calls something **external to Domo** (or otherwise needs a real secret), the documented,
idiomatic source is a **Domo Account connected to the function as an input of type `Account`** bound to a
data provider. The secret is read from the account's properties **at runtime** — never hardcoded. `[DOC]`

```javascript
// Documented pattern (KB 000005173, Twilio example): fetch the connected account, read its properties.
const account = await codeengine.getAccount(acct.id);
const { accountSID, password } = account.properties;   // property names vary by provider — inspect them
```

- **This is the documented alternative to embedding a credential in code.** `[DOC]`
- Two honest qualifications: (1) Domo's docs *demonstrate* the pattern (Twilio `accountSID`/`password`; a
  Google Sheets provider) but state **no verbatim "never hardcode" rule** — that is idiomatic best practice
  implied by the pattern, plus the repo's own hard rule below. `[INFER]` (2) The docs show credential/secret
  accounts *generally*, not a **token**-type account specifically — applying the pattern to a Domo access
  token is an idiomatic generalization, not a doc-shown example. `[INFER]`
- **In CE code, prefer the account-properties path over any env/config token.** The repo's token-only
  fallbacks (below) read the token from account-property keys tried in order
  (`password`/`Password`/`Api Key`/`api_key`/`token`/`Token`); host = `get_execution_information().domo_hostname`
  with config/env fallback. Never inline a token into a committed file. `[REPO]`

### When the tokenless client may not be enough (verify, don't assume)

This repo falls back to an explicit dev-token `requests` call (not the tokenless client) for two things:
`[REPO]`

- **Multipart/form-data file upload** — the CE client is not used for the two-part upload here
  (`fileset_ops.py` literally documents "アップロード（Requests 必須 / マルチパート）").
- **Raw binary content download** — a dev-token path is used as the fast path, with a tokenless fallback.

> **This is repo behavior, NOT a documented platform limitation.** Domo's docs describe `sendRequest` only for
> JSON metadata APIs and are **silent** on multipart/binary — they neither confirm nor deny that the tokenless
> client *can't* do it. The App-Framework note that browser file upload/download needs `fetch`/`FormData`
> (rather than the `domo.*` helpers) is a **client-side mechanism** difference on the browser proxy, not an
> auth requirement, and not about the CE internal client. So: **if you can make the CE client perform the
> multipart/binary call, prefer tokenless**; fall back to a token only when it demonstrably can't, and label
> that as `[REPO]`. `[REPO]`/`[INFER]`

### Coverage and limits — what is NOT documented

- **No official allow-list of CE-reachable API families.** Domo publishes no catalog of which internal API
  families the tokenless client can reach. The set this repo has observed working — AppDB/datastores,
  query/execute, data v3, dataprocessing dataflows, files/filesets, content/v2 users, ai/v1 — is
  **repo-observed and version-fragile**; it can change without notice. Multiple Domo Community requests ask
  Domo to publish this very list, corroborating its absence. `[REPO]`
- **Only the CE compute envelope is published**, and it bounds the *function*, not the API calls it makes:
  **1 GB memory, 5-minute max runtime, single output**, a limited set of bundled JS/Python libraries. `[DOC]`
- **No documented rate limit, throughput quota, or payload cap** on CE-issued Domo API calls — no
  429/Retry-After/X-RateLimit language in the CE API reference or OpenAPI spec. Some third-party guides cite
  ~3,000 req/min per instance, but that is **non-official and not CE-specific** — verify empirically, don't
  cite docs. Treat retry/backoff as defensive coding, not a documented behavior. `[INFER]`

### Do NOT claim as documented fact (hedge list)

Nothing in this section is **refuted** by the docs — every risk here is over-claiming. Do not state any of
these as documented fact:

1. **The Python `send_request` name/signature/return shape is officially documented** — it is not; Domo's
   library docs are JS-only and the `python-libraries` page 404s. It is `[REPO]`.
2. **An official list/allow-list of CE-reachable API endpoints or families exists** — it does not; the working
   set is repo-observed and version-fragile.
3. **Multipart upload / binary download *requires* a dev token as a platform/CE constraint** — that is a repo
   coding choice, `[REPO]`, not a documented limitation.
4. **Documented rate limits / 429 / Retry-After / payload caps** on CE-issued calls — none published (the
   5-min runtime cap bounds the whole function, not per-request throughput).
5. **"CE injects credentials" as a standalone documented auth contract** you can contrast with OAuth/dev-token
   — it is documented only for the internal `sendRequest` path; the nearest documented category is App
   Framework "automatic/inherited."
6. **"Never hardcode credentials" as a verbatim doc rule** — it is idiomatic best practice (and this repo's
   hard rule), not a stated Domo prohibition.
7. **`X-DOMO-Developer-Token` as part of the in-function call path** — documented only for *invoking* a CE
   function from outside Domo, or as the Product-API path; the opposite direction from a CE function calling
   Domo. (That invoke direction *is* documented and is charted in **Invoking a CE function** below — this guard
   is only that it does not belong to the in-function `sendRequest` path.)

### Invoking a CE function (the opposite direction — the Run-Function API)

Everything above is a CE function calling **out** to Domo. The **opposite** direction — a caller *outside* the
function invoking it — is a separate public OpenAPI surface: **two `codeengine.yaml` specs, both invoke-only**
(a single `POST`-to-run each; **no** package-CRUD / list-executions / logs-fetch endpoint in either). Hedge #7
above only *names* this direction to disclaim it for the in-function path — here it is, charted. Two worlds, not
interchangeable: different base path, addressing model, **and** auth scheme. `[DOC]` (both spec bodies fetched
HTTP 200, real OpenAPI, verified 2026-09-05 rank-30 and re-verified 2026-09-06 rank-60):

| World | Run-function endpoint | Auth | Addressing |
|---|---|---|---|
| **Product / External** (`product/codeengine.yaml`, *"Code Engine API (External)"*) | `POST /api/codeengine/v2/packages/{packageId}/versions/{version}/functions/{functionName}` (Run Function) | `X-DOMO-Developer-Token` (apiKey header) on **your instance host** | fully-qualified: `packageId` (uuid) + `version` + `functionName` |
| **App-Framework / in-app** (`framework/codeengine.yaml`, *"Code Engine API"*) | `POST /domo/codeengine/v2/packages/{functionAlias}` (Run Code Engine Function; *"usable by Workflows and other Apps by Domo"*) | `bearerAuth` (HTTP bearer JWT) | alias-only: the manifest `functionAlias` |

- **Request bodies differ.** World-1 `RunFunctionRequest = {inputVariables, settings.getLogs}` — `settings.getLogs`
  is a request-body **flag** (not an endpoint) controlling whether execution logs are returned. World-2
  `CodeEngineInput` is an **open object** whose properties are the manifest parameter **aliases**.
- **Only World-1 returns a rich response.** `RunFunctionResponse` = `executionId`, `packageId`, `version`,
  `functionName`, `status`, `startedOn`/`completedOn` (date-time), `startedBy`, `result` (any),
  `stdout`/`stderr` (each a `LogOutput = {log:[]}`), and `errorInformation`. **World-2 returns a bare
  `CodeEngineOutput`** (open object, defined in the function's *"Output"* tab / the manifest
  `packageMapping.output`) with **no** execution metadata or logs — do not claim otherwise (`O3`).
- **`ErrorInformation` (World-1 only)** carries type-checking metadata explaining *why* an input/output failed
  validation: `expectedType`, `actualType`, `expectedIsList`, `actualIsList`, `expectedAllowNull`,
  `errorMessages[]` (+ `result`). Errors: World-1 `401`/`404`, World-2 `400`/`401`/`404` → `ErrorResponse {message}`.
- **Host caveat (`O4`):** the Product spec's server variable default is literally `'api'` — a **placeholder for
  `{instance}`** (spec: *"e.g., mycompany"*), **not** the `api.domo.com` OAuth gateway. Dev-token invoke lives on
  **your instance host** (per the three-auth-category table above).
- **Direction caveat (`O5`):** this surface calls **INTO** a function from outside; the skill's core scope is the
  opposite direction (a function calling **out** via tokenless `sendRequest`). Keep them distinct.
- **Scope (`O1`, no universal-negative):** "no CRUD/list/logs endpoint" is scoped to **these two spec files as
  read** (exactly one path each) — not a doc-stated claim that the whole CE platform lacks a control plane.
  Package management stays via the manifest/publish flow this skill already documents; a broader packages/
  executions/logs control-plane remains an `[INFER]` gap to scout, **not** a declared absence.

### Repo precedent

Working CE auth patterns already live in the repo — read these before writing new code (line numbers drift,
so grep the token, not the line): `[REPO]`

| Project | What it demonstrates |
|---|---|
| `news-summary-app/code-engine/fileset_ops.py` | The fullest reference: tokenless `send_request` metadata calls, defensive `ce = globals().get("codeengine")` + dual `send_request`/`sendRequest` casing probing, the token-only multipart **upload** and content **download** with a tokenless fallback, and account-property token resolution |
| `beast-mode-manager/bm_bulk_lock.py` | The explicit dev-token server-to-server path (`X-DOMO-Developer-Token`) for a client that does not run inside CE — the contrast case to tokenless |
| `sales-os-portal/pro-code/app.js` | Browser side: the App-Framework proxy attaches the session; the app author authors no token |

Companion skills: [`domo-filesets.md`](domo-filesets.md) (FileSet auth slice + upload/download token cases),
[`domo-beast-mode.md`](domo-beast-mode.md) (Beast Mode `/functions/` auth slice),
[`domo-procode-app.md`](domo-procode-app.md) (browser bundle wiring).

## Contract Rules

- Do not add or remove public functions without explicit user approval.
- Do not change public function signatures without explicit user approval.
- Keep return values as dictionaries or plain objects where existing callers expect structured results.
- Error paths should also return dictionaries or plain objects with clear keys such as `success`, `message`, `error`, and `diagnostics`.
- Preserve names used by Pro Code `packagesMapping[]`, workflows, prompts, and AppDB records.
- Do not hardcode secrets, tokens, SIDs, cookies, private keys, or `.env` values.

## Implementation Rules

- Prefer standard libraries unless the project already depends on an external package.
- Add timeout, retry, and error handling around external API calls when safe and consistent with local patterns.
- Validate JSON inputs before use and return actionable error messages.
- Do not log sensitive payloads. Redact config, auth headers, and raw document text.
- For AI-agent-facing functions, use stable output keys and avoid ambiguous state names.

## Required Reads

- Target Code Engine file.
- Pro Code manifest `packagesMapping[]`, if a Pro Code app calls the function.
- Prompts or workflow JSON that call the function.
- the repo-level `AGENTS.md` and relevant `../docs/` for Domo API behavior.
