# Domo App Studio / DataApps API Skill

Use this when a task **creates, reads, mutates, embeds cards into, versions, or shares an App Studio
DataApp** (the multi-view "app" surface: pages/views, navigation, layout, landing view, theme) — from a
provisioning script, a clone, or an embed-wiring cycle. It covers the **one small documented island**
(five read/share endpoints on the official *App Studio API* docs page) and the **large undocumented
`[REPO]` sea** around it (every create/mutate/layout/card/variable path), plus the traps that make App
Studio work fail silently: host/auth mismatch, layout writelock, PC-vs-mobile embedding, and the
CE-binding / Workflow-trigger version resolution that 404s a card on a version bump.

Scope boundaries — use the neighbor skill instead when:

- the work is the **Pro Code bundle** that a card renders (manifest, `app.js`, aliases) →
  [`domo-procode-app.md`](domo-procode-app.md);
- you're putting **standard chart cards next to Pro Code on one page** (filter/Variable propagation,
  O(N) version-binding cost) → [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md);
- it's a **standard card's own CRUD/chart-type** definition → [`domo-cards.md`](domo-cards.md);
- it's **Code Engine** auth/packaging → [`domo-code-engine.md`](domo-code-engine.md);
- it's a **Workflow** definition (triggers/tasks) → [`domo-workflow.md`](domo-workflow.md).

The cross-instance write recipes (bodies, field-by-field) live in
[`../docs/reference/app-studio-clone.md`](../docs/reference/app-studio-clone.md) — this skill is the
map + the tier discipline over that reference, not a re-transcription of every body.

## Evidence tiers

Every load-bearing line carries a tier. Anything `[REPO]` or `[INFER]` must be re-verified live on the
target instance before you depend on it — App Studio's write surface drifts by instance and by version.

```
[DOC]   Official Domo docs — the docs portal (domo.com/docs/portal), incl. the
        App Studio API reference page, or the developer API reference / OpenAPI.
[KB]    Domo Knowledge Base / support / community. Product behavior, limits, UI facts.
[REPO]  Verified only against this repo's working usage on a live instance
        (maintenance-instance, or a source instance during a 2026-05 cross-instance clone) —
        NOT in public docs. Internal/undocumented; RE-VERIFY per instance + per version.
[INFER] Reasoned from the documented model or community sources — plausible, not first-party.
```


## The headline: one small documented island in a large [REPO] sea

**The correction that anchors this whole skill:** an official **App Studio API** page now exists on the
docs portal (`www.domo.com/docs/portal/API-Reference/app-framework-apis/AppStudio-API`, confirmed live
2026-09-05). It documents **exactly five endpoints — all READ or SHARE**, nothing that mutates a
dataapp's structure. So:

- **list / get / adminsummary / access / share of a DataApp are `[DOC]`.** `dataAppId` is a
  **documented Integer**; `includeHiddenViews` (on get) is a **documented** boolean query param. This
  *raises* those five from the old "the entire App Studio surface is undocumented" framing.
- **Every create, every mutate, every layout write, every card add, every variable/nav wire is still
  `[REPO]`.** The docs page adds nothing there. Do not let the existence of an "App Studio API" page
  tempt you into tagging a write path `[DOC]`.

**Two hosts, and a name-collision trap** `[DOC]`:

| | **DataApp API** (App Studio) | **classic Pages API** (dashboards) |
|---|---|---|
| **Host** | `https://{instance}.domo.com/api/content/v1/dataapps/*` | `https://api.domo.com/v1/pages` (+ instance mirrors) |
| **Auth** | `X-DOMO-Developer-Token` (or session SID) `[DOC]`/`[REPO]` | OAuth 2.0 Bearer for the public one `[DOC]` |
| **"Page" means** | a **view** inside a dataapp (`/api/content/v1/pages/{viewId}`) | a **classic dashboard** — a different object entirely |

- The public OAuth Platform API (`api.domo.com`) has **NO DataApp / App Studio surface** — it only has
  the *classic* "Pages" (dashboards) API. Domo's own overview warns these two "Pages" are different
  objects. Never point a DataApp call at `api.domo.com`, and never assume the classic Pages API touches
  App Studio. `[DOC]`/`[KB]`
- All five documented dataapp endpoints, and every `[REPO]` write path below, live on the **instance
  host** under `/api/content/v*` with a **developer token or SID** — the same host/auth pairing as the
  instance-internal DataSet endpoints (see [`domo-datasets.md`](domo-datasets.md) "two worlds").

## Documented surface — the 5 dataapp read/share endpoints `[DOC]`

All on the **instance host** (`https://{instance}.domo.com`), auth `X-DOMO-Developer-Token`. This is the
complete documented set — if you need anything not in this table, you are in `[REPO]` territory.

| Op | Method + path | Documented query params | Returns / notes | Tier |
|---|---|---|---|---|
| Admin summary | `POST /api/content/v1/dataapps/adminsummary` | `limit`, `skip` | Summaries of dataapps with admin detail; `dataAppId` (Integer) | `[DOC]` |
| List | `GET /api/content/v1/dataapps/` | — | All dataapps for the authenticated user | `[DOC]` |
| Get one | `GET /api/content/v1/dataapps/{dataAppId}` | `includeHiddenViews` (bool) | Full dataapp incl. views/nav when hidden views included | `[DOC]` |
| Access list | `GET /api/content/v1/dataapps/{dataAppId}/access` | `expandUsers` | Users with access to the dataapp | `[DOC]` |
| Share | `POST /api/content/v1/dataapps/share` | `sendEmail` | Grants access; body carries `dataAppIds` (**array**) | `[DOC]` |

- **Over-claim guard:** the docs page shows these five and only these five. The GET body is documented as
  a *read* shape; it is **not** documented as a *PUT-back* shape. The unified PUT that saves edits (below)
  is `[REPO]` — and the GET deliberately returns a **subset** of what PUT requires, so "GET then PUT it
  back" does not round-trip. `[REPO]`
- `includeHiddenViews=true` is the documented way to get every view (the shipping provisioner and the
  clone both read with it). `[DOC]`

## Identity, context, and version pinning

- **`dataAppId` is an Integer** (DOC-confirmed), returned on the list/get endpoints. In App Studio's
  *list/create* responses this repo has seen the id under the key **`dataAppId`** (not `id`/`guid`); a
  resolver that only reads `id` picks up the wrong value and embeds the wrong app. Read `dataAppId`
  explicitly and fail loud if it's empty. `[REPO]`
- **`viewId == pageId`.** A "view" inside a dataapp is addressed as a *page*: rename, layout, and card
  endpoints all take the **viewId** in the `/pages/{viewId}` slot. There is no separate pageId to chase.
  `[REPO]`
- **PINNED vs FOLLOW_LATEST** — which design version an embedded context renders. Read it from
  `GET /domo/apps/v2/contexts/{contextId}` → `designVersion`; a context is either pinned to a specific
  design version or set to follow the latest publish. This is the switch that decides whether a Pro Code
  / CE version bump reaches the live card automatically (see the wiring section). `[REPO]`
- **Layout `isDynamic` decides the mobile contract.** For a single-card full-page mobile embed, this
  repo ships `isDynamic:false` (static layout). Do **not** generalize any one instance's `hasPageBreaks`
  value into a universal rule — see the hedge list. `[REPO]`

## Reading a view's structure (cards / stack / layout) — all `[REPO]`

To find what cards/containers a view holds, there are three read paths of **different reliability**. None
is on the docs page — all `[REPO]`, all instance-host + dev-token/SID.

| Read path | Method + path | Strength (this repo's experience) | Tier |
|---|---|---|---|
| **Cards on a view** | `GET /api/content/v1/pages/{viewId}/cards` | Primary, but **400s `PAGE_ACCESS_DENIED` instance-wide** on some instances | `[REPO]` |
| ↳ fallback | `GET /api/content/v3/stacks/{viewId}` | **Weakest** — PARTIALLY confirmed; use only when v1 400s | `[REPO]` |
| **Layout (authoritative)** | `GET /api/content/v4/pages/{viewId}/layouts` | **Strongest** — the layout the write PUT round-trips against | `[REPO]` |

- **Order of attempt:** the shipping provisioner tries the **v1 `/cards`** endpoint first and falls back
  to **v3-stacks** when v1 fails; treat v3-stacks as the least-trustworthy of the three (it under-reports
  on some instances). For anything you're about to *write*, read the **v4 `/layouts`** — that's the body
  the layout PUT mutates and the only read that reflects the appendix entries created by prior card
  placements. `[REPO]`
- The v1 `/cards` 400 is an **instance-wide `PAGE_ACCESS_DENIED`** on some instances even with a valid
  token — it is not (necessarily) a real permission problem on that one view; it's the endpoint. Don't
  read it as "I lack access to this page." `[REPO]`
- **Do not tag any of these three read paths `[DOC]`.** The only documented read of a dataapp is
  `GET /api/content/v1/dataapps/{dataAppId}?includeHiddenViews=true`, which returns the view *list* and
  nav — not the per-view card/layout detail these three return.

## Writing / mutation — every endpoint here is `[REPO]`, instance/version-fragile

Nothing in this section is on the docs page. Bodies (field-by-field) are in
[`../docs/reference/app-studio-clone.md`](../docs/reference/app-studio-clone.md); this is the map + the
tier hedges. All instance-host, `X-DOMO-Developer-Token` (or SID).

| Purpose | Method + path | Tier + hedge |
|---|---|---|
| Create dataapp shell | `POST /api/content/v1/dataapps` | `[REPO]` |
| **Add a view (shipping path)** | `POST /api/content/v1/dataapps/{id}/views` | `[REPO]` — what the provisioner uses per-view |
| **Unified save (clone path)** | `PUT /api/content/v1/dataapps/{id}?includeHiddenViews=true` | `[REPO]` — single-instance editor capture |
| Rename a view | `PUT /api/content/v1/pages/{viewId}` body `{"title": "<new>"}` | `[REPO]` |
| Read layout (to mutate) | `GET /api/content/v4/pages/{viewId}/layouts` | `[REPO]` |
| Acquire layout writelock | `PUT /api/content/v4/pages/layouts/{layoutId}/writelock` body `{}` | `[REPO]` — instance-dependent |
| Write layout | `PUT /api/content/v4/pages/layouts/{layoutId}` | `[REPO]` — surgical mutation only |
| Release layout writelock | `DELETE /api/content/v4/pages/layouts/{layoutId}/writelock` | `[REPO]` |
| Create document/image card | `POST /api/content/v1/cards?pageId={viewId}` | `[REPO]` |
| Create/update KPI card | `PUT /api/content/v3/cards/kpi?pageId={viewId}` / `.../kpi/{urn}` | `[REPO]` |
| Register variable control | `PUT /api/content/v1/variable/controls` (body is ARRAY) | `[REPO]` |
| Bind variable to a view | `PUT /api/content/v1/variable/controls/PAGE/{viewId}` | `[REPO]` — **session-bound**, rejects token replay |

**Two different "add content" paths — don't conflate them (hedge f):**

- The **shipping provisioner** builds a dataapp view-by-view with `POST /dataapps/{id}/views`. This is the
  idempotent path a fresh provision should follow.
- The **unified `PUT /dataapps/{id}`** is the body the App Studio *editor* sends on "Save", captured
  during a cross-instance **clone** on a single source instance. It's the right tool for cloning an
  existing app's nav/theme/landing/view-order in one shot, but it is a single-instance capture with
  **required-on-PUT fields that come back `null` on GET** (`viewIds` parallel to `views[]`,
  `pageDrillParentStates:[]`, `conversationalAgentContextRequest`, `viewId`/`landingViewId` as **strings**,
  `parentViewId:"0"`). Missing any of them → new views silently dropped or a bare 400. `[REPO]`

**Layout PUT is surgical — but not strictly "in-place only" (hedge c):**

- A **rebuilt** `content[]`/`template[]` body → generic **400, no detail**. You must GET the current
  layout and **mutate the entries it already has** (mirror the source card's style flags onto the matching
  `cardId`; set `x/y/width/height` and `virtual:false`/`virtualAppendix:false` on the matching
  `contentKey`). `[REPO]`
- **You CAN append** new containers (e.g. TABS) — the rule is every new `contentKey` must be **above the
  highest existing `contentKey`**, or it collides with the target's auto-appendix entries and 400s. So
  "layout PUT only edits existing entries" is wrong: new entries are addable at `contentKey > max`.
  `[REPO]`

**Writelock codes are single-instance, not portable (hedge d):**

- Use `PUT` to acquire (returns `{layoutId,userId,lockTimestamp,lockHeartbeat}`), always `DELETE` to
  release **in a `finally`**. `[REPO]`
- **Do NOT hard-code the status codes.** On one instance the layout PUT was accepted with **no lock** and
  `POST .../writelock` returned **405**; on `maintenance-instance` the lock was **required** and omitting it returned
  **403 `WL003`**. Treat writelock as: try `PUT`-acquire, do the write, `DELETE`-release in `finally`, and
  **degrade gracefully** if acquire fails rather than asserting a specific code. `[REPO]`

**Cards — the only documented card-render endpoint is not a create (hedge g):**

- Document/image cards: `POST /api/content/v1/cards?pageId={viewId}` with `type:"document"`; **`metadata.title`
  must be filename-style** (`"Banner"` → 400; `"Executive Summary.png"` → 200 — the title is parsed for an
  extension). `[REPO]`
- KPI cards: `PUT /api/content/v3/cards/kpi?pageId={viewId}` (create) and `.../kpi/{urn}` (update); on
  UPDATE **keep `definition.modified` and `definition.allowTableDrill`**, and **re-emit every source Beast
  Mode as a card-level BM in `formulas.card[]`** (emptying `card[]` orphans `formulaId` refs → 400). `[REPO]`
- The **only `[DOC]` cards path** is the v1 `.../render` endpoint that returns a **PNG image** of a card —
  that is a render, not a create. Never present the v3 `cards/kpi` create/update as documented. `[REPO]`

**Variable + nav wiring needs an editor session — plan a manual task (hedge i):**

- `PUT /api/content/v1/variable/controls/PAGE/{viewId}` (adds a variable's pill to a view) **rejects
  token-auth replay with 400 even with the byte-identical captured body** — it requires App Studio editor
  session state. Same for the **nav phosphor-icon** save: after the unified PUT, VIEW nav icons revert to
  `{value:"pages"}` (both `value` and `phosphor` stripped), and re-applying the rich icon uses a separate,
  session-bound endpoint. Emit a **per-view manual task** ("open the app → Controls → drag the variable
  onto the view → Save", and the icon recommendation) rather than pretending a token call can do it.
  `[REPO]`

## Layout embedding facts (PC vs mobile, the fields that actually bite)

The layout fields that actually decide whether an embedded app renders and clicks correctly — learned
the hard way, all `[REPO]`:

- **`isDynamic`** — for a single Pro Code card meant to fill a mobile screen, this repo ships a **static**
  layout (`isDynamic:false`), with `printFriendly:false`, `virtual:false`/`virtualAppendix:false` on the
  card's template entry. A missing/`true` `isDynamic` with no `PAGE_BREAK` was the cause of a
  **mobile-only white screen** (a Domo spinner and nothing else). That white-screen diagnosis is
  **`[INFER]`, n=1** — the fix bundled three changes (`isDynamic:false` + fixed 60×82 / 12×29 sizing +
  a `PAGE_BREAK`), so no single one is proven the cause. `[REPO]`/`[INFER]`
- **`PAGE_BREAK` is NOT universally required (hedge b).** It was part of the bundled mobile-white-screen
  fix for a **single-card full-page embed**, and that's the only scope in which to reach for it. A
  cross-instance clone shipped a working `isDynamic:false` layout with **`hasPageBreaks:false`** and no
  page break. Scope the advice to "single-card full-page mobile embed", never "always add PAGE_BREAK".
  `[REPO]`
- **`interaction.type=DISABLED` kills PC clicks.** Setting a card's interaction to DISABLED removes the
  blue mobile focus ring — but also **disables click on PC**, which matters more. Keep interaction unset
  (pop) / `editInAppViewer:true`; suppress the mobile ring with static layout + sizing instead. The blue
  ring that persists after that is **host chrome** (the App Studio iframe), an **open backlog** item, not
  something the layout body removes. `[REPO]`
- **PC is the priority surface** for App Studio embeds in this repo's apps; some are explicitly
  **mobile-out-of-scope** (App Studio embed on PC/tablet, narrow width is horizontal-overflow by design).
  Confirm the target app's stance before spending effort on `@media` mobile tuning. `[REPO]`

## Wiring cards that live on a page — CE bindings and Workflow triggers

A card embedded in an App Studio view carries **snapshots** of its Code Engine and Workflow wiring. How
a version bump propagates depends on the wiring and the context's pin state — this is the single most
expensive App Studio footgun, so treat it carefully (hedge h):

- **CE alias binding (`packagesMapping`) is snapshotted into the card instance at embed time** `[REPO]`.
  Bumping the CE version and re-publishing does **not** update a card that snapshotted an older version —
  it keeps calling the old alias and **404s**.
- **Exception — FOLLOW_LATEST App Studio cards resolve CE binding from the design version**, so for those
  a `domo publish` of the CE package *does* reach the live card. A **PINNED** context does not — it stays
  on its pinned design version. Read the context's `designVersion` (above) to know which you have.
  `[REPO]`
- **Workflow `triggerId` NEVER auto-resolves across versions.** KB **000005179** states workflow
  **triggers cannot be copied between versions**; a card's `workflowMapping` holds a specific `triggerId`
  that a version bump orphans. `[KB]` The confirmed repair is manual: **re-issue the card → re-embed it →
  delete the old card** (the card instance is the version selector; layout provisioning does *not* touch
  the wiring, which lives on the card instance, so re-provisioning layout won't fix it). `[REPO]`
- **Net rule:** after a CE/Workflow version bump, a **PINNED** or **workflow-wired** card needs
  re-issue + re-embed + delete-old; a **FOLLOW_LATEST CE-only** card fixes itself on publish. When in
  doubt, verify the live card actually calls the new version before declaring the bump done. `[REPO]`

See [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md) for the O(N) cost of this when a
page holds many wired cards, and [`domo-code-engine.md`](domo-code-engine.md) for CE packaging.

## Do NOT claim as documented fact (hedge list)

The verification's whole point was to keep these from being written as `[DOC]`. Do **not** state any of
these as a documented, portable Domo contract:

1. **That any dataapp *write/mutate* endpoint is documented.** Only list/get/adminsummary/access/share
   are on the App Studio API page (`[DOC]`). Every create/PUT/layout/card/variable path is `[REPO]`.
2. **That the documented GET body can be PUT back to save.** GET returns a **subset**; the unified PUT
   requires fields that are `null`-on-GET. The save-PUT is `[REPO]`, single-instance-captured.
3. **That `PAGE_BREAK` is universally required.** It belongs only to the **single-card full-page mobile
   embed** fix; a working clone shipped `isDynamic:false` + `hasPageBreaks:false` with no page break.
4. **That the layout PUT is "in-place only".** New entries (e.g. TABS) are addable at
   `contentKey > max(existing)`; only *rebuilt* bodies are rejected.
5. **That writelock returns a specific code (`WL003`/403/405).** Codes differ by instance/version —
   one instance needs no lock (405 on POST), another requires it (403 `WL003`). Try-acquire /
   write / release-in-`finally`, degrade gracefully; don't assert a code.
6. **That the mobile white-screen was caused by any one field.** `[INFER]`, n=1 — the fix bundled
   `isDynamic:false` + fixed sizing + `PAGE_BREAK`; causation is not isolated.
7. **That the unified `PUT /dataapps/{id}` is the normal add-content path.** It's the **clone** path
   (single source-instance editor capture). The shipping provisioner adds views via
   `POST /dataapps/{id}/views`.
8. **That `POST /cards` or `PUT /cards/kpi` is a documented card API.** The only `[DOC]` cards endpoint
   is v1 `.../render` (returns a **PNG**). Create/update of dataapp cards is `[REPO]`.
9. **That CE FOLLOW_LATEST behavior means Workflow triggers also auto-resolve.** They do **not** —
   KB 000005179: triggers can't be copied between versions (`[KB]`); pinned/workflow-wired cards need
   re-issue + re-embed + delete-old (`[REPO]`).
10. **That variable page-binding or nav-icon save works over token auth.** Both are session-bound and
    reject token replay with 400 (`[REPO]`) — emit a manual task.
11. **That the classic Pages API (`api.domo.com/v1/pages`) touches App Studio.** Different object; App
    Studio DataApps live only on the instance host under `/api/content/v*`.

## Safety / hygiene

- **`maintenance-instance` is a shared Domo-internal validation instance.** Create/modify/delete only **self-owned,
  clearly-named** dataapps (`zz-*`/`test-*`), and verify ownership + timestamp before deleting. Never
  modify, delete, or inventory an App Studio app you did not create.
- **Layout and unified PUTs overwrite live structure.** A malformed body can strip nav, reorder views, or
  drop a card. Read the current object first (v4 `/layouts` for layout, GET dataapp for the app), mutate
  surgically, and — for layout — hold the writelock and release it in a `finally` so a crash doesn't leave
  the view locked for the human editor.
- **A version bump can silently 404 a live card.** After any CE/Workflow bump, verify the embedded card
  actually calls the new version (don't declare done on publish alone) — see the wiring section.
- **Never commit** developer tokens, SIDs, OAuth secrets, captured request bodies that embed tokens/cookies,
  or downloaded dataapp/layout JSON that carries instance-identifying content. Summarize; don't paste raw
  captures into commits/handoffs.
- **Deploys are pre-authorized** for this workspace (AGENTS.md) — run them without asking — but do them in
  **small increments**, one change at a time, and confirm each live before the next.

## Repo precedent

Working App Studio usage already lives in the repo — **grep the function/token, not the line** (line
numbers drift): `[REPO]`

| Where | What it demonstrates |
|---|---|
| `../docs/reference/app-studio-clone.md` | The canonical write-body reference: unified dataapp PUT, surgical layout PUT + TABS-append, writelock, document/image card create, KPI card UPDATE, variable-control + session-bound page-binding |
| `inventory-management-app/scripts/provision_domo.py` | `configure_app_studio_layout` (isDynamic:false, virtual/virtualAppendix:false, PAGE_BREAK, writelock PUT/DELETE-in-`finally`), `add_dataapp_view`, `_id()` reading `dataAppId`, `_list_page_cards` (v1 `/cards` → v3-stacks fallback), PINNED/FOLLOW_LATEST from `contexts/{id}.designVersion` |
| `equipment-inventory-app/scripts/provision_domo.py` | The deploy order that matters — `apply → sync-manifest → publish → app-studio → verify` (out of order bakes an empty `packageId` into the version → CE 404s) |
| `asset-lifecycle-app/scripts/provision_domo.py` | `rename_dataapp_view` — `PUT /api/content/v1/pages/{viewId}` body `{"title": ...}` |
| `pl-summary-app/`, `equipment-analytics-app/scripts/provision_domo.py` | Additional App Studio provisioning + multi-page (guide-tab) layouts |

Companion skills: [`domo-procode-app.md`](domo-procode-app.md) (the bundle a card renders),
[`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md) (many cards on one page + version-bind
cost), [`domo-cards.md`](domo-cards.md) (standard card CRUD), [`domo-datasets.md`](domo-datasets.md)
(the same instance-host / dev-token world), [`domo-code-engine.md`](domo-code-engine.md) (CE packaging),
[`domo-workflow.md`](domo-workflow.md) (Workflow triggers).
