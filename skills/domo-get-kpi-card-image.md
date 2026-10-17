# Domo Get KPI Card Image

Use this skill to render an existing native card into an image and structured query results.
For card creation, drill paths and host placement, use [standard cards](domo-cards.md) and
[App Studio](domo-appstudio.md). Rendering is a data-bearing read; keep returned rows/images
private unless their publication is authorized.

## Working request verified 2026-10-17

```http
PUT /api/content/v1/cards/kpi/<card-urn>/render?parts=image,queryResult
Content-Type: application/json

{"width":900,"height":600}
```

All **35 final displayed cards / 31 chart codes**, plus drill views, produced native PNGs and
query results in the live exercise. The **SID** header `X-Domo-Authentication` worked.
Numeric card IDs and full `dr:<view-id>:<root-card-id>` URNs worked. This is instance-scoped
runtime evidence [LIVE], not a guarantee for every card type or auth scheme.

**Both width and height were necessary.** Width-only, height-only and the dimensionless
published example returned HTTP 400. The legacy heatmap-table code saved and queried but
returned render 400, including on its original template; use a tested native alternative
when the requirement permits. Do not infer that the same chart fails in every browser UI.

The observed response was **named parts**, not a positional array:

```json
{
  "image":{"data":"<base64 PNG>","notAllDataShown":false},
  "queryResult":{
    "type":"ordered-column-list","limited":false,
    "data":{"datasource":"<dataset-id>","rows":[],"numRows":0,"metadata":[]}
  },
  "limited":false,"notAllDataShown":false
}
```

Decode only `image.data`; queryResult is structured JSON. Check dataset, types, row count and
limit flags, then compare important measures to independent SQL and inspect the actual image.
A query with a saved limit can omit population rows even when limited flags are false.
The legacy `/cards/{id}/data` preview stopped at 500 observations; render queryResult returned
all 9,006 observations for a distribution card. A PNG is not a browser click/interaction test.

The [validation guide](../docs/domo-cards-validation.md) contains complete trial-and-error
findings, filtered drill requests, limits and reproducible validation steps. The read-only
`domo-card-tools.py verify` command validates named parts while omitting row values from output.

## Published contract and its limits

The [Product OpenAPI specification](https://www.domo.com/docs/openapi/product/get-kpi-card-image-api.yaml)
was fetched successfully on 2026-10-17. It documents one operation on the **instance host**, with
`X-DOMO-Developer-Token` authentication [DOC]. It does not establish token exclusivity;
SID is independently verified above. This is not the Platform OAuth `api.domo.com` surface.

`parts` is one comma-joined query parameter. Its 15 documented values are:
`title`, `chartType`, `queryResult`, `data`, `image`, `imagePDF`, `graph`, `dynamic`, `summary`,
`summaryImage`, `dataSource`, `pdp`, `annotations`, `extendedDateInfo`, `table`.
Only the requested/observed parts have live evidence here. Do not interpret every part as an
image, substitute the metadata-GET parts enum, or promise a ready-made PDF. A client may compile
parts into a PDF; this is separate from live interactive embedding.

The request schema is open (`additionalProperties:true`); it names queryOverrides,
treatLongsAsStrings and cardLoadContext but omits the working dimension requirements.
The published response schema describes a generic data array, which differs from the named
parts observed live. Parse actual responses defensively. The declared 200/403/409 responses
are not an exhaustive error inventory: 400 was also observed. PDP enforcement, additional
part schemas, non-KPI render surfaces, and cross-auth equivalence were not tested.

## Boundaries

- Render PUT computes output; v3 `/cards/kpi`, `/cards/kpi/{urn}` save cards, and v3
  `/cards/kpi/definition` reads their configuration. Keep those operations distinct.
- A renderer image/query result is a snapshot. Use [native card embedding](domo-procode-embedded-cards.md)
  or [Domo Everywhere](domo-everywhere.md) for an interactive card.
- Browser behavior, dashboard filters, drill click dispatch and layout require their own checks.
- Keep credentials, raw responses and customer data out of skill documents and public repos.
