# Domo Alerts

Use this when you are creating, reading, listing, deleting, subscribing to, or sharing a Domo **platform Alert** (the thing that watches a Card, DataSet, or Page for a data condition and notifies people or fires an action) — via the UI Alert wizard, the Alert Center, or the `/api/social/v4/alerts` REST surface — **and especially when you have to tell a platform Alert apart from the dozen-plus unrelated things in this workspace and in Domo that are also called "alert" or "notification."** On this surface, conflation is the number-one hazard, so the disambiguation table comes before anything else.

This surface is a **documented island that is only partially charted**. A real Alerts OpenAPI spec exists and was reached (`alerts.yaml`, OpenAPI 3.0.0, title "Alerts API", version 4.0), so the stale community belief "there is no Alerts REST API" is **false**. But the operation set is small (list / get / delete / subscribe / unsubscribe / share — **6 ops, GET-only base path, no create in-spec**), the `200` bodies are bare `type: object` with **no `components.schemas`** (so the complex `actions`/`configurations`/`filterGroups` arrays and the rule/trigger-frequency grammars are genuinely **undefined in-spec**, not merely unfetched), and auth is **spec-declared BearerAuth JWT but live-unresolved**. So this skill is part small-API-map, part heavy disambiguation, and it hedges every under-charted corner rather than guessing a contract.

## What this skill owns (and what it defers)

**Owns:**
1. The **platform Alert** feature end-to-end — Card/Visualization-Card Alerts, DataSet Alerts, the rule/condition model, the Alert wizard, the Alert Center, subscriptions, delivery, and the four Attach-Actions (as the *alert-side* of each).
2. The **Alerts REST API** (`/api/social/v4/alerts`) — list / get / delete / subscribe / unsubscribe / share.
3. **Disambiguating** every "alert"/"notification" term in Domo and in this repo, and routing each to its true owner.

**Defers (do not restate their contracts here — cross-reference):**

| Face | Owner |
|---|---|
| The **Workflow** that an alert Action initiates (the trigger/execution side, workflow versions, start params) | `domo-workflow.md` |
| Workflow **inbound API/HTTP trigger** (a different entry point entirely) | `domo-workflow.md` |
| Beast Mode expressions used inside an alert **rule** | `domo-beast-mode.md` |
| DataSet identity / PDP that scopes what rows an alert can see | `domo-datasets.md` |
| DomoStats / Governance activity datasets whose column values contain the string `alert` | `domo-governance-datasets.md` |
| **Scheduled Reports** (`scheduled-reports-api.yaml`) — the report OBJECT + REST surface (the *alert Action* that sends one stays here) | `domo-scheduled-reports.md` |

## Evidence tiers

```
[DOC]   developer.domo.com API reference / docs-portal OpenAPI or integration pages /
        machine-readable OpenAPI YAML (e.g. alerts.yaml). NOTE: a domo.com/docs/s/article/
        <digits> page (or a support.domo.com / knowledge.domo.com help article) is a KB
        page = [KB], NOT [DOC], even on the docs domain.
[KB]    Domo Knowledge Base / help articles / documented product behavior.
[REPO]  Verified only against THIS repo's working code (app-internal, re-verify per app).
[INFER] Reasoned from the documented model / community / marketing / inference-from-absence.
```

On disagreement, choose the **more conservative** tier. **A fetch FAILURE (405 / JS-gated / login wall) is MISSING evidence, not proof of absence** — never downgrade a positive claim because a *different* page failed to load, and never let a fetch failure be read as confirming a negative. Every "there is no X" on this surface is at best `[INFER]` ("not reached in what we saw"), never fact.

**Verification provenance.** Built from workflow `wf_4ee45762-944` (13 agents / 6 clusters — openapi-catalog, alerts-product-kb, alerts-delivery-channels, alerts-workflow-trigger, naming-traps, repo-precedent — each `verify` + adversarial `refute`, plus a completeness critic). The refute pass did substantial work and its downgrades are baked into this file: it **could not reproduce a `POST /alerts` create endpoint** on independent re-fetch (→ create is `[INFER]`, treated as **not documented**); it flagged the spec's **BearerAuth-JWT** declaration vs the API-overview's **`X-DOMO-Developer-Token`** classification as a **genuine, unresolved** conflict (→ `[INFER]`); it pulled the **alert-row-value → workflow-start-parameter mapping** down to `[INFER]` (official article 000005179 does *not* describe it); it scoped **"Teams is not a native channel"** and **"no first-class DataSet-updated Workflow trigger"** and **"no anomaly/goal alert type"** to `[INFER]` universal-negatives; and it caught a **Slack documentation discrepancy** (one docs article lists four Instant-Alert channels incl. Slack, a migrated mirror of the *same* article lists fewer). Two workflow caveats carried forward: the **alerts.yaml body was only summarized** (persistent 405 on some deep links — the complex sub-schemas were never fully charted), and several product specifics are **single-source** and marked needs-live-verify below.

**Provenance update (2026-09-06, `wf_d69feb76-977`, 19 agents / 0 errors).** The "only summarized / persistent-405" caveat above is **superseded**: the **full 297-line `alerts.yaml` body has since been reached at HTTP-200** (twice — the rank-47 fetch and this rank-67 re-fetch — byte-stable, no drift). The complex sub-schemas remain uncharted **not** because the body was truncated but because **the spec defines no `components.schemas` at all** — `components` holds only the `BearerAuth` securityScheme (`grep 'schemas'` / `$ref` = 0), and every `200` response is a bare `type: object`. So all Alert field knowledge is **example-derived** (the list example + the get-an-alert single-object example) plus the `get-alerts` `fields`-param `default:` list — never a formal schema. The do-not-publish hedge on `actions[]`/`configurations[]`/`filterGroups[]`/`error{}` internals therefore stands on firmer ground: those are genuinely undefined in-spec (empty `[]` / `{}` in the example), not merely unfetched. This increment (rank-67) applied the rank-47 pending fold: **PARTIAL_APPLY — 7 folds APPLY + 1 APPLY-CORRECTED (subscribe `method`=POST is `[DOC]` via the `post:` verb, not `[INFER]`), 0 dropped; all 7 planted over-claim negative controls REFUTED.**

## The naming-trap table — read this first

"Alert" and "notification" collide across a dozen-plus senses. Copying logic, a field name, or an owner from one into another is the #1 way to be wrong here. Route by this table first; only then reason about the mechanism.

| Term you saw | What it actually is | Owner / routing | Tier |
|---|---|---|---|
| **Card / Visualization-Card Alert** | A platform alert watching one card's data condition | **this skill** | `[KB]` |
| **DataSet Alert** | A platform alert watching a dataset condition (a variant co-managed with the card alert, not a different feature — but two alert *types*) | **this skill** | `[KB]` |
| **Alerts REST API** (`/api/social/v4/alerts`) | The documented REST surface: list/get/delete/subscribe/share | **this skill** | `[DOC]` |
| **Alert Center / "Alerts Explorer"** | The management + discovery UI for existing alerts | **this skill** | `[KB]` (naming/layout single-source → verify) |
| **Subscription / "Notify Me"** | Adding a user/group to be notified by an existing alert (a *separate* object from the alert definition) | **this skill** | `[KB]` |
| **Alert Action: Domo Webhook** (outbound) | An alert fires an outbound HTTP POST to a fixed-body webhook | **this skill** | `[KB]` |
| **Alert Action: create a Task** | An alert opens a Projects & Tasks task | **this skill** | `[KB]` |
| **Alert Action: Initiate a Workflow** | An alert triggers a deployed workflow version | **this skill** (alert side) **+ `domo-workflow.md`** (workflow side) | `[KB]` |
| **Alert Action: Send a Scheduled Report** | An alert triggers sending of a scheduled report | **this skill** (the action) | `[KB]` |
| **Scheduled Report / Report Scheduler** (`scheduled-reports-api.yaml`) | A *separate* feature+spec for scheduled email report delivery | **`domo-scheduled-reports.md`** owns the object + REST; do NOT absorb it here (see Boundaries) | `[DOC]` |
| **Notification** (umbrella) | Domo's broader notification bell/center; an alert *produces* notifications but is **not 1:1** with one | **this skill**, with the not-1:1 caveat | `[KB]` |
| **Buzz mention / Buzz post** | A Buzz-channel message; can be an alert *subscription type* (`BUZZ`) or a Workflow step output | subscription type → **this skill**; Workflow→Buzz-post → `domo-workflow.md`; the Buzz **conversation surface** itself → `domo-buzz.md` | `[KB]`/`[INFER]` |
| **Workflow API trigger** (inbound HTTP) | Starting a workflow via its own HTTP endpoint — **not** an alert at all | `domo-workflow.md` | — |
| `ALERT_HISTORY` / `ALERT_STATE` / `alert_id` (inventory-management-app) | **App-internal AppDB** collections + a threshold-transition state machine (`SHORTAGE`/`RECOVERY`; `MANUAL` is a separate history kind). **THE #1 false friend.** | the app itself — **NOT** platform Alerts | `[REPO]` |
| `REORDER_ALERT` (equipment-inventory-app) | An app-internal reorder flag/record | that app — false friend | `[REPO]` |
| `alerts_count` / `usage_scope:'alerts'` (asset-lifecycle-app) | App-internal usage counters | `asset-lifecycle-app` — false-friend-adjacent | `[REPO]` |
| DomoStats / Governance activity rows whose value `== 'ALERT'` (or an `'alert'`-like dataset) | Just **data** in a governance/activity DataSet | `domo-governance-datasets.md` (dataset), not this skill | `[INFER]` (that it's a false friend) |
| `window.alert()` / `role="alert"` / `icon-alert` / `md04-alert` / `MarginAlertRanking` / `parseAlertCount` | Browser API, ARIA role, CSS/icon classes, app UI identifiers | the app's UI — **all false friends** | `[REPO]` |
| **Goals & Metrics** / **Anomaly Classification AI Agent** | Goal-tracking (the OKR app) / an AI agent — adjacent, sometimes *feels* like an alert | `domo-goals.md` / `domo-ai-services.md` — cross-ref only, **not** this skill | `[INFER]` |

Card Alert and DataSet Alert are best described as **two alert types co-managed in the Alert Center**, not "the same feature" and not two unrelated objects.

## The headline — the Alerts REST API is a documented island (partially charted)

A machine-readable **`alerts.yaml`** exists in the docs OpenAPI catalog (reached via `https://www.domo.com/docs/llms.txt` → Product APIs), served at `https://www.domo.com/docs/openapi/product/alerts.yaml`. It is **OpenAPI 3.0.0**, `info.title` "Alerts API", `info.version` "4.0".

- **Host = the instance host `https://{instance}.domo.com`** — **NOT** `api.domo.com`. This is the historically-internal **"social" v4 namespace** now given an official spec.
- **Base path = `/api/social/v4/alerts`.**
- **Six CONFIRMED operations** (survived verify + refute):

| Method | Path | operationId |
|---|---|---|
| GET | `/api/social/v4/alerts` | `get-alerts` (list) |
| GET | `/api/social/v4/alerts/{alertId}` | `get-an-alert` |
| DELETE | `/api/social/v4/alerts/{alertId}` | `delete-an-alert` |
| POST | `/api/social/v4/alerts/{alertId}/subscriptions` | `subscribe-user-to-an-alert` |
| DELETE | `/api/social/v4/alerts/{alertId}/subscriptions` | `unsubscribe-user-from-an-alert` |
| POST | `/api/social/v4/alerts/{alertId}/share` | `share-an-alert` |

- **The `share` body** (`POST .../share`, `requestBody` `required: true`, an **inline** typed schema — not a `components.schemas` ref) carries `userMessage` (string), `alertSubscriptions` (array of objects), `sendEmail` (boolean), `metaData` (object); the schema's `required:` array is **exactly `[userMessage, alertSubscriptions]`**. `sendEmail` is **optional with no `default:`** (the example's `sendEmail: true` is an example value, not a default), and `alertSubscriptions` being an **array** means one share call can **fan out to multiple entities** (see the email-blast NOTE under Safety). `[DOC]`.
- **The subscribe op has NO `requestBody` block.** `subscribe-user-to-an-alert` = **`POST`** `/api/social/v4/alerts/{alertId}/subscriptions` — the **method `POST` is `[DOC]`** (declared by the `post:` verb key), and its **only formally declared input is the path param `alertId`** (integer, required). The body contract **`{subscriberId, type: 'USER'}` appears ONLY in the `x-codeSamples` JS** (`body: JSON.stringify({ subscriberId: userId, type: 'USER' })`) — `[DOC]` for *existence*, but the **body field types, which fields are required, and the request `Content-Type` are `[INFER]`** (never schematized). Do not present the body as a documented schema.
- **Subscribe/unsubscribe asymmetry `[DOC]`:** unlike subscribe (no body), **unsubscribe** (`DELETE .../subscriptions`) declares two **formal required query params** — `subscriberId` (integer, `required: true`) and `type` (string, `required: true`). The two sides take input differently: subscribe via an unschematized body, unsubscribe via required query params.
- **⚠ Auth: SPEC-side resolved `[DOC]`, LIVE-side unresolved `[INFER]`.** The spec declares exactly one security scheme — `components.securitySchemes.BearerAuth` (`type: http`, `scheme: bearer`, `bearerFormat: JWT`) applied globally (`security: [{BearerAuth: []}]`); there are **zero** `X-DOMO-*` / `apiKey` / `DomoDeveloper` references anywhere in `alerts.yaml` (the `X-DOMO-Developer-Token` header belongs to *other* specs/the overview, e.g. `scheduled-reports-api.yaml`). So **spec-side auth = BearerAuth JWT (`[DOC]`)**. **BUT** the API-Reference overview classes Alerts under dev-token APIs, and the **live endpoint's accepted header on a given instance is UNRESOLVED (`[INFER]`)** — spec-declared ≠ live-accepted. Do **not** hard-code either; probe a read-only `GET /alerts` on the target instance first.
- **⚠ No create endpoint in this spec (`[DOC]`-absent).** The complete 297-line spec has exactly **4 paths / 6 operations** (charted above) and the base path `/api/social/v4/alerts` carries **GET only** — there is no `POST`/create on it. (This resolves the earlier "claimed then not reproduced" story: the full body simply contains no create op.) **Scope the claim precisely:** "no `POST` on the base path / no create operation in THIS spec," **NOT** "creation is impossible" — alert creation is a documented **UI wizard** flow, and absence from this spec ≠ no create endpoint anywhere on the platform (`[INFER]`).
- **⚠ This is `v4` in the path while `info.version` is "4.0"**, on the internal `social` surface — a consumer should not assume long-term URL stability the way a top-level `/v1/` Platform API implies.

### `get-alerts` (list) query params `[DOC]`

`GET /api/social/v4/alerts` declares **exactly 15 query params, every one `required: false`** (this is the complete param set for the list op in this spec; `get-an-alert` by contrast takes only `alertId` (path) + `fields` (query)). The response is still a bare `type: object`, so these params are charted but the response body is not (see the Alert-object section).

| Param | Type | `default:` | Note |
|---|---|---|---|
| `all` | boolean | — | fetch all alerts at once |
| `cardId` | integer | — | alerts for one card |
| `currentUserSubscriptions` | boolean | `false` | alerts the current user is subscribed to |
| `dataSetId` | **string** | — | alerts for one dataset — ⚠ **string**, unlike the integer id params |
| `disabled` | boolean | — | only disabled alerts |
| `fields` | string | `id, category, type, name, description, resourceType, resourceId, createdAt, createdBy, modifiedAt, modifiedBy` | which fields to return; can be set to `all` |
| `limit` | integer | `100` | page size |
| `offset` | integer | `0` | pagination offset |
| `ownerId` | integer | — | alerts owned by a user |
| `pageId` | integer | — | alerts for a page |
| `sort` | string | `createdAt` | sort field |
| `subscriberId` | integer | — | alerts a user is subscribed to |
| `subscriptionTypes` | string | — | filter by subscription types (a free-form comma-separated list, **no `enum:`**) |
| `suggested` | boolean | — | only suggested alerts |
| `triggered` | **string** | — | only triggered alerts — ⚠ a **string** query param |

- **Exactly 5 params carry a real JSON-Schema `default:` keyword:** `currentUserSubscriptions` (`false`), `fields` (the field-name list), `limit` (`100`), `offset` (`0`), `sort` (`createdAt`). The other 10 have no default. Type breakdown: **4 booleans** (`all`, `currentUserSubscriptions`, `disabled`, `suggested`), **6 integers** (`cardId`, `limit`, `offset`, `ownerId`, `pageId`, `subscriberId`), **5 strings** (`dataSetId`, `fields`, `sort`, `subscriptionTypes`, `triggered`).
- **⚠ Two name-collision traps** (same-looking name, different thing — do not thread one into the other):
  - `currentUserSubscriptions` is a **query param** (plural, boolean, request-side); `currentUserSubscribed` is a **response scalar** on the Alert object (singular, boolean, response-side). Different names, different sides — not the same field.
  - `triggered` as a **query param is a `string`**, but `triggered` on the response Alert object is a **boolean**. Same name, different type across request/response.

## The Alert object `[DOC]` field names / `[INFER]` complex sub-schemas

The spec defines **no `components.schemas`** — every `200` response is a bare `type: object`, so there is **no formal Alert schema**. The field names below are **example-derived**: from the `get-alerts` list example, the `get-an-alert` single-object example, and the `get-alerts` `fields`-param `default:` list. Treat the *set* as reached-not-exhaustive and every field as `[DOC]`-for-existence-only (no declared type/format/required):

`id`, `name`, `type`, `category`, `description`, `resourceType`, `resourceId`, `resourceName`, `rule`, `triggerFrequency`, `owner`, `enabled`, `active`, `contextual`, `triggered`, `currentUserSubscribed`, `createdAt`, `createdBy`, `modifiedAt`, `modifiedBy`, and an `error` object.

⚠ **Field provenance is uneven** (state it, don't smooth it over): `description` appears **only in the `fields`-param `default:` list**, not in either example payload; `resourceType` shows only `DATASET` in the example (`CARD`/`PAGE` are product-`[INFER]`, not example-attested); `resourceName`, `owner`, `active`, `contextual`, `currentUserSubscribed`, and `error` appear **only** in the `get-an-alert` single-object example.

Plus four **arrays**, all shown **empty (`[]`)** in the `get-an-alert` example: `actions[]`, `configurations[]`, `filterGroups[]`, `subscriptions[]`.

**⚠ Do NOT publish the sub-schemas as documented.** They are **genuinely undefined in-spec**, not merely unfetched: with no `components.schemas` and every response a bare `type: object`, the `get-an-alert` example shows `actions`, `configurations`, `filterGroups`, `subscriptions` as empty **arrays** `[]` and `error` as an empty **object** `{}` — the example reveals only the container type (array vs object), **zero** field-level shape. `rule` and `triggerFrequency` appear as **free-form strings** in the example (a human-readable rule sentence / a frequency word) — no grammar or enum is defined. List their *names* if useful; never their internal structure "per the spec." The subscription **type** set `USER` / `GROUP` / `BUZZ` / `DAILY` / `WEEKLY` / `AUTO` is sourced from the **`description` string of the unsubscribe endpoint's `type` query param** ("The entity type, can be USER, GROUP, BUZZ, DAILY, WEEKLY, or AUTO") — it is **NOT a formal `enum:` block** (a `grep` for `enum` across the whole spec returns 0), so treat its completeness as `[INFER]`. Do not confuse it with the `get-alerts` `subscriptionTypes` query param (a separate free-form comma-separated filter string, also with no `enum`).

## Alert types & rule behavior `[KB]`

Documented product behavior (`[KB]`, well-corroborated across multiple articles):

- **Condition statements** for a rule include the comparisons **greater than / less than / equal to** (and their combinations), plus change-based conditions **changes by / increases by / decreases by**, and a **percentage-threshold** form. This condition set is corroborated across `www.domo.com/docs`, `knowledge.domo.com`, and third-party write-ups — solid `[KB]`.
- A **DataSet Alert** can use more flexible rules (multiple trigger rules; the "complex calculations / data from other DataSets" clause is `[KB]` but was not independently re-quoted — soft-cite it).
- **Anomaly / Goal alerts:** the standard rule builder was **not observed** to expose an anomaly-detection condition, and no separate "Goal alert" / "KPI alert" object type was found. State both **only** as `[INFER]` ("not found in what we saw"), never as "Domo has no anomaly alert" — anomaly detection exists elsewhere in the platform (AI services / cards) and could surface as an alert condition. (This bullet is only about the *absence of a Goal-alert condition in the alert rule builder* — the Goals OKR *application* itself is a distinct owned surface → `domo-goals.md`.)

## The Alert Wizard flow `[KB]`

The UI create flow (`[KB]`) is broadly a three-step wizard: **define the Rule** (the condition, on a card/visualization or dataset) → **compose the Message** (title/body a subscriber receives; on a DataSet alert the message can embed **DataSet field macros/tags** that inject row-level values) → **Share** (choose who is subscribed). PDP-scoped data means different subscribers can see different triggering rows, so message content and subscriber choice interact with row security (`domo-datasets.md`). **The exact wizard step labels are version-dependent — verify against the live UI rather than quoting fixed labels.**

## Alert Actions — the four Attach-Actions `[KB]`

An alert can attach an **Action** that fires when it triggers. The KB article (`360043430513`) enumerates **four native alert actions** (`[KB]`):

1. **Domo Webhook** — outbound HTTP POST. The body is **largely fixed**, but the editable alert **`message`** inside it can embed DataSet field macros/tags carrying row-level values. **Do not publish the webhook payload schema** — it was not charted (`[INFER]` for structure).
2. **Create a Task** (Projects & Tasks).
3. **Initiate a Workflow** — runs a **deployed workflow version** (see the two-paths warning below).
4. **Send a Scheduled Report** — triggers sending of a scheduled report (the report itself is owned by `domo-scheduled-reports.md` — see Boundaries).

**⚠ Attach-Action labels and the exact count are version-dependent** — treat "four" and the labels as reached-`[KB]`, and re-check the live UI before quoting them as fixed. The set of delivery options can also **narrow by alert surface**: the "Create an Alert for a Visualization Card" article narrows delivery to "email or …" in a way the general article does not.

## Subscriptions & delivery channels `[KB]`/`[INFER]`

- **A subscription is a separate object from the alert definition.** The `subscriptions[]` array (types `USER`/`GROUP`/`BUZZ`/`DAILY`/`WEEKLY`/`AUTO`) and the `POST`/`DELETE .../subscriptions` operations manage who is notified, independently of who owns/defines the alert.
- **Instant delivery channels** documented in the KB "Configuring Notification and Alert Settings" include **email**, in-Domo (the notification bell / mobile), and — per `domo.com/docs` article `360042925814` — **Slack** as an Instant Alerts channel. `[KB]`.
  - **⚠ Slack has a documentation discrepancy:** the `domo.com/docs` version of that article lists four Instant-Alert channels including Slack, but the migrated `knowledge.domo.com` mirror of the *same* article lists fewer. Cite Slack-native as `[KB]` **with this mirror-discrepancy caveat**, and verify on the target instance.
- **Microsoft Teams:** treat "Teams is native / not native" as **`[INFER]`** — the only support was a repo doc note ("Teams via Webhook, native is a feature request"), a universal negative that must not be stated as fact. Teams is reachable at least via the outbound **Webhook** action.
- **Removing a subscriber:** the Share modal → People → Remove flow removes a subscriber; do **not** assert this is **Admin-gated** — the reached KB did not gate it to Admins (`[INFER]` for the "only an Admin can unsubscribe another person" claim).

## Alert Center & discovery `[KB]`/`[INFER]`

The **Alert Center** is the UI for managing existing alerts and finding new ones to subscribe to. A discovery surface (variously described as "Alert Discover" / "Alerts Explorer" with suggested alerts) exists (`[KB]` for *existence*), but its **load-bearing specifics are single-source and need live verification**: the exact naming duality, a heat-map view, any color enum, a carousel, and whether **"Status alerts"** is a real Alert Center category (found only in a docs mirror, **not** in the `knowledge.domo.com` "Alert Center Layout" article). The top-nav path to it is **version-dependent** (KB shows "Alerts in the app toolbar" / a user-menu Settings tab; the docs mirror described "Alerts Explorer" / "Manage Alerts"). Treat all of the above as `[INFER]`/needs-live-verify, not established fact.

## ⚠ Two DISTINCT Alert→Workflow paths — do not merge them

These are two different integration points and must never be merged:

- **(a) The alert-side path — "Alert Action: Initiate a Workflow."** A Card/DataSet Alert, when it triggers, runs a **deployed workflow version**. This is owned on the alert side by this skill; the workflow definition/version is owned by `domo-workflow.md`. `[KB]` (cross-referenced at `domo-workflow-reference.md`).
- **(b) The workflow-side path — the Workflow inbound API/HTTP trigger.** A workflow can be started by its own HTTP endpoint (the "start a workflow" API). This has **nothing to do with alerts** and is owned entirely by `domo-workflow.md`.

**Two hedges the refute pass forced (`[INFER]`):**
1. **The mapping of alert row/card values into the workflow's start parameters is NOT documented.** Official article `000005179` describes initiating a workflow from an alert but does **not** describe passing alert row values as workflow start parameters (nor a "types must align" rule). Do not state that mapping as documented.
2. **"There is no first-class DataSet-updated Workflow trigger; data-condition starts must go through an alert"** — the *alert-initiates-workflow* half is `[KB]`, but the **universal negative** ("no other data trigger exists") is `[INFER]`. Likewise "there is no separate Webhook *trigger type* in Workflows" is `[INFER]`, not fact. Whether the Alerts REST spec itself can **wire** an alert Action to a workflow version is **unconfirmed** (the `actions[]` sub-schema was never charted).

## Boundaries & orphans

- **Scheduled Reports is owned by `domo-scheduled-reports.md` — disambiguate, do NOT absorb.** A separate spec `scheduled-reports-api.yaml` (OpenAPI 3.1.0, 31 operations under `/api/content/v1/reportschedules`) is the report OBJECT + REST surface, now owned by `domo-scheduled-reports.md`. Scheduled Reports is a distinct feature (scheduled email report delivery) that merely *appears* as one of the alert Attach-Actions — the alert *Action* that triggers a send stays here; the report definition, schedule, recipients, and the send/subscribe/history REST all live there. The one DOC-level seam is `ResourceSendNowInfo.alertActionId`. Do not restate its contract here.
- **`remote-datastats-api.yaml`** is another adjacent catalog spec (not read, not owned here) — named only so it is not mistaken for an alerts endpoint.
- **The `social` namespace** hosts more than alerts (Buzz, sharing). Reaching `/api/social/v4/alerts` does not license assumptions about sibling `social` paths. The Buzz **conversation surface** (messaging/collaboration — the likely undocumented sibling under `social`) is owned by `domo-buzz.md`.

## Repo false friends `[REPO]`

In THIS repo, **every "alert" token is a false friend** — there is no platform-Alerts consumer. Grep the token, not the concept:

- **The only repo-wide hits for genuine *platform-alert* terms are documentation** (`domo-workflow-reference.md` cross-referencing "runs a deployed workflow when a Domo Alert fires"). No working code calls `/api/social/v4/alerts`. (Caveat: that "only docs" claim holds for the narrow platform-alert-endpoint regex; a broad grep for the substring `alert` hits many app internals below.)
- The **vendored `domo.js`** builds (11 byte-identical copies) contain **zero** platform-alert substrings.
- **`inventory-management-app`** — `ALERT_HISTORY` / `ALERT_STATE` AppDB collections + an `alert_id`. This is an **app-internal threshold state machine**: transitions are `SHORTAGE` / `RECOVERY` (with `MANUAL` as a separate `ALERT_HISTORY` kind) — **not** `NORMAL/SHORTAGE/MANUAL`, and **not** platform Alerts. **This is the #1 silent-failure false friend.**
- **`equipment-inventory-app`** — `REORDER_ALERT`, an app-internal reorder record/flag.
- **`asset-lifecycle-app`** — `alerts_count`, `usage_scope:'alerts'`, app-internal counters.
- **UI false friends everywhere:** `window.alert()`, `role="alert"` (ARIA), `icon-alert` / `md04-alert` (CSS/icon), `MarginAlertRanking`, `parseAlertCount`, and column values `== 'ALERT'` (a domo.js page-filter *example* — just data; that it's a false friend is `[INFER]`).

The canonical platform endpoint is `/api/social/v4/alerts` under the **`social`** namespace — **not** a hyphenated `alert-service` / `alert-center` / `alerts-api` path. Any future `domo-alerts` REST consumer must be built against `social/v4`, and must not be confused with the AppDB `ALERT_*` collections above.

## Do NOT claim as documented fact

The single failure mode on this surface is **over-claiming** — presenting an under-charted corner as a documented contract. Hold every one of these:

1. **"There is no Alerts REST API."** **FALSE / stale.** `alerts.yaml` exists and was reached; there are six confirmed operations. Never repeat the community belief.
2. **A CREATE endpoint (`POST /api/social/v4/alerts`) exists.** The complete spec has **no `POST` on the base path / no create op** (`[DOC]`-absent; GET-only base path). Scope it as "not in **this** spec," **NOT** "creation impossible" (`[INFER]`) — alert creation is a documented **UI wizard** flow.
3. **Which auth header the LIVE endpoint accepts.** The spec declares **BearerAuth JWT** (`[DOC]`; 0 `X-DOMO-*` refs in `alerts.yaml`); the overview implies `X-DOMO-Developer-Token`. **Spec-declared ≠ live-accepted** — the live header is UNRESOLVED (`[INFER]`). Do not hard-code one — verify live.
4. **The webhook payload schema.** Not charted — do not publish it.
5. **The internal structure of `actions[]` / `configurations[]` / `filterGroups[]` / `error`, or the `rule` / `triggerFrequency` value grammars.** Names only; sub-schemas were never fetched (`[INFER]`).
6. **The Alerts REST spec can wire an alert-Action-to-workflow.** Unconfirmed (`actions[]` uncharted) — `[INFER]`.
7. **Alert row/card values map into a workflow's start parameters ("types must align").** UNDOCUMENTED (`[INFER]`) — article 000005179 does not describe it.
8. **"There is no first-class DataSet-updated Workflow trigger."** `[INFER]` universal-negative (the alert-initiates-workflow half is `[KB]`).
9. **"There is no separate Webhook *trigger type* in Workflows."** `[INFER]`, not fact.
10. **Slack is native** — cite as `[KB]` **with the mirror discrepancy caveat**; verify on the instance. **Teams is NOT native** — `[INFER]` (repo-doc-only universal negative).
11. **No anomaly-detection condition / no Goal-alert object type.** Both `[INFER]` ("not found in what we saw"), never "Domo has none."
12. **"Status alerts" is an Alert Center category, and the Alert Discover/Explorer heat-map/color/carousel specifics.** Single-source (docs mirror only) — needs live-UI verification; not established.
13. **App-internal `ALERT_HISTORY` / `ALERT_STATE` / `REORDER_ALERT` / `alerts_count` are platform Alerts.** No — they are per-app AppDB/UI constructs (`[REPO]` false friends). Never conflate.
14. **Absorbing Scheduled Reports** (`scheduled-reports-api.yaml`) into this skill. Disambiguate only — its object + REST surface is owned by `domo-scheduled-reports.md`; keep only the alert *Action* here.
15. **Attach-Action labels / count and wizard step labels are fixed.** Version-dependent `[KB]` — re-check the live UI before quoting them as fixed.

## Safety & hygiene

- **The developer token (`X-DOMO-Developer-Token`) and any bearer JWT are secrets** — server-side only, never in front-end code, handoffs, or commits.
- **`DELETE /alerts/{alertId}` is destructive** and there is no confirmed undo. On a shared/validation instance, only delete alerts you created; never delete another owner's alert. (Consistent with the workspace rule that destructive tests run only against self-owned objects.)
- **⚠ `share` with `sendEmail: true` is a human-gated email fan-out.** `alertSubscriptions` is an **array**, so one `POST .../share` call can email **multiple** entities at once. This is an outbound-email side effect with a recipient list — do **not** fire it autonomously; confirm explicit human intent for the recipient set first. (NOTE-only: the share *contract* is `[DOC]`; this gate is an operational-safety rule consistent with the workspace email-blast human-gate, not a schema claim.)
- **Row security travels with the alert.** A DataSet alert's message can carry row-level values; PDP scoping means different subscribers may see different rows. Do not assume every subscriber sees the same triggering data.
- **Auth is unresolved — probe read-only first.** Before any write (subscribe/share/delete), confirm the accepted auth header against a `GET /alerts` on the target instance rather than assuming.

## Companion skills

- `domo-workflow.md` — owns the workflow that an alert Action initiates (versions, start params, execution) **and** the separate inbound API/HTTP trigger. The alert↔workflow boundary is the two-paths warning above.
- `domo-beast-mode.md` — owns Beast Mode expressions used inside an alert rule.
- `domo-datasets.md` — owns DataSet identity and PDP row policies that scope what an alert (and its message) can see.
- `domo-governance-datasets.md` — owns DomoStats / Governance activity datasets whose rows may contain the string `alert` (data, not the alert feature).
- `domo-ai-services.md` — owns the Anomaly Classification AI Agent and related AI features that are adjacent to, but not, platform Alerts.
- `domo-scheduled-reports.md` — owns the Scheduled Reports object + REST surface (`scheduled-reports-api.yaml`). The alert *Action* "Send a Scheduled Report" stays here; the seam is `ResourceSendNowInfo.alertActionId`.
