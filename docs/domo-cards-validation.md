# Native card authoring, drill paths, and App Studio validation

Read this when creating cards, diagnosing saved-but-wrong charts, or adding click-to-drill.
It supplements [configuration](domo-cards-configuration.md) and
[App Studio](../skills/domo-appstudio.md). Examples use placeholders.

## Evidence and completion criteria

The 2026-10-17 authoring exercise created **35 displayed cards across 31 final chart codes**,
plus two drill views, on one authorized target dataset. All 35 final cards produced native PNGs
and structured query results. The initial 32nd code, legacy `badge_heatmap_table`, saved and
queried successfully but returned render HTTP 400, including on the original template. It was
replaced with a native Mega Table with conditional formatting. This is a renderer observation,
not evidence that the chart is unavailable in every Domo UI/version.

Verified: saved definitions, dataset bindings, independent aggregate comparisons, native images,
drill ancestry/order, filtered drill results, app settings readback, one-view membership, and
both layout grids. Browser click behavior and whole-app screenshots were **not** verified.
Do not equate server-rendered images with a browser interaction test.

Use these distinct checks:

1. Read the saved definition; check chart code, roles, aggregation, formulas and properties.
2. Compare query results with an independent SQL aggregate or known cardinality.
3. Render the native chart; inspect its image, not just its HTTP status.
4. Verify page membership, layout registration and intended interactions separately.
5. When browser testing is authorized/available, exercise filters, drilling, back/up, resizing
   and compact display. Otherwise state that limit explicitly.

## Native render: the working request

```http
PUT /api/content/v1/cards/kpi/<card-urn>/render?parts=image,queryResult
Content-Type: application/json

{"width":900,"height":600}
```

SID authentication and numeric card IDs worked. Drill URNs `dr:<view-id>:<root-card-id>` also
worked. Width **and** height were necessary in the tested instance: width-only, height-only,
and the documented dimensionless example returned 400. The observed response uses named parts:

```json
{
  "image": {"data":"<base64 PNG>","notAllDataShown":false},
  "queryResult": {
    "type":"ordered-column-list","limited":false,
    "data":{"datasource":"<dataset-id>","rows":[],"numRows":0,"metadata":[]}
  },
  "limited":false,"notAllDataShown":false
}
```

Decode only `image.data`. Query rows are structured data. Check returned dataset, row count,
types and all limit flags. False limit flags do not prove that an intentionally saved query
`limit` includes the full population, or that every row fits in the visible table viewport.

```bash
python3 scripts/domo-card-tools.py verify --instance example.domo.com --card 123 \
  --width 900 --height 600 --expected-dataset '<dataset-id>'
python3 scripts/domo-card-tools.py verify --instance example.domo.com --card dr:456:123
```

The helper reads rows but reports only structural metadata. It does not save, copy or delete
cards, and does not establish semantic correctness or browser behavior.

## Trial-and-error findings

| Failure / misleading result | Repair and evidence | Scope |
|---|---|---|
| Global KPI grouped by entity | COUNT DISTINCT without groupBy; check one returned row against SQL | Use the intended measure grain |
| Event quantity repeated in every activity | Filter to the one creation event for planned totals; use MAX per entity in details | Inspect event/entity semantics first |
| String timestamp treated as a date | Card formula `DATE(STR_TO_DATE(\`event_time\`,'%Y-%m-%d %H:%i:%s'))`, typed DATE | MIN/MAX datetime Gantt formulas use DATETIME |
| `dateGrain:MONTH` stored, but query still daily | Explicit month bucket `STR_TO_DATE(CONCAT(LEFT(\`event_time\`,7),'-01'),'%Y-%m-%d')`; 12 monthly rows confirmed | Do not rely on stored dateGrain alone |
| Calendar creation returned 500 | Adding `main.dateGrain:{column:<DATE-formula-id>}` alone fixed the same DATE/EVENT/VALUE1 graph | Confirm failure did not create a card before retry |
| Calendar showed unintended period | `dates_from:"User Specified"`, `user_year:"Specified"`, `selected_year:"<year>"`, `user_month:"Aug"`, `view:"Month"`; explicit month filter | Respect prerequisites; first_month_displayed belongs to Year view |
| Multi-value creation returned 500 | VALUE before ITEM **and** explicit month bucket repaired save/render | Two changes together; individual cause not isolated |
| Radial query value correct, image misleading | Added a constant ITEM projection/group and explicit Half style/value-label settings; image then matched SQL | Bundled repair; do not attribute solely to ITEM |
| Legacy data GET returned only 500 box-plot observations | `GET /cards/{id}/data?limit=20000` still 500; native render query returned all 9,006 input observations | Preview count is not distribution population |
| Raw subscription POST to query API failed or ignored filters | Do not wrap/cast legacy subscription JSON into query-v1 expressions; use the saved-card renderer or explicit SQL | A 200 on a malformed translation can be wrong |
| Raw property valueList rejected gauge hex colors | Live radial range colors accepted hex despite a published named-color list; some non-select_list colors also have a separate documentation UI hex-picker transformation | Keep UI transformations separate from live per-chart acceptance |
| Numeric conditional format save returned 400 | Legacy operand `GREAT_THAN_EQUALS_TO` worked; `GREATER_THAN_OR_EQUAL` failed | These are legacy conditional-format operands, not a universal filter enum |
| Card create/update succeeded but page placement was missing | Reconcile actual page/layout membership with the registry before retiring anything | HTTP success does not establish placement |
| Layout removed old card frames but they reappeared as virtual appendix cards | Page/card membership survives frame omission; retire the explicitly authorized old membership/resources, then check again | A layout save is not a card deletion |

New-card formula and conditional-format wrappers remain as described in the configuration guide.
For updates read the target's fresh `modified`. For non-idempotent create failures, reconcile
page/card state before retrying. Never experiment on the read-only source dashboards.

## Drill paths: two meanings of “path”

Domo's product behavior is described in
[adding drill paths](https://www.domo.com/docs/ja/s/article/360042924094) and
[drilling down](https://www.domo.com/docs/ja/s/article/360042923994).
Each selected category/series adds a filter to the next view; later selections accumulate.
The same measure can recur at each level. Cross-dataset drilling requires matching category/
series column names and values. Create Beast Modes on the root; the documentation warns that
new calculations made only in child views disappear. Funnel roots and period-over-period child
charts have documented restrictions. The default final raw-data table is available in card
details, not dashboard in-place drilling; an explicit table drill view is a separate authored view.

These instance routes were verified live; they are not a public Platform API contract:

| Object / action | Working shape |
|---|---|
| Create a drill view | `PUT /api/content/v3/cards/kpi?parentUrn=<root-card-id>` with the normal new-card write envelope; **no pageId** |
| Resulting drill view identity | `urn:"dr:<drill-view-id>:<root-card-id>"`; ID and URN have different purposes |
| Read/update/render a child | Pass the **full drill URN**, not its numeric view ID, to definition/update/render routes |
| Inspect descendants | `GET /api/content/v1/cards?urns=<root-id>&parts=drillPath,drillPathURNs,drillParents,metadata` |
| Root metadata | `drillPathURNs` is the ordered list of descendant URNs; `drillPath.paths` is nested by numeric drill-view ID |
| Definition read's outer `drillpath` | **Ancestors** of the requested view. Root is `[]` even when it has children. Do not interpret it as “no drill configured” |
| Order modification | Client bundle exposes `PUT /api/content/v1/cards/<root-id>/drillviews/reorder` with a JSON ID array [SOURCE]; **not exercised** in this run |

Creating two views sequentially with the same root parentUrn produced a sequential chain.
The second child's definition listed root and first-child URN as ancestors. Confirm the saved
tree rather than assuming every instance appends the same way. Do not copy drill targets into
App Studio `viewIds`: drill views are not navigation tabs or page-drill destinations.

For a root bar grouped by `site`, first child grouped by physical `line`, and final event table:

1. Create children using native chart templates and physical columns where possible.
2. Re-read root descendants and each child's ancestors. Keep the child views off the main page.
3. Configure the root's layout content entry with
   `interaction:{type:"DRILL",config:{}}`, `editInAppViewer:true`,
   `compactInteractionDefault:true`. Default STANDARD may filter/open details instead.
4. Render first child with a selected site; then render the last child with site **and** line:

   ```json
   {"width":1000,"height":600,"queryOverrides":{"filters":[
     {"column":"site","dataSourceId":"<dataset-id>","values":["<selected-site>"],
      "operand":"IN","dataType":"string","filterType":"LEGACY"},
     {"column":"line","dataSourceId":"<dataset-id>","values":["<selected-line>"],
      "operand":"IN","dataType":"string","filterType":"LEGACY"}
   ]}}
   ```

5. Include context columns in the final table and assert every returned row matches both
   filters. Compare event and distinct-entity counts to independent SQL. Check the saved limit
   before claiming full-population coverage. The live exercise matched 4,683 event rows and
   1,161 distinct entities. This verifies the drill query/filter mechanism; actual click dispatch,
   back navigation and reset still require browser interaction testing.

Do not disable interactions to remove selection outlines. Keep `allowTableDrill` deliberate;
hiding the final view does not replace PDP. This exercise did not test PDP or cross-dataset drilling.

## App Studio: preserve the target's schema

The older [clone capture](reference/app-studio-clone.md) and this target used different write
representations. On the tested instance, **GET → mutate fields → PUT the full GET object** worked;
forcing the older `type:"dataapp"`, string view scaffolding and entityType conventions failed.
The successful target kept `type:"app"`, numeric view IDs and navigation `entity` fields.
Do not treat either capture as a universal DTO or mix their fields blindly.

Theme changes were isolated by top-level collection. Cards, tables, fonts, pages, navigation and
headers saved successfully. Replacing an `AUTOMATIC_COLOR` with an `RGB_HEX` color caused 400;
preserving its light/dark references and changing only existing RGB_HEX entries worked.
Use `{sourceId:"ca2"}` card styles, `{sourceId:"t2"}` table styles, `{sourceId:"h1"}` headers
and `{sourceId:"p0"}` page styles. Re-read values because the server can normalize navigation
button fit/alignment, borders/dividers and page density.

To consolidate multiple tabs: first register and validate every intended card on the retained
page, then `DELETE /api/content/v1/dataapps/<app-id>/views/<extra-view-id>`. This route removed
three tabs and left exactly one view. It is a mutation, not a hide toggle; authorization and
backups are required. In this exercise explicit newly created replacement cards were used;
adding pageId to a card **update**, or sending guessed page `cardIds`, did not establish placement.

For final layout: read its existing card/header entries, retain their contentKeys, set explicit
standard/compact frames, remove virtual/virtualAppendix, acquire the layout writelock, PUT,
and DELETE the lock in `finally`. Verify membership, unique keys, grid bounds and no overlaps
after old resources are retired. Do not delete unrelated cards to satisfy a layout assertion.
The tested final page has 35 cards, four native section headings and no additional tabs.
