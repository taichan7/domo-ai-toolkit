# Domo Standard Cards — Chart Type Reference

Exhaustive companion to the [`domo-cards.md`](../skills/domo-cards.md) skill: the full family catalog of
standard (`cardType: "kpi"`) chart variants, with an explicit evidence tier on every load-bearing
claim. Read the skill first for the CRUD API and the authoring recipe; use this doc when you need to
know whether a given chart exists and which family it belongs to.

## Evidence tiers (what to trust)

- **[LIVE]** — verified on a real instance (maintenance-instance, 2026-09-05) via the card CRUD API.
- **[ENUM]** — from Domo's charting-engine enum `domo-phoenix` `CHART_TYPE` (~196 members) and Domo KB
  "Chart Types" articles. Reliable for *names*, but a picker entry ≠ a distinct chart.
- **[DOC]** — from Domo product/developer documentation.
- **[INFER]** — reasoned inference, not independently confirmed; flagged so it is not mistaken for fact.

## The count, honestly [ENUM]

There are **not "hundreds" of distinct chart types.** Domo's engine enum exposes **~196 selectable
picker entries**; Domo markets **"150+"** `[DOC]`; the number of genuinely *distinct* chart types is **a few
dozen (~40–70)**. A naive family-by-family sum of documented picker entries lands near **~170** before
removing cross-listed types. The gap between "170 picker entries" and "a few dozen distinct charts" is
inflation from three sources:

- **Orientation twins** — ~44 `HORIZ_*` horizontal copies of vertical charts. Orientation is a property.
- **Preinstalled map geographies** — one map chart type multiplied across ~37 regions/countries.
- **Render-style variants** — curved / stepped / symbol / running-total flavors of the same base chart.

Cross-listing further inflates any raw total: Spark Bar sits under Bar *and* Misc; Spark Line under Line
*and* Misc; Box Plot under Data Science *and* Misc; Funnel Bars under Bar *and* Pie/Funnel; the
"…with Line/Symbols" combos under both Bar and Line. The catalog also shifts release to release (Bubble
was folded into Scatter; Correlation/Confusion Matrix were added later). Treat the lists below as the
current shape, not a frozen contract.

## `badge_*` internal codes [4 LIVE-confirmed; full set in the `domo-phoenix` enum]

`metadata.chartType` on a KPI card is a `badge_*` code. **Only four are confirmed from a live card:**

| chartType | Chart |
|---|---|
| `badge_vert_bar` | Vertical Bar |
| `badge_pie` | Pie |
| `badge_singlevalue` | Single Value |
| `badge_basic_table` | a basic table (exact label unconfirmed — could be HTML Table or Mega Table) [INFER] |

The four above are confirmed from a live card. The **full set of `badge_*` codes is published** in the
open-source `domo-phoenix` `CHART_TYPE` enum (`src/enums/phoenix-chart-type.ts`, GitHub
`DomoApps/domo-phoenix`) as its enum *values* `[ENUM]` — so look a code up there rather than inventing
one. Still confirm the exact code a given chart actually uses by reading `metadata.chartType` off a real
card of that type via `GET /api/content/v1/cards?urns=<id>&parts=metadata` (enum membership ≠ proof a
specific instance's card carries that exact code). **Never fabricate a `badge_*` code that is not in the
enum.**

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

- **Textbox / Note** and **Document / uploaded file** are card *types* (`cardType` ≠ `kpi`), not chart
  badges. Included for completeness; excluded from the ~196 chart count.
- **Pro Code / custom app** = `cardType: "domoapp"` — see [`domo-procode-embedded-cards.md`](../skills/domo-procode-embedded-cards.md).

## Known uncertainties

- `badge_*` codes beyond the four [LIVE] ones come from the `domo-phoenix` `CHART_TYPE` enum [ENUM]; confirm the exact code by reading it off a real card.
- Whether each orientation/curve/step permutation is a truly separate picker entry vs. a property toggle
  is not always explicit in Domo docs; the KB lists them separately, so they are listed separately here.
- Niche picker entries (e.g. "3-Metric Bar", standalone "100 Percent Stacked Bar" articles) appear in KB
  indexes but could not all be cross-checked against a family table [INFER].
- Salesforce-hosted `domo-support.domo.com` pages are JS-rendered and were cross-checked against the
  static `www.domo.com/docs/s/article/*` mirror and search snippets, not scraped directly.
