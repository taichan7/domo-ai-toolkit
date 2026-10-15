# Changelog

All notable changes to this repository are documented here. This project is
kept in sync with the authors' working toolkit; versions follow
[Semantic Versioning](https://semver.org/) loosely (MINOR = new
skills/apps/docs, PATCH = fixes and content refreshes).

## [1.1.1] - 2026-10-15

### Public distribution safety
- Ship unbound manifests and omit both design IDs. Deployment resolves IDs and
  Code Engine/Workflow versions on the selected instance, including fresh stacks.
- Exclude instance registries, credentials, sandbox state and caches even when
  accidentally tracked. Replace tenant UUIDs and numeric asset metadata with
  examples; remove customer/staff identifiers and private paths.
- Strip non-rendering PNG EXIF/text/time while retaining pixel and color data.
- Add a CI distribution gate for hostnames, deployment state, bindings, image
  metadata and managed content hashes. Sync rejects traversal/symlinks and preserves
  independently edited public files. ZIPs use the same release transformation.

### Reference architecture corrections
- Fix stored HTML injection in inventory trend labels when a date formatter
  falls back to an untrusted value. Confirm execution before the fix and rejection
  after it in local headless Chrome, while preserving valid date labels.
- Inventory v2.4.107: synchronize destination package and active Workflow versions;
  fail before writing bindings when a version is unresolved. Remove the shipped
  instance registry; test with synthetic local state. Scope saved state to the
  explicit instance and sandbox tag; never inherit a base registry in a sandbox.
- P/L v0.3.3 / CE v1.0.4: bind saving to the deployment's report collection and
  reject foreign/unconfigured targets before AppDB I/O. Guide v0.3.2 explains the
  current write guards and storage boundary.
- Require an explicit target, reject cross-origin credential forwarding/redirects,
  protect shared base-name writes on every instance, and suppress raw error bodies.
- Verify the active report API and all four P/L outputs rather than unused legacy
  assets. Fresh data provisioning no longer creates the obsolete dedupe package.
- Consolidate setup guidance and document reference/production limits, including
  stock concurrency and AppDB record authorization. Isolate test runtime stubs so
  both apps' Python suites can execute together.

### Verification
- Source and portable app suites, release-boundary regressions, Node/guide checks,
  live maintenance bindings and asset byte comparisons, and extracted ZIP checks.
- History/current-tree credential scans reviewed; generated SHA256 hashes and a
  synthetic store-period test key were confirmed false positives.
- Destination email delivery, physical mobile operation, fresh-instance integration
  and production load/authorization acceptance remain deployment-specific checks.

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
