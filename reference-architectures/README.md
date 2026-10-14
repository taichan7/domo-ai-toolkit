# Reference Architectures

Two complete, production-shaped Domo apps. Each is **self-contained** and can
be deployed to your own Domo instance — the provisioning scripts discover
target-instance object IDs **by name**, so no manual ID edits are needed.

> 日本語の詳細ドキュメントは各アプリの README にあります。Each app's full
> documentation is in its own README (Japanese, with an English summary at the top).

## [inventory-management-app](inventory-management-app/)

**在庫入出庫管理リファレンスアプリ** — inventory in/out management.

```text
Pro Code (PC + Domo Mobile, QR scanning)
  → Code Engine API (1 public + 6 private functions)
  → AppDB (single collection, record_type separation)
  → standard AppDB DataSet sync
  → Magic ETL (7 tiles, per-item AI commentary)
  → Dashboard → App Studio (2 pages)
  + AI notification Workflow triggered server-side by Code Engine
```

Highlights: request-ID idempotency, negative-stock prevention, master-data
CRUD with cascading deletes, sandbox namespacing for safe side-by-side
deploys.

Start here: [inventory-management-app/README.md](inventory-management-app/README.md)

## [pl-summary-app](pl-summary-app/)

**店舗損益AI分析アプリ** — store P/L AI analysis.

```text
Magic ETL (detail + summary datasets)
  → parent Workflow (store loop ∥ company-wide branch, 2 terminal nodes)
  → unified sub-Workflow (AI report generation per store / company)
  → AppDB (AI summaries)
  → App Studio page with a fully self-contained Pro Code card
    (store selector, KPI/trend/ranking tabs, AI HTML)
```

Highlights: layout-math workflow provisioning (no canvas drift), dedupe folded
into the save path, instance-aware production-write guards.

Start here: [pl-summary-app/README.md](pl-summary-app/README.md)

## Deploying one

Each app ships a prompt you can hand to an AI coding agent
(`prompts/deploy-with-agent.ja.md`) plus a canonical runbook under `docs/`.
The agent authenticates with the Domo CLI, provisions the assets, and verifies
the deploy. Set `DOMO_INSTANCE=your-instance.domo.com` first.
