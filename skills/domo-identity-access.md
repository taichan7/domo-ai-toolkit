# Domo Identity & Access-Control API Skill

Use this when a task **reads or manages who exists in a Domo instance and what they can do** — creating
/ listing / updating / deleting **users** and **groups**, assigning **roles**, editing a role's **grants
(authorities)**, resolving the current user, or wiring **users/groups into PDP** row policies. Unlike most
Domo surfaces, the identity API is **broadly documented** — but it is documented across **three different
auth worlds** that are easy to conflate, and the single most damaging mistake is calling the right path on
the wrong host with the wrong credential. This skill's job is to keep those worlds apart, to mark exactly
where the documented island ends, and to stop two specific over-claims: that role/grant management is
"UI-only" (it is not — there is a documented instance-host API), and that the undocumented `content/v2`
paths this repo leans on are a public contract (they are not).

Scope boundaries — use the neighbor skill instead when:

- it's the **PDP row-policy CRUD on a DataSet** (the `POST/GET/PUT/DELETE
  api.domo.com/v1/datasets/{id}/policies` endpoints, filter/operator body, column masking) →
  [`domo-datasets.md`](domo-datasets.md) **owns that**. This skill covers only the *identity side* of PDP
  (how a policy references `users[]`/`groups[]`, snapshot-vs-dynamic membership) and cross-refs it;
- it's **Code Engine auth mechanics** — the tokenless `send_request`/`sendRequest` that most of the
  in-repo `content/v2/users` reads ride on → [`domo-code-engine.md`](domo-code-engine.md);
- it's driving Domo's hosted **MCP `user_admin_toolkit`** (agent-side user read/manage tools, not raw
  REST) → [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md);
- it's **Publication Groups** (dashboard/page row-level view filtering) or **Publish subscriber groups**
  (cross-instance replication) — those are *not* security groups →
  [`domo-appstudio.md`](domo-appstudio.md) / [`domo-everywhere.md`](domo-everywhere.md). See the "three
  group meanings" section below.

## Evidence tiers

Every load-bearing line below carries a tier. Anything `[REPO]`, `[KB]`, or `[INFER]` must be re-verified
live against the target instance and the current docs before you depend on it — identity behavior is
instance-config-, plan-, and version-dependent, and the two Product APIs below were only recently added to
Domo's documentation.

```
[DOC]   Official Domo docs — the docs portal (domo.com/docs/portal), the developer
        API reference (developer.domo.com), or a machine-readable OpenAPI YAML in
        Domo's own doc-hub. Note two DOC sub-classes below: /docs/portal/ OpenAPI
        pages (developer API) vs /docs/s/article/ knowledge-base pages ([KB]).
[KB]    Domo Knowledge Base / support help center. Product behavior: role names,
        group types, SCIM/SSO framing, limits, admin-UI facts. Not the API reference.
[REPO]  Verified only against this repo's working usage on a live instance — NOT in
        public docs. Undocumented; re-verify per instance/version. (Identity has real
        repo usage — the content/v2 reads — so this tier IS populated here.)
[INFER] Reasoned from the documented model or community sources, or inferred from the
        ABSENCE of a documented endpoint — plausible, not first-party. Verify live.
```


_Provenance — Activity Log fold (rank-65, 2026-09-06):_ the two audit lines above (World-1 OAuth
`/v1/audit` params + 15-field single-object 200; World-2 dev-token `/api/audit/v1/user-audits` +
`/objectTypes`) were folded from the rank-29 REPORT_ONLY cluster after a fresh 12-agent adversarial-verify
workflow (`<verification-run>`) re-fetched both specs byte-identical to rank-29 and returned **APPLY_ALL
(F1–F5)** — 5 `[DOC]` folds confirmed, 4 negative controls all refuted, no over/under-claim. The
load-bearing distinctions the panel enforced: OAuth `time`=STRING vs product `time`=int64-ms; OAuth
limit/offset defaults are **description-only** vs product's real `default: 0`/`300`; `objectType` is
**free-form (no enum)** and `/objectTypes` is a **runtime discovery list**, not a closed set; OAuth 200 is a
**single object** vs product 200 is an **array** — the two worlds' audit contracts are never canonicalized.

_Provenance — groups/avatar fold (rank-66, 2026-09-06):_ the `content/v2/groups` management block and the
`{instance}.domo.com/domo/*` App-Framework block in surface #2 were folded from the rank-45 REPORT_ONLY
report after a fresh adversarial-refute workflow (`<verification-run>`) re-fetched the four owned specs
(`product/groups-api`, `framework/groups`, `framework/user`, plus `platform/group` as a negative control)
all http-200, and returned **APPLY_ALL (5/5 — F-alpha as APPLY-CORRECTED)** with all 6 negative controls
refuted. The panel caught **one over-claim of my own** — an invented `?parts` selector on the group-fetch
(that param belongs to `GET /api/identity/v1/users/{userId}`, not to groups) — now stripped. The load-bearing
distinctions it enforced: content/v2/groups **existence=`[DOC]` but reliability=`[INFER]`** (repo executes
none); the create-response `id`=**string** vs fetch-response `id`=**integer** spec-internal inconsistency;
App-Framework `/domo/*` is **app bearer-JWT, NOT dev-token**; `Group.type` in `framework/groups` is
**free-form** (`adHoc`/`directory`), unlike content/v2's `[closed,open,dynamic]` enum; and the avatar API is
**genuinely net-new** but scoped to identity **only** because `entityType` is `[USER]`-restricted here.

_Provenance — auth-family mint-ops fold (rank-77, 2026-09-07):_ Surface #1's `customer`/`jti`/`grant_type`-
required/Basic-scheme details and the **credential-minting precursors** subsection (create-OAuth-client
`POST /clients`; create-instance-SID `POST /api/content/v2/authentication`) were folded from the **rank-25
REPORT_ONLY** auth-family report (`Client-API` + `Instance-Authentication` + `API-Authentication`), whose
disposition — fold here, ship **no** standalone skill — stands (this is not a re-adjudication). Trigger: a
WAF-gate lift. All three portal bodies, WAF-blocked when rank-25 could read them only via cross-check agents,
now re-fetch **HTTP-200**, so a Method-1 line-by-line read of the live bodies directly confirmed every rank-25
claim; a 13-agent triage workflow (`<verification-run>`, NC-passed / GraphQL-absent) independently re-flagged the same
absentees; and a repo-wide `git grep` confirmed the fold-ins were never previously applied
(`content/v2/authentication` / `sessionToken` / `jti` / `/clients` = 0 pre-fold hits). All example values
(access-token blobs, `jti` / `client_id` / `client_secret` GUIDs, `sessionToken` base64, passwords) were
withheld — field **types/shapes** only.

_Provenance — Group-API field fold (rank-78, 2026-09-07):_ the Groups paragraph's `PUT`-partial-update
correction, `memberCount` `[INFER]`→`[DOC]` upgrade, `limit`/`offset` paging (doc-only-not-enforced, type-split
`integer`-vs-`string`), `POST` `200`-vs-`201` + `creatorId`-string + create-request-body-`{name}`-only
correction, `DELETE`-group destructive-&-irreversible note, and the customer-deleted `deleted`-tombstone edge
were folded from the dev-portal **`Group-API.yaml`** (WAF-lifted 405→**200**, 8 ops across 4 paths, `bearerAuth`
@ `api.domo.com`) — the same field-level re-mine as rank-76/77, applied because rank-34 only
**domain-adjudicated** the portal Group spec and never field-folded it (verified never-applied: the specifics
above were absent pre-fold). Verified by a Method-1 line-by-line read of the live 200 body + a 6-agent
adversarial workflow (`<verification-run>`: extract → 4 refute lenses + one planted negative control → adjudicate) →
**APPLY all 6**, unanimous `CONFIRM_NETNEW`, zero drops, all survive at `[DOC]` (the `deleted` edge graded
prose-only), and the false NC refuted by **every** lens. No example values (group ids/names, `creatorId`
strings, member userIds) reproduced.

_Provenance — User-API field fold (rank-79, 2026-09-07):_ the Users table's create required-ness (on the
**query params**, not the body — the requestBody schema has no `required[]`), the `employeeNumber` **integer**
send-side type (prose table says `string`; create-body + GET-one response both say `integer`), the returned
`groups` **`{id,name}` object-array** shape, the `roleId`-in-GET-one-response discovery path (typed `string`,
correcting "only in update args"), and the misspelled **`roled`** write param were folded from the dev-portal
**`User-API.yaml`** (WAF-lifted 405→**200**, 4 ops, `bearerAuth` @ `api.domo.com`; ⚠ **no `DELETE` op present in
this spec body** — the charted user-DELETE now flags that discrepancy) — the same field-level re-mine as
rank-76/77/78, applied because rank-34 only **domain-adjudicated** the portal User spec. Verified by a Method-1
line-by-line read of the live 200 body + a 5-agent adversarial workflow (`<verification-run>`: 4 refute lenses + one
planted negative control → adjudicate) → **APPLY 5 of 6**, `nc_all_refuted` (the fabricated "POST returns 201 +
`Location` header" refuted by every lens and by spec — POST returns **200**, no `Location`), one candidate
dropped as TRIVIA (a lone weak-prose `locale` `date-time` typo, `string` everywhere authoritative). No example
values (user ids/names, emails, employeeNumbers, avatar URLs, group ids/names) reproduced.

Unlike most Domo surfaces this cycle has skill-ized, identity has a **large** documented island — full CRUD
for users and groups, role assignment, and (surprisingly) role/grant editing all have `[DOC]` endpoints.
The trap is not "is there an API"; it is **which of three auth worlds a given endpoint lives in**, because
the same-looking `/users` path exists in all three with *different data models, different verbs, and
different credentials*, and picking wrong gets you a 401 (wrong host) or a silent behavior difference (wrong
model), not a helpful error.

The three worlds, and the one sentence that anchors each:

- **World 1 — Platform OAuth, `api.domo.com`, `Authorization: Bearer` `[DOC]`.** The stable public developer
  API. Users `/v1/users`, Groups `/v1/groups`, Audit `/v1/audit`. Bearer token minted from a
  `client_id:client_secret` via `client_credentials`. **A developer token does NOT work here** (401) — this
  host only accepts OAuth Bearer.
- **World 2 — Product APIs, `{instance}.domo.com`, `X-DOMO-Developer-Token` `[DOC, recently]`.** The APIs
  the Domo product's own admin UI calls: instance-host **Identity** Users (`/api/identity/v1/users`),
  **Roles Governance** (`/api/authorization/v1/roles`), dataset access-lists. Documented, but UI-parity and
  CORS-restricted / server-side-only, and freshly added — expect drift and per-instance/version variance.
  **OAuth Bearer does NOT authenticate this host**; it wants the dev-token (or the CLI's `X-Domo-
  Authentication` SID).
- **World 3 — undocumented `content/v2`, `{instance}.domo.com`, dev-token/SID `[REPO]`.** The paths this
  repo's provisioners actually call — `content/v2/users/me`, `content/v2/users/{id}`, `content/v2/users?
  limit=…`. Domo's own `api-reference.md` calls `content/v2` "stable, the same APIs the UI uses, but **not
  formally part of the published developer API**." The repo only ever **reads** here — there is no
  `content/v2` user/group *write* anywhere in the tree.

Two over-claims this skill exists to stop: **(1)** "role & grant management is UI-only" — false; World 2's
Roles Governance API creates/clones roles and rewrites a role's authorities via REST. **(2)** "the
`content/v2/users` paths are a public contract" — false; they are `[REPO]`, undocumented, and re-verify-per-
instance.

## Three worlds: match the host to the auth (the #1 mistake)

The single most damaging mistake is calling the right path on the wrong host with the wrong credential. Read
this table before writing any request:

| World | Host | Auth header | Verb style | User path | Data model note | Tier |
|---|---|---|---|---|---|---|
| 1 — Platform OAuth | `api.domo.com` | `Authorization: Bearer <oauth>` | REST, **PUT = full-replace** (⚠ **groups `PUT` is documented *partial*** — see Groups paragraph) | `/v1/users`, `/v1/groups` | `role` is a **string** (Admin/Privileged/Participant); update replaces the whole object **for users**, but the **group** `PUT` leaves omitted attrs unchanged | `[DOC]` |
| 2 — Product Identity | `{instance}.domo.com` | `X-DOMO-Developer-Token` (or CLI SID `X-Domo-Authentication`) | REST, **PATCH = partial** | `/api/identity/v1/users` | `roleId` is a **number**; `?parts=` selector; role assigned via `PATCH {roleId:N}` | `[DOC, recent]` |
| 2 — Product Roles | `{instance}.domo.com` | `X-DOMO-Developer-Token` | REST | `/api/authorization/v1/roles` | create is **clone-only** (`fromRoleId`); authority edit is **destructive full-array replace** | `[DOC, recent]` |
| 3 — content/v2 | `{instance}.domo.com` | dev-token / SID | **GET only in this repo** | `/api/content/v2/users/{me,id,?limit}` | undocumented; role read off the profile object | `[REPO]` |

Rules that fall out of the table:

- **A dev-token is worthless on `api.domo.com` and an OAuth Bearer is worthless on `{instance}.domo.com`.**
  A 401 here almost always means host↔credential mismatch, not a bad token.
- **World 1's `role` (string) and World 2's `roleId` (number) are different fields on different models.**
  Do not send `role:"Admin"` to the identity API or `roleId:1` to the OAuth API.
- **World 1 update is PUT (full-replace); World 2 update is PATCH (partial).** GET-merge-PUT on World 1 to
  avoid nulling fields; send only the changed keys on World 2.
- The **`X-DOMO-Developer-Token`** header (Product) and the CLI's **`X-Domo-Authentication`** SID header
  authenticate the *same* instance host; do not confuse either with the OAuth `Authorization: Bearer`.

## Documented surface #1 — Platform OAuth on `api.domo.com` `[DOC]`

The stable public developer API. Host `api.domo.com`, `Authorization: Bearer <token>`.

**Minting the token `[DOC]`.** `api.domo.com/oauth/token` with HTTP Basic `base64(client_id:client_secret)`,
`grant_type=client_credentials`, `scope=` space-separated. Response: `access_token`, `token_type=bearer`,
`expires_in`≈3599, `scope`, `role`, `userId`, plus two fields the `API-Authentication.yaml` 200 schema
documents that callers often miss — **`customer`** (string; the instance/subdomain name) and **`jti`** (string;
the token's JWT ID) `[DOC]` (non-load-bearing, but genuinely in the documented response body). In that spec
**`grant_type` is the only `required:true` query param; `scope` is optional** — a subset-limiter that narrows a
token to a subset of the client's *granted* scopes, never a way to exceed them `[DOC]`. (The spec's
`securityScheme` is labeled `API Key - 1` but declared `type: http, scheme: basic` — it is **HTTP Basic**, not
an API-key header; the label is a Stoplight naming quirk, not a second auth mode.) **The docs show this as a GET
with query params** — the common `POST` form is `[INFER]`, works in practice but isn't the documented shape. The token page's scope
enum `[DOC]` lists six: `account, audit, buzz, dashboard, data, user`. A **seventh, `workflow`, is real but
absent from that enum** — treat the six-item list as incomplete, not a closed set: the Projects & Tasks spec
(`projects.yaml`) `info.description` requires "the Workflow scope" `[DOC-prose]`, and live OAuth grants return
it in the `scope` string (`…data user workflow`) `[KB]`. So `workflow` is a real grantable scope `[KB]`; the
enum page simply omits it (a `[DOC]` inconsistency, not proof of absence). A **third** first-party `[DOC]`
corroboration: the `POST /clients` create-client `scope` array (see the credential-minting subsection below) is
a formal **7-item `enum`** that includes `workflow` — but that is a client-**grant** enum, still not proof
`workflow` is an accepted token-**request** scope. What stays unresolved: whether
`workflow` is a first-class assignable scope vs. a special-cased/internal one — no authenticated grant test
settles it here, so don't present the 6-vs-7 catalog as closed. Which scope a given endpoint needs is
softer — Users API needs `user`; "reads also need `data`" is community/`[INFER]`. **Never log the `/oauth/token` URL** — it
carries the scope in the query string and the Basic-auth `client_id:client_secret`. `client_secret` is
server-side only, never in front-end code or a commit.

**Credential-minting precursors — where the OAuth client and the instance SID come from `[DOC]`.**
Surface #1 above *consumes* a `client_id:client_secret` (→ OAuth Bearer); World 3 below *consumes* an instance
SID (`X-DOMO-Authentication`). Two first-party doc-hub specs document how each of those credentials is
originally **minted**. Both are **credential-producing mutations → EXECUTION-gated** (documenting them is
autonomous; a live create-client / login call is not — it produces a secret and would gate on explicit human
intent).

- **Create OAuth client — `POST https://api.domo.com/clients` `[DOC]` (`Client-API.yaml`).** "Creates an OAuth
  client for use with the Get Access Token endpoint" — i.e. it MINTS the `client_id`/`client_secret` that
  Surface #1's `/oauth/token` treats as pre-existing inputs. Request headers **`X-DOMO-Authentication`** (an
  instance SID) and **`X-DOMO-CustomerDomain`** are both `required:true`; body `{name` (required, "must be
  unique"), `description`, `scope` (required — an **array whose item `enum` lists seven**: `account, audit,
  buzz, dashboard, data, user, workflow`)`}`. 201 → `{name, description, scope[], user` (integer; the creator's
  id), `client_id, client_secret` (`format: password`), `authorized_grant_types` (array — item enum is the
  single value `client_credentials`)`}`. ⚠ **Do NOT present this as a stable public programmatic API.** The
  `API-Authentication.yaml` Quickstart documents client creation **exclusively as a Developer-Portal UI
  walkthrough** (log in → Manage Clients → new client), and the KB routes it to **Admin ▸ Authentication ▸ API
  Clients** (a surface Domo is deprecating). Read `POST /clients` as the **plausible session-authed backend the
  UI calls** `[INFER]`, not a supported public endpoint. ⚠ **Its auth is internally self-contradictory:** the op
  declares the SID+CustomerDomain headers as `required` **parameters** `[DOC]`, sets op-level `security: []`
  (none) `[DOC]`, while the file-global `security` is HTTP Basic `[DOC]` — three conflicting signals; the SID
  headers are plain `parameters` bound to no `securityScheme`, so "SID+CustomerDomain is THE auth" is `[INFER]`.
  ⚠ This 7-item `scope` enum is the client-**grant** layer — a first-party `[DOC]` source that `workflow` is a
  real 7th scope (reinforcing the 6-vs-7 note above), but it proves only that a client MAY be *granted*
  `workflow`, **NOT** that `workflow` is an accepted `/oauth/token` token-**request** scope (that bridge stays
  `[KB]`, live grants). Do not rewrite the scope catalog to "exactly seven" or treat either enum as closed.

- **Create instance session identifier (SID) — `POST https://{customer}.domo.com/api/content/v2/authentication`
  `[DOC]` (`Customer Instance APIs` spec).** "Create a Session Token to be used within the `X-DOMO-Authentication`
  header" — the previously-uncharted **creation** of the instance-host session credential that World 3 (and the
  CLI SID) *consume*. Body `{method` (**enum `[password, exptoken]`**), `emailAddress` (required when
  `method: password`, `format: email`), `password` (required when `method: password`, `format: password`)`}`.
  **`Origin` header `required:true`** and must match `https://{customer}.domo.com` — a same-origin/CSRF guard, so
  this is browser-shaped, not a clean server-to-server call. `method: exptoken` instead **exchanges the `_dsidv1`
  browser cookie** (declared a `cookie` parameter, required for that method). 200 → schema `required: [userId`
  (integer), `sessionToken` (string)`]` — **those two fields only**. ⚠ **`success` / `twoFactorInfo` / `userRole`
  appear ONLY in the spec's `x-examples`, OUTSIDE the declared 200 schema — do NOT chart them as response
  fields.** MFA-gated accounts may return a 2FA challenge, so a valid password does **not** guarantee an
  immediately-usable `sessionToken` `[INFER]`. ⚠ **This is a login endpoint with a plaintext `password` in the
  request body** — never log, echo, or commit the request body (`emailAddress`+`password`), and treat the
  returned `sessionToken` as a **bearer-equivalent secret** (it authenticates AS the user via
  `X-DOMO-Authentication`): server-side only, never logged or committed. ⚠ **Do NOT equate this `sessionToken`
  with the repo's own SID.** This repo does not call `content/v2/authentication`; it mints its SID via `POST
  /api/oauth2/token` (refresh grant) → `GET /api/oauth2/sid` returning field **`sid`** (see
  `../docs/api-reference.md` Method 2). Same *class* of instance-host session credential, both target the
  `X-DOMO-Authentication` header, but **interchangeability is `[INFER]`, not attested** — cross-reference, never
  canonicalize the two as one mint path.

**Users `/v1/users` `[DOC]`:**

| Op | Endpoint | Notes |
|---|---|---|
| Create | `POST /v1/users` | `name`, `email`, `role` are `required:true` on the **query params** — **not** the JSON body (the requestBody schema has **no `required[]`**); the op exposes **both** a query and a body interface for these fields, so send the required trio on the **query** side `[DOC]`. Optional `title/alternateEmail/phone/location/timezone/locale/employeeNumber`; `?sendInvite=true` (boolean). ⚠ **`employeeNumber` must be sent as an `integer`** — the prose attributes table types it `string`, but **both** the create-body schema and the GET-one response schema type it `integer`; a string risks a create-time type rejection `[DOC]`. Response carries `id/createdAt/updatedAt/groups/image` but **omits `timezone`+`locale`** you sent; the returned `groups` is an **array of `{id:integer, name:string}` objects**, not a bare id array `[DOC]`. |
| Read one | `GET /v1/users/{id}` | On a **deleted** user this returns a **subset object that includes `deleted: true`** (not a 404) — the same tombstone-on-GET pattern already charted for DataSets/Streams in `domo-datasets.md` (`GET /v1/datasets/{id}`, `GET /v1/streams/{id}`). The GET-one **response schema also surfaces `roleId`** (typed `string` here) and `groups` as an **array of `{id:integer, name:string}` objects** — so a plain read **is** a `roleId` discovery path (see the `roleId` note below). `[DOC]` |
| List | `GET /v1/users?limit&offset` | `limit` default 50 / **max 500**; response is a **bare JSON array**; **no documented server-side email/name filter** → paginate + filter client-side. |
| Update | `PUT /v1/users/{id}` | docs are internally contradictory ("omitted params unchanged" vs "Known limitation: all fields required") → operationally **GET-merge-PUT / treat as full-replace**. |
| Delete | `DELETE /v1/users/{id}` | 204, **permanent**. ⚠ Note: this op is **not present in the current WAF-lifted `User-API.yaml` body** (which documents only `GET`/`PUT` `{id}` + `POST`/`GET /v1/users`) — the `DELETE` charted here rests on the prior corpus/KB, **not** re-confirmed by this spec render; MISSING ≠ removed, so keep it but don't cite this spec as its source. `[DOC/KB]` |

- `role` documented values are **exactly `Admin` / `Privileged` / `Participant`** — Editor/Social are *not*
  accepted in this OAuth field even though five roles exist product-wide (see Roles section).
- `roleId` is **NOT confined to the update args** (correcting the earlier "only in the *UPDATE* argument docs /
  no discovery path"): the **GET-one response schema surfaces `roleId`**, so `GET /v1/users/{id}` **is** a valid
  OAuth path to discover a given user's current `roleId` `[DOC]`. ⚠ **Read/write type split:** the GET-one
  response types `roleId` as **`string`**, while the write-side role-id param is an **`integer`** — round-trip
  with care. ⚠ **That write-side param is literally spelled `roled` (integer), NOT `roleId`** `[DOC]` — an
  apparent spec typo that is wire-load-bearing: sending `roleId` on the `PUT` is silently ignored and the role
  will not change. You still cannot *list* all valid roleIds via OAuth (for the full catalog use the KB table or
  World 2) — but you CAN read a given user's current one.

**Groups `/v1/groups` `[DOC]`:** `POST` (create — request body documents **only `name`** (`required:[name]`),
*not* `{name[,default]}`; documented status is **`200`** returning a full object `{id:int, name, active:bool,
creatorId:string, default:bool}` — the portal yaml says `200`, so treat the earlier `201` as **contested**, and
note `creatorId` is typed **string** in this create response while `id` is `int`), `GET` (list), `GET /{id}`,
`PUT /{id}` (no PATCH) — a **documented partial update** (`[DOC]`: "any parameter left out … will remain
unchanged"; body `{name, active}`), which **corrects** the earlier "full-replace `[INFER]`" note and **contests
the World-1 table row's "PUT = full-replace" for groups only** (the Users `PUT` carries its own "all fields
required" caveat and is a separate spec, so the blanket row is not overturned wholesale) — and `DELETE /{id}`
(**204 No Content; permanently deletes the whole group — destructive & irreversible per the spec's own
`<Warning>`; EXECUTION human-gated**). Paging `[DOC]`: both `GET /v1/groups` and `GET .../users` take `limit` +
`offset` query params (**default 50 / max 500 stated in the param *description* prose only — documentation, not
a machine-enforced JSON-Schema `maximum`, same posture as Audit below; and `limit`/`offset` are typed `integer`
on `GET /v1/groups` but `string` on `GET .../users`**). Membership: `PUT
/v1/groups/{group_id}/users/{user_id}` (add → 204), `DELETE .../users/{user_id}` (remove → 204), `GET
.../users` returns **user IDs, not full user objects** (a bare integer array). Confirmed fields:
`id/name/default/active/creatorId`; **`memberCount` is now `[DOC]`** (typed `integer` in the GET-one and GET-list
response schemas — upgraded from `[INFER]`), while **`userIds` stays `[INFER]`** (only in the prose attributes
table + as that bare integer-array return, never a named response field). `id` is doc-typed inconsistently
(String in the portal / Integer in the yaml; the values are numeric). **Tombstone-on-GET edge `[DOC]`:** `GET
/{id}` for a group whose **customer** was deleted returns a *subset* including a `deleted` property = true
(**prose-only** — stated in the 200 response *description*, not in the schema properties list). **This manages
ordinary security groups only** — not Publication Groups, not Publish subscriber groups (see traps section).

**Audit `/v1/audit` `[DOC]`:** `GET` the read-only Activity Log (info.title "Activity Log API" v1.0,
`bearerAuth`). Query params `[DOC]`: **`start` is the only required one** (`required: true`, `number`,
epoch-ms) — `user` (string userId filter), `end` (`number` ms), `limit` (integer), `offset` (integer) are
all optional. ⚠ **`limit` default 50 / max 1000 and `offset` default 0 live ONLY in the parameter
*description* strings — they are NOT JSON-Schema `default`/`maximum` keywords, so treat them as
documentation, not machine-enforced** (contrast World-2's real `default` below). The **200 is a SINGLE
inline object, not an array and not an envelope** (`components.schemas` is empty `{}`; the schema is fully
inline) — do NOT code a list/pagination wrapper against it even though `limit`/`offset` imply list
retrieval. It declares **15 properties**: `actionType, actorId, actorName, additionalComment,
browserDetails, device, eventText, ipAddress, objectId, objectName, objectType, time, userId, userName,
userType`. ⚠ **`time` here is a STRING** — a formatted `YYYY-MM-DD hh:mm:ss AM/PM` datetime, NOT epoch-ms
(this diverges from World-2 audit, whose `time` is int64 ms — never state one `time` type across both).
`actorId`/`actorName` carry **proxy/impersonation semantics** ("Id / Name of proxying user if applicable").
Two spec-internal inconsistencies, with the **response schema as the authoritative machine-readable source
over the prose `### Attributes` table**: (1) `actorId` is `type: integer` in the 200 schema but typed
"Long" in the Attributes table; (2) `actionType` is present in the schema (string) but ABSENT from the
Attributes table.

## Documented surface #2 — Product APIs on `{instance}.domo.com` (dev-token) `[DOC]`

These are the APIs the Domo product's own admin UI calls. Host `{instance}.domo.com`,
`X-DOMO-Developer-Token` (or CLI SID `X-Domo-Authentication`). All are **UI-parity, CORS-restricted /
server-side-only, and recently documented** — re-check the live docs and expect per-instance/version drift.

**Identity Users `/api/identity/v1/users` `[DOC, recent]`** — a *different data model* from World 1's
`/v1/users`:

| Op | Endpoint | Notes |
|---|---|---|
| Create | `POST /api/identity/v1/users` | body `displayName`, `emailAddress`, `roleId` (**number**). |
| List | `GET /api/identity/v1/users` | |
| Read one | `GET /api/identity/v1/users/{id}` | `?parts=MINIMAL\|SIMPLE\|DETAILED\|GROUPS\|ROLE` selector. |
| Update | `PATCH /api/identity/v1/users/{id}` | **partial** — send only changed keys; **assign role via `{roleId:5}`**. |
| Delete | `DELETE /api/identity/v1/users/{id}` | (Product also documents `DELETE {instance}.domo.com/users/{id}`.) |

Note the contrasts with World 1: `displayName`/`emailAddress` (not `name`/`email`), `roleId` number (not
`role` string), **PATCH** partial-update (not PUT full-replace).

**Domo Users API — bare `{instance}.domo.com/users` `[DOC]`** (`product/user-api.yaml`, title "Domo Users
API", dev-token `X-DOMO-Developer-Token`) — a **distinct documented path** from the `/api/identity/v1/users`
table above. The two share the `displayName`/`emailAddress`/`roleId` data model **and** the `?parts` selector,
but the paths differ — **do NOT treat a fact proven here as proven for `/api/identity/v1/users`** (or vice-versa).
This is the OpenAPI spec behind the "Product also documents `DELETE {instance}.domo.com/users/{id}`" note above;
it documents the full CRUD set on **bare `/users`**:

| Op | Endpoint | Response / notes `[DOC]` |
|---|---|---|
| Create | `POST /users` | body `{displayName, emailAddress, roleId}` all required → **200** single `User`. Documents **400 / 401 / 409** — the **409 Conflict** ("user already exists") means a duplicate create **fails loudly, it does not upsert**. |
| List | `GET /users` | **200** → `UserListResponse` (`{users:[]}` wrapper). Also takes the **`?parts=MINIMAL\|SIMPLE\|DETAILED\|GROUPS\|ROLE`** selector — `parts` is **NOT a read-one-only** param here (the same `PartsQueryParam` is declared on both list and read-one). |
| Read one | `GET /users/{id}` | ⚠ **200 → `UserListResponse` (`{users:[]}` wrapper), NOT a single `User`** — a spec-internal oddity, since Create and Update each return a single `User`. Also takes `?parts`. `401 / 404`. |
| Update | `PATCH /users/{id}` | partial (`UpdateUserRequest`) → **200** single `User`; `400 / 401 / 404`. |
| Delete | `DELETE /users/{id}` | ⚠ **200 with an *integer* body** (schema `type: integer`, example `1`; the spec assigns it **no documented meaning** — do **not** read it as a "deleted-count"), **NOT 204**; `401 / 404`. Contrast **World-1** `DELETE /v1/users/{id}` above (charted **204, no body**) — same verb, different status/shape across the two worlds. |

- **The `User` object carries `attributes[]` `[DOC]`** — an array of `UserAttribute {key: string, values: string[] | int[]}`
  (`values` is a `oneOf` of `array<string>` | `array<integer>`): Domo user **custom attributes**. Distinct from the
  World-1 audit-log Attributes table and from dynamic-group attribute-based membership elsewhere in this file.
- **`userName` is a field distinct from `emailAddress` `[DOC]`** — the `User` schema lists both as separate strings
  (`userName` = the login/username field, **not** the email). ⚠ The `userName` that appears elsewhere in this skill
  (the audit / Activity-Log event columns) is a **different surface** — do not conflate.
- All rows are `[DOC]` from `product/user-api.yaml`; **zero repo precedent** (never `[REPO]`). Create/Update/Delete are
  **write** ops — **EXECUTION-gated** like the other identity mutations.

**Roles Governance `/api/authorization/v1/roles` `[DOC, recent]`** — this is the endpoint that disproves
"role management is UI-only":

| Op | Endpoint | Notes |
|---|---|---|
| Create | `POST /api/authorization/v1/roles` | **clone-only**: body `{name, description, fromRoleId}` — there is **no blank-role creation**. |
| List | `GET /api/authorization/v1/roles` | |
| Read one | `GET /api/authorization/v1/roles/{roleId}` | fields `id/name/description/authorityCount/userCount/created/modified` (epoch-ms). |
| Edit grants | `PATCH /api/authorization/v1/roles/{roleId}/authorities` | body is the **COMPLETE authority string array** — **destructive full-replace, not additive**. Example: `["dataset.manage","dataset.export"]`. |
| Delete | `DELETE /api/authorization/v1/roles/{roleId}` | 204. |

- Auth is the **dev-token, not OAuth**.
- **`PATCH .../authorities` replaces the whole set** — to add one grant you must GET the current array, append,
  and PATCH the union; sending `["dataset.export"]` alone strips every other authority.
- **No documented read of the current authority list** `[DOC]` — `GET .../{roleId}` returns only
  `authorityCount` (a *count*), and `.../{roleId}/authorities` exposes **only `PATCH`** (its `{status, message}`
  response does not echo the array). So the "GET the current array" step above is **`[INFER]` live behavior,
  not a spec-documented endpoint** — a live read may work, but the spec defines none.
- There is **no documented user→role assignment endpoint on this surface** — assign the role on the *user*
  (World 2 Identity `PATCH {roleId}` or World 1 `role`), not on the role.
- The authority-token **full enum is not published** — the docs show a bare string array with ~2 examples,
  so the complete set of valid tokens is `[INFER]`; discover them live.
- **Whether role changes are audited is undocumented** `[INFER]` — the Roles Governance spec is silent on
  whether create / delete / authority-`PATCH` emit Activity-Log events, or under which `objectType` they'd
  surface. Don't assume coverage; to check, query the audit surface's runtime `/objectTypes` list (see the
  Activity Log / audit sections below) for a role-related type.

**Dataset access-list (distinct from PDP row-filtering) `[DOC, recent]`:** `GET
/api/data/v3/datasources/{id}/permissions`, `POST .../share`, `DELETE .../permissions/USER/{userId}`. This
is *who can see the dataset*, not *which rows* — PDP row policies live in `domo-datasets.md`.

**Groups management — instance-host `content/v2/groups` `[DOC]` existence / `[INFER]` reliability.** A
first-party doc-hub OpenAPI spec ("Group Documentation", host `{instance}.domo.com`, auth
`X-DOMO-Developer-Token` — the *same dev-token world* as the rest of surface #2) publishes a
**groups-management** surface the World-3 framing (below) otherwise treats as undocumented:

| Op | Endpoint | Notes |
|---|---|---|
| Create | `POST /api/content/v2/groups` | body `name`+`type` required (+ optional `description`); `type` is the **only formal `enum` in the spec**: `[closed, open, dynamic]`. Response `CreateGroupResponse{id}` where **`id` is a STRING** — *create-response only*. |
| Fetch | `GET /api/content/v2/groups/{group}` | path param `group` **only — no query params**. (Do NOT attach a `?parts` selector — that belongs to the separate `GET /api/identity/v1/users/{userId}`.) Returns `GroupResponse` (id/name/type/userIds/creatorId/memberCount/guid/description/hidden/default/active). |
| Add member | `PUT /api/content/v2/groups/{group}/user/{userId}` | no body → bare JSON **boolean**. |
| Remove member | `DELETE /api/content/v2/groups/{group}/removeuser/{userId}` | no body → bare JSON **boolean**. |
| Bulk-remove | `PUT /api/content/v2/groups/access` | body is an **array** of `{groupId, removeMembers:[{type, id}]}` → boolean. |

- ⚠ **Tier split — existence is `[DOC]`; callable-reliability / behavior-in-practice is `[INFER]`/drift-prone.**
  This repo executes **none** of these five ops (repo-wide grep of `removeuser` / `groups/access` /
  `CreateGroupRequest` / `content/v2/groups/` = 0 non-doc files) — **never tag them `[REPO]` or "proven live."**
- ⚠ **Spec-internal id-type inconsistency:** the **create** response (`CreateGroupResponse`) types `id` as a
  **string**, but the **fetch** response (`GroupResponse`) types `id` (and `userIds`/`creatorId`/`memberCount`)
  as **integer** — the same logical group id, two JSON types in one spec. Never state one uniform
  `content/v2/groups` id type; and note both differ again from World-1 OAuth `/v1/groups`.
- ⚠ **This complicates — but does not overturn — the World-3 framing.** That a doc-hub OpenAPI spec publishes
  `content/v2/`**`groups`** write ops is an **unresolved Domo-internal doc inconsistency** vs the repo's
  `../docs/api-reference.md` "not formally part of the published developer API" prose (analogous to the
  workflow-scope-enum inconsistency documented elsewhere) — it is **not** proof that `content/v2/groups` is "a
  public/published developer API" (that label is World-1 `api.domo.com/v1/groups`). The repo-scoped
  write-absence fact below **stays true**; this refines only the adjective "undocumented," and **only for the
  groups sub-path** (NOT `content/v2/users`).

**App-Framework in-app APIs — `{instance}.domo.com/domo/*`, app bearer-JWT `[DOC]` (NOT dev-token).** A
*distinct auth world* from the rest of surface #2: these `/domo/*` endpoints authenticate with an **app
bearer-JWT** (spec `securityScheme bearerAuth`: `type: http, scheme: bearer, bearerFormat: JWT` →
`Authorization: Bearer <JWT>`), the token an embedded Custom App receives from Domo's in-app auth flow —
**not** the `X-DOMO-Developer-Token`. Carry the App-Framework per-instance/version drift hedge (`[INFER]`) on
exact shapes.

| Op | Endpoint | Notes |
|---|---|---|
| Users (list) | `GET /domo/users/v1` | resolve users from inside an app context; `includeDetails` query. |
| User (one) | `GET /domo/users/v1/{userId}` | thin per-ID variant of the list; `includeDetails` query. |
| Groups (all) | `GET /domo/groups/v1` | **READ-ONLY** — no write verbs on this surface. |
| Group by name | `GET /domo/groups/v1/name?groupName=` | here `Group.type` is a **free-form string** (e.g. `adHoc`/`directory`) — **no enum**, and different from content/v2's `[closed,open,dynamic]`. |
| Group by id | `GET /domo/groups/v1/{groupId}` | |
| Groups by user | `GET /domo/groups/v1/user/{userId}` | |
| Avatar image | `GET /domo/avatars/v2/{entityType}/{entityId}` | **the material net-new** — returns a **binary image** (`image/jpeg`\|`png`\|`jpg`, `format: binary`). `entityType` enum is **`[USER]` in this spec only** (do NOT assume PAGE/DATASET); `size` enum `[100, 300]`; `defaultForeground`/`defaultBackground`/`defaultText` query strings drive a fallback initials-avatar. |

- The groups GETs are the READ-ONLY counterpart to the users list; the **write** verbs on groups belong to
  the `content/v2/groups` block above (dev-token), NOT here.
- Avatar is in-scope for identity-access **only because `entityType` is USER-restricted in this spec**; a
  broader avatar spec carrying PAGE/DATASET entities would fall outside identity ownership (frontier flag).
- `[DOC]` version-drift observations: the avatar path is `avatars/**v2**` while the World-1 OAuth user model
  exposes an `avatarKey` **string** (v1-style) — two avatar representations; and `entityId` is typed integer
  (no `format`) while `userId` elsewhere is `int64`.

**Activity Log (product/dev-token) `[DOC]`** — a *separate* Activity Log from World-1's OAuth `/v1/audit`;
same host/auth as the rest of surface #2 (`{instance}.domo.com`, `X-DOMO-Developer-Token`). Two endpoints:

| Op | Endpoint | Notes |
|---|---|---|
| Query entries | `GET /api/audit/v1/user-audits` | `start`+`end` **both required** (`integer`/`int64`, epoch-ms); `offset` (**real `default: 0`**), `limit` (**real `default: 300`** — a genuine JSON-Schema keyword, unlike World-1's description-only 50), `objectType` (**free-form `type: string`, comma-separated, NO `enum`**). |
| Discover types | `GET /api/audit/v1/user-audits/objectTypes` | Returns a **runtime array of strings** of currently-queryable object types (e.g. `ACCOUNT`, `DATAFLOW_TYPE`, `DATA_SOURCE`). |

- ⚠ **`objectType` is NOT a closed enum.** The `/objectTypes` endpoint is a **runtime discovery list**, not a
  schema enum — never hard-code its output as a validated/fixed set; query it live and expect drift.
- The **200 for `/user-audits` is an ARRAY** of `ActivityLogEntry` (contrast World-1's single object — keep the
  two worlds' response shapes separate, never canonicalized). `ActivityLogEntry` has **8 properties**:
  `userName, userId, userType, actionType, objectType, additionalComment, time, eventText`.
- ⚠ **`time` here is `integer`/`int64` epoch-ms** — the opposite of World-1 audit's formatted STRING.
- Documented responses are **only `200` and `401`** (401 = `ErrorResponse` = `{message: string}`); other codes
  are **not documented in this spec** (≠ "cannot occur").

## Roles, grants & authorities

**Five built-in roles with fixed roleIds `[KB]`** (Governance Toolkit KB): **Admin=1, Privileged=2,
Editor=3, Participant=4, Social=5**. `Privileged` is the default role for new users. The roles are
**cumulative** in capability ordering. Note the mismatch that bites: World 1's OAuth `role` field accepts
only `Admin/Privileged/Participant` — `Editor` and `Social` exist as roleIds but are **not** valid strings
in that field.

**Custom roles `[KB]`** are **Enterprise-only** and created by **duplicate-then-edit** (which is exactly why
the Roles Governance `POST` is clone-only, `fromRoleId`).

**Grants vs authority tokens `[KB]`/`[INFER]`.** The admin UI shows grants by **display name** — "Manage All
Roles", "Assign Users to a Role", "Manage DataSet". The Roles Governance `authorities` array uses **dotted
tokens** — `dataset.manage`, `dataset.export`. The **mapping from display name → dotted token is not
published** (`[INFER]`); the two examples in the docs are the only confirmed tokens. Do not invent tokens
from grant names — discover the live strings from an existing role at runtime (the spec documents **no `GET`
on `.../authorities`** — only `PATCH`; see the Roles Governance caveat above — so that read is `[INFER]`).

There is **no standalone "Manage PDP" grant** — PDP-policy management rides on DataSet ownership, Admin, or
the "Manage DataSet" grant (see PDP section).

## Identity ↔ PDP linkage (cross-ref `domo-datasets.md`)

**PDP row-policy CRUD itself belongs to [`domo-datasets.md`](domo-datasets.md)** (`POST/GET/PUT/DELETE
api.domo.com/v1/datasets/{id}/policies`, filter/operator body, column masking). This section covers only
where identity and PDP touch — the parts a user/group-management task must not get wrong.

- A policy references members by **numeric-ID arrays** — `users[]` and `groups[]` — plus a `type`
  (`'user'` | `'system'`). The policy `id` is numeric; **only `dataset_id` is a UUID**. `groups[]` entries
  are **security-group IDs** (World 1 `/v1/groups`), not Publication Groups.
- **The arrays are a stored snapshot.** GET returns exactly what was written. **Dynamic access comes from
  group-membership resolution at *evaluation* time, not from the array auto-updating.** Never present
  "add a user to a group and the policy updates" as an API-payload guarantee — the payload doesn't change;
  the *evaluation* picks up new members. Adding a member is a group-membership call (World 1
  `PUT /v1/groups/{gid}/users/{uid}`), not a policy edit.
- **Users and groups must exist before the policy is created** — you cannot reference an ID that isn't
  provisioned yet. Provision identity first, then write the policy.
- Owners / co-owners are **auto-added to the default "All Rows" policy**; you don't (and can't cleanly)
  remove them via PDP.
- Semantics that affect identity reasoning: **OR between policies, AND within a policy**; column-masking is
  **highest-listed-rule-wins** plus a system control group; **DataFlow INPUT datasets can't be PDP-limited**
  (outputs only); and **Publication Groups supersede PDP** (a dashboard-level RLS that overrides row
  policies — see traps).

## The `content/v2` surface — what the repo actually calls `[REPO]`

This is what the the original workspace repo *actually executes* for identity — and it is **read-only**. Domo's own
`../docs/api-reference.md` frames `content/v2` as "stable, the same APIs the UI uses, but not formally part
of the published developer API." Treat every row as `[REPO]`: undocumented, re-verify per instance/version,
**never cite as a documented contract**.

⚠ **One exception to "undocumented" — the `content/v2/groups` sub-path only.** A first-party doc-hub
OpenAPI spec *does* publish content/v2/groups **write** ops (see the groups-management block in surface #2);
that is an unresolved Domo-internal doc inconsistency, and its existence is `[DOC]` / reliability `[INFER]`.
It does **not** change the fact below: the repo itself still executes **zero** `content/v2` writes (the ops
are documented, not called here), and `content/v2/users` remains fully `[REPO]`/undocumented.

| Path | Where it's called | What it returns |
|---|---|---|
| `GET api/content/v2/users/me` | ~5 provisioners (equipment-inventory, inventory-management, asset-lifecycle, pl-summary, support-center) | current user profile — the standard "who am I" resolve |
| `GET api/content/v2/users/{id}` | support-center `_is_admin_user` | profile incl. role, read off to gate admin |
| `GET api/content/v2/users?limit=500&offset={n}` | `asset_lifecycle_service.py` (CE, tokenless) | user page for inventory/listing |
| `GET api/content/v3/users?limit=1` | **only in `sales-margin-impact/AGENT.md` + `production-priority-app/README.md` — documented, not executed** | v3 variant, existence/probe |
| `GET api/content/v2/users/search?q=` , `GET api/content/v2/groups?limit=50` | **only in `../docs/api-reference.md` tables — not executed** | documented-in-repo, unproven live |
| `GET api/identity/v1/users/search` | `workflow-env-vars.md` (shape "TBD — verify via DevTools") | search, shape unconfirmed |

Load-bearing facts:

- **No write verbs.** There is **no** `POST`/`PUT`/`PATCH`/`DELETE` on users or groups anywhere in the repo
  — every identity mutation this repo needs is done through the product UI or would be a *new* capability.
  When the first real identity **write** lands, document it as a fresh `[REPO]` row and, if a live instance
  is available, empirically confirm the verb before trusting it. (⚠ Scope note: this "no write verbs" fact is
  about **users/groups**. The documented `POST /api/content/v2/authentication` session-mint — surface #1's
  credential-minting subsection — is a `content/v2` write, but it is a **session-identifier mint, not a
  users/groups write**, and this repo does not call it; do not over-generalize "all of `content/v2` is
  read-only.")
- The CE reads run **tokenless** via `send_request`/`sendRequest` (invoking user's context) — that mechanic
  is owned by [`domo-code-engine.md`](domo-code-engine.md); this skill just notes that `content/v2/users`
  reads ride on it.
- All three instance-host auth headers work for these reads: **dev-token**, and the CLI **SID**.

## SCIM & SSO provisioning `[KB]`/`[INFER]`

**SCIM `[KB]`/`[INFER]`.** SCIM is **IdP-side provisioning configuration**, not a general-purpose Domo REST
API you script against. It is **Enterprise-gated**, an **SSO prerequisite**, and uses an **admin-generated
Bearer token that is SEPARATE from the OAuth `client_credentials` token** — do not reuse one for the other.
It exposes the six standard SCIM schemas (Users/Groups/etc.). **SCIM is absent from Domo's doc-hub repo** —
what's documented lives in third-party/KB sources, so treat schema/endpoint specifics as `[KB]` and verify
against the actual IdP connector.

**SSO `[KB]`/`[INFER]`.** SSO is **configuration only** — there is **no REST provisioning endpoint** to
create/toggle SSO. The stronger claim "**no** user-provisioning API exists anywhere" is `[INFER]` (an
argument from absence): the safe statement is that *this cycle found none documented*, not that none can
exist. Just-in-time provisioning happens through the IdP + SCIM path, not a Domo endpoint you call.

## The three unrelated "group" meanings, and other governance traps

**"Group" means at least three unrelated things in Domo.** Conflating them sends the right call to the wrong
API:

| "Group" | What it is | API home | Tier |
|---|---|---|---|
| **Security group** | membership container for users; referenced by PDP `groups[]` and role-independent access | World 1 `/v1/groups`, World 2 identity | `[DOC]` |
| **Publication Group** | dashboard/page **row-level view filtering** (RLS); **supersedes PDP** | App Studio surface → [`domo-appstudio.md`](domo-appstudio.md) | `[KB]` |
| **Publish subscriber group** | audience of a cross-instance **Publish** replication job (Domo Everywhere) | → [`domo-everywhere.md`](domo-everywhere.md) | `[KB]` |

This skill's `/v1/groups` covers **only the security group**. When a task says "group", disambiguate before
picking an endpoint.

**Six group *types* `[KB]`** (for security groups): a user can create **Open / Closed / Dynamic**; a user
**cannot** create **Directory (SSO) / System / Ad hoc**. **Dynamic** groups are **attribute-based** —
membership is computed, so you don't `PUT .../users/{id}` into them.

Other governance traps:

- **`content/v2/users` reads returning role** are reading the *product* role model — don't reconcile that
  numeric/string against the OAuth `role` string blindly (the two worlds differ, per the worlds table).
- **Deleting a user/group/role is permanent and outward-facing.** World 1 `DELETE /v1/users/{id}` is 204 +
  irreversible; role delete `DELETE .../roles/{roleId}` orphans nothing gracefully. Treat any identity
  delete as high-impact (see Safety).
- **`PATCH .../authorities` is a full-array replace** — the single easiest way to silently strip a role's
  grants (repeated here because it is the highest-blast-radius write on this whole surface).

## Do NOT claim as documented fact

Each of these is a real, tempting over-claim. State the hedge, not the confident version.

1. **"The `content/v2/users` paths are a public API."** No — `[REPO]`, undocumented, read-only in this repo,
   re-verify per instance/version. Domo itself says content/v2 is "not formally part of the published
   developer API."
2. **"Role & grant management is UI-only."** No — World 2's Roles Governance API (`/api/authorization/v1/
   roles`, dev-token) creates/clones roles and edits authorities. (But it is *recently* documented — treat
   its exact shapes as drift-prone.)
3. **"You can create a blank custom role via API."** No — creation is **clone-only** (`fromRoleId`), and
   custom roles are **Enterprise-only**.
4. **"`PATCH .../authorities` adds a grant."** No — it **replaces the entire authority array**; omitted
   tokens are removed.
5. **"The authority tokens are `dataset.manage`, `dataset.export`, …"** — those two are the only documented
   examples; the **full enum is unpublished** (`[INFER]`). Discover live.
6. **"Grant display names map predictably to dotted tokens."** No — the name→token mapping is **not
   published** (`[INFER]`).
7. **"OAuth `role` accepts all five role names."** No — only **`Admin/Privileged/Participant`**; Editor/
   Social are valid roleIds but not valid strings in that field.
8. **"`/oauth/token` is a POST."** The docs show a **GET with query params**; the POST form is `[INFER]`.
9. **"`GET /v1/users` can filter by email/name server-side."** No documented filter — **paginate + filter
   client-side** (limit max 500).
10. **"World 1 PUT is a partial update."** Docs contradict themselves; **treat as full-replace / GET-merge-
    PUT** to avoid nulling fields.
11. **"A dev-token works on `api.domo.com`" / "OAuth Bearer works on `{instance}.domo.com`."** No — each host
    accepts only its own credential; a 401 is usually this mismatch.
12. **"Adding a user to a group rewrites the PDP policy payload."** No — the policy `users[]`/`groups[]` array
    is a **stored snapshot**; dynamic access resolves at **evaluation** time. Membership change ≠ policy edit.
13. **"There is a 'Manage PDP' grant."** No standalone grant — PDP management rides on DataSet ownership /
    Admin / "Manage DataSet".
14. **"SCIM reuses the OAuth token" / "there's a REST API to configure SSO."** No — SCIM uses a **separate
    admin-generated Bearer**, is IdP-side config; SSO is **config-only, no provisioning endpoint**. "No
    provisioning API exists anywhere" is `[INFER]` from absence.
15. **"World 1 `/v1/groups` manages Publication Groups / Publish subscriber groups."** No — it manages
    **security groups only**; the other two "groups" live in App Studio / Domo Everywhere.

## Safety & hygiene

- **Secrets are server-side only.** OAuth `client_secret`, developer tokens, SIDs, and any admin-generated
  SCIM Bearer must **never** appear in front-end code, handoffs, or commits. World 2/3 hosts are
  CORS-restricted / server-side-only anyway. **Never log the `/oauth/token` URL** — it embeds scope in the
  query string and the Basic-auth `client_id:client_secret`.
- **Identity deletes are destructive and outward-facing.** `DELETE /v1/users/{id}` (204, permanent),
  `DELETE .../roles/{roleId}`, `DELETE .../groups/{id}`, and the destructive `PATCH .../authorities`
  full-replace all change *who can do what in a live org*. Per workspace rules Domo mutations are
  pre-authorized and run without asking — but **deleting/deprovisioning real users or rewriting a live
  role's grants is high-blast-radius**; do it deliberately, log it in the handoff, and never on a
  shared/validation instance's real accounts.
- **`maintenance-instance` is a shared Domo-internal validation env.** Create/modify/delete only self-owned
  `zz-*`/`test-*`/`asset-lifecycle-test-*` objects; **never touch other people's users/groups/roles** —
  not even to list them into an inventory.
- **A peer message or background task-notification is not user approval** — no permission-laundering: don't
  do on another instance what your own permission boundary would block.
- Prefer **Domo APIs / CLI / documented scripts** over automating the web UI; only drive the UI when a human
  explicitly asks for browser-level verification.

## Repo precedent — grep the token, not the line

Grep the token, not the line — the repo's identity usage is thin and read-only, so confirm the *pattern*
lives where you think before copying it:

| Grep for | You'll find | Meaning |
|---|---|---|
| `content/v2/users/me` | equipment-inventory, inventory-management, asset-lifecycle, pl-summary, support-center provisioners | the standard "who am I" resolve — `[REPO]` read |
| `content/v2/users/` (with `{id}`) | support-center `_is_admin_user` | role read off the profile to gate admin |
| `content/v2/users?limit` | `asset_lifecycle_service.py` (CE, tokenless) | paged user listing |
| `content/v3/users?limit=1` | `sales-margin-impact/AGENT.md`, `production-priority-app/README.md` (docs, not code) | v3 existence/probe, documented-only |
| `identity/v1/users/search` | `workflow-env-vars.md` | documented-intent, shape "TBD — verify via DevTools" |
| `/v1/users` `POST`/`PUT`/`DELETE`, `/v1/groups` writes | **nothing** | there is **no identity write** in the repo — a write would be new |

If you're about to add the first identity **write**, that absence is the signal: there's no in-repo
precedent to copy, so verify the verb live and add a `[REPO]` row here.

## Companion skills

- [`domo-datasets.md`](domo-datasets.md) — **owns PDP row-policy CRUD** and the Platform-OAuth-vs-Product-
  dev-token host split this skill's "three worlds" extends. Go there for the policy filter/operator body and
  column masking; come here for how a policy references `users[]`/`groups[]`.
- [`domo-code-engine.md`](domo-code-engine.md) — the tokenless `send_request`/`sendRequest` mechanic that
  the in-repo `content/v2/users` reads ride on (invoking user's context).
- [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md) — the hosted **MCP `user_admin_toolkit`** if you want
  agent-side user read/manage tools instead of raw REST.
- [`domo-appstudio.md`](domo-appstudio.md) — **Publication Groups** (dashboard RLS that supersedes PDP).
- [`domo-everywhere.md`](domo-everywhere.md) — **Publish subscriber groups** (cross-instance replication
  audiences), and the OAuth `client_credentials` mint pattern this skill's World 1 shares.
- [`domo-sandbox.md`](domo-sandbox.md) — the Governance **Sandbox** content-promotion feature carries its
  own grant vocabulary (Administer Sandbox / Manage Repositories / Manage Repository Promotion) plus per-repo
  Co-Owner/Can-Edit/Can-Commit/Can-Promote levels. This skill owns the grant *mechanism*; that skill owns how
  those specific Sandbox grants gate commit/promote/ownership. `[KB]`
