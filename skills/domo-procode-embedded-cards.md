# Pro Code + Standard Cards Skill

Use this when the goal is **"many standard Domo cards plus a thin layer of custom logic, in one
maintainable app."** It answers the feasibility question honestly and points at the architecture that
actually works. Companions: standard-card authoring in [`domo-cards.md`](domo-cards.md); Pro Code
bundle mechanics in [`domo-procode-app.md`](domo-procode-app.md).

## The headline (verified against this repo + live API, 2026-09-05)

**You cannot cleanly embed standard cards *inside* a single Pro Code app's own DOM as a supported,
self-contained pattern. The maintainable realization of the goal inverts the container: an App Studio
page (dataapp) is the container; standard cards are laid out on it natively; the Pro Code app is added
as *one more card* on the same page for the parts standard cards can't do.**

Why the literal "cards inside one Pro Code bundle" shape does not hold:

- **There is no `cardsMapping`.** A Pro Code `manifest.json` maps only `datasetsMapping`,
  `collectionsMapping` (AppDB), `workflowsMapping`, `packagesMapping` (Code Engine), and
  `accounts/actions/databasesMapping`. Re-verified across every manifest in this repo: **no card
  mapping key exists**. A standard card is not a declarable app resource — you cannot bind one into a
  bundle the way you bind a dataset or a Code Engine package.
- **A Pro Code app is itself a card.** Domo publishes a custom app *as a card/tile* you drop onto a
  page — so "cards inside the app" is backwards; the app sits *beside* cards, as a sibling tile.

## Recommended architecture: App Studio page as the container

This is the repo's own precedent — `configure_app_studio_layout(...)` in several
`*/scripts/provision_domo.py` lays cards out on an App Studio page, and Pro Code apps embed as a tile
on that page.

```
App Studio page (dataapp)  ← the container; owns page filters, date filters, Variables, theming
  ├─ standard card (Analyzer-authored)   ← native drill, filters, PDP, refresh — maintainability 5
  ├─ standard card
  ├─ standard card  … (as many as possible)
  └─ Pro Code custom-app card            ← exactly ONE thin tile: only what standard cards can't do
```

- **Maximize standard cards.** Everything expressible as a standard chart should be a standard card:
  zero code, native interactivity, page-level filter/date/Variable propagation, per-instance theming,
  Personalized Data Permissions, and automatic refresh. This is the maintainability win the user wants.
- **Keep the Pro Code tile thin.** Reserve it for bespoke interaction, a custom write-back flow, a
  Code Engine call, or a visual no standard card offers. One tile, small surface. When one thin tile
  genuinely isn't enough, scaling to several Pro Code cards on the page is supported — see
  "Multiple Pro Code apps + multiple standard cards on one page" for the mechanics and the real cost.
- **Trade-off to state plainly:** the deliverable is then *several Domo objects* (cards + dataapp +
  custom app), not one self-contained bundle. Cross-instance cloning is heavier (the repo does surgical
  layout PUTs with write-locks; see the inventory/asset-lifecycle `provision_domo.py`). You gain
  maintainability and native behavior; you give up "one portable bundle."

## Multiple Pro Code apps + multiple standard cards on one page

Feasible and platform-supported — the interesting question is *when*, not *whether*, because cost
scales with the number of Pro Code cards. (Verified 2026-09-05: research + adversarial-verify pass,
**0 claims refuted, 0 unverifiable**; repo artifacts + Domo docs.)

**Why it works.** A layout tile is **type-agnostic**: every placed card — standard KPI/chart or Pro
Code — serializes as the same `{type:"CARD", contentKey, x, y, width, height, virtual}` tile. The
chart type lives on the *card definition* (`metadata.chartType=="domoapp"` for Pro Code; cardType
`kpi` + a `badge_*` for standard), **not** on the tile. `layout.content[]` and
`layout.standard.template[]` / `compact.template[]` are arrays with no cardinality-of-1 limit. Repo
proof of multi-card capacity: `pl-summary-app/app-studio/page-layout.json` places **12 CARD tiles**
(+ SPACER/SEPARATOR) across **3 segments** delimited by 2 `PAGE_BREAK`s. *Honest limit of the
evidence:* a `domoapp` card and a `kpi` card interleaved on the **same segment** is guaranteed by the
schema + Domo's "pro-code and no-code coexist" docs, but was **not witnessed in a single repo
layout** — treat mixed-on-one-page as schema-supported and confirm on the target instance.

**Placement mechanics — generalizing the repo's single-card `configure_app_studio_layout`.** Each Pro
Code card is minted independently: `POST domoapps/apps/v2/contexts` (dataset `mapping` + AppDB
`collections`) → `POST domoapps/apps/v2?{query}` with that `contextId` (Domo allocates a distinct
outer proxy, `proxy_id != context_id` — do **not** send `id=contextId`). The layout write is the same
write-locked full-object PUT the repo already uses: `PUT api/content/v4/pages/layouts/{layoutId}/writelock`
→ PUT the full layout with **multiple** `content[]` entries and **multiple** CARD tiles at distinct
`x/y/width/height` → release the lock. The repo's `configure_app_studio_layout` today filters
`content[]` down to one card and stacks it at `x:0,y:0`; the multi-card case appends N entries and lays
out N tiles — the layout *shape* is proven (page-layout.json), the *builder generalization* is
greenfield in the repo. **N Pro Code cards = N contexts + N instances + N iframes**, with the
dataset/AppDB mappings duplicated into each context.

**Filters, dates, and Variables propagate ASYMMETRICALLY by card type:**

- **Standard cards** receive page filters, date filters, and App Studio Variables **automatically and
  natively** (server-side re-query, zero code). This is the maintainability win.
- **Pro Code cards get nothing automatically in-code** — the iframe is sandboxed. The app must opt in
  through the `domo.js`/`ryuu.js` postMessage bridge:
  - Register `domo.onFiltersUpdate` (v5 `onFiltersUpdated`). The callback gets an **array of filter
    descriptors** (`column`, `operand`, `values[]`, `dataType`, `dataSourceId`, `label`). **Date
    filters ride this same channel** (a date-typed filter whose `values` carry the range) — there is
    no separate date API. **Applying the filter to the app's own queries/state is the app's job.**
  - Nuance: `domo.get` is scoped to the filters *as they were at load*; the default un-handled behavior
    on a filter change is a **full iframe reload** that re-runs the query with current filters.
    Registering `onFiltersUpdate` **suppresses that reload**, so you then own translating later changes
    onto your own queries.
  - Push outward with `domo.filterContainer` (v5 `requestFiltersUpdate`) — the canonical "one card's
    selection filters the whole page" pattern.
  - Variables: **read** via `domo.onVariablesUpdated`, **write** via `domo.sendVariables` (v5
    `requestVariablesUpdate`). *Hedge:* that writing a Variable re-drives standard cards bound to it is
    plausible-by-model, **not proven here**, and the exact `requestVariablesUpdate` payload shape is
    unverified — confirm live before relying on it.

**Sibling cards cannot talk directly.** Every Pro Code card is a cross-origin sandboxed iframe
(`domoapps.*` origin); same-origin policy + the sandbox + `ryuu.js`'s own origin check block direct
DOM/iframe access, and the bridge's `MessageChannel` port is shared only with `window.parent`. **All
coordination is relayed by the parent (Domo host) frame** through four sanctioned channels:

| Channel | API (4.6.0 → v5) | Reaches standard cards? | Use for |
|---|---|---|---|
| Page filters | `filterContainer`/`onFiltersUpdate` → `requestFiltersUpdate`/`onFiltersUpdated` | **Yes** (dataset/column-scoped) | selection → drill / filter |
| Page Variables | `sendVariables`/`onVariablesUpdated` → `requestVariablesUpdate` | Yes (cards bound to it) | shared scalar UI state |
| Custom App Data | `sendAppData`/`onAppData` → `requestAppDataUpdate`/`onAppDataUpdated` | No (custom-app ↔ custom-app only) | rich custom events |
| Shared AppDB / dataset | `domo.post`/`domo.get`; push only via `onDataUpdate`/`onDataUpdated` | via the data | durable / cross-session state |

To coordinate a Pro Code card with a **standard** card you must use **filters or Variables** — standard
cards run no author JS, so appData never reaches them.

**Decision rule — prefer fewer Pro Code cards:**

1. **Default: standard-cards-first** — App Studio page + as many native standard cards as possible +
   **one thin Pro Code tile**. Native drill/filter/PDP/refresh and filter/Variable propagation for free.
2. **Consolidate into ONE larger Pro Code app** when several custom views genuinely share state/logic and
   you want interaction the platform won't wire. Collapses N iframes/bundles/version-lifecycles into one —
   at the cost of all-or-nothing versioning and prop-threading fragility (a new prop must thread the whole
   component chain or you get a runtime white screen `node --check` misses).
3. **Multiple *separate* Pro Code cards** only when the apps are truly independent (different owners,
   release cadences, or reused on other pages). Otherwise it's an anti-pattern. **Decisive cost:** each
   card **snapshots its Code Engine and Workflow version binding at embed time**, so a shared-server-code
   bump carries an O(N) manual re-embed/re-wire tax (stale CE alias → `404 "No parameter name found for
   the alias"`; stale workflow `triggerId` → the old version keeps firing). *Exception:* a card on
   **FOLLOW_LATEST** resolves its CE binding from the design version, so a plain `domo publish` refreshes
   it without re-embed — the manual tax applies firmly to **workflow `triggerId`** pinning (no
   auto-resolve) and to CE cards **not** on FOLLOW_LATEST. See `domo-code-engine.md` / `domo-procode-app.md`.

**Capacity budget.** No published hard cards-per-page cap exists; ~15 cards is *third-party* best practice
for **lightweight** standard cards. Pro Code iframe cards are much heavier (each boots a bundle + bridge +
its own data/CE queries; each design is capped at **100 data connections**), so budget **far fewer** and
scale out with `PAGE_BREAK` multi-page navigation (add a page/tab with `add_dataapp_view` →
`POST api/content/v1/dataapps/{app_id}/views`). Always measure real load time on the target instance —
per-iframe cost here is architectural/qualitative, **not benchmarked**.

**SDK version caveat.** The repo vendors `ryuu.js` **4.6.0** (`onFiltersUpdate`, `filterContainer`,
`sendVariables`, `sendAppData`, `onDataUpdate`); **v5** renames these to `onFiltersUpdated`,
`requestFiltersUpdate`, `requestVariablesUpdate`, `requestAppDataUpdate`, `onDataUpdated`
(`onVariablesUpdated` already carried the `-ed` form in 4.6.0). Feature-detect and pin the SDK version.

## If you truly need a card rendered inside the Pro Code DOM

The only sanctioned way to put a live standard card inside your app's own markup is a **Domo Everywhere
embed** (`<iframe>` to a per-card embed ID). Treat it as the exception, not the default:

1. Enable embedding per card in **Admin → Domo Everywhere → Embed** — this yields one embed ID per
   card (no bulk/dynamic enablement).
2. **Public embed** = a plain `<iframe>` at the embed ID: view-only, no auth, and the data is
   world-readable (governance risk; AppDB-in-Bricks is blocked in public-embed contexts).
3. **Private embed** = a **server** authenticates with an OAuth `client_id`/`client_secret`, mints a
   short-lived embed token, and the iframe loads the live card with it. Supports PDP and programmatic
   filters. The secret can **never** live in front-end code, so private embed forces a backend *outside*
   the self-contained app.

Costs to weigh: a nested iframe (app iframe → embed iframe) with CSP / "Embed Authorized Domains"
allowlist friction; per-card enablement; and for private embed, an external token server. A
**render-to-image** endpoint (`PUT /api/content/v1/cards/kpi/{urn}/render`) exists and is documented,
but returns a **static PNG** and needs a developer token the app front-end must not hold — it is not a
live card. Framing the card's own Domo URL directly is refused by `X-Frame-Options`/`frame-ancestors`
except through the sanctioned Everywhere embed.

## Decision guide

| You want… | Do this |
|---|---|
| Mostly standard charts + a little custom logic, best maintainability | **App Studio page** (cards + one Pro Code tile). Default. |
| Several standard charts + more than one custom view in one destination | Multiple cards on one App Studio page (standard + Pro Code) — see "Multiple Pro Code apps + multiple standard cards on one page." Prefer consolidating into one Pro Code app unless the views are truly independent; mind the O(N) version-binding tax. |
| A live card literally inside your app's DOM, same instance, interactive | Domo Everywhere **private** embed (needs a server to mint the token). |
| A read-only card snapshot in your app | Render-to-image is a static PNG only — no drill/filter; avoid unless a picture truly suffices. |
| One portable bundle that *is* the card set | Not supported — cards aren't manifest resources. Re-scope to App Studio. |

## Safety / hygiene

- Never put an OAuth `client_secret` or embed token in front-end Pro Code — the SDK forbids it and it
  would leak to every viewer. Private embed tokens are minted server-side only.
- Don't hardcode card IDs/embed IDs as customer-identifying values in committed source; treat them like
  other IDs (config/state files, not literals in shared artifacts).
- App Studio layout writes use write-locks; follow the existing `provision_domo.py` pattern rather than
  hand-PUTting layouts, to avoid clobbering a concurrently-edited page.
