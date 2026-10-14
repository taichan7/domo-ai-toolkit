# Domo Scheduled Reports

Use this skill to reason about — or drive via REST — Domo **Scheduled Reports**: the feature that emails a rendered Dashboard/page/card to a recipient list on a recurring cadence (Admin → *Scheduled Reports*). The surface is a **single-world, fully-inventoried OpenAPI island**: one spec (`scheduled-reports-api.yaml`, "Scheduled Reports API" v1.0.0), one host `https://{instance}.domo.com`, one auth header `X-DOMO-Developer-Token`, everything under `/api/content/v1/reportschedules` — **31 operations across 27 path templates**, every op `[DOC]`, **zero repo precedent** (the yaml is not even in this repo; it was read by WebFetch only).

**Read the naming-trap table below before anything else.** The words "report" and "schedule" each collide with several unrelated Domo concepts, and this feature was, until this skill, an explicit **orphan** that `domo-alerts.md` deliberately left unowned. Conflation is the #1 hazard here — not endpoint mechanics. And a second, subtler hazard: the island is **broad but shallow** — the full operation *inventory* is charted, but most request/response *behavior* is undocumented in the spec. Guard hard against letting an inferred behavior harden into a documented contract.

## The naming-trap table — read this first

Conflation is the #1 hazard on this surface. Match the phrase in front of you to a row *before* you reason about it.

| Phrase / token you'll see | What it means on THIS surface | The collision to NOT make | Owned by |
|---|---|---|---|
| alert Action **"Send a Scheduled Report"** | an **alert** action-type that fires a report when an alert trips — configured on the *alert*, not here | NOT an operation of this API; it is alert-side wiring that may merely *reference* a report action via `alertActionId` | `domo-alerts.md` owns the Action; **this skill** owns the report object/REST it points at |
| "**report**" (a *scheduled* report) | a **ReportSchedule**: a saved recurring email of a Dashboard/page/card | NOT a Beast-Mode/analyzer "report", NOT a Dataset/DataFlow output, NOT marketdata `*_report_*` columns, NOT news-summary `report_month`/`application_summary`, NOT dataset-exporter `FY68SepMDMonthlyReport` | this skill |
| "**schedule**" | either the cadence sub-object (`ReportSchedule`: frequency/daysToRun/hourOfDay/…) or a saved report row (`ReportScheduleItem`) | NOT a Dataset/DataFlow update schedule, NOT soccer `scheduleSlotLayout`, NOT a Workflow / Task-Center queue timer | this skill |
| `type` (on `ReportScheduleItem`) | a **bare string, no enum** on the read model | NOT a cadence; `RECURRING`/`DAILY`/`WEEKLY`/`MONTHLY` are example/UI words, never an enumerated contract | this skill |
| `sendnow` vs `sendNow` | **two different operations** distinguished only by casing (`sendReportNow` by scheduleId vs `sendReportNowByViewId` by viewId) | do not treat them as one path or as a typo | this skill |
| `scheduled_report` (asset-lifecycle governance flag) | an app's internal governance boolean | NOT this API | asset-lifecycle app |

## What this skill owns (and what it defers)

| Concern | Owner | Note |
|---|---|---|
| the ReportSchedule REST surface (all 31 ops, 9 schemas, host/auth) | **this skill** | fully inventoried below |
| the scheduled-report OBJECT model (what a scheduled report *is*) | **this skill** | adopted from the orphan `domo-alerts.md` explicitly left unowned |
| alert **Action** "Send a Scheduled Report" (the alert-side wiring) | `domo-alerts.md` | stays there — it is an alert action-type, not a report op |
| the DOC-level seam between the two | shared | `ResourceSendNowInfo.alertActionId` (int) is the ONLY spec-level reference from a report op back to an alert action |
| the page/view a report renders (`pageId`, `viewId`) | `domo-pages.md` | this skill only carries the ids as params; it does not model pages |
| identity / roles / scopes of the caller | `domo-identity-access.md` | but note this API declares **no OAuth scope at all** (see Auth) |

## Evidence tiers

- `[DOC]` — first-party contract, read verbatim from the OpenAPI spec `scheduled-reports-api.yaml` (domo.com/docs/openapi/product). Authoritative for *shape*; silent on much *behavior*.
- `[KB]` — Domo product behavior (help articles, admin UI). A `domo.com/docs/s/article/<digits>` page is a Salesforce KB = `[KB]`, never `[DOC]`.
- `[REPO]` — verified against working code in THIS repo. **For this surface there is NONE**: no file calls these endpoints and the yaml is not vendored here.
- `[INFER]` — reasoned, including inferred-from-absence. A fetch failure (405 / JS-gate / login-wall) is MISSING evidence, never proof of absence.

## Verification provenance

Skill-ized after a 13-agent doc-cross-check + adversarial-verify workflow (6 clusters × verify+refute, a completeness critic, an island verdict), plus two targeted YAML fetches — one to extract the read-models the summarizer had left uncharted, one to enumerate all 27 paths / 31 operations exhaustively. **Island verdict: a LARGE / BROAD but FULLY-INVENTORIED-ONLY documented island** — the operation *catalog* is complete and trustworthy; per-operation *behavior* mostly is not. Everything below is `[DOC]` unless tagged otherwise. The spec was reachable ONLY via WebFetch (it is not vendored in the repo), so treat field-level detail as spec-accurate but **verify live before depending on any behavior the spec does not state**.

## The documented island: host, auth, base path

- **Spec** `[DOC]`: `scheduled-reports-api.yaml`, OpenAPI 3.1.0, title *"Scheduled Reports API"*, version 1.0.0 (~39.7 KB). URL: `https://www.domo.com/docs/openapi/product/scheduled-reports-api.yaml`.
- **Host** `[DOC]`: single server `https://{instance}.domo.com` (server variable `instance`, spec default `YOUR_INSTANCE`). No `api.domo.com` twin is declared *in this spec*; whether a Platform-scoped twin exists anywhere else is `[INFER]` (unproven — do not assert its absence as fact).
- **Auth** `[DOC]`: exactly ONE declared scheme — `DomoDeveloperToken` = `apiKey` in `header`, name `X-DOMO-Developer-Token`. Some operations carry `security: []` (declared open), but there is **no OAuth flow and no scope enum anywhere in the spec**. This is the Product-instance auth world (same as the pages/accounts REST islands), NOT the Platform `api.domo.com` OAuth-Bearer world. Whether a caller additionally needs a specific role/grant is `[INFER]` — verify live.
- **Base path** `[DOC]`: `/api/content/v1`; every one of the 27 path templates begins with `/reportschedules`, so the shared prefix is `/api/content/v1/reportschedules`.

## The 31 operations (fully inventoried, contracts uncharted)

**31 operations across 27 path templates** `[DOC]`. Two paths carry three methods each (`/reportschedules` and `/reportschedules/{scheduleId}`); the other 25 are single-method. Every operationId below is verbatim from the spec. **Response schemas are largely unstated** — the delivery ops that return `202` are `[DOC]`; most read responses have no declared schema, so their body shapes are `[INFER]`.

### 1. Schedule CRUD (6 ops, 2 paths)

| Method + path | operationId | body / key params |
|---|---|---|
| GET `/reportschedules` | `listReportSchedules` | query: filter="USER", title, limit=0, skip=0, orderBy="startDate", isAscending=false |
| POST `/reportschedules` | `createReportSchedule` | body `ReportScheduleInfo` |
| DELETE `/reportschedules` | `deleteReportScheduleByPageId` | ⚠ query `pageId` (int, **required**) — NO scheduleId (Anomaly 1) |
| GET `/reportschedules/{scheduleId}` | `getReportScheduleById` | path scheduleId |
| PUT `/reportschedules/{scheduleId}` | `updateReportSchedule` | path scheduleId; body `ReportScheduleInfo` |
| DELETE `/reportschedules/{scheduleId}` | `deleteReportSchedule` | path scheduleId (by-id delete) |

### 2. Discovery & render reads (6 ops)

| Method + path | operationId | body / key params |
|---|---|---|
| GET `/reportschedules/views/{viewId}` | `getReportScheduleByViewId` | path viewId |
| GET `/reportschedules/resources` | `getResourcesWithReports` | query: limit=100, skip=0, title |
| GET `/reportschedules/resources/{resourceType}/{resourceId}` | `getReportSchedulesByResourceId` | path resourceType (enum `OPEN\|PAGE\|CARD\|REPORT`), resourceId; query showAll=false |
| GET `/reportschedules/sortby` | `getReportSchedulesMap` | same query set as `listReportSchedules` (a keyed "map" variant) |
| GET `/reportschedules/misconfigured` | `getMisconfiguredReports` | query: limit=100, skip=0 |
| POST `/reportschedules/card-email-data` | `renderCardForEmail` | body `integer[]` (card ids) → `CardEmailData` |

### 3. Enable toggles (2 ops)

| Method + path | operationId | body / key params |
|---|---|---|
| PUT `/reportschedules/{scheduleId}/enabled` | `setReportScheduleEnabled` | path scheduleId; body `boolean` (per-schedule) |
| PUT `/reportschedules/emails/enabled` | `setScheduledReportEmailsEnabled` | body `boolean`; **NO scheduleId** — company/global scope `[INFER]` |

### 4. Send / deliver now (6 ops — all return `202` `[DOC]`)

| Method + path | operationId | body / key params |
|---|---|---|
| POST `/reportschedules/{scheduleId}/sendnow` | `sendReportNow` | path scheduleId; body `ReportScheduleRecipient[]` |
| POST `/reportschedules/{scheduleId}/queue` | `queueReportNow` | path scheduleId; body `ReportScheduleRecipient[]` |
| POST `/reportschedules/{scheduleId}/notifications` | `buildAndEmailReport` | path scheduleId; body `ReportRecipient[]` |
| POST `/reportschedules/{scheduleId}/notifications/queue` | `queueBuildAndEmailReport` | path scheduleId; body `ReportRecipient[]` |
| POST `/reportschedules/views/{viewId}/sendNow` | `sendReportNowByViewId` | path viewId; query attachmentInclude; body `ReportScheduleRecipient[]` |
| POST `/reportschedules/views/{viewId}/sendNowWithParams` | `sendReportNowWithParamsByViewId` | path viewId; query attachmentInclude; body `ResourceSendNowInfo` |

The `sendnow`/`queue` pair and the `notifications`/`notifications/queue` pair read as immediate-vs-queued twins, but the spec never states the difference — immediate-vs-queued semantics are `[INFER]`. The two `notifications*` ops take `ReportRecipient[]`; the four `send*now*` ops take `ReportScheduleRecipient[]` (a different shape — see Object model).

### 5. Subscription management (4 ops)

| Method + path | operationId | body / key params |
|---|---|---|
| POST `/reportschedules/{scheduleId}/resubscribe` | `resubscribeToReport` | path scheduleId; query userId, emailId (targets a specific recipient) |
| POST `/reportschedules/{scheduleId}/unsubscribe` | `unsubscribeFromReport` | path scheduleId only (reads as self-unsubscribe `[INFER]`) |
| DELETE `/reportschedules/{scheduleId}/unsubscribe/recipient` | `deleteUnsubscribedRecipient` | path scheduleId; query userId, emailId (targets a specific recipient) |
| POST `/reportschedules/{scheduleId}/sendResubscribe` | `sendResubscribeEmail` | path scheduleId; body `ReportScheduleRecipient[]`; returns `202` |

Self-vs-other and email-vs-userId targeting semantics beyond the params shown are `[INFER]`.

### 6. History, logs & failure recovery (7 ops)

| Method + path | operationId | body / key params |
|---|---|---|
| GET `/reportschedules/{scheduleId}/history` | `getReportHistoryByScheduleId` | path scheduleId; query limit=100, skip=0 |
| GET `/reportschedules/history` | `getReportHistory` | query filter="USER", limit=100, skip=0, orderBy="startTime", isAscending=false, includeRecipientInfo=false |
| GET `/reportschedules/history/{id}` | `getReportHistoryById` | path id |
| POST `/reportschedules/history/search` | `searchReportHistory` | body `ReportLogSearchCriteria`; ALSO query filter="USER", limit=100, skip=0, orderBy="startTime", isAscending=false |
| GET `/reportschedules/created` | `getCreatedReportHistory` | query filter="USER", days=10, isAscending=false |
| GET `/reportschedules/extendedHistory` | `getExtendedReportHistory` | query filter="USER", days=10, orderBy="startTime", isAscending=false |
| POST `/reportschedules/failures/rerun` | `rerunFailedScheduledReports` | query start (int, **required**), end (int, **required**) — epoch-ms window `[INFER]` |

## The object model (9 schemas)

All field types/names are `[DOC]`; semantics beyond the name are `[INFER]` unless noted. No schema declares `required` or `readOnly` unless stated.

**`ReportSchedule`** — the cadence sub-object (nested as `schedule` inside BOTH `ReportScheduleInfo` and `ReportScheduleItem`; it is NOT unreferenced). 8 props: `frequency` (string, **no enum**), `daysToRun` (string, **no enum**), `hourOfDay` (int), `minOfHour` (int), `timezone` (string), `enabled` (bool), `nextRunDate` (int, "Epoch milliseconds"), `additionalRecipients` (`ReportScheduleRecipient[]`).

**`ReportScheduleInfo`** — write body of POST `/reportschedules` and PUT `/{scheduleId}`. 5 props: `title` (string), `pageId` (int), `viewId` (int), `schedule` (`ReportSchedule`), `attachmentInclude` (bool).

**`ReportScheduleItem`** — read/response model. 13 props: `id` (int), `reportViewId` (int), `pageId` (int), `title` (string), `viewName` (string), `type` (string, **no enum** — this is where `RECURRING` etc. show up), `ownerId` (int), `embedViewId` (int), `owner` (bool), `cardCount` (int), `recipientCount` (int), `cardId` (int), `schedule` (`ReportSchedule`).

**`ReportScheduleRecipient`** — `type` (enum: `[EMAIL]`, single member), `value` (string). Body element for the four `send*now*` ops and `sendResubscribe`.

**`ReportRecipient`** — `userId` (int), `displayName` (string), `emailAddress` (string, format email). Body element for the two `notifications*` ops. A richer shape than `ReportScheduleRecipient` — do not swap them.

**`ReportHistoryEntry`** — a history/log row (returned by the history reads). Field list not charted here; treat as opaque until fetched.

**`CardEmailData`** — result of `renderCardForEmail`. **Open object (`additionalProperties: true`)** with 12 known props: `title`, `encodedImage`, `encodedImageId`, `timeframeLabel`, `summaryNumberValue`, `summaryNumberLabel`, `htmlContent`, `cardType`, `cardLink`, `pdpEnabled` (bool), `certified` (bool), `companyCertified` (bool).

**`ResourceSendNowInfo`** — body of `sendReportNowWithParamsByViewId`. 3 props: `recipients` (`ReportScheduleRecipient[]`), `alertActionId` (int — **the one DOC seam to alerts**), `emailParams` (open object, `additionalProperties: true`).

**`ReportLogSearchCriteria`** — body of `searchReportHistory`. 7 props: `includeTitleClause` (bool), `titleSearchText` (string), `includeStatusClause` (bool), `status` (string), `includeTypeClause` (bool), `isAutomated` (bool), `includeScheduleIdClause` (bool).

## High-value anomalies & guards

**Anomaly 1 — `DELETE /api/content/v1/reportschedules` deletes by PAGE, not by id.** `deleteReportScheduleByPageId` takes NO `scheduleId` in the path and a **required `pageId` query param** (int), no body — e.g. `DELETE .../reportschedules?pageId=345678`. It is a *distinct* operation from the by-id `deleteReportSchedule` (`DELETE /{scheduleId}`). Whether it removes ONE schedule or ALL schedules on that page is **`[INFER]` — treat as a page-context (potentially multi-row) delete and confirm blast radius live before using.**

**Anomaly 2 — `sendnow` vs `sendNow` casing is load-bearing.** `POST /{scheduleId}/sendnow` (lowercase) = `sendReportNow` (by schedule id); `POST /views/{viewId}/sendNow` (camelCase) = `sendReportNowByViewId` (by view id). Different path, different key, different id space. Not a typo, not interchangeable.

**Two independent enable levers.** `setReportScheduleEnabled` toggles ONE schedule (`/{scheduleId}/enabled`); `setScheduledReportEmailsEnabled` toggles emails with NO scheduleId (`/emails/enabled`) — almost certainly a company/global kill-switch, but its scope is `[INFER]`. Do not assume toggling one affects the other.

**Recipient shape depends on the op.** `send*now*`/`sendResubscribe` take `ReportScheduleRecipient` (`{type:[EMAIL], value}`); `notifications*` take `ReportRecipient` (`{userId, displayName, emailAddress}`). Sending the wrong shape is the most likely silent 4xx.

## Open questions (need a live probe or a KB harvest — do NOT present as settled)

- **`deleteReportScheduleByPageId` cardinality** — one schedule vs all on the page.
- **`setScheduledReportEmailsEnabled` scope** — per-user vs company-global kill-switch.
- **immediate vs queued** — the real difference between `sendnow`/`queue` and `notifications`/`notifications/queue`.
- **subscription semantics** — self vs other, and email-vs-userId targeting, for resubscribe/unsubscribe.
- **frequency / daysToRun grammar** — both are bare strings with NO enum; the accepted token vocabulary is unknown.
- **`rerunFailedScheduledReports` window** — `start`/`end` are ints, presumably epoch-ms, unconfirmed.
- **attachment format** — the word "PDF" does NOT appear in the spec; `attachmentInclude` is a bool with no stated format.
- **response schemas** — most reads' response bodies are unstated in the spec.

## Guards — do NOT claim as documented fact

1. **Do NOT** enumerate `frequency` values — `DAILY`/`WEEKLY`/`MONTHLY`/`RECURRING` are UI/example words; `frequency` is a bare string with NO enum.
2. **Do NOT** enumerate `daysToRun` values — also a bare string, no enum.
3. **Do NOT** attribute `type: RECURRING` to the `schedule` sub-object — `type` lives on `ReportScheduleItem` (the read model) and is itself an enum-less string.
4. **Do NOT** say reports are delivered as "PDF" — the word "PDF" is not in the spec; `attachmentInclude` is a bool with no stated format.
5. **Do NOT** state the scope of `setScheduledReportEmailsEnabled` (per-user vs company) — `[INFER]`.
6. **Do NOT** state that `sendnow`/`notifications` are synchronous or that the `queue` variants are asynchronous — the difference is unstated (`[INFER]`).
7. **Do NOT** state subscription self-vs-other or email-vs-userId semantics beyond the params shown — `[INFER]`.
8. **Do NOT** state whether `deleteReportScheduleByPageId` removes one schedule or all on the page — `[INFER]`.
9. **Do NOT** assert "there is no `api.domo.com` twin" as fact — the spec's silence is `[DOC]` only *within this spec*; platform-wide absence is `[INFER]`.
10. **Do NOT** call this surface "well-charted" — it is fully *inventoried* but its per-op behavior is *uncharted*.
11. **Do NOT** cite any operation as `[REPO]` — repo precedent is ZERO; the yaml is not vendored here; every op is `[DOC]`-never-`[REPO]`.
12. **Do NOT** treat `sendnow` and `sendNow` as the same operation.
13. **Do NOT** swap `ReportScheduleRecipient` and `ReportRecipient` — they are different shapes used by different op families.
14. **Do NOT** claim an OAuth scope gates this API — the spec declares no OAuth flow and no scope; only `X-DOMO-Developer-Token` (and some `security: []`) appear.
15. **Do NOT** trust summarizer totals ("37 ops", "8 schemas") — the verified enumeration is 31 ops / 27 paths / 9 schemas.
16. **Do NOT** present any response-body schema as known unless it carries a `$ref` in the spec — most reads' responses are unstated.

## Cross-skill seams

- **`domo-alerts.md`** — the alert Action "Send a Scheduled Report" stays owned there (it is an alert action-type). The ONLY spec-level (`[DOC]`) reference from this surface back to alerts is `ResourceSendNowInfo.alertActionId` (int), used by `sendReportNowWithParamsByViewId`. The alert-Action → report-REST linkage as a *workflow* is `[KB]`, not `[DOC]` — do not assert a call graph the spec does not show.
- **`domo-pages.md`** — a scheduled report renders a page/view; this surface carries `pageId` / `viewId` / `reportViewId` / `embedViewId` as ints but does not model pages. The `resourceType` enum (`OPEN|PAGE|CARD|REPORT`) is the bridge vocabulary.
- **`domo-identity-access.md`** — caller identity/roles live there. Note the divergence: that surface is Platform OAuth-scoped; THIS surface declares only the Product `X-DOMO-Developer-Token` and no scope.
- **False friends (all `[REPO]`, NONE related to this API):** marketdata `realized_pnl_after_reported_exit_fees_usd`; dataset-exporter `FY68SepMDMonthlyReport`; news-summary `report_month` / `application_summary`; inventory-management report-ish test names; safety-command-center tokens; soccer `scheduleSlotLayout`; asset-lifecycle `scheduled_report` governance flag. None of these touch `/api/content/v1/reportschedules`.
