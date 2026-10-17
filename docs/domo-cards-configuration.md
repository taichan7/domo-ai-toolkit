# Standard cards: configuration and authoring

> 日本語: [domo-cards-configuration.ja.md](domo-cards-configuration.ja.md)

Read this when an agent must turn an app requirement into native cards, inspect a template,
change its bindings/settings, or decide which part needs Pro Code. The entrypoint is
[the cards skill](../skills/domo-cards.md); the broader family list is in
[the chart reference](domo-cards-reference.md).

## Evidence and lookup

The 2026-10-17 study read 154 unique standard cards on five user-selected dashboards:
71 chart codes, 110 configured override keys. All full definitions had `chartVersion: 12`.
This proves retrieval and stored configuration; it does not prove save compatibility or rendering.

The [offline catalog](reference/domo-card-config-catalog.json) combines two distinct sources:

| Catalog field | Evidence | Use |
|---|---|---|
| `live_card_count`, `live_chart_versions`, `observed_role_signatures`, `observed_override_keys` | [LIVE], definition reads on 2026-10-17 | Select examples and identify settings actually present |
| `documented_columns` | [DOC], public Phoenix chart documentation | Mapping name, required flag, format support, documented maximum |
| `property_refs` → `properties` | [DOC], same public documentation snapshot | Key, label, category, type, value list, dependency, feature flag, bounds/default when published |
| `observed_keys_missing_from_active_docs` | [LIVE] versus [DOC] comparison | Preserve known source values; do not discard them merely because an older public schema omits them |
| `documentation_ui_hex_picker` | [DOC], PropertyConfig source map | UI transformation for some non-select_list colors; raw valueList remains intact |
| `live_hex_color_chart_types` | [LIVE], later save/render exercise | Hex acceptance only on the listed chart codes, even when the raw list contains named colors |

The public documentation currently serves build `main.a710eb8e.chunk.js`. Its factual property
metadata was normalized without tooltip prose. The snapshot covers all 71 observed chart codes,
6,933 active chart/property associations and 820 distinct property keys (1,100 schema variants).
These are documented possibilities, **not 6,933 settings tested in Analyzer**. Same-named properties
can have different value lists/dependencies on different charts; follow a chart's references.
Feature-gated entries and undocumented defaults require target-instance verification.

**Phoenix input roles and Analyzer subscription roles are related, not identical contracts.**
For example, the public `badge_line_bar` metadata requires ITEM/VALUE/SERIES, while all six stored
Analyzer examples in this study projected ITEM plus two or three numeric SERIES columns and no
VALUE mapping. Treat documented roles as selection guidance; use the actual template's ordered
projection for authoring. Do not "repair" a valid Analyzer definition to satisfy the Phoenix list.

Query only the relevant chart or property instead of reading the entire JSON:

```bash
python3 scripts/domo-card-tools.py catalog --search gantt
python3 scripts/domo-card-tools.py catalog badge_pivot_table --property total
python3 scripts/domo-card-tools.py catalog badge_two_trendline --property scale
python3 scripts/domo-card-tools.py catalog badge_line_bar --property line_style
```

An absent code is outside this study, not proof Domo cannot render that chart. A published
`valueList` is a versioned library contract, not a universal enum for all Analyzer releases.
`dependencyOption`/`dependencyValue` describe conditions for that property; preserve them together
and check prerequisites. The literal `<ANY>` is metadata, not a value to write into a card.

## Inspect a supplied dashboard

Use the existing authentication helper. Export a matching `INSTANCE` and `DOMO_TOKEN` or `SID`;
the inspection command does not print credentials or switch instances. For a CLI session:

```bash
bash scripts/authenticate.sh example.domo.com
# bash/zsh: load the owner-only session established above
source scripts/.sid
export INSTANCE SID
python3 scripts/domo-card-tools.py inspect --page https://example.domo.com/page/123
python3 scripts/domo-card-tools.py inspect --card 456 --card 789
```

Repeat `--page` for multiple pages. The tool enumerates those pages only, skips non-KPI objects,
deduplicates card IDs, and reads full definitions. Reports retain source IDs and structural counts;
they omit titles, columns, formulas, filter values, override values, and annotation text. Keep
instance-specific reports private. Nonzero exit means a failed/unsupported read; inspect `failures`
before claiming the page was fully analyzed. It does not follow child pages or drill-target cards.

For the actual authoring body, retrieve the selected template separately into a protected temporary
location outside Git:

```bash
# This PUT retrieves a definition. It does not save or modify the card.
curl --fail-with-body -sS -X PUT "https://$INSTANCE/api/content/v3/cards/kpi/definition" \
  -H "X-Domo-Authentication: $SID" -H 'Content-Type: application/json' \
  -d '{"dynamicText":true,"variables":true,"urn":"<cardId>"}'
```

Developer-token auth uses `X-DOMO-Developer-Token` instead. Never treat a CLI refresh token as a
developer token. The retrieval route is an internal instance API [LIVE/REPO], not the public
OAuth Cards API. Support/auth acceptance must be checked on each target instance.

## Read the right configuration layer

| Location in the full response | Meaning / edits |
|---|---|
| `definition.charts.main.chartType` | Exact native chart code; select a matching template rather than swapping this alone |
| `definition.charts.main.component` | Subscription component the chart consumes; preserve the relationship |
| `definition.charts.main.overrides` | Chart presentation properties, often null for defaults |
| `definition.charts.main.goal` | Goal configuration when supplied; distinct from a KPI's summary and from the Goals product |
| `definition.subscriptions.main.columns[]` | Actual projection order and roles: `column`, `formulaId`, `mapping`, `aggregation`, `distinct`, `alias`, `format`, `calendar` when present |
| `...main.groupBy`, `orderBy`, `filters`, `limit` | Query grouping, order, restrictions, result size; not appearance |
| `...main.dateGrain`, `dateRangeFilter`, `fiscal`, `projection` | Date buckets/ranges and query behavior; date grain and range are different operations |
| `definition.subscriptions.big_number` | Independent summary-number query when present; not necessarily the chart total |
| `definition.formulas` | Returned formula definitions; may include dataset formulas unused by this chart |
| `definition.conditionalFormats` | Conditions and resulting formats; preserve column/formula references |
| `definition.controls` | Card quick-filter/control configuration; not chart overrides or page Variables |
| `definition.dynamicTitle`, `dynamicDescription` | Display text and dynamic references; not source labels to expose in public catalogs |
| `definition.annotations`, `segments`, `allowTableDrill`, outer `drillpath` | Additional behavior/content that must be preserved or deliberately handled |
| outer `columns[]` | Source-column metadata/type inventory; not the same array as the chart projection |

Do not infer the full definition from v1 `metadata.inputTable: null`. On all 154 full reads,
`definition.inputTable` was the boolean `false`, while the query bindings were present under
`subscriptions`. Neither null nor false means there is no chart graph.

Use the actual datasource schema and formula result types. A numeric-looking string is not a
measure until its type is correct. Preserve grouping keys and ordering when replacing columns.
For calculated fields, resolve the transitive `formulaId` / `DOMO_BEAST_MODE(...)` dependencies;
counting all returned formulas as "used by the chart" overstates the evidence.

## Mapping traps and native alternatives

The table shows useful native choices. Required/optional slots and maxima are available per exact
code in the catalog; the shorthand here is not a universal schema.

| Requirement | Native candidates and bindings | Configuration to inspect |
|---|---|---|
| Compare categories; grouped/stacked/100%/nested/running totals | `badge_vert_*`, `badge_horiz_*`; usually ITEM, VALUE, optional SERIES | Labels, sort, series grouping, percent/running-total semantics |
| Trend and comparison lines | `badge_trendline`, `badge_two_trendline`, curved/symbol/step/running-total variants | Dates, date grain, gaps, scales, projection, regression |
| Currency bars and ratio line | `badge_line_bar`, line/stacked/grouped/symbol combinations | Role/series ordering, line/bar formats and axis titles; do not assume two generic VALUE slots |
| One KPI or recent-period comparison | `badge_singlevalue`, `badge_multi_value` | VALUE, optional ITEM/TARGET; selection of first/last/comparison values and number format |
| Target/attainment | `badge_filledgauge` | Required CURRENT, optional TARGET/MAX/CATEGORY; actual data-backed target versus fixed override |
| Range/threshold gauge | `badge_gauge`, `badge_facegauge`, `badge_bullet`, `badge_vert_bullet` | VALUE; bullet can use TARGET/RANGE1–3; radial ranges and face thresholds are properties |
| Exact rows, wrapping, totals | `badge_basic_table` = Mega Table [DOC]; `badge_table` is a legacy table code with UI label unverified | VALUE projections, column formats, totals, wrapping, conditional formats |
| Cross-tab / subtotal | `badge_pivot_table` | ROW/COLUMN dimensions and VALUE measures; subtotals, total rows/columns, sort |
| Matrix intensity | `badge_heatmap` or `badge_heatmap_table` | Heatmap ITEM/SERIES/VALUE versus table-style VALUE columns; palette/distribution |
| Correlation or bubble | `badge_xybubble`, `badge_xy_line`, legacy scatter/bubble codes | X is XTIME on the modern bubble contract; VALUE is Y; BUBBLESIZE and SERIES optional |
| Geographic aggregation | world, Japan, US, Canada, Australia codes observed | Geography key, aggregation, gradient, balanced distribution, zoom; not arbitrary route geometry |
| Project schedule | `badge_gantt` | Required ITEM/START_DATE/END_DATE, optional CATEGORY; prepare typed start/end data |
| Calendar events | `badge_calendar` | Required DATE/EVENT, optional VALUE1; not a generic ITEM/VALUE chart |
| Distribution/range | box plots, `badge_highlow` | Boxplot ITEM/VALUE versus high-low CATEGORY/HIGH/LOW; do not aggregate away the distribution |
| Funnel/share/hierarchy | pie/donut/treemap/funnel/folded funnel/funnel bars | Category/value/series contract and order; valid aggregation and stage population |
| Dashboard selection | `badge_slicer`, `badge_checkbox_selector`, `badge_dropdown_selector` | ITEM required, VALUE optional; placement/filter scope belongs to the host page |
| Data-driven text | `badge_textbox`, `badge_word_cloud` | `badge_textbox` is a KPI chart; the separate `Text` card type is not |

Native Gantt, calendar, selectors, pivots, gauges, conditional formats, and dual-scale charts are
reasons to investigate a standard card first. These are not automatically reasons to build Pro Code.

## Properties that were configured in the study

Every one of the 416 stored override values in these cards was a **string**. Preserve the original
representation (`"true"`, `"false"`, `"0.15"`), case and spelling. A `Default` value, an omitted key,
and an explicit false are not interchangeable. No stored override means "uses defaults", not
"has no configurable properties". Query the exact chart's documented schema before adding a key.

| Settings | Observed keys | Practical use / caveat |
|---|---|---|
| Data labels | `datalabel_text`, `datalabel_fill`, `datalabel_show_total`, `datalabel_allow_overlap`, `datalabel_use_scale_abbrev` | Text, background, stack totals, overlap and abbreviation. Box plots included `%_MEDIAN`; bar labels included `%_VALUE`. Macro support varies by chart. |
| Hover | `hover_text`, `hover_use_scale_format`, `hover_use_scale_abbrev` | Tooltip text/number handling; observed macros include `%_CATEGORY_NAME`, `%_SERIES_NAME`, `%_VALUE`, `%_BUBBLE_VALUE`. Reuse chart-appropriate macros, not arbitrary template syntax. |
| Axes and line appearance | `title_x`, `title_y`, `line_style`, `dual_y_scales`, `log_scale_x`, `log_scale_y`, `value_scale_min`, `value_scale_min_right`, `value_scale_max_y` | Axis titles, dual scales, minima/maxima, logarithms. Inspect exact key support; X/Y and left/right variants differ across chart codes. |
| Date/gaps | `never_use_time_scale`, `hide_empty_values` | Category rendering and empty-value behavior. These do not replace `dateGrain` or query filters. |
| Legend | `lrg_legend_position`, `details_legend_position` | Separate card/detail presentation; `Hide` was stored with that case. |
| Combo formats | `label_format_bar`, `label_format_line`, `decimal_places_line`, `divide_value_scale_by`, `title_bar`, `title_line` | Native bar/line formatting, e.g. Currency and Percentage. Confirm whether data is a fraction or already multiplied by 100. |
| Prediction/reference lines | `multi_projection_method`, `multi_proj_btn_visibility`, `last_point_complete`, `project_val_method`, `show_linear_regression`, `show_min_line`, `show_max_line` | Projection and incomplete-period behavior; some saved legacy keys are absent from the active public snapshot. Preserve them pending verification. |
| KPI comparison | `comp_data_used`, `single_value_type`, `single_value_format`, `change_value_format`, `single_divide_value_by`, `size_single_val`, `val_color_from_comp` | Stored examples include `Last 2 Values`, `Last Value`, `Number`. Comparison type, ordering and selected dates affect the result. |
| Filled gauge | `min_value`, `max_value`, `target_value`, `target_label`, `value_label`, `value_format`, `value_type`, `color_source` | Fixed bounds/target and display; data-bound CURRENT/TARGET remain separate projection roles. |
| Radial/face thresholds | `range1_min` through `range6_max`, `range1_color` through `range6_color`; `green_range_min/max`, `yellow_range_min/max`, `red_range_min/max` | Interval thresholds/colors; choose business thresholds deliberately. Do not transplant source target amounts. |
| Map/heat colors | `balanced_distribution`, `auto_zoom`, `hide_total`, `color_theme`, `data_label_format_text`, `use_gradient_colors` | Map label key differs from `datalabel_text`; observed map macros included `%_NAME` and `%_VALUE`. |
| Table | `header_row_fill_color`, `total_row`, `total_row_fill_color`, `total_row_position`, `total_row_suppress_count`, `allow_wrap` | Native totals/header/wrapping. Stored colors included 8-digit RGBA-like hex; preserve source encoding rather than assuming 6 digits. |
| Pivot | `total_col`, `total_col_fill_color`, `total_column_label`, `subtotal_rows`, `subtotal_columns`, `subtotal_col_fill_color`, `apply_total_colors_to_col_headers`, `attr_total_row`, `colsubtotal_vert_border`, `column_sort` | Cross-tab summaries and layout. Derive opaque sort structures from the source definition, not guessed JSON. |

The full set of 110 configured keys and all per-chart applicability is in the catalog. Generic
saved filter keys (`range_filter_*`, `row_filter`, `hide_series`, `series_filter`) are often absent
from active Phoenix metadata. Their presence does not establish a supported public configuration
API. Also keep card `controls[]`, query `filters[]`, host page filters, and Variables distinct.

For example, after selecting a compatible template, these are **partial override edits**, not a
complete save body and not proof of rendering support on a new instance:

```json
{
  "datalabel_text": "%_VALUE",
  "hover_text": "%_CATEGORY_NAME<br>%_VALUE",
  "lrg_legend_position": "Hide"
}
```

Change only properties required by the request. Leave unspecified options and source defaults
intact. Validate chart dependencies, role requirements, ranges, source data units, and target
feature availability before interpreting a setting as supported.

## Authoring: reuse a graph, then verify the saved result

Use a same-instance template with the desired exact chart code and closest binding structure.
`POST /api/content/v1/cards/{sourceId}/copy` with `{}` creates an independent card [REPO]; read its
full definition again. Simple title changes may use v1 partial updates. New column roles, series,
formulas, filters and deep properties use the **full v3 definition workflow**. A clone alone does
not verify that retargeting to a different schema worked.

The established create/update workflow is documented in the toolkit's
[native KPI recipe](../skills/domo-cross-instance-clone.md#section-11--native-kpi-cards) and
[App Studio clone reference](reference/app-studio-clone.md#card-update-recipe-definition-driven).
Critical transformations from that recipe:

1. Start with the retrieved `definition`, preserving `modified`, `allowTableDrill`, subscription
   names, column order, and `charts.main.component`. On UPDATE, read the target too and preserve its
   current modification/identity fields. A fresh read avoids silently applying a stale template.
2. Map datasource, projection columns, grouping/sort/filter/date references, formula references,
   conditional formats, controls, dynamic text and drill destinations as needed. Use an explicit
   mapping and abort on an unresolved dependency; a broad string replacement is not a schema map.
3. Read `formulas` is an array; write shape is `{dsUpdated:[], dsDeleted:[], card:[...]}`. Retain
   required formula definitions as card-level formulas (`persistedOnDataSource:false`); never empty
   the list while leaving `formulaId` references. Resolve transitive Beast Modes as well.
4. Convert read `conditionalFormats` to `{card:[...], datasource:[]}`; annotations to
   `{new:[], modified:[], deleted:[]}`; segments to `{active:[], create:[], update:[], delete:[]}`
   according to the canonical clone recipe. These empty change sets are suitable for a new-copy
   workflow; they do not prove that existing annotations or segment definitions were migrated.
   On an update involving those features, preserve their target state or capture the exact write
   contract rather than silently clearing/rebuilding it.
5. The write envelope has `definition`, `dataProvider:{dataSourceId:"<targetDatasetId>"}`,
   `variables:true`, `columns:false`. Strip the outer read fields `urn/id/embedded/dataSourceWrite`
   and the outer `columns` array. The query's `subscriptions.main.columns[]` stays. Handle nested
   datasource IDs as specified by the canonical recipe; don't blindly copy outer response fields.
6. CREATE uses `PUT /api/content/v3/cards/kpi?pageId=<pageId>`; UPDATE uses
   `PUT /api/content/v3/cards/kpi/<cardUrn>` [REPO]. These **save**, unlike the `/definition` PUT.
   Apply the current repository/user authorization. Source dashboards are examples to read; do not
   edit their cards to test a recipe. Cross-instance work also needs the clone skill's ID maps.

Preserve the source's subscription shape. Some KPI types have only `main`; do not synthesize a
`big_number` subscription. Where present, the summary is its own query, commonly a single aggregate
with `limit:1`; it must be validated independently of the plotted data.

After saving, re-read the **new/target card**, compare chart code, role/column bindings, datasource,
aggregations, filters/date grain, formulas and edited overrides. Then verify data and rendering
using the authorized target workflow (or a browser check when requested). Test the target's actual
width, date/filter changes, drill, empty results and PDP where relevant. HTTP 200 alone is not visual
verification. No create/update was executed as part of this read-only dashboard study.

For subsequent live authoring evidence, read [validation and drill paths](domo-cards-validation.md).
It records 35 final cards / 31 chart codes, exact failed requests and repairs, dimensioned native
rendering, full-population versus preview checks, drill URNs/ancestor semantics, cumulative filters,
and App Studio theme/layout experiments. The catalog's original 154-card study remains read-only.

## Place the result in the app

For a Domo app containing many native cards, use **App Studio as the container**, with native KPI
cards and Pro Code tiles for the remaining interactions. Card creation and layout registration
are separate concerns; verify content registration plus desktop/compact layout membership. Follow
[App Studio](../skills/domo-appstudio.md) for locks/layout and
[native cards plus Pro Code](../skills/domo-procode-embedded-cards.md) for host integration.

Choose Pro Code for a demonstrated gap: transactional editing/write-back, a custom diagram or
interaction absent from native types, a bespoke workflow UI, or shared custom application state.
First check whether data preparation, Beast Modes, native controls, conditional formatting or a
different native family solves the requirement. Missing examples or unfamiliar configuration
are evidence gaps, not proof of a product limitation. A Phoenix chart drawn in a custom app is
still Pro Code, not an independently managed native KPI card.

## Primary sources and maintenance

- [Public Phoenix chart/property documentation](https://domoapps.github.io/domo-phoenix/#/properties)
  supplies mapping and property facts; the catalog records the inspected build and SHA-256.
- [Phoenix chart-type enum](https://github.com/DomoApps/domo-phoenix/blob/master/src/enums/phoenix-chart-type.ts)
  supplies public code names; enum membership does not certify a save operation.
- [Domo Line Chart documentation](https://www.domo.com/docs/s/article/360043429233)
  explains native line/axis options. Its prose labels must not be guessed into internal keys.

For later dashboard URLs, inspect their definitions, deduplicate by source card ID, record the
coverage denominator/failures, and compare roles, properties and shapes against this catalog.
Add newly observed chart codes with dated evidence; retain unknown keys without inventing their
semantics. Update public schemas only from verified primary metadata, retaining dependencies,
feature flags and per-chart variants. Keep source IDs and raw exports out of public resources.
