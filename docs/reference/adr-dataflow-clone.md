# ADR (Adrenaline/Databricks) Dataflow Cloning Reference

Captured during the PE Ops clone 2026-05-12. Covers the cases where source dataflows have `databaseType: "ADR"` and feed from Databricks ADC catalog tables.

## ADR vs MAGIC at a glance

| Engine | When | Behavior |
|---|---|---|
| `databaseType: "ADR"` | Source uses Spark SQL, Databricks-backed | Requires Databricks cloud integration on target. Do NOT downgrade. |
| `databaseType: "MAGIC"` | Source uses legacy MySQL | Portable across instances. |

Source flows with `databaseType: "ADR"` won't run on instances that lack a Databricks-backed ADR compute target — they fail with `ADR-4001: A referenced table(s) does not exist on the target device`.

Silently downgrading to `databaseType: "MAGIC"` is appealing but breaks Spark functions (`trunc('MM')`, `add_months`, `LATERAL VIEW explode(sequence(...))`, `date_trunc`, etc.) with a generic DP-0059 "Syntax error in expression" that points at the SQL tile but doesn't say "this is a Spark dialect mismatch."

## Prereq detector

Before attempting to clone an ADR flow, verify both:

1. **Target has a Databricks cloud integration** with a capturable UUID for the `computeCloud` field. Inspect via:
   ```bash
   curl -s "https://$TARGET_HOST/api/data/v3/datasources?limit=500&offset=0" \
     -H "X-DOMO-Developer-Token: $TARGET_REFRESH" \
     | jq '[.dataSources[]? | select(.dataProviderType == "databricks") | {id, name}]'
   ```

2. **The same source catalog tables are federated as datasets** on target. For each source `inputs[].dataSourceId`, look up its source `name` and verify a matching federated dataset exists on target.

If either is missing, emit a manual-task and abort:

```
[target instance] Configure Databricks cloud integration and federate these source tables as datasets:
  <catalog>.<schema>.<table_a>_bronze
  <catalog>.<schema>.<table_b>_bronze
  ...
Why: Source dataflows are ADR (Spark SQL) and reference these tables. Without the integration, target dataflow will fail with ADR-4001.
Verify: curl ... /api/data/v3/datasources?... | jq '... databricks ...'
```

## Required ADR fields on PUT/POST

When transforming an ADR source dataflow for target write, SET these explicitly:

```python
df["databaseType"] = "ADR"
df["settings"] = {"sqlDialect": "ADRENALINE"}
df["computeCloud"] = "<target Databricks integration UUID>"
df["draft"] = False
df["enabled"] = True
df["runState"] = "ENABLED"
```

**Stripping `computeCloud` or `settings` produces flows that CREATE fine but fail at RUN with `ADR-11: unable to create single use connection`.** This is one of the most common cross-instance ADR clone failures.

## Identity field stripping

```python
for k in ("id", "dapDataFlowId", "created", "modified", "lastExecution", "executionCount",
          "executionSuccessCount", "hydrationState", "container", "onboardFlowVersion",
          "editable", "numInputs", "numOutputs", "abandoned", "deleted",
          "responsibleUserId", "passwordProtected", "subsetProcessing",
          "triggeredByInput", "useLegacyTriggerBehavior", "neverAbandon", "paused"):
    df.pop(k, None)
```

## Input + output rewriting

```python
# Inputs[] + LoadFromVault actions both carry dataSourceId
for a in df["actions"]:
    if a["type"] == "LoadFromVault":
        a["dataSourceId"] = federated_bronze_map[a["dataSourceId"]]
for inp in df["inputs"]:
    inp["dataSourceId"] = federated_bronze_map[inp["dataSourceId"]]

# Outputs: null IDs so target allocates; suffix names with a recognizable tag
for out in df["outputs"]:
    out["dataSourceId"] = None
    out["dataSourceName"] = out["dataSourceName"] + "_<suffix>"
for a in df["actions"]:
    if a["type"] == "PublishToVault":
        a["dataSource"]["guid"] = None
        a["dataSource"]["name"] = a["dataSource"]["name"] + "_<suffix>"
        a["dataSource"].pop("cloudId", None)

df["name"] = df["name"] + " (modocorp clone)"
```

## Create + run cycle

```bash
# CREATE — response carries new dfid AND populated outputs[].dataSourceId
curl -s -X POST "https://$TARGET_HOST/api/dataprocessing/v1/dataflows" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" \
  --data-binary @/tmp/dfdef-<id>-target.json

# RUN
curl -s -X POST "https://$TARGET_HOST/api/dataprocessing/v1/dataflows/<tgt>/executions" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" -H "Content-Type: application/json" -d '{}'

# POLL — every 15-30s, timeout 30min
curl -s "https://$TARGET_HOST/api/dataprocessing/v1/dataflows/<tgt>/executions?limit=1" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH"
# state in (SUCCESS, FAILED_DATA_FLOW, FAILED)
```

## Output mapping — match by NAME not POSITION

**The CREATE response's `outputs[]` may return entries in a DIFFERENT order than source.** Mapping by array index swaps UUIDs and downstream dataflows fail with mysterious DP-50000 errors (rows-read > 0 but join produces nonsense).

```python
# CORRECT
src_by_name = {o["dataSourceName"] + "_<suffix>": o for o in src_outputs}
tgt_by_name = {o["dataSourceName"]: o for o in resp["outputs"]}
output_map = {src_by_name[n]["dataSourceId"]: tgt_by_name[n]["dataSourceId"] for n in src_by_name}

# WRONG — silently swaps UUIDs
# for i, src_out in enumerate(src_outputs):
#     output_map[src_out["dataSourceId"]] = resp["outputs"][i]["dataSourceId"]
```

## Dependency ordering

If dataflow B's `inputs[]` includes one of dataflow A's outputs, run A to SUCCESS before transforming B (so the bridge map can include A's new output UUIDs).

For PE Ops, the order was:
- A.5a parallel: df 14 + df 17 (bronze inputs only)
- A.5b sequential after A.5a SUCCESS: df 15 (consumes df 14 output) + df 19 (consumes df 17 output)

## Spark → MySQL translation cheatsheet

If the user chooses to downgrade ADR → MAGIC despite the recommendation, these are the functions that need rewriting:

| Spark (ADR) | MySQL (MAGIC) |
|---|---|
| `trunc(col, 'MM')` | `DATE_FORMAT(col, '%Y-%m-01')` |
| `date_trunc('month', col)` | same |
| `add_months(col, n)` | `DATE_ADD(col, INTERVAL n MONTH)` |
| `months_between(a, b)` | `TIMESTAMPDIFF(MONTH, b, a)` |
| `LATERAL VIEW explode(sequence(start, end))` | requires generated calendar dataset; can't translate inline |
| `sequence(start, end)` | requires generated calendar dataset |
| `concat(year(col), monthname(col))` | works in both |
| basic `CASE WHEN` | works in both |

If any source SQL/Expression tile uses `sequence(...)` or `LATERAL VIEW explode`, the only honest path is either (a) keep ADR with the Databricks integration, or (b) refuse to clone and emit a manual-task: the dataflow logic must be rewritten by the user.

## Where it broke in PE Ops (case study)

- First attempt: bronze datasets weren't on ADR cluster → ADR-4001 at RUN.
- Second attempt: stripped `computeCloud` + `settings` thinking they were source-instance specific → ADR-11 at RUN.
- Third attempt: matched outputs by array index → df 15 hit DP-50000 with 1505 rows-read because it joined on (property_id, unit_number, tenant_id) against the wrong silver dataset (uuids got swapped).
- Fourth attempt: full recipe above + user-provisioned Databricks integration → all 4 dataflows reached SUCCESS.

The recipe in this file reflects the working fourth-attempt state.
