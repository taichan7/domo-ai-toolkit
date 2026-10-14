# Domo Standard Cards Skill

Use this when creating, editing, or reasoning about **standard Domo cards** (the built-in chart
types added from a Dataset — *not* Pro Code / custom apps). Companion background + full catalog:
[`../docs/domo-cards-reference.md`](../docs/domo-cards-reference.md). To put standard cards **inside a
Pro Code app / App Studio page**, see [`domo-procode-embedded-cards.md`](domo-procode-embedded-cards.md).

## What "standard card" means (verified live on maintenance-instance, 2026-09-05)

- Standard card = `cardType: "kpi"`. Its chart is chosen by `metadata.chartType`, always in the
  **`badge_*`** family. Four codes are confirmed live here (`badge_vert_bar` = Vertical Bar,
  `badge_pie` = Pie, `badge_singlevalue` = Single Value, `badge_basic_table` = a basic table). The full
  set of `badge_*` codes **is published** `[DOC]` — the open-source `domo-phoenix` `CHART_TYPE` enum
  (`src/enums/phoenix-chart-type.ts`, GitHub `DomoApps/domo-phoenix`) lists ~196 of them as its enum
  *values*. So look a code up in that enum rather than inventing one — but still confirm the exact code a
  given chart uses by reading it off a real card of that type (enum membership ≠ proof that a specific
  instance's card carries that exact code).
- `cardType: "domoapp"` = **Pro Code** custom app (out of scope for this skill).
  `cardType: "document"` = an uploaded file. Neither is a standard card.
- `metadata.chartVersion` is a per-chart schema version (seen: `6`, `12`, …). It matters: on modern
  cards (`chartVersion ≥ 12`) `metadata.inputTable` is **null** and the column→axis/series/aggregation
  config is **not** exposed through the content API — it lives in the internal Analyzer graph definition.

## How many chart types really exist (don't say "hundreds")

The "hundreds of card types" framing is an artifact of counting picker entries, not distinct charts.
Grounded numbers:

- **~196 selectable picker entries** — Domo's own charting-engine enum (`domo-phoenix` `CHART_TYPE`)
  has ~196 members. That is what the "Add a Chart" picker offers.
- **Domo markets "150+"** chart types `[DOC]` (domo.com visualizations-and-dashboards page).
- **A few dozen genuinely *distinct* chart types** (~40–70 depending on how strictly you split families).

The picker count is inflated by: **orientation twins** (~44 `HORIZ_*` horizontal copies — orientation is
a property, not a new chart), **preinstalled map geographies** (one map type × ~37 regions), and
**render-style variants** (curved / stepped / symbol / running-total flavors of the same base). Design
by choosing a *family* and a variant, not by memorizing 196 names.

## Chart type families (for selection)

Pick the family by the question the card answers; pick the variant for shape. Full per-variant lists are
in the companion reference. This is for *selection* — the exact per-chart config is authored through the
Analyzer / clone-and-retarget, not hand-written JSON.

| Family | Use for | Representative variants |
|---|---|---|
| **Bar / Column** | compare categories | vertical/horizontal, grouped, stacked, 100% stacked, waterfall, bullet, Pareto, Marimekko, histogram, running-total |
| **Line** | trend over time | line, curved, step, symbol, multi-line, running-total |
| **Area** | trend + magnitude | area, stacked, 100% stacked, curved, step, stream |
| **Combo (bar + line)** | two measures, different scales | grouped/stacked bar with line or symbols |
| **Pie / Donut** | part-to-whole (few slices) | pie, donut, Nightingale rose, nautilus |
| **Funnel** | stage drop-off | funnel, folded, stream funnel, funnel bars |
| **Treemap** | nested part-to-whole | treemap |
| **Table / Pivot** | detail + cross-tab | Mega Table, Pivot, Flex Table, HTML Table, Heatmap Table |
| **Single value / Gauge** | one KPI vs target | single-value, multi-value, radial, filled, progress-bar, comparative-fill, face, waffle, shape |
| **Map / Geo** | value by geography | country, world, regional, U.S. county, lat-long point/route |
| **Scatter / Bubble** | correlation of 2–3 measures | scatter, XY line, category scatter |
| **Data science** | stats / prediction | forecasting, predictive, outliers, box plot, SPC, correlation/confusion matrix |
| **Lollipop** | ranked categories | grouped/stacked, ± line |
| **Period-over-Period** | this period vs last | bar-line, variance, trendline (PoP flavors of the above) |
| **Filter / selector cards** | dashboard controls | slicer, checkbox, radio, range slider, date selector, dropdown |
| **Misc** | specialized | radar, word cloud, heat map, calendar, Gantt, candlestick, high-low, Sankey, symbol |

Exhaustive per-variant catalog + evidence tiers: [`../docs/domo-cards-reference.md`](../docs/domo-cards-reference.md).

Discover what actually exists on an instance (there is **no** chart-type catalog endpoint —
`/api/content/v1/cards/kpi/definitions`, `/kpi/types`, `/charttypes` all 404/405). Enumerate from live
data instead:

```bash
# POST /api/search/v1/query — page through cards, tally distinct standard chartTypes
curl -sS -X POST -H "X-Domo-Authentication: $SID" -H 'Content-Type: application/json' \
  -d '{"count":200,"offset":0,"query":"*","entityList":[["card"]]}' \
  "https://$INSTANCE/api/search/v1/query"
# each searchObject: cardType (keep "kpi") + chartType (the badge_*). Page offset by 200.
```

## Card CRUD API (verified live, `X-Domo-Authentication: <SID>`; no admin PAT needed)

| Op | Call | Result |
|---|---|---|
| **Read** | `GET /api/content/v1/cards?urns={id,id}&parts=metadata,datasources,conditionalFormats,slicers,drillPath,dateInfo` | `200` — array of card objects. |
| **Clone** | `POST /api/content/v1/cards/{id}/copy` body `{}` | `200` — **persists a NEW card owned by the caller**; returns the full new card. The reliable authoring primitive. |
| **Update** | `PUT /api/content/v1/cards/{id}` body `{"title":"…", …}` | `200` — partial merge (an empty `{}` body is a no-op). |
| **Delete** | `DELETE /api/content/v1/cards/{id}` | `200`; a subsequent read returns an empty array. |
| Raw create | `POST /api/content/v1/cards` | `400` without a correct body — the endpoint exists but the full-definition body is undocumented and version-brittle; **do not hand-roll it** (see Limitations). |

A card object's shape: top-level `id/urn/type/title/description/ownerId/creatorId/datasources[]`, plus a
`metadata` blob (`chartType`, `chartVersion`, `columnFormats`, `columnAliases`, `SummaryNumberFormat`,
`calendar`, `dynamicTitle/Description`). Read parts you don't need out, not in.

## Public Platform Cards API (`api.domo.com`, OAuth2 — 7 ops, experimental) `[DOC]`

Distinct from the internal content API above (different host, different auth). The **public** Platform Cards API
is **not create-only** — the dev-portal spec documents a **7-op** surface. Auth is OAuth2 `clientCredentials`
(`tokenUrl /oauth/token`, empty `scopes {}`). Treat the **whole** surface as **experimental**: the same
403/500/"Network Error" reliability caveat in Limitations applies to every op — probe per-instance before relying
on it. Types/shapes below; do **not** hand-build a `CardDefinition` (that invites the brittle authoring this skill
steers away from — see clone-and-retarget).

- **List** — `GET /v1/cards` (query `limit` default 35, `offset` default 0) → `CardSummaryList{cards[]:CardSummary, totalCardCount:int64}`; `CardSummary = {cardTitle, cardUrn, lastModified:int64, ownerId:int64, ownerName, pages:int64[], type}`. Overlaps the already-charted internal `POST /api/search/v1/query` enumeration.
- **Get** — `GET /v1/cards/{cardUrn}` → `CardSummary`.
- **Create** — `POST /v1/cards/chart` (body `CardDefinition` → `CardDefinition`); optional `pageId` (int64) query param inserts the new card into a Page/Dashboard.
- **Get definition** — `GET /v1/cards/chart/{cardUrn}` → the full `CardDefinition` whose `chartBody` is the column→axis/aggregation query model (a `Component`: `columns[]`/`groupBy`/`orderBy`/`filters`/`limit`/`offset`, columns carrying `aggregation`). This is the documented (**if experimental**) way to **READ** the equivalent of the graph the internal content API withholds as `inputTable: null` on `chartVersion ≥ 12` (nuances the top Limitation below).
- **Update definition** — `PUT /v1/cards/chart/{cardUrn}` (body `CardDefinition` → `CardDefinition`). Takes a full hand-constructed `CardDefinition`, so **clone-and-retarget** (internal `PUT /api/content/v1/cards/{id}`) stays the preferred edit path — not this.
- **Add drill view** — `POST /v1/cards/chart/{cardUrn}/drill` (body `CardDefinition`); also needs a hand-rolled `CardDefinition`.
- **Get drill properties** — `GET /v1/cards/chart/{cardUrn}/drillpath` → `DrillPathProperties{allowTableDrill:bool, drillOrder[]:string}`. Drill info is already reachable via the internal read op's `parts=…,drillPath`.

## Recommended authoring path: clone-and-retarget (round-trip verified 2026-09-05)

Building a card's chart definition from raw JSON is undocumented and brittle. The maintainable,
AI-friendly path is to **start from a known-good template card and mutate it**:

1. **Clone** a template card of the right `chartType` → `POST /api/content/v1/cards/{templateId}/copy`.
   You now own the copy.
2. **Retarget / edit** via `PUT /api/content/v1/cards/{newId}` — change `title`, formatting, and
   (where applicable) datasource. Deeper column/series edits are done in the **Analyzer UI**, which is
   the supported editor for the graph definition.
3. **Verify** by reading it back; **delete** disposable test cards when done.

Verified end-to-end on a self-owned card: clone → `PUT {"title":…}` (the read-back confirmed the title
actually changed) → delete → gone; the source card was untouched. Keep test cards named `zz-…` and
delete them.

## Picking the right chart

Match the *question* to the family (table above), then pick the variant for shape. Rules of thumb:

- **Trend over time →** Line (many points) or Area (magnitude matters). Don't use Pie for time.
- **Compare categories →** Bar/Column. Horizontal when labels are long; grouped for a second dimension,
  stacked for part-to-whole *within* each bar.
- **Part-to-whole →** Pie/Donut only for ≤5 slices; Treemap or 100%-stacked Bar for more.
- **One KPI vs a target →** Single value / Gauge. Add a comparison (PoP) instead of a second card when
  the point is "vs last period."
- **Detail / cross-tab →** Table / Pivot. Reach for a chart only when a shape reveals more than numbers.
- **Correlation →** Scatter (2 measures) or Bubble (3). **By geography →** a Map family.
- **Dashboard controls →** selector cards (slicer/dropdown/date) drive other cards on the page; they are
  standard cards too.

## Authoring paths, ranked for a headless agent

| Path | Reliable headless? | Notes |
|---|---|---|
| **Clone a golden template + retarget** (`POST …/copy` then `PUT`) | **Yes — recommended** | Inherits a correct modern-card graph you can't hand-write. Cleanest when the clone reuses the template's dataset. |
| Analyzer UI | No (not headless) | The canonical human path and the *source of truth* for a modern card's graph. Build your golden templates here. |
| Public Platform Cards API `POST /v1/cards/chart` (OAuth2, api.domo.com) | Experimental | **Documented** from-scratch path with a `CardDefinition` (chartType, dataSetId, `columns[]` with axis/series mapping + aggregation). But 2025 community reports show 403/500/"Network Error" against the documented sample — verify per-instance before relying on it. |
| pydomo SDK | N/A | Has **no** cards module (datasets/streams/pages/users only). |
| `ryuu` / `domo publish` CLI | Yes, but wrong object | Creates **Pro Code** (`domoapp`) cards, not standard KPI cards. |

**Beast Mode** (CASE/aggregation calculated fields) is a *component* of a card, not a create method —
generate the formula text with AI, but wire it in via the Analyzer or a cloned template.

## Limitations (be honest about these)

- **The *internal* content API does not expose a modern card's chart definition.** For
  `chartVersion ≥ 12`, `/api/content/v1/cards` (SID auth) returns `metadata.inputTable: null` and no
  writable column→axis/series/aggregation config — that graph lives in the internal Analyzer definition.
  This is why clone-and-retarget (not raw create against this API) is the reliable path. (The **public**
  `GET /v1/cards/chart/{cardUrn}` op is the documented — *if experimental* — way to READ the equivalent
  graph as a `CardDefinition.chartBody`; see the Public Platform Cards API section.)
- **A documented *public* from-scratch API does exist, but is unreliable in practice.** The Platform
  Cards API `POST /v1/cards/chart` (OAuth2, api.domo.com) defines a `CardDefinition` with column
  mapping + aggregation — so "there is no documented way" is *false*. However, multiple 2025 community
  reports show it returning 403/500/"Network Error" against Domo's own sample body. Treat it as
  documented-but-experimental: probe it on the target instance before designing around it.
- `POST /api/query/v1/execute/{cardId}` is the data-query/render pipeline (`400` without a body); it is
  for *reading* card data, not authoring the chart. `PUT /api/content/v1/cards/kpi/{urn}/render` is a
  documented endpoint but returns a **static image** (needs a developer token), not a live card.
- There is no chart-type *catalog* endpoint — enumerate from live cards, the family table above, or the
  `domo-phoenix` `CHART_TYPE` enum.

## Safety (shared instances such as `maintenance-instance`)

- Create only clearly-named disposable cards you own (`zz-…-verify-*`) and delete them when done.
- **Never** modify, delete, or inventory a card you did not create. `POST …/copy` makes you the owner of
  the *copy* only — the source is unchanged; still don't clone others' cards except as a throwaway you
  immediately delete.
- Never commit the SID, developer tokens, or raw card exports. Treat live card content as sensitive
  (real cards carry customer column names) — summarize, don't paste into commits/handoffs.
