# Docs Index

Guides and references. Most guides have a Japanese twin (`*.ja.md`).

## Getting started

| Doc | What it covers |
|---|---|
| [quickstart.md](quickstart.md) / [ja](quickstart.ja.md) | First-run setup: CLI, auth, first API call |
| [ai-agent-setup.md](ai-agent-setup.md) / [ja](ai-agent-setup.ja.md) | Point Claude Code / Cursor / other agents at this repo |
| [domo-auth.md](domo-auth.md) | Auth conventions: CLI session, SID, developer tokens |

## API & feature references

| Doc | What it covers |
|---|---|
| [api-reference.md](api-reference.md) / [ja](api-reference.ja.md) | Auth flow + the endpoints used across this toolkit |
| [domo-mcp.md](domo-mcp.md) / [ja](domo-mcp.ja.md) | Domo MCP toolkits: endpoints, handshake, verified paths |
| [domo-magic-etl-reference.md](domo-magic-etl-reference.md) | Per-tile / per-engine Magic ETL feature reference |
| [domo-workflow-reference.md](domo-workflow-reference.md) | Per-shape / per-action Domo Workflows reference |
| [domo-cards-reference.md](domo-cards-reference.md) | Standard card / chart types |
| [domo-cards-configuration.md](domo-cards-configuration.md) / [ja](domo-cards-configuration.ja.md) | Native-card bindings, properties, definition authoring and app placement |
| [domo-card-config-catalog.json](reference/domo-card-config-catalog.json) | Searchable role/property metadata for 71 observed chart codes; query with `scripts/domo-card-tools.py` |

## Deep references (clone & migration work)

Under [reference/](reference/):

| Doc | What it covers |
|---|---|
| [adr-dataflow-clone.md](reference/adr-dataflow-clone.md) | DataFlow clone architecture decision record |
| [app-studio-clone.md](reference/app-studio-clone.md) | App Studio clone procedure |
| [dataset-bridging.md](reference/dataset-bridging.md) | Dataset bridging between instances |
| [mapping-table.md](reference/mapping-table.md) | Object-ID mapping table pattern |
| [workflow-env-vars.md](reference/workflow-env-vars.md) | Workflow environment-variable handling |

The operational skill that uses these references is
[../skills/domo-cross-instance-clone.md](../skills/domo-cross-instance-clone.md).

For surface-by-surface operating notes, see the [skills library](../skills/README.md).
