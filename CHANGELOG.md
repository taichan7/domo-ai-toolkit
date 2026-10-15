# Changelog

All notable changes to this repository are documented here. This project is
kept in sync with the authors' working toolkit; versions follow
[Semantic Versioning](https://semver.org/) loosely (MINOR = new
skills/apps/docs, PATCH = fixes and content refreshes).

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
