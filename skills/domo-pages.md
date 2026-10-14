# Domo Pages

Use this when you are creating, listing, reading, updating, deleting, or sharing a **classic Domo Page** (a.k.a. a **Dashboard** — the tree of tabbed pages that holds standard cards, with `visibility`, `owners`, and card collections) via the REST API — **and, just as often, when you need to work out which of the six-or-seven things called a "page" you are actually looking at.** A classic Page is the dashboard object addressed at `api.domo.com/v1/pages/{id}`; it is *not* an App Studio view-page, *not* a DataApp page, *not* a Pro Code `fullpage` app, *not* a `.md` file, *not* an embed "page". The name collides more than almost any other object in Domo, so **disambiguation is this skill's first job** — read the naming-trap table below before you touch an endpoint.

The classic Pages surface is a **moderate, well-charted documented island** — smaller than identity-access, far better charted than alerts — with a few un-sounded shallows (OAuth scope, some sub-schema completeness, one intra-spec id-type inconsistency, and the create-subpage-vs-view object identity). The single most valuable thing this file does is keep you from calling the classic Page API when you meant the App Studio view-page API that the repo *actually* uses — the two share the literal token `pages` in their paths but live on different hosts, take different auth, and expect different field names, and mixing them **fails silently**.

## What this skill owns (and what it defers)

**Owns:** the **classic Page / Dashboard** object and its collections, on two documented surfaces — the Platform-OAuth `api.domo.com/v1/pages` world (create/list/get/update/delete a page; list/create/update/delete a page *collection*) and the product/instance `{instance}.domo.com/api/content/v1` world's three page-tree write ops (create-subpage, bulk-move, revoke-page-access). Plus the job of disambiguating every other "page".

**Defers:**

| Face / concern | Owner |
|---|---|
| App Studio **view-page** single-resource ops — `/api/content/v1/pages/{viewId}` rename, `/{viewId}/cards`, v4 `/layouts`, writelock, TABS-append, `isDynamic`/PAGE_BREAK, `interaction:DISABLED`, and all `/api/content/v1/dataapps/*` — **this is what the repo actually calls** | `domo-appstudio.md` |
| Standard cards referenced by `cardIds[]` (chart-type families, card CRUD, clone-and-retarget) | `domo-cards.md` |
| Row-level security (PDP) scoping what a page's cards *show* — there is no documented page-level PDP | `domo-datasets.md` |
| Identity behind `owners[]` / `visibility.userIds`/`groupIds` and the person in `/share/page/{pageId}/user/{personId}` | `domo-identity-access.md` |
| Surfacing a page **outside** its instance (embed / publish "page") | `domo-everywhere.md` |
| Pro Code manifest `fullpage` / "page" as an app render mode | `domo-procode-app.md` |
| A Variable/filter *control* bound to a page | `domo-variables-filters.md`, `domo-appstudio.md` |

## Evidence tiers

```
[DOC]   developer.domo.com API ref / docs-portal OpenAPI / machine-readable OpenAPI YAML / first-party SDK ref.
        A domo.com/docs/s/article/<12-digit-id> page is a Salesforce KB → [KB], NOT [DOC].
[KB]    Domo Knowledge Base / documented product behavior.
[REPO]  Verified only against this repo's working code — an instance-internal convenience, NOT a public contract.
[INFER] Reasoned from the documented model / community / marketing / inference-from-absence.
        A fetch FAILURE (405 / JS-gated / login-wall) is MISSING evidence, NOT proof of absence.
```

On disagreement, take the more conservative tier. The single guarded failure mode is **over-claiming** — dressing a repo convenience or a reasoned guess as a documented contract.

**Verification provenance.** The `[DOC]` claims here were verified by a 16-agent doc-cross-check + adversarial-refute workflow (`wf_a319c652-02b`: 6 spec-reading clusters → refute the top-8 over-claim-risk claims, each default-refuted-if-uncertain → completeness critic + island verdict → synthesizer). All 8 refute verdicts returned **CONFIRMED at [DOC]**. The critic flagged one load-bearing provenance gap (whether the OpenAPI specs are genuinely fetchable or only summarized); I resolved it by fetching three specs directly and independently — `openapi/platform/page.yaml`, the `domo.com/docs/llms.txt` catalog, and `openapi/product/pages-api.yaml` — confirming the endpoint sets, the create-vs-update body split, `children`-in-list-only, `bearerAuth` with no `oauth2` flows block, the `page_id` string/integer intra-spec inconsistency, the Page Collection schema, that **no `/v1/dashboards` spec exists in the catalog**, and World B's exact three ops with **no documented GET route**. Sub-schema completeness and **most** behavioral rules remain `[INFER]` — the specs pin field *names* and *types*, not every constraint — but a handful of behavioral rules *are* documented `[DOC]` (the partial/merge PUT, `collectionIds` reorder-only, the two PUT access side-effects, and the base `locked` restrict-non-owner-edits semantic).

## The naming-trap table — read this first

Conflating these is the #1 hazard. When someone says "page", pin the sense before you pick an API.

| # | What they might mean | Identity / handle | Documented address | Owner |
|---|---|---|---|---|
| a | **Classic Page == Dashboard** — a tabbed dashboard of standard cards | integer `id` / `pageId` | `api.domo.com/v1/pages` (Platform) + `{instance}/api/content/v1/pages` writes (Product) | **this skill** |
| b | **App Studio view-page** — a page *inside* a DataApp | `{viewId}` | `{instance}/api/content/v1/pages/{viewId}`, `/{viewId}/cards`, v4 `/layouts` | `domo-appstudio.md` |
| c | **DataApp** — the App Studio app that *contains* view-pages | `dataAppId` | `{instance}/api/content/v1/dataapps/{appId}/views` | `domo-appstudio.md` |
| d | **Pro Code full-page app** — a Pro Code bundle rendered as a page | manifest `fullpage:true` | (manifest key, not a REST route) | `domo-procode-app.md` |
| e | **Markdown `.md` page** — a doc/runbook file | file path | (no API; a repo/file artifact) | (no owner) |
| f | **Embed / "publish" page** — Domo content rendered *outside* the instance | embed token / story id | `api.domo.com/v1/{stories,cards}/embed/auth` → `public.domo.com` | `domo-everywhere.md` |
| g | **Browser deep-link** `…/page/{id}` | integer `id` | URL form of sense **(a)** — the classic Page | **this skill** |

The trap that fails **silently**: senses (a) and (b) both put the literal token `pages` in the path, but (a) is `api.domo.com/v1/pages` (Platform OAuth) while (b) is `{instance}/api/content/v1/pages/{viewId}` (instance dev-token). They differ in host, auth, **and field names** — a create against (a) wants `name`/`parentId`, (b)'s world wants `title`/`parentPageId`. **The repo only ever calls sense (b).** If you find yourself writing `api.domo.com/v1/pages` because you saw `content/v1/pages` in a provisioning script, stop — you have crossed worlds.

## The headline — a documented island across two worlds `[DOC]`

The classic Page object is documented in **two OpenAPI specs that describe two different worlds** of the same object:

- **World A — Platform OAuth**, host `https://api.domo.com`, base `/v1/pages`, auth `bearerAuth` (HTTP bearer). This is the mirror pair `openapi/platform/page.yaml` ≡ portal `Page-API.yaml` (they agree exactly). Nine documented ops: full CRUD on a page + full CRUD on a page *collection*.
- **World B — Product / instance**, host `https://{instance}.domo.com`, base `/api/content/v1`, auth `DomoDeveloperToken` (apiKey header `X-DOMO-Developer-Token`). This is `openapi/product/pages-api.yaml` — a **disjoint, complementary** surface: three page-tree write ops (create-subpage, bulk-move, revoke-access) and **no documented GET/read/list route**.

Both specs are listed in `domo.com/docs/llms.txt`. They are not the "same path, two hosts" trap from datasets/identity — the path **prefixes** differ (`/v1/pages` vs `/api/content/v1/pages`), so no literal path collides. The silent-failure trap here is **field-name divergence** (`name`/`parentId`/`id` in World A vs `title`/`parentPageId`/`pageId` in World B).

## World A — Platform, `api.domo.com/v1/pages` `[DOC]`

Auth: `bearerAuth` = an HTTP bearer token. The spec's security scheme is `type: http, scheme: bearer` with **no `oauth2` flows block** — the token is an OAuth2 `client_credentials` access token minted from a Domo developer client, but that acquisition is an out-of-band detail the spec does not describe. Do **not** name a required scope; the spec does not pin one.

| Op | Method + path | Body / query (documented) |
|---|---|---|
| **Create Page** | `POST /v1/pages` | `name`, `parentId`, `locked`, `cardIds[]`, `visibility{userIds[],groupIds[]}`. **No `owners`, no `collectionIds` at create.** |
| **List Pages** | `GET /v1/pages` | query `limit` (int, default 50, max 500), `offset`. Response array carries nested **`children[]`** (the subpage tree). |
| **Retrieve Page** | `GET /v1/pages/{page_id}` | `page_id` typed **string** here. Single-page schema has **no `children`**. |
| **Update Page** | `PUT /v1/pages/{page_id}` | body is a **superset** of create: adds `owners[]` and `collectionIds[]`. |
| **Delete Page** | `DELETE /v1/pages/{page_id}` | 204 on success. |
| **List Collections** | `GET /v1/pages/{page_id}/collections` | `page_id` typed **integer** here (intra-spec inconsistency — see hedge list). |
| **Create Collection** | `POST /v1/pages/{page_id}/collections` | `title`, `description`, `cardIds[]`. |
| **Update Collection** | `PUT /v1/pages/{page_id}/collections/{page_collection_id}` | collection body. |
| **Delete Collection** | `DELETE /v1/pages/{page_id}/collections/{page_collection_id}` | removes one collection. |

The `owners`/`collectionIds` split is real and load-bearing: you **create** a page without owners or collections, then **PUT** to set them — with one asymmetry `[DOC]`: `owners[]` is genuinely *set* by the PUT, but `collectionIds` on the PUT only **reorders** existing collections (order follows the IDs you send); collection **membership** (adding or removing a section) is done through the collections sub-resource (`POST`/`DELETE /v1/pages/{page_id}/collections`), never the page PUT. A page *collection* is a within-page grouping of cards (a "section"), a distinct sub-resource from the page itself.

**Two `PUT` access side-effects `[DOC]` — they widen access *upward*, silently.** Both are documented consequences of a World-A page `PUT`: (1) granting a user or group access to a page **also grants that user/group access to the parent page — if the page is a subpage**; (2) moving a page by changing its `parentId` **also grants everyone with access to the page access to the new parent page** (unconditional). Sharing or re-parenting a page therefore propagates access to its parent; account for it on a shared instance before you PUT.

## World B — Product / instance, `{instance}.domo.com/api/content/v1` `[DOC]` (single-source)

Auth: `DomoDeveloperToken` = apiKey header `X-DOMO-Developer-Token`. These three ops are documented **only** in `product/pages-api.yaml` (single-source [DOC] — corroborated by my direct fetch, but no second spec mirrors them). This world has **no documented GET/read/list route** for pages.

| Op | Method + path | Body / path (documented) |
|---|---|---|
| **Create Subpage** | `POST /api/content/v1/pages` | body: `parentPageId` (**required**), `title` (**required**), `hasLayout` (bool, default true). It is **always a subpage** — `parentPageId` is required, so this route cannot create a top-level page. |
| **Bulk Move Pages** | `PUT /api/content/v1/pages/bulk/move` | body: `pageIds[]` (**required**), `parentPageId` (**required**), `pagePermission` (**required**, enum whose only documented value is `ORIGINAL`). |
| **Revoke Page Access** | `DELETE /api/content/v1/share/page/{pageId}/user/{personId}` | path `pageId` (int) + `personId` (int). Note the prefix is `/share/`, not `/pages/`. |

`Pages_CreateSubpageResponse` documents these fields: `pageId`, `parentPageId`, `ownerId`, `owners`, `type`, `title`, `pageName`, `locked`, `mobileEnabled`, `sharedViewPage`, `metadata`, `virtualPage`, `hasLayout`.

## The Page object `[DOC]` (World A schema)

| Field | Type | Notes |
|---|---|---|
| `id` | integer | The page's identity in World A. (`page_id` path param is typed *string* on GET, *integer* on collections — see hedges.) |
| `parentId` | integer | Parent page; a top-level page has none. |
| `name` | string | Title. |
| `locked` | boolean | Restricts users **besides the page owner** from making updates to the page or its content; default `false`. `[DOC]` Deeper mechanics (exact owner-bypass scope, what counts as an "update", interaction with sharing) stay `[INFER]`. |
| `collectionIds` | array<int> | Set via **PUT only**, not at create — and **reorder-only** on PUT: the IDs you send set collection *order*, they do **not** add or remove collection membership (use the collections sub-resource for that). `[DOC]` |
| `cardIds` | array<int> | Cards placed directly on the page (outside any collection). |
| `visibility` | object | `{ userIds[], groupIds[] }` — who can see the page. |
| `owners` | array<obj> | `{ id, type, displayName }` — set via **PUT only**. |
| `children` | array | Nested subpages — appears in the **list** response only, **not** in single-page GET. |

**Page Collection object** `[DOC]`: `id` (int), `title` (string), `description` (string), `cardIds` (array<int>).

## The two worlds — don't cross them

|  | World A (Platform) | World B (Product) |
|---|---|---|
| Host | `https://api.domo.com` | `https://{instance}.domo.com` |
| Base | `/v1/pages` | `/api/content/v1` |
| Auth | `bearerAuth` (OAuth2 access token) | `X-DOMO-Developer-Token` |
| Reads | full CRUD + collections | **none documented** |
| Create field for title | `name` | `title` |
| Create field for parent | `parentId` | `parentPageId` |
| Identity field | `id` | `pageId` |

Same object, two documented control planes. Because the path prefixes differ, nothing collides *literally* — but the **field names** do the damage: send World B's `title`/`parentPageId` to World A's `POST /v1/pages` and the server ignores the unknown fields and creates a nameless, unparented page. The one true path collision to watch is that World B's `/api/content/v1/pages` prefix is **also** App Studio's view-page prefix (sense **b**, owned by `domo-appstudio.md`) — the same first three segments front two different resources.

## Boundaries & orphans

- **No `/v1/dashboards` spec.** "Dashboard" is the product name for a classic Page; there is **no separate Dashboards API** in the catalog. Do not assert one exists — and do not assert one *cannot* exist (inference-from-absence is `[INFER]`). Use `/v1/pages`.
- **App Studio view-pages are a different object.** Everything about a page *inside* a DataApp — `{viewId}` rename, `/{viewId}/cards`, v4 `/layouts`, DataApp `views` — belongs to `domo-appstudio.md`. That is the surface the repo actually drives.
- **Sharing vs visibility.** World A's `visibility{userIds,groupIds}` (who sees the page) and World B's `/share/page/{pageId}/user/{personId}` revoke are both here; the **identity** of those users/groups (resolving a person, PDP membership) is `domo-identity-access.md`.
- **PDP is dataset-level, not page-level.** Row policies that change what a page's cards *show* live in `domo-datasets.md`. There is no documented page-level PDP.

## Repo false friends `[REPO]`

**Repo precedent for the classic Page API is ZERO.** No `.py/.js/.mjs/.ts` calls `api.domo.com/v1/pages`; `create_page`/`createPage`/`/v1/dashboards`/`createDashboard` return no code hits. The string `api.domo.com/v1/pages` appears **only** in Markdown warnings (`domo-appstudio.md:67,290`). **Every classic Page op in this file therefore stays `[DOC]`, never `[REPO]`** — you have no working local example to lean on.

What the repo *does* call is the **App Studio view-page surface** (sense **b**, deferred to `domo-appstudio.md`), 38 code hits under `content/v1/pages/`:
- `GET {instance}/api/content/v1/pages/{viewId}/cards` — the provisioners in `asset-lifecycle-app`, `support-center`, `equipment-analytics`, `equipment-inventory`, `inventory-management`, `pl-summary`.
- `PUT …/pages/{viewId}` rename, `POST …/dataapps/{appId}/views`.
- A `DELETE api/content/v1/pages/{id}` exists only in a **CE test stub** (`asset-lifecycle-app/tests/test_code_engine.py:222`), not production code.
- The browser deep-link `'/page/' + encodedId` (`asset-lifecycle-app/pro-code/app.js:176`) is the **URL form of a classic Page** (sense **g**) — a link, not an API call.

Unrelated tokens that are **not** pages at all: `PAGE_BREAK`/`pageCount` (49 hits — App Studio layout markers, `domo-appstudio.md`), `collectionId` in non-page contexts, a `page_id` column in lineage/governance datasets.

## Do NOT claim as documented fact

1. **That `owners` or `collectionIds` can be set at create.** They appear only in the PUT (update) body, not the POST (create) body. Create the page, then PUT owners/collections.
2. **A required OAuth scope for World A.** The spec's `bearerAuth` is HTTP-bearer with no `oauth2` flows block; the scope is not pinned. Don't name one.
3. **The Page Collection sub-schema is complete.** `id/title/description/cardIds` are the confirmed `[DOC]` fields; treat "these are *all* the fields" as `[INFER]`.
4. **The `visibility` object is complete.** `userIds[]`/`groupIds[]` are documented; that there are no other keys is `[INFER]`.
5. **These behavioral rules remain `[INFER]`** — not stated in the spec: cards auto-granting visibility, delete cascading to subpages, and deeper `locked` mechanics beyond the documented restrict-non-owner-edits sentence. (`collectionIds` reorder-only, the partial/merge PUT, the two PUT access side-effects, and the base `locked` restrict-non-owner-edits semantic are now `[DOC]` — see World A and the Page object table.)
6. **World B sharing is "revoke-only".** Only a DELETE `/share/page/.../user/...` is documented; that there is no grant/list-share op is `[INFER]` (absence of a route ≠ absence of the capability).
7. **That World B has no GET route** *as a platform fact*. The spec documents none; Domo ships undocumented `/api/*` reads. Say "no GET is **documented** in `pages-api.yaml`".
8. **That `api.domo.com` has no subpage/move op.** World A documents none; that's the spec's shape, not a proof of absence.
9. **The `page_id` path type.** It is typed **string** on `GET /v1/pages/{page_id}` and **integer** on the collections routes — an unreconciled intra-spec inconsistency. Don't assert one canonical type.
10. **That create-subpage returns the same object as a view-page.** `Pages_CreateSubpageResponse` fields (`virtualPage`, `hasLayout`, `sharedViewPage`, `type`) overlap App Studio view concepts; the identity relationship is **unverified** — don't equate them.
11. **Describe App Studio `{viewId}` single-resource ops here.** Those are `domo-appstudio.md`'s; this file owns the *classic* Page, not the DataApp view-page.
12. **A page-level PDP.** Row policies are dataset-level (`domo-datasets.md`); no documented page-level PDP exists.
13. **The three World B ops from more than one source.** They are single-source `[DOC]` (`pages-api.yaml` only) — corroborated by direct fetch, but no mirror spec.
14. **The meaning of a `type == 'page'` value** in the subpage response. The field exists; its value grammar is unverified.
15. **That the classic Page surface accepts a SID / session cookie.** World A is OAuth-bearer, World B is dev-token; no SID auth is documented for either.
16. **That `llms.txt` is an exhaustive catalog.** It is the catalog we reached; it is not proven complete. Undocumented routes may exist beyond it.
17. **A separate `/v1/dashboards` API — as existing *or* as impossible.** No such spec is in the catalog; both the positive and the negative are unverified beyond that.
18. **Ever tier a classic Page op as `[REPO]`.** The repo has zero classic-Page calls; there is nothing to promote to `[REPO]`.

## Safety & hygiene

- **Probe with a read before you write.** In World A, `GET /v1/pages?limit=1` (or `GET /v1/pages/{id}`) is the cheapest way to confirm host + auth work before any create/update/delete.
- **`DELETE /v1/pages/{id}` is destructive** and (by the model) may cascade to the page's subpages/collections — cascade behavior is `[INFER]`, so treat delete as irreversible and confirm the target `id` first. Never delete a page you did not create in a shared instance.
- **`PUT` in World A is a partial/merge update, not a full-object replace `[DOC]`.** Any parameter left out of the request leaves that attribute **unchanged** (spec PUT description). The old fear that omitting `owners`/`visibility`/`cardIds` *blanks* them is therefore refuted — omitting a scalar field **preserves** it, so the safe minimal update sends **only** the fields you actually want to change. Read-modify-write still earns its keep for **array** fields, where what you send *defines* the outcome: the `cardIds` you provide add or remove cards that aren't part of a collection, and `collectionIds` is **reorder-only** (order follows the IDs you send). So `GET` first to build a correct array payload when you touch one — but for scalar fields send only what changes and let the merge protect the rest.
- **Never hard-code a token.** World A wants an OAuth bearer, World B wants `X-DOMO-Developer-Token`; both are secrets — read from config, never write them into source, handoffs, or commits.
- **Bulk move needs `pagePermission`.** `PUT /pages/bulk/move` requires it; the only documented enum value is `ORIGINAL`. Send it explicitly.
- **`maintenance-instance` is a shared validation instance** — only create/move/delete pages you own (`zz-*`/`test-*`), never someone else's.

## Companion skills

- `domo-appstudio.md` — App Studio view-pages/DataApps (senses **b**/**c**); **the surface the repo actually calls.**
- `domo-cards.md` — the standard cards referenced by `cardIds[]`.
- `domo-identity-access.md` — the users/groups behind `owners`, `visibility`, and `/share/.../user/{personId}`.
- `domo-datasets.md` — dataset-level PDP that scopes what a page's cards show.
- `domo-everywhere.md` — embedding/publishing a page outside the instance (sense **f**).
- `domo-procode-app.md` — Pro Code `fullpage` (sense **d**).
- `domo-variables-filters.md` — Variable/filter controls placed on a page.
