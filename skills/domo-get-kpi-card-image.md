# Domo Get KPI Card Image

Operating notes for the **Domo "Get KPI Card Image API"** — a tiny **single-operation** surface that server-side **renders a KPI card** into a caller-selected mix of parts (image, PDF, structured data, and metadata) and returns them **base64-encoded** (`PUT /api/content/v1/cards/kpi/{urn}/render`). Read this before touching any `/api/content/v1/cards/kpi/{urn}/render` call, or any code mentioning `ChartRequest`, `ChartResponse`, the render `parts` enum (`title`/`chartType`/`queryResult`/`data`/`image`/`imagePDF`/`graph`/`dynamic`/`summary`/`summaryImage`/`dataSource`/`pdp`/`annotations`/`extendedDateInfo`/`table`), `queryOverrides`/`treatLongsAsStrings`/`cardLoadContext`, or any "render a card to image/PDF" flow. It reads a card's **live data** and emits it off-platform as decodable bytes — treat every call as a **data-egress read** (see Safety & hygiene).

## What this skill owns (and defers)

- **Owns**: the REST **Get KPI Card Image API** surface — the first-party candidate spec `get-kpi-card-image-api.yaml` (info.title "Get KPI Card Image API", info.version 1.0.0, OpenAPI 3.1.0), host `https://{instance}.domo.com`, auth `X-DOMO-Developer-Token`, the single path+op `PUT /api/content/v1/cards/kpi/{urn}/render` (op "Render KPI Card Chart or Table"), and the `CardURNParam` / `ChartRequest` / `ChartResponse` schemas.
- **Defers**: KPI card **CREATE / UPDATE / read-definition** (`PUT /api/content/v3/cards/kpi`, `.../kpi/{urn}`, `.../kpi/definition` — **v3**, `[REPO]` in `domo-cross-instance-clone.md` + `../docs/reference/app-studio-clone.md`) → `domo-cards.md` / `domo-appstudio.md`. Card **DATA-query** (`POST /api/query/v1/execute/{cardId}`) → `domo-cards.md`. Card **LIST** + the card-metadata `parts` param (`GET /api/content/v1/cards?parts=…`, `GET /api/content/v1/pages/{id}/cards?parts=metadata,properties,chartMetadata`) → `domo-cards.md` / `domo-pages.md`. **Live interactive embed** (Domo Everywhere) → `domo-everywhere.md` / `domo-procode-embedded-cards.md`. **Scheduled-report PDF/exports** (the other `/api/content/v1/` sibling, `/reportschedules`) → `domo-scheduled-reports.md`. Token / SID minting → `domo-identity-access.md`.

## Evidence tiers

Every claim below carries a tier. Do not silently upgrade a tier.

```
[DOC]  = developer.domo.com page / OpenAPI YAML under domo.com/docs/openapi / dev-portal API-Reference page / first-party SDK.
         (A domo-support.domo.com/s/article/<digits> = Salesforce KB = [KB], NOT [DOC].)
[KB]   = Domo Knowledge Base article / documented product behavior.
[REPO] = verified against this repo's actually-running code (a real caller, not dead scaffolding).
[INFER]= reasoned / inference-from-absence / spec-author-assumed.
```

Rules: a fetch FAILURE (405 / JS-gated / login-wall / 404 / timeout) is MISSING evidence, NOT proof of absence. Universal negatives ("no other op exists", "the enum is closed", "SID is rejected", "no divergent mirror anywhere") are `[INFER]` unless a doc positively says so. Prefer positive phrasing. The single guarded failure mode is **over-claiming** — presenting a spec quirk or an unverified assumption (the `urn` id-scheme, enum closedness, the response array's positional meaning, the open body's contract, error codes, auth exclusivity) as documented Domo fact.


## Naming traps (read first)

Conflation is the #1 hazard: `parts` is an overloaded query-param name across the content API, and `/api/content/` is a heavily-shared root spanning versions and resources.

| you see | reality |
|---|---|
| `parts` on render **and** `parts` on GET cards | **DIFFERENT enums, different operations, same param NAME.** render `PUT .../kpi/{urn}/render?parts=` takes a **15-value** enum (`title`/`chartType`/`queryResult`/`data`/`image`/`imagePDF`/`graph`/`dynamic`/`summary`/`summaryImage`/`dataSource`/`pdp`/`annotations`/`extendedDateInfo`/`table`) `[DOC]`; the repo's `GET /api/content/v1/pages/{id}/cards?parts=metadata,properties,chartMetadata` `[REPO]` and `GET /api/content/v1/cards?parts=…` take a DISJOINT card-metadata enum. A render `parts` value on a GET (or vice-versa) is invalid — do NOT cross-wire. |
| render `dataSource` ≈ GET `datasources`; render `extendedDateInfo` ≈ GET `dateInfo` | **Near-miss false friends.** render's part `dataSource` (camelCase, singular) is one of the 15 render parts; a card-metadata `datasources` (lowercase, plural) belongs to the GET-cards enum. Same for render `extendedDateInfo` vs any GET `dateInfo`. Near-identical spelling, DIFFERENT enums. |
| `renderKpis(...)` in an `app.js` | **False friend — no API call.** `renderKpis()` (`pl-summary-app`/`safety-command-center`/`equipment-analytics-app` `app.js`) is CLIENT-SIDE JS that paints KPI tiles into the app's own DOM `[REPO]`. Nothing to do with this render ENDPOINT. |
| render == the `cards/kpi` you already call | **Version + verb split.** render is **v1** `PUT /api/content/v1/cards/kpi/{urn}/render` (returns bytes) `[DOC]`; KPI card CREATE/UPDATE/read-definition is **v3** `PUT /api/content/v3/cards/kpi{,/definition,/{urn}}` `[REPO]` (`domo-cross-instance-clone.md`, `../docs/reference/app-studio-clone.md`). Same `cards/kpi` substring, different version + purpose. Do NOT normalize v1↔v3. |
| render "returns a static PNG" (as other skills phrase it) | **Over-simplification — correct it.** `domo-cards.md`, `domo-procode-embedded-cards.md`, `domo-appstudio.md`, `domo-everywhere.md` describe render as a "static PNG/image." That holds ONLY for the common `image`/`summaryImage` part; the 15-part enum can ALSO yield a **PDF** (`imagePDF`), **structured data** (`data`/`table`/`queryResult`), and **metadata** (`chartType`/`summary`/`dynamic`/`annotations`/`pdp`/`dataSource`/`extendedDateInfo`). "PNG only" understates the surface (Do-NOT #4). |
| `{urn}` is the numeric card id | **UNSPECIFIED `[INFER]`.** `urn` is a REQUIRED opaque string with NO `format` constraint `[DOC]`; the "URN" vocabulary implies an opaque resource name, so "urn ≡ the card id" is `[INFER]` — the v3 card-authoring siblings DO use `{urn}` for a card id (plausible, not documented for render) → verify live (Do-NOT #1). |
| info tag `card-kpi-resource` vs op tag `Get KPI Card Image API` | Cosmetic first-party spec quirk: `info.description` names the tag `card-kpi-resource`, the operation self-tags `[Get KPI Card Image API]`. Present faithfully in the published YAML, no runtime meaning — don't treat either as an API contract. |
| the 200 example base64 `aSDinaTvuI8gbWludGxpZnk=` | Decodes to **"i love mintlify"** — a Mintlify doc-platform placeholder (the docs portal is Mintlify-built), NOT a real render payload. Do not treat it as a response-shape sample. |

## The surface, in one line

A **doc-convergent single-world small island** (1 path `/api/content/v1/cards/kpi/{urn}/render`, 1 op PUT, 1 host `{instance}.domo.com`, 1 auth `X-DOMO-Developer-Token`) that is distinctively **INPUT-mandatory-yet-opaque + OUTPUT-opaque**: the request body is REQUIRED but `additionalProperties:true` (OPEN — the 3 named props `queryOverrides`/`treatLongsAsStrings`/`cardLoadContext` are typeless-and-description-free, NOT a complete contract), and the 200 response is an untyped positional `{data:[base64…]}` array **whose very shape the sole first-party consumer contradicts** by reading NAMED keys (`pdf.title`/`pdf.image`) and decoding only the image part. The mirror is **found-and-convergent** (published YAML + HTML API-reference + a Pro-Code PDF tutorial all agree on auth/host/path/15-enum/body) but only **semantically** — byte-identity is UNVERIFIED (WebFetch normalizes) — and "no divergent App-Framework twin exists anywhere" is `[INFER]`, not proven absence. **Contrast rank-21** (byte-identical hash-confirmed mirror, 2 CONFIRMED verdicts): this island is a rung less nailed — **0 CONFIRMED verdicts**, semantic-equivalence not hash-identity. Zero callers in repo → all runtime/response behavior is `[DOC]`/`[INFER]`-never-`[REPO]`, 0 executed calls.

## Operations (1 path, 1 op — `[DOC]`)

| # | op | method + path | request | 200 body | error codes |
|---|---|---|---|---|---|
| 1 | Render KPI Card Chart or Table | `PUT /api/content/v1/cards/kpi/{urn}/render` | path `urn` (REQUIRED, opaque string); query `parts` (REQUIRED, `style:form` `explode:false` → **comma-joined** `parts=title,data,image`, `uniqueItems:true`, 15-value enum); query `locale` (optional); **REQUIRED body** `ChartRequest` (OPEN) | `ChartResponse` = `{data: array<string, format:byte>}` (base64) | documents **200 / 403 / 409** ONLY |

Notes: `parts` is `explode:false` form-style → serialize as ONE comma-joined query value (`parts=title,data,image`), not repeated `parts=` keys `[DOC]`. `403` = the client lacks the permission to access the resource; `409` = a conflict with the target resource's current state — both are generic RFC-7231 boilerplate (Do-NOT #6). Only these three codes are DOCUMENTED; the 4xx/5xx surface is otherwise UNCHARTED (401/404/400 near-certain, `[INFER]`).

## Schemas (shapes `[DOC]`; the opacity + response-shape tension are the story)

- **`CardURNParam`** — `type: string`, "the unique resource name (URN) of the KPI card to be rendered." REQUIRED as the `{urn}` path param. **NO `format`** → the id-scheme (opaque urn vs the numeric card id) is `[INFER]` (Do-NOT #1).
- **`ChartRequest`** (REQUIRED body) — `type: object`, **`additionalProperties: true` (OPEN)**. Three named props, ALL shallow/typeless and **description-free**: `queryOverrides` (object, `additionalProperties:true` — open), `treatLongsAsStrings` (boolean), `cardLoadContext` (object, open). Documented example `{queryOverrides:{}, treatLongsAsStrings:true, cardLoadContext:{}}`. Because the body is OPEN and the props carry zero declared semantics, the 3 props are NOT the complete contract (Do-NOT #11) — the empty-valued example is the only concretely-safe body `[DOC]`; anything richer is `[INFER]`.
- **`ChartResponse`** (200 body) — `type: object`, ONE prop `data`: an `array` whose items are `type: string, format: byte` (base64). **No per-part typing, no key names, no length/order contract.** The spec advertises a flat positional array; the sole first-party consumer (the PDF-export tutorial) instead reads **named keys** (`pdf.title`, `pdf.image.pages` / `pdf.image.data`) and base64-decodes ONLY the image part — a genuine doc-vs-consumer SHAPE tension. So `data[i] ↔ parts[i]` positional alignment is REFUTED (Do-NOT #3), and "every element is a base64 image" is `[INFER]` (non-image parts are structured/metadata; Do-NOT #4). Parse the payload by inspection, never by part index.

## Auth & host

- **Auth**: apiKey header **`X-DOMO-Developer-Token`** (securityScheme `DomoDeveloperToken`, global `security` block) — the single declared scheme `[DOC]`, in the dev-portal **Product-API** family (instance dev-token native), NOT the Platform/OAuth (`api.domo.com`/Bearer) or App-Framework (JWT/`/domo/`) families. **Do NOT assert dev-token EXCLUSIVITY** and **do NOT assert a session SID works** on this path — both are unsupported (dev-token is `[DOC]`; exclusivity + SID-here are `[INFER]`; content-API family precedent — the repo's `/api/content/v1/...` callers all ride an OAuth→SID session `[REPO]` — LEANS toward SID also working here, but render has 0 callers). Hard-code dev-token; claim neither negative (Do-NOT #5).
- **Host / base path**: `https://{instance}.domo.com` + `/api/content/v1/cards/kpi/{urn}/render` — the server block, convergent across all three renderings `[DOC]`. Shares the `/api/content/v1/` ROOT with rank-14 Scheduled Reports (`/reportschedules`), card LIST (`/cards`), DataApps (`/dataapps`), and users (`/users/me`) — **but render is NESTED inside the `cards/kpi` namespace, ZERO literal path collision** (method + full-path templates all differ). Do NOT normalize v1→v3.

## Repo precedent = ZERO

Executed-call count for render = **0**. No running code calls `/api/content/v1/cards/kpi/{urn}/render` or references `ChartRequest` / `ChartResponse` / the 15-part enum. Every `/api/content/` grep hit is a FALSE FRIEND (same root/namespace, different resource) — so each is `[DOC]`/`[INFER]`-never-`[REPO]` for render:

1. **card LIST** `GET /api/content/v1/cards?parts=…` (`equipment-analytics-app`/`domo-support/new/support-center`/`pl-summary-app` `provision_domo.py`) — shared root, the card-metadata `parts` enum (NOT render's).
2. **page-cards + the `parts` false friend** `GET /api/content/v1/pages/{id}/cards?parts=metadata,properties,chartMetadata` (`provision_domo.py:603` / `:1450` / `:1727`) — the `[REPO]` PROOF that `parts` is overloaded across content-API ops with DISJOINT value sets.
3. **DataApp CRUD** `GET`/`POST /api/content/v1/dataapps` + `GET /api/content/v1/dataapps/{id}` — App Studio DataApps, not cards.
4. **page layout** `GET`/`PUT /api/content/v4/pages/layouts/{id}` + `/writelock` — v4, pages.
5. **identity** `GET /api/content/v2/users/me` — v2.
6. **v3 card authoring** `PUT /api/content/v3/cards/kpi` / `.../kpi/{urn}` / `.../kpi/definition` (`domo-cross-instance-clone.md`, `../docs/reference/app-studio-clone.md`) — the version-split sibling (create/update/read-definition), NOT render.
7. **`renderKpis()` client JS** (`pl-summary-app`/`safety-command-center`/`equipment-analytics-app` `app.js`) — a NAME false friend; paints KPI tiles into the app's own DOM, no HTTP.

Every op is `[DOC]`/`[INFER]`-never-`[REPO]`.

## Do NOT claim as documented fact

1. Do NOT hard-code `{urn}` as the numeric card id. `urn` is a REQUIRED opaque string with NO `format` constraint `[DOC]`; "urn ≡ card id" is `[INFER]` (the URN vocabulary implies an opaque name; the v3 card-authoring siblings DO use `{urn}` for a card id, so it is plausible — verify live before assuming). (verdict 1 PARTIAL)
2. Do NOT call the 15-value `parts` enum a documented CLOSED set. The 15 values are documented `[DOC]`; closedness rests on one convergent source + 0 executed calls → `[INFER]`; treat an unknown part value defensively. (verdict 2 PARTIAL)
3. Do NOT assume response `data[i]` positionally aligns with requested `parts[i]`. Positional alignment is not merely undocumented but **actively contradicted** — the sole first-party consumer reads NAMED keys (`pdf.title`/`pdf.image`) `[DOC/INFER]`. Parse by inspecting the payload, not by index. (verdict 3 REFUTED)
4. Do NOT treat every requested part as a base64 IMAGE. `format:byte` is the item type `[DOC]`; the non-image parts (`data`/`table`/`queryResult`/`chartType`/`summary`/`dynamic`/`annotations`/`pdp`/`dataSource`/`extendedDateInfo`) are structured/metadata payloads, NOT PNGs — decode/parse per part, not as a uniform image array. **This is the load-bearing CORRECTION** to the "static PNG only" framing in `domo-cards.md` / `domo-procode-embedded-cards.md` / `domo-appstudio.md` / `domo-everywhere.md`. (verdict 4 PARTIAL)
5. Do NOT assert dev-token EXCLUSIVITY, and do NOT assert a session-SID works, on this path — both unsupported (dev-token `[DOC]`; both `[INFER]`; family precedent leans SID-also-works, but render has 0 callers). Hard-code dev-token; claim neither. (verdict 5 PARTIAL)
6. Do NOT read "200/403/409 documented" as the COMPLETE failure set. Those three are `[DOC]`; 401 (bad/missing token), 404 (unknown urn), 400 (malformed body/parts) are near-certain but UNCHARTED `[INFER]`. (verdict 6 REFUTED)
7. Do NOT assert a divergent App-Framework mirror "exists nowhere." Path-authority + zero-literal-collision are `[DOC]`; "no second-world twin anywhere" is `[INFER]` from a fetch-limited search — render is NESTED inside the cards namespace (not an orthogonal tree), and the portal warns App-Framework APIs share names with Platform APIs (the rank-20 Export divergence pattern). Scope the single-world claim to the located sources. (verdict 7 PARTIAL)
8. Do NOT claim render works on KPI cards ONLY / that "no render exists for other card types." The path is literally `/cards/kpi/` `[DOC]`; whether an analogous render endpoint exists for non-KPI card types is `[INFER]` (unexamined). (verdict 8 PARTIAL)
9. Do NOT conflate render's 15-value `parts` with the card-metadata `parts` on `GET /api/content/v1/cards` / `GET .../pages/{id}/cards` — disjoint enums, different operations, same param NAME (`[REPO]` shows `parts=metadata,properties,chartMetadata` on page-cards). A render part on a GET (or vice-versa) is invalid.
10. Do NOT say render "returns a ready-made PDF." The summary states the base64 parts "can then be **decoded and compiled into a PDF**" — the CLIENT compiles the PDF (as the tutorial does); the endpoint returns base64 parts, not a finished PDF document. `imagePDF` is one requestable part, not a guarantee the whole response is a PDF.
11. Do NOT treat the 3 `ChartRequest` props (`queryOverrides`/`treatLongsAsStrings`/`cardLoadContext`) as the complete request contract. The body is `additionalProperties:true` (OPEN) and the 3 props are typeless/description-free — the empty-valued example is the only concretely-safe body `[DOC]`; any richer body is `[INFER]`.
12. Do NOT tag any part of this surface `[REPO]`. ZERO executed render calls exist; every `/api/content/` repo hit is a false-friend sibling. All runtime/response/error-code claims are `[DOC]`/`[INFER]`, never `[REPO]`.

## Safety & hygiene

**Data-egress READ — NOT destructive; eligible for autonomous documentation-only work, but any LIVE call is an off-platform data read: authorize and scope it.**

- **Data-egress**: render reads a KPI card's **live data** (PDP row-policy enforcement is `[INFER]` here — the Export sibling enforces it, but this spec does not say so) and returns it as decodable base64 (image / PDF / structured rows). A render call moves card contents to wherever the bytes land — treat it as a data-bearing read, not a cosmetic thumbnail. Never log/echo/commit decoded payloads that may carry sensitive rows.
- **Not destructive**: render mutates nothing (`PUT` is a render verb here, not a write) → unlike rank-20 Export / rank-21 Dataset-History this is **eligible for autonomous DOCUMENTATION-only work**; a real invocation is still a live data read (scope to intent; prefer a non-prod card first).
- **Opaque-contract footguns**: the request body is OPEN and its props are undocumented — send the empty-valued example unless a live probe validates a richer body (Do-NOT #11); the response is untyped and the sole consumer reads named keys — parse defensively, never index by part position (Do-NOT #3); non-image parts are not images (Do-NOT #4).
- **Uncharted failures**: only `200`/`403`/`409` documented `[DOC]`; `401`/`404`/`400` are near-certain but `[INFER]` — handle them. `403` = caller lacks card permission; `409` = a state conflict.
- **Secrets / placeholders**: `X-DOMO-Developer-Token` is a credential — never log/commit it. Never paste a real card `urn` / instance hostname into committed artifacts — use `<card-urn>` / `<instance>.domo.com`. **ZERO executed calls** → any first real use should be a low-blast render of a NON-PROD card, live-verifying auth → the `urn` scheme → the real `data` shape (positional vs named) → which codes emit.

## Companion skills

`domo-cards.md` (the KPI card model; card DATA-query `POST /api/query/v1/execute/{cardId}`; card LIST + the GET card-metadata `parts` enum; **its "static image" line is the over-simplification this skill corrects**) · `domo-appstudio.md` + `domo-procode-embedded-cards.md` (the **v3** `cards/kpi` create/update — the version-split sibling; their "static PNG" framing is corrected here) · `domo-everywhere.md` (the live interactive embed render is NOT — its "static image" note) · `domo-scheduled-reports.md` (the other `/api/content/v1/` sibling, `/reportschedules` — scheduled PDF/export delivery) · `domo-identity-access.md` (dev-token / SID minting + the card-render grant).
