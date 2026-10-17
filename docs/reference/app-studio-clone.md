# App Studio Clone Reference

Captured during the PE Ops clone 2026-05-12 through 2026-05-14 against `source-instance.domo.com`. Covers the cross-instance write paths for App Studio dataapps that the original clone-content skill marked "UNVERIFIED".

## Endpoint cheatsheet

| Purpose | Method | Path |
|---|---|---|
| Read source dataapp | GET | `/api/content/v1/dataapps/<id>?includeHiddenViews=true` |
| Create dataapp shell | POST | `/api/content/v1/dataapps` |
| Add view to dataapp | POST | `/api/content/v1/dataapps/<id>/views` |
| Unified dataapp PUT (theme/nav/landing/view-order) | PUT | `/api/content/v1/dataapps/<id>?includeHiddenViews=true` |
| Read view page stack | GET | `/api/content/v3/stacks/<viewId>` |
| Read view layout | GET | `/api/content/v4/pages/<viewId>/layouts` |
| Acquire layout writelock (instance-dependent) | PUT | `/api/content/v4/pages/layouts/<layoutId>/writelock` body `{}` |
| Write view layout | PUT | `/api/content/v4/pages/layouts/<layoutId>` |
| Release layout writelock | DELETE | `/api/content/v4/pages/layouts/<layoutId>/writelock` |
| Rename view | PUT | `/api/content/v1/pages/<viewId>` |
| Read card definition (full write shape) | PUT | `/api/content/v3/cards/kpi/definition` body `{dynamicText, variables, urn}` |
| Create KPI card on page | PUT | `/api/content/v3/cards/kpi?pageId=<viewId>` |
| Update KPI card by urn | PUT | `/api/content/v3/cards/kpi/<urn>` |
| Create document/image card | POST | `/api/content/v1/cards?pageId=<viewId>` |
| Download source file | GET | `/api/data/v1/data-files/<dataFileId>` |
| Upload file (target) | POST | `/api/data/v1/data-files` (multipart) |
| Variable function template create | POST | `/api/query/v1/functions/template` |
| Variable control register | PUT | `/api/content/v1/variable/controls` (body is ARRAY) |
| Variable page-binding (session-bound, see below) | PUT | `/api/content/v1/variable/controls/PAGE/<viewId>` |

All callable with the ryuu refresh token as `X-DOMO-Developer-Token`.

## Unified dataapp PUT body shape

**Later evidence, 2026-10-17:** this section is the older clone capture, not a universal DTO.
A later live target accepted full GET→mutate→PUT with `type:"app"`, numeric view IDs and
navigation `entity`, while forcing the older scaffolding below returned 400. Preserve the
target's representation and verify the result. See [live validation](../domo-cards-validation.md#app-studio-preserve-the-targets-schema)
for theme collection isolation, polymorphic color types, one-tab consolidation and readback checks.

This is the body captured from the App Studio editor in the older clone. It controls views, nav, theme, landing view, view order, and view-add. In that capture GET returned a SUBSET — several required-on-PUT fields came back as `null` on read.

```json
{
  "id": <number>,
  "title": "...",
  "description": "...",
  "type": "dataapp",
  "landingViewId": "<string viewId>",
  "viewIds": ["<viewId1>", "<viewId2>", ...],
  "pageDrillParentStates": [],
  "conversationalAgentContextRequest": {"add": null, "remove": {"dataSourceIds": []}},
  "views": [
    {
      "viewId": "<string>",
      "parentViewId": "0",
      "viewOrder": 1,
      "title": "Executive Summary",
      "view": null,
      "layout": null,
      "children": [],
      "type": "dataappview",
      "hasLayout": true,
      "appPageDataSourceId": "null"
    },
    ...
  ],
  "navigations": [
    {"entityType": "HOME", "entityId": null, "icon": {"value": "home"}, ...},
    {"entityType": "VIEW", "entityId": "<viewId1>", "icon": {"value": "pages"}, "title": "Executive Summary", ...},
    ...
    {"entityType": "AI_ASSISTANT", ...},
    {"entityType": "CONTROLS", ...},
    {"entityType": "DISTRIBUTE", ...},
    {"entityType": "MORE", ...}
  ],
  "theme": { /* full theme spec — preserved verbatim from source */ },
  "appLevelControls": [ /* preserved verbatim */ ],
  ...
}
```

### Required-on-PUT, null-on-GET fields

| Field | Required because |
|---|---|
| `viewIds` (array of strings, parallel to `views[]`) | Without this, new views[] entries are silently dropped. |
| `pageDrillParentStates` (usually `[]`) | PUT returns 400 without it. |
| `conversationalAgentContextRequest` | Required even when not changing context. |
| `views[].viewId` as STRING | GET returns numbers. PUT requires strings. |
| `landingViewId` as STRING | Same. |
| `views[].parentViewId: "0"` | String, not number. |
| `views[].viewOrder` 1-indexed integer | |
| `views[].view: null`, `views[].layout: null`, `views[].children: []` | Required scaffolding. |
| `navigations[]` with one VIEW entry per viewId + standard HOME/AI_ASSISTANT/CONTROLS/DISTRIBUTE/MORE system entries | Without these the dataapp doesn't render the chrome. |

### Nav `phosphor` icons — STRIPPED (open gap)

VIEW nav entries on source have rich icons like `{value: "webpage", phosphor: "Globe"}`, `phosphor: "ChartArea"`, `phosphor: "Workflow"`. After this unified PUT, the subsequent GET shows ALL VIEW icons reverted to `{value: "pages"}` — both `value` and `phosphor` fields are stripped/normalized. The default `"pages"` is what the "Add Page" UI captures too.

The icon-picker save call uses a SEPARATE endpoint (not yet captured — probably `PUT /api/content/v1/dataapps/<id>/navigations/<navEntityId>/icon` or similar). Emit a per-view manual-task with the source's `phosphor` value as the recommendation.

## Layout PUT — surgical in-place mutation ONLY

`PUT /api/content/v4/pages/layouts/<layoutId>` does NOT accept a rebuilt body with new `content[]` / `template[]` entries. Returns generic HTTP 400 with no error details. It accepts ONLY mutations of entries the target layout already contains.

### Body shape

```json
{
  "layoutId": <number>,
  "pageUrn": "<viewId as string>",
  "printFriendly": true,
  "enabled": true,
  "isDynamic": false,
  "hasPageBreaks": false,
  "content": [
    {
      "id": <numeric internal id>,
      "contentKey": <integer>,
      "compactInteractionDefault": true,
      "hideTitle": false, "hideDescription": true, "hideSummary": false,
      "summaryNumberOnly": false, "hideTimeframe": false, "hideFooter": true,
      "hideWrench": false, "hideMargins": false, "hasSummary": false,
      "fitToFrame": false, "hideBorder": false,
      "acceptFilters": true, "acceptDateFilter": true, "acceptSegments": true,
      "cardId": <number>, "cardUrn": "<string>",
      "type": "CARD",
      "style": {"sourceId": "ca3"},
      "showMoreContent": false
    }
  ],
  "standard": {
    "template": [
      {"contentKey": <integer>, "x": 0, "y": 0, "width": 30, "height": 12,
       "type": "CARD", "virtual": false, "virtualAppendix": false, "children": []}
    ]
  },
  "compact": {
    "template": [ /* same shape for mobile */ ]
  },
  "style": { /* page-level styling */ },
  "background": { /* page background */ }
}
```

### Mutation recipe

```python
# 1. GET target layout (has appendix entries for every card placed earlier via PUT ?pageId=)
layout = GET("/api/content/v4/pages/<view_id>/layouts")

# 2. For each target CARD entry in content[]:
for c in layout["content"]:
    if c.get("cardId") == target_card_id:
        # mirror source content[] entry's style flags
        c["hideTitle"] = src_content_entry["hideTitle"]
        c["hideDescription"] = src_content_entry["hideDescription"]
        c["hideFooter"] = src_content_entry["hideFooter"]
        c["hideWrench"] = src_content_entry["hideWrench"]
        c["hideMargins"] = src_content_entry["hideMargins"]
        c["fitToFrame"] = src_content_entry["fitToFrame"]
        c["hideBorder"] = src_content_entry["hideBorder"]
        c["acceptFilters"] = src_content_entry["acceptFilters"]
        c["acceptDateFilter"] = src_content_entry["acceptDateFilter"]
        c["acceptSegments"] = src_content_entry["acceptSegments"]
        c["editInAppViewer"] = src_content_entry.get("editInAppViewer", True)
        c["showMoreContent"] = src_content_entry.get("showMoreContent", False)
        c["compactInteractionDefault"] = src_content_entry.get("compactInteractionDefault", True)
        c["style"] = src_content_entry.get("style", {})  # carries sourceId for theme card-styles
        target_content_key = c["contentKey"]

# 3. For each target template[] entry matching that contentKey:
for section in ("standard", "compact"):
    for t in layout[section]["template"]:
        if t["contentKey"] == target_content_key:
            t["x"] = src_x; t["y"] = src_y
            t["width"] = src_w; t["height"] = src_h
            t["virtual"] = False
            t["virtualAppendix"] = False
            # KEEP contentKey and other fields

# 4. Acquire a writelock when the instance requires it, PUT, then release.
# maintenance-instance returned WL003 without this sequence on 2026-08-08.
PUT("/api/content/v4/pages/layouts/<layoutId>/writelock", body={})
try:
    PUT("/api/content/v4/pages/layouts/<layoutId>", body=layout)
finally:
    DELETE("/api/content/v4/pages/layouts/<layoutId>/writelock")
```

Writelock enforcement differs by instance/version. The earlier `source-instance` capture accepted the layout PUT without a lock and `POST .../writelock` returned 405. On `maintenance-instance`, `PUT .../writelock` with `{}` returns `{layoutId,userId,lockTimestamp,lockHeartbeat}` and is required; omitting it returns 403 `WL003`. Use `PUT`, never `POST`, and always release with `DELETE` in a `finally` block.

### TABS surgical-append (gap #5 resolution)

If source uses TABS/TAB_BAR/TAB_CONTENT containers, you CAN add them — but every new contentKey you allocate must be **above** the highest existing target contentKey to avoid collision with the target's auto-appendix entries (which is what causes the "TABS rejected" 400).

```python
max_ck = max(c["contentKey"] for c in layout["content"])
next_ck = max_ck + 1

# Append TABS entry as content[] + template[] pair (fresh contentKey)
tabs_ck = next_ck; next_ck += 1
layout["content"].append({"contentKey": tabs_ck, "type": "TABS", ...})
layout["standard"]["template"].append({
    "contentKey": tabs_ck, "x": 0, "y": <below_existing>, "width": 60, "height": 30,
    "type": "TABS", "virtual": False, "virtualAppendix": False,
    "children": [<tab_bar_entry>, <tab_content_entries>...]
})

# For each card moving INTO a tab, REMOVE its top-level template[] entry
# (cards in tabs should not also appear at top level)
```

### Source `id` field

Layout entries carry `content[].id` numeric values (internal layout entry IDs). Probably worth stripping any source `id` before PUT — couldn't isolate empirically due to the surgical-mutation constraint.

### Source TABS-flattening fallback

If reconstructing TABS on target isn't wanted, recurse `children[]` and compute absolute positions (`abs_x = parent.x + child.x`, `abs_y = parent.y + child.y`). Cards in multiple tabs collapse to first-tab position. Lossy but acceptable for demo.

## Image / PDF tile clone

Full 4-step recipe for `type: "document"` cards (`chartType: null`).

```bash
# 1. Download source file
curl -s "https://$SOURCE_HOST/api/data/v1/data-files/<source_dataFileId>" \
  -H "X-DOMO-Developer-Token: $SOURCE_REFRESH" -o /tmp/<filename>

# 2. Upload to target (multipart)
curl -s -X POST "https://$TARGET_HOST/api/data/v1/data-files" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" \
  -F "file=@/tmp/<filename>;type=<content-type>"
# → {"dataFileId": <new_id>}

# 3. Create document card
curl -s -X POST "https://$TARGET_HOST/api/content/v1/cards?pageId=<target_viewId>" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  -d '{
    "type": "document",
    "description": "<source metadata.title>",
    "metadata": {
      "title": "<source metadata.title>",
      "documentId": "<new_dataFileId>:undefined",
      "usingSampleData": "",
      "kpiType": "document",
      "description": "<source metadata.title>"
    }
  }'

# 4. Position on layout per surgical mutation recipe above
```

### Gotcha: `metadata.title` MUST be filename-style

Simple titles ("Banner", "Test") return HTTP 400 — the title is parsed for an extension. Use source's exact `metadata.title` (`Executive Summary.png`, `Domo-Terra-Properties Deck.pdf`) for byte-for-byte fidelity.

### Validated examples (PE Ops, 2026-05-14)

| Source page | Source docId | Source title | Target urn | Position |
|---|---|---|---|---|
| Exec Summary | 1658 | `Executive Summary.png` | 1536641002 | (0,0,30,12) |
| Property Details | 1659 | `Gemini_Generated_Image_3am64g3am64g3am6.png` | 800746631 | (0,0,40,19) |
| Ops Cmd | 1660 | `Gemini_Generated_Image_3am64g3am64g3am6 (1).png` | 1117497855 | (0,0,38,19) |
| Demo Assets | 1661 | `Domo-Terra-Properties Deck.pdf` | 1409425567 | (0,0,60,58) |

## Card variable + control wiring

Defer to `variable-creation` for the 5-step canonical flow. Notes specific to cross-instance clones:

1. **`community-domo-cli variables create`'s step 4 has a bug**: the CLI's internal `_read_card_definition` returns 400 where direct curl with identical body returns 200 on some target cards. Workaround: do steps 1-3 via CLI, step 5 manually via curl with the merged body.

2. **Beast Mode formula rewrites**: any source BM containing `DOMO_BEAST_MODE(<src_templateId>)` must have that reference rewritten to the target variable's templateId before being applied to the target card. Walk the source card's `formulas[]` and rewrite `formula` strings before re-embedding as card-level BMs.

3. **Page-binding endpoint is session-bound**: `PUT /api/content/v1/variable/controls/PAGE/<viewId>` is the captured endpoint that adds the variable's pill to a view, but direct token-auth replay returns 400 even with the byte-identical captured body. It requires App Studio editor session state.

   **Endpoint body shape** (for the audit trail):
   ```json
   {
     "urn": "<globalControlId>",
     "entityType": "PAGE",
     "entityId": "<viewId>",
     "function": { /* full function definition with checkSum, lastModified, created */ },
     ... rest of the control fields
   }
   ```

   **Manual-task workaround**:
   ```
   [target instance] Open <dataapp URL> → Controls → drag <variable name> onto <view> → Save.
   ```
   That fires the captured PUT and creates the page-scoped control instance + corresponding layout VARIABLE content entry.

## Card UPDATE recipe (definition-driven)

See [SKILL.md Section 11](../../skills/domo-cross-instance-clone.md#section-11--native-kpi-cards) for the full canonical recipe. Two corrections to the existing `card-creation` skill that are critical for cross-instance work:

1. **Keep `definition.modified` and `definition.allowTableDrill`** on UPDATE. The skill says to remove them; empirically removing them breaks the UPDATE.

2. **`formulas` read-list must be re-emitted as `formulas.card[]` on write**, not just converted to the wrapper `{dsUpdated, dsDeleted, card}` shape with empty `card`. Emptying `card[]` orphans any `formulaId` reference in main subscription → 400 "The following formula(s) are missing from the definition or datasource". Re-emit every source BM as a card-level BM with `persistedOnDataSource: false`.

## Why the original skill marked these UNVERIFIED

The original clone-content skill explicitly refused to write App Studio bodies because the POST/PUT shapes hadn't been sniffed yet. Two reasons that's now resolved:

1. The user captured the App Studio "Save with new tab" PUT against source-instance during the PE Ops clone (the body in §Unified dataapp PUT body shape).
2. The layout PUT was tried empirically — first attempts failed with rebuilt bodies (which is what the prior skill version implied was correct), then succeeded with surgical mutation.

The lesson: refuse-without-capture is the wrong default when the cost of trial-and-error is bounded and reversible. The new default in clone-content is "try surgical mutation first, fall back to manual task only when the endpoint genuinely requires session state".
