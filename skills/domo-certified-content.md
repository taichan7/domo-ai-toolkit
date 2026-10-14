# Domo Certified Content

Use this skill to reason about — or drive via REST — **Domo Certified Content**: marking a **Card** or a **Dataset** as *certified* (and reading or removing that mark). **Read the naming-trap table below before anything else**: certification is **not** modeled as its own `/certifiedcontent` resource — it is a **system tag named `CERTIFIED`** carried on a generic **tags** namespace (`/api/tags/v3/{entityType}/{entityId}/system/CERTIFIED/state`), and the certified *state value* `ACTIVE` is a literal **path segment**, not a request body. That path shape is the #1 conceptual surprise on this surface.

Certified Content is a **single-world, small, fully-documented OpenAPI island** — **3 operations / 2 paths** — and the **same shape as rank-13 Projects & Tasks** (one world, all `[DOC]`, **ZERO repo precedent**, no product/framework twin), but far smaller (3 ops vs 21) and on **product dev-token auth** rather than platform OAuth. This skill is therefore a **faithful map of a tiny REST surface + a strong disambiguation layer** (the `CERTIFIED`-tag path shape, the read-path that lives in `domo-datasets.md`, and the product certification *workflow* that has no API), guarded hard against over-claiming (**zero calls were executed** against this API).

## What this skill owns (and what it defers)

**Owns:** the three Certified Content REST operations — **read / certify / decertify** a Card or Dataset's `CERTIFIED` system-tag state — under `{instance}.domo.com/api/tags/v3/…/system/CERTIFIED/state`, `X-DOMO-Developer-Token`.

**Defers:**
- **Reading dataset certification as embedded metadata.** `GET /api/data/v3/datasources/{id}?part=certification` returns certification inside the dataset's core metadata — a **different, repo-verified read path** → `domo-datasets.md`. For datasets there are **two** documented ways to *read* state; **write** (certify/decertify) is documented only here.
- **The product certification *workflow*** — request-certification, owner/approver chains, approve/reject/send-back, the Certification Center, and the Company-vs-Department certification tiers — is `[KB]` product behavior with **no counterpart in this API** → treat as UI/product-only.
- **Who is allowed to certify** (the "Manage Certified Content" grant / Certified Content Admin role) → `domo-identity-access.md` (role & grant model). The spec documents only a valid-token requirement (401).
- **The broader `/api/tags/v3` surface** (other system tags, user tags, generic tag CRUD) — **uncharted**; this spec documents only the `CERTIFIED` system tag.
- **What a Card or Dataset *is*** → `domo-cards.md` / `domo-datasets.md`. Minting the developer token → `domo-identity-access.md`.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo.com/docs/s/article/<12-digit> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  verified only against this repo's working code (an instance-internal convenience, NOT a public contract).
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (405 / JS-gate / login-wall / 404) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting an untested runtime behavior, an inference-from-absence, or a `[KB]` product fact as an API contract. This entire skill is `[DOC]`/`[KB]`/`[INFER]` with **zero `[REPO]`**: no working code in this repo calls this API, and **no request was ever executed** against it — so treat all request/response *behavior* (does GET on an uncertified entity 404 or return null-state; is PUT idempotent; what a 403 looks like) as **documented-but-untested**.

**Verification provenance.** Written after verification Workflow **`wf_e2a7693b-83e`** (15 agents, 0 errors: spec-reading clusters → adversarial refute of the seven highest over-claim-risk claims, each default-refuted-if-uncertain → completeness critic + island verdict → synthesizer), corroborated by a **direct read of the raw YAML** `/tmp/certifiedcontent.yaml` (160 lines, 4,772 bytes) whose fresh `curl` was **byte-identical** to the cache (no drift), plus the dev-portal guide and the three `api-reference/certified-content/*` pages (all agree exactly). **All seven refuted claims were caught and re-tiered:** three DROP (PUT echoes a body / DELETE returns status / "only Cards & Datasets can be certified anywhere"), three → `[INFER]` (no platform twin / tags-namespace-is-cert-only / null-means-uncertified), one → `[DOC]`-affirmative-only (dev-token is the only *documented* scheme). 鉄則 satisfied (doc-cross-check + adversarial-verify **before** writing).

## The naming-trap table — read this first

This is the highest-value part of the skill. Read it first.

| You see… | It actually is… | Owner |
|---|---|---|
| **certification** | a **system tag named `CERTIFIED`** with a `state`, on a generic tags namespace — **not** a `/certifiedcontent` resource | **this skill** |
| **base path** | `/api/tags/v3/{entityType}/{entityId}/system/CERTIFIED/state` — a **TAGS** namespace, not `/certified…` | **this skill** |
| **`ACTIVE`** (in the PUT path) | the **certified state value**, expressed as a literal **path segment** (`…/state/ACTIVE`), **NOT** a request body | **this skill** |
| **`DATA_SOURCE`** (entityType) | a **Dataset** (Domo's internal name for a dataset entity) | **this skill** / `domo-datasets.md` |
| **`GET …?part=certification`** | reading dataset certification as **embedded metadata** on `/api/data/v3/datasources/{id}` — a **different API** | `domo-datasets.md` (`[REPO]`) |
| **"certified" column** (YES/NO) | a **governance/DomoStats DataSet column**, consumed by asset-lifecycle app logic — **not** this API | `domo-governance-datasets.md` (data) |
| **`'CERTIFIED': '認証済み'`** (app.js) | a **display-label translation map** in the asset-lifecycle Pro Code app — a **false friend** | not an API call |
| **Request Certification / approval chain / Certification Center** | the **product workflow** (request → owner/approver → approve/reject) — **no op in this API** | `[KB]` product-only |
| **Company vs Department certification** | two product certification **types/tiers** — **not** parameters of this API (it models one `CERTIFIED`/`state`) | `[KB]` product-only |

**Memorize:** the resource is a **tag** (`CERTIFIED`), the verb-of-state is a **path segment** (`ACTIVE`), and the *product* concept of certification (tiers, approval workflow, admin grant) is **richer than the API**, which is a bare 3-op on/off/read switch.

## The headline — a single-world documented island `[DOC]`

`certifiedcontent.yaml` — OpenAPI **3.0.0**, title **"Certified Content API"**, version **v3**, description *"API for managing the certification status of Cards and Datasets."* `[DOC]`

| axis | value |
|---|---|
| host | **one** server `https://{instance}.domo.com` (no `api.domo.com` platform host) |
| auth | **one** securityScheme `DeveloperToken` — apiKey header **`X-DOMO-Developer-Token`**; global `security: [DeveloperToken: []]`. **No OAuth scope declared.** |
| base namespace | **`/api/tags/v3/`** (a **tags** namespace) — certification is the system tag `CERTIFIED` |
| operations | **3** (1 GET / 1 DELETE / 1 PUT) across **2 paths** |
| operationIds | present on all three (`get-certification-status`, `delete-certification`, `certify-content`) |
| entityType | closed **`enum: [CARD, DATA_SOURCE]`** (path param) |
| repo precedent | **ZERO** — every op `[DOC]`, never `[REPO]`; executed calls: **0** |

**Single-world is established positively, not from a failed fetch** `[INFER]`: the reached catalog (`domo.com/docs/llms.txt`) is a **positive enumeration** of all OpenAPI specs across three namespaces (framework, platform/`api.domo.com`, product), and the token `certif` matches **exactly one line** — `certifiedcontent` under **Product** APIs. No Platform (`api.domo.com`/OAuth) twin and no Framework (`/domo/`) twin is *listed*. (Note: platform **does** carry `cards.yaml` and `dataset.yaml` — the two entity *types* have twins, but the **certify/decertify operation** does not.) The absolute "no such API exists anywhere" stays `[INFER]` (a 404 is missing evidence, not proof of absence).

**Chartedness — fully-inventoried, response-contract partially charted `[DOC]`:** all 3 ops carry paths, methods, operationIds, params, response-code sets, and an HTTP `x-codeSample`; the **request** contract is fully charted (closed `entityType` enum, `entityId` string, and the explicit **absence** of any `requestBody` or query param on every op). Three **thin spots** on the response side: (1) PUT's 200 has **no schema/body at all**; (2) `CertificationStatus.metadata` is a bare `object, nullable` with **zero declared properties**; (3) `state` is `string, nullable` with only `ACTIVE` given as an *example* — the full state set is **not** enumerated. So this is **richer than Scheduled Reports** (2 of 3 ops carry response detail + all carry request detail + code samples) but **not** charted to runtime.

## The surface — 3 operations / 2 paths `[DOC]`

Both paths require **both** `{entityType}` (`CARD` | `DATA_SOURCE`) **and** `{entityId}` (string) — declared **`in: path`** (the dev-portal guide mislabels them "Query Parameters"; the spec is authoritative → they are **path** params). All ops `[DOC]`, all with only **401 / 404** error responses documented.

**Path 1 — `/api/tags/v3/{entityType}/{entityId}/system/CERTIFIED/state`:**

- `GET` — **`get-certification-status`**. Read the entity's certification status. → **200** `CertificationStatus`, **401**, **404**. Documented example body: `{ "tag": "CERTIFIED", "state": null, "metadata": null, "updated": null }`.
- `DELETE` — **`delete-certification`**. **Removes** certification on the Card/Dataset. → **204 No Content** (no body documented), **401**, **404**. **Trap:** DELETE targets the **`/state`** collection, **not** `/state/ACTIVE`; there is **no request body** and **no returned body** — to read the resulting (removed) state, issue a follow-up GET.

**Path 2 — `/api/tags/v3/{entityType}/{entityId}/system/CERTIFIED/state/ACTIVE`:**

- `PUT` — **`certify-content`**. **Certify** the Card/Dataset. → **200** (description *"SUCCESS. The content is now certified."*, **no schema/body documented**), **401**, **404**. **Trap:** the state value **`ACTIVE` is a literal path segment**, not a request body; there is **no `requestBody`** on this op (grep count across the whole spec: **0**). Do **not** assume the 200 echoes a `CertificationStatus` and do **not** assume PUT is idempotent — neither is documented.

**Verb map `[DOC]`:** GET = read, **PUT `…/state/ACTIVE`** = certify (set state), **DELETE `…/state`** = decertify. **No POST, no PATCH.** There is **no list / search / enumerate** operation — you must **already hold the `entityId`**; you cannot discover which entities are certified via this API `[INFER]` (capability negative: no such op is documented).

## The objects `[DOC]`

**`CertificationStatus`** (GET 200 body) `[DOC]`:

| field | type | notes |
|---|---|---|
| `tag` | string | example `"CERTIFIED"` |
| `state` | string, **nullable** | description *"The state of the tag (e.g., 'ACTIVE' or null)."* — **`e.g.` is non-exhaustive**; the value set is **not** closed |
| `metadata` | object, **nullable** | **zero declared properties** — its shape is uncharted `[INFER]` |
| `updated` | string (`date-time`), **nullable** | last-updated timestamp |

The documented GET **example returns all-null** (`state:null, metadata:null, updated:null`) — so the example depicts a **not-currently-certified** entity `[DOC]`.

**`ErrorResponse`** (401 / 404 body) `[DOC]`: `{ message: string }` — a human-readable error message. That is the entire error schema.

**Path params `[DOC]`:** `entityType` = closed `enum: [CARD, DATA_SOURCE]` (`DATA_SOURCE` = Dataset, per its description); `entityId` = string ("Id of the card or dataset").

**State-value semantics are `[INFER]`, not `[DOC]`:** the PUT sets state to `ACTIVE` and the GET example shows `null`, so **`state:"ACTIVE"` reads as certified and `state:null` as not-currently-certified** — an inference from the example + path shape, **not** a positively-defined contract. The spec's `"e.g."` explicitly forbids treating `{ACTIVE, null}` as the *complete* state set; the product shows further badge states (**PENDING**, **EXPIRED**) `[KB]`, so treat the state space as **open**.

## What the product does that the API does not `[KB]`

Certification is a **richer product feature** than this 3-op switch — carry these as `[KB]`/`[INFER]`, never as API contract:

- **Two certification *types*** `[KB]`: **Company** certification (org-wide, most stringent, a single non-deletable Company process) and **Department** certification (the default). The API models certification as **one `CERTIFIED` tag with a `state`** and has **no type/process parameter** `[DOC]`; how a `PUT …/state/ACTIVE` maps to company vs department is **undocumented** `[INFER]`.
- **A request → approval workflow** `[KB]`: request certification → owner decision → approver chain → approve/reject/send-back, tracked in a **Certification Center**. The documented API exposes **only** direct certify/decertify/status — **no request or approval op** `[DOC]`.
- **A permission gate** `[KB]`: direct one-step certify requires the **"Manage Certified Content"** grant (a Certified Content Admin — Admin role, or a custom role with that grant); "Request Certification" is a separate lighter flow. The API-specific claim "the PUT requires that grant" is **`[INFER]`** — the spec states only that a valid developer token is required (401 otherwise); a **403** is *plausible* but **undocumented**.
- **Certifiable entity types** — the API enum is **closed `[CARD, DATA_SOURCE]`** `[DOC]`, corroborated by KB (badges for Cards and DataSets only) `[KB]`. Do **not** generalize to "only Cards and Datasets can be certified anywhere in Domo" — that universal negative is **over-claiming**; whether other entity types are certifiable via other paths is `[INFER]`.

## Boundaries & orphans

- **Two read paths, one write path `[DOC]`/`[REPO]`.** For a **dataset**, certification state is *also* readable via `GET /api/data/v3/datasources/{id}?part=certification` (embedded in dataset metadata, read-only) — owned by `domo-datasets.md:145` `[REPO]`. **Writing** certification (PUT to certify, DELETE to decertify) is documented **only here**. These are **related distinct APIs**, not a second world — the data/v3 read path does **not** change the single-world verdict.
- **The broader `/api/tags/v3` namespace is uncharted `[INFER]`.** `certifiedcontent.yaml` documents **only** the literal `…/system/CERTIFIED/state(/ACTIVE)` paths; the segment `system` implies other **system** tags may exist, and there may be user/non-system tags and generic tag CRUD — none documented in the reached catalog (no `tags.yaml` was found). "`CERTIFIED` is one of possibly several system tags" is `[INFER]`; only "this spec documents no tag other than `CERTIFIED`" is `[DOC]`.
- **No enumerate op `[INFER]`.** Both paths require a specific `{entityId}`; there is no way to *list* certified entities through this API. Governance dashboards read certification from a **DataSet column** instead → `domo-governance-datasets.md`.
- **Error surface is 401/404 only `[DOC]`.** `400 / 403 / 409 / 500` are **undocumented** (absence → `[INFER]`, not a documented negative). Do not promise specific behavior on a malformed id, an unauthorized role, or an already-(un)certified entity — none is charted.
- **Dev-portal guide inconsistency `[DOC]`.** The guide's parameter table headers `entityType`/`entityId` as "Query Parameters"; the authoritative spec declares them `in: path` and the HTTP samples place them in the path. **Use path params.**

## Repo false friends `[REPO]`

**Repo precedent = ZERO** `[REPO]`. A full-tree grep (all `.py/.js/.mjs/.ts/.sh/.ipynb`, tracked + untracked) for `api/tags/v3`, `get-certification-status`, `delete-certification`, `certify-content` returns **no API caller** — the only file matching is this skill doc. **Therefore every operation stays `[DOC]`, never `[REPO]`,** and no request was ever executed. Every `certif…` occurrence in code is a false friend:

- **`asset-lifecycle-app/pro-code/app.js:340`** — `'CERTIFIED': '認証済み'`, a **Japanese display-label map** (candidate-reason humanizer). A display translation, not an API call.
- **`asset-lifecycle-app/code-engine/asset_lifecycle_service.py`** and **`pro-code/domo-access.js`** — read a **`certified` (YES/NO) column** from a governance/DomoStats **input DataSet** and filter on a `certified_scope`; **`scripts/provision_domo.py`** stores a `certified_policy` **SETTING**. All are the governance-data *column/policy*, not the certification API.
- The ubiquitous in-repo **`X-DOMO-Developer-Token`** is all FileSets / provisioning / DataFlow deploy — **same header, unrelated surface.** The `api/tags/v3` needle is the real test, and it is **zero**.

## Do NOT claim as documented fact

1. **Do NOT** describe the base as `/certifiedcontent` or as its own resource — it is the **`CERTIFIED` system tag** on **`/api/tags/v3/{entityType}/{entityId}/system/CERTIFIED/state`** (a tags namespace).
2. **Do NOT** send `ACTIVE` (or any state) as a **request body** — `ACTIVE` is a **path segment** on the PUT; **no op has a `requestBody`** (spec grep count 0).
3. **Do NOT** say the **PUT (`certify-content`) returns a `CertificationStatus`** or is idempotent — its 200 has **no documented body/schema** (only a success description); both claims are unsupported.
4. **Do NOT** say the **DELETE (`delete-certification`) returns a status** — it returns **204 No Content** with no body; read the result with a follow-up GET.
5. **Do NOT** claim **`state` is only `ACTIVE` or `null`** — the spec's `"e.g."` is non-exhaustive and the product shows PENDING/EXPIRED badge states; treat the state space as **open** `[INFER]`.
6. **Do NOT** state the semantics of **`state:null`** (uncertified vs certified-but-state-unknown) as fact — `null` reading as "not currently certified" is `[INFER]` from the example, not a defined contract.
7. **Do NOT** describe **`metadata`**'s fields — it is a bare `object, nullable` with **zero declared properties**; its contents would become `[REPO]` only after a live GET on a genuinely certified entity.
8. **Do NOT** generalize the closed enum to **"only Cards and Datasets can be certified in Domo"** — the enum `[CARD, DATA_SOURCE]` is `[DOC]` **for this API**; broader certifiability is `[INFER]`.
9. **Do NOT** promise a **403** (or any behavior) for an unauthorized/insufficient-role caller — the spec documents only 401 (bad token); the "Manage Certified Content" grant requirement is `[KB]` product behavior, not an API-documented response.
10. **Do NOT** claim a **platform (`api.domo.com`/OAuth) or framework (`/domo/`) twin** exists or that this is the *only* certification mechanism anywhere — "no twin is **listed** in the reached catalog" is `[DOC]` (positive enumeration), but the absolute negative is `[INFER]` (404 = missing evidence).
11. **Do NOT** claim `/api/tags/v3` supports **only** certification — this spec exposes only the `CERTIFIED` tag; the rest of the tags namespace is **uncharted** `[INFER]`, not proven empty.
12. **Do NOT** invent a **list / search / enumerate** op, an **approval / request-certification** op, or **company-vs-department** parameters — none exist in the API; the product workflow and tiers are `[KB]`, UI-only here.
13. **Do NOT** frame any request/response **behavior** as "verified/works" — the whole skill is `[DOC]`/`[KB]`/`[INFER]` with **zero `[REPO]`** and **zero executed calls**.

## Safety & hygiene

- **`X-DOMO-Developer-Token` is a secret** — never write it into source, handoffs, or commits; read it from config at call time (repo convention: macOS Keychain / `~/.config/domo-utils/`). Never log the token.
- **Certification is a governance signal on shared content.** `PUT …/state/ACTIVE` and `DELETE …/state` change how an org **trusts** a Card/Dataset — a wrongful certify misleads users; a wrongful decertify strips a trust badge. **Confirm human intent** before either write, and do not certify/decertify content you don't own or aren't authorized to govern (the "Manage Certified Content" grant is a real product gate `[KB]`).
- **Probe read-only first** — `GET …/system/CERTIFIED/state` to confirm auth and current state before any write. Because the state space is open (PENDING/EXPIRED exist `[KB]`), read the actual `state` rather than assuming `ACTIVE`/`null`.
- **DELETE targets `/state`, PUT targets `/state/ACTIVE`** — mixing the two paths is the most likely silent misfire. Neither carries a body.
- Treat the product **approval workflow** as the safer path when an org uses it: a direct PUT bypasses request→approve → prefer the UI/Workflow-driven certification where governance requires review.

## Companion skills

- `domo-datasets.md` — the **other read path** for a dataset's certification (`GET /api/data/v3/datasources/{id}?part=certification`, embedded metadata, `[REPO]`); what a Dataset (`DATA_SOURCE`) is.
- `domo-cards.md` — what a Card (the other `entityType`) is.
- `domo-governance-datasets.md` — the **`certified` (YES/NO) DataSet column** that governance/asset-lifecycle dashboards read (the data-side false friend; also how you'd *enumerate* certified content, which this API cannot).
- `domo-identity-access.md` — the **"Manage Certified Content" grant** / Certified Content Admin role, and minting the developer token.
- `domo-projects.md` — the rank-13 **same-shape** island (single-world, all-`[DOC]`, ZERO repo precedent) for scale contrast.
- `domo-workflow.md` — where a certification could be driven as part of an automated governance flow (the product's request/approval workflow has no direct API here).
