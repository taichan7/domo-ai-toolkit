# Domo Buzz (messaging / social-collaboration surface)

**Use this when** you are authoring, driving, or reasoning about **Domo Buzz** — the in-product **messaging / social-collaboration** feature: conversations and threads *about* Domo content (cards, dashboards, projects) or as direct/group chat, @mentions, the message-action toolbar (like/react/quote/favorite/flag/edit/delete), slash commands, **NLQ Bots**, the notification model, the Buzz layout/panes, and the roles/enablement that gate access. This is Domo's **conversation SURFACE**, not an alert delivery type.

**NOT for:**
- The **`BUZZ` alert *subscription type*** — a value in the alert `subscriptions[]` enum (`USER`/`GROUP`/`BUZZ`/`DAILY`/`WEEKLY`/`AUTO`) that names *where an alert is delivered* (into Buzz). A delivery target INTO Buzz is **not** the Buzz surface → **`domo-alerts.md`** (it explicitly scopes this at `domo-alerts.md:58`).
- The **"send Buzz" Workflow action** (outbound) and the **inbound Buzz-message Workflow trigger** — two distinct Workflow shapes, both owned by → **`domo-workflow.md`** (`:9` outbound CE-package action; `:70` inbound event trigger).
- The **OAuth `buzz` token scope** — one enum value in the six-scope token list (`account`/`audit`/`buzz`/`dashboard`/`data`/`user`). A token permission `[DOC]`, **not** evidence of a documented Buzz product API → **`domo-identity-access.md`**.
- The **Buzz DomoStats report** — an analytics DataSet *about* Buzz activity → **`domo-governance-datasets.md`**.
- The content objects a conversation is *about* (cards/dashboards/pages/projects) and their own CRUD → **`domo-cards.md` / `domo-appstudio.md` / `domo-pages.md` / `domo-projects.md`**.

## What this skill OWNS vs DEFERS

| This skill OWNS | Defers to |
|---|---|
| The Buzz **conversation / thread model**, @mentions, message-action toolbar, slash commands, **NLQ Bots**, notifications, layout/panes, roles/enablement — all as documented product behavior (`[KB]`). | — |
| The **five-sense disambiguation** of the word "buzz" (surface vs subscription-type vs workflow-action vs OAuth-scope vs DomoStats-report). | — |
| The `BUZZ` alert *subscription type* (delivery target). | `domo-alerts.md` |
| The outbound "send Buzz" action + inbound Buzz-message trigger. | `domo-workflow.md` |
| The OAuth `buzz` token scope (a token permission). | `domo-identity-access.md` |
| The Buzz DomoStats report (a metadata DataSet). | `domo-governance-datasets.md` |
| The content a conversation references, and its CRUD. | `domo-cards.md` / `domo-appstudio.md` / `domo-pages.md` / `domo-projects.md` |
| Task-creation destination (Buzz "Create task" lands in Projects & Tasks). | `domo-projects.md` |

## Evidence tiers

- `[DOC]` — reproduced from an official machine-readable OpenAPI spec / dev-portal REST reference.
- `[KB]` — documented product behavior from Domo's Salesforce KB (the Buzz support articles). Behavior, not a REST contract.
- `[REPO]` — observed only in this repository / on a live instance.
- `[INFER]` — reasoned, not sourced. Every universal negative is at best `[INFER]`.

**⚠ Whole-surface tier = `[KB]`, NOT `[DOC]`.** Buzz is a **product feature documented only in Salesforce KB articles** (`domo.com/docs/s/article/<id>`). **No public OpenAPI spec for it exists** — absent from the 67-spec `llms.txt` catalog (checked 2026-09), and a live probe returned `product/buzz.yaml` = **HTTP 404** (MISSING evidence, **not** proof of absence) while the control `product/alerts.yaml` = 200. An **undocumented REST surface under the `social` namespace** (sibling to `/api/social/v4/alerts`, which `domo-alerts.md` owns) **almost certainly exists** — but every endpoint/verb/payload is `[INFER]`, never `[DOC]`. A 404/405 while fetching a KB page is **MISSING evidence, never proof of absence**. **Fetch pattern** (KB is UA-gated; plain curl 405s): `curl -s -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36' -H 'Accept: text/markdown' https://www.domo.com/docs/s/article/<id>.md`.

## Naming traps — READ FIRST

Five senses of "buzz" live in this repo; **only sense (a) is this skill.** Resolve the sense before reaching for a mechanism — the repo already splits them (`domo-alerts.md:58`, `:151`).

| You see | Reality | Owner | Tier |
|---|---|---|---|
| **(a) Buzz the messaging SURFACE** — conversations/threads, @mentions, slash commands, NLQ bots, notifications | The subject of THIS skill. | **THIS skill** | `[KB]` |
| **(b) OAuth `buzz` token scope** | One value in the six-scope token enum (`account`/`audit`/`buzz`/`dashboard`/`data`/`user`). A token permission — **NOT** evidence of a documented Buzz product API. | `domo-identity-access.md` | `[DOC]` |
| **(c) `BUZZ` alert *subscription type*** | A value in the alert `subscriptions[]` enum — a **delivery target INTO Buzz**, not the surface. Owning an enum value is not owning the product. | `domo-alerts.md` (`:58`, `:99`, `:126`) | `[KB]`/`[INFER]` |
| **(d) Buzz DomoStats report** | An analytics DataSet *about* Buzz activity. | `domo-governance-datasets.md` (`:110`, `:154`) | `[KB]` |
| **(e) Workflow Buzz shapes — TWO** | `domo-workflow.md:9` = OUTBOUND "send Buzz" CE-package action; `domo-workflow.md:70` = INBOUND Buzz-message-as-workflow **TRIGGER** (event-driven entry). **`:70` is a trigger, NOT a "send" action.** | `domo-workflow.md` | `[KB]`/`[INFER]` |

The `BUZZ` subscription type (c) **presupposes** the Buzz surface exists as its target — by the negative-control's own logic, "email" and "SMS" channels would each "be" a whole surface, which is absurd. `domo-alerts.md:151` is the repo's own ownership seam: alerts owns `/api/social/v4/alerts` but **explicitly disclaims** sibling `social` paths (Buzz, sharing). Cite `:58`/`:151` as the repo's pre-existing discriminators — they are not distinctions newly asserted here.

## The surface, in one line

Buzz is Domo's **conversation / social-collaboration** layer: you hold **conversations** (about a card/dashboard/project, or as direct/group messages), organized into **threads**, with **@mentions**, a per-message **action toolbar**, **slash commands** (incl. **NLQ Bots**), and a granular **notification** model — surfaced across a five-pane layout with a Universal Compose bar. It has **no public REST API**; every action below is a UI action, and any programmatic path is `[INFER]`.

## Conversation & thread model (`[KB]`, main `360042925574`)

- A **conversation** is created from **New Message** (a modal): toggle **New Topic**, give it a **title**, set **private/public**, add participants. Conversations attach to Domo content (a card/dashboard/project) or stand alone as direct/group chat.
- **Threads** organize replies within a conversation. **There are no subthreads** — "you cannot create threads of threads"; the thread icon appears only on top-level conversations.
- **Privacy status is one-way**: you can switch a **private thread to public**, but **you cannot switch a public thread back to private** — ⚠ **IRREVERSIBLE**. Making a thread public **grants access to all conversation members**.
- **Membership grants access.** Adding a user/group to a conversation or thread grants them access to it (and, for referenced content, may trigger a **Grant Access** prompt — see @mentions).
- **You cannot delete a conversation** — you can only **unfollow** it. (Individual *messages* can be deleted; see the action toolbar.)
- **Create a thread based on a message** can pull in members outside the original conversation — it **grants them access** and they **continue to receive notifications**. (Outward-facing — see Safety.)

## @mentions (`[KB]`)

- Mention **users, groups, cards, dashboards, projects**, or **@all** (everyone in the conversation).
- ⚠ **Grant-Access warning**: if you @mention a **user/group that lacks access** to a referenced Card/Page/Project, Buzz offers to **Grant Access** — a **permission mutation** bundled into the posting flow (see Safety).

## Message action toolbar (`[KB]`)

Per-message actions: **Like / React** (attributed, others-visible counters), **Quote reply**, **Favorite** (per-user/private), **Flag for follow-up** (per-user/private), **Create thread**, **Create task** (lands in Projects & Tasks — notifies the assignee), **Edit**, **Delete**.

- **Delete/Edit permission**: a message can be deleted by its **author**, by the **Admin** default role, or by a **custom role with "Edit Conversations and Messages"** enabled. **Editing** mutates already-delivered, shared content.
- **Safe vs outward-facing boundary** (drawn on evidence, not left implicit): **Favorite**, **Flag for follow-up**, and **per-conversation notification settings** are **per-user/private → autonomous-eligible**; **Like/React** are attributed, others-visible writes (low-stakes outward-facing → gate); **Edit / Delete / Create-thread-adding-members / Create-task-with-assignee** are mutating/outward-facing (gate — see Safety).

## Slash commands & NLQ Bots (`[KB]` behavior / `[INFER]` payloads)

Slash commands are typed into the message box. The documented set is **explicitly non-exhaustive** (the source labels its table "some of these"):
- `/invite [email]` — invite anyone by email, **even without a Domo account**; ⚠ the email's **domain must be authorized** in Company Settings (external-user surface — see Safety).
- `/giphy [text]`, `/roll` (0–100), `/support`, `/todo [text]`.
- `/[commandname] <natural-language question>` — invoke an **NLQ Bot** (below).

**NLQ Bots** (main `360042925574` + `360043430273` "Adding a Bot to Buzz"): all NLQ Bots are **third-party connector integrations** with Buzz; **many** (not all — the doc scopes it to "many") are **webhook-based** — the third-party system **pushes** notifications into the conversation. Add via the conversation **Details pane → Bots → +**, configure per the connector's own instructions, set a **Command Name**, Save; then invoke with `/[commandname]`. Remove via the same pane's **trash-can → Delete**. The webhook payload shape is **`[INFER]`** — connector-specific, not a documented contract.

## Notifications (`[KB]`)

A **3 × 4 matrix**: **3 levels** (Mentions / All activity / None) × **4 channels** (computer pop-up / Domo Mobile / email / SMS). **Per-conversation settings inherit from the global setting** and can be **overridden per conversation**.

## Layout & entry points (`[KB]`, layout `360043429973`)

- **Five panes**: navigation, conversation, details, flag-for-follow-up, discover.
- The black top bar carries the **Buzz Menu**, a **Status** selector (Available / Busy / Away / Out-of-office), and **Universal Compose**.
- **Ctrl+Alt+x** toggles fullscreen.
- **Import Email Thread / "Email to Buzz"**: generate a **unique Buzz email address**, add it as a recipient on an email, and the thread (plus collaborators + attachments) imports into Buzz; **all collaborators are notified by email**. ⚠ Treat a generated Buzz import email address as sensitive — never commit it.
- ⚠ **Stale-doc caveat**: the layout article still shows a "Download the Buzz App" item and says web/desktop "are the same". The **main "Use Buzz" article (`360042925574`) is authoritative**: **Buzz Desktop is deprecated** — "no longer available for download; the desktop app still functions but is no longer supported." Do NOT cite the layout article's download/parity language as current.

## Roles & enablement (`[KB]`, roles `360043438953`)

- **Social** is **one of five system roles** (Social / Participant / Editor / Privileged / Admin) — the source calls it a "system role", **not literally "free"**. It is the most basic: access to **Buzz, user profiles, and Projects & Tasks**. But its scope is **not strictly** those three "only": Social users can also **subscribe to existing alerts** and **create OAuth clients** (API tokens), and (on web) **cannot open dashboards to view cards**.
- **Retention**: there is **no built-in retention/auto-purge** in Buzz — only a per-user duration for auto-removing conversations from *your own* Buzz menu.
- **Enablement**: Buzz can be **disabled per-instance** via the Domo account team / support (`[KB]`).

## The programmatic surface (no public API)

**No PUBLIC OpenAPI spec** — Buzz is absent from the 67-spec `llms.txt` catalog; `product/buzz.yaml` = **HTTP 404 (MISSING, not proof-absent)**. An **undocumented REST surface under the `social` namespace** (sibling to `/api/social/v4/alerts`, owned by `domo-alerts.md`) **almost certainly exists `[INFER]`** — but no endpoint, verb, or payload is documented, so treat any programmatic path as `[INFER]`, never `[DOC]`. **Never phrase this as "Buzz has no API."** NLQ-bot webhook payloads are likewise `[INFER]`.

## Do NOT claim as documented fact (hedge list)

The single failure mode is **over-claiming** — and wrongly declaring the surface "fully owned / exhausted / has no API" is an equally-bad under-claim. Keep each at `[INFER]`/`[KB]`, never elevate:

1. **No Buzz REST API** — scope it: *"No PUBLIC OpenAPI spec; absent from the 67-spec `llms.txt`; `product/buzz.yaml` = 404 MISSING. An undocumented `social`-namespace surface almost certainly exists `[INFER]`."* Never "Buzz has no API." A 404/405 = MISSING evidence, not absence.
2. **NLQ bots** — "**many** are webhook-based", not "all"; all are third-party connector integrations, but the doc scopes webhooks to "many" (main L289).
3. **Slash commands** — the documented list is **examples, non-exhaustive** ("some of these", main L129).
4. **"Social" role** — one of **five system roles**, not "free"; its access is not strictly Buzz+Profiles+Projects/Tasks "only" (also alert-subscribe + OAuth-client-create; no web card view).
5. **Desktop parity** — the layout article's "Download the Buzz App" / "web and desktop are the same" is **stale**; the main article's **deprecation** is authoritative.
6. **The five senses** — never let the `buzz` OAuth scope, `BUZZ` subscription type, DomoStats report, or Workflow shapes be treated as the messaging surface; the subscription type is a delivery target INTO Buzz, not the surface.
7. **Do not restate** the `BUZZ` alert-subscription contract (`domo-alerts.md`), the Workflow Buzz shapes (`domo-workflow.md`), the OAuth `buzz` scope (`domo-identity-access.md`), or the DomoStats report (`domo-governance-datasets.md`) here — cross-reference, don't absorb.
8. **The KB set is non-exhaustive** — never declare the Buzz docs (or the surface) fully charted; a fetch failure is MISSING evidence.

## Safety (documentation-only — autonomous-eligible; live actions are human-gated)

This skill ships **documentation-only with ZERO API calls** — there is no documented API to call, and reading the KB is inert. The reader's action-verbs, however, are **live, outward-facing executions** — gate them on explicit human intent:

- **Make a thread Public (Change Privacy Status)** — ⚠ **IRREVERSIBLE** (public→private is impossible) and **expands access to all conversation members**. Human-gated (mirror the sandbox skill's treatment of irreversible actions).
- **Post a message** (reaches everyone with access; **@all/@mentions notify**) and **`/invite [email]`** (invites external users — domain must be authorized). Human-gated.
- **Create a thread that adds new members** — **grants access** to the added users/groups + generates **ongoing notifications**. Human-gated.
- **Grant Access** (the @mention-without-access grant path) and **Edit a posted message** — permission/content mutations. Human-gated.
- **Delete a message or thread**, **add/remove an NLQ Bot** (third-party webhook integration), **Import Email Thread** (notifies all collaborators), and **disable Buzz per-instance**. Human-gated.
- **Create a task with an assignee** — outward-facing (**notifies the assignee**; cross-surface into Projects & Tasks). Human-gated.
- **Autonomous-eligible (per-user/private)**: **Favorite**, **Flag for follow-up**, and **per-conversation notification settings**. Documentation-only READ work is autonomous.
- Never commit a **Buzz import email address**, an **NLQ-bot webhook URL**, instance hostnames, user/group IDs, or any credential verbatim — placeholders only (`{instance}.domo.com`). Public Domo support address `support@domo.com` is documentation-safe.
- **Follow-up (non-blocking)**: whether to register this skill in `AGENTS.md`'s Skill-Mapping is left to human judgment — **`AGENTS.md` is on the never-edit list**, so (as with rank-53 `domo-custom-connector-authoring.md` and rank-54 `domo-sandbox.md`) this skill is registered in `README.md` only. This is the **third** `[KB]`-only skill awaiting that decision.

## Companion skills

- **`domo-alerts.md`** — the `BUZZ` alert *subscription type* (delivery target INTO Buzz) + the `social`-namespace ownership seam (`:58` c-vs-e split; `:151` un-charted-sibling caveat). This skill owns the surface; alerts owns the subscription type.
- **`domo-workflow.md`** — the OUTBOUND "send Buzz" CE-package action (`:9`) and the INBOUND Buzz-message workflow trigger (`:70`). Two distinct shapes; neither restated here.
- **`domo-identity-access.md`** — the OAuth `buzz` token scope (a token permission, sense b) + roles/authorities (the grant mechanism behind "Edit Conversations and Messages" and the five system roles).
- **`domo-governance-datasets.md`** — the Buzz **DomoStats report** (a metadata DataSet about Buzz activity, sense d), a word-collision with the surface.
- **`domo-projects.md`** — where Buzz "Create task" lands (Projects & Tasks board).
- **`domo-cards.md` / `domo-appstudio.md` / `domo-pages.md`** — the content objects a conversation references, and their own CRUD.

**Reference memory:** the whole-surface-`[KB]` + fetch-failure-is-missing-evidence + five-sense-disambiguation methodology is the cycle standard; see `project-domo-surface-skillization-cycle`. This is the **third** `[KB]`-only product-surface skill (after rank-53 custom-connector-authoring and rank-54 sandbox).
