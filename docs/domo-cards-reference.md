# Domo Standard Cards — Chart Type Reference

Companion to the [`domo-cards.md`](../skills/domo-cards.md) skill: a family catalog of
standard (`cardType: "kpi"`) chart variants, with an explicit evidence tier on every load-bearing
claim. Read the skill first for the CRUD API and the authoring recipe; use this doc when you need to
know whether a given chart exists and which family it belongs to.

## Evidence tiers (what to trust)

- **[LIVE]** — retrieved from real cards; 2026-10-17 coverage is definition reads, not save/render testing.
- **[ENUM]** — from Domo's charting-engine enum `domo-phoenix` `CHART_TYPE` (versioned snapshot) and Domo KB
  "Chart Types" articles. Reliable for *names*, but a picker entry ≠ a distinct chart.
- **[DOC]** — from Domo product/developer documentation.
- **[INFER]** — reasoned inference, not independently confirmed; flagged so it is not mistaken for fact.

## Observed chart codes and required mappings

The 2026-10-17 study retrieved 154 unique KPI definitions across five supplied dashboards,
covering **71 chart codes**. This is observed coverage, not the total number Domo supports.
Picker variants include orientations, region maps and rendering styles; select a family and
then the exact variant without relying on a fixed platform-wide count.

Names and required slots below come from the public Phoenix documentation [DOC]; counts come
from full live definitions [LIVE]. Code-derived names are identified, and the UI label of
`badge_table` remains unverified. Optional mappings, maxima, property keys/value lists and
dependencies are in the [configuration guide](domo-cards-configuration.md) and
[queryable catalog](reference/domo-card-config-catalog.json). Read-time evidence is not save/render evidence.
The required mappings describe Phoenix inputs; actual Analyzer subscription roles may differ.
Preserve a valid template projection rather than enforcing this table as a save validator.

| Exact chart code | Name | Cards | Required mappings [DOC] |
|---|---|---:|---|
| `badge_basic_table` | Mega Table | 1 | VALUE |
| `badge_bubble` | Bubble (legacy) | 1 | XTIME, VALUE, SERIES |
| `badge_bullet` | Bullet | 1 | ITEM, VALUE |
| `badge_calendar` | Calendar | 2 | DATE, EVENT |
| `badge_checkbox_selector` | Checkbox selector | 2 | ITEM |
| `badge_curved_symbolline` | Curved symbol line | 2 | ITEM, VALUE |
| `badge_curvedline` | Curved line | 3 | ITEM, VALUE |
| `badge_donut` | Donut | 2 | ITEM, VALUE |
| `badge_dropdown_selector` | Dropdown selector (code-derived label) | 1 | ITEM |
| `badge_facegauge` | Face | 1 | VALUE |
| `badge_filledgauge` | Filled | 4 | CURRENT |
| `badge_funnel` | Funnel | 1 | ITEM, VALUE |
| `badge_funnel_bars` | Funnel bars | 1 | ITEM, VALUE |
| `badge_funnel_swing` | Folded funnel | 1 | ITEM, VALUE |
| `badge_gantt` | Gantt | 3 | ITEM, START_DATE, END_DATE |
| `badge_gauge` | Radial | 1 | VALUE |
| `badge_heatmap` | Heat map | 4 | ITEM, VALUE, SERIES |
| `badge_heatmap_table` | Heatmap table (code-derived label) | 1 | VALUE |
| `badge_highlow` | High low | 2 | CATEGORY, HIGH, LOW |
| `badge_horiz_100pct` | 100% Stacked bar (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_bar` | Bar (Horizontal) | 7 | ITEM, VALUE |
| `badge_horiz_boxplot` | Box plot (Horizontal) | 1 | ITEM, VALUE |
| `badge_horiz_dual_stackedbar` | Grouped and stacked (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_line_clusterbar` | Line + grouped and stacked (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_line_stackedbar` | Line + stacked bar (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_multibar` | Grouped bar (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_nestedbar` | Nested bar (Horizontal) | 1 | ITEM, VALUE, SERIES |
| `badge_horiz_percentbar` | Percent of total (Horizontal) | 1 | ITEM, VALUE |
| `badge_horiz_stackedbar` | Stacked bar (Horizontal) | 4 | ITEM, VALUE |
| `badge_line_bar` | Line + grouped bar | 6 | ITEM, VALUE, SERIES |
| `badge_line_clusterbar` | Line + grouped and stacked | 1 | ITEM, VALUE, SERIES |
| `badge_line_stackedbar` | Line + stacked bar | 1 | ITEM, VALUE, SERIES |
| `badge_map` | Map United States | 1 | ITEM, VALUE |
| `badge_map_australia` | Map Australia | 1 | ITEM, VALUE |
| `badge_map_canada` | Map Canada | 1 | ITEM, VALUE |
| `badge_map_japan` | Map Japan | 2 | ITEM, VALUE |
| `badge_multi_value` | Multi-value | 7 | VALUE |
| `badge_pareto` | Pareto | 1 | ITEM, VALUE |
| `badge_pie` | Pie | 4 | ITEM, VALUE |
| `badge_pivot_table` | Pivot table | 1 | VALUE |
| `badge_radar` | Radar | 1 | ITEM, VALUE, SERIES |
| `badge_rttrendline` | Running total line | 5 | ITEM, VALUE |
| `badge_singlevalue` | Single value | 3 | VALUE |
| `badge_slicer` | Slicer | 1 | ITEM |
| `badge_stackedtrend` | Stacked area | 1 | ITEM, VALUE, SERIES |
| `badge_stepline` | Step line | 1 | ITEM, VALUE |
| `badge_symbol_bar` | Symbol + grouped bar | 1 | ITEM, VALUE, SERIES |
| `badge_symbol_stackedbar` | Symbol + stacked bar | 1 | ITEM, VALUE, SERIES |
| `badge_symbolline` | Symbol line | 2 | ITEM, VALUE |
| `badge_table` | Table (legacy code; UI label unverified) | 9 | VALUE |
| `badge_textbox` | Textbox | 1 | ITEM |
| `badge_treemap` | Treemap | 3 | ITEM, VALUE |
| `badge_trendline` | Line | 3 | ITEM, VALUE |
| `badge_two_trendline` | Multi-line | 6 | ITEM, VALUE |
| `badge_vert_100pct` | 100% Stacked bar | 1 | ITEM, VALUE, SERIES |
| `badge_vert_bar` | Bar | 5 | ITEM, VALUE |
| `badge_vert_boxplot` | Box plot | 3 | ITEM, VALUE |
| `badge_vert_bullet` | Bullet (Vertical) | 1 | ITEM, VALUE |
| `badge_vert_dual_stackedbar` | Grouped and stacked | 1 | ITEM, VALUE, SERIES |
| `badge_vert_multibar` | Grouped bar | 1 | ITEM, VALUE, SERIES |
| `badge_vert_nestedbar` | Nested bar | 1 | ITEM, VALUE, SERIES |
| `badge_vert_percentbar` | Percent of total | 1 | ITEM, VALUE |
| `badge_vert_rtbar` | Running total bar | 1 | ITEM, VALUE |
| `badge_vert_rtmultibar` | Running total grouped bar | 1 | ITEM, VALUE, SERIES |
| `badge_vert_rtstackedbar` | Running total stacked bar | 1 | ITEM, VALUE, SERIES |
| `badge_vert_stackedbar` | Stacked bar | 5 | ITEM, VALUE |
| `badge_word_cloud` | Word cloud | 5 | ITEM, VALUE |
| `badge_world_map` | Map World | 3 | ITEM, VALUE |
| `badge_xy_line` | XY line | 1 | XTIME, VALUE |
| `badge_xybubble` | Bubble | 3 | XTIME, VALUE |
| `badge_xyscatterplot` | Scatter plot (legacy) | 3 | XTIME, VALUE, SERIES |

## Family catalog [ENUM]

Vertical variants are listed; unless noted, **each has a Horizontal twin** (the `HORIZ_*` orientation
copy). "with Line / with Symbols / with Curved Line" are combo overlays on the base.

### Bar / Column
Bar, Grouped Bar, Grouped Bar with Line, Line with Grouped Bar, Grouped Bar with Curved Line, Grouped
Bar with Symbols, Stacked Bar, Stacked Bar with Line, Stacked Bar with Curved Line, Stacked Bar with
Symbols, Nested Bar, Nested Bar with Line, 100% Stacked Bar, 100% Stacked Bar with Line, Percent of
Total, Marimekko, Pareto, Grouped and Stacked Bar, Grouped and Stacked Bar with Line, Bullet, Waterfall,
Running Total Bar, Running Total Grouped Bar, Running Total Stacked Bar, Overlay Bar, Histogram, Funnel
Bars, Spark Bar. (3-Metric Bar appears in a KB index [INFER].)

### Line
Line, Symbol Line, Curved Line, Curved Symbol Line, Step Line, Multi-line, Running Total Line, plus
Vertical Line / Vertical Curved Line / Vertical Step Line / Vertical Symbol Line / Vertical Curved Symbol
Line, Spark Line.

### Area
Area, Curved Area, Step Area, Stacked Area, Curved Stacked Area, Step Stacked Area, 100% Stacked Area,
Curved 100% Stacked Area, Step 100% Stacked Area (each vertical/horizontal), Stream, Area Overlay.

### Pie / Donut / Funnel
Pie, Donut, Nautilus, Nautilus Donut, Nightingale Rose, Funnel, Stream Funnel, Folded Funnel, Funnel
Bars, Tree Map.

### Table / Pivot
Mega Table, Pivot Table, Flex Table, HTML Table, Heatmap Table.

### Gauge / Single-Value
Single Value Gauge, Multi-Value Gauge, Comparative Gauge, Comparative Fill Gauge (Basic), Comparative
Fill Gauge (Advanced), Radial Gauge, Radial Progress Gauge, Multi Radial Progress Gauge, Filled Gauge,
Progress Bar Gauge, In Range Gauge, Face Gauge, Shape Gauge, Waffle Gauge, Image Chart.

### Map / Geo
Country Map, Continental/Regional Map, World Map, Latitude-Longitude Map, Latitude-Longitude Route Map,
U.S. County Map. (Picker inflated by ~37 preinstalled geographies.)

### Data Science
Scatter Plot (Bubble folded in), XY Line, Predictive Modeling, Forecasting, Outliers, Box Plot
(vertical/horizontal), SPC (Statistical Process Control), Correlation Matrix, Confusion Matrix.

### Lollipop
Grouped Lollipop, Stacked Lollipop, Grouped Lollipop with Line, Stacked Lollipop with Line (each
vertical/horizontal).

### Period-over-Period
Bar Line, Variance Bar Line, Line Bar, Variance Line Bar, Trendline, Variance Trendline, Grouped Bar,
Running Total Line, Multi-Value Gauge (PoP), Shape Gauge (PoP), Flex Table (PoP), Filled Gauge (PoP),
Progress Bar (PoP).

### Filter / Selector cards
Slicer, Checkbox, Radio Button, Range (Slider), Date Selector, Dropdown Selector. (Standard cards that
drive other cards on the page.)

### Miscellaneous
Radar, Word Cloud, Heat Map, Calendar, Gantt, Gantt Percent Complete, High-Low, Candlestick, Category
Scatter, Symbol (vertical/horizontal), Symbol Overlay (vertical/horizontal), Sankey.

## Not standard chart cards

- A standalone **Text/Note** object and **Document/uploaded file** have non-KPI card types.
  The separate `badge_textbox` is a KPI chart, observed in the study; do not conflate the two.
- **Pro Code / custom app** = `cardType: "domoapp"` — see [`domo-procode-embedded-cards.md`](../skills/domo-procode-embedded-cards.md).

## Known uncertainties

- Codes outside the 71 observed types require additional live examples. Public enum/property membership alone does not prove target-instance save compatibility.
- Whether each orientation/curve/step permutation is a truly separate picker entry vs. a property toggle
  is not always explicit in Domo docs; the KB lists them separately, so they are listed separately here.
- Niche picker entries (e.g. "3-Metric Bar", standalone "100 Percent Stacked Bar" articles) appear in KB
  indexes but could not all be cross-checked against a family table [INFER].
- Salesforce-hosted `domo-support.domo.com` pages are JS-rendered and were cross-checked against the
  static `www.domo.com/docs/s/article/*` mirror and search snippets, not scraped directly.

## Public Platform Cards API

[DOC] This is the distinct OAuth2 `clientCredentials` API on `api.domo.com` (`/oauth/token`,
empty declared `scopes {}`). Its `CardDefinition` schema is different from the internal instance
v3 definition. Historical community failures concern create requests; they do not establish that
all seven operations fail. None of these public operations was exercised by the dashboard study.

| Operation | Path | Documented shape / use |
|---|---|---|
| List | `GET /v1/cards` | `limit` default 35, `offset` default 0; `CardSummaryList{cards[], totalCardCount}` |
| Get | `GET /v1/cards/{cardUrn}` | `CardSummary` |
| Create | `POST /v1/cards/chart` | `CardDefinition` body/response; optional `pageId` query inserts into a dashboard |
| Read definition | `GET /v1/cards/chart/{cardUrn}` | `CardDefinition`; `chartBody` contains columns/aggregation, grouping, ordering, filters and pagination |
| Update definition | `PUT /v1/cards/chart/{cardUrn}` | Full `CardDefinition` body/response |
| Add drill view | `POST /v1/cards/chart/{cardUrn}/drill` | `CardDefinition` body |
| Read drill properties | `GET /v1/cards/chart/{cardUrn}/drillpath` | `DrillPathProperties{allowTableDrill, drillOrder[]}` |

`CardSummary` declares `cardTitle`, `cardUrn`, `lastModified`, `ownerId`, `ownerName`, `pages[]`,
and `type`. Do not infer extra list/search parameters or timestamp semantics from field names.
For authoring in this workspace, the reusable v3 template-definition recipe in the
[configuration guide](domo-cards-configuration.md) has repository precedent. Verify whichever
API/auth world the target actually supports; do not mix host, credential, or definition shapes.
