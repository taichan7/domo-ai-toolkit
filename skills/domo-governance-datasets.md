# Domo DomoStats & Governance Datasets Skill

Use this when a task **reads Domo's own operational metadata** — the inventory of Datasets, Cards,
Pages, Dataflows, Beast Modes, Groups, Users, and PDP policies in an instance; who used what (the Activity
Log); or credit/consumption figures. This is the data that powers governance dashboards, asset-lifecycle /
"what's unused" apps, adoption reporting, and cost attribution.

The surface is the **exact inverse of the identity API** (`domo-identity-access.md`, a large documented
island). Here there is **almost no documented island at all**: DomoStats and Governance metadata are **not a
REST API namespace** — there is no `/api/governance/v1`, no `/api/domostats`, no "Governance" OpenAPI. That
metadata exists only as **DataSets that two Domo-native connectors materialize on a schedule**, which you
then read with the **ordinary DataSet query/read API** (owned by `domo-datasets.md`). So this skill is mostly
`[KB]` (connector product behavior) and `[REPO]` (how this repo actually consumes it), with the read
mechanics deliberately deferred to a neighbor skill. Its job is to keep you from three specific mistakes:
inventing a governance endpoint, mistaking the Activity Log *dataset* for the Activity Log *API endpoint*,
and being lured by the unrelated "Roles Governance API" that merely shares the word "governance".

Scope boundaries — use the neighbor skill instead when:

- it's **reading/querying/importing the resulting DataSet rows** — `POST /api/query/v1/execute/{id}`, the
  public `GET /v1/datasets/{id}/data`, the in-app `domo.get('/data/v1/<alias>')` /
  `domo.post('/sql/v1/<alias>')` proxies, Stream imports, pagination → [`domo-datasets.md`](domo-datasets.md)
  **owns all of that**. This skill tells you *which* DataSet holds the metadata and how it got there; the
  read/query contract is a cross-ref, never restated here;
- it's the **Activity Log *API endpoint*** — the instance-host `GET /api/audit/v1/user-audits` (dev-token)
  or the public Platform-OAuth `GET /v1/audit` — → [`domo-identity-access.md`](domo-identity-access.md) owns
  the audit endpoints. This skill covers only the Activity Log **dataset** (a DomoStats connector report).
  See the "three Activity Logs" section for the boundary;
- it's the **"Roles Governance API"** (`/api/authorization/v1/roles`, editing a *role's grants*) → that is
  RBAC role management on [`domo-identity-access.md`](domo-identity-access.md), **not** this surface, despite
  the shared word "governance" (see the trap section);
- it's **merging these metadata DataSets in a dataflow** (the usual real-world consumption pattern) →
  [`domo-magic-etl.md`](domo-magic-etl.md) owns the ETL; this skill supplies the inputs;
- it's the **tokenless CE `send_request` mechanic** a Code Engine reader rides on →
  [`domo-code-engine.md`](domo-code-engine.md).

## Evidence tiers

Every load-bearing line below carries a tier. Almost nothing here is `[DOC]`: the connector facts are `[KB]`
help-center product behavior, and everything the repo does with them is `[REPO]`. Re-verify any `[KB]`,
`[REPO]`, or `[INFER]` line against the live connector and the current docs before depending on it — the
report catalogs, column schemas, and admin gating are all **connector-version- and instance-specific**.

```
[DOC]   Official Domo developer documentation — the developer API reference
        (developer.domo.com / docs portal OpenAPI pages) or a machine-readable
        OpenAPI YAML in Domo's doc-hub. NOTE: a domo.com/docs/s/article/<12-digit-id>
        page is a Salesforce knowledge-base help article = [KB], NOT [DOC], even
        though it is served from the docs domain. Almost nothing on THIS surface is
        [DOC] — the two exceptions are noted explicitly.
[KB]    Domo Knowledge Base / connector help articles / support center. Connector
        existence, report catalogs, column lists, admin gating, refresh behavior,
        documented side effects, limits. Product behavior — NOT an API contract.
[REPO]  Verified only against this repo's working usage on a live instance — NOT in
        public docs. Dataset ids, row/column counts, dataflow names, derived column
        names and enum vocab. Single-instance; re-verify per instance/version.
[INFER] Reasoned from the documented model, community/forum posts, marketing, or the
        ABSENCE of a documented endpoint. Plausible, not first-party. Verify live.
```


## The headline: no governance API — a connector that materializes DataSets

State the model **positively**, because the tempting negative is an over-claim:

> **The documented access path is: a connector materializes a DataSet → you read that DataSet with the
> ordinary DataSet query/read API.** `[KB]` for the connector half, `[DOC]` for the read half (owned by
> `domo-datasets.md`).

The corollary everyone wants to write — *"therefore Domo has no governance/DomoStats REST API"* — is
**`[INFER]`, not a documented fact.** It rests on two things that are individually weaker than they look: the
`domo.com/docs/llms.txt` OpenAPI catalog enumerates specs for DataSet/Stream/User/Group/Page/Card/Account/
Auth/ActivityLog/Search/Projects and contains **no** DomoStats or governance-metadata spec (`[DOC]`, but only
for "absent from *this* catalog" — `developer.domo.com/portal` was blocked with a 405, so exhaustiveness is
unverified), plus this repo's own `api-reference.md:428` note and a repo-wide grep that finds **zero**
`/api/governance` or `/api/domostats` paths (`[REPO]`). Absence in an authoritative-but-non-exhaustive index
plus absence in one repo is a strong practical signal — **but Domo ships undocumented instance `/api/*`
routes**, so write *"no governance REST API is **documented**; consume via connector → DataSet → query API,"*
never *"no governance API exists."*

Why it matters: the whole surface is **admin-provisioned data**, not a live endpoint. If the connector's
DataSet hasn't been created on the target instance, there is nothing to query — you cannot "just call the
governance API," because there isn't one. The first question on any instance is always *"has an admin run the
connector, and what is the resulting DataSet's id?"* — never *"what's the endpoint?"*

## The two connectors (mental model)

Two **different** Domo-native connectors provision this metadata `[KB]`. They are not the same connector and
do not have the same catalog, auth, or gating — conflating them is a common mistake:

| | **DomoStats Connector** | **Domo Governance Datasets Connector** |
|---|---|---|
| KB article | `360043433813` | `360056318074` |
| Focus | Broad: object metadata **+ activity + credits + adoption** | Narrow: **object metadata inventory** only |
| Catalog size | Large (`[KB]` overview says "~90+"/"120+" report types; treat the number as marketing, the exact list as verify-in-product) | Smaller (`[KB]` help table lists ~14–18 reports as of fetch; connector-version-specific) |
| Includes Activity Log / Buzz / Credits? | **Yes** — Activity Log, Buzz, Credit reports are DomoStats reports `[KB]` | **Not in the documented report table** `[INFER]` — do not assert it "cannot", only that the table doesn't list them |
| Auth to configure | **No credentials** — Admin (default) security role to CREATE `[KB]` | **Domo Access Token**: `APIKEY` = access token, `CUSTOMER` = subdomain `[KB]`; the token owner needs instance-wide visibility `[INFER]` |
| Card→dataset report name | `Card Datasource` (**singular**) `[KB]` | `Cards and Datasets` `[KB]` |
| Documented side effect | — | Importing/refreshing makes the **token owner appear in Activity Logs as visiting every Card and Dashboard every day** `[KB]` |

Both emit **ordinary DataSets** once configured — nothing special about how you read them. The report
catalogs above are **point-in-time `[KB]` snapshots**: they grow across connector versions, some field-level
schemas are documented as "forthcoming," and which reports actually exist on an instance depends on which an
admin provisioned. Never present either catalog as fixed, complete, or portable.

## How you actually read it — connector → DataSet → query API

The read is **not special** — it is the generic DataSet path, and it belongs to
[`domo-datasets.md`](domo-datasets.md). This skill does **not** restate that contract; the steps are:

1. **An Admin configures the connector** (DomoStats or Governance Datasets) and selects the report(s). This
   creates one DataSet per report. `[KB]` — this is an admin/product action, not an API call you make.
2. **Discover the resulting DataSet's id** — by name in the Data Center, or via the DataSet list/Search API
   (`domo-datasets.md`). The id is **instance-specific**; never hard-code it (see repo precedent).
3. **Read/query the rows** with whatever the neighbor skill documents — the in-app `domo.get`/`domo.post`
   proxies, the server-side SQL/query endpoints, or the public data GET. `[DOC]`, owned by
   `domo-datasets.md`.
4. **In practice this repo does not read the reports directly at runtime** — it merges roughly ten of them
   through a Magic ETL dataflow into **one** derived output DataSet and reads only that (see repo precedent).
   That is one app's design choice `[REPO]`, not a Domo-mandated pattern.

Because it is just a DataSet, everything DataSets support applies: PDP row policies **can** be attached to it
like any DataSet (it is *not* documented as PDP-filtered by default — hedge both ways, and treat the rows as
**sensitive instance-wide metadata**), sharing is ordinary DataSet sharing, and refresh cadence is whatever
the connector's Scheduling pane was set to `[KB]` (no fixed built-in cadence, except the Activity Log's
own windowing below).

## The DomoStats connector `[KB]`

The broad connector (KB article `360043433813`). Provisions object-metadata **and** activity, credit, and
adoption reports.

- **Creation is Admin-gated `[KB]`.** It requires the **Admin (default) security role** to CREATE the
  DataSets / install the QuickStart apps, and needs **no credentials**. Write it as "Admin (default) role" —
  a custom role carrying the equivalent grants is plausible but undocumented, so do **not** claim only the
  built-in Admin role qualifies. Gating is **create-only**: once created, the DataSets follow **ordinary
  DataSet sharing** and can be shared with any user — state both halves, or it reads as "admin-only data."
- **Report catalog `[KB]`.** The overview cites a large number ("~90+" / "120+"); treat that **count as
  marketing** and the **exact list as verify-in-product**. Confirmed-by-name examples include `Activity Log`,
  `Buzz`, `Card Datasource` (singular), `Cards`, `DataSets`, `Pages`, `Groups`, `DataFlows`, `Credit Usage`,
  `People`, and QuickStart-app families. Newer names (AI Services, Workflows) and granular PDP/legacy report
  names came only from thin extraction — cite the exact spelling from the **in-product Report menu**, not
  from memory, or the report won't be found.
- **Four QuickStart Appstore apps `[KB]`**: *Activity Log*, *DataSets and DataFlows*, *People*, *Projects and
  Tasks* — each refreshes once/day and needs the Admin grant to deploy.
- **Documented limitation `[KB]`, connector-version-specific:** you **cannot cleanly combine** a "Certified
  Content" DomoStats DataSet with an "Activity Log" DomoStats DataSet in one import. The evidence states only
  *that* a limitation exists — do not invent the mechanism or a workaround.
- **`People` vs `Users`:** the DomoStats user report is named `People` (with `User Activity`, `Role Grants`);
  whether DomoStats has a report literally named `Users` is **`[INFER]`** (absence in a possibly-truncated
  list) — the plain `Users` report is the **Governance** connector's. Don't assert DomoStats "lacks a Users
  report" as fact.

## The Governance Datasets connector `[KB]`

The narrow connector (KB article `360056318074`). Provisions an **object-metadata inventory** — the "what
exists and how is it wired" side — and **not**, per its documented report table, the activity/credit/adoption
reports.

- **Auth is a Domo access token, not a role grant `[KB]`.** Configuring it needs a Domo **Access Token**
  supplied as two connector fields: `APIKEY` = the access token value, `CUSTOMER` = the instance subdomain.
  This is the sharpest contrast with DomoStats (no credentials, Admin-to-create): here **anyone who can
  create a DataSet and holds a token can run it** — there is **no documented Admin requirement** for the
  Governance connector. Do **not** claim the two connectors share admin gating (that was a caught over-claim);
  admin-scoping this connector is `[INFER]`.
- **The token owner needs instance-wide visibility `[INFER]`.** The rows describe *every* Card/Page/Dataset,
  so the token's owner must be able to see them all; a low-privilege token yields a partial inventory. This is
  reasoned from the data model, not a stated requirement.
- **Documented side effect — the loud one `[KB]`:** because the connector authenticates as the token owner
  and touches every object daily, **that user shows up in Activity Logs as having visited every Card and
  Dashboard every day.** Flag this before anyone provisions it against a real person's token — it pollutes
  adoption metrics and can alarm a governance reviewer. Prefer a dedicated service identity's token.
- **Report catalog `[KB]`, ~14–18 as of fetch.** The documented table includes inventories such as `Cards and
  Datasets` (the card→dataset map — note the name), `DataFlows`, `Pages`, `Users`, `Groups`, `Page
  Collections`, `PDP Policies`, and certification/ownership columns. The **exact set is
  connector-version-specific** and some field definitions were marked "forthcoming" — verify the live report
  list, don't quote this range as fixed.
- **It is not the Governance *Toolkit*.** Admin → Governance in-product (the Governance Toolkit UI) is a
  **separate, grant-gated feature** for policy/bulk management — it is *not* this connector and does not share
  its report catalog. Keep the two apart in any explanation.

## "Activity Log" means three different things

"Activity Log" is used for **three distinct things** in Domo, and only the third belongs to this skill. The
same underlying audit stream feeds all three, but they are **not row-identical** — the connector windows,
adds batch columns, and converts timezones — so never treat one as a drop-in for another.

| # | What it is | Access | Owned by |
|---|---|---|---|
| 1 | The in-product **Governance › Activity Log** page (a UI report) | Admin UI | product UI — not an API |
| 2 | The Activity Log **API endpoint** — instance `GET /api/audit/v1/user-audits` (dev-token) `[DOC]` cross-ref, and public Platform-OAuth `GET /v1/audit` (`/v1/audit` + scope `audit` specifics are forum-sourced `[INFER]`) | Bearer / dev-token | **`domo-identity-access.md`** |
| 3 | The Activity Log **DataSet** — a DomoStats connector report `[KB]` | connector → DataSet → query API | **this skill** (read via `domo-datasets.md`) |

This skill covers **only #3**. The distinction matters operationally:

- **#2 is live and pull-on-demand; #3 is a scheduled materialization.** If you need this instant's events,
  hit the endpoint (#2, identity skill). If you need a queryable historical table joined against other
  metadata, use the DataSet (#3).
- **The DataSet's load behavior `[KB]`:** the Activity Log DomoStats report does an **initial load of ~the
  last 30 days**, then runs **incrementally from the last load** on the connector's schedule; **older
  backfill is available on request** (a documented support/config path, not an API parameter you pass). Do not
  claim it holds unlimited history by default.
- **They are not equal rows.** The connector adds batch/ingestion columns, may convert timestamps to a
  configured timezone, and applies its own windowing — so a row count or a timestamp from the DataSet will not
  match the raw endpoint one-for-one. Reconcile on event id / natural keys, never on "the counts should
  match."

## Credits & consumption `[KB]` / `[REPO]`

Credit / consumption reporting is a **DomoStats** function, **not** a Governance-connector one, and **not** a
dedicated billing API. Keep three things separate — they use similar words for different numbers:

- **Where it comes from `[KB]`:** the DomoStats connector's credit reports. Confirmed report names:
  - `Credit Usage` — line items with a `creditsUsed` field and a `usageQuantity` field.
  - `Credit Balance Summary`.
  - `Credit Balance Details` — with `usedCredits`, `adjustmentCredits`, and `standardImpact` fields.
- **`creditsUsed` ≠ `usedCredits` ≠ the repo's `Credits Used` `[KB]`/`[REPO]`.** The first two are **different
  first-party fields in different reports** (Usage line-item vs Balance Details) — do not treat them as
  synonyms. The repo's `Credits Used` (see repo precedent) is a **derived display alias**, not either
  first-party column.
- **Provisioning & cadence `[KB]`:** credit reports are documented as **primary-instance-only**, gated behind
  a **"View Credit Reports"** grant, and refreshed roughly **daily on a UTC boundary**. Multi-instance credit
  visibility is not a default.
- **What is NOT documented `[INFER]`:** any per-operation credit *rate* (how many credits a TextGen call, an
  AI-service call, or a Dataflow run costs), and whether these connectors themselves are free or
  credit-consuming — pricing/entitlement is **plan-dependent and undocumented** (Appstore pages are
  JS-gated). Never quote a credit price or a per-op cost as fact; if asked, say it is plan-specific and point
  to the Credit reports for the actual figures on that instance.

## Access & admin model `[KB]` / `[INFER]`

The two connectors do **not** share one access model — the single most common over-claim here is "governance
data is admin-only," which is true for one connector and unproven for the other.

- **DomoStats — Admin to CREATE, then shareable `[KB]`.** Creating DomoStats DataSets / installing its
  QuickStart apps needs the **Admin (default) security role**; no credentials. That gate is **create-time
  only** — the resulting DataSets are ordinary DataSets and can be shared with anyone afterward. Credit
  reports carry the extra **"View Credit Reports"** grant.
- **Governance Datasets — token, no documented Admin gate `[KB]`/`[INFER]`.** It authenticates with a Domo
  **access token** (`APIKEY`/`CUSTOMER`) and has **no documented Admin requirement**; that the token owner
  needs broad visibility is `[INFER]` from the data model. Do **not** state the two connectors are gated
  identically.
- **No documented default PDP `[INFER]`.** There is no evidence these metadata DataSets ship with a built-in
  PDP policy. Hedge **both** ways: PDP **can** be attached to them like any DataSet, and they are **not**
  documented as PDP-filtered by default — so treat their rows as **sensitive instance-wide metadata** (who
  owns what, who used what, credit spend) and gate sharing deliberately.
- **Observability Metrics `[KB]`:** the sanctioned way to pull DomoStats across **multiple** instances (a
  multi-instance program), distinct from the single-instance connector run — mention it only if the task is
  explicitly cross-instance.
- **Governance Toolkit ≠ these connectors `[KB]`.** Admin → Governance (the Toolkit UI) is a separate
  grant-gated management feature; it is not what provisions these DataSets.
- **The public API does not expose this metadata as its own endpoints `[INFER]`.** The repo's
  `api-reference.md:428` lists "governance datasets" among what the public API does not surface directly; that
  is a `[REPO]` note generalized to an `[INFER]` claim (absence, not a documented "unsupported"). The
  supported path remains connector → DataSet → query API.

## Schemas are connector-version-specific — verify live `[KB]`

Do **not** hard-code column names, types, or the report list from this skill (or from memory) — they are
**connector-version- and instance-specific**, and the KB documents several field sets as "forthcoming."

- **Discover columns from the live DataSet, not from docs.** Query the actual DataSet schema (via
  `domo-datasets.md`) before writing any Beast Mode, dataflow join, or `SELECT` against it. A report that
  exists on one instance may be absent on another (an admin only provisioned some), and casing/labels drift
  across connector releases.
- **Report *names* are not stable across the two connectors** — the card→dataset report is `Card Datasource`
  (singular) under DomoStats but `Cards and Datasets` under Governance; the repo's `Card Datasources` (plural)
  is neither (it is a repo label). Always confirm the exact in-product report name before telling someone "add
  the X report."
- **Completeness is not promised `[INFER]`.** Where a field or report is undocumented, that means *verify
  live* — not "it doesn't exist" and not "more is guaranteed to be coming." The workflow's refute pass
  explicitly downgraded "the remaining schemas are forthcoming" to `[INFER]`.
- **Treat any column list you write down as a snapshot.** If a downstream artifact (a dataflow, an app) binds
  to specific columns, note in that artifact that the binding is connector-version-specific and must be
  re-checked on version bumps.

## The "Roles Governance API" is a trap — it is not this surface `[DOC]`

There **is** a genuine official OpenAPI whose name contains "governance" — and it has **nothing to do with
this surface.** This is the sharpest trap on the whole surface, because the word matches and the tier is
`[DOC]`, so it looks authoritative for the wrong thing.

- **`roles-governance-api.yaml` / `/api/authorization/v1/roles` is RBAC role-grant management `[DOC]`** — it
  creates/clones a *security role* and edits that role's *authorities* (grants). It is about **what a role can
  do**, not **an inventory of instance objects**. It never returns Datasets, Cards, Pages, credits, or
  activity.
- **It is owned by [`domo-identity-access.md`](domo-identity-access.md), not this skill.** If a task is about
  editing a role's permissions, go there. If a task is about reading metadata/activity/credits, stay here —
  and it will be a connector + DataSet, never `/api/authorization/v1/roles`.
- **The tell:** "governance" in the *API* name means **access-control governance** (roles/grants);
  "governance" in *this surface's* name means **data/asset governance** (the metadata inventory). Same word,
  two unrelated domains. Reaching for the Roles Governance API to answer a "what datasets exist / who used
  what" question is the mistake this section exists to stop.

## Repo precedent — grep the token, not the line `[REPO]`

This repo consumes governance/DomoStats metadata in exactly one place, and it does so **indirectly** — every
concrete id, count, column name, and enum value below is **instance/app-specific `[REPO]`**, re-wired per
target via the app manifest's `datasetsMapping[]`. Grep for the *token* to find where a concept lives; never
copy a literal id.

- **`asset-lifecycle-app` reads ONE derived Dataflow output**, not the connector reports directly. That
  output DataSet id is `ce05d371-cea5-5ffe-88de-ee8d0972912e` (~8,642 rows × ~29–30 cols on the reference
  instance) — a Magic ETL dataflow named "Dataset Inventory" (dataflows ~2279–2282) merges roughly ten
  DomoStats/Governance inputs into it. "~ten inputs" is a **handoff label, not enumerated in the repo**; the
  merge design lives in `domo-magic-etl.md` territory.
- **All ids are placeholders.** `fcadcd24…`, `22c6779b…`, `bf20ca9c…`, `28dfe696…`, the dataflow numbers, and
  the dataflow name are the reference instance's — they are **not portable**. On a new instance they are
  discovered by name and injected through `datasetsMapping[]`; hard-coding any of them is the bug this note
  guards.
- **Derived columns and enum vocab are app-defined `[REPO]`.** `Credits Used` (a derived alias over a
  `credit_usage` figure — a Dataflow `GroupBy(entityId, SUM creditsUsed)` LEFT-joined with
  `IFNULL(...,0)` — **not** a first-party report column), plus status/category enums like `Activity Status`,
  `Scope`, `Candidate` / `Dependency Status`, and `Certified`, are all authored in the dataflow, not emitted
  by the connector. Do not describe them as connector fields.
- **The repo's own naming quirks `[REPO]`:** `api-reference.md:194` uses `Card Datasources` (**plural**) for
  the card→dataset mapping — that is repo shorthand, not the documented report name (DomoStats:
  `Card Datasource` singular; Governance: `Cards and Datasets`). `api-reference.md:428` records that the
  public API does not expose governance datasets directly. Cite these as repo notes, not as Domo docs.
- **Reads are read-only.** The app treats these inputs as read-only sources; there is no repo code that
  *writes* to a governance/DomoStats DataSet (the connector owns their contents). Any "update the inventory"
  work is a connector re-run or a dataflow change, never a row write from the app.

## Do NOT claim as documented fact

These are the specific over-claims the verify/refute pass caught or guarded. Each is a line you might be
tempted to state as fact; state it only with the hedge shown.

1. **"Domo has no governance / DomoStats REST API."** → `[INFER]`, not fact. Say *"no governance REST API is
   **documented**; the documented path is connector → DataSet → query API."* Absence from a non-exhaustive
   catalog (and a 405-blocked portal) is not proof of non-existence; Domo ships undocumented instance
   `/api/*` routes.
2. **"Both connectors require Admin."** → false. Only **DomoStats** create is Admin-gated `[KB]`; the
   **Governance** connector uses token auth with **no documented Admin requirement** (`[INFER]` that the
   token needs broad visibility).
3. **"These DataSets are admin-only / locked down."** → the Admin gate is **create-time**; the DataSets are
   ordinary shareable DataSets afterward. State both halves.
4. **"The report catalog has ~90+ / ~150 reports"** (or any exact count) → the **count is marketing**; the
   **exact list is verify-in-product** and connector-version-specific.
5. **"Column `X` / report `Y` exists on this DataSet."** → schemas and report sets are
   **connector-version- and instance-specific**; discover from the **live** DataSet, don't quote this skill.
6. **"The Activity Log DataSet equals the audit API rows"** → not row-identical; the connector windows, adds
   batch columns, and converts timezones. And the **endpoint** (`/api/audit/v1/user-audits`, `/v1/audit`) is
   `domo-identity-access.md`'s, not this surface.
7. **"`creditsUsed` = `usedCredits` = `Credits Used`."** → three different things: a `Credit Usage`
   line-item field, a `Credit Balance Details` field, and the repo's **derived alias**. Don't conflate; don't
   quote a per-op credit rate (undocumented `[INFER]`).
8. **"The Roles Governance API (`/api/authorization/v1/roles`) is how you read governance data."** → no —
   that is RBAC role-grant management (`domo-identity-access.md`). Shared word, unrelated domain.
9. **"These metadata DataSets are PDP-filtered by default"** *or* **"PDP can't apply to them."** → neither is
   documented; PDP **can** be attached like any DataSet but is **not** documented as applied by default.
   Treat rows as sensitive instance-wide metadata.
10. **"The connectors are free"** *or* **"they cost N credits."** → pricing/entitlement is
    **plan-dependent and undocumented**; do not assert either.
11. **Any repo id / row count / column name as portable fact.** → all `[REPO]`, reference-instance-specific,
    re-wired via `datasetsMapping[]`.

## Safety & hygiene

- **The rows are sensitive.** Governance/DomoStats metadata is a map of the whole instance — who owns what,
  who viewed what, and credit spend. Treat it as confidential; do not paste asset names, owner emails, user
  activity, or credit figures into handoffs, commits, or external artifacts. This is instance-internal data
  even though it is "just metadata."
- **The Governance connector's token is a credential.** Its `APIKEY` (a Domo access token) and `CUSTOMER`
  (subdomain) are secrets — never write them into source, manifests, handoffs, or commits; supply them only
  through the connector's Account config or env vars. A token that can inventory the whole instance is
  high-value.
- **Provisioning writes to the token owner's audit trail.** Running the Governance connector makes its token
  owner appear to visit every Card/Dashboard daily `[KB]` — use a dedicated service identity, not a real
  user's token, and warn stakeholders so it isn't mistaken for anomalous access.
- **Don't provision on a shared validation instance without cause.** On `maintenance-instance` (a shared Domo-internal
  env) create/modify/delete only self-owned `zz-*` / `test-*` / `asset-lifecycle-test-*` assets; never run a
  connector that materializes instance-wide metadata there just to explore, and never inventory others'
  assets.
- **Reads over writes.** This surface is materialized *for* you by a connector; there is no supported
  "write governance data" path. If something looks wrong in the data, fix the connector config or the
  dataflow — never try to patch metadata DataSet rows directly.

## Companion skills

- [`domo-datasets.md`](domo-datasets.md) — **owns the read.** How to discover the DataSet id and
  query/read/paginate its rows (in-app proxy vs server SQL vs public data GET), plus PDP CRUD. This skill only
  tells you *which* DataSet and *how it got there*.
- [`domo-identity-access.md`](domo-identity-access.md) — **owns the Activity Log *endpoint*** (`/api/audit/v1/
  user-audits`, `/v1/audit`) and the **Roles Governance API** (`/api/authorization/v1/roles`, the "governance"
  name-trap). Users/groups/roles/PDP-wiring live here.
- [`domo-magic-etl.md`](domo-magic-etl.md) — **owns the merge.** The real-world consumption pattern is to
  join these metadata DataSets in a dataflow (as `asset-lifecycle-app` does); the ETL contract is there.
- [`domo-code-engine.md`](domo-code-engine.md) — the tokenless `send_request` mechanic a CE-based reader
  rides on, if you read a governance DataSet from Code Engine.
- [`domo-ai-services.md`](domo-ai-services.md) — for credit *context*: AI operations consume credits that
  show up in the DomoStats credit reports, but neither skill publishes a per-op credit rate.
- [`domo-sandbox.md`](domo-sandbox.md) — **word-collision discriminator**: Sandbox is *also* an Admin ›
  **Governance** feature, but it promotes **content definitions dev→prod** (Repositories/Commit/Promote), not
  the read-only **DomoStats/Governance metadata DataSets** this skill owns. Same "Governance" menu, opposite
  job — don't confuse content-promotion with metadata-reporting. `[KB]`
