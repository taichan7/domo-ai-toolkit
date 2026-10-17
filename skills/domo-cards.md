---
name: domo-cards
description: Analyze, select, create, or configure native Domo standard cards from real definitions, and choose native cards versus Pro Code when building apps or dashboards.
---

# Domo Standard Cards

Use native cards for requirements they can satisfy. Deliver a Domo app as an App Studio container
with standard KPI cards, adding Pro Code for demonstrated gaps such as transactional write-back,
custom interactions, or unsupported diagrams. Native cards are separate Domo objects, not resources
inside a Pro Code `manifest.json`; a Phoenix chart drawn by custom JavaScript is still Pro Code.

## Read only what the task needs

| Task | Resource |
|---|---|
| Pick a chart family or find a native alternative | [Chart reference](../docs/domo-cards-reference.md) |
| Inspect a dashboard, map columns, configure properties, create/update from a template | [Configuration and authoring guide](../docs/domo-cards-configuration.md) |
| Find exact required/optional mappings, property values and dependencies | Query [the offline catalog](../docs/reference/domo-card-config-catalog.json) using `domo-card-tools.py` below |
| Place native cards and Pro Code together; filters, SDK and embedding | [Native cards plus Pro Code](domo-procode-embedded-cards.md) and [App Studio](domo-appstudio.md) |
| Cross-instance creation/migration | [Native KPI clone recipe](domo-cross-instance-clone.md#section-11--native-kpi-cards) |
| Calculated fields or host Variables/filters | [Beast Modes](domo-beast-mode.md) / [Variables and filters](domo-variables-filters.md) |

## Requirement to working card

1. State the analytic question, dimensions/measures, aggregation, date grain/range, target units,
   and required interactions. Check real dataset/formula types. Choose the native family first.
2. Find the closest **exact chart code and binding shape** in the catalog and actual template
   definitions. Inspect the supplied pages/cards rather than inventorying unrelated instance assets.
3. Read the template's full v3 definition. Record main projections/roles, formulas, filters,
   grouping/order, date configuration, summary subscription, overrides, controls, and drill behavior.
4. Reuse/copy a known graph. For deeper edits/new cards, follow the v3 read→write transformations in
   the guide; map all references explicitly. A metadata title update alone does not retarget a graph.
5. Re-read the resulting target card, verify bindings and edited settings, then validate data,
   rendering and host interactions through the authorized verification workflow. State what was
   verified: retrieval, save, data correctness and visual behavior are separate evidence levels.
6. Put the result on the app's page and verify layout/content registration. Use Pro Code only for
   the remaining requirement. Lack of an example does not establish a native-card limitation.

## Discovery and exact configuration

```bash
# Offline, no authentication: inspect one family/property at a time.
python3 scripts/domo-card-tools.py catalog --search gauge
python3 scripts/domo-card-tools.py catalog badge_line_bar --property format
python3 scripts/domo-card-tools.py catalog badge_pivot_table --property subtotal

# Authenticated read-only inspection; INSTANCE and DOMO_TOKEN or SID must be exported.
python3 scripts/domo-card-tools.py inspect --page https://example.domo.com/page/123
python3 scripts/domo-card-tools.py inspect --card 456
```

Repeat `--page` / `--card` for a supplied set. The tool skips non-KPI cards, deduplicates IDs and
reports retrieval failures. It omits source titles, column names, formulas, values and annotations;
its structural report is not a write body. Read the guide for authentication/full-body retrieval.

The 2026-10-17 study read **154 cards / 71 chart codes / 110 configured property keys**. The catalog
also contains public Phoenix mapping/property metadata: **820 distinct property keys**, including
types, value lists, prerequisites, feature flags and per-chart variations. Distinguish [LIVE] stored
settings from [DOC] possibilities. No save/render test was performed in that study.

## The configuration traps that matter

- Standard charts normally have `type/cardType: "kpi"` and a `badge_*` chart code. `domoapp` and
  `document` are different card types. A separate `Text` card is different from the KPI chart
  `badge_textbox`. `badge_basic_table` is Mega Table [DOC]; do not equate it with every table code.
- **Modern definitions are readable.** V1 metadata may show `inputTable:null`, but
  `PUT /api/content/v3/cards/kpi/definition` with `{dynamicText:true,variables:true,urn:"<id>"}`
  retrieves `definition.subscriptions` and `definition.charts`. All 154 retrieved definitions had
  chartVersion 12 and `inputTable:false`. Null/false does not mean the bindings are unavailable.
- Presentation lives in `definition.charts.main.overrides`; data roles and aggregation live in
  `definition.subscriptions.main.columns[]`. Query filters/order/grouping/dates, conditional formats,
  card controls, and page filters/Variables are separate layers. Do not rewrite one as another.
- Do not force ITEM/VALUE onto every chart: filled gauges use CURRENT; modern bubbles use XTIME for
  X and BUBBLESIZE for size; Gantt needs START_DATE/END_DATE; calendar needs DATE/EVENT; pivot uses
  ROW/COLUMN/VALUE. The catalog gives per-code required slots and maxima.
  Those documented slots describe Phoenix input; Analyzer projections can differ (the observed
  `badge_line_bar` templates use numeric SERIES columns without VALUE). Preserve the real graph.
- Stored overrides were strings, including `"true"`, `"false"` and numbers. Preserve representation,
  casing, dependencies and missing/default distinctions. `overrides:null` means defaults, not lack
  of configurable properties. A setting's schema/value list can differ between chart codes.
- Source formula lists may contain unused dataset formulas; inspect actual `formulaId` references
  and transitive Beast Mode dependencies. Never leave a reference without a definition/resolution.
- Do not invent a summary subscription: preserve a template with `main` only when it has no
  `big_number`. Where present, the summary query can differ from the plotted query.

## Instance API operations

These are internal instance routes [REPO/LIVE], with SID verified in the earlier CRUD work and full
definition reads verified in the 2026-10-17 study. Follow the current repository's authorization for
writes; endpoint existence does not authorize changing a supplied source dashboard.

| Purpose | Operation | Evidence / caveat |
|---|---|---|
| Supplied page inventory | `GET /api/content/v1/pages/{pageId}/cards` | [LIVE] list; includes non-KPI objects |
| Metadata | `GET /api/content/v1/cards?urns={ids}&parts=metadata,datasources,conditionalFormats,slicers,drillPath,dateInfo` | [REPO] lightweight properties, not the full graph |
| Full definition **read** | `PUT /api/content/v3/cards/kpi/definition` | [LIVE] body `{dynamicText:true,variables:true,urn:"<id>"}`; retrieves without saving |
| Independent copy | `POST /api/content/v1/cards/{id}/copy` with `{}` | [REPO] creates a new card; source remains unchanged |
| Simple metadata update | `PUT /api/content/v1/cards/{id}` | [REPO] title partial-merge verified; not proof of arbitrary graph retargeting |
| New native KPI on a page | `PUT /api/content/v3/cards/kpi?pageId={pageId}` | [REPO] full transformed definition, not the raw read response |
| Update a native KPI | `PUT /api/content/v3/cards/kpi/{urn}` | [REPO] read target first; preserve modification/identity fields |
| Delete a disposable copy | `DELETE /api/content/v1/cards/{id}` | [REPO] source selection/authorization must be explicit |

The [authoring guide](../docs/domo-cards-configuration.md#authoring-reuse-a-graph-then-verify-the-saved-result)
explains formula/conditional-format wrappers, read-only fields, dataProvider, and preservation
requirements. Reuse that procedure instead of constructing a new graph from guessed JSON.

## Public API and boundaries

The distinct OAuth API on `api.domo.com` documents **seven Cards operations**, including read/create/
update definitions and drill operations; see [the public API reference](../docs/domo-cards-reference.md#public-platform-cards-api).
Its `CardDefinition` is not the v3 instance definition shape. Historical create failures do not prove
every public operation fails; verify the selected operation on the target before depending on it.
`domo publish` creates Pro Code cards, not native KPI cards. A render-image endpoint provides a
snapshot, not a live embedded card; use [the image skill](domo-get-kpi-card-image.md) for that surface.

Do not infer universal endpoint absence from a few 404s. No chart-catalog route is established by
this study; use primary enum/property documentation and supplied card definitions. Keep credentials,
raw definitions, source IDs, customer labels and annotation content out of public skill artifacts.
Analyze authorized sources without modifying them; use a separate owned target when authoring.
