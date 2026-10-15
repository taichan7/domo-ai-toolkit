# Domo Everywhere (external Embed + Publish) API Skill

Use this when a task **surfaces Domo content outside its own instance** — either **Embed** (render a
dashboard / card / App Studio app inside a foreign web page via an iframe, optionally with a
server-minted embed token) or **Publish** (replicate content from a publisher instance to subscriber
instances). It covers the **one small documented island** — the OAuth embed-token flow (two `embed/auth`
endpoints on the docs portal) — and the **large `[KB]`/`[INFER]` sea** around it: public-vs-private embed
behavior, per-viewer security (PDP), App Studio external embed, and Publish jobs — none of which has a
documented mutating API. Its whole reason to exist is to stop you from tagging that sea `[DOC]`, because
the governance mistakes here (leaking data through a public embed, putting `client_secret` in front-end
code) are high-blast-radius.

**The word "embed" means three unrelated things — keep them apart from line one:**

- **Domo Everywhere Embed** *(this skill)* — content in an **external** page on a **foreign origin**, via
  `public.domo.com` (public, tokenless) or a **server-minted embed token** (private). Auth world =
  `api.domo.com` OAuth `client_credentials`.
- **In-app embedding** — a card placed in an **App Studio** view, or a Pro Code app iframing a card, on
  the **instance host** while the viewer is a logged-in Domo user (the `ryuu.js`/`domo.js` postMessage
  bridge, a Domo session, **no** embed token). That's [`domo-appstudio.md`](domo-appstudio.md) /
  [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md), not this skill.
- **`domo publish` (the CLI) / the "Domo Publish" GitHub Action** — deploys a **Pro Code bundle to one
  instance**. Nothing to do with Domo Everywhere Publish jobs.

Scope boundaries — use the neighbor skill instead when:

- the content lives **inside your own instance** for a logged-in Domo user (App Studio view, Pro Code
  card iframe) → [`domo-appstudio.md`](domo-appstudio.md) /
  [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md). Those skills already name the
  "Domo Everywhere embed exception"; **this skill is the concrete version** of that pointer;
- it's the **Pro Code bundle** you want to embed (manifest, `app.js`, aliases) →
  [`domo-procode-app.md`](domo-procode-app.md);
- it's **PDP row-policy authoring on a DataSet** (independent of embed) →
  [`domo-datasets.md`](domo-datasets.md);
- it's **Code Engine** auth/packaging for the token-minting server → [`domo-code-engine.md`](domo-code-engine.md).

There is **no repo toolkit, provisioner, or reference doc** for Domo Everywhere in the original workspace today (the
only prior mention is a ~30-line paragraph in [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md)
lines 147-179). That absence is exactly why over-claiming is the risk: there is nothing in-repo to
re-verify a body against, so every non-`[DOC]` line below must be re-checked live.

## Evidence tiers

Every load-bearing line carries a tier. Anything `[REPO]`, `[KB]`, or `[INFER]` must be re-verified live
against the target instance and the current docs before you depend on it — Domo Everywhere's behavior is
instance-config- and version-dependent, and most of it is described in the KB/help center, not the API
reference.

```
[DOC]   Official Domo docs — the docs portal (domo.com/docs/portal), incl. the
        embed code-examples page and the two embed/auth API reference pages, or
        the developer API reference / OpenAPI.
[KB]    Domo Knowledge Base / support help center. Product behavior, modes, limits,
        admin UI facts. Much of Domo Everywhere lives ONLY here, not in [DOC].
[INFER] Reasoned from the documented model or community sources, or inferred from the
        ABSENCE of a documented API — plausible, not first-party. Verify live.
[REPO]  Verified only against this repo's working usage on a live instance — NOT in
        public docs. (Domo Everywhere has NO repo usage yet, so this tier is unused
        below; it is listed only for consistency with the sibling skills.)
```


## The headline: two documented embed-token endpoints in a large [KB]/[INFER] sea

**The correction that anchors this whole skill:** the Domo Everywhere **OpenAPI / developer reference
exposes exactly two mutating endpoints** — `POST /v1/stories/embed/auth` (dashboard) and
`POST /v1/cards/embed/auth` (card) — plus the shared OAuth `GET /oauth/token` that feeds them. That is
the entire documented API surface. So:

- **Minting a private embed token is `[DOC]`.** The OAuth `client_credentials` grant, the two
  `embed/auth` endpoints, the authorization body shape (`{sessionLength, authorizations:[{token,
  permissions, filters}]}`), and the programmatic-filter field shape (`{column, operator, values}`) are
  documented.
- **Everything else is `[KB]` or `[INFER]`.** Public-vs-private mode behavior, per-object enablement, the
  Authorized-Domains allowlist, the private-embed sub-types (User-Based SSO / Server-Based programmatic /
  Platform), App Studio external embed, and **all of Publish** (jobs, subscribers, publication groups)
  are described in the KB/help center or inferred — **none has a documented mutating API.** Do not let the
  existence of an embed-token API tempt you into tagging any of that `[DOC]`.

**Three "publish" meanings — never conflate them** `[DOC]`/`[KB]`/`[INFER]`:

| Term | What it is | Has a public API? |
|---|---|---|
| **`domo publish`** (CLI) / "Domo Publish" GitHub Action | Deploy **one Pro Code app** to **one instance** via a PAT | Yes (CLI) — unrelated to Everywhere |
| **Domo Everywhere Publications / Publish Jobs** | Replicate content **publisher instance → subscriber instances** | **No documented API** `[INFER]` |
| **Publication Groups** | **In-instance** row-level view filtering (RLS/PDP grouping) for internal users | Separate feature; not replication |

## Hosts and auth — three hosts, and the name-collision traps

Private embed touches **three different hosts** with **three different roles**. Conflating the token-mint
host with the render host is the most common mistake `[DOC]`:

| Host | Role | Auth |
|---|---|---|
| `https://api.domo.com/oauth/token` | **Mint** an OAuth access token (`client_credentials`) | HTTP **Basic** — `base64(client_id:client_secret)` `[DOC]` |
| `https://api.domo.com/v1/{stories\|cards}/embed/auth` | **Mint** the per-render **embed token** (the `authentication` JWT) | **Bearer** `<access_token>` `[DOC]` |
| `https://public.domo.com/embed/pages/{embedId}` | **Render** host — the iframe target; private variant receives the embed token via a self-submitting HTML **form POST** | the embed token (JWT), server-injected `[DOC]` for pages |

- **`api.domo.com` only mints; it never renders.** The private embed is *rendered* on `public.domo.com`.
  Pointing the iframe at `api.domo.com`, or expecting the mint call to return HTML, is the classic error.
  `[DOC]`
- **Do NOT mint an embed token with a developer token or SID on the instance host.** External embed-token
  minting is **OAuth `client_credentials` on `api.domo.com`** with a developer.domo.com API **client**
  (`client_id`/`client_secret`). Developer-token / SID auth on `{instance}.domo.com` is the *in-app*
  world (App Studio / DataSet APIs) — a different host and a different auth world. `[DOC]`/`[KB]`
- **`api.domo.com` is not guaranteed universal across regions.** Regional deployments may use a different
  API host — read it from your client's region, don't hard-code. `[INFER]`
- **Public embed uses none of this.** A public embed is a **plain tokenless `<iframe>`** to a
  `public.domo.com` URL — no OAuth, no token, no `embed/auth` call. The whole token flow above is
  **private-embed-only.** `[KB]`

## Documented surface — the embed-token flow (2 endpoints) `[DOC]`

This is the **complete documented mutating surface**. Two steps, server-side only. Live reference:
`domo.com/docs/portal/embed/embed-in-sites-and-apps/code-examples` (the developer.domo.com code URLs
often 405/redirect — cite the docs-portal page).

> **Spec provenance (verified 2026-09-06, rank-61 spec-body cross-check).** The embed-token surface is now a
> live-fetchable OpenAPI body: `www.domo.com/docs/openapi/platform/embed.yaml` — `openapi: 3.1.0`,
> `info.title: "Embed Token API"` (version `1.0`), a single server `https://api.domo.com`, and **exactly two
> POST-only paths** (`/v1/cards/embed/auth`, `/v1/stories/embed/auth`) under one global HTTP-bearer scheme.
> This confirms the two-endpoint claim above **against the spec body itself** (not just the code-examples
> page) and re-bases provenance to the new docs host (fetch with a browser-UA `curl`; a plain no-UA fetch on
> `*.domo.com` is UA-gated → 301/405). **No `/oauth/token` and no GET/DELETE/list/revoke path exists in this
> spec** — it is token-*mint* only; the OAuth step lives in the separate "API Authentication" spec. Two body
> quirks: `components.schemas` is empty (`{}`) — every shape is inline, so there is **no schema `enum:`
> anywhere** (see the operator note under Programmatic filters); and **both operations share the same
> `operationId` (`post-v1-stories-embed-auth`)** — the cards op is mislabelled, so don't key tooling on it.
> `[DOC]`

**Step 1 — mint an OAuth access token** `[DOC]`

```
GET  https://api.domo.com/oauth/token?grant_type=client_credentials&scope=<space-separated scopes>
Authorization: Basic base64(client_id:client_secret)
```

- POST is also accepted; the official curl example uses **GET**. `[DOC]`
- Response carries `access_token` and **`expires_in` ≈ 3599s (~1h)** — this is **issuer-provided**; read
  it from the response and refresh, do **not** hard-code a fixed lifetime. `[DOC]`
- **The scope string is example-specific, not a fixed contract.** Samples show `data user` and
  `data audit user dashboard`; Domo does not rigorously document the *minimum* scopes required to mint an
  embed token. Treat any specific scope set as illustrative and verify for your client. `[INFER]`

**Step 2 — mint the embed token** `[DOC]`

```
POST https://api.domo.com/v1/stories/embed/auth      # dashboard  (EMBED_TYPE 'dashboard')
POST https://api.domo.com/v1/cards/embed/auth        # card       (EMBED_TYPE 'card')
Authorization: Bearer <access_token>
{
  "sessionLength": <minutes>,
  "authorizations": [{
    "token": "<embedId>",                 # the 5-char embed ID from the dialog — NOT the access token
    "permissions": ["READ","FILTER","EXPORT"],
    "filters": [{"column":"Region","operator":"IN","values":["West"]}]
  }]
}
```

- **Use the right endpoint for the object type:** dashboards/stories → `/v1/stories/embed/auth`; cards →
  `/v1/cards/embed/auth`. Using the wrong one for the object type fails. `[DOC]`
- **`authorizations[].token` is the per-object embed ID** (the ~5-char value from the embed dialog's
  "private" option, e.g. `bc36f`), **not** the OAuth access token (that goes only in the `Bearer`
  header). Using the object id from the instance URL will fail. The "5-character" length is illustrative,
  not a versioned contract. `[DOC]`/`[INFER]`
- **`sessionLength` is in MINUTES**, caller-set (examples use `1440` = 24h). The **default 8h and the max
  are instance-capped** by the customer's session idle-length setting — so the effective ceiling is
  instance-dependent, not a portable constant. `[DOC]`/`[KB]`
- **Two independent clocks:** the OAuth `access_token` `expires_in` (~3600s) vs the embed
  `sessionLength` (≤ the instance cap). Don't present either as the other, and don't state a fixed embed
  TTL. `[DOC]`
- The response field is **`authentication`** (the embed JWT). It's delivered to the render iframe via a
  self-submitting HTML **form field** (documented as `embedToken` for pages) — it is **not** a JSON API
  the browser calls. `[DOC]`
- **Proxy user must have access.** The API client's owner (the proxy service account) must have view
  access to the content, or the mint call fails / returns nothing renderable. `[KB]`

## Programmatic filters, PDP, and the governance crux

This is the security-critical part. Two questions decide everything: **is the embed public or private?**
and **does Domo know who the viewer is?**

**Filter body mechanics** `[DOC]` (the field names that silently fail if you copy the wrong ones):

- The embed-token filter uses the key **`operator`**. The spec's `operator` field **description** lists
  **eight** documented operators verbatim: `IN`, `NOT_IN`, `EQUALS`, `NOT_EQUALS`, `GREATER_THAN`,
  `GREAT_THAN_EQUALS_TO`, `LESS_THAN`, `LESS_THAN_EQUALS_TO`. Keep the literal typo-looking
  **`GREAT_THAN_EQUALS_TO`** (single `E` — that IS Domo's spelling; do **not** "correct" it). **This list is
  prose inside a `description` string, not a schema `enum`** (the field is `type: string` and
  `components.schemas` is `{}`), so treat it as the *documented* set, not a machine-enforced closed enum —
  Domo may extend/version it; verify any operator you depend on. `[DOC]`
- The **client-side Pfilter URL params and the JS API use `operand`, not `operator`.** Copying a
  client-side `operand` example into a server-minted embed-token body **fails silently.** `operator`
  (server, in the token) ≠ `operand` (client, in the URL/JS). **The spec body corroborates the trap
  directly:** the request schema property is `operator` (required, alongside `column`/`values`), yet the
  endpoint's own "Sample Filter Objects" markdown keys two of its three samples on **`operand`** — and
  **`BETWEEN` appears only in an `operand` sample, never in the server `operator` list above**. So `BETWEEN`
  is a *client operand*, not a documented server operator; do not place it in a minted-token
  `filters[].operator`. `[DOC]`
- **Filter `values` are always a quoted string array** — the spec's `values` field description states,
  verbatim: *"The values must be in quotes even if it is a numeric type and it must be in a list even if
  there is only one."* A single numeric filter is therefore `"values":["4"]`, never `4` or `[4]`. `[DOC]`
- Large `IN` lists hit a **~8KB JWT size cap** on the embed token — big per-viewer filter sets can blow
  it. `[DOC]`/`[KB]`
- Singular `datasourceId` vs plural `sqlFilters.datasourceIds` appear in different call shapes; don't
  assume one spelling. `[DOC]`

**Who can be secured, and how — the governance crux** `[DOC]`/`[KB]`:

| Embed mode | Viewer identity | Per-viewer security available |
|---|---|---|
| **Public** | none (anonymous) | **NONE.** No PDP, no *secure* filter. Only client-side Pfilters/JS API the viewer can read & change. `[DOC]`/`[KB]` |
| **Private — Server-Based** (programmatic) | not a Domo user | **Server-computed programmatic filters** in the embed token. PDP does **not** apply (no Domo identity). `[DOC]`/`[KB]` |
| **Private — User-Based** (SSO / provisioned Domo user) | a real Domo user | **PDP applies** (Domo knows the viewer). `[KB]` |

- **PDP and programmatic filters are NOT interchangeable per viewer.** PDP works only when Domo knows the
  viewer (User-Based SSO / provisioned user). Server-Based viewers are not Domo users, so they get
  server-computed programmatic filters instead. Don't claim "PDP on any private embed." `[KB]`
- **Public embed can NEVER be secured or personalized per viewer.** It is unauthenticated; any "row-level
  security on a public embed" claim is wrong. Client-side Pfilters are cosmetic, not security. `[DOC]`/`[KB]`
- **⚠ The single most dangerous governance trap — treat as a RISK, not a documented guarantee:** it is
  *commonly stated* that a **public dashboard** embed makes **all columns of all underlying page datasets
  filterable** (including hidden/sensitive columns), whereas a **public card** embed exposes only what the
  card shows. The dashboard half is **`[INFER]` / mis-attributed** (the cited article states the opposite
  for cards, and the dashboard claim is unverified). **Operating rule regardless of which is true:** never
  publicly embed content whose underlying datasets contain columns you would not publish to the world —
  assume a public embed can be probed beyond what is visually shown until you verify otherwise. `[INFER]`
- **The JWT Identity Broker (SSO) path is a different auth method** — `IDP_URL` + `JWT_SECRET`, configured
  under Admin > Domo Everywhere > Embed (Routing/Mapping, `KEY_ATTRIBUTE`). Do not conflate it with the
  OAuth `client_credentials` programmatic-filter flow: different secrets, different endpoints, different
  purpose (SSO / edit experience vs server-side filtering). `[KB]`
- **Cookie-based SSO+PDP is the path Domo itself frames as deprecated** (third-party cookie blocking);
  programmatic filters are the pushed replacement. Behavior around cookies/SSO is in flux — verify current
  guidance. `[KB]`
- **Programmatic filters do not work for every embedded app.** The **Inline Dataset Editor** and **Form
  Viewer** apps rely on their own OAuth and cannot take programmatic filters. `[DOC]`

## Public vs private embed — modes and enablement `[KB]`

Nearly all of this is `[KB]` — it traces to KB article **360043437993** (which redirects into the
domo-support Salesforce help center) and the admin UI, **not** the API reference.

- **Enablement is per-object, through the UI.** Each dashboard/card/app is individually enabled for
  embedding from its share/embed dialog, which yields the ~5-char **embed ID**. There is **no documented
  bulk/programmatic enablement** — "no bulk enablement" is an inference from absence, not a documented
  prohibition; do not assert it as fact either way. `[KB]`/`[INFER]`
- **Public embed = world-readable, tokenless.** Anyone with the URL sees it; it carries no security (see
  the governance section). The admin toggle that governs it is labeled **"Publicly embed content"**. `[KB]`
- **Private embed has sub-types:** **User-Based** (SSO / provisioned Domo user, PDP applies),
  **Server-Based** (programmatic, token-minting server, viewer is not a Domo user), and **Platform**
  (a distinct licensing/billing model beyond mirror-user and server-side impressions). Treat the
  sub-type taxonomy and any "Beta" labeling as `[KB]`, not a stable contract — the earlier
  "Platform-Based Beta" label was unverified and is dropped here. `[KB]`/`[INFER]`
- **Authorized Domains allowlist.** Private embeds can be restricted to an allowlist of parent domains
  (admin-configured); the exact admin route is a UI/instance path and may change by version. `[KB]`
- **Instance policy can remove public embed entirely.** It is **disabled on HIPAA instances** and can be
  turned off company-wide by an admin — so "public embed is available" is never a portable guarantee.
  `[KB]`
- **AppDB / Domo Bricks custom apps are blocked in public embed contexts.** A data-backed Brick needs a
  **private** embed. `[KB]`
- **Billing shifts under the server-based model** to impression / card-load metering — a commercial
  constraint to flag, not a free capability. `[KB]`

## Embedding an App Studio app externally

Embedding an **App Studio app** (a DataApp, multi-view) externally is described in KB article
**000005295**, and it behaves differently from a single dashboard/card:

- **The mechanism is a UI flow, not a documented endpoint.** You embed via the app's **Distribute >
  Embed Domo App** modal with a **Private / Public** toggle, which yields an embed id. There is **no
  App-Studio-specific embed-token endpoint in the docs.** `[KB]`
- **Whether an App Studio app routes through `/v1/stories/embed/auth` for a private token is `[INFER]`.**
  It's the plausible path (App Studio views are story/dashboard-like), but no doc says so — **verify live
  on the target instance** before relying on it. Do not present a `page` EMBED_TYPE as documented: the
  canonical docs and examples specify only **`dashboard`** or **`card`**; `page` appears in a single
  example-README variant and is uncorroborated. `[INFER]`
- **Public-embed feature gaps in App Studio apps** `[KB]`: some widgets/fields don't work in a public
  embed — **Button pop-ups, the Workflows widget, the Queues widget**, and the **Account / Person /
  Groups / DataSet** field types. If the app uses those, it needs a private embed (or won't fully
  function publicly).
- **Interactivity is gated per-embed.** Filtering / export / maximize / drill are controlled by
  per-embed display-option toggles, and public embeds are commonly locked down. Don't assume an embedded
  app is interactive by default. `[KB]`

## Publish — cross-instance content replication (publisher → subscriber)

**Publish** replicates content from a **publisher** instance to one or more **subscriber** instances
(distinct orgs). This is the *other* half of Domo Everywhere, and it is almost entirely `[KB]`/`[INFER]`
— **the Domo Everywhere OpenAPI exposes only the two embed-token endpoints; it has no publish surface.**

- **There is no documented public API for creating, reading, running, or managing Publish jobs.** The
  admin UI calls an internal backend; that endpoint is **not** a stable, supported, portable contract.
  "No publish API" is an **inference from absence** — treat any internal endpoint you discover as
  undocumented and version-fragile, never as `[DOC]`. `[INFER]`
- **Programmatic subscriber-instance creation is "not currently available"** — this is Domo's own
  documented wording. Don't design a flow that provisions subscriber orgs via API. `[KB]`
- **A publish job's refresh is a manual/targeted UI action** — there's no documented "trigger publish
  run" API, and Domo explicitly warns **not to modify source dashboards mid-refresh**. `[KB]`
- **Operational constraints** `[KB]`: **Azure-hosted instances are excluded** from Publish; pages must be
  **shared with the user configuring the job**; subscribers **accept publications individually** by
  default; and **embedded / read-only publications render under the PUBLISHER owner's PDP**, not the
  subscriber's — a governance subtlety that decides what a subscriber's viewers can see.
- **Publication Groups ≠ Publications.** "Publication Groups" is **in-instance row-level view filtering
  (RLS)** for internal users — a different feature that shares the word. Don't fold it into cross-instance
  replication. `[KB]`
- **`domo publish` (CLI) creates none of this.** It deploys a Pro Code app to one instance; it makes no
  publication and no subscriber content. `[DOC]`
- **Publish ≠ Domo Sandbox.** Publish pushes **DATA / DataSets outward to EXTERNAL subscribers**
  (syndication across orgs). The Governance **Sandbox** feature moves **CONTENT definitions, not data**,
  **dev→prod (or same-instance), internally**, via Repositories/Commit/Promote. Same "promote content
  across instances" instinct, opposite payload and audience → [`domo-sandbox.md`](domo-sandbox.md). `[KB]`

## Do NOT claim as documented fact (hedge list)

The verification's whole point was to keep these from being written as `[DOC]`. Do **not** state any of
these as a documented, portable Domo contract:

1. **That anything beyond the two `embed/auth` endpoints (+ `/oauth/token`) is a documented API.** No
   documented API enables embedding, creates publish jobs, manages subscribers, or creates subscriber
   instances. All of that is `[KB]` or `[INFER]`.
2. **That `api.domo.com` renders the embed.** It only *mints* tokens; the private embed renders on
   **`public.domo.com`**. And the private **card** render path (`public.domo.com/cards/{embedId}`) is
   `[INFER]` — only the **pages** path `public.domo.com/embed/pages/{embedId}` is clearly published.
3. **That a developer token or SID can mint an external embed token.** External minting is **OAuth
   `client_credentials` on `api.domo.com`**; dev-token/SID is the in-app instance-host world.
4. **That the OAuth scope string is a fixed required set.** `data user` / `data audit user dashboard` are
   examples; the strictly-required scopes are not rigorously documented. `[INFER]`
5. **That the embed token has a fixed expiry.** The ~3599s value is the OAuth **access** token's
   `expires_in` (issuer-provided); the **embed** token TTL is caller-set via `sessionLength` (minutes),
   itself capped by the instance idle-length setting. Two clocks; neither is an immutable constant.
6. **That `authorizations[].token` is the access token.** It is the ~5-char **embed ID** from the dialog;
   the access token goes only in the `Bearer` header. The "5 characters" is illustrative, not versioned.
7. **That the filter operator enum is universal / that you should fix the typo.** The spec documents a
   specific **eight**-operator list (enumerated under Programmatic filters) but as *prose in a `description`*,
   not a schema `enum` — so it is the documented set, **not** a guaranteed-exhaustive/universal contract. The
   token body uses `operator` (with the literal `GREAT_THAN_EQUALS_TO`); client Pfilters/JS use `operand`, and
   `BETWEEN` is an `operand`-only sample value. Copying a client `operand` example — or "correcting" the typo
   — fails silently.
8. **That public embed can be secured or personalized per viewer.** Public = unauthenticated: no PDP, no
   secure filter, only viewer-readable client-side Pfilters.
9. **That PDP applies to any private embed.** PDP needs a Domo-known viewer (User-Based SSO / provisioned
   user). Server-Based programmatic viewers get server-computed filters, not PDP.
10. **That a public dashboard embed's exposure is fully known.** "All columns of all page datasets are
    filterable on a public dashboard embed" is `[INFER]`/mis-attributed. Operate as if a public embed can
    be probed beyond what's shown; never publicly embed sensitive-column datasets.
11. **That the JWT Identity Broker (`IDP_URL`/`JWT_SECRET`, SSO) is the same as the OAuth
    programmatic-filter flow.** Different auth method, secrets, endpoints, purpose.
12. **That an App Studio app has a documented external-embed endpoint, or routes through
    `/v1/stories/embed/auth`.** Both are `[INFER]`; the mechanism observed is a UI Distribute modal.
    `EMBED_TYPE` is documented only as `dashboard`/`card`, not `page`.
13. **That the `client_secret` or a minted embed token can be used from front-end code.** CORS blocks
    client-side auth; both are **server-side only**. A "front-end-only private embed" is impossible.
14. **That the render-to-image (`.../render` PNG) endpoint is an interactive embed.** It returns a static
    image and needs a developer token — not a Domo Everywhere embed.
15. **That "Publish" and `domo publish` / Publication Groups are the same surface.** Three different
    things (cross-instance replication vs Pro Code deploy vs in-instance RLS).
16. **That subscriber creation or a publish refresh can be triggered programmatically.** Subscriber
    creation is documented as "not currently available"; refresh is a manual UI action.

## Safety / hygiene

- **`client_secret` and embed tokens are server-side secrets — never in front-end code, commits, or
  handoffs.** Mint both on a server (Code Engine, or a backend the customer controls); the browser
  receives only the rendered iframe / self-submitting form. CORS blocks client-side minting anyway, so a
  "self-contained front-end private embed" is both impossible and a leak.
- **Never log the `/oauth/token` request URL.** It carries the scope in the query string and the
  `client_id:client_secret` in the Basic-auth header — logging either leaks the secret. Log the *fact* of
  a token mint, not the URL or headers.
- **Public embed is a data-exposure decision, not a UI convenience.** Before enabling one, confirm every
  column of every underlying dataset is publishable to anonymous viewers — a public embed carries no
  PDP and (for dashboards) may expose more than is visually shown. When in doubt, use a **private** embed.
- **Respect instance policy.** Public embed may be disabled (HIPAA, or admin-off company-wide); don't
  design a deliverable that assumes it's on without checking.
- **This is an external-publishing surface** — content sent to `public.domo.com` or a subscriber instance
  is outward-facing. Treat enabling a public embed or a publish job as a hard-to-reverse, outward-facing
  action: confirm scope with the human before flipping content public, even though Domo *deploys* are
  otherwise pre-authorized (a `domo publish` of a Pro Code app is not the same risk class).
- **Never commit** OAuth `client_secret`/`client_id`, minted embed tokens/JWTs, captured `embed/auth`
  request or response bodies, `IDP_URL`/`JWT_SECRET`, or subscriber/publisher instance identifiers.
  Summarize; don't paste raw captures.

## Repo precedent

Domo Everywhere has **no working usage in this repo yet** — no provisioner, no toolkit script, no clone
reference. The only in-repo mention is conceptual: `[REPO]`

| Where | What it says |
|---|---|
| [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md) (§ "Domo Everywhere embed", ~lines 147-179) | The narrow card-in-your-own-DOM embed: public embed = tokenless world-readable; private embed = server mints a short-lived token via OAuth `client_id`/`client_secret` (secret never in front-end); AppDB-in-Bricks blocked in public-embed contexts. This skill is the endpoint-level expansion of that paragraph. |

Because there is nothing in-repo to re-verify a body against, **every non-`[DOC]` line above must be
re-checked live** (current docs + the target instance's admin settings) before you depend on it. When you
*do* build the first working embed-token minter in this repo (most likely a Code Engine function), add a
`[REPO]` row here and a reference doc under `../docs/reference/`, the way `app-studio-clone.md` backs
[`domo-appstudio.md`](domo-appstudio.md).

Companion skills: [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md) (the in-DOM card
embed this expands), [`domo-appstudio.md`](domo-appstudio.md) (in-app App Studio embedding + the
`domo publish`/version-binding world), [`domo-procode-app.md`](domo-procode-app.md) (the Pro Code bundle
you embed), [`domo-datasets.md`](domo-datasets.md) (PDP row-policies + the Platform-OAuth-`api.domo.com`
vs Product-instance-host auth split), [`domo-code-engine.md`](domo-code-engine.md) (where a server-side
token minter would live).
