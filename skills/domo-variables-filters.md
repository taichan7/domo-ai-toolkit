# Domo Variables & Filters

Use this when you are reading, driving, or reasoning about a Domo **Variable** (the interactive dashboard/Analyzer value a viewer changes through a control, which then feeds Beast Modes) or a dashboard/card **filter** — especially from inside an embedded Pro Code app, or when you have to tell one "variable"/"filter" apart from the several unrelated things that share the name.

This surface is not shaped like the others in the cycle. Identity and AI-services were **large documented REST islands**; governance-datasets was the **inverse — no documented API at all**. Variables & filters are a **client-side interaction surface**: the feature is defined and its value is driven from *inside* an embedded app through the documented App-Framework JS SDK (ryuu.js), while its server-side management rides *other surfaces'* APIs (Beast Mode functions, the embed-token body, PDP). So the honest move here is mostly **disambiguation and deferral** — most of the value is knowing which "variable" or "filter" you are looking at and which skill owns its API.

## What this skill owns (and what it defers)

This skill claims exactly **three faces** and defers everything else:

**Owns:**
1. The interactive **Variables feature** itself — what it is, its data types, its definition/value scope model, its controls, and its governance grant (product behavior, `[KB]`).
2. The **dashboard/card filter object** and how a filter *propagates* to standard cards / into an embedded app.
3. The **ryuu.js App-Framework client** for reading and driving filters and variables from inside an embedded Pro Code app (`onFiltersUpdate` / `filterContainer` / `onVariablesUpdated` / `sendVariables` and their v5/v6 renames).

**Defers (do not restate their API contracts here — cross-reference):**

| Face | Owner |
|---|---|
| Beast Mode `functions` API (the `variable:boolean` flag lives here) | `domo-beast-mode.md` |
| **Workflow** variables (`"type":"variable"` in workflow JSON) | `domo-workflow.md` |
| Pro Code `manifest.json` mappings | `domo-procode-app.md` |
| DataSet SQL `WHERE` + PDP row policies | `domo-datasets.md` |
| Domo Everywhere embed-token filter body + client Pfilter | `domo-everywhere.md` |
| The App-Studio variable-control bind endpoint | `domo-appstudio.md` |
| Multi-Pro-Code + multi-standard-card coordination on one page | `domo-procode-embedded-cards.md` |

## Evidence tiers

```
[DOC]   developer.domo.com API reference / docs-portal OpenAPI or integration pages /
        machine-readable OpenAPI YAML / the ryuu.js (domo-js) first-party SDK reference.
        NOTE: a domo.com/docs/s/article/<12-digit-id> page is a Salesforce KB help
        article = [KB], NOT [DOC], even though it lives on the docs domain.
[KB]    Domo Knowledge Base / help articles / documented product behavior.
[REPO]  Verified only against THIS repo's working code (re-verify per instance/SDK version).
[INFER] Reasoned from the documented model / community / marketing / inference-from-absence.
```

On disagreement, choose the **more conservative** tier. **A fetch FAILURE (405 / JS-gated) is MISSING evidence, not proof of absence** — do not mechanically downgrade a positive claim because a *different* page failed to load; and never let a fetch failure be read as confirming a negative.


## The headline

A Domo **Variable** is one product object with two faces: a **value-face** authored in the enhanced Beast Mode Editor, and a **control-face** — the interactive widget a viewer uses to change that value. It is read and driven along three documented paths, and has no dedicated REST API of its own:

- **Its DEFINITION** is surfaced through the documented **Beast Mode `functions` API** as a function object carrying a boolean `variable` field (host `{instance}.domo.com`, auth `X-DOMO-Developer-Token`) — `[DOC]`, but that API is owned by `domo-beast-mode.md`. You can search / read / lock / update-expression a variable-flagged function there; there is **no create or delete endpoint present in `beastmodes.yaml`** — state that as "not present in that spec," never "no REST way exists" (`[INFER]`).
- **Its runtime VALUE** is read and set from inside an embedded app through the documented **App-Framework JS SDK** (ryuu.js): `domo.onVariablesUpdated(cb)` to read, `domo.requestVariablesUpdate(...)` to set — `[DOC]`. There is **no documented REST endpoint that reads or sets a Variable's value** (`[INFER]`); the value lives in card/dashboard control state.
- **Its behavior** — data types, definition scope, the value-control hierarchy, and the governance grant — is documented **product behavior** (`[KB]`).

State the tempting negatives conservatively. "There is no Variables REST API" is **`[INFER]`**, not fact: it rests on absence from a non-exhaustive OpenAPI catalog (`llms.txt`, reached but not guaranteed complete) plus a repo grep-absence — and the repo itself references undocumented instance routes (`/api/content/v1/variable/controls`, `functions/variables/uniqueName`), so variable-related REST routes *do* exist; only a spec **named** "variables" is absent. Say "no `variables.yaml` in the catalog reached," not "no Variables API."

## The four "variable" naming traps

This is the single highest-value guard on this surface. At least four distinct things are called "variable" in Domo:

| # | "Variable" means… | What it actually is | Tier | Owner |
|---|---|---|---|---|
| 1 | **Dashboard / Analyzer Variable** (this skill) | An interactive, named, typed, instance-global value a viewer changes via a **control**, feeding Beast Modes. This is the same object as #3 seen from the control-face. | `[KB]` | this skill (+ beast-mode for its definition API) |
| 2 | **Workflow variable** | Domo Workflows v2 instance-scoped **local state** — appears as `"type":"variable"` inside `designElements[…].advancedRule` in workflow JSON, passed as `data`-object keys at start, referenced by FEEL. Unrelated to #1. | `[KB]`/`[REPO]` | `domo-workflow.md` |
| 3 | **Beast Mode variable** | The value-face of #1, authored in the Beast Mode Editor and consumed inside a formula (double-click to insert, reference by name). **Not** an inline/local `let`/`DECLARE` — there is no scratch-local syntax (`[INFER]`). | `[KB]` | this skill (+ beast-mode) |
| 4 | **Pro Code "manifest / env variable"** | A **misnomer.** `manifest.json` holds mappings + metadata; no `domo.env`, per-instance-settings, or customization schema is *documented*, and this repo's manifests have **no** `variables`/`variablesMapping`/`env`/`settings`/`customization` key (grep = 0). The "no env-var feature" conclusion is `[INFER]` (absence-from-a-page-that-also-failed-to-load), not a documented contract. | `[REPO]`/`[INFER]` | `domo-procode-app.md` |

Senses **1 and 3 are ONE object**, two faces — not two object types. "App Studio Variables" is likewise **not a fifth kind**: it is sense #1's Dashboard Control surfaced as a pill on a view, bound via an undocumented session-bound endpoint (`domo-appstudio.md`). Variables are also *supported for* Domo Everywhere embedding — a consumption context, not feature ownership (`[KB]`).

## The six "filter" naming traps

"Filter" fans out even wider. These are unrelated mechanisms with different shapes, vocabularies, and owners — copying one's syntax into another's slot fails, sometimes **silently**:

| Sense | What it is | Shape / vocabulary | Tier | Owner |
|---|---|---|---|---|
| A — **dashboard/page filter object** | The UI filter a viewer sets; propagated into a Pro Code app via the ryuu SDK | array of filter objects; SDK channel `onFiltersUpdate`/`filterContainer` (v5 `onFiltersUpdated`/`requestFiltersUpdate`) | `[REPO]` (+ `[KB]` for the feature) | this skill |
| B — **DataSet SQL `WHERE`** | A raw SQL predicate in a server-side query | free-form SQL string, **no enum**; page filters are **not** applied to a SQL read | `[REPO]` (hedged) | `domo-datasets.md` |
| C — **PDP row policy filter** | Row-level security policy | `filters:[{column,values,operator,not}]` under `/v1/datasets/{id}/policies` | `[REPO]` (hedged) | `domo-datasets.md` |
| D — **Domo Everywhere embed filter** | The structured filter in an embed-token body | `filters:[{column,operator,values}]` in `authorizations[]`; server key is **`operator`** (with the literal typo `GREAT_THAN_EQUALS_TO`) | `[DOC]` object / `[REPO]` trap | `domo-everywhere.md` |
| E — **Beast Mode search `filters`** | The `filters` array parameter of `POST /functions/search` that filters the *set of functions returned* (e.g. `{field:'notvariable'}`) | request param, not a data filter | `[REPO]`; the `notvariable` *effect* is `[INFER]` | `domo-beast-mode.md` |
| F — **client-side Pfilter** | Viewer-readable/changeable URL/JS filters on an embed | client uses key **`operand`**; **cosmetic, NOT security** — a public embed carries no PDP | `[REPO]` | `domo-everywhere.md` |

**The `operator`-vs-`operand` trap (senses A/D/F):** the server-side embed body uses `operator`; the in-iframe client Pfilter uses `operand`. The vendored ryuu SDK's `filterContainer()` reads `e.operator || e.operand` defensively and emits `{columnName, operator, …}` to the desktop parent but `{column, operand, …}` to the iOS bridge — a single SDK build's `[REPO]` implementation detail. Copying a client `operand` object straight into a server-token `filters[]` body **fails silently**.

## The Variables feature — product behavior `[KB]`

All of the following is documented product behavior in the KB "Variables | Overview" article (`domo.com/docs/s/article/7903767835031` — a Salesforce KB page, so `[KB]`, not `[DOC]`):

- **Data types: Numbers, Strings, Dates.** Creation requires a name + type + default value. There is **no "list" data type** — a "list" is a kind of *Control*, not a Variable type. (This negative is a positive KB enumeration, not argument-from-absence.)
- **DEFINITION scope is global / instance-level.** Every Variable is visible instance-wide; changing a Variable's *default* propagates to every Beast Mode in the instance that uses it.
- **A Variable must be referenced inside a Beast Mode to be used.** It cannot appear on a card or dashboard on its own — the load-bearing rule for consumption. To consume it: double-click to insert it into a Beast Mode formula and reference it by name. (A `CASE` statement keyed on the variable is a *community* pattern — `[INFER]`, not KB.)
- **VALUE scope is a three-level control hierarchy:** Default Control (in the Beast Mode Editor) → Card Variable Control → Dashboard Variable Control. Changes at one level do **not** transfer to another, and a **dashboard refresh resets** Dashboard Variable Controls to the base default.
- **Governance:** the **"Edit Variables"** grant is required to create/edit/delete a Variable; any user with "Edit Cards" can *use* one. Variables can be **locked**.
- **Adding a control in App Studio:** in Edit mode, drag a Control → **Add** → pick a Variable → this creates a **Dashboard Variable Control** that drives every card on the view using that variable.

## Variable DEFINITION surface = the Beast Mode functions API `[DOC]`

A Variable's **definition** is not its own API — it is a **function object** in the Beast Mode `functions` surface, distinguished by a boolean **`variable`** field. Host `{instance}.domo.com`, auth `X-DOMO-Developer-Token` (the Product/dev-token world — **not** the `api.domo.com` OAuth Bearer surface). `[DOC]` from `beastmodes.yaml`.

The documented operations (all owned by `domo-beast-mode.md` — read them there, do not re-contract them here):

- `GET /functions/statistics`
- `POST /functions/search` — its `filters[]` param (e.g. `{field:'notvariable'}`) filters *which functions come back*; the exact `variable`-only filter is implied, only `notvariable` is shown as an example (`[INFER]`).
- `GET /functions/template/{id}`
- `PUT …/functions/template/{id}` (lock/unlock)
- `PUT …/functions/template/{id}/update` (update expression)

There is **no create or delete endpoint present in `beastmodes.yaml`** and **no endpoint that reads or sets a Variable's runtime value** — both `[INFER]` (absence within a single ~505-line spec). Phrase these as "not present in that spec," never as "no such API exists": Domo demonstrably ships undocumented instance routes (this repo references `/api/content/v1/variable/controls` and `functions/variables/uniqueName`), which are `[REPO]`/internal and must not be presented as a public contract.

## Variable runtime VALUE = the App-Framework JS SDK `[DOC]`

From inside an embedded Pro Code app the current Variable value is read and set through the first-party ryuu.js SDK (the `domo-js` developer-portal reference = `[DOC]`). The current (v5/v6) surface:

- **Read:** `domo.onVariablesUpdated(callback)` — push subscription; the callback receives `Variable[]`; the call returns an unsubscribe function. There is **no synchronous `getVariable()`** in the reached docs or the vendored build (scope that negative to the build — cross-version it is `[INFER]`).
- **Set:** `domo.requestVariablesUpdate(variables, onAck?, onReply?)` → returns a request id.
- **Object shape:** `{name, value, functionId?}` (v6). Page variables are transported over `postMessage` / `MessageChannel`; native bridges are `webkit.messageHandlers.domovariable` (iOS) and `window.domovariable` (Android). `[DOC]`.

**This repo's vendored ryuu.js is the older v4.x build** (see version section). It uses `sendVariables(e)` (posts `{event:'variables', variables:e}` to `window.parent`) and an `onVariablesUpdated` that listens for a `'variablesUpdated'` message; it has **no `requestVariablesUpdate`**. `[REPO]`. The rename `sendVariables → requestVariablesUpdate` is a `[DOC]`-via-search-index sub-point with no repo corroboration — re-verify per instance/SDK version.

⚠ Two honest limits: obtaining a `variableId` is reportedly non-obvious / not surfaced in Analyzer (community, `[INFER]`); and that a Pro Code app **writing** a Variable then re-drives sibling **standard** cards is **plausible-by-model, not proven** — no repo consumer exercises it, and the `requestVariablesUpdate` payload shape is unconfirmed (`[INFER]`).

## The programmatic filter OBJECT `[DOC]`

The Domo Everywhere embed programmatic-filter object (owned by `domo-everywhere.md`, but its **complete operator enum** is pinned here as this surface's net-new contribution) — confirmed against the reached docs-portal page *and* two official `domoinc` sample repos, so `[DOC]`:

- **Shape:** `{column, operator, values}` plus optional `datasourceId`. The key is **`operator`** (not `operand`), and the value key is **`values`** (an array).
- **Complete operator enum (8), verbatim spellings — keep the typos:**
  `IN`, `NOT_IN`, `EQUALS`, `NOT_EQUALS`, `GREATER_THAN`, `GREAT_THAN_EQUALS_TO`, `LESS_THAN`, `LESS_THAN_EQUALS_TO`. **`BETWEEN` is absent.** The source states this is the complete list — treat the 8 as the **currently-documented** set (a point-in-time first-party statement), not a permanent guarantee.
- **`datasourceId` semantics:** omit it → the filter applies to **all** datasets on the page; supply it → only cards backed by that datasource are filtered. This is distinct from the token body's top-level `sqlFilters.datasourceIds`.
- **Size ceiling:** a large `IN` list can overflow the browser's ~8 KB JWT cap on the embed token (the source says "around 8kb" — approximate, not a portable numeric guarantee); mitigate by pre-aggregating the values into a new upstream column.

Adjacent, lower-tier: the in-app proxy card-data query exposes a `filter` query-string operator on `GET /data/v1/{alias}`, and `EMBED_TYPE` accepts `dashboard`/`card` (both corroborated) — but **`page` is `[INFER]`** (single sample-README, uncorroborated in the canonical docs). The Magic ETL Filter tile uses a *separate* short-code vocabulary (`EQ`,`NE`,`LT`,`GT`,`LE`,`GE`,`IN`,`NIN`,`NN`,`NL`) — `[INFER]`, community/internal, owned by `domo-magic-etl.md`.

## In-iframe filter propagation via the ryuu SDK `[REPO]`/`[DOC]`

Inside an embedded app, the dashboard filter is read and pushed through the ryuu SDK — not any REST call. The mechanism is fully corroborated by this repo's vendored `domo.js` (so the behavior is `[REPO]`-solid; the `domo-js` docs page corroborates method existence at `[DOC]`):

- **`domo.filterContent(dataset, filters)` does NOT exist.** The real push method is **`filterContainer(filters)`** — it takes only a filter array (no dataset argument). `filterContent` appears **0 times** in the entire repo; it is a misnomer. Each filter is `{column, operator/operand, values, dataType}`; `filterContainer` posts `{event:'filter', filter:[{columnName, operator, values, dataType}]}` to `window.parent`.
- **Reading is push-only.** `domo.onFiltersUpdate(callback)` is a subscription returning an unsubscribe function; there is **no synchronous `getFilters()`/`setFilters()`** in the vendored v4.x build (grep-exhaustive for *this build*; cross-version that negative is `[INFER]` — v5/v6 add namespaces that were never grepped). The callback delivers objects whose `column` and `values` are repo-confirmed; extra keys (`dataSourceId`, `label`, `operand`, `dataType`) are "per docs," not guaranteed at runtime.
- **You cannot query the current filter value directly.** There is no auto-translation of a received filter into a `domo.get`/`domo.post` — a consumer must hand-build a translation layer, and a default filter change triggers a **full refresh** unless handled (the "must build a translation layer" necessity is a community answer, `[INFER]`; the refresh-on-change is `[DOC]`).
- **All of this messaging is tokenless.** `filterContainer`/`onFiltersUpdate`/`onVariablesUpdated`/`sendVariables`/`sendAppData`/`onAppData`/`navigate` ride pure `window.parent.postMessage` + `MessageChannel` (port2 transferred on subscribe) — no token, header, or credential. Only the *data* calls (`domo.get`/`domo.post`) attach the platform-injected `window.__RYUU_SID__` as the `X-DOMO-Ryuu-Session` header (+ a `ryuu_sid` query param appended to same-origin `href`/`src` via a MutationObserver) against a same-origin proxy. (That the *platform* sets `__RYUU_SID__` and the proxy topology are `[INFER]` — the grepped SDK only *reads* it.)

## Cross-card / cross-page propagation in App Studio `[KB]`

How filters, dates, and Variables reach *standard* cards on an App Studio page is documented **product/UI behavior** (`[KB]`), not a REST contract:

- **Page filters** apply to cards powered by the **same DataSet** (and carrying the filtered column); cards on other datasets are untouched.
- A card can be **exempted** via the **"Filter Exceptions"** tab, with three toggles: *Allow filtering*, *Allow global date*, *Allow segments* (`[KB]`). These map — by plausible correspondence, **`[INFER]`, not a verified wire identity** — to this repo's `acceptFilters` / `acceptDateFilter` / `acceptSegments` layout flags. The UI toggles (KB) and the boolean flags (`[REPO]`) each exist independently; nothing documents that the flag name *is* the wire form of the toggle label.
- A filter selection does **not** persist across App Studio pages by default; cross-page persistence is explicit opt-in ("Configure Persistent Filters").
- **A Variable propagates to cards ONLY through Beast Mode.** Changing the default in the Beast Mode Editor updates every Beast Mode instance-wide that uses it; runtime propagation is governed by the **Variable Control scope** (Dashboard/Page vs Card control), and scopes do not leak into each other.
- **Embedded App Studio apps:** `overrideFilters=true` makes the app ignore its saved default filters and wait for the parent to send filter state via the `/v1/filters/apply` event; `overrideFilters=false` loads saved defaults (`[DOC]`, reached docs-portal page). That page does **not** document pushing Variables to embedded apps.

## ryuu.js version divergence — v4.x legacy vs v5/v6

The SDK renamed its filter/variable methods between the build this repo vendors and the current one. This matters because the **names you grep in the repo are not the names in today's docs**:

| Concern | Vendored **v4.x** (this repo) | Current **v5/v6** (docs) |
|---|---|---|
| Read filters | `onFiltersUpdate` | `onFiltersUpdated` |
| Push filters | `filterContainer` | `requestFiltersUpdate` |
| Read variables | `onVariablesUpdated` | `onVariablesUpdated` |
| Set variables | `sendVariables` | `requestVariablesUpdate` |
| Namespaces | (none) | adds `domo.data` / `appdb` / `ai` / `workflow` |

- The repo-side divergence is `[REPO]`-confirmed (`onFiltersUpdated`, `requestFiltersUpdate`, `requestVariablesUpdate`, `domo.data` all appear **0** times in the vendored build). The v5/v6 names come from search-index-extracted docs pages (the direct `developer.domo.com` fetches 405'd) — `[DOC]` for existence, **re-verify per instance/version**.
- **v5/v6 gotcha (`[DOC]`, unverified against this v4.x repo):** on first registration, `onFiltersUpdated` fires `requestFiltersUpdate(null)`, which **clears all parent filters**. Use `onDataUpdated` instead where you only want to observe. This does not apply to the vendored v4.x `onFiltersUpdate`.
- Do **not** claim "old names kept as aliases" (not in the cited evidence — `[INFER]`), and do **not** cite the npm `ryuu` **CLI** at v5.1.0 as the SDK/library version — the library is `ryuu.js` (this repo pins **4.6.0** where pinned); they are different packages.

## Repo precedent `[REPO]`

In THIS repo, dashboard Variables & filters are a **near-dormant** capability — the SDK ships the symbols, but almost nothing consumes them. Every statement here is `[REPO]`-scoped (grep the token, not the line — the wire names below are v4.x-build-specific):

- **The vendored SDK is a single build.** All 11 vendored `domo.js` files are **byte-identical** (`md5 77b232e54712c0bcb9aaa630bfddb91f`, 44,218 bytes each). The bundle contains `filterContainer`, `sendVariables`, `onFiltersUpdate`, `onVariablesUpdated`, and a listener registry `{onFiltersUpdate:[], onAppData:[], onVariablesUpdated:[]}`. Symbol *presence* is `[REPO]`; that these drive a live Domo bridge end-to-end is untested here (`[INFER]`).
- **`filterContent` = 0 occurrences repo-wide** — the real method is `filterContainer`.
- **Exactly ONE non-vendor consumer** of any of these: the doc-summary app calls `domo.onFiltersUpdate`. **Zero** non-vendor calls to `filterContainer` / `sendVariables` / `onVariablesUpdated` / `onAppData`.
- That one consumer uses the filter **client-side** — it maps `filter.column`/`values` into local state to drive a FileSet/RAG query — **not** as a server-side `/data/v1` data filter.
- **No `/data/v1` dataset call is filtered:** every non-vendor `/data/v1/{alias}` read uses projection/pagination params only (`fields=` / `limit=` / `offset=` / `useBeastMode=true`). Scope this negative to `/data/v1` — the doc-summary app *does* do filter-driven server-side querying, just against the FileSet/RAG API.
- **No `manifest.json` declares `variables`/`variablesMapping`** — no app-manifest Variable-binding precedent.
- **False friend:** the workflow `*.json` files with `"type":"variable"` are **workflow-local variable operands** nested in `designElements[…].advancedRule` — **not** dashboard Variables. They belong to `domo-workflow.md`; there is no top-level `variables` key and no `domo-variables.md` predecessor.

Anything beyond "the SDK ships the methods + one app subscribes to `onFiltersUpdate` client-side" is not backed by working repo code (`[INFER]`).

## Do NOT claim as documented fact

1. **"There is no Variables REST API."** `[INFER]`, not fact — absence from a non-exhaustive `llms.txt` catalog + a repo grep-absence; undocumented variable REST routes *do* exist. Say "no `variables.yaml` in the catalog reached."
2. **"There is no create/delete endpoint / no runtime-value endpoint for a Variable."** `[INFER]` — absence within a single spec. Say "not present in `beastmodes.yaml`," never "no such endpoint exists anywhere."
3. **"The runtime value is read/set ONLY via the App-Framework SDK."** Drop the "only" — it is the *documented* path; a universal negative here is `[INFER]`.
4. **The 8-operator embed enum is a permanent list.** It is the **currently-documented** set (a point-in-time first-party "complete" statement); do not promise Domo will never add one. `BETWEEN`'s absence is safe only as that point-in-time statement.
5. **The `operator`/`operand` split and iOS `column` vs desktop `columnName` wire keys are a portable contract.** They are **one minified v4.x SDK build's implementation detail** (`[REPO]`, SDK-version-specific).
6. **v5/v6 SDK specifics** (the renames, the object shapes, the first-registration filter-clear gotcha, `requestVariablesUpdate`) are verified against this repo. They are **search-index-sourced `[DOC]`** (direct fetches 405'd), zero repo corroboration (repo is v4.x) — re-verify per version.
7. **"Filter Exceptions" UI toggles ARE the `acceptFilters`/`acceptDateFilter`/`acceptSegments` flags.** An `[INFER]` correspondence — the toggles (`[KB]`) and the flags (`[REPO]`) each exist, but the identity is undocumented.
8. **SQL `WHERE` / PDP / embed-token filter body shapes are newly-documented DOC.** No — those contracts are owned and **hedged** by `domo-datasets.md` / `domo-everywhere.md`; only the specs' *existence* is `[DOC]` via the catalog. This pass verified them at `[REPO]`.
9. **"Manifest env variables" don't exist as a feature.** `[INFER]` (the CLI docs page failed to load); state it as "not documented in the page reached + not present in this repo's manifests," not as a contract. (And that repo manifests carry *only* an 11-key list is false — they also carry `accountsMapping`, `actionsMapping`, `aiContextId`, `databasesMapping`, `draft`, `flags`, `publicAssetsEnabled`, `scopes`, `description`, `fullpage`; the load-bearing point is just that no `env`/`variables` key exists.)
10. **A Pro Code app writing a Variable re-drives sibling standard cards.** `[INFER]` — plausible-by-model, no repo consumer proves it, payload shape unconfirmed.
11. **`notvariable` excludes variable-type functions.** The `filters` param existence is real; the *effect* of `notvariable` is `[INFER]`.
12. **DomoStats connectors give variable-usage telemetry.** Plausible (a KB `#domostats_reports` section exists) but unverified this pass — present as unconfirmed, drop the marketing "all the data you need."

## Safety & hygiene

- **The developer token (`X-DOMO-Developer-Token`) and any embed token/JWT are secrets** — server-side only. Never write them into front-end code, handoffs, or commits. The in-iframe SDK messaging is *tokenless* by design (postMessage/MessageChannel); the session id `__RYUU_SID__` is platform-injected, never something you hard-code.
- **A public embed carries no PDP and no secure filter.** A client-side Pfilter (`operand`) is **cosmetic, not security** — a viewer can read and change it. Never rely on it to hide rows; row security is PDP (`domo-datasets.md`), which requires an identified viewer.
- **`operator` (server body) vs `operand` (client)** — copying one into the other's slot fails **silently**. Verify which side you are on before shipping a filter payload.
- **Grep the token, not the line.** The repo's ryuu wire names are a **v4.x** build; today's instance may run v5/v6 with different method names and the first-registration filter-clear gotcha. Re-verify the SDK version before relying on a method name.

## Companion skills

- `domo-beast-mode.md` — owns the `functions` API where a Variable's **definition** lives (the `variable:boolean` flag; search/read/lock/update-expression; the `notvariable` search filter).
- `domo-everywhere.md` — owns the embed-token filter body and the client Pfilter; the `operator` enum pinned above complements it.
- `domo-datasets.md` — owns the DataSet SQL `WHERE` and PDP row-policy filters.
- `domo-appstudio.md` — owns the App-Studio Variable-control bind endpoint and the layout `acceptFilters`/`acceptDateFilter`/`acceptSegments` flags.
- `domo-procode-embedded-cards.md` — owns Pro Code ↔ standard-card coordination on one page (the 4-channel table; asymmetric propagation).
- `domo-procode-app.md` — owns `manifest.json` (the "manifest env variable" misnomer).
- `domo-workflow.md` — owns Workflow variables (`"type":"variable"` in workflow JSON), an unrelated namespace.
