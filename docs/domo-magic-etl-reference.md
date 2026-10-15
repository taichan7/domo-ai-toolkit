# Domo Magic ETL — Feature Reference

> Companion to the [`domo-magic-etl` skill](../skills/domo-magic-etl.md). This is a per-tile / per-engine
> reference compiled from Domo product documentation and community sources (cited per feature) plus
> live authoring verification on `maintenance-instance` (2026-09-05). Treat version-dependent notes as of that date;
> re-verify a specific tile's schema by GETting a live dataflow that already uses it before relying on exact field names.

Scope: this catalogs *what tiles/engines exist and how they appear in the DataFlow JSON*. For the
authoring workflow (GET/PUT/run/verify, the create-from-scratch recipe, safety), read the skill.

## Contents

- [Engines & execution model](#engines--execution-model)
- [Input, output & write modes](#input-output--write-modes)
- [Combine & reshape tiles](#combine--reshape-tiles)
- [Column operations & formulas](#column-operations--formulas)
- [Text & date tiles/functions](#text--date-tilesfunctions)
- [Data science & AI tiles](#data-science--ai-tiles)

## Engines & execution model

### engine

#### Magic ETL v2 (MAGIC engine / Adrenaline-backed)
*Category: engine*

- **What it does:** Domo's current visual drag-and-drop transform engine. A dataflow is a DAG of 'tiles' (actions) from input DataSet tiles through transforms to output DataSet tiles. The v2 engine ('the new Magic ETL', GA'd ~2020) replaced the old MySQL-backed engine with a columnar/Adrenaline-style engine that Domo says runs 'roughly two to four times faster' and 'now often outperforms many MySQL and RedShift DataFlows'. Ships a formula system of 200+ Beast-Mode/SQL/spreadsheet-inspired functions, plus a native SQL tile.
- **When to use:** Default choice for nearly all in-Domo transforms; recommended by Domo over MySQL/Redshift SQL dataflows for both performance and maintainability. Best for combining/cleaning DataSets visually without SQL. If a dataflow grows past ~30 action tiles some practitioners consider SQL, but Domo now steers everyone to Magic ETL/Adrenaline.
- **API / JSON representation:** Internal API family /api/dataprocessing (e.g. POST /api/dataprocessing/v2/dataflows/data-version-hydrate?engine=MAGIC). DataFlow object carries data_flow_type/engine = "MAGIC". Actions are objects with fields {id (uuid), type, name, dataSourceId, sql, dependsOn, parentActions}. Confirmed action type strings: LoadFromVault (input DataSet tile), PublishToVault (output DataSet tile), ExpressionEvaluator (Add Formula tile), SelectValues (Select/Alter Columns), Metadata, Constant, PythonEngineAction, DataHubManifestLoaderAction. Not exposed in the public developer.domo.com API — created via the private dataprocessing endpoints.
- **Config options:** Per-tile config; output tile update method (Replace/Append/Partition/Upsert); input tile Data Selection (All/New/Filter by batch); DataFlow transform settings for timezone and locale; per-column date-format handling on input tiles.
- **Gotchas:** v2 has breaking behavior differences from v1 — read Behavior Changes before authoring: null comparisons follow SQL 3-valued logic (any comparison with null yields null, treated as false by Filter Rows — must use IS NULL); date ops use company timezone not UTC; stricter date parsing (fixed unambiguous-format list); WEEK_OF_YEAR redefined (week 1 = first week containing a Sunday). Only hard limit is completing all steps within a 24-hour window; can hit out-of-memory on huge/complex flows (Rank & Window and Remove Duplicates are the most 'costly' actions; memory upgrades are requestable via support).
- **Sources:** https://www.domo.com/blog/the-new-magic-etl-faster-smarter-and-easier-etl-for-all, https://www.domo.com/docs/s/article/360047787514, https://jaewilson07.github.io/domolibrary/blog/posts/20231118%20_creatingDomoStats_MagicETL/index_v2_with_history.html, https://www.domo.com/docs/portal/35115c5c48927-datasets-api, https://community-forums.domo.com/main/discussion/55495/limit-on-ranking-tiles

#### Magic ETL v1 (legacy 'ETL' engine, MySQL-backed)
*Category: engine*

- **What it does:** The original Magic ETL engine (a.k.a. 'Legacy Magic ETL'). Same drag-and-drop tile model, but the execution engine loaded ALL input rows on every run and executed on a MySQL-derived backend. Superseded by v2; Domo lets you upgrade a v1 flow to v2 or switch back.
- **When to use:** Effectively deprecated — only relevant when maintaining old flows or when a v2 behavior change breaks a mission-critical legacy flow. New authoring should target MAGIC (v2).
- **API / JSON representation:** engine/data_flow_type distinguishes legacy 'ETL' from 'MAGIC'. Tile catalog is a subset of v2 (no Add Formula/Alter Columns/Dynamic Unpivot; older Group By/Join semantics).
- **Config options:** Upgrade path is in-product ('Upgrade to Magic ETL v2'); can revert to v1 but must re-check behavior differences.
- **Gotchas:** v1 reprocesses the entire input every run (no auto-append optimization), so it is materially slower on large inputs. v1 Join tile refuses a join when the left column has >10,000 identical values (this 10k limit was removed in v2). Converting v1<->v2 can silently change output (Column not found / Duplicate column name errors, or subtly different data).
- **Sources:** https://www.domo.com/docs/s/article/360047787514, https://www.domo.com/docs/s/article/360043427953

#### MySQL SQL DataFlow (MYSQL engine)
*Category: engine*

- **What it does:** A SQL DataFlow that runs your transforms as SQL statements against an embedded MySQL engine (not your source's MySQL — Domo spins up an embedded MySQL over the input DataSets). Supports Table Transforms (SELECT-based, produce output tables, indexable) and SQL Transforms (non-SELECT statements like stored procedures, no output table). Created under Data > Transform Data > SQL Transforms.
- **When to use:** When you prefer SQL, need custom functions/stored procedures, or want full control over indexing. Domo notes an optimized MySQL flow can beat Redshift; a single SQL statement can replace many Magic tiles. Good when maintainers are SQL-fluent.
- **API / JSON representation:** engine/databaseType = "MYSQL". SQL DataFlow definition holds ordered transform steps, each with SQL text; table transforms declare an output DataSet name and optional indexes. Created programmatically via the internal dataprocessing dataflow endpoints (no official public REST endpoint — community confirms only private API).
- **Config options:** Per-transform SQL; 'Easy Indexing' tab to add indexes on input DataSets or table transforms; Strict Mode toggle (controls MySQL handling of invalid/missing values, divide-by-zero, bad dates); processing method Entire DataSet vs append-only (only new rows since last run, requires an append-type source); Preview options (display text, null handling, decimal precision).
- **Gotchas:** DataSet name and EVERY column name MUST be <= 64 chars (MySQL identifier limit). Indexing is manual but high-leverage — Domo cites indexes cutting an 8-hour run to ~30 min. Input DataSets cannot be PDP-restricted (all rows flow through; apply PDP to outputs). Row-size errors on very wide rows (drop large text columns). Data-type conversion errors are more likely with the append method (no validation during append). MySQL version is old/embedded and not regularly upgraded.
- **Sources:** https://www.domo.com/docs/s/article/360042922994, https://domo-support.domo.com/s/article/360042935434, https://dojo.domo.com/main/discussion/52398/mysql-data-flows-clarification-mysql-version-window-functions-row-number, https://www.domo.com/docs/s/article/360043427953

#### Redshift SQL DataFlow (REDSHIFT engine)
*Category: engine*

- **What it does:** A SQL DataFlow that runs transforms as SQL against a Domo-managed Amazon Redshift (columnar MPP) backend. Same Table Transform / SQL Transform model as MySQL. Historically recommended for very large inputs (>100M rows).
- **When to use:** For SQL users who are 'a heavy Redshift shop' and want to paste existing Redshift queries, or for very large joins/appends. Note Domo now says Magic ETL v2 frequently outperforms Redshift, so Redshift is less favored than it once was.
- **API / JSON representation:** engine/databaseType = "REDSHIFT". Same SQL-transform-step structure as MYSQL flows.
- **Config options:** Per-transform SQL with Redshift dialect; ORDER BY must be specified in EVERY query that relies on ordering.
- **Gotchas:** Redshift does NOT support stored procedures. Redshift DataFlows do NOT work on Azure-backed Domo environments (AWS only). Redshift reorders data on storage after a query completes to optimize its distributed nodes, so ordering does NOT persist between transforms — re-issue ORDER BY in each dependent query. Same 64-char name limit and PDP-on-output rule as MySQL. Benchmarks show large appends run about the same in Redshift vs Magic ETL, so the >100M-row guidance is soft.
- **Sources:** https://www.domo.com/docs/s/article/360042922994, https://www.domo.com/docs/s/article/360043427953, https://domo-support.domo.com/s/article/360042935434, https://community-forums.domo.com/main/discussion/43206/appending-large-datasets-magic-etl-vs-redshift

#### Adrenaline DataFlow (ADR engine)
*Category: engine*

- **What it does:** A premium SQL DataFlow ('Adrenaline' option in the SQL dialect dropdown, released Mar 2021). Lets you write SQL directly against Domo's Adrenaline query layer (the same engine that powers cards and DataSet Views), then MATERIALIZES the result as a stored DataSet in Vault (S3-backed with disaster recovery). Positioned for supersized datasets and full-scan aggregations where Magic ETL/MySQL/Redshift fall short — 'transform 10x larger datasets in less than a tenth of the time'.
- **When to use:** Huge datasets and heavy aggregations that must scan the entire dataset; when you want SQL against the Adrenaline layer with materialized (not live-view) output. Premium/expensive add-on.
- **API / JSON representation:** engine/databaseType = "ADR". Requires the 'Edit Adrenaline DataFlow' grant — the same grant that also governs Magic ETL cloud pushdown (Snowflake/BigQuery) and Pass-Through SQL, indicating these share the Adrenaline execution path.
- **Config options:** SQL against Adrenaline; output materialized to a Vault DataSet.
- **Gotchas:** Premium feature (historically ~high 5-figure cost) — many instances don't have it, and lacking the grant surfaces confusing errors like 'Adrenaline Data Export Failed'. Distinct from DataSet Views (which are non-materialized SQL views over Adrenaline). 'Edit Adrenaline DataFlow' grant is the gate.
- **Sources:** https://www.domo.com/blog/adrenaline-dataflows-the-solution-to-supersized-datasets, https://dojo.domo.com/main/discussion/52398/mysql-data-flows-clarification-mysql-version-window-functions-row-number, https://community-forums.domo.com/main/discussion/55189/adrenaline-data-export-failed

#### Jupyter Workspaces DataFlow (JUPYTER engine)
*Category: engine*

- **What it does:** A DataFlow whose transform is a scheduled Jupyter notebook running in a Domo-managed Python/R workspace. Reads Domo input DataSets, runs notebook code, and writes output DataSets back into Domo without moving data out. Created by scheduling a notebook ('When should this DataFlow be run? > On a Schedule').
- **When to use:** Data-science / DSML workloads: custom models, heavy Python/R, work that needs a full notebook environment and managed compute rather than a single scripting tile.
- **API / JSON representation:** DataFlow type "JUPYTER"; associated dataset displayType/dataProviderType = "domo-jupyterdata", type "Jupyter". Appears in the DataFlows list with a History tab; notebook output downloadable per execution.
- **Config options:** Schedule/trigger; input & output DataSets bound to the workspace; compute resource sizing; workspace sharing with co-owners; manual Run from DataFlow options.
- **Gotchas:** Only ONE scheduled dataflow per Jupyter workspace (docs implying per-notebook scheduling are misleading — opening a second notebook and scheduling it fails). Settings/DataSets/Lineage tabs show no info for a Jupyter DataFlow (only History is meaningful). Edit only via 'Edit in Jupyter'.
- **Sources:** https://www.domo.com/docs/s/article/36004740075, https://community-forums.domo.com/main/discussion/68589/scheduling-dataflows-with-multiple-notebooks-within-a-single-jupyter-workspace, https://pypi.org/project/domolibrary/4.2.23/, https://www.domo.com/product/new-features/jupyter-workspaces

#### Magic ETL Pushdown on cloud warehouses (Snowflake / BigQuery / Databricks compute)
*Category: engine*

- **What it does:** Cloud Amplifier feature: author transforms in the Magic ETL UI but EXECUTE them on your own cloud warehouse (Snowflake, BigQuery, or Databricks) with no data movement. A 'Compute Cloud' dropdown in the Magic ETL editor selects where the ETL runs. Enables the SQL tile's Pass-Through SQL in native warehouse dialect.
- **When to use:** When source data lives in Snowflake/BigQuery/Databricks and you want governed, in-warehouse transformation (avoids moving data into Domo cloud) while keeping the low-code UI. Business users drag-and-drop; warehouse experts write native SQL in the same flow.
- **API / JSON representation:** Executes on the Adrenaline/pushdown path; gated by 'Edit Adrenaline DataFlow' grant. Compute integration configured via Cloud Amplifier (read+write/'Transform' capability).
- **Config options:** Compute Cloud dropdown per DataFlow; SQL tile dialect follows the chosen warehouse (Snowflake/Databricks/BigQuery); output update methods; on Snowflake supports Append/Upsert/Partition + Subset Processing via Snowflake Dynamic Tables and cluster keys.
- **Gotchas:** Snowflake pushdown requires a Domo Consumption (credit) agreement; all inputs must come from a SINGLE cloud (no cross-cloud or mixed Domo-cloud inputs). Python/R scripting tiles are NOT supported on Snowflake execution. Pass-Through SQL is SELECT-only (no DDL/DML); only the integration account owner (or shared users with Edit DataFlow + Can Write) can save a pass-through flow. If you change the compute engine after a run, you must delete and recreate the outputs. Service-account Snowflake role needs SELECT, MODIFY, USAGE, CREATE on referenced tables.
- **Sources:** https://www.domo.com/docs/s/article/000005815, https://www.domo.com/docs/s/article/000005455, https://www.domo.com/docs/s/article/000005557, https://www.domo.com/product/new-features/cloud-amplifier-pushdown-magic-etl

#### DataFusion (Blend)
*Category: engine*

- **What it does:** A lightweight, non-Magic/non-SQL transform that joins DataSets (by column keys) or unions them (rows, when schemas match) through a simple UI, producing a new blended DataSet. A distinct product from Magic ETL and SQL DataFlows.
- **When to use:** Quick joins/unions of existing DataSets without building a full dataflow. Superseded in most cases by Magic ETL joins.
- **API / JSON representation:** Managed under the same Data Center transform surface but a separate object type from dataflows.
- **Config options:** Join type per pair (left/inner/right); join columns.
- **Gotchas:** Slow with non-numeric joins, many join columns, or nested DataFusions — use a single Long-type numeric join key and avoid nesting. Schema-change errors are fixed by toggling join type (left->inner->left) to reset the schema.
- **Sources:** https://www.domo.com/docs/s/article/360043427953, https://www.clearpeaks.com/building-an-all-in-one-serverless-data-platform-with-domo/

### execution-internals

#### Auto Append Processing (incremental execution optimization)
*Category: execution-internals*

- **What it does:** Magic ETL v2 optimization: at each run, the engine inspects inputs/outputs/actions and, when it can prove the result is identical, processes ONLY new input rows since the last successful run and appends them to the output — dramatically reducing runtime. Fully automatic (no config).
- **When to use:** Applies automatically to eligible v2 flows; design flows to stay eligible for big speedups on growing append-style inputs.
- **API / JSON representation:** Reflected in execution History (hover the Success badge shows optimization; lower rows-processed and faster runtime).
- **Config options:** None directly; interacts with the input tile Data Selection = All (default) which still allows this optimization.
- **Gotchas:** Optimization is DISABLED by: current-date functions (NOW/TODAY/CURDATE/'Current Date and Time'); aggregation tiles (Group By, Rank & Window, Remove Duplicates, Pivot/Uncollapse Columns); Full Outer Joins (only non-outer lookup side unchanged works); any Union input that is wholly replaced or contains a disqualifying element (forces all union inputs to reprocess); and ANY use of Python or R scripting tiles (disables entirely).
- **Sources:** https://www.domo.com/docs/s/article/360051062653, https://www.domo.com/docs/s/article/360047787514

#### Data Selection on input tiles (All / New / Filter by batch)
*Category: execution-internals*

- **What it does:** Per-input-DataSet control over WHICH batches load into a Magic ETL run. All = load all rows (default, still auto-append eligible). New = load only batches updated since last successful execution (including restated partitions). Filter by batch = load specific batches by processing date or partition name.
- **When to use:** Reduce data volume per run for large/partitioned inputs; New for incremental pipelines; Filter by batch for date-windowed or partition-scoped processing.
- **API / JSON representation:** Input-tile (LoadFromVault) configuration: data-selection mode + optional Filter-By-Batch expression over batch metadata.
- **Config options:** Filter by batch offers 'Import data when' = Data processed (e.g. Last 5 Days) or a custom freeform expression over batch metadata (e.g. DATE(batch.name) >= CURRENT_DATE() - CASE WHEN DAYOFMONTH(CURRENT_DATE())=1 THEN 365 ELSE 30 END). Selection is based on DataSet METADATA (batch/partition names), not the row values.
- **Gotchas:** With New: if the source has a Replace, the next run loads all Replace batches + everything appended since. Occasionally replacing all input batches while always appending to the output can create duplicate output data.
- **Sources:** https://www.domo.com/docs/s/article/000005150

#### Output DataSet Update Methods (Replace / Append / Partition / Upsert)
*Category: execution-internals*

- **What it does:** The four ways an output tile writes results. Replace: overwrite entire output each run. Append: add results as a new batch, ignoring existing data. Partition: group rows by a partition-name column — matching partitions are replaced, non-matching appended. Upsert: use a unique key (one or more columns) to update matching rows and insert new ones.
- **When to use:** Replace for small outputs or full refresh. Append for guaranteed net-new rows. Partition for date/segment-scoped incremental updates (replace one day without rewriting all). Upsert when a few records change per run and you have a stable unique key — removes the need for recursive dataflows.
- **API / JSON representation:** Output tile = PublishToVault action; carries updateMethod = REPLACE|APPEND|PARTITION|UPSERT plus partition column / upsert key config.
- **Config options:** Partition: pick/derive partition-name column; optional 'Specify which partitions to keep' retention expression (validates the [partition.name] expression). Upsert: select key column(s) from dropdown.
- **Gotchas:** Append is the least robust — no dedup, can duplicate or lose data. Upsert key must be unique with NO null/duplicate values, and is a poor fit if you replace most records each run (use Replace). Partition cap: 3000 partitions per DataSet. Partition/Upsert are the basis of subset processing.
- **Sources:** https://www.domo.com/docs/s/article/000005541, https://www.domo.com/docs/s/article/360043430733

#### Subset Processing & Partitioning
*Category: execution-internals*

- **What it does:** Combines partitioned inputs (Data Selection) with partition/append/upsert outputs so a run ingests and updates only a SUBSET of data each time instead of full replace — dividing data into smaller managed units for faster, cheaper updates. On Snowflake pushdown it is implemented via Snowflake Dynamic Tables and can reuse existing Snowflake partitions/cluster keys.
- **When to use:** Large datasets updated frequently where full reprocessing is too slow/costly; time-series data partitioned by date; replaces older recursive-dataflow patterns for incremental loads.
- **API / JSON representation:** Input Filter-By-Batch expression + PublishToVault updateMethod=PARTITION; on cloud compute uses warehouse-native partition/dynamic-table constructs.
- **Config options:** Partition column selection, retention expression, per-input batch filters; usage-based billing model on cloud.
- **Gotchas:** Partitioning keys off DataSet metadata (partition/batch names), not data values, so the partition column must map cleanly to those groupings. 3000-partition ceiling. On Snowflake, Upsert/Partition conversion from a Domo-Magic-ETL-executed flow is not directly supported (execution-location dependent).
- **Sources:** https://www.domo.com/product/new-features/subset-processing-and-partitioning-in-magic-etl, https://www.domo.com/docs/s/article/000005150, https://www.domo.com/docs/s/article/000005455

#### Recursive / Snapshot DataFlow pattern
*Category: execution-internals*

- **What it does:** A construction pattern (not an engine) where a DataFlow uses its OWN output DataSet as one of its inputs, so each run appends to / accumulates history — because DataFlows (both SQL and Magic ETL) cannot natively append across runs like connectors. Used for snapshots and history accumulation.
- **When to use:** Building historical/snapshot tables, dedup-on-append, or accumulation when Upsert/Partition don't fit. Domo now recommends Upsert instead where possible.
- **API / JSON representation:** Realized as a normal dataflow whose input LoadFromVault dataSourceId equals its own output PublishToVault DataSet; connected via an Append Rows (Union) tile.
- **Config options:** Typical build: load prior output as input, isolate a constraint column (Select Columns), Remove Duplicates, Filter Rows where new constraint is null, then Append Rows (Union) to output.
- **Gotchas:** DANGEROUS: editing a recursive flow incorrectly can lose ALL historical data — always keep a static backup copy of the historical DataSet before editing (reverting to a prior dataflow VERSION does NOT restore lost rows). A dataflow stuck in 'Draft' state indicates a trigger loop (output feeding input); break by removing triggering inputs in DataFlow Settings.
- **Sources:** https://www.domo.com/docs/s/article/360057087393, https://www.domo.com/docs/s/article/360043427953, https://community-forums.domo.com/main/discussion/54805/reverting-back-to-the-old-dataset-version

#### DataFlow versioning & drafts
*Category: execution-internals*

- **What it does:** Every save of a DataFlow creates a version entry (Details view > Versions tab) with an optional user-entered description; you can revert to any prior version. A DataFlow can also be in a 'Draft' state (unpublished/edited, or a detected trigger loop).
- **When to use:** Roll back a broken edit; audit change history; clone before major edits as a safety net.
- **API / JSON representation:** domolibrary exposes get_versions() returning versioned dataflow objects each with version_id/version_number and their full actions list; execution History via get_execution_history(maximum=N) returns records {dataflow_execution_id, dataflow_version, begin_time, action_results[{is_success, rows_processed, begin_time, end_time, duration_in_sec}]}.
- **Config options:** Save-time description field (blank unless you type one — Domo does not auto-summarize changes).
- **Gotchas:** Version history stores the DEFINITION only, not the data — reverting does not restore data rows that were lost (critical for recursive flows). Version descriptions are empty unless authored. Draft state can silently mean a trigger loop rather than an in-progress edit.
- **Sources:** https://jaewilson07.github.io/domolibrary/blog/posts/20231118%20_creatingDomoStats_MagicETL/index_v2_with_history.html, https://community-forums.domo.com/main/discussion/62821/description-of-the-changes-made-to-every-version-of-magic-elt-dataflow, https://www.domo.com/docs/s/article/360043427953

#### Scripting tiles (Python / R) execution environment
*Category: execution-internals*

- **What it does:** In-flow Python and R tiles (Data Science section) that run custom scripts as part of a Magic ETL run, with data marshalled via the 'domomagic' API (load/unload DataFrames). Managed container environment (e.g. 'Domo 2.0' env with pinned libraries incl. domomagic 0.3).
- **When to use:** Custom algorithms/data-science steps that standard tiles can't express, running automatically every time data updates.
- **API / JSON representation:** Action type PythonEngineAction (and R equivalent) within a MAGIC dataflow.
- **Config options:** Script body; environment selection (default Domo env, or request custom environments/memory upgrades); Project Directory and /tmp for sharing intermediate data/models between scripting tiles in the same flow.
- **Gotchas:** Scripting tiles DISABLE auto-append optimization entirely (whole flow reprocesses). NOT supported on Snowflake cloud execution. Paid feature. Subject to memory limits (a documented flowchart exists for handling Python/R memory limits in v2); heavy data should be chunked.
- **Sources:** https://www.domo.com/docs/s/article/360045485833, https://domo-support.domo.com/minasan/s/article/000005117?language=en_US, https://domo-support.domo.com/s/article/8276764172951?language=en-us

#### Execution limits & performance characteristics
*Category: execution-internals*

- **What it does:** Runtime envelope common to dataflows. Per a Domo DataFlows PM, 'the only true limit in Magic ETL is whether we can complete the specified transformation steps in a 24-hour window'; runs exceeding 24h fail. Runtime variance grows with input size. Preview processes only the first 10,000 rows by default.
- **When to use:** Capacity planning; diagnosing OOM/timeout; deciding when to split into modular flows or move to Adrenaline/cloud pushdown.
- **API / JSON representation:** Execution history exposes per-action rows_processed and duration_in_sec (via History API), useful to find bottleneck tiles.
- **Config options:** Request memory upgrades / custom environments via support; break large flows into smaller modular dataflows; filter/aggregate early (DataSet Views as inputs) to cut rows before transforms.
- **Gotchas:** Rank & Window is the most compute-costly action (evaluates every row against every other row), followed by Remove Duplicates — too many can OOM. Preview passing but full run failing usually means the failing data is beyond the first 10,000 rows. Magic ETL has limited granular error handling and can fail on schema conflicts.
- **Sources:** https://community-forums.domo.com/main/discussion/55495/limit-on-ranking-tiles, https://www.domo.com/docs/s/article/360043427953, https://community-forums.domo.com/main/discussion/68373/does-domo-allow-a-dataflow-to-run-for-more-than-24-hours

#### Fixed Input & Disable Tiles (authoring/execution controls)
*Category: execution-internals*

- **What it does:** Fixed Input Tile: add literal data onto the Magic ETL canvas (typed, pasted, uploaded Excel/CSV, or AI-generated sample data), stored securely in the DataFlow and usable as an input for later transforms. Disable Tiles: 'comment out' one or more tiles so they don't run during execution, individually or by selecting upstream/downstream tiles.
- **When to use:** Fixed Input for lookup/mapping tables, prototyping, or seed data without a separate DataSet. Disable Tiles for troubleshooting or keeping historical calculations without running them every execution.
- **API / JSON representation:** Fixed Input = a Constant/fixed-data action embedded in the dataflow definition; disabled tiles carry a disabled flag and are skipped at execution.
- **Config options:** Fixed Input data entry modes; disable/enable per tile or tile group.
- **Gotchas:** Disabled tiles change the effective DAG — downstream tiles depending on a disabled tile will error or drop columns.
- **Sources:** https://www.domo.com/product/new-features/magic-etl-beta-enhancements

### portability

#### SQL tile & Pass-Through SQL inside Magic ETL
*Category: portability*

- **What it does:** A Magic ETL tile that lets you write SQL as one step of an otherwise visual flow. On cloud compute (Snowflake/Databricks) 'Pass-Through SQL' runs NATIVE warehouse SQL directly against the live warehouse; the tile has a dialect dropdown matching the chosen warehouse. Also gained window functions (running totals, rankings, moving averages) in beta.
- **When to use:** Mix SQL power (window functions, warehouse-specific functions, pasted existing queries) into a low-code flow without building a separate SQL DataFlow.
- **API / JSON representation:** SQL-type action tile within a MAGIC dataflow; sql field populated, dialect tied to compute cloud.
- **Config options:** Dialect dropdown (Snowflake/Databricks/etc.); autocomplete with database/schema/table discovery.
- **Gotchas:** Pass-Through SQL is SELECT-only (no DDL/DML); executes against the LIVE warehouse using integration credentials; requires Edit Adrenaline DataFlow grant + integration ownership/sharing. Available only with a cloud compute integration selected.
- **Sources:** https://www.domo.com/docs/s/article/000005815, https://www.domo.com/product/new-features/magic-etl-tsu6p

#### Engine portability & selection guidance
*Category: portability*

- **What it does:** How engines interoperate: all engines read/write standard Domo Vault DataSets, so outputs of one dataflow feed any other regardless of engine. But dataflow DEFINITIONS are not portable across engines — you cannot convert a Magic ETL flow into a SQL DataFlow (or vice versa); you rebuild. Magic ETL can swap its EXECUTION location (Domo Adrenaline <-> Snowflake/BigQuery/Databricks) if all inputs live on one cloud.
- **When to use:** Choosing an engine: default Magic ETL v2; SQL DataFlow (MySQL/Redshift) only for SQL-preference/stored-procedures/custom-index cases; Adrenaline/ADR or cloud pushdown for supersized data; Jupyter for data science.
- **API / JSON representation:** engine/databaseType enum values observed/used: MAGIC (Magic ETL v2), ETL (legacy Magic ETL v1), MYSQL, REDSHIFT, ADR (Adrenaline), JUPYTER; passed as ?engine= on dataprocessing endpoints and stored on the dataflow object.
- **Config options:** SQL DataFlow dialect dropdown = MySQL | Redshift | Adrenaline. Magic ETL Compute Cloud dropdown = Domo (Adrenaline) | a configured Snowflake/BigQuery/Databricks integration.
- **Gotchas:** Redshift dialect unavailable on Azure Domo. Swapping a Magic ETL flow's compute to a cloud requires all inputs on that single cloud and dropping/recreating outputs. SQL DataFlows enforce 64-char name/column limits that Magic ETL does not. Domo is steering users away from MySQL/Redshift toward Magic ETL + Adrenaline.
- **Sources:** https://www.domo.com/docs/s/article/360042922994, https://www.domo.com/docs/portal/35115c5c48927-datasets-api, https://dojo.domo.com/main/discussion/52398/mysql-data-flows-clarification-mysql-version-window-functions-row-number, https://www.domo.com/docs/s/article/000005557

**Open questions / not fully verified:**

- Exact string for legacy Magic ETL v1 in the engine/databaseType enum is inferred as 'ETL' (task-provided) but not directly confirmed in a read source; only 'MAGIC' and 'Jupyter' were seen verbatim in API/library output.
- The precise private endpoint and full JSON body to CREATE a dataflow (POST) — including the complete action 'type' vocabulary for every tile and the top-level field that sets the engine — was not fully enumerated from an official source; action types were harvested from the domolibrary SDK, not Domo docs.
- Whether Databricks appears as its own SQL-DataFlow dialect vs only as a Magic ETL compute-cloud target (Pass-Through SQL lists Databricks + Snowflake; the SQL DataFlow dropdown lists only MySQL/Redshift/Adrenaline).
- Exact per-tier row/size thresholds and memory ceilings (only the soft >100M-row guidance and the hard 24-hour completion window were confirmed).

## Input, output & write modes

### Input tiles

#### Input DataSet tile
*Category: Input tiles*

- **What it does:** Starting point of every Magic ETL DataFlow; loads an existing Domo DataSet's rows into the flow. At least one input tile is required per DataFlow (there can be many). In the tile editor you Choose DataSet, preview data (Data tab), and see owner/columns/types (Details tab).
- **When to use:** Whenever the source data already lives in Domo as a DataSet. Substitute the SQL tile or Query DataSet tile when you want to push a SELECT/subdivided load instead of loading the whole DataSet.
- **API / JSON representation:** action type "LoadFromVault". Fields observed in the domo/dataflow-actions JSON: name, id (uuid), type:"LoadFromVault", gui{x,y,color,colorSource}, dependsOn:[] (empty for inputs), removeByDefault:false, notes:[], dataSourceId (the input DataSet GUID), executeFlowWhenUpdated (bool), onlyLoadNewVersions (bool), recentVersionCutoffMs (int), columnSettings:{}, visiblePartitionColumn (null|colName), versionWindow (null|object).
- **Config options:** Choose DataSet (sets dataSourceId); Data Selection (All/New/Filter by batch); expose Partition Column Name (visiblePartitionColumn); Data Handling to lock/override column data types so upstream schema changes don't break the flow; per-column bad-value and null-value handling (e.g. treat null as empty string).
- **Gotchas:** Max 1,500 columns per DataFlow. Federated DataSets cannot be used as input (Virtual/AppDB-backed DataSets are OK). Historically input DataSets could NOT be restricted by PDP (all rows had to pass through) — a 2025/2026 update added full PDP row-level-security support inside Magic ETL, so this is version-dependent; to use a still-PDP-restricted input the builder must own the DataSet, be Admin/have Manage DataFlows grant, or be in the All Rows policy.
- **Sources:** https://www.domo.com/docs/s/article/360045402273, https://www.domo.com/docs/s/article/360055259234, https://community-forums.domo.com/main/discussion/58617, https://knowledge.domo.com/Prepare/Magic_Transforms/ETL_DataFlows/Magic_ETL_v2_Tiles:_DataSets_(Beta)

#### Query DataSet tile (cloud input)
*Category: Input tiles*

- **What it does:** Alternative input that runs a custom SELECT against a cloud-warehouse-backed DataSet and can subdivide the result into multiple smaller loads for efficient ingestion of very large tables. Available in Domo-on-Databricks (and cloud pushdown) environments.
- **When to use:** Loading large tables from a Cloud Data Warehouse (Databricks) where a plain Input tile would be too heavy; push filtering/selection into the query.
- **API / JSON representation:** Cloud-query input action carrying the SELECT text, a Query Partition Key, and a number-of-loads value.
- **Config options:** Select the (Databricks) DataSet; write a SELECT (no CTEs allowed); set the Query Partition Key (column must not be NULL); specify number of loads.
- **Gotchas:** Exclusive to cloud/Databricks compute. No CTEs in the query. Size partitions so the largest load stays under ~4GB (total size ÷ 4GB gives a starting load count); analyze distribution with COUNT(DISTINCT)/GROUP BY.
- **Sources:** https://www.domo.com/docs/s/article/360045402273

#### Fixed Input tile
*Category: Input tiles*

- **What it does:** Lets you place literal data directly on the canvas (typed, pasted, uploaded, or AI-generated) as an input, without a pre-existing DataSet. The data is stored in the DataFlow definition itself.
- **When to use:** Prototyping/validating logic, demos with placeholder data, lookup/mapping tables, or building a flow before the real input DataSet exists.
- **API / JSON representation:** Input-family action embedding the literal rows/columns and their declared types in the DataFlow JSON (not a separate DataSet).
- **Config options:** Manual cell entry (set column names/types); upload .csv/.xlsx (specify header row); or AI-generate columns/sample data (requires AI Services enabled). Connect to an Output DataSet tile to persist it as a real DataSet.
- **Gotchas:** Uploaded files capped at 10,000 rows and 1,000 columns. Data lives in the DataFlow, not as a standalone DataSet, until you output it.
- **Sources:** https://www.domo.com/docs/s/article/360045402273, https://www.domo.com/product/new-features/magic-etl-beta-enhancements

#### SQL tile as input (freeform SELECT)
*Category: Input tiles*

- **What it does:** Can substitute for an Input DataSet tile in the first position, letting you write a custom SELECT statement (and, on cloud/Snowflake, native pass-through SQL) instead of loading a whole DataSet.
- **When to use:** When a hand-written query is cleaner than assembling equivalent tiles, or to leverage warehouse-native SQL on cloud pushdown.
- **API / JSON representation:** SQL-action input carrying the query text; on Snowflake compute supports Pass-Through/native syntax.
- **Config options:** Enter the SELECT; on Snowflake compute, native Snowflake functions and pasted scripts are supported (Pass-Through SQL Tile).
- **Gotchas:** Detailed config is lightly documented for the classic engine; native pass-through SQL requires a cloud compute integration.
- **Sources:** https://www.domo.com/docs/s/article/360045402273, https://www.domo.com/product/new-features/snowflake-integration-enhancements

### Output tiles

#### Output DataSet tile
*Category: Output tiles*

- **What it does:** Required terminal tile; writes the transformed result to a Domo DataSet that can power cards or feed other DataFlows. The tile name becomes the output DataSet name. Every DataFlow must have at least one Output DataSet tile.
- **When to use:** Always — it is mandatory to materialize the flow's result. Use multiple output tiles to emit several DataSets from one flow.
- **API / JSON representation:** action type "PublishToVault" (confirmed in exported domo/dataflow-actions JSON). Fields include name (output DataSet name), id, type:"PublishToVault", gui{x,y,color,colorSource}, dependsOn (the upstream tile id feeding it), plus update-method configuration fields (update method, upsert key column(s), partition id column). On first successful run the output DataSet is created/registered ('onboarded'); before that only owner/column names/types are known.
- **Config options:** Rename tile (= output DataSet name) + description; Update Method dropdown (Replace default / Append / Partition / Upsert); when a Cloud compute integration is selected, 'Add DataSet to Cloud' plus Database/Schema/Table destination fields; preview via Run preview + Preview tab.
- **Gotchas:** Output DataSets are the correct place to apply PDP policies (not inputs). A successful run does NOT mark the output as 'Updated' if the data did not actually change. 1,500-column ceiling applies. Fixed decimals use precision/scale (19,5) — only 5 decimal places retained.
- **Sources:** https://www.domo.com/docs/s/article/360045402273, https://community-forums.domo.com/main/discussion/52496, https://www.domo.com/docs/s/article/360055259234

#### Writeback tile
*Category: Output tiles*

- **What it does:** Outputs the transformed data and pushes it to an external system via a Writeback Connector, in addition to producing a Domo DataSet. Enables reverse-ETL style integration.
- **When to use:** When the flow's result must be sent to an external destination/system, not just stored in Domo.
- **API / JSON representation:** Distinct output-family action feeding into an Output DataSet tile (must still terminate with an Output DataSet).
- **Config options:** Drag Writeback tile → Edit to set output DataSet name + description → Additional Options > Update Method (replace default / append) → Configure Writeback > choose Writeback Connector → connect downstream and end with an Output DataSet tile.
- **Gotchas:** Still requires a terminating Output DataSet tile. Only replace/append update methods are offered here.
- **Sources:** https://www.domo.com/docs/s/article/360045402273

#### Cloud pushdown output destination (Snowflake / Databricks / BigQuery)
*Category: Output tiles*

- **What it does:** When a Cloud compute integration is chosen from the compute dropdown, the Output tile writes to the cloud warehouse and exposes explicit Database / Schema / Table destination fields (Schema Picker). Output methods expand beyond Replace to include Append, Upsert, and Partition on Snowflake/Databricks.
- **When to use:** Magic ETL on Snowflake/Databricks/BigQuery where transformations execute on your own engine and results are written back as governed cloud tables.
- **API / JSON representation:** Output action carries cloud destination params (database/schema/table) plus the chosen update method; compute target selected on the DataFlow.
- **Config options:** Pick the cloud integration from the compute dropdown; 'Add DataSet to Cloud'; set Database/Schema/Table; choose Replace/Append/Upsert/Partition (subset processing).
- **Gotchas:** On Snowflake, converting an existing DataFlow to run on the cloud works ONLY if all inputs are in that Snowflake cloud AND the method is Replace or Append — Upsert or Partition will ERROR (subset processing via Snowflake Dynamic tables is the exception). Python/R Scripting tiles are NOT supported on Snowflake compute. Service account needs SELECT/MODIFY/USAGE/CREATE privileges.
- **Sources:** https://www.domo.com/docs/s/article/000005455, https://www.domo.com/product/new-features/snowflake-integration-enhancements, https://www.domo.com/product/new-features/databricks-integration-enhancements, https://www.domo.com/product/new-features/cloud-amplifier-pushdown-magic-etl

### Output write modes

#### Update Method: Replace
*Category: Output write modes*

- **What it does:** Each execution discards the output DataSet's entire contents and writes the DataFlow's latest results in their place (full overwrite).
- **When to use:** Default and safest method. Best for small/medium outputs, or whenever every row must be recomputed each run. Recommended over Upsert when most rows change each run (better performance).
- **API / JSON representation:** Update method encoded on the PublishToVault action (default). In DataSet Update Methods docs also called an 'accumulation method'.
- **Config options:** Select 'Replace' from the Update Method dropdown; no extra parameters.
- **Gotchas:** Recomputes everything — no incremental benefit. On the Snowflake/cloud pushdown engine, Replace (and Append) are the only universally supported methods.
- **Sources:** https://www.domo.com/docs/s/article/000005541, https://www.domo.com/docs/s/article/360043430733

#### Update Method: Append
*Category: Output write modes*

- **What it does:** Each execution appends its results to the output DataSet as a NEW batch, ignoring existing data. No deduplication is performed.
- **When to use:** When each run produces genuinely net-new rows (e.g. daily snapshots, event logs) that should accumulate.
- **API / JSON representation:** Update method value on PublishToVault. Underlying store keeps each append as a separate batch/version (list of uploaded files).
- **Config options:** Select 'Append' from the Update Method dropdown; no extra parameters.
- **Gotchas:** Brittle: can produce duplicated or missing rows because it never inspects existing data. Classic footgun: input using Data Selection 'New' that periodically undergoes a Replace, while the output keeps appending, accumulates duplicates. Recursive/snapshot DataFlow pattern is the traditional workaround to dedupe; Upsert now removes most need for recursion.
- **Sources:** https://www.domo.com/docs/s/article/000005541, https://www.domo.com/docs/s/article/000005150

#### Update Method: Upsert (Merge)
*Category: Output write modes*

- **What it does:** Rows whose key matches an existing row UPDATE that row in place; rows with a new key are APPENDED. Called 'Merge' in general connector/DataSet documentation. Operates at the individual-record level.
- **When to use:** When only a small number of scattered records change per run and you want to update-in-place without a recursive DataFlow. Not for replacing most rows each run (use Replace instead).
- **API / JSON representation:** Update method value on PublishToVault plus an upsert/merge key column list (one or more columns defining uniqueness). General docs call the key the 'Merge Key'.
- **Config options:** Select 'Upsert' from the Update Method dropdown, then choose one column or a combination of columns for the Upsert Key.
- **Gotchas:** The key MUST be unique — it cannot contain duplicate or null values. Upsert-backed output DataSets are exported in their entirety (like a DataSet View) rather than as a list of batch files, so they do NOT support input-side data-version filtering: an Upsert DataSet used as a later input cannot use 'Only new rows'/version filtering. Errors if you try to push an Upsert DataFlow to the Snowflake cloud engine.
- **Sources:** https://www.domo.com/docs/s/article/000005541, https://www.domo.com/docs/s/article/360043430733, https://community-forums.domo.com/main/discussion/68466, https://www.domo.com/docs/s/article/000005455

#### Update Method: Partition (partition-based upsert)
*Category: Output write modes*

- **What it does:** Groups rows into partitions by the value of a chosen column. On each run, partitions present in the new data REPLACE the matching existing partitions; partitions not present are left untouched (or appended). Optionally, non-matching partitions can be deleted via a keep-expression. Replaces whole groups, not individual rows.
- **When to use:** Efficient incremental updates of large DataSets where you re-load some slices (e.g. per-day or per-store) each run without reprocessing everything. Good for rolling-window retention.
- **API / JSON representation:** Update method value on PublishToVault plus a partition id / 'Partition name column'. An optional 'specify which partitions to keep' expression uses [partition.name] tokens.
- **Config options:** Select 'Partition' → choose the 'Partition name column' (can be a composite of multiple columns, e.g. storeID + date). Optional toggle 'Specify which partitions to keep' to define a retention/delete expression on [partition.name].
- **Gotchas:** Hard limit of 3,000 partitions per DataSet (e.g. 8 stores x daily = only ~375 days). Incoming data must contain ALL records for a partition being replaced or you lose rows. Date/day-level partitions are the usual sweet spot; use week/month for 5+ years of daily data. Partition column should not contain nulls. Errors if pushed to the Snowflake cloud engine (unless using subset processing via Snowflake Dynamic tables).
- **Sources:** https://www.domo.com/docs/s/article/000005541, https://www.domo.com/docs/s/article/360043430733, https://www.domo.com/docs/s/article/000005455

### Input data selection

#### Data Selection: All (Entire DataSet)
*Category: Input data selection*

- **What it does:** Loads every row of the input DataSet on each run. Default behavior for input tiles.
- **When to use:** Default; use when the full source must be reconsidered each run, or when transforms need all history.
- **API / JSON representation:** onlyLoadNewVersions:false and no versionWindow on the LoadFromVault action.
- **Config options:** Set Data Selection = All (default). Still eligible for automatic Auto Append Processing optimization behind the scenes.
- **Gotchas:** Slowest for large inputs; the v2 engine may still auto-optimize to append-only where results would be identical.
- **Sources:** https://www.domo.com/docs/s/article/000005150, https://www.domo.com/docs/s/article/360045402273

#### Data Selection: New (only load new versions/batches)
*Category: Input data selection*

- **What it does:** Loads only the batches added/updated to the input since the DataFlow's last successful execution (including restated partitions), instead of the whole DataSet.
- **When to use:** Incremental processing of large append-type inputs; update running aggregates/complex calcs without recomputing from scratch (a documented use case for the Scripting tile).
- **API / JSON representation:** onlyLoadNewVersions:true (with recentVersionCutoffMs and/or versionWindow) on the LoadFromVault action.
- **Config options:** Set Data Selection = New. Requires the input DataSet to be an Append-type DataSet (not Replace).
- **Gotchas:** Only works on Append DataSets; not for Replace. If the source undergoes a Replace, the next run pulls all Replace batches plus any appended since — combined with an appending output this can duplicate rows. Upsert DataSets do NOT support version filtering at all (exported whole). If the source did a Replace, 'New' effectively loads everything from that Replace forward.
- **Sources:** https://www.domo.com/docs/s/article/000005150, https://domo-support.domo.com/minasan/s/article/000005150, https://community-forums.domo.com/main/discussion/68466

#### Data Selection: Filter by batch
*Category: Input data selection*

- **What it does:** Loads a specified subset of batches based on their processing/creation date or, for partitioned DataSets, their partition name — filtering on batch METADATA, not on the row data itself.
- **When to use:** Load a rolling window (e.g. 'Data is in Last 5 Days') or target specific partitions by name; sophisticated date-range logic that shifts with the current calendar date.
- **API / JSON representation:** Encoded via versionWindow / batch-filter settings on the LoadFromVault action (metadata predicate).
- **Config options:** Choose 'Filter by batch', then in the 'Import data when' dropdown pick 'Data processed' (by processing date) or a custom expression; for partitions, filter by partition name. Complete the 'Filter By Batch' section with the date/expression.
- **Gotchas:** Filter operates on batch metadata (which files/partitions), not on individual row values — do not confuse with the Filter Rows tile. Requires the DataSet to be stored as batch files; not available for whole-export (Upsert/View) DataSets.
- **Sources:** https://www.domo.com/docs/s/article/000005150

#### Partition column exposure on input (visiblePartitionColumn)
*Category: Input data selection*

- **What it does:** Surfaces a partitioned input DataSet's partition identifier as a usable column inside the flow, and enables partition-name-based batch filtering.
- **When to use:** When the input is a partitioned DataSet and you need the partition key available as data or as a Filter-by-batch predicate.
- **API / JSON representation:** visiblePartitionColumn field on the LoadFromVault action (null when not exposed, else the column name).
- **Config options:** Set the Partition Column Name in the input tile editor.
- **Gotchas:** Only meaningful for partitioned source DataSets.
- **Sources:** https://community-forums.domo.com/main/discussion/58617, https://www.domo.com/docs/s/article/360045402273

### Execution / scheduling

#### Trigger: run when input DataSet updates (executeFlowWhenUpdated)
*Category: Execution / scheduling*

- **What it does:** Marks specific input DataSets so the DataFlow auto-runs whenever those DataSets are updated. This is the most common automatic-run mode.
- **When to use:** Chain a DataFlow to fire as soon as its upstream source refreshes.
- **API / JSON representation:** Per-input boolean executeFlowWhenUpdated on each LoadFromVault action (true = this input triggers the flow). Multiple inputs can each be flagged.
- **Config options:** Enabled per input tile (or via the Settings-tab trigger). In the modern Settings tab this is expressed as a 'When DataSets update' trigger listing the triggering DataSets.
- **Gotchas:** With multiple triggering inputs and no conditions, the flow starts as soon as ANY selected DataSet updates — it can fire off the smallest/fastest input before a larger input finishes, missing that run's data. A DataFlow will NOT run if the triggering DataSet's data did not actually change ('no change in data' skip). Use the 'DataSets have updated' condition to require ALL specified DataSets before running.
- **Sources:** https://www.domo.com/docs/s/article/000005216, https://community-forums.domo.com/main/discussion/46346, https://dojo.domo.com/main/discussion/40423/magic-etl-dataflow-not-running-because-of-no-change-in-data

#### Advanced DataFlow Triggering (Settings tab triggers/schedule/conditions)
*Category: Execution / scheduling*

- **What it does:** The Settings tab of a DataFlow lets you add one or more named Triggers that start the flow. Trigger types: 'When DataSets update' and 'On a schedule'. Triggers can carry Conditions evaluated before the flow starts.
- **When to use:** Time-based runs ('On a schedule' with Open Schedule Details), or update-driven runs that should only proceed when extra conditions are met (e.g. all inputs updated).
- **API / JSON representation:** Trigger/schedule/condition config lives on the DataFlow container object (separate from the tile actions array). Condition option: 'DataSets have updated'.
- **Config options:** Settings > + Add Trigger > Edit title > choose type. 'When DataSets update' → select DataSets. 'On a schedule' → Open Schedule Details to set the cadence. + Add Condition → e.g. 'DataSets have updated' (one or many); multiple conditions supported.
- **Gotchas:** 'When DataSets update' with no conditions runs immediately after ANY selected DataSet updates; to require all, add the 'DataSets have updated' condition. A pure schedule trigger without conditions runs on the schedule regardless of data changes (subject to the no-data-change skip for update triggers).
- **Sources:** https://www.domo.com/docs/s/article/000005216, https://www.domo.com/docs/s/article/360055259234

#### Manual run (default) + Save / Save and Run
*Category: Execution / scheduling*

- **What it does:** By default a DataFlow has no trigger and must be run manually. Saving offers 'Save' (definition only) or 'Save and Run' (executes and produces/updates the output DataSet), with an optional version description.
- **When to use:** Default for new flows; also for ad-hoc reruns. 'Save' without running is used in archive/scheduling tricks so the flow only fires when its trigger DataSet later updates.
- **API / JSON representation:** Absence of triggers on the DataFlow container = manual schedule. Run = execution request against the dataflow id via API/CLI.
- **Config options:** Orange down-arrow → Save vs Save and Run; enter version description; add triggers at save time.
- **Gotchas:** If you Save and Run on an append/archive flow prematurely it may immediately append/archive data you did not intend. Output shows 'no update' when data is unchanged even on a successful run.
- **Sources:** https://www.domo.com/docs/s/article/360055259234, https://knowledge.domo.com/Prepare/DataFlow_Tips_and_Tricks/Archiving_Historical_Data_Using_a_DataFlow

### Execution behavior

#### Auto Append Processing (execution optimization)
*Category: Execution behavior*

- **What it does:** A v2/Adrenaline performance feature: at each run the system checks inputs/outputs and, when appending only new input rows would yield identical output to a full reprocess, it processes just the new rows and appends them — dramatically cutting runtime.
- **When to use:** Automatic; benefits large append-based pipelines. No explicit toggle — it applies when the flow's shape qualifies.
- **API / JSON representation:** Engine-side optimization keyed off input version state and action graph; not a user field.
- **Config options:** None directly; you influence it by which tiles you use and by input Data Selection.
- **Gotchas:** DISABLED by: NOW()/TODAY()/CURDATE()/'Current Date and Time'; aggregation tiles Group By, Rank & Window, Remove Duplicates, Pivot (Uncollapse Columns); Python/R Scripting tiles (disable it entirely); Joins unless one side appends and the static side is not the outer side; Unions unless ALL inputs receive appended data (a wholly replaced input disqualifies it).
- **Sources:** https://www.domo.com/docs/s/article/360051062653, https://www.domo.com/docs/s/article/360047787514

### Write/versioning internals

#### DataSet versioning / batch model ('Onboard' behavior)
*Category: Write/versioning internals*

- **What it does:** Determines how written data is physically stored and re-exposed. Replace and Append DataSets are stored as a list of the originally uploaded files/batches (usually CSV). Version/batch filtering works by selecting a subset of those files to load. Upsert DataSets (and DataSet Views) are exported from a database in their entirety.
- **When to use:** Understand this when building incremental inputs or when a downstream flow needs 'Only new rows' — the storage model dictates whether version filtering is even possible.
- **API / JSON representation:** Underlying onboarding uses Domo's Stream/batch model (replace vs append execution). Input action carries recentVersionCutoffMs and versionWindow to pick versions.
- **Config options:** Not user-configured on the store itself; controlled via output Update Method + input Data Selection.
- **Gotchas:** Because Upsert/View DataSets export whole tables, the export contains no per-upload lineage, so 'which rows came from which batch' is unknown → no version filtering. Output DataSet name for standard-synced/AppDB-backed DataSets is Domo-managed and may be locked.
- **Sources:** https://community-forums.domo.com/main/discussion/68466, https://www.domo.com/docs/s/article/000005150

### Engine / versions

#### Magic ETL 1.0 (engine ETL) vs 2.0 (engine MAGIC / Adrenaline)
*Category: Engine / versions*

- **What it does:** Two generations of the Magic ETL engine. Legacy v1 reloads all input data on every run; v2 runs on Domo's upgraded (Adrenaline-class) engine, ~2–4x faster, adds Auto Append Processing, 200+ functions, better error/null/type handling, timezone-aware global transform settings, and new tiles.
- **When to use:** Author new flows in v2. Migrating a v1 flow requires per-DataFlow upgrade and awareness of behavior changes.
- **API / JSON representation:** DataFlow container carries an engine/type discriminator; the task specifies v1 engine string "ETL" and v2 engine string "MAGIC". DataFlow definition JSON = contentType "domo/dataflow-actions" with a data[] array of action nodes (DAG). Distinct from MySQL DataFlows ("MYSQL") and Redshift.
- **Config options:** Upgrade to Magic ETL v2 per DataFlow; v2 exposes input column-type/error/null handling and output Partition/Upsert methods that v1 lacked.
- **Gotchas:** Behavior changes when moving v1→v2: null comparisons in Filter Rows now return null/false (e.g. col <> 5 also drops null rows) → can silently drop rows; Append Rows now merges same-named columns of differing type (incompatible→text, compatible→promoted) instead of renaming; Join name conflicts require user resolution; date ops default to company timezone (was UTC); WEEK_OF_YEAR redefined; stricter date parsing. Test outputs after upgrading.
- **Sources:** https://www.domo.com/blog/the-new-magic-etl-faster-smarter-and-easier-etl-for-all, https://www.domo.com/docs/s/article/360047787514, https://www.domo.com/docs/s/article/4408794063639, https://community-forums.domo.com/main/discussion/52496

#### DataFlow JSON container + programmatic authoring (CLI/API)
*Category: Engine / versions*

- **What it does:** A Magic ETL DataFlow is a JSON document describing a DAG of action nodes (inputs, transforms, outputs). Nodes reference each other via id and dependsOn[]. The clipboard/export format is {"contentType":"domo/dataflow-actions","data":[ ...actions ]}. Can be created, fetched, updated, and executed programmatically.
- **When to use:** Programmatic authoring: build the actions array (LoadFromVault inputs → transform actions → PublishToVault outputs), set dataSourceId on inputs and output name/method on outputs, then create/run the dataflow.
- **API / JSON representation:** Each action: {name, id(uuid), type, gui{x,y,color}, dependsOn:[upstreamIds], removeByDefault, notes:[], ...type-specific fields}. Input=LoadFromVault, Output=PublishToVault. Domo Java/community CLI supports list/get/create/update/run of dataflows using this JSON; container object holds triggers/schedule + engine type.
- **Config options:** Assemble the DAG in JSON; wire dependsOn to connect tiles; the Domo CLI list-dataflow/get exports the full JSON for inspection or cloning; create supplies a complete JSON body.
- **Gotchas:** There is no fully documented PUBLIC REST endpoint for creating Magic ETL flows — authoring goes through the internal dataprocessing dataflow API / the Domo CLI. ids must be internally consistent (dependsOn must reference existing node ids). gui coordinates are required for a sane canvas layout.
- **Sources:** https://community-forums.domo.com/main/discussion/52496, https://skills.rest/skill/magic-etl-cli, https://stackoverflow.com/questions/77917850/extract-domo-magic-etl-metadata-for-sql-migration

### Constraints

#### DataFlow-level constraints (columns, decimals, PDP, naming)
*Category: Constraints*

- **What it does:** Cross-cutting limits that affect input/output tile design.
- **When to use:** Design-time validation before authoring.
- **API / JSON representation:** Enforced by engine, not individual fields.
- **Config options:** N/A.
- **Gotchas:** Max 1,500 columns per Magic ETL DataFlow. Fixed-decimal precision/scale = (19,5) (5 decimals max). Apply PDP to OUTPUT DataSets, not inputs (historic rule; newer versions add in-ETL PDP support). Unlike MySQL DataFlows, Magic ETL is NOT bound by the 64-char DataSet/column name limit. Every DataFlow needs ≥1 input and ≥1 output; Magic errors if an input isn't incorporated into a transform.
- **Sources:** https://www.domo.com/docs/s/article/360045402273, https://www.domo.com/docs/s/article/360055259234, https://knowledge.domo.com/Prepare/Magic_Transforms/SQL_DataFlows/01Creating_an_SQL_DataFlow

**Open questions / not fully verified:**

- Exact PublishToVault field NAMES for update method / upsert key / partition column were not directly captured — the forum JSON dump was truncated right after the PublishToVault gui block. Names like partitionIdColumns / upsertKeyColumnNames / a method enum are inferred from the UI, not verified from raw JSON.
- The precise DataFlow-container discriminator for engine version (task-supplied 'ETL' for v1 vs 'MAGIC' for v2) was not independently confirmed in official docs; corroborated only indirectly via Adrenaline references and the clipboard contentType 'domo/dataflow-actions'.
- No official PUBLIC REST endpoint for creating Magic ETL dataflows is documented; programmatic creation appears to rely on the internal /dataprocessing dataflow API or the Domo CLI — the exact request path/verb was not located in official developer docs.
- Whether the 3,000-partition ceiling and (19,5) decimal precision differ on cloud pushdown (Snowflake/Databricks/BigQuery) engines was not confirmed.
- The full set of conditions under which the 'run when DataSet updates' trigger's no-data-change skip fires (and how it interacts with schedule-only triggers) is only partially documented.

## Combine & reshape tiles

### json-format

#### DataFlow JSON envelope (how tiles are represented)
*Category: json-format*

- **What it does:** Magic ETL tiles serialize as a JSON document {"contentType":"domo/dataflow-actions","data":[ ...actions ]}. Each tile is one object in the data[] array. Universal per-action keys: name (tile display name), id (UUID the author must generate), type (the action-type string that selects the tile behavior), gui{x,y,color,colorSource} (canvas position/color), dependsOn[] (array of upstream action ids wiring the graph — this is how tiles connect, not visual edges), removeByDefault (bool), notes[] (tile annotations). The whole document can be copied from the editor to clipboard and pasted back, so authoring = emitting this JSON.
- **When to use:** This is the top-level structure an authoring AI produces for the whole ETL. Build the graph by giving every tile a unique id and listing its parent tile id(s) in dependsOn.
- **API / JSON representation:** Root: {contentType:"domo/dataflow-actions", data:[{name,id,type,gui:{x,y,color,colorSource},dependsOn:[...],removeByDefault,notes:[...], ...type-specific fields}]}. Order in data[] is not significant; wiring is by dependsOn ids.
- **Config options:** gui.x/gui.y in pixels (grid snaps to 12px, optionally 32px). color is an integer RGB.
- **Gotchas:** Tile ids are UUIDs that the backend must accept; community consensus is that fully programmatic generation is fragile because of id/GUID assignment and version validation — copy/paste of an edited JSON export is the reliable path. dependsOn wiring, not array order, defines execution.
- **Sources:** https://community-forums.domo.com/main/discussion/52496/recursive-issue-help-new-magic-etl-2-0, https://community-forums.domo.com/main/discussion/54298/magic-etl-copy-paste-json-definition-to-clipboard, https://community-forums.domo.com/main/discussion/52491/dataflow-transform-i-e-action-types-in-api-json-data

#### Adjacent confirmed action types (context for wiring)
*Category: json-format*

- **What it does:** Reference of other confirmed type strings an authoring AI will emit around combine/reshape tiles: Input DataSet, Output DataSet, Filter, Add Formula, and SQL/Table transforms.
- **When to use:** Needed to build a complete, runnable graph (inputs feed combine tiles; outputs publish results).
- **API / JSON representation:** Confirmed: type:"LoadFromVault" (Input DataSet — fields dataSourceId, executeFlowWhenUpdated, onlyLoadNewVersions, recentVersionCutoffMs, columnSettings). type:"PublishToVault" (Output DataSet — fields dataSource:{guid,type,name}, versionChainType e.g. "REPLACE", plus partitionIdColumns[], upsertColumns[], retainPartitionExpression for Upsert/partition). type:"Filter" (filterList[] of {leftField, rightValue:{value,type} or rightExpr, operator e.g. "NE","NL", andFilterList[]}). type:"ExpressionEvaluator" (Add Formula — expressions[] of {fieldName, expression, settings}). For SQL DataFlows / SQL tile: types "GenerateTableAction" (SELECT→CREATE TABLE AS), "SQL"/"SqlAction" (arbitrary DML/DDL).
- **Config options:** PublishToVault versionChainType selects Replace vs Append/Upsert semantics; upsertColumns enables the Upsert output option.
- **Gotchas:** A GUI 'Table' transform can serialize as type "SQL" in exports — GUI label and JSON type do not map 1:1 for SQL-family actions.
- **Sources:** https://community-forums.domo.com/main/discussion/52496/recursive-issue-help-new-magic-etl-2-0, https://community-forums.domo.com/main/discussion/58617/need-help-subtract-currentrowdatetime-previousrowdatetime-from-same-column, https://community-forums.domo.com/main/discussion/52491/dataflow-transform-i-e-action-types-in-api-json-data, https://www.domo.com/product/new-features/magic-etl-enhancements

### combine

#### Join Data (Merge Join)
*Category: combine*

- **What it does:** Combines columns from two input streams into one, matching on common key column(s). Supported join types: Inner, Left Outer, Right Outer, Full Outer. Also supports expression-based (freeform) join conditions using inequality operators (<, >, >=, <=) and range keywords (BETWEEN) in addition to simple equality on column pairs. Optional cardinality constraint validation (Many to Many, Many to One, One to Many, One to One) that errors the DataFlow if violated.
- **When to use:** Whenever you need to enrich/look up columns from a second dataset by key. Use expression joins for non-equi joins (date ranges, greater-than). Put the smaller/aggregated table on the lookup (non-outer) side to keep auto-optimization.
- **API / JSON representation:** type:"MergeJoin". Fields (confirmed from export): joinType (string, e.g. "LEFT OUTER", "INNER", "RIGHT OUTER", "FULL OUTER"), step1 & step2 (the two upstream action ids for left/right inputs), keys1[] & keys2[] (arrays of join-key column names, index-aligned across the two sides for multi-column joins), schemaModification1[] & schemaModification2[] (per-side output column control: array of {name, rename, remove} to rename/drop columns and resolve name collisions), partitioningInputId ("" when unused). dependsOn lists both input ids.
- **Config options:** Match Another Column adds paired keys (append to keys1/keys2). Rename collisions via schemaModification entries (e.g. rename:"Select ID Column.id"). Cardinality/constraint validation optional.
- **Gotchas:** Join key matching is CASE-SENSITIVE (long-standing limitation; no case-insensitive checkbox). Hard limit: a single join key value may not have more than 10,000 duplicates on a side — exceeding it fails with error 'MergeJoin: Duplicate key limit in left/right table exceeded!'. Join columns must have the same data type/structure on both sides. Join Data is a heavier tile (slower execution).
- **Sources:** https://www.domo.com/docs/s/article/360044876194, https://community-forums.domo.com/main/discussion/52496/recursive-issue-help-new-magic-etl-2-0, https://community-forums.domo.com/main/discussion/58617/need-help-subtract-currentrowdatetime-previousrowdatetime-from-same-column, https://community-forums.domo.com/main/discussion/4969/duplicate-key-limit-error-in-magic-etl, https://community-forums.domo.com/main/discussion/67368/magic-etl-join-tile

#### Split Join
*Category: combine*

- **What it does:** An expanded join tile that outputs BOTH matched and unmatched records as separate named output nodes in a single tile. Selectable outputs include Inner join (matches), Left Only / Right Only (unmatched rows from each side), and Left anti-join / Right anti-join. Configure join keys and column handling exactly like the regular Join Data tile; each enabled output becomes its own downstream node.
- **When to use:** Join auditing / reconciliation: find rows present in A but not B (missing records), or split matched vs unmatched in one pass instead of building separate joins + filters. Anti-join for 'records with no match'.
- **API / JSON representation:** Located under Combine Data. Action-type string not confirmed in a public JSON export; behaves as a multi-output MergeJoin variant. Same join-key / schemaModification concepts as MergeJoin, plus per-output enable flags and output names.
- **Config options:** Under 'Output names', check which outputs to emit (Inner, Left Only, Right Only, Left Anti, Right Anti) and optionally rename each. Tile expands horizontally per enabled output; unused outputs can be hidden.
- **Gotchas:** Same-result alternative to a Join+Filter. Newer tile; the standalone 'Anti-join' type returns rows from one table with no match in the other. Canvas gets wide as outputs are enabled.
- **Sources:** https://www.domo.com/docs/s/article/000005919

#### Append Rows (Stack)
*Category: combine*

- **What it does:** Stacks rows from two or more input datasets/streams (UNION) into one dataset by matching COLUMN NAMES (not positions). Returns all rows including duplicates. Column-inclusion modes: 'Include all columns', 'Include columns from [a chosen DataSet]', or 'Only include shared columns'. Type-mismatch handling: 'Use best compatible data type' or 'Display a type error' (mismatched types can otherwise be split into two columns).
- **When to use:** Combine like-structured datasets (e.g., monthly files, multiple regions) into one. Core building block of recursive/snapshot DataFlows (append new data onto historical output).
- **API / JSON representation:** type:"UnionAll" (confirmed from export). Fields: unionType (string, e.g. "INCLUDE_MATCHES"), strict (bool). dependsOn lists all input action ids being appended.
- **Config options:** unionType controls which columns survive (all vs shared/matched). strict toggles type-error vs best-compatible-type behavior. Appends align by column name — mismatched names create separate columns.
- **Gotchas:** Magic ETL appends work off COLUMN NAMES, not column order — a name mismatch silently produces extra columns rather than stacking. Preview may not preserve row order (ordering is a card/display concern). Input datasets should share structure and data types.
- **Sources:** https://www.domo.com/docs/s/article/360044876194, https://community-forums.domo.com/main/discussion/52496/recursive-issue-help-new-magic-etl-2-0, https://community-forums.domo.com/main/discussion/67919/how-to-join-two-group-by-without-matching-pair-column

#### Split Filter
*Category: combine*

- **What it does:** Splits one input stream into multiple named output nodes by FORMULA conditions (each formula = one output stream), with an optional 'Else' output capturing all unmatched rows. Sibling to Split Join under the multi-output tile family.
- **When to use:** Route one dataset into several downstream branches by rule in a single tile (e.g., region A / region B / everything else) instead of many separate Filter tiles.
- **API / JSON representation:** Located under Filter. Action-type string not captured in a public export. Config: ordered list of formula filters (each names an output) + optional Else output name.
- **Config options:** Formula filters only (no simple filter rules here). Optional Else. Each output is independently wired downstream.
- **Gotchas:** Only FORMULA filters are supported here, not point-and-click filter rules. Tile widens per output.
- **Sources:** https://www.domo.com/docs/s/article/000005919

#### Fixed Input (manual rows / 'Add Rows')
*Category: combine*

- **What it does:** Lets you create data directly on the canvas — manually enter/paste rows, upload a file, or (with AI Services) generate placeholder data — without a source DataSet. This is the closest tile to an 'Add Rows' action.
- **When to use:** Prototype/validate logic without a real input, seed lookup/mapping tables inline, or add a small static set of rows to append.
- **API / JSON representation:** Called 'Fixed Input' (under DataSets; evolved from the placeholder-data role of Query DataSet). Action-type string not captured in a public export.
- **Config options:** Manual grid entry, paste, or file upload; AI generation requires AI Services enabled.
- **Gotchas:** AI generation needs instance AI Services; otherwise manual/paste/upload only.
- **Sources:** https://www.domo.com/docs/s/article/360045402273

### aggregate

#### Group By (Aggregate)
*Category: aggregate*

- **What it does:** Aggregates rows into groups defined by one or more grouping columns, producing new aggregated columns. Full list of aggregation types: Count (non-null), Count including nulls, Count distinct, First non-null value, Last non-null value, First value (incl null), Last value (incl null), Sum, Average, Median, Minimum, Maximum, Standard deviation, Combine strings separated by ',' (GROUP_CONCAT), Combine distinct strings separated by ','. Also supports 'Add Formula' aggregate columns using SQL-style expressions (SUM/MEDIAN/PERCENTILE etc.) via the formula editor / AI SQL Assistant.
- **When to use:** Any roll-up: totals per category, distinct counts, first/last per group, concatenated lists. Use Group By (not Add Formula) whenever the operation is an aggregation. Place on the lookup side of a join to preserve join auto-optimization.
- **API / JSON representation:** Action-type string NOT confirmed in a public export (community docs call it the Group By tile). Confirmed detail: the aggregated columns live in a JSON array named "fields" (reorderable by editing that array). Data-type compatibility per aggregation: Sum/Average/Median/StdDev = Decimal/Whole Number only; Min/Max = Decimal/Whole Number/Date; Count variants + First/Last = all types; Combine strings = Text only.
- **Config options:** Select grouping column(s) or 'add all columns'; for each new column: name it, pick source column(s), pick aggregation type; optionally add a formula-based aggregate. GROUP_CONCAT supports DISTINCT and SEPARATOR clauses.
- **Gotchas:** Cannot aggregate the whole dataset without a grouping column — you must add a constant column to group on for a grand total, then drop it. GROUP_CONCAT does NOT support ORDER BY (tile fails if used). Heavier/slower tile; forces full-dataset load (blocks row-by-row auto-optimization) unless it's the lookup side of a join.
- **Sources:** https://www.domo.com/docs/s/article/360044876094, https://community-forums.domo.com/main/discussion/53581/magic-etl-allow-group-by-without-a-grouping-column, https://community-forums.domo.com/main/discussion/64534/add-order-by-to-group-concat-function-in-magic-etl-v2, https://www.domo.com/docs/s/article/360047787514, https://www.domo.com/docs/s/article/360051062653

#### Rank & Window
*Category: aggregate*

- **What it does:** Adds new columns computed by rank/window functions over an ordered, optionally partitioned set of rows. Three categories: (1) Ranking — Rank (ties share rank, gaps in sequence), Dense Rank (ties share rank, no gaps), Row Number (sequential, restarts per partition); (2) Framed — Sum/Average/Count over a window of N Preceding and N Following rows (running/rolling calcs); (3) Offset — Lag (value from N rows earlier) and Lead (value from N rows later).
- **When to use:** Running totals/moving averages (Framed), top-N per group (Rank/Row Number + Filter), previous/next-row comparisons like current-minus-previous (Lag/Lead), sequential numbering within groups.
- **API / JSON representation:** type:"WindowAction" (confirmed). Fields: partitionedAggregation (bool), additions[] = the functions, each {name (new column), operation:{type, operationType, column, amount}}, orderRules[] = [{column, caseSensitive, ascending(bool)}] (the ORDER BY), groupRules[] = [{column, caseSensitive}] (the PARTITION BY). Confirmed operation example: {type:"OFFSET", operationType:"LAG", column:"...", amount:"1"}. By category, operation.type is OFFSET for Lag/Lead (operationType LAG/LEAD, amount=offset); the Ranking category (Rank/Dense Rank/Row Number) and Framed category (Sum/Average/Count with Preceding/Following counts) use analogous operation objects (exact type/operationType strings for those two categories not captured in a public export).
- **Config options:** Per function: new column name, function type, source column, order column(s) + asc/desc, optional partition column(s). Framed adds Preceding & Following integer counts. Offset adds the offset amount.
- **Gotchas:** Row Number restarts at 1 in each partition (so derived row numbers won't match dataset row numbers). Offset/framed cells at partition edges come out blank/null where not enough rows exist. Ordering is set inside the tile (orderRules); don't rely on upstream sort. Heavier/slower tile; blocks auto-optimization.
- **Sources:** https://www.domo.com/docs/s/article/360044876094, https://community-forums.domo.com/main/discussion/58617/need-help-subtract-currentrowdatetime-previousrowdatetime-from-same-column, https://knowledge.domo.com/Prepare/Magic_Transforms/ETL_DataFlows/Magic_ETL_v2_Tiles:_Aggregate_(Beta)

### reshape

#### Pivot (a.k.a. Uncollapse Columns)
*Category: reshape*

- **What it does:** De-normalizes long→wide: turns a single key column with multiple rows into multiple columns in one row, using key-value pairs. You enumerate each output column: its header name, the key value that maps to it, and the value column that fills it. In current Magic ETL this tile is called 'Pivot'; in older/Edit-Columns docs the same behavior is 'Uncollapse Columns'.
- **When to use:** Cross-tab / matrix layouts: e.g., Product values A/B/C in one column become separate Product A / Product B / Product C columns keyed by Month.
- **API / JSON representation:** Called 'Pivot' (new) / 'Uncollapse Columns' (legacy). Public JSON export of the action-type string not captured; documented internally as the Pivot/Uncollapse action. Config concepts: key column (to spread into headers), grouping column (identifies each output row), and per-new-column {header name, matching key value, value column}.
- **Config options:** 1) key column to pivot into headers; 2) grouping column; 3) for each new column: header name + key value + value column (use the SAME value column for every added column).
- **Gotchas:** HARD LIMIT 1,500 columns — exceeding it errors and the DataFlow won't run. Not dynamic: you must manually enumerate every target column/value, so a new key value appearing in data requires editing the tile. Counts as an aggregation tile (blocks auto-optimization).
- **Sources:** https://www.domo.com/docs/s/article/360044951294, https://knowledge.domo.com/Prepare/Magic_Transforms/ETL_DataFlows/Magic_ETL_v2_Tiles:_Pivot_(Beta), https://www.domo.com/docs/s/article/360043427353, https://www.domo.com/docs/s/article/360051062653

#### Unpivot (a.k.a. Collapse Columns)
*Category: reshape*

- **What it does:** Normalizes wide→long: turns multiple columns in one row into a single key column + single value column across multiple rows. You define the new header-column name, the new value-column name, and for each source column: the column to normalize and the header value it maps to. Current name 'Unpivot'; legacy Edit-Columns name 'Collapse Columns'.
- **When to use:** Flatten spreadsheet-style data (Jan/Feb/Mar columns → a Month column + Value column) so it charts/aggregates cleanly.
- **API / JSON representation:** Called 'Unpivot' (new) / 'Collapse Columns' (legacy). Action-type string not captured in a public export. Config: new header column name, new value column name, and per-source-column {column to collapse, header value}.
- **Config options:** Add Column repeatedly, one per source column to fold in; each supplies its own header value literal.
- **Gotchas:** STATIC ONLY — only works when the number of columns stays the same; a newly added source column is NOT unpivoted automatically (use Dynamic Unpivot for that). You must list every column explicitly.
- **Sources:** https://www.domo.com/docs/s/article/360044951294, https://knowledge.domo.com/Prepare/Magic_Transforms/ETL_DataFlows/Magic_ETL_v2_Tiles:_Pivot_(Beta), https://www.domo.com/docs/s/article/360043427353

#### Dynamic Unpivot
*Category: reshape*

- **What it does:** Wide→long unpivot that ADAPTS to schema changes. Instead of listing columns to unpivot, you list the columns to KEEP static (not pivot); every other column — including new ones added later — is automatically unpivoted into the header/value column pair.
- **When to use:** When the set of columns to unpivot changes over time (e.g., a new month column added each period) and you don't want to re-edit the tile. Preferred over Unpivot for evolving schemas.
- **API / JSON representation:** Called 'Dynamic Unpivot'. Action-type string not captured in a public export. Config differs from Unpivot: step 1 = column(s) that should NOT be pivoted (kept + duplicated per output row); step 2 = new header column name; step 3 = new value column name.
- **Config options:** Step1: exclusion list (static columns). Step2/3: names for the generated key and value columns. Any column not excluded is auto-unpivoted on future runs.
- **Gotchas:** The exclusion approach is the inverse of Unpivot's inclusion approach — get the mental model right. New columns silently fold into the value column unless explicitly excluded (can surprise if an unrelated column is added upstream).
- **Sources:** https://www.domo.com/docs/s/article/360044951294, https://community-forums.domo.com/main/discussion/45348/how-do-i-transpose-pivot-dataflows-for-non-technical-users-to-any-columns-and-values

#### Split Column
*Category: reshape*

- **What it does:** Splits one text column into multiple columns by a delimiter (or regex). You choose how many output columns to create and name them; extra splits beyond the column count can be kept in the last column or discarded.
- **When to use:** Break 'a | b | c' style fields, full names, delimited codes, or CSV-in-a-cell into separate columns. Often paired with Group By + Combine strings to reshape rows into columns.
- **API / JSON representation:** type:"SplitColumnAction" (confirmed). Fields: sourceColumn (column to split), delimiterType (e.g. "CUSTOM"), delimiter (e.g. " | "), useRegex (bool), plus output column definitions/names and extra-split handling.
- **Config options:** delimiterType/delimiter (custom string or preset), useRegex flag, number + names of output columns, keep-vs-drop extra splits.
- **Gotchas:** If there are more delimited values than output columns AND you choose not to keep extras, those values are dropped entirely (not placed anywhere).
- **Sources:** https://community-forums.domo.com/main/discussion/44942/edit-string-in-beastmode-or-etl, https://www.domo.com/docs/s/article/360043427353

#### Remove Duplicates
*Category: reshape*

- **What it does:** Removes duplicate rows based on a chosen set of columns; a row is dropped only if ALL selected columns match another row. Per-column case-sensitivity toggle. (Adjacent to combine/reshape; commonly used after Append to dedupe.)
- **When to use:** Dedupe after appends/joins; keep unique rows by a business key. Core of recursive dedupe DataFlows.
- **API / JSON representation:** type:"Unique" (confirmed). Fields: partitionedAggregation (bool), fields[] = [{name (column), caseInsensitive (bool)}].
- **Config options:** Choose the columns that define uniqueness; set caseInsensitive per column. Newer UI adds a bulk column-add.
- **Gotchas:** Only exact all-selected-columns matches are removed — pick columns that truly identify a unique row or you keep dupes / lose data. Counts as an aggregation tile (blocks auto-optimization; slower).
- **Sources:** https://www.domo.com/docs/s/article/360044876614, https://community-forums.domo.com/main/discussion/58617/need-help-subtract-currentrowdatetime-previousrowdatetime-from-same-column, https://www.domo.com/docs/s/article/360051062653

#### Select Columns
*Category: reshape*

- **What it does:** Chooses which columns pass through and optionally renames them. Frequently the companion to joins/appends for pruning and disambiguating columns before/after combining.
- **When to use:** Trim to needed columns, rename for downstream clarity, resolve name collisions ahead of an Append (which matches by name).
- **API / JSON representation:** type:"SelectValues" (confirmed). Field: fields[] = [{name, rename}] (rename null = keep name).
- **Config options:** Per column: include + optional rename.
- **Gotchas:** Because Append matches by column name, use Select Columns to align names before appending.
- **Sources:** https://community-forums.domo.com/main/discussion/52496/recursive-issue-help-new-magic-etl-2-0

#### Add Constants
*Category: reshape*

- **What it does:** Adds a new column whose value is the same constant for every row. Column type selectable: Text, Decimal, Decimal Fixed, Whole Number, Date, Date and Time; value may be blank.
- **When to use:** Create a dummy grouping key so Group By can compute a grand total; tag rows with a source label before appending; seed a cross-join key.
- **API / JSON representation:** Called 'Add Constants' (legacy) / part of Edit Columns. Action-type string not captured in a public export. Config: column name, column type, constant value.
- **Config options:** name, type, value (blank allowed).
- **Gotchas:** The canonical workaround for 'Group By without a grouping column' (whole-dataset aggregate) is Add Constants → Group By on it → drop it.
- **Sources:** https://www.domo.com/docs/s/article/360043427353, https://community-forums.domo.com/main/discussion/53581/magic-etl-allow-group-by-without-a-grouping-column

#### Combine Columns
*Category: reshape*

- **What it does:** Concatenates values from multiple columns into one new column using a specified separator; option to remove the original columns.
- **When to use:** Build composite keys for joins/dedupe (concatenate the join columns), or merge first+last name into full name.
- **API / JSON representation:** Called 'Combine Columns' (Edit Columns). Action-type string not captured in a public export. Config: new column name, separator, columns to combine, remove-originals flag.
- **Config options:** new column name, separator char, selected columns, remove-originals toggle.
- **Gotchas:** Row-by-row concatenation only (not an aggregation across rows — use Group By 'Combine strings' for that).
- **Sources:** https://www.domo.com/docs/s/article/360043427353

#### JSON Expander ('Expand')
*Category: reshape*

- **What it does:** Visually explores a JSON/nested/array text column and expands it into clean flat columns (and rows for arrays) without custom parsing. This is the tile behind 'Expand' for nested structures.
- **When to use:** Flatten API/JSON payload columns, nested objects, or arrays into tabular columns/rows.
- **API / JSON representation:** Called 'JSON Expander' tile. Action-type string not captured in a public export.
- **Config options:** Point at the JSON column; pick nodes/paths to expand into columns; arrays expand into rows.
- **Gotchas:** Newer tile; availability may vary by instance/version.
- **Sources:** https://community-forums.domo.com/main/discussion/70709/tip-of-the-week-30-json-expander-tile-for-working-with-json-data

**Open questions / not fully verified:**

- Exact JSON action-type strings for Group By, Pivot/Uncollapse Columns, Unpivot/Collapse Columns, Dynamic Unpivot, Add Constants, and Combine Columns were not found in any public JSON export — only the tiles' behavior and config fields are documented. (Group By's aggregate array is confirmed to be named 'fields'.) These likely follow the same 'XxxAction' or bare-name convention (e.g. plausibly a Pivot/Unpivot/GroupBy action) but should be verified by exporting a real DataFlow that contains them via copy-to-clipboard or the Domo CLI 'list-dataflow' command.
- For Rank & Window, only the OFFSET/LAG operation object was confirmed from an export ({type:'OFFSET',operationType:'LAG',column,amount}). The exact operation.type/operationType strings for the Ranking category (Rank, Dense Rank, Row Number) and Framed category (Sum, Average, Count with Preceding/Following counts) were not captured and should be confirmed from a real export.
- Split Join and Split Filter action-type strings and their multi-output JSON shape (how each named output node is represented) were not found in a public export.
- Whether the 10,000 duplicate-key join limit and the 1,500-column pivot limit are configurable or subscription/environment-dependent was not determined (they appear as hard platform limits).

## Column operations & formulas

### authoring-contract

#### Common action/tile JSON envelope (authoring contract)
*Category: authoring-contract*

- **What it does:** Every Magic ETL tile is one object in the dataflow's top-level `actions[]` array (a DAG node). The dataflow itself is PUT/POST to /api/dataprocessing/v1/dataflows as {name, databaseType:'MAGIC', responsibleUserId, draft, enabled, engineProperties:{'kettle.mode':'STRICT'}, inputs:[], outputs:[], actions:[...], gui:{}}. Each transform action shares a base shape.
- **When to use:** Read this before authoring ANY column/row tile below — the per-tile schemas only list the fields unique to that tile; these base fields are required on all of them.
- **API / JSON representation:** Base fields on a transform action: `type` (action-type string, e.g. 'SelectValues'), `id` (unique string within the flow), `name` (display label), `dependsOn:[<id-of-upstream-action>]` (wiring; single-input transforms link one parent), `gui:{x,y,color,colorSource,sampleJson}`. Non-input, non-output transforms also carry `disabled:false, removeByDefault:false, notes:[], previewRowLimit:null`. Many single-input transforms additionally take `input:<upstream-id>` in the body. Actions reference upstream columns by exact column name (backticked in formula/SQL contexts). Clipboard/copy envelope for a subgraph is {'contentType':'domo/dataflow-actions','data':[...actions...]}. Workflow: GET full dataflow object -> mutate actions[] -> PUT full object -> POST .../executions to run -> GET .../executions?limit=1 to verify.
- **Config options:** N/A (structural)
- **Gotchas:** STRICT engine mode rejects many partial/misconfigured actions with DP-0003 (misconfigured action) or DP-0069 (invalid/unknown action type). The `tables` field on actions is volatile/regenerated — re-PUTting a canonical definition just to run it makes Domo treat all tiles as changed; trigger a data-only refresh with an empty-body POST to .../executions instead. Exact `type` strings are case-sensitive. When unsure of a tile's exact `type` or field schema, build it once in the web UI, GET the dataflow, and read the action back — this is the reliable ground-truth for newer tiles.
- **Sources:** https://skills.rest/skill/magic-etl-cli, https://www.domo.com/docs/s/article/000006036, ../skills/domo-magic-etl.md, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl-cli/SKILL.md

### select-reorder

#### Select Columns (keep + reorder subset)
*Category: select-reorder*

- **What it does:** Keeps only the columns you list and drops all others; the order you list them can set output column order. Doubles as the Rename and Remove-Columns tile.
- **When to use:** Prune a wide dataset to the columns you need before an output/join; reorder columns; rename in the same step. Place before a PublishToVault output to control final schema.
- **API / JSON representation:** `type:'SelectValues'`. Body carries the kept-column list as `fields:[{name:'<orig>', rename:'<newname-or-null>'}]` (some flows use the key `select:[{name,rename}]` — both observed in real dumps). Only listed columns survive; omit `rename` (or set null) to keep the original name. Do NOT add `remove:true`, `type`, `dateFormat`, or a `settings` block to the entries -> triggers DP-0003.
- **Config options:** Pick columns to keep (checkbox list); optional new name per kept column; drag to reorder.
- **Gotchas:** Column REORDER via Select Columns is unreliable at the output — users report the Output Dataset does not honor the listed order (Domo may re-sort schema); do not depend on it for downstream column position. CONTRADICTION TO VERIFY: one community CLI skill flags `SelectValues` as returning DP-0069 (invalid action type) for brand-new flows authored via API, yet real GET dumps of existing flows show `SelectValues` with `fields:[{name,rename}]` working — likely graph-version/instance dependent; if DP-0069 occurs on create, build the tile in UI and read back the exact type.
- **Sources:** https://community-forums.domo.com/main/discussion/53089/using-select-columns-to-reorder-columns-in-magic-etl, https://www.domo.com/docs/s/article/360044876874, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl-cli/SKILL.md

#### Remove Columns
*Category: select-reorder*

- **What it does:** Drops columns from the schema.
- **When to use:** Remove PII/unused columns before output; slim intermediate steps.
- **API / JSON representation:** Two paths: (1) via Select Columns — simply OMIT the unwanted columns from the `SelectValues.fields[]` keep-list (everything not listed is dropped). (2) via the Alter Columns tile (`type:'Metadata'`) which supports a per-column remove flag, or via join `schemaModification` entries with `remove:true`. There is no standalone 'RemoveColumns' action type; do not fabricate one.
- **Config options:** Select columns to remove.
- **Gotchas:** Do not add `remove:true` to a `SelectValues` entry (DP-0003) — with SelectValues, removal = omission from the keep-list, not a remove flag. A dedicated remove flag only belongs to Metadata/schemaModification structures.
- **Sources:** https://www.domo.com/docs/s/article/360044876874, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### rename

#### Rename Columns
*Category: rename*

- **What it does:** Changes one or more column names without altering values or types.
- **When to use:** Normalize names for downstream joins/outputs, or make names human-readable. Renaming is HIGH-RISK: downstream Beast Modes, ETL tiles, AutoML, dashboards depend on names.
- **API / JSON representation:** Most commonly done through the Select Columns tile: `type:'SelectValues'`, `fields:[{name:'Old',rename:'New'}]`. Rename can also happen implicitly in other tiles: MergeJoin `schemaModification1/2:[{name,rename,remove}]`, and ExpressionEvaluator can 'rename' by writing a new fieldName. A dedicated `RenameColumns` type is referenced by one CLI skill but flagged there as unsupported/DP-0069 for new flows — prefer SelectValues.rename as the portable path.
- **Config options:** Old name -> new name pairs.
- **Gotchas:** There is no separate first-class Rename tile in the JSON in practice — it is a facet of SelectValues (and join/formula tiles). Renaming inside a formula same-fieldName replaces the source column. Track renames because they silently break downstream references.
- **Sources:** https://www.domo.com/docs/s/article/360044876874, ../skills/domo-magic-etl.md, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl-cli/SKILL.md

### type-cast

#### Alter Columns / Change Data Type (Set Column Type)
*Category: type-cast*

- **What it does:** Changes a column's data type (e.g. STRING -> LONG/DECIMAL/DOUBLE/DATE/DATETIME), and can adjust column metadata such as name and date parse format.
- **When to use:** Cast text to numeric/date before math or date filtering; fix connector-inferred types; set an explicit parse format for date strings.
- **API / JSON representation:** `type:'Metadata'` (the Alter Columns tile). It carries a per-column list describing target type / rename / remove / date-format for each column being altered (exact key name of the list was not captured verbatim from a dump — build once in UI and read back to confirm the entry keys). Type-name tokens seen elsewhere in Domo action JSON: STRING, LONG, DOUBLE, DECIMAL, DATE, DATETIME.
- **Config options:** Per column: target type (Text/String, Integer/Long, Decimal/Double, Date, DateTime); for dates, a parse/format pattern; optional rename; optional remove.
- **Gotchas:** Casting text->number/date fails silently to NULL for unparseable values. For date strings, you often MUST supply the format pattern (Java/MySQL-style, e.g. yyyy-MM-dd) or the cast yields null. Prefer explicit casting early — Magic v2 formula math on string columns can behave unexpectedly. Exact JSON entry-field names for Metadata were not confirmed from a raw dump; verify via read-back before relying on them in generated JSON.
- **Sources:** https://www.domo.com/docs/s/article/360043427373, https://jaewilson07.github.io/domolibrary/blog/posts/20231118%20_creatingDomoStats_MagicETL/index_v2_with_history.html, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### constant

#### Add Constants (Add Column with fixed value)
*Category: constant*

- **What it does:** Adds one or more new columns whose value is a fixed constant on every row.
- **When to use:** Tag rows with a source/label, add a fixed flag or version, or seed a column later overwritten by a formula.
- **API / JSON representation:** `type:'Constant'` (confirmed via domolibrary DomoStats generator output). Carries the new column name, its type, and the constant value. A related `FixedInput` type also appears in the known-types list (used to inject a small fixed/literal input); for a single constant column the Constant tile is the target. Field-key detail not captured verbatim — read back from UI to confirm.
- **Config options:** New column name; column type (Text/Number/Decimal/Date); the constant value.
- **Gotchas:** Constant-added columns get a type; a numeric constant added as text will not do math without an Alter Columns cast. If you only need a computed literal referenced later, an ExpressionEvaluator expression (e.g. `'US'` or `1`) is often simpler than a Constant tile.
- **Sources:** https://jaewilson07.github.io/domolibrary/blog/posts/20231118%20_creatingDomoStats_MagicETL/index_v2_with_history.html, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

#### Set Column Value
*Category: constant*

- **What it does:** Overwrites all values in an existing column with a fixed value or with another column's value (v1 Magic ETL 'Edit Data' tile family). In Magic ETL v2 there is no dedicated 'Set a value' tile.
- **When to use:** Blank out / standardize a column, or copy one column's values into another.
- **API / JSON representation:** v1: part of the legacy 'Edit Data' tile group (older Magic ETL). v2 EQUIVALENT (recommended for API authoring): use `type:'ExpressionEvaluator'` with an entry whose `fieldName` is the EXISTING column name and whose `expression` is the constant/other-column — writing to an existing fieldName replaces that column's values on every row. For a brand-new fixed column use the Constant tile instead.
- **Config options:** (v1 Edit Data) target column; value = constant or another column.
- **Gotchas:** Do not look for a standalone 'SetColumnValue' action type in v2 JSON — it maps to ExpressionEvaluator overwrite. Overwriting a column changes its downstream meaning; treat like a rename for dependency risk.
- **Sources:** https://www.domo.com/docs/s/article/360043427373, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### formula

#### Add Formula (Formula tile — row-level expression evaluator)
*Category: formula*

- **What it does:** Creates or replaces columns using row-by-row expressions in Domo's MySQL-flavored (Adrenaline-engine) formula language. Supports 200+ functions (string/numeric/date/logical/aggregate). This is the Magic ETL analog of Beast Mode, but with more power.
- **When to use:** Any computed/derived column: conditionals (CASE/IF), string manipulation, math, date derivation, null coalescing. Preferred over the SQL tile for portable per-row logic. Also used to emulate 'Set Column Value' (write same fieldName).
- **API / JSON representation:** `type:'ExpressionEvaluator'`. Body: `expressions:[{expression:'<expr>', fieldName:'<outputCol>', settings:null}]`. Reference existing columns with BACKTICKS: e.g. {expression:'LAST_DAY(`Date`)', fieldName:'Month', settings:null}. Multiple entries in `expressions[]` evaluate top-to-bottom and LATER expressions can reference columns created by EARLIER ones in the same tile. Writing an existing column name as `fieldName` REPLACES that column (this is how you overwrite/'set' a column's values). CASE WHEN...THEN...ELSE...END and IF(cond,a,b) both work.
- **Config options:** Per formula: the expression text, the output column name, whether it is a new column or overwrites an existing one. Multiple formulas can be chained inside one tile.
- **Gotchas:** IFNULL takes exactly 2 args; use COALESCE for N args. A bad expression -> DP-0059 (formula error) or DP-0118 (code crash). Division by zero / bad casts -> VALIDATION-DIV / VALIDATION-DE. The Formula Editor is NOT identical to Analyzer's calculated-field editor — some Formula-tile functions do not work in a card Beast Mode (DataFlow has more processing capacity), and vice-versa. GROUP_CONCAT here does NOT support ORDER BY or DISTINCT inside the expression (Magic ETL v2 limitation). TRUNC_MONTH is not a function (use DATE_TRUNC / TRUNCATE appropriately).
- **Sources:** https://www.domo.com/docs/s/article/360044258533, https://www.domo.com/docs/s/article/360044289573, https://community-forums.domo.com/main/discussion/44942, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### function-library

#### Formula function library — String functions
*Category: function-library*

- **What it does:** String manipulation functions available inside the Add Formula (ExpressionEvaluator) tile and Magic ETL formula contexts.
- **When to use:** Concatenation, case changes, padding/trimming, substring extraction, regex matching/replacement, cleaning, contains/startswith/endswith tests, casting to string.
- **API / JSON representation:** Used as text inside ExpressionEvaluator `expression`. Complete list from the Supported Functions in Magic ETL reference: CHAR_LENGTH, CONCAT, DYNACAST, GROUP_CONCAT, INITCAP, INSTR, LCASE, LEFT, LENGTH, LISTAGG, LOWER, LPAD, LTRIM, REGEXP_LIKE, REGEXP_REPLACE, REPLACE, RIGHT, SPLIT_PART, STR_CLEAN, STR_CONTAINS, STR_DIGITS, STR_ENDS_WITH, STR_NORMALIZE, STR_REMOVE_DIGITS, STR_STARTS_WITH, STRING, SUBSTRING, UCASE, UPPER.
- **Config options:** N/A
- **Gotchas:** STR_CONTAINS/STR_STARTS_WITH/STR_ENDS_WITH and the STR_* family are Adrenaline/Magic-v2 extensions NOT present in legacy MySQL DataFlows. GROUP_CONCAT/LISTAGG cannot take ORDER BY/DISTINCT in v2. LENGTH vs CHAR_LENGTH differ on multibyte text (bytes vs characters); OCTET_LENGTH (byte length) exists in the Adrenaline SQL DataFlow set.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/360044258533

#### Formula function library — Numeric / Math functions
*Category: function-library*

- **What it does:** Numeric, trigonometric, rounding, unit-conversion, logarithmic and type-cast functions for the Formula tile.
- **When to use:** Arithmetic, rounding/truncation, trig/log, unit and distance conversions, numeric casts, bucketing.
- **API / JSON representation:** Complete list (Supported Functions in Magic ETL): ABS, ACOS, ASIN, ATAN, ATAN2, AVG, CBRT, CEIL, CEILING, CONV, CONVERT_UNIT, COS, COSH, COT, CRC32, DECIMAL, DEGREES, DISTANCE, DISTANCEV, DOUBLE, E, EXP, FINITE, FLOOR, INFINITY, LN, LOG, LOG10, LOG2, LONG, LONG_MAX, LONG_MIN, MOD, NAN, NEGATIVE_INFINITY, PI, POW, POWER, RADIANS, RAND, ROUND, RPAD, RTRIM, SIGN, SIN, SINH, SQRT, TAN, TANH, TRUNCATE, WIDTH_BUCKET.
- **Config options:** N/A
- **Gotchas:** CONVERT_UNIT, DISTANCE/DISTANCEV, CBRT, WIDTH_BUCKET, CRC32, and the INFINITY/NAN/FINITE/LONG_MAX helpers are Adrenaline/Magic-v2 extensions absent from legacy MySQL DataFlows. TRUNCATE(n,d) truncates decimals (not the date TRUNC). Trig/advanced-math availability can be reduced on Magic-on-Cloud-Compute engines — check DX_ENGINE.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://knowledge.domo.com/Prepare/Magic_Transforms/SQL_DataFlows/Creating_an_Adrenaline_DataFlow

#### Formula function library — Date / Time functions
*Category: function-library*

- **What it does:** Date and time construction, arithmetic, extraction, truncation, formatting, and timezone conversion functions for the Formula tile.
- **When to use:** Derive periods (month/quarter/week), date math (add/subtract/diff), parse strings to dates, format dates, timezone conversion, working-day differences.
- **API / JSON representation:** Complete list (Supported Functions in Magic ETL): ADDDATE, ADDTIME, CONVERT_TZ, CURDATE, CURDATETIME, CURRENT_DATE, CURRENT_TIME, CURRENT_TIMESTAMP, CURTIME, DATE, DATEDIFF, DATE_ADD, DATE_FORMAT, DATE_SUB, DATE_TRUNC, DATE_WORKING_DIFF, DATETIME, DAY, DAYNAME, DAYOFMONTH, DAYOFWEEK, DAYOFYEAR, DURATION, FROM_DAYS, FROM_UNIXTIME, HOUR, LAST_DAY, MICROSECOND, MILLISECOND, MINUTE, MONTH, MONTHNAME, NOW, PERIOD_ADD, PERIOD_DIFF, QUARTER, SEC_TO_TIME, SECOND, STR_TO_DATE, SUBDATE, SUBTIME, SYSDATE, TIME, TIME_FORMAT, TIME_TO_SEC, TIMEDIFF, TIMESTAMP, TIMESTAMP_TRUNC, TO_DAYS, TODAY, TRIM, TRUNC, UNIX_TIMESTAMP, WEEK, WEEKDAY, WEEKOFYEAR, YEAR, YEARWEEK.
- **Config options:** N/A
- **Gotchas:** WEEKDAY returns 0=Monday..6=Sunday, whereas DAYOFWEEK follows the ODBC standard 1=Sunday..7=Saturday — a classic off-by-one bug when porting. WEEKDAY() is NOT supported in card Beast Mode (silently replaced by DAYOFWEEK there). DATE_WORKING_DIFF, TIMESTAMP_TRUNC, CURDATETIME, DURATION are Magic-v2/Adrenaline extensions. Use DATE_TRUNC / LAST_DAY for period bucketing (there is no TRUNC_MONTH).
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://knowledge.domo.com/Visualize/Adding_Cards_to_Domo/KPI_Cards/Transforming_Data_Using_Beast_Mode/Sample_Beast_Mode_Calculations%3A_Date_Transforms

#### Formula function library — Logical / Conditional functions
*Category: function-library*

- **What it does:** Conditional branching, boolean logic, null handling and error handling in the Formula tile.
- **When to use:** IF/CASE branching, coalescing nulls, comparing-then-nulling equal values, catching errors, boolean aggregation across expressions.
- **API / JSON representation:** Complete list (Supported Functions in Magic ETL): ALL_TRUE, ANY_TRUE, BOOLEAN, COALESCE, ERROR, IF, IFERROR, IFNULL, NULLIF. Plus SQL-style CASE WHEN <cond> THEN <v> ... ELSE <v> END is valid inside expressions. IF(cond, then, else). The Adrenaline SQL DataFlow set also lists NVL (Oracle-style null default).
- **Config options:** N/A
- **Gotchas:** IFNULL is 2-arg ONLY — for multiple fallbacks use COALESCE(a,b,c,...). In Magic v2 (Adrenaline), a comparison involving NULL evaluates to NULL (treated as not-true), so `WHERE col <> 'x'` / filters silently DROP null rows unless you IFNULL/COALESCE first — different from some MySQL intuitions. Use IFERROR/ERROR to control validation failures rather than letting DP-0118 abort the run.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/360044876614, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

#### Formula function library — Aggregate, Statistical, Financial & System functions
*Category: function-library*

- **What it does:** Aggregate/window-capable statistical functions, hypothesis tests, financial (TVM) functions, and DX_* system/introspection functions available in the Formula/Group By/Rank & Window contexts.
- **When to use:** Aggregations and distributions (SUM/AVG/MEDIAN/PERCENTILE/STDDEV/VARIANCE/CORR/COVAR), statistical tests (ANOVA/t-test), finance (NPV/IRR/PMT), and runtime introspection (which engine/dataflow/execution, preview mode, locale/timezone).
- **API / JSON representation:** Aggregate: APPROXIMATE_COUNT_DISTINCT, CORR, COUNT, COVAR_POP, COVAR_SAMP, FIRST_NON_NULL_VALUE, FIRST_VALUE, LAST_NON_NULL_VALUE, LAST_VALUE, MAX, MEDIAN, MIN, PERCENTILE, STD, STDDEV, STDDEV_POP, STDDEV_SAMP, SUM, VAR_POP, VAR_SAMP, VARIANCE, VARIANCE_POP, VARIANCE_SAMP. Statistical: ANOVAF, ANOVAP, TTEST. Financial: FV, IRR, NPV, PMT, PV, RATE, XIRR, XNPV. System/Other: DX_ACTION_ID, DX_ACTION_NAME, DX_DATAFLOW_ID, DX_DATAFLOW_NAME, DX_ENGINE, DX_EXECUTION_ID, DX_IS_PREVIEW, LOCALE, SYSTEM_LOCALE, SYSTEM_TZ, TZ.
- **Config options:** N/A
- **Gotchas:** Financial functions require interest rates as RATIOS (0.01 = 1%), not percentages. COUNT(*) returns 0 for no rows but most aggregates return NULL when no rows match. In the Group By tile the aggregate is chosen by a type token (SUM, AVERAGE, COUNT_ALL, COUNT_DISTINCT, MIN, MAX, FIRST, LAST, CONCAT_COMMA) — use MIN/MAX (NOT MINIMUM/MAXIMUM). DX_ENGINE lets you detect Magic-on-Cloud-Compute vs classic Adrenaline to branch around unsupported functions. Statistical/financial functions are the most likely to be missing on Cloud Compute engines.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md, https://domohelp.domo.com/hc/en-us/articles/360042935434-Data-Processing-and-Tools-Best-Practices

### filter

#### Filter Rows
*Category: filter*

- **What it does:** Keeps (or excludes) rows matching one or more conditions on column values, constants, other columns, or arbitrary expressions.
- **When to use:** Restrict to a plant/date/status, drop nulls or blanks, keep only rows meeting complex multi-clause logic.
- **API / JSON representation:** `type:'Filter'`. Body: `filterList:[{leftField:'<col>', rightField:'<col-or-null>', rightValue:{value:'<v>', type:'STRING'|'NUMERIC'|'DATE'}, rightExpr:'<expr>', operator:'<OP>', expression:'<raw-expr-or-null>', andFilterList:[ ...nested clauses... ]}]`. Semantics: entries in the top-level `filterList[]` are OR'd together; clauses inside a single entry's `andFilterList[]` are AND'd. Operators: EQ, NE, LT, GT, LE, GE, IN, NIN, NN (is not null), NL (is null). For a raw complex condition set `operator` accordingly and put the full boolean text in `expression`.
- **Config options:** Add conditions: left column, operator, compare-to (value / another column / expression). Combine with AND/OR groups.
- **Gotchas:** A STRING comparison value MUST be a typed object `rightValue:{value:'x',type:'STRING'}` AND the `rightExpr` must be single-quoted ('x'), else VALIDATION-DE. Because NULL comparisons yield NULL (not true) in Adrenaline, `NE`/`<>` filters DROP null rows — add an explicit NL/NN clause or COALESCE upstream if you need to keep them. Empty-string vs NULL are distinct ('' < any date = TRUE can create false matches in date-string filters). Use NN to drop nulls, NL to keep only nulls.
- **Sources:** https://www.domo.com/docs/s/article/360044876614, https://community-forums.domo.com/main/discussion/53828, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### dedupe

#### Deduplicate Rows / Remove Duplicates
*Category: dedupe*

- **What it does:** Removes duplicate rows based on a chosen set of columns; can optionally output a count of collapsed rows.
- **When to use:** Collapse exact/near-duplicate records to a unique grain; count occurrences per key.
- **API / JSON representation:** `type:'Unique'`. Body: `input:<upstream-id>`, `countRows:<true|false>`, `fields:[{name:'<col>', caseInsensitive:<true|false>}]`. A row is a duplicate only when ALL listed `fields` match; unlisted columns are ignored for matching but the first row's values are retained.
- **Config options:** Choose the columns that define uniqueness; per-column case-insensitive option; option to add a row-count column.
- **Gotchas:** Which row 'wins' among duplicates is not guaranteed to be deterministic — sort/rank first (Rank & Window ROW_NUMBER partitioned by the key, then Filter =1) if you must keep a specific record. caseInsensitive is per-field. If you list too few columns you over-collapse; too many and nothing dedups.
- **Sources:** github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md, https://knowledge.domo.com/Prepare/DataFlow_Tips_and_Tricks/Adding_A_Unique_Key_Column_to_A_DataSet

### sort

#### Order / Sort (Utility tile)
*Category: sort*

- **What it does:** Sorts the rows of the dataset by one or more columns, ascending or descending, with advanced string-collation and locale options. Multiple columns sort by list position (primary, secondary...).
- **When to use:** Order data for a specific output ordering, prepare rows for LIMIT (top-N), or to control which row is retained by a downstream step. Newer tile (shipped with the LIMIT tile).
- **API / JSON representation:** Exact action `type` string was NOT confirmed from a raw JSON dump (recent tile; UI name is 'Order'). Following Domo's UI-name=type convention the type is most likely 'Order' with an ordered list of {column, ascending, collation/locale} entries — VERIFY by building the tile in the UI and reading the dataflow back via GET before hard-coding it in generated JSON. Do not confuse with WindowAction.orderRules (that orders WITHIN a Rank & Window partition, not the whole dataset).
- **Config options:** Add one or more columns; per column Ascending/Descending; column position sets sort priority; advanced: String Collation and Locale.
- **Gotchas:** Output DataSets do NOT reliably preserve row order for card consumption — Domo generally treats datasets as unordered and cards re-sort; use Order mainly to feed LIMIT/top-N or a downstream dedup, not to guarantee display order. Historically Magic ETL had no sort tile at all (users faked it with Rank & Window); ensure the target instance has the Order tile.
- **Sources:** https://www.domo.com/docs/s/article/360044876874, https://www.domo.com/product/new-features/magic-etl-order-and-limit-tiles, https://community-forums.domo.com/main/discussion/66723/order-by-in-etl

### limit

#### Limit Rows (Utility tile)
*Category: limit*

- **What it does:** Restricts output to the first N rows (top-N), typically paired with the Order tile.
- **When to use:** Top-N / sampling; keep only the highest/lowest N after an Order.
- **API / JSON representation:** Recent tile; UI name 'Limit'. Exact `type` string not confirmed from a dump — likely 'Limit' with a row-count field; verify via UI-build + GET read-back. Pair after 'Order' for deterministic top-N.
- **Config options:** Row count N.
- **Gotchas:** Without an upstream Order, which N rows are kept is non-deterministic. Not a substitute for previewRowLimit (a sampling setting on inputs).
- **Sources:** https://www.domo.com/docs/s/article/360044876874, https://www.domo.com/product/new-features/magic-etl-order-and-limit-tiles

### text-split

#### Split Column and Text-transform tiles (Value Mapper, Replace Text, Combine Columns, String ops)
*Category: text-split*

- **What it does:** Column-level text transforms adjacent to the core set: split one column into several by a delimiter/regex; map values (lookup replace); replace text; combine/concatenate columns; case/trim/pad string operations.
- **When to use:** Parse composite fields, standardize categorical values (Value Mapper), string cleanup without hand-writing every formula.
- **API / JSON representation:** Split Column = `type:'SplitColumnAction'`, body `{sourceColumn:'<col>', delimiterType:'CUSTOM', delimiter:'<d>', useRegex:<bool>, additions:[{name:'<newcol>', dataType:'STRING'}]}`. Other observed text/utility action types in real dumps: `StringCalculator` (string operations), `Normalizer` (STR_NORMALIZE-style), plus generic ones handled via `ExpressionEvaluator` (REPLACE, REGEXP_REPLACE, CONCAT, LPAD/RPAD, TRIM, LOWER/UPPER/INITCAP). Value Mapper's exact type was not captured; many mappings are equally expressible as a CASE expression in ExpressionEvaluator.
- **Config options:** Split Column: source column, delimiter or regex, output columns. Value Mapper: input column, mapping table of old->new (plus default). Replace Text / Combine Columns / Trim / Capitalize as per Text tiles doc.
- **Gotchas:** For portable API authoring, prefer ExpressionEvaluator (REGEXP_REPLACE / SPLIT_PART / CASE) over the specialized tiles whose exact JSON schemas are less documented. SplitColumnAction.additions define the resulting columns; a regex split with useRegex:true changes delimiter interpretation. STR_NORMALIZE/Normalizer handles accent/width normalization.
- **Sources:** https://www.domo.com/docs/s/article/360045402873, https://community-forums.domo.com/main/discussion/52496, github:stahura/domo-ai-vibe-rules/skills/transformation/magic-etl/SKILL.md

### meta-gotcha

#### MySQL vs Adrenaline (Magic v2) function differences & engine gotchas
*Category: meta-gotcha*

- **What it does:** Captures the behavioral and function-availability differences the authoring AI must respect between legacy MySQL DataFlows, the SQL tile, Adrenaline SQL DataFlows, and the Magic ETL v2 (Adrenaline-engine) Formula tile.
- **When to use:** Whenever porting MySQL/SQL logic into Magic ETL formulas, or generating formulas that must run on Magic-on-Cloud-Compute engines.
- **API / JSON representation:** N/A (guidance). Detect engine at runtime with DX_ENGINE inside a formula.
- **Config options:** N/A
- **Gotchas:** 1) NULL semantics: Magic v2/Adrenaline treats comparisons with NULL as NULL (not-true), so NE/<> filters silently drop nulls and arithmetic with null yields null — wrap with IFNULL/COALESCE; legacy MySQL DataFlows behave more MySQL-classically. 2) Magic ETL v2 adds many functions absent from MySQL (STR_* family, CONVERT_UNIT, DISTANCE, WIDTH_BUCKET, DATE_WORKING_DIFF, TIMESTAMP_TRUNC, APPROXIMATE_*, DX_* introspection, financial FV/IRR/NPV, ANOVA/TTEST). 3) The Formula Editor != Analyzer Beast Mode: some Formula-tile functions do NOT work in a card Beast Mode and some Beast Mode behavior differs (WEEKDAY unsupported in Beast Mode -> becomes DAYOFWEEK). 4) WEEKDAY (0=Mon..6=Sun) vs DAYOFWEEK (1=Sun..7=Sat) index mismatch. 5) GROUP_CONCAT/LISTAGG in v2 cannot use ORDER BY or DISTINCT. 6) Group By agg tokens are SUM/AVERAGE/COUNT_ALL/COUNT_DISTINCT/MIN/MAX/FIRST/LAST/CONCAT_COMMA (use MIN/MAX, not MINIMUM/MAXIMUM). 7) 'Adrenaline DataFlows' are a SEPARATE, on-demand/paid, SQL-script product for billion-row aggregation (not row-by-row) — distinct from Magic ETL v2 even though both run on the Adrenaline engine; its published function set is smaller (adds OCTET_LENGTH, TO_CHAR/TO_NUMBER/TO_DATE, NVL, NTILE, LAG/LEAD, PERCENTILE_CONT, APPROXIMATE_MEDIAN/PERCENTILE). 8) Magic-on-Cloud-Compute (Snowflake/Databricks) can lack advanced statistical/financial/trig functions — branch on DX_ENGINE. 9) Financial functions need rate as ratio not percent. 10) The SQL tile is MySQL-flavored (also basic Redshift, CTEs, window functions) and is a fallback when a transform is hard in tiles; use it to convert existing SQL DataFlows.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/4410213098903, https://www.domo.com/docs/s/article/000005809, https://www.domo.com/docs/s/article/360047787514, https://knowledge.domo.com/Prepare/Magic_Transforms/SQL_DataFlows/Creating_an_Adrenaline_DataFlow, https://domohelp.domo.com/hc/en-us/articles/360042935434-Data-Processing-and-Tools-Best-Practices, https://knowledge.domo.com/Visualize/Adding_Cards_to_Domo/KPI_Cards/Transforming_Data_Using_Beast_Mode/Sample_Beast_Mode_Calculations%3A_Date_Transforms

**Open questions / not fully verified:**

- Exact action `type` strings for the newer Order and Limit utility tiles are unconfirmed from a raw JSON dump (likely 'Order'/'Limit' per Domo's UI-name convention) — should be verified by building each tile in the web UI and reading the dataflow back via GET /api/dataprocessing/v1/dataflows/{id}.
- Verbatim field-key schemas for the Alter Columns (`Metadata`) and Add Constants (`Constant`) actions were not captured from a raw dump — type names are confirmed but the exact per-column entry keys (list name, type-token casing, date-format key) should be confirmed by read-back.
- Contradiction to resolve: one community CLI skill reports `SelectValues` returning DP-0069 (invalid action type) when CREATING new flows via API, while real GET dumps of existing flows show `SelectValues` working with `fields:[{name,rename}]`. Likely graph-version/instance dependent; confirm on the target instance before generating create payloads.
- Value Mapper and the specialized text tiles' exact action `type`/schema (beyond SplitColumnAction, StringCalculator, Normalizer seen in dumps) are only partially documented — ExpressionEvaluator (CASE/REGEXP_REPLACE/SPLIT_PART) is the recommended portable substitute.
- Auth discrepancy across the two community skills: one uses `x-domo-developer-token`, the other a session SID for the dataflows API — confirm which header the target automation path expects.

## Text & date tiles/functions

### meta / API representation

#### Dataflow JSON envelope & action structure (how tiles are represented)
*Category: meta / API representation*

- **What it does:** Every Magic ETL dataflow is a directed acyclic graph (DAG) of 'actions' (tiles). The copy/paste + API payload wraps them as {"contentType":"domo/dataflow-actions","data":[ ...actions... ]}. Each action object carries: name (tile label), id (GUID), type (the tile-type string — this is the load-bearing field), gui{x,y[,color]}, dependsOn[array of upstream action ids], removeByDefault(bool), notes[]. Input tiles are type 'LoadFromVault' (with dataSourceId), output tiles type 'PublishToVault'. Transform-specific fields (calculations[], fields[], separator, etc.) hang directly off the action object.
- **When to use:** Foundation for authoring ANY text/date tile programmatically. Build tiles as action objects, wire them via dependsOn (each tile references the id(s) of the tile feeding it), assign unique GUIDs.
- **API / JSON representation:** {"contentType":"domo/dataflow-actions","data":[{"name":...,"id":"<guid>","type":"<TileType>","gui":{"x":n,"y":n},"dependsOn":["<upstream-guid>"],"removeByDefault":false,"notes":[], ...tile-specific fields...}]}. Input=LoadFromVault(dataSourceId,executeFlowWhenUpdated,onlyLoadNewVersions), Output=PublishToVault. MySQL-dataflow transforms use GenerateTableAction / SQL / SqlAction instead.
- **Config options:** Discover exact current type strings by building a tile in the UI and Ctrl+C copying it, or exporting via Domo CLI `list-dataflow` (returns this JSON). Assigning system-accepted unique GUIDs is the hard part of full automation.
- **Gotchas:** Community-confirmed type strings below are from Magic ETL 1.0 copy/paste; the v2 (current) canvas uses the same 'domo/dataflow-actions' envelope and LoadFromVault/PublishToVault carry over, but individual calculator tile type names may differ in v2 — verify by copying a tile from the target instance. Magic will error if an input dataset is loaded but not consumed by a transform (unlike MySQL dataflows).
- **Sources:** https://community-forums.domo.com/main/bestof/awesome/p3?Page=p38, https://community-forums.domo.com/main/discussion/52491/dataflow-transform-i-e-action-types-in-api-json-data, https://stackoverflow.com/questions/77917850/extract-domo-magic-etl-metadata-for-sql-migration

### text tile

#### Combine Columns tile (concatenate fields)
*Category: text tile*

- **What it does:** Combines values from multiple columns into one column, joined by a configurable separator character. Option to remove (drop) the original source columns after combining.
- **When to use:** Building compound keys or display fields (e.g., first+last name → full name). Documented MySQL equivalent: CONCAT(col1,' ',col2) AS full_name.
- **API / JSON representation:** type:"ConcatFields". Fields: separator (string), targetFieldName (output column name), removeSelectedFields (bool), fields:[{name:"colA"},{name:"colB"}].
- **Config options:** separator, targetFieldName, removeSelectedFields, ordered fields[] list.
- **Gotchas:** For NULL handling / non-column literals you often need Add Formula's CONCAT() instead (CONCAT returns NULL if any arg is NULL).
- **Sources:** https://community-forums.domo.com/main/bestof/awesome/p3?Page=p38, https://www.domo.com/docs/s/article/360042923234, https://www.domo.com/docs/s/article/360045402873

#### String Operations tile (substring / trim / pad)
*Category: text tile*

- **What it does:** Applies substring extraction, trim, and pad operations to a text column, writing each result to a new named column. Multiple operations can be batched in one tile via a calculations[] array.
- **When to use:** Extract fixed-position slices (e.g., first 4 chars of a Julian date), trim, or pad without writing a formula.
- **API / JSON representation:** type:"StringCalculator", calculations:[{calcType:"SUBSTR_RL", constantB:{value:"4",type:"LONG"}, constantC:{value:"LEFT",type:"STRING"}, fieldA:"src", fieldName:"OUT"}]. calcType SUBSTR_RL = take N chars from LEFT or RIGHT (constantC direction, constantB length). fieldA=source column, fieldName=output column.
- **Config options:** Per calculation: calcType (operation), fieldA (source col), fieldName (output col), constantB/constantC (typed {value,type} operands, e.g. length + LEFT/RIGHT direction). Other calcType values (trim, pad, case) exist but weren't enumerated in public docs — inspect a UI-built tile to confirm exact strings.
- **Gotchas:** Legacy 1.0 tile; in v2 much of this is folded into the Add Formula tile (SUBSTRING/LEFT/RIGHT/LPAD/RPAD/TRIM). Operands are typed objects, not bare values.
- **Sources:** https://community-forums.domo.com/main/bestof/awesome/p3?Page=p38, https://www.domo.com/docs/s/article/360045402873

#### Replace Text tile
*Category: text tile*

- **What it does:** Search-and-replace within a text column. Supports whole-word matching, case-sensitive matching, and Java regular expressions (SQL RegEx for Snowflake-backed dataflows).
- **When to use:** Cleaning/standardizing strings, stripping characters, regex-based extraction. Docs use it as the equivalent of MySQL SUBSTRING_INDEX (extract portion / split by delimiter) and TRIM (via regex).
- **API / JSON representation:** Public type string not confirmed in fetched sources (likely "ReplaceText"/"StringReplace"); verify from a UI-copied tile. Config carries pattern, replacement, whole-word flag, case-sensitive flag, regex flag.
- **Config options:** Match text, replacement text, Whole words only, Case sensitive, Use regular expressions (Java regex; SQL RegEx on Snowflake).
- **Gotchas:** Regex flavor is Java (or SQL on Snowflake) — not identical to MySQL regex. For pattern replace inside Add Formula use REGEXP_REPLACE(str,pat,repl[,flags]) with c/i/m/n flags.
- **Sources:** https://www.domo.com/docs/s/article/360045402873, https://www.domo.com/docs/s/article/360042923234, https://www.domo.com/docs/s/article/360044289573

#### Split Column tile
*Category: text tile*

- **What it does:** Splits a single string column into multiple columns by a specified delimiter. Option to keep all extra/leftover splits in the final column.
- **When to use:** Break a delimited field (CSV cell, path, name) into separate columns. MySQL analog: repeated SUBSTRING_INDEX(col,delim,n).
- **API / JSON representation:** Public type string not confirmed (likely "SplitColumn"); config includes delimiter and a flag to keep remainder in last column. Verify from UI-copied tile.
- **Config options:** Delimiter, number of output columns, keep-extra-splits-in-last-column toggle.
- **Gotchas:** For a single Nth piece rather than a full split, Add Formula's SPLIT_PART(str,sep,N) is simpler (returns '' if fewer than N segments; NULL if N<=0).
- **Sources:** https://www.domo.com/docs/s/article/360045402873, https://www.domo.com/docs/s/article/360044289573

#### Text Formatting tile
*Category: text tile*

- **What it does:** Reformats a text column: lower case, UPPER CASE, or Capitalization; remove numbers; or remove everything except numbers.
- **When to use:** Case normalization and quick numeric/alpha stripping without a formula. MySQL analog: UPPER/LOWER; capitalize-first-letter via CONCAT(UPPER(LEFT(...)),...).
- **API / JSON representation:** Public type string not confirmed (likely "TextFormatting"/"CaseFormatter"). Config selects the formatting mode and target column. Verify from UI-copied tile.
- **Config options:** Mode: lower / upper / capitalize (title-ish) / remove numbers / keep only numbers; source column; new-or-overwrite output.
- **Gotchas:** 'Capitalization' here is not the same as INITCAP (per-word) — for reliable per-word title case use Add Formula INITCAP(str).
- **Sources:** https://www.domo.com/docs/s/article/360045402873, https://www.domo.com/docs/s/article/360042923234

### text / utility tile

#### Value Mapper tile (search-and-replace by value pairs)
*Category: text / utility tile*

- **What it does:** Searches and replaces string values in a column according to pairs of from→to values you enter (e.g., abbreviation or language-code lookups). Can write to a new column or overwrite, with a configurable default value for unmatched entries.
- **When to use:** Small lookup/recode tables inline (map codes to labels) without a Join tile. Alternative to Replace Text/Duplicate Column for discrete value recoding.
- **API / JSON representation:** Lives in the Utility tab. Public type string not confirmed (likely "ValueMapper"). Config holds the mapping pairs, target/new column, and default-for-unmatched.
- **Config options:** Mapping pairs (from,to), output column (new or overwrite), default value for non-matches.
- **Gotchas:** For many/dynamic mappings prefer a Join against a reference dataset; Value Mapper pairs are static in the tile config.
- **Sources:** https://www.domo.com/docs/s/article/360044876874

### text+date tile (primary)

#### Add Formula tile (row-by-row expression evaluator)
*Category: text+date tile (primary)*

- **What it does:** A row-by-row expression evaluator (the modern home for most text AND date transforms). Uses MySQL/Beast-Mode-style SQL syntax. Each formula produces exactly one output column (new, or overwrite when the name matches). Supports string, date, math, statistical, time-value-of-money, conditional/case, and type-cast functions. Includes an AI SQL Assistant to draft formulas.
- **When to use:** Any transform not covered by a dedicated tile, and the recommended way in v2 to do concat/substring/replace/case/date-diff/date-add/format/parse in one place. NOT for aggregations — use Group By.
- **API / JSON representation:** Utility-section tile. type not confirmed in fetched docs (v2 formula-evaluator action; verify from UI-copied tile — legacy analogs were StringCalculator/DateCalculator). Config carries output column name + the formula expression string.
- **Config options:** Output Column Name; Formula expression. Column refs use backticks `col` (required for multi-word names or names colliding with function keywords like DATE) or double quotes; string literals use single quotes. Ctrl+Enter previews a single row. Aggregate functions are NOT allowed.
- **Gotchas:** Formula Editor is a superset of Analyzer Beast Mode — formulas here may not paste back into a Beast Mode (extra DataFlow processing power). One column per formula. No aggregates.
- **Sources:** https://www.domo.com/docs/s/article/360044258533, https://www.domo.com/docs/s/article/360044289573

### date tile (primary)

#### Date Operations tile (10 date operations)
*Category: date tile (primary)*

- **What it does:** Adds a new column from a date-based calculation. Ten operations: (1) Add to date, (2) Subtract from date, (3) Difference between dates, (4) Year of date, (5) Quarter of date, (6) Month of date, (7) Day of year, (8) Day of month, (9) Day of week, (10) Week of year.
- **When to use:** Extract date parts or do date arithmetic/diff without a formula. Add/Subtract support months, weeks, days, hours, minutes, seconds, milliseconds. Difference supports days, WORKING days, hours, minutes, seconds, milliseconds. Docs map MySQL DAYNAME(date)→this tile.
- **API / JSON representation:** type:"DateCalculator", calculations:[{fieldName:"OUT", calcType:"ADD_SUBTRACT_DATE", fieldA:"startDate", fieldB:"intervalCol", constantC:{type:"STRING",value:"DAYS"}}]. calcType ADD_SUBTRACT_DATE = add/subtract (unit in constantC: DAYS, etc.; fieldB or a constant gives the amount). Other calcTypes cover diff and each extract-part op (inspect a UI tile for their exact strings).
- **Config options:** Per calculation: output column (fieldName), operation (calcType), source date column (fieldA), second operand (fieldB column or constant), unit constant (constantC: DAYS/WEEKS/MONTHS/HOURS/... or WORKING days for diff).
- **Gotchas:** Week of year weeks span Sunday–Saturday. Day of week returns a NUMBER (ODBC standard: 1=Sunday); use DAYNAME() in a formula for the text name. 'Working days' diff excludes weekends. For truncate-to-month/week/quarter there is NO tile op — use DATE_TRUNC/TIMESTAMP_TRUNC in Add Formula.
- **Sources:** https://www.domo.com/docs/s/article/360045402313, https://community-forums.domo.com/main/bestof/awesome/p3?Page=p38, https://www.domo.com/docs/s/article/360042923234

### date/type tile

#### Set Column Type / Alter Columns tile (string↔date parsing)
*Category: date/type tile*

- **What it does:** Changes a column's data type — notably parses a text column into a DATE/DATETIME (and vice-versa) using a date-format hint, without writing STR_TO_DATE. This is Domo's documented way to reformat a non-standard date string into a real date type.
- **When to use:** Turn '23.01.2017' or 'YYYY-MM-DD' strings into DATE columns; or coerce numbers/booleans. Docs map MySQL STR_TO_DATE(col,'%d.%m.%Y')→this tile.
- **API / JSON representation:** type:"Metadata", fields:[{name:"col",type:"DATE",dateFormat:"YEAR_FIRST"},{name:"n",type:"LONG"}]. dateFormat enum controls interpretation order (e.g. YEAR_FIRST = yyyy-mm-dd; MONTH_FIRST / DAY_FIRST analogs exist). type ∈ STRING/LONG/DOUBLE/DECIMAL/DATE/DATETIME/BOOLEAN.
- **Config options:** Per field: name, target type, dateFormat hint (YEAR_FIRST etc.) for date parsing.
- **Gotchas:** Named 'Set Column Type' in 1.0, 'Alter Columns' in v2 — same JSON type 'Metadata'. Wrong dateFormat silently mis-parses. For arbitrary format masks use STR_TO_DATE(str,'%d.%m.%Y') in Add Formula instead.
- **Sources:** https://community-forums.domo.com/main/bestof/awesome/p3?Page=p38, https://www.domo.com/docs/s/article/360042923234, https://www.domo.com/docs/s/article/360044876874

### text tile (AI)

#### AI Text Generation tile
*Category: text tile (AI)*

- **What it does:** LLM-powered tile that processes a text field per row with a natural-language instruction — summarize, categorize, classify, or extract structured pieces — turning qualitative text into structured columns.
- **When to use:** When rule-based text tiles can't parse free text (sentiment, categorization, entity extraction). Lives under the AI Services tile group.
- **API / JSON representation (`type: "TextGeneration"`):** `modelId` (e.g. `domo.domo_ai.domogpt-medium-v2.2:anthropic`), `temperature`, `instructions` (system text), `prompt` (user template), `parameters` (map), `structuredOutput`, `outputColumnName: "output"`, `outputColumns: [{title, type, description}]`, `executionPreference` (`BATCH` for >100-row inputs; non-batch is forced under 100 rows), plus the usual `input`/`dependsOn`/`gui`.
- **Column binding contract (verified 2026-10-07):** the prompt template references columns as `{{列名}}` and `parameters` maps `{列名: 列名}` — the exact form the editor writes via **Insert Value (値の挿入)**. An English alias → column mapping (`{alias: 列名}` with `{{alias}}`) still substitutes at runtime but renders as an unresolvable `?` chip in the editor, so it is unverifiable and forbidden. The `?` badge can also be a transient editor state — reload the tile before concluding a binding is broken. Regression check: walk the dependency graph and assert every parameter column exists in the tile input schema (see `reference-app/tests/test_textgen_parameters.py`).
- **Gotchas:** Consumes credits and is subscription/entitlement-gated; non-deterministic output. A manual UI save can append experimental chips and drop unresolvable parameters — re-PUT the builder definition instead of hand-merging. Not a substitute for deterministic text tiles when a rule works.
- **Sources:** https://www.domo.com/product/new-features/ai-text-generation-dataflow-tile-for-magic-etl, https://www.domo.com/docs/s/article/000005741, ../skills/domo-magic-etl-textgen-tile.md

### text functions

#### String function library (Add Formula / Group By)
*Category: text functions*

- **What it does:** Documented string functions usable in Add Formula/Group By: CONCAT(a,b,...); SUBSTRING(str,pos[,len]) (also SUBSTRING(str FROM pos FOR len); negative pos counts from end); REPLACE(str,from,to) (case-sensitive); TRIM([{BOTH|LEADING|TRAILING} [remstr] FROM] str), LTRIM/RTRIM; UPPER/UCASE, LOWER/LCASE; INITCAP (capitalize each word); LEFT/RIGHT(str,len); LPAD/RPAD(str,len,padstr); SPLIT_PART(str,sep,N); LENGTH (UTF-8 byte length) vs CHAR_LENGTH (character count) vs OCTET_LENGTH; INSTR(str,substr) (1-based position, 0 if absent); STR_CONTAINS / STR_STARTS_WITH / STR_ENDS_WITH (booleans); REGEXP_LIKE(str,pat[,flags]) and REGEXP_REPLACE(str,pat,repl[,flags]) with c/i/m/n flags; TO_CHAR(any,format) / TO_NUMBER(str[,pattern]).
- **When to use:** All programmatic text manipulation inside Add Formula. SPLIT_PART/REGEXP_*/STR_CONTAINS/INITCAP are Domo additions beyond core MySQL.
- **API / JSON representation:** Plain SQL-ish expressions inside the Add Formula tile's formula string; columns in backticks.
- **Config options:** N/A (expression text).
- **Gotchas:** LENGTH counts BYTES (multi-byte chars >1) — use CHAR_LENGTH for character count. REPLACE is case-sensitive. CONCAT returns NULL if any argument is NULL. Full authoritative list lives in the in-editor Functions list.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/4410213098903

### date functions

#### Date/time function library (Add Formula / Group By)
*Category: date functions*

- **What it does:** Documented date/time functions: DATE_FORMAT(date,format) render; STR_TO_DATE(str,format) parse; DATE_ADD/DATE_SUB(date,INTERVAL expr unit) and synonyms ADDDATE/SUBDATE; DATEDIFF(expr1,expr2) (days, date-part only, expr1−expr2); DATE_TRUNC(precision,date) and TIMESTAMP_TRUNC(ts[,precision]) (arg order flipped between them); extract parts YEAR/QUARTER/MONTH/WEEK(date[,mode])/DAYOFMONTH(DAY)/DAYOFWEEK/DAYOFYEAR/WEEKDAY/HOUR/MINUTE/SECOND; DAYNAME/MONTHNAME (text names); YEARWEEK(date[,mode]); LAST_DAY(date); DATE()/DATETIME()/TIME()/TIMESTAMP()/TO_DATE() casts; NOW/CURRENT_TIMESTAMP/SYSDATE, CURDATE/TODAY; UNIX_TIMESTAMP/FROM_UNIXTIME, TO_DAYS/FROM_DAYS, TIME_TO_SEC/SEC_TO_TIME; PERIOD_ADD/PERIOD_DIFF (YYYYMM period math); CONVERT_TZ(dt,from_tz,to_tz); ADDTIME/SUBTIME/TIMEDIFF/TIME_FORMAT.
- **When to use:** All date arithmetic, extraction, formatting, and truncation in Add Formula. Truncate-to-month/week/quarter = DATE_TRUNC('MONTH',`d`) / TIMESTAMP_TRUNC. 'First day of this week' pattern: SUBDATE(`Date`,WEEKDAY(`Date`)-1).
- **API / JSON representation:** Expression text in Add Formula. Structures (Adrenaline ref): DATEDIFF(TIME,TIME)->LONG; DATE_TRUNC(STRING date_part, TIME)->TIME; WEEK/YEAR/YEARWEEK take optional mode.
- **Config options:** WEEK/YEAR mode: 2-digit; 1st digit 1=Jan-1-based / 2=ISO; 2nd digit first weekday (Sun=1,Mon=2). Only modes 11 and 22 are supported.
- **Gotchas:** DATEDIFF ignores time components (date-part only). DATE_TRUNC vs TIMESTAMP_TRUNC have flipped argument order. DAYOFWEEK==WEEKDAY numbering. STR_TO_DATE return type varies (STRING for '%T'/'%H...', DATETIME if format >10 chars, else DATE).
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/4410213098903, https://knowledge.domo.com/Visualize/Adding_Cards_to_Domo/KPI_Cards/Transforming_Data_Using_Beast_Mode/Sample_Beast_Mode_Calculations:_Date_Transforms

### date functions (detail)

#### DATE_FORMAT / STR_TO_DATE format specifiers
*Category: date functions (detail)*

- **What it does:** MySQL-style format codes used by DATE_FORMAT (render) and STR_TO_DATE (parse): %Y 4-digit year, %y 2-digit year; %M full month name, %b short month, %m 2-digit month; %d 2-digit day, %e 1–2 digit day; %H 00–23 hour, %h/%I 01–12 hour, %i minutes, %S/%s seconds, %f microseconds(6); %W full weekday, %a short weekday, %w weekday index 0–6, %j day-of-year 001–366; %U/%V Sunday-based week, %u/%v Monday-based week; %r 12-hour AM/PM time, %T 24-hour time.
- **When to use:** Constructing/parsing date strings in Add Formula (e.g., DATE_FORMAT(`d`,'%Y-%m'), STR_TO_DATE(`s`,'%d.%m.%Y')).
- **API / JSON representation:** Format string literal (single-quoted) inside the formula.
- **Config options:** N/A.
- **Gotchas:** Case matters (%M month name vs %m month number; %Y 4-digit vs %y 2-digit). TIME_FORMAT handles time-only masks.
- **Sources:** https://www.domo.com/docs/s/article/360044289573

#### DATE_TRUNC / TIMESTAMP_TRUNC precision constants
*Category: date functions (detail)*

- **What it does:** Precision keywords for truncating a timestamp: MILLENNIUM, CENTURY, YEAR, ISOYEAR, QUARTER, MONTH, YEARWEEK, ISOWEEK, MONTHWEEK, WEEK, DAY, HOUR, MINUTE, SECOND, MILLISECOND, MICROSECOND.
- **When to use:** Bucketing dates to month/quarter/week for time-series rollups — the canonical 'truncate to month/week' capability (no dedicated tile op exists for it).
- **API / JSON representation:** DATE_TRUNC('MONTH',`d`) or TIMESTAMP_TRUNC(`ts`,'WEEK'). Note the two functions take precision in opposite argument positions.
- **Config options:** Precision constant (string).
- **Gotchas:** ISOWEEK/ISOYEAR/MONTHWEEK are Domo/Adrenaline extensions not present in stock MySQL. Watch the flipped arg order between DATE_TRUNC and TIMESTAMP_TRUNC.
- **Sources:** https://www.domo.com/docs/s/article/360044289573

### logic / conversion functions

#### Conditional, logical & type-cast functions
*Category: logic / conversion functions*

- **What it does:** Conditional/logical: CASE WHEN...THEN...ELSE...END, IF(test,exprTrue,exprFalse), IFNULL(a,b), COALESCE(...), NULLIF(a,b), IFERROR(a,b), ALL_TRUE(c1,c2,...), ANY_TRUE(c1,c2,...). Type conversion: CAST(expr AS type) plus function-form casts DOUBLE(), LONG(), STRING(), BOOLEAN(), DECIMAL(), DATE(), DATETIME(), DURATION().
- **When to use:** Row-level categorization/derivation in Add Formula (equivalent to the docs' 'Categorizing Rows' pattern that otherwise needs Filter+Add Constants+Append). Casting text↔number↔date inside formulas.
- **API / JSON representation:** Expression text in Add Formula. IFERROR/ALL_TRUE/ANY_TRUE are Domo-specific conveniences.
- **Config options:** N/A.
- **Gotchas:** These belong to the Formula-Editor superset; some won't paste back into Analyzer Beast Modes. Aggregate functions still not allowed in Add Formula.
- **Sources:** https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/360042923234

### engine / equivalences

#### MySQL vs Adrenaline engine — function-set differences
*Category: engine / equivalences*

- **What it does:** Magic ETL runs on Domo's proprietary Adrenaline engine (columnar/in-memory; NOT Apache Spark — the 'Spark' label is a common misnomer) and can also run 'Magic ETL on Snowflake'. MySQL/Redshift/Adrenaline SQL DataFlows are SEPARATE dataflow types that take raw SQL. The Add Formula / Adrenaline function library is deliberately MySQL-flavored (DATE_FORMAT %Y codes, STR_TO_DATE, DATEDIFF, DAYNAME, PERIOD_ADD) so most same-named functions behave alike.
- **When to use:** Deciding whether to express text/date logic as tiles (Magic ETL) or SQL (MySQL/Redshift/Adrenaline dataflow), and translating between them.
- **API / JSON representation:** Adrenaline SQL DataFlow function reference (article 4410213098903) lists supported funcs with signatures. Magic ETL formula reference (article 360044289573) is the tile-formula superset.
- **Config options:** N/A.
- **Gotchas:** Adrenaline ADDS functions MySQL lacks: DATE_TRUNC/TIMESTAMP_TRUNC with ISOWEEK/MONTHWEEK, SPLIT_PART, INITCAP, STR_CONTAINS/STARTS_WITH/ENDS_WITH, REGEXP_LIKE/REGEXP_REPLACE, IFERROR, ALL_TRUE/ANY_TRUE, function-form casts (DOUBLE/LONG/STRING). Conversely some MySQL funcs may be absent in a given engine. Adrenaline WEEK only supports modes 11/22. Redshift dataflows have long queue startup; MySQL dataflows are far slower than Magic ETL v2 on large data. Regex flavor in the Replace Text tile is Java (SQL on Snowflake), not MySQL.
- **Sources:** https://www.domo.com/docs/s/article/4410213098903, https://www.domo.com/docs/s/article/360044289573, https://www.domo.com/docs/s/article/360042923234, https://note.com/domo_official/n/n2ddeba3e2e36

### date tile (gap)

#### Dedicated date-dimension / calendar tile — absence & workaround
*Category: date tile (gap)*

- **What it does:** Magic ETL has NO dedicated calendar/date-dimension generator tile. The Dates & Numbers tab contains only Date Operations and Calculator. Date dimensions are built by combining other tiles.
- **When to use:** When a skill needs a calendar table: generate rows with the Series tile (sequential integers) or the newer Fixed Input tile (type/paste/AI-generate seed rows), then derive date columns with Add Formula (DATE_ADD from an anchor date, then YEAR/MONTH/QUARTER/DATE_TRUNC/DAYNAME to fill attributes).
- **API / JSON representation:** Series tile (sequential row numbers) + Fixed Input tile (inline seed data, stored in the dataflow) + Add Formula. No 'calendar' action type exists.
- **Config options:** Series: start/step/count-style row generation. Fixed Input: manual/CSV-paste/AI-generated columns.
- **Gotchas:** Don't look for a calendar tile — assemble one. The Fixed Input tile is a recent addition (may be entitlement/version-gated).
- **Sources:** https://www.domo.com/docs/s/article/360045402313, https://www.domo.com/docs/s/article/360044876874, https://www.domo.com/product/new-features/magic-etl-beta-enhancements

**Open questions / not fully verified:**

- Exact v2 (current) tile 'type' strings for the Text tiles (Replace Text, Split Column, Text Formatting, Value Mapper) and the v2 Add Formula action are not published in official docs — confirmed strings (StringCalculator, DateCalculator, ConcatFields, Constant/Metadata) come from Magic ETL 1.0 copy/paste JSON. Best confirmed by building each tile in the target instance and Ctrl+C copying, or `list-dataflow` via Domo CLI.
- Full enumeration of StringCalculator/DateCalculator calcType values (only SUBSTR_RL and ADD_SUBTRACT_DATE observed directly) — remaining trim/pad/case/diff/extract calcType strings need a UI-copied tile to confirm.
- Whether the public Domo REST API supports creating Magic ETL (Adrenaline) dataflows directly, or whether the practical path is the Domo CLI / copy-paste 'domo/dataflow-actions' payload; sources point to CLI list-dataflow for round-tripping but community notes creating dataflows programmatically is difficult mainly due to GUID assignment.
- Precise dateFormat enum values for the Metadata/Alter Columns tile beyond YEAR_FIRST (MONTH_FIRST / DAY_FIRST assumed but not directly cited).
- Exact behavioral deltas between 'Magic ETL on Snowflake' and Adrenaline for these text/date functions (e.g., regex flavor is noted as SQL RegEx on Snowflake vs Java elsewhere) were not fully enumerated in fetched pages.

## Data science & AI tiles

### Scripting

#### Python Script tile
*Category: Scripting*

- **What it does:** Runs a custom Python script inside a Magic ETL DataFlow. Reads upstream tile data into pandas/NumPy via the domomagic library, executes arbitrary Python, and writes one output DataFrame back into the DAG as the tile's output. Used for any transformation/data-science logic not expressible with native tiles.
- **When to use:** Custom ML/stats, complex reshaping, regex-heavy parsing, or reusing existing Python code that must run on every DataFlow refresh. Place native tiles before/after to shape data cheaply and reserve Python for the hard part.
- **API / JSON representation:** Action type string: "PythonEngineAction" (display name "Python Script", category "Scripting"). Node lives in the dataflow actions[] DAG with id/type/dependsOn/gui like other tiles; script text and declared output schema are carried in the action's settings.
- **Config options:** Script body (Python). Output SCHEMA must be declared in the Schema tab via one of three methods: type columns manually, bulk-add from an input dataset, or run the script to auto-detect. Environment selection (Domo 2.0 default). Preview runs on a sample; sample row limit is configurable. Only ONE output (one write_dataframe) per tile.
- **Gotchas:** Available BY DEFAULT only to customers on the Domo Consumption agreement; others must contact their Domo account team (on-demand). Data-type coercion: LONG becomes DOUBLE in Python (NumPy can't hold NULLs in int columns) and DECIMAL becomes DOUBLE. node -c style syntax checks won't catch schema mismatch — declared schema must match what the script actually writes or the run fails. Exactly one export per script.
- **Sources:** https://www.domo.com/docs/s/article/360045485833, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### R Script tile
*Category: Scripting*

- **What it does:** Runs a custom R script inside Magic ETL. Reads upstream data into an R data.frame via the domomagic R package, executes R code, and writes one data.frame/matrix as the tile output.
- **When to use:** When the needed statistical/ML capability is best expressed in R (e.g. forecast, caret, survival models) or existing R code must run on refresh.
- **API / JSON representation:** Action type string: "REngineAction" (display name "R Script", category "Scripting").
- **Config options:** Script body (R). Output schema declared in Schema tab (same 3 methods as Python). Environment selection (Domo 2.0 default). read.dataframe() accepts colClasses, stringsAsFactors, integersAsNumerics, allVerbatimExcept, allIgnoredExcept parameters to control type mapping. One output per tile.
- **Gotchas:** Same availability gate as Python (Consumption agreement default, else on-demand). DECIMAL becomes DOUBLE (no analogous R type). One export only.
- **Sources:** https://www.domo.com/docs/s/article/360045485833, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### domomagic API (Python & R I/O contract)
*Category: Scripting*

- **What it does:** The bridge library that loads data into and out of scripting-tile contexts. Every scripting tile must import it to receive input and emit output.
- **When to use:** Always, inside Python/R Script tiles — it is the only supported way to read the upstream tile and write the tile output.
- **API / JSON representation:** Python module `domomagic` (v0.3): read_dataframe(input_name=None) -> pandas.DataFrame; write_dataframe(dataframe); read_array(column_name, input_name=None) -> NumPy array; read_array_dict(input_name=None) -> OrderedDict of column->NumPy array; write_array_dict(array_dict). R package `domomagic` (v0.4): read.dataframe(input.name=NULL); write.dataframe(table). Import with `from domomagic import *`.
- **Config options:** input_name / input.name selects which upstream input when the tile has multiple inputs (defaults to the single/first input). write_array_dict requires equal-length arrays.
- **Gotchas:** read_dataframe does not accept a pandas dtype dictionary parameter (community-confirmed) — cast after reading. Only one write per script.
- **Sources:** https://www.domo.com/docs/s/article/360045485833, https://community-forums.domo.com/main/discussion/54835/python-tile-typecasting-while-reading-data

#### Scripting environment & shared directories (Domo 2.0)
*Category: Scripting*

- **What it does:** Defines the runtime for scripting tiles: a preinstalled 'Domo 2.0' environment plus two shared filesystem locations for passing objects/models between tiles or executions.
- **When to use:** When you need to persist a trained model between runs, share intermediate objects across scripting tiles in the same DataFlow, or know which libraries are available before writing code.
- **API / JSON representation:** Not a separate action type; environment is a setting on the Python/R tile. Shared dirs: Project Directory (/path/to/home/project or `project`) and /tmp.
- **Config options:** Domo 2.0 Python includes (versions from Domo docs) pandas 1.4.1, numpy 1.22.3, scikit-learn 1.0.2, scipy 1.8.0, statsmodels, xgboost 1.5.1, tensorflow 2.7.0, keras 2.7.0, torch 1.11.0, plus ~80+ packages; R includes forecast 8.16, caret 6.0-91, tidyverse 1.3.1, xgboost 1.5.1, cluster, tsoutliers, plus ~200+ packages. Project Directory persists between executions and is shared across all tiles (8 GB limit). /tmp is shared within a run but cleared between DataFlow executions.
- **Gotchas:** Library versions are pinned/older — do not assume latest APIs. Custom package installation / alternative environments are limited and not documented as self-serve; heavy models should be written to the Project Directory rather than retrained each run.
- **Sources:** https://www.domo.com/docs/s/article/000005117, https://domo-support.domo.com/minasan/s/article/000005117?language=en_US

### Data Science

#### Clustering tile (K-means / K-medians)
*Category: Data Science*

- **What it does:** Unsupervised clustering: assigns each row to one of K clusters based on its distance to iteratively-recomputed cluster centers (K-medians recomputes the median as the new center each iteration until membership stabilizes).
- **When to use:** Segmentation on numeric features (customers, SKUs, sensors) with no labels.
- **API / JSON representation:** Legacy Data Science tiles are represented by action type "UserDefinedAction" (display name "Data Science Model", category "Data Science"); the specific algorithm (K-means vs K-medians) and parameters are carried inside the action's settings.
- **Config options:** Select the numeric column(s) to cluster on; Number of clusters (K); Algorithm (K-means or K-medians); Output column name (default "cluster").
- **Gotchas:** Requires at least one numeric column. Output appends a cluster-membership column to the original rows. Tiles gated behind Consumption agreement (default) or on-demand+paid; you may need to complete training before use. Clean/scaled data strongly recommended.
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### Outlier Detection tile (univariate)
*Category: Data Science*

- **What it does:** Flags anomalous values in a single numeric column using either Standard Deviation or Mean Absolute Deviation from the mean/median.
- **When to use:** Simple single-variable anomaly flagging (spikes in a metric).
- **API / JSON representation:** action type "UserDefinedAction" ("Data Science Model", Data Science category); algorithm + threshold in settings.
- **Config options:** Single numeric column; Algorithm (Standard Deviation | Mean Absolute Deviation); deviation threshold (typical 2–3); Output column name (default "outlier").
- **Gotchas:** Operates on one numeric column only. Output is TRUE/FALSE per row. Same availability gating as other DS tiles.
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753

#### Multivariate Outliers tile
*Category: Data Science*

- **What it does:** Anomaly detection across two or more numeric columns using a Chi-square-distribution distance cutoff to flag unusual multi-dimensional observations.
- **When to use:** Detect rows that are unusual in combination (e.g. clients whose spend pattern across categories is atypical) rather than on any single metric.
- **API / JSON representation:** action type "UserDefinedAction" ("Data Science Model", Data Science category); numeric columns + chi-square quantile in settings.
- **Config options:** Select 2+ numeric columns; Chi-square quantile cutoff (0–1, typically 0.95–0.99); Output column name (default "outlier").
- **Gotchas:** Truly multivariate needs 2+ numeric columns. Output column is 0 (not outlier) / 1 (outlier).
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753

#### Forecasting tile (ARIMA, legacy Data Science)
*Category: Data Science*

- **What it does:** Time-series forecast using ARIMA (Auto-Regressive Integrated Moving-Average). Produces future values with lower/upper prediction bands.
- **When to use:** Univariate time-series forecast (daily revenue etc.) built entirely inside a DataFlow when you want ARIMA specifically and control over history/seasonality.
- **API / JSON representation:** action type "UserDefinedAction" ("Data Science Model", Data Science category); date column, target column, band, horizon, seasonality in settings.
- **Config options:** Date/time column; numeric column to forecast; Prediction band width (default 95%); Number of dates to forecast; number of historical rows to use; Seasonal frequency (observations per period). Output column names: "prediction", "prediction lower", "prediction upper" (all editable).
- **Gotchas:** Requires exactly one date column + one numeric column. Distinct from the newer AI Forecasting tile (below). Legacy tile availability gating applies.
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753

#### Classification tile (legacy Data Science: Naive Bayes / Random Forest)
*Category: Data Science*

- **What it does:** Supervised classification. Trains on a training DataSet with one categorical target column plus numeric/categorical predictor columns, then predicts the class for each row of a test/prediction DataSet.
- **When to use:** Predict a categorical outcome (churn yes/no, claim catastrophic/not) from labeled historical data, all inside a DataFlow.
- **API / JSON representation:** action type "UserDefinedAction" ("Data Science Model", Data Science category); algorithm, train/test dataset refs, target and predictor columns in settings.
- **Config options:** Training DataSet + optional test/validation DataSet (may be the same); target categorical column; numeric classifier columns; categorical classifier columns; Algorithm (Naive Bayes | Random Forest); Output column name (default "classification").
- **Gotchas:** Requires one categorical target for training and 1+ predictor columns. Domo recommends comparing multiple methods. Availability gating applies.
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753

#### Prediction tile (legacy Data Science regression: Linear Regression / Random Forest)
*Category: Data Science*

- **What it does:** Supervised regression. Trains a model to predict a numeric target column and applies it to a test DataSet, appending predicted numeric values.
- **When to use:** Predict a continuous value (num claims, demand) from numeric/categorical predictors within a DataFlow.
- **API / JSON representation:** action type "UserDefinedAction" ("Data Science Model", Data Science category); algorithm, train/test refs, target, predictors in settings.
- **Config options:** Training + test DataSet; numeric target column; numeric predictor columns (selected first, can be blank); categorical predictor columns; Algorithm (Linear Regression | Random Forest); prediction column name.
- **Gotchas:** Categorical predictors capped at a MAXIMUM of 53 unique categories. Random Forest is an ensemble of weak trees averaged for the prediction. Availability gating applies.
- **Sources:** https://www.domo.com/docs/s/article/360045259294, https://www.domo.com/docs/s/article/360043427753

### Data Science / AI

#### AutoML (training) + AutoML Inference tile
*Category: Data Science / AI*

- **What it does:** AutoML (powered by Amazon SageMaker Autopilot) auto-preps data and launches hundreds of training jobs on a DataSet to find the best classification/regression model; the trained model is then deployed into a DataFlow via the AutoML Inference tile, which appends a prediction to every input row.
- **When to use:** When you want a strong model without hand-coding — train once from the DataSet's AutoML tab, then score new data on every DataFlow refresh.
- **API / JSON representation:** Inference tile action type "MLInferenceAction" (display name "AutoML Inference", category "Data Science"). Training is launched from the DataSet Details > AutoML tab (not an ETL action); deploy via the Model Leaderboard 'Deploy to ETL' button which drops a configured MLInferenceAction on the canvas.
- **Config options:** Training: 'Column to predict' dropdown; Task Type 'Automatic (Recommended)' (auto-detects binary/multiclass/regression). Leaderboard picks a Best Candidate but any candidate can be deployed. Inference tile: input DataSet, prediction column name, output DataSet.
- **Gotchas:** Requires the 'Enable AutoML' grant (train models + run DataFlows containing AutoML Inference). Default for Consumption agreement, else on-demand+paid. The inference input DataSet MUST have the SAME schema (column names + data types) as the training DataSet or the run errors with mismatch details (the target column is optional in the input). Training runs in Domo's private AWS network and can take ~45 min to hours. Prep data first (impute nulls, drop IDs/collinear cols).
- **Sources:** https://www.domo.com/docs/s/article/360048127854, https://www.domo.com/docs/s/article/360045259294

### AI Services

#### AI Model Inference tile
*Category: AI Services*

- **What it does:** Runs inference using a model registered/managed in Domo's AI model management ('Manage AI Models and Projects') against one input DataSet, producing an inferred output DataSet usable across Domo (App Studio, cards, what-if).
- **When to use:** To operationalize a managed/hosted model (including ones deployed from the AI Models page) on refreshing data — a more general model-serving path than AutoML Inference.
- **API / JSON representation:** Action type "ModelInferenceAction" (display name "AI Model Inference", category "AI Services"). Deployable from the AI Models page via Action menu > Deploy to ETL, which opens the canvas with this tile.
- **Config options:** 'Select a Model' (search the model registry); connect exactly one input DataSet; checkbox to include original input columns in output (unchecked = only inferred data); output DataSet. Any model with a CSV input and an output task can be deployed.
- **Gotchas:** Requires the 'Use AI Services' grant. Model schema must match the input DataSet schema or an error displays. Only ONE input DataSet allowed. Magic ETL Preview does NOT work with this tile — you must Save and Run. Starting/stopping the model endpoint elsewhere in Domo affects its availability here.
- **Sources:** https://www.domo.com/docs/s/article/000005741, https://domo-support.domo.com/s/article/000005502, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### Text Generation tile (LLM tile)
*Category: AI Services*

- **What it does:** Applies an LLM row-by-row to a text column using free-text instructions — summarize, categorize, extract, translate, sentiment, etc. Adds a generated column named 'Output'.
- **When to use:** Any per-row qualitative-text processing where you need flexible, instruction-driven LLM output. Use multiple Text Generation tiles for different aspects/columns.
- **API / JSON representation:** Action type "TextGeneration" (display name "Text Generation", category "AI Services"). Prompt/instructions, model, execution mode, temperature, and output schema live in the action settings.
- **Config options:** Choose AI model; Execution Preference (Batch | Non-batch); instructions (be very specific); 'Insert Value' dropdown to reference the text column; optional additional Knowledge; output = structured or unstructured, single column or multiple columns each with name/type/description; Temperature (lower = predictable, higher = creative). Handles <100 rows to >1M rows by auto-picking the processing method.
- **Gotchas:** Requires grants: Execute AutoML, Create AI Service Models, Use AI Services — PLUS 'AI Services enabled' and DataFlow-create ability. AWS limitation: <100 rows auto-switches to non-batch mode. Output column is always literally named 'Output' — rename downstream. Multiple instructions in one tile need a delimiter + Split Columns to parse. Consumption: 1 AI operation per tile + input/output tokens (~300k rows ≈ 4M input / 11k output tokens); each AI Pro operation = 0.01 Domo Consumption credits.
- **Sources:** https://www.domo.com/docs/s/article/000005741, https://www.domo.com/docs/s/article/000005918, https://www.domo.com/product/new-features/ai-text-generation-dataflow-tile-for-magic-etl

#### Sentiment Analysis tile (Beta)
*Category: AI Services*

- **What it does:** Pre-configured LLM tile that classifies each text row as Positive, Negative, Neutral, or Not Applicable. Optionally returns per-topic (targeted) sentiment.
- **When to use:** Fast sentiment on reviews/social/surveys without prompt engineering — easier than the Text Generation tile for this specific task.
- **API / JSON representation:** No distinct action-type string confirmed in the public community parser map (which predates the Beta AI-Services tiles); it is a pre-configured AI Services tile likely sharing the AI-Services text-inference machinery. Treat type as uncertain / verify by exporting a live dataflow.
- **Config options:** Input = Data Column OR Documents (Document Collection ID + File Path); choose AI model; Execution Preference (Batch | Non-batch); additional instructions; Output type = Overall Sentiment (one value) OR Targeted Sentiment (a value per specified topic, e.g. Fit, Durability, Customer Service). Adds one or more sentiment columns.
- **Gotchas:** Grants: Execute AutoML, Create AI Service Models, Use AI Services + AI Services enabled + DataFlow-create. <100 rows -> non-batch (AWS limit). Cannot bring your own model yet (roadmap). Multi-column output requires enabling Targeted Sentiment. 1 AI operation/tile + tokens.
- **Sources:** https://www.domo.com/docs/s/article/000005741, https://www.domo.com/docs/s/article/000005918

#### Classification tile (AI Services, Beta)
*Category: AI Services*

- **What it does:** Pre-configured LLM tile that categorizes data (text, images, or files) into predefined classes. Supports multi-label output.
- **When to use:** Fast LLM classification into your own categories without prompt tuning — easier than the Text Generation tile for classification.
- **API / JSON representation:** No distinct action-type string confirmed in the public community parser map (predates this Beta tile); pre-configured AI Services tile. Verify actual type by exporting a live dataflow's JSON.
- **Config options:** Input = Data Column OR Documents (Document Collection ID + File Path); choose AI model; execution mode; define classes; enable Multi Label for multiple output columns. Adds one or more classification columns.
- **Gotchas:** Same grant set as other AI Services tiles + AI Services enabled. <100 rows -> non-batch. Can't use your own model yet (roadmap). 1 AI operation/tile + tokens. Distinct from the legacy Data-Science 'Classification' (Naive Bayes/Random Forest) tile.
- **Sources:** https://www.domo.com/docs/s/article/000005741, https://www.domo.com/docs/s/article/000005918

#### AI Forecasting tile (Forecasting Universal Model)
*Category: AI Services*

- **What it does:** Time-series forecast using Domo's hosted Forecasting Universal Model — no model building. Predicts future points with configurable frequency, horizon, and seasonality; output is viewable as a Forecasting Chart in Analyzer.
- **When to use:** Modern, low-effort forecasting inside a DataFlow when you want a managed universal model rather than hand-tuning ARIMA.
- **API / JSON representation:** Action type "AIForecasting" (display name "AI Forecasting", category "AI Services"). Model choice + date/value columns + frequency/length/seasonality in settings.
- **Config options:** Select model: Domo ETS Forecasting Universal Model OR Domo ARIMA Forecasting Universal Model. Configuration tab: date column, value column, forecast frequency, forecast length, seasonality period — all per your chosen granularity. Output DataSet.
- **Gotchas:** CRITICAL: the granularity of the data feeding the tile MUST match the granularity selected in the tile config or the DataFlow fails. Distinct from the legacy ARIMA Data-Science Forecasting tile. AI Services grants/enablement apply; consumption-based.
- **Sources:** https://www.domo.com/docs/s/article/000005741, https://www.domo.com/product/new-features/ai-forecasting-universal-model, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### Vector Output tile
*Category: AI Services*

- **What it does:** Generates vector-based assets (e.g. SVG files) from data within a Magic ETL DataFlow using Domo AI.
- **When to use:** When a DataFlow needs to produce generated vector/graphic output rather than tabular enrichment.
- **API / JSON representation:** Action type "MakoVectorOutputAction" (display name "Vector Output"; the community parser maps its category to 'DataSets', though functionally it is an AI Pro capability).
- **Config options:** Output configuration for the vector asset (e.g. SVG); model/prompt-driven. (Detailed config fields not documented publicly.)
- **Gotchas:** AI Pro capability — consumption is one or more operations plus tokens based on output complexity (0.01 credits per operation). Sparsely documented; verify config by exporting a live dataflow.
- **Sources:** https://www.domo.com/docs/s/article/000005918, https://raw.githubusercontent.com/brycewc/domo-toolkit/9918b10aaeeb490a1c78346c6cdb799cdb91a413/src/services/dataflowParser.js

#### Domo.AI grants, AI Service Layer & consumption model (cross-cutting)
*Category: AI Services*

- **What it does:** The permission and billing layer every AI/ML tile depends on. Governs which roles can train/serve models and how AI usage is metered.
- **When to use:** Read before authoring ANY AI/ML dataflow — missing grants or an unenabled AI Services flag cause the tile to be unavailable or the run to fail.
- **API / JSON representation:** Not a tile; role grants + account enablement. Relevant grants: 'Use AI Services', 'Execute AutoML', 'Create AI Service Models' (AI Services tiles need all three plus AI Services enabled); 'Enable AutoML' (AutoML train + inference). Models managed on the 'Manage AI Models and Projects' page (article 000005502) feed the AI Model Inference tile.
- **Config options:** AI model selection is exposed per-tile (Text Generation / Sentiment / Classification / AI Model Inference / AI Forecasting each have a model picker). Execution Preference Batch vs Non-batch trades latency/cost (batch cheaper, async; non-batch consistent, forced under 100 rows).
- **Gotchas:** Domo AI Pro pricing: every AI Pro operation = 0.01 Domo Consumption credits, plus model token usage (input+output). Data-science and scripting tiles are default only on the Domo Consumption agreement; non-consumption customers get them on-demand and paid, sometimes after required training. Batch mode is unavailable under 100 rows due to an AWS limitation.
- **Sources:** https://www.domo.com/docs/s/article/000005918, https://www.domo.com/docs/s/article/000005741, https://domo-support.domo.com/s/article/000005502

**Open questions / not fully verified:**

- Do the Beta AI Services 'Sentiment Analysis' and 'Classification' tiles have their own dataflow action 'type' strings, or are they pre-configured variants of an existing type (e.g. TextGeneration / ModelInferenceAction)? The community domo-toolkit parser map (the best public source of type strings) lists TextGeneration, AIForecasting, ModelInferenceAction, MLInferenceAction, MakoVectorOutputAction, UserDefinedAction, PythonEngineAction, REngineAction — but NOT Sentiment/Classification, likely because it predates them. Confirm by exporting a live dataflow's JSON (GET dataflow definition / CLI list-dataflow).
- Exact JSON settings/config keys inside UserDefinedAction ('Data Science Model') that select the algorithm (K-means vs K-medians, SD vs MAD, Naive Bayes vs Random Forest) and parameters (K, thresholds, chi-square quantile, forecast horizon) are not publicly documented — must be reverse-engineered from an exported dataflow.
- Exact settings field names for TextGeneration (prompt, model id, temperature, output schema), AIForecasting (model id, frequency, seasonality), and MakoVectorOutputAction are not in public docs; export a real dataflow to capture them.
- The concrete list of selectable AI models (which foundation models/LLMs) in the per-tile model pickers is not enumerated in the docs read.
- There is no dedicated 'Statistics' tile in Magic ETL Data Science; descriptive statistics come from aggregate/window tiles or from Python/R scripting — confirm no separate statistics tile exists in the current build.
