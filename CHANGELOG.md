# Changelog

All notable changes to this repository are documented here. This project is
kept in sync with the authors' working toolkit; versions follow
[Semantic Versioning](https://semver.org/) loosely (MINOR = new
skills/apps/docs, PATCH = fixes and content refreshes).

## [1.1.0] - 2026-10-15

### Reference architectures
- P/L app v0.3.2 adds cancel-first confirmation before manually updating all
  store/company reports through Code Engine. The server resolves the latest
  released parent Workflow; scheduled parent triggers are removed.
- Preserve the understated enji UI. A discreet progress link opens the child
  Workflow execution list in a new tab using an instance-relative SDK path.
- Document all 15 DataFlow tiles and organize five pipeline sections using the
  bundled shared geometry engine, strict forward-edge checks and logic-equality
  round-trip validation. Cosmetic edits do not rerun the DataFlow.
- Fix stored XSS in report rendering: preserve headings, tables and prose while
  rejecting active markup, event handlers, external resources and DOM-clobbering IDs.
- Update guide v0.3.0 and deployment order: create/bind the Workflow Code Engine
  before publishing the frontend; reconcile the exact embedded card's context.

### Safety and validation
- Whole-tree secret/private-identifier/forbidden-file scan: 256 files, zero
  violations. Sanitized source sync and Markdown links pass.
- Both reference architectures: 420 Python tests passed; P/L Node suite:
  41 tests passed. Offline browser checks cover desktop/tablet/phone, confirmation
  cancellation, relative new-tab navigation and hostile report HTML rejection.
- Live maintenance verification: parent completed, all 100 stores plus company
  report saved; frontend/CE wiring and zero scheduled parent timers confirmed.

## [1.0.1] - 2026-10-15

### Reference architectures
- Inventory app v2.4.105: consistent confirmation popups before inventory
  registration, AI email notification, and master creation/update/deletion.
  The existing understated blue UI is preserved; navigation, search, refresh
  and QR input remain immediate.
- Show the exact target and proposed values before approval. Default focus
  is on Cancel; Escape, the close button and backdrop dismiss without writes.
  Trap Tab/Shift+Tab, restore focus/scroll, and prevent duplicate or stale
  approvals. Destructive actions retain irreversible/cascade warnings.
- Add offline confirmation regression tests and a zero-network Chrome
  interaction/layout harness at desktop, tablet and phone widths.
  Update the walkthrough, mobile checks and test documentation.

### Repo infrastructure
- Run the complete inventory Node test suite in CI, including the new
  confirmation regression tests.

## [1.0.0] - 2026-10-15

Initial public release.

### Starter kit
- Auth helpers and runnable scripts: `authenticate.sh`, `list-datasets.sh`,
  `query-dataset.sh`, `list-dataflows.sh`, `diagnose-etls.sh`, MCP helpers,
  `check-secrets.sh`
- Guides: quickstart, AI agent setup, API reference, Domo MCP, Magic ETL /
  Workflow / card references (English + Japanese)
- Deep references for clone/migration work under `docs/reference/`
- `templates/pro-code-app/` minimal Pro Code skeleton

### Skills library (55)
- 45 Domo surface skills (DataSets, Magic ETL, Workflows, Code Engine,
  Pro Code, AppDB, App Studio, AI Services, Alerts, Pages, Search, …)
- 10 platform-agnostic agent-workflow skills (implementation, code review,
  testing, refactoring, documentation, handoff, multi-agent collaboration, …)

### Reference architectures (2)
- `inventory-management-app` — inventory in/out management
  (Pro Code + Code Engine + AppDB + Magic ETL + AI notification Workflow)
- `pl-summary-app` — store P/L AI analysis
  (Magic ETL + parallel parent/child Workflows + AppDB + App Studio)

### Request templates
- `prompts/implementation-request-template.md`
- `prompts/review-request-template.md`
- `prompts/prompt-revision-request-template.md`

### Repo infrastructure
- CI: secret scan, Markdown link check, JSON/JS syntax, offline test suites
- `AGENTS.md` / `CLAUDE.md` agent contracts, bilingual top-level READMEs,
  `CONTRIBUTING.md`, `SECURITY.md`
