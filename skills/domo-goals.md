# Domo Goals (OKR objectives / key-results management app)

**Use this when** you are authoring, driving, or reasoning about **Domo Goals** — the in-product **OKR / objectives-and-key-results management application** (the "Goals Center"): personal / team / company **goals** (objectives), their nested **metrics** (key results / KPIs), **check-ins** and **status**, **owners / delegates / managers**, **time periods**, org **tags**, the configurable **nomenclature**, and the standalone Goals mobile companion. This is Domo's **goal-management SURFACE**, not a card target-line and not an alert type.

**NOT for:**
- The **KPI-card GOAL / TARGET line** — the Analyzer "goal line" property, a gauge/bullet **target**, or a Beast Mode conditional-formatting threshold on a card. That is a **card property**, not the Goals app → **`domo-cards.md`**. (Do NOT absorb it here.)
- The **"Goal alert" object-type absence** — an `[INFER]` finding of the alert **rule builder** (no anomaly/goal alert *condition* was observed), documented at `domo-alerts.md:107`/`:180`. That is an alerts-surface negative, **not** the Goals app → **`domo-alerts.md`**.
- Reading Goals **data programmatically** — the only documented path is the **DomoStats** "OKR Objectives" / "OKR Key Results" reports materialized as DataSets, read via the ordinary DataSet API → **`domo-governance-datasets.md`** + **`domo-datasets.md`** (cross-ref, not restated here).
- The **KPI-card image-render API** (`get-kpi-card-image-api.yaml`, `/api/content/v1/cards/kpi/{urn}/render` → base64) — a card **rendering** endpoint whose name merely *sounds* KPI/goal-adjacent → **`domo-get-kpi-card-image.md`**. Not a Goals endpoint.
- **Microsoft "Viva Goals"** (and Todoist "Goals", etc.) — third-party OKR products that *data-link into* Domo but are **other vendors**, not this surface. A "Domo Goals deprecated" search hit almost always refers to one of these.

## What this skill OWNS vs DEFERS

| This skill OWNS | Defers to |
|---|---|
| The Goals **object model** (goal/objective + nested metric/key-result), owners/delegates/managers, start & achieve-by dates, check-ins/status, time periods, tags, and the configurable **nomenclature** — all as documented product behavior (`[KB]`). | — |
| The **five-sense disambiguation** of "goal" (OKR app vs card target-line vs Goal-alert-absence vs loop standing-goal vs the four nomenclature labels) + the external **Viva Goals** collision. | — |
| The KPI-card **goal/target line** (a card property). | `domo-cards.md` |
| The **"Goal alert" object-type absence** (an alerts rule-builder `[INFER]`). | `domo-alerts.md` (`:107`, `:180`) |
| **Reading** Goals data (DomoStats OKR-Objectives / OKR-Key-Results DataSets via the DataSet API). | `domo-governance-datasets.md` + `domo-datasets.md` |
| The **metric SOURCE** when it is a card (a metric can be fed by a card), or a Project/Task. | `domo-cards.md` / `domo-projects.md` |
| The KPI-card **image render** endpoint (name collision only). | `domo-get-kpi-card-image.md` |
| The **grant / role mechanism** behind who can create or reassign goals. | `domo-identity-access.md` |

## Evidence tiers

- `[DOC]` — reproduced from an official machine-readable OpenAPI spec / dev-portal REST reference.
- `[KB]` — documented product behavior from Domo's Salesforce Knowledge Base (the Goals support articles) / knowledge.domo.com. Behavior, not a REST contract.
- `[REPO]` — observed only in this repository / on a live instance.
- `[INFER]` — reasoned, not sourced. Every universal negative is at best `[INFER]`.

**⚠ Whole-surface tier = `[KB]`, NOT `[DOC]`.** Goals is a **product application documented only in Salesforce KB articles** (`domo.com/docs/s/article/<id>`) and product/marketing pages. **No public Goals OpenAPI/REST spec was found in what I probed** — absent from the authoritative `www.domo.com/docs/llms.txt` catalog (HTTP 200, full read), and a live probe returned genuine **404** at `goals.yaml` / `goal.yaml` / `okr.yaml` / `objectives.yaml` / `metrics.yaml` across the `product/`, `framework/`, and `platform/` namespaces (control `alerts.yaml` = 200, proving the 404s are real absence-of-spec, not fetch failures); `developer.domo.com/llms.txt` and `api.domo.com` probes returned **405 / 401 = MISSING / inconclusive** (they auth-gate *before* routing). Per convention a 404/405/401 is **MISSING evidence, never proof of absence** — an undocumented internal surface may well exist, so every endpoint/verb/payload is `[INFER]`. **Never write "Domo Goals has no API."** **Fetch pattern** (KB is UA-gated; plain curl 405s): `curl -s -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36' -H 'Accept: text/markdown' https://www.domo.com/docs/s/article/<id>.md`.

## Naming traps — READ FIRST

Five senses of "goal" live in this repo (plus one external collision); **only sense (a) is this skill.** Resolve the sense before reaching for a mechanism — the repo already scatters the others across other owners.

| You see | Reality | Owner | Tier |
|---|---|---|---|
| **(a) Goals the OKR APPLICATION** — personal/team/company objectives + nested metrics + check-ins, the "Goals Center" | The subject of THIS skill. | **THIS skill** | `[KB]` |
| **(b) KPI-card GOAL / TARGET line** | An Analyzer card property (goal line / gauge-bullet target / Beast Mode conditional-format threshold). A card decoration, **not** the OKR app. | `domo-cards.md` | `[KB]`/`[REPO]` |
| **(c) "Goal alert" object-type absence** | An `[INFER]` alerts finding — the rule builder exposes **no** anomaly/goal alert *condition*; stated only as "not found in what we saw." NOT the Goals app. | `domo-alerts.md:107`/`:180` | `[INFER]` |
| **(e) "Goals & Metrics"** | **ONE of four admin-selectable NOMENCLATURE labels for the SAME product** (see below) — Goals and Metrics / Objectives and Key Results / Objectives and KPIs / Priorities and Action Items. So the alerts-table label "Goals & Metrics" **is** this OKR surface (which is why `domo-alerts.md:65` now routes it here). | **THIS skill** | `[KB]` |
| **(ext) Microsoft "Viva Goals"** / Todoist "Goals" | Third-party OKR products that data-link into Domo — **other vendors**. Deprecation news about "Viva Goals" is NOT about Domo Goals. | *external* | — |

The negative control ("Goals is just the card target-line") is absurd by its own logic: a card's goal line is a per-card visual annotation with no owner/check-in/time-period/delegate model, whereas Goals is a cross-user application. `domo-cards.md` owns (b); this skill owns (a)/(e). Cite these seams — they pre-date this write.

## The surface, in one line

Goals is Domo's **OKR management application**: users create **goals** (objectives) — scoped **personal / team / company** — each with an **owner**, optional **manager/delegate**, a **start date** and **achieve-by date**, and one or more nested **metrics** (key results) that carry a **target** with a **≥ / ≤ / =** operator and a **source**. Progress advances by **check-ins** (manual status updates) or automatically from a metric's data source; the app rolls status up across the org, filtered by **time periods** and **tags**. Admins pick the **nomenclature** the whole app uses. It has **no documented public REST API**; every action below is a UI action and any programmatic path is `[INFER]`.

## Object model (`[KB]`)

- **Goal (objective):** the unit. Has a **title**, a **type/scope** (personal / team / company `[KB]`), an **owner** (a person), optional **manager** and **delegate**, a **start date** and an **achieve-by date**, a **status**, optional **tags**, and a set of nested **metrics**. Belongs to a **time period**.
- **Metric (key result / KPI):** nested under a goal. Carries a **target value** with a comparison **operator (≥ / ≤ / =)** — i.e. "reach at least / stay under / hit exactly" — and a **source** (below). A goal's overall progress aggregates its metrics.
- **Metric sources — three (`[KB]`):** **(1) Card** — the metric reads its current value from a Domo card (cross-ref `domo-cards.md`); **(2) Manual** — a value the owner enters/updates by hand; **(3) Projects & Tasks** — progress derived from a linked project/task board (cross-ref `domo-projects.md`).
- **Check-in:** a status/progress update on a goal or metric (owner or delegate). **Request Check-in** pings another user to update theirs (outward-facing — see Safety).
- **Time Periods:** admin-defined windows (e.g. quarters) that scope and group goals.
- **Tags:** org taxonomy for grouping/filtering goals; admins can **delete/merge** tags (destructive to the taxonomy — see Safety).
- **Save As Goal / copy:** duplicate an existing goal as a new one.

Documented UI/navigation and management behavior: KB `4578278680855` (app/navigation), KB `4663374299031` ("Managing Your Goals and Metrics"), plus "Getting Started With Goals" and the Goals Center topic `0TO5w000000ZanmGAC`.

## Nomenclature — the same product, four names (`[KB]` `4577172785559`)

An admin selects **one** nomenclature for the whole instance; it renames every label in the app but not the feature:

1. **Goals and Metrics** (the default / most common label)
2. **Objectives and Key Results** (classic OKR)
3. **Objectives and KPIs**
4. **Priorities and Action Items**

⚠ Consequence: "Goals & Metrics", "OKRs", and "Objectives and KPIs" in docs/screenshots may all name **this one surface**. Never treat a nomenclature label as a distinct feature. Selecting the nomenclature is an **admin mutation** (see Safety).

## The programmatic surface (no public API) + the ONLY data path

**No PUBLIC Goals OpenAPI spec** — absent from the `llms.txt` catalog; `goals/goal/okr/objectives/metrics.yaml` = **404 MISSING** across product/framework/platform (control `alerts.yaml`=200); `developer.domo.com/llms.txt` = 405, `api.domo.com` = 401 (both MISSING/inconclusive, auth-gate before routing). An undocumented internal surface may exist `[INFER]`; **never phrase this as "Goals has no API."**

The **only documented programmatic path to Goals data** is a **cross-ref, not a restatement**: the **DomoStats** connector materializes two reports — **"OKR Objectives"** (= your goals) and **"OKR Key Results"** (= your metrics) — as ordinary **DataSets**, which you then read via the **DataSet API**. Own the *pointer*, defer the *mechanism*:

- The DomoStats connector / report catalog and its metadata-DataSet nature → **`domo-governance-datasets.md`**.
- Querying/exporting those DataSets (DataSet API, SQL, PDP) → **`domo-datasets.md`** (+ `domo-query-dataset.md` for SQL).
- Source article: KB `4577793742615` "Accessing Goals Data" — **body UA-gated, needs-live-verify**; the DataSet names ("OKR Objectives"/"OKR Key Results") are the load-bearing fact.

Do NOT restate the DataSet API contract here.

## Currency (`[KB]` / `[LIVE]`) — verified current

- **Goals is a current, shipping surface.** Confirmed live at `domo.com/business-apps/goals` (also reachable under the automation / intelligent-apps product nav), the Goals Center KB topic `0TO5w000000ZanmGAC`, and Domopalooza 2025 coverage.
- ⚠ **"Domo Goals deprecated" is a false-positive trap.** Such hits almost always refer to **Microsoft Viva Goals** (a different vendor, with its own sunset timeline) or Todoist — **not** this surface. Never carry a Viva-Goals deprecation over to Domo Goals.
- ⚠ **Mobile companion staleness ≠ web-feature deprecation.** The standalone Goals **mobile** apps look stale (iOS `id1537180023`, copyright 2009–2020, ~v4.38; Android `com.domo.goals` v4.5.0, last updated 2023-11-10). A stale companion app does **not** mean the **web** Goals feature is deprecated — scope any staleness claim to the mobile app only.

## Do NOT claim as documented fact (hedge list)

The single failure mode is **over-claiming** — and wrongly declaring the surface "fully owned / exhausted / has no API / deprecated" is an **equally-bad under-claim**. Keep each at `[INFER]`/`[KB]`, never elevate:

1. **No Goals REST API** — scope it: *"No PUBLIC Goals OpenAPI spec found; absent from `llms.txt`; `goals/okr/objectives.yaml` = 404 MISSING; developer/api probes 405/401 MISSING. An undocumented surface may exist `[INFER]`."* Never "Goals has no API." A 404/405/401 = MISSING evidence, not absence.
2. **The metric ≥/≤/= operator set, the three metric sources, and the personal/team/company scoping** are `[KB]` product behavior — do not assert exact field names / JSON as `[DOC]`.
3. **Nomenclature** — the four options rename the SAME product; never treat "OKRs"/"Objectives and KPIs" as separate features (`4577172785559`).
4. **DomoStats path** — "OKR Objectives"/"OKR Key Results" DataSets are the documented data path, but KB `4577793742615`'s body is UA-gated → **needs-live-verify**; don't restate a DataSet schema you haven't confirmed.
5. **Currency** — VERIFIED-CURRENT; a "deprecated" hit is likely **Viva Goals / Todoist**; mobile-app staleness ≠ web deprecation.
6. **The five senses + external collision** — never let the card goal-line (b), the Goal-alert absence (c), the loop standing-goal (d), a nomenclature label (e), or Microsoft Viva Goals be treated as this OKR application.
7. **Do not restate** the DataSet/DomoStats read path (`domo-governance-datasets.md`/`domo-datasets.md`), the card target-line (`domo-cards.md`), the Goal-alert absence (`domo-alerts.md`), the KPI image-render API (`domo-get-kpi-card-image.md`), or the grant mechanism (`domo-identity-access.md`) here — cross-reference, don't absorb.
8. **The KB set is non-exhaustive** — never declare the Goals docs (or the surface) fully charted; a fetch failure is MISSING evidence. NEVER declare catalog/tree exhaustion.

## Safety (documentation-only — autonomous-eligible; live actions are human-gated)

This skill ships **documentation-only with ZERO API calls** — there is no documented API to call, and reading the KB is inert. The reader's action-verbs, however, are **live, people-facing executions** — gate them on explicit human intent:

- **Create / edit / copy / delete a goal or metric**, **reassign the Owner**, **update status**, **Save As Goal** — mutating; and Goals is people-centric (owners/delegates), so edits are outward-facing. Human-gated.
- **Check-in** and **Request Check-in** (pings another user), **comment**, **assign a Delegate** — outward-facing notifications / access. Human-gated.
- **Enable weekly reminder emails** — an **org-wide email-blast**. Human-gated.
- **Select the Nomenclature**, **create Time Periods**, **delete / merge Tags** — admin/taxonomy mutations (tag delete/merge is destructive to the org taxonomy). Human-gated.
- **Autonomous-eligible:** **reading** Goals data via the DomoStats OKR DataSets, and **reading** status — documentation-only READ work only (`4663374299031` + `4577172785559`).
- **Never commit** (Goals is people-centric — the strictest never-commit list in the cycle): instance hostnames + `api.domo.com` creds / dev-tokens / client-id / secret; **owner / delegate / manager NAMES and EMAILS**; **DomoStats OKR-Objectives / OKR-Key-Results DataSet GUIDs**; **OKR CONTENT itself** (objective text, target / quota / revenue values, progress figures); and **org tag taxonomies**. Placeholders only (`{instance}.domo.com`, `<datasetId>`, `<owner>`). **Customer-tied Goals data = FLAG-only** per the owned-only improvement-cycle rule — never fix/mutate it. Public Domo support address `support@domo.com` is documentation-safe.
- **Follow-up (non-blocking)**: whether to register this skill in `AGENTS.md`'s Skill-Mapping is left to human judgment — **`AGENTS.md` is on the never-edit list**, so (as with rank-53 `domo-custom-connector-authoring.md`, rank-54 `domo-sandbox.md`, rank-55 `domo-buzz.md`) this skill is registered in `README.md` only. This is the **fourth** `[KB]`-only skill awaiting that decision. (Repo holds ~54 skill files; none other is Goals.)

## Companion skills

- **`domo-cards.md`** — the KPI-card **goal / target line** (sense b, a card property) and a metric's **card** source. This skill owns the OKR app; cards owns the target-line decoration.
- **`domo-alerts.md`** — the **"Goal alert" object-type absence** (`:107`/`:180`, an `[INFER]` rule-builder negative) and the naming-table re-point at `:65` ("Goals & Metrics" → here).
- **`domo-governance-datasets.md`** + **`domo-datasets.md`** — the **only documented data path**: the DomoStats "OKR Objectives"/"OKR Key Results" DataSets and how to read them. Do not restate.
- **`domo-projects.md`** — a metric's **Projects & Tasks** source.
- **`domo-identity-access.md`** — the grant/role mechanism behind who may create or reassign goals.
- **`domo-get-kpi-card-image.md`** — the KPI-card **image-render** API (name-collision only; not a Goals endpoint).

**Reference memory:** the whole-surface-`[KB]` + fetch-failure-is-MISSING-evidence + multi-sense-disambiguation methodology is the cycle standard; see `project-domo-surface-skillization-cycle`. This is the **fourth** `[KB]`-only product-surface skill (after rank-53 custom-connector-authoring, rank-54 sandbox, rank-55 buzz).
