# Domo Sandbox (Governance content-promotion / version control)

**Use this when** you are promoting, version-controlling, or reasoning about the mechanics of moving **Domo content objects** (dashboards/pages, cards, DataFlows, App Studio apps, DataSet Views, connectors) **between Domo instances** (dev→prod) or **within one instance** — Domo's admin **Governance › Sandbox** feature: its Repository / Version / Commit / Promote object model, the invite→create→commit→share→promote→logs flow, **Linked Repositories** (one-time migration of *existing* prod content into a dev instance), the four Sandbox grants + per-repository permission levels, the long "unsupported items" list, and the operational facts (revert = re-promote an older version; versions guaranteed to work for one month; destination edits overwritten by the next promotion). This is Domo's **content-promotion / release-management** surface.

**NOT for:**
- **Who exists in the instance and the grant MECHANISM** — creating the Sandbox grants on a role, per-user role assignment, the authorities API. This skill names *which* grants gate Sandbox; the grant-editing machinery lives in → **`domo-identity-access.md`**.
- Reading Domo's **operational metadata** (the inventory of DataSets/Cards/Pages, Activity Log, credits) that a governance *dashboard* consumes — a different "Governance" menu-neighbor, not content promotion → **`domo-governance-datasets.md`**.
- A **runtime / execution / isolation "sandbox"** — a Node `vm` cross-realm test realm, a sandboxed cross-origin iframe, a Python/CE execution sandbox → **`domo-procode-app.md` / `domo-procode-embedded-cards.md`** (see naming trap b; ≥4 unrelated senses of the word live in this repo).
- Pushing **DataSets / DATA to EXTERNAL subscribers** (cross-instance *data* replication / syndication) or embedding content outside the instance → **`domo-everywhere.md`** (see naming trap c — Sandbox moves *content, not data*, internally; Publish pushes *data* outward).
- The promoted objects' own authoring/CRUD APIs (App Studio apps, classic pages, cards, DataFlows, the Account credential behind a connector) → **`domo-appstudio.md` / `domo-pages.md` / `domo-cards.md` / `domo-magic-etl.md` / `domo-accounts-connectors.md`**.

## What this skill OWNS vs DEFERS

| This skill OWNS | Defers to |
|---|---|
| The Sandbox **object model** (Repository / Version / Commit / Promote / Same-Instance Promotion / Source-Dev / Destination-Prod) and the **promote/version-control feature** as documented behavior (`[KB]`). | — |
| The **end-to-end flow**: Invite/approve instance → create Repository → commit a Version → share the repository → Promote on the destination → read Sandbox Logs (`[KB]`). | — |
| **Linked Repositories** — the one-time migration of *existing* prod content into a dev instance, and the Promote-and-Link rollback semantics (`[KB]`). | — |
| The **unsupported-items** catalog and the **operational FAQ facts** (revert, 1-month guarantee, overwrite-on-repromote, 1,000-card repo limit, aborted-promotion partial state) (`[KB]`). | — |
| *Which* grants + per-repo permission levels gate Sandbox actions (names + gating logic). | `domo-identity-access.md` (the grant-EDITING mechanism / authorities API) |
| The Governance *metadata* dashboards (inventory / Activity Log / credits). | `domo-governance-datasets.md` |
| Runtime/execution/isolation "sandbox" senses. | `domo-procode-app.md` / `domo-procode-embedded-cards.md` |
| Cross-instance **data** replication / external syndication / embed. | `domo-everywhere.md` |
| The promoted objects' own authoring/CRUD APIs. | `domo-appstudio.md` / `domo-pages.md` / `domo-cards.md` / `domo-magic-etl.md` / `domo-accounts-connectors.md` |
## Evidence tiers

- `[DOC]` — reproduced from an official machine-readable OpenAPI spec / dev-portal REST reference.
- `[KB]` — documented product behavior from Domo's Salesforce KB (the Sandbox support articles). Behavior, not a REST contract.
- `[REPO]` — observed only in this repository / on a live instance.
- `[INFER]` — reasoned, not sourced. Every universal negative is at best `[INFER]`.

**⚠ Whole-surface tier = `[KB]`, NOT `[DOC]`.** Domo Sandbox is an **admin UI feature documented only in Salesforce KB articles** (`domo.com/docs/s/article/<id>`). **No REST API for it is documented in Domo's public OpenAPI catalog** (72 specs enumerated in `domo.com/docs/llms.txt`, checked 2026-09), **in the official SDKs** (which cover only DataSets/Streams/Users/Groups/PDP), **or in the developer portal**. That is a *scope-bounded* negative — **NOT** "Sandbox has no API." Any REST endpoint / verb / payload for Sandbox is **`[INFER]`**, never `[DOC]`. A 404/405 while fetching a KB page is **MISSING evidence, never proof of absence**. **Fetch pattern** (KB is UA-gated; plain curl 405s): `curl -s -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36' -H 'Accept: text/markdown' https://www.domo.com/docs/s/article/<id>.md`.

## Verification provenance

Doc-cross-check + 7-agent adversarial-refute workflow (`wf_f2b6f42c-177`; six refute lenses — fold-into-owner, not-net-new, exclude, evidence-over-claim, naming-trap, transactionality — plus a planted negative control that Sandbox is a duplicate of the runtime/VM "sandbox"). Verdict: **SKILL**, net-new confirmed (no existing `*` owned content-promotion — every "sandbox" hit in the tree is a runtime-isolation sense; capital-S content-promotion Sandbox = 0), negative control correctly rejected by all six lenses. 鉄則 satisfied: doc-cross-check + adversarial refute + per-token both-tree grep (owners + siblings + committed handoffs) ran **before** this write, and the owner-collision grep was re-run immediately before writing. Sources (read in full): KB `4403367344023` "Domo Sandbox" (main) + KB `000005059` "Domo Sandbox: Linked Repositories", fetched with the browser-UA pattern above.

## Naming traps — READ FIRST

Four collisions send promotion tasks to the wrong surface. Resolve the term before reaching for a mechanism.

| You see | Reality | Owner | Tier |
|---|---|---|---|
| **"Sandbox"** = Domo Governance content-promotion feature (Repositories, Commit, Promote dev→prod) | The subject of THIS skill. | **THIS skill** | `[KB]` |
| **"sandbox instance" / "sandbox tenant" / "development or sandbox Domo instance"** | A *non-production Domo instance* used as the promotion **source** — an environment, not the feature. **The Sandbox docs themselves use this phrasing**, and repo handoffs call `maintenance-instance` a "demo/sandbox" tenant. Same word, different noun. | environment term (no skill) | `[REPO]`+`[KB]` |
| **runtime / execution / isolation "sandbox"** | A Node `vm` cross-realm test realm (`domo-procode-app.md`), a sandboxed cross-origin iframe (`domo-procode-embedded-cards.md`), a Python exec sandbox (`magic-etl-graph-ui-layout.md`), a CE execution sandbox (a marketdata handoff). **≥4 unrelated senses in THIS repo** — the strongest collision. | `domo-procode-app.md` / `domo-procode-embedded-cards.md` | `[REPO]` |
| **Domo "Publish" / Domo Everywhere** | Cross-instance/**external** replication that **PUSHES DATA / DataSets to subscribers** (syndication). Discriminator: **Sandbox moves CONTENT not DATA, dev→prod, internal; Publish pushes DATA outward to external subscribers.** Different Admin home. | `domo-everywhere.md` | `[KB]` |
| **Repository / Commit / Version / Promote** (git-shaped words) | Looks like git; **is not** (see "Git-shaped, but not git" below). No branches/diffs/merge; selection is whole-committed-version-scoped. | **THIS skill** | `[KB]`+`[INFER]` |
## The surface, in one line

Sandbox is Domo's **admin content-promotion / release-management** feature (Admin › Governance › Sandbox): you bundle content objects into a **Repository**, snapshot them with a **Commit** into a **Version**, share the repository to another instance (or the same one), and **Promote** a chosen version to *create-then-update* those objects in the destination. It moves **content definitions, not the underlying data**. There is **no documented REST API** — every action below is a UI action; treat any programmatic path as `[INFER]`.

## Object model (`[KB]`)

| Term | Meaning |
|---|---|
| **Repository** | A collection of versioned content objects (e.g. a dashboard + its cards + Beast Modes + images). Granularity is a **design choice at creation** — Domo's guidance leans **one repository per dashboard**; a repository is capped at **1,000 cards**. |
| **Version** | A snapshot of the repository's objects at a point in time. |
| **Commit** | The action that stores a new Version. "Create initial commit" is offered (default-on) at repository creation. |
| **Promote** | Applies a chosen version to the destination: **creates** the objects on first promotion, **updates** them on subsequent promotions. |
| **Same-Instance Promotion** | Promote within one instance (must be enabled in global Sandbox settings). |
| **Source (Dev) Instance** | Where the repository is committed and shared from. |
| **Destination (Prod) Instance** | Where a shared repository is promoted (the promote action runs *on* the destination). |

## Promotable content types (`[KB]` — render BOTH source wordings, do not synthesize a single count)

The docs enumerate promotable types **inconsistently** — record both, never invent "N types":
- **Main-article intro:** pages, cards, DataFlows, App Studio apps, Views, connectors.
- **FAQ wording:** Dashboards, DataFlows, connectors, DataSet Views.

("Pages" and "Dashboards" are the same object under two names; "Views" = DataSet Views.) The authoritative constraint is the **Unsupported Items** list below, not the promotable enumeration.
## Unsupported items (`[KB]` — the full documented list; do NOT abridge to a category)

Sandbox silently omits or breaks these. This is the load-bearing constraint list — promotion appears to succeed while these are dropped.

- **App Studio:** Forms, the Workflow widget, the Queue widget, Content links, App components, Element actions, Saved filters, Annotations, large files/images.
- **DataSet Views:** Calculated columns, SQL Views, non-Domo-cloud (external) warehouse-backed Views.
- **Pages / Dashboards:** Poll Cards, Dynamic Summary Numbers in Notebook Cards, Annotations, Certifications, page ordering, Doc Cards with large files, content links, filter options.
- **DataFlows:** Recursive dataflows, password-protected dataflows, the Writeback tile, Jupyter (dataflows), the Split-Join tile, the Split-Filter tile, BYO-model AI tiles, non-Domo-cloud warehouses, PDP applied in tiles, customized UI layouts.
- **Connectors:** DataSet-via-email connectors; linked repositories that *use* connectors.
- **Custom / Pro-code Apps:** AppDB collection promotion, Enterprise Apps, Pro-Code-Editor apps, the Form-and-Dataset Brick, Bricks that use an extra AppDB.
- **General (not promotable):** Nested calculations, Workflows, Code Engine packages, Queues, Approvals, Projects & Tasks, Slideshows, Jupyter Notebooks, Workspaces, Worksheets.
- **Same-instance-promotion only (unsupported cross-instance):** Smart Text, Dynamic Summary Numbers.

## The flow (`[KB]` — all UI actions; no API)

1. **Invite / approve an instance** (cross-instance only). Source: Admin › Governance › Sandbox › Instances › **+ Invite Instance** → enter `example.domo.com` + optional alias. Destination approves under **Incoming Invites**. (Same-instance promotion skips this but must be enabled in global settings.)
2. **Create a repository.** My Repositories › **+ New Repository**; **"Create initial commit"** is default-on. For an App Studio app: pick Object Type **"Apps (App Studio)"**, optionally **"Create as a Linked Repository"** + "Create initial commit"; use **Select All Visible / Clear Selection**; set access in the **Share Access** modal.
3. **Commit a version.** **"Allow this commit to be promoted"** is default-on — **uncheck it to hold** a commit back from promotion.
4. **Share the repository.** *Instance Sharing:* Can Promote / Add All / No Access / Remove All. *User Sharing:* the People tab.
5. **Promote** (runs on the **destination**). Repositories › **Shared Repositories** › **Promote**; choose a version (**defaults to the most-recent committed**); **Map dependencies** (most common = data sources); the **Advanced** tab offers rename/remove strings (primarily for same-instance promotion).
6. **Read Sandbox Logs.** **Commit Logs** in the source; **Promote Logs** in the destination; **View More** for detail.
## Linked Repositories (`[KB]`, KB `000005059`)

A **one-time migration** that brings **existing production** content into a **development** instance *without changing production*. After the link is established, the normal direction resumes — you only ever promote **dev→prod**, and later prod promotions update the linked objects **in place** rather than duplicating them. Terms here invert the usual roles: **Production Instance = destination**, **Development Instance = source**.

Flow:
1. In **production**, create the repository for the existing content and **create the initial commit** (pick the Object Type; for App Studio the same "Apps (App Studio)" sub-flow applies).
2. Check **"Create as a Linked Repository"**.
3. In **development**, **Assign Owner** on the shared repository — the button then becomes **Promote**.
4. **Promote-and-Link**: creates the objects in dev, **creates and commits a new dev repository** containing them, shares it back to prod, and **maps onto the existing prod objects** so a later prod-side promote updates them in place (no duplicate content).
5. **Verify success** — ⚠ if Promote-and-Link errors, it **rolls back**: "will undo any completed steps from the promotion and link." (This is the one place Sandbox is transactional — contrast ordinary Promote below.)

## Permission model (`[KB]`; the grant MECHANISM lives in `domo-identity-access.md`)

**Per-repository permission levels** (set via repository sharing):
- **Co-Owner** — edit, delete, share.
- **Can Edit** — edit + share, **no delete**.
- **Can Commit** — commit only (still needs the *Manage Repositories* grant).
- **Can Promote** — promote only (still needs the *Manage Repository Promotions* grant).

**The four instance-level grants** (assigned on a role; edit them via `domo-identity-access.md`'s authorities API — do NOT restate that mechanism here):
- **Administer Sandbox** — invitations; global settings (incl. *require approvals* + *enable same-instance promotion*); **assign repository ownership** (⚠ *"Once ownership is assigned, it cannot be changed"* — **IRREVERSIBLE**); the approval template; manage ALL repositories. **Supersedes** the other two.
- **Manage Repositories** — create + commit; manage user/group + inter-instance sharing.
- **Manage Repository Promotion** — configure promotion (incl. dataset mappings); promote (incl. version select).
- **Manage All Cards, Pages and Apps (App Studio)** — the **content** grant (not a Sandbox-specific grant) that is **also required** to *commit* page-type repositories and to *promote* card/dashboard content that was **shared** (rather than owned) by the promoter.

⚠ **Grant-name spelling is inconsistent in the source** — the grants table reads **"Manage Repository Promotion"** (singular) while the rows/examples read **"Manage Repository Promotions"** (plural). Note the discrepancy; do **not** canonicalize one as the true name.
## Grant examples (`[KB]` — the composite conditions)

- **To commit a repository** you need: *Manage Repositories* (and/or *Administer Sandbox*) **+** the **"Manage All Cards, Pages and Apps (App Studio)"** content grant **(only for page-type repositories)** **+** you own or are shared the repository **+** you own or are shared the content.
- **To promote a repository** you need: *Manage Repository Promotions* (and/or *Administer Sandbox*) **+** you own or are shared the repository **+** for **each PDP-enabled DataSet** used by any card/dashboard in the repo you must be **in ≥1 PDP policy** on it **+** you own the content (**or** it is shared *and* you also hold *Manage All Cards, Pages and Apps*).
- ⚠ **"Content must be owned or explicitly shared, not merely accessible via Domo Admin-level grants."** Admin reach is not a substitute for ownership/sharing here.
- **Ownership side effects of promotion:** if a repository was **never promoted before**, the promoter becomes **owner of the content created during that promotion**. Promoting a **card** also assigns the promoter **ownership of any Beast Mode tied to that card's DataSet**.
- ⚠ **PDP note:** the source doc writes **"Personalized Date Permissions"** — this reads as a typo for **Personalized *Data* Permissions** (PDP, row-level policies; see `domo-datasets.md`). Do not propagate the "Date" spelling as a distinct feature.

## Git-shaped, but not git (`[KB]`+`[INFER]`)

Repository / Commit / Version / Promote borrow git's vocabulary but **not** its model:
- **Selection granularity is whole-committed-version-scoped** (`[INFER]`) — you promote *a version of the whole repository's committed objects*. There is **no per-object cherry-pick, no diff, no branch, no merge** (`[INFER]` from the docs' silence — a universal negative, not a stated fact).
- **Linear history / revert** (`[KB]`): to revert, you **repeat the promotion choosing the desired (older) version** — there is no "undo" verb.
- **Versions are stored indefinitely but only *guaranteed to work* for one month** (`[KB]`) — an old version may fail to promote later.
- **Repository granularity is a design choice** (`[KB]`), not a branch: bundle deliberately (one repo per dashboard; 1,000-card cap).

## Transactionality is PATH-DEPENDENT (`[KB]` — never blanket-assert)

- **Ordinary Promote is NON-transactional** (`[KB]`): if a promotion is **aborted, progress stops but partial changes REMAIN and are NOT reverted**. Scope any "non-transactional / partial state remains" statement to **ordinary promote only**.
- **Linked-repo Promote-and-Link ROLLS BACK on error** (`[KB]`, KB `000005059`): it "will undo any completed steps from the promotion and link."
- Therefore: **do not** state "Sandbox promotion is (non-)transactional" as a blanket fact — always name the path.
## Operational FAQ facts (`[KB]`)

- **Sandbox moves content, not data.** Keep data in prod and expose it to dev via **Virtual DataSets** or the **DataSet Copy Connector** (see `domo-datasets.md`); raw data sources come across via **Connectors**, which need an **associated account in the target** instance (see `domo-accounts-connectors.md`).
- **Revert** = repeat the promotion, choosing the desired version.
- **Destination edits are OVERWRITTEN** by the next promotion — use **Save As** to preserve destination-side changes.
- **Repository limit: 1,000 cards.**
- **Aborted promotion**: progress stops; **partial changes remain and are not reverted** (ordinary promote).
- **Keep files < 100 MB** — this is a **suggestion**, not a documented hard cap.
- **Provisioning is NOT self-serve** (`[INFER]` gloss): the docs say "contact your Domo account team," cross-instance needs a provisioned instance, and "you may be required to complete training." (Public support fallback: `support@domo.com`.)

## Do NOT claim as documented fact (hedge list — the `must_preserve_[INFER]`)

The single failure mode is **over-claiming** — and wrongly declaring the surface "fully owned / exhausted / has no API" is an equally-bad under-claim. Keep each of these at `[INFER]`/`[KB]`, never elevate:

1. **No Sandbox REST API** — scope it: *"No REST API is documented in Domo's public OpenAPI catalog (72 specs, 2026-09), the official SDKs, or the developer portal."* **Not** "Sandbox has no API." Any endpoint/verb/payload you reason out is `[INFER]`.
2. **Git-contrast negatives** (no branch/diff/merge/cherry-pick; whole-version selection) are `[INFER]` from silence.
3. **Blanket transactionality** — forbidden; always name ordinary-promote vs Promote-and-Link.
4. **Publish/Everywhere mechanics** — cite `domo-everywhere.md`, not the Sandbox docs, for the Publish side of trap c.
5. **"Not self-serve"** provisioning is an `[INFER]` editorial gloss on "contact your account team" + "may require training."
6. **< 100 MB** is a suggestion, not a firm limit.
7. **Grant-name spelling** (Promotion vs Promotions) — a source inconsistency; don't resolve by fiat.
8. **Promotable-type count** — two source wordings; never synthesize "N types."
9. **The KB set is non-exhaustive** — a 404/405 = MISSING evidence, not absence; never declare the Sandbox docs (or the surface) fully charted.

## Safety (documentation-only — autonomous-eligible; live promotion is human-gated)

This skill ships **documentation-only with ZERO API calls** — there is no documented API to call, and reading/writing the KB is inert. The reader's action-verbs, however, are **live, high-blast-radius executions** — gate them on explicit human intent:

- **Cross-instance promotion into production** — mutating and **non-transactional** (aborted = partial state remains). Human-gated.
- **Commit** and **Invite/Approve Instance** — establish shareable/promotable state across instances. Human-gated.
- **Assign Repository Ownership** — ⚠ **IRREVERSIBLE** ("cannot be changed"). Human-gated.
- Never commit instance hostnames / repository or instance IDs / account IDs / any credential verbatim — placeholders (`{instance}.domo.com`, `<repoId>`) only. Public Domo support address `support@domo.com` is documentation-safe.
- **Follow-up (non-blocking):** whether to register this skill in `AGENTS.md`'s Skill-Mapping is left to human judgment — **`AGENTS.md` is on the never-edit list**, so (as with rank-53 `domo-custom-connector-authoring.md`) this skill is registered in `README.md` only. Discoverable via README today.

## Companion skills

- **`domo-identity-access.md`** — the grant-EDITING mechanism (authorities API) behind the four Sandbox grants + per-repo permission levels. This skill names *which* grants gate Sandbox; identity-access owns *how* to create/edit them.
- **`domo-governance-datasets.md`** — the other "Governance" menu-neighbor (operational metadata dashboards); a word-collision, not content promotion.
- **`domo-everywhere.md`** — Publish/Everywhere (external **data** syndication + embed); trap c, the highest-value discriminator in both directions.
- **`domo-procode-app.md` / `domo-procode-embedded-cards.md`** — the runtime/execution/isolation "sandbox" senses (trap b).
- **`domo-datasets.md`** — "moves content not data": Virtual DataSets / DataSet Copy Connector; PDP row-policies; DataSet Views as a promotable type.
- **`domo-accounts-connectors.md`** — a promoted connector needs an **associated account in the target** instance (dual-account mapping).
- **`domo-appstudio.md` / `domo-pages.md` / `domo-cards.md` / `domo-magic-etl.md`** — the promoted objects' own authoring/CRUD APIs; cross-instance promotion of any of these object types is this skill.

**Reference memory:** the whole-surface-`[KB]` + fetch-failure-is-missing-evidence + scope-bounded-negative methodology is the cycle standard; see `project-domo-surface-skillization-cycle`.
