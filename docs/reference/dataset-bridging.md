# Dataset Bridging Reference

Detailed algorithm and recipes for resolving source dataset IDs to target dataset IDs without ever copying data.

## Why no dataset copy

Production datasets are populated by connectors, ETL, or upstream systems that already exist on the target instance (or need to be set up there separately — outside this skill's scope). Copying rows across instances would be slow, error-prone, and would create silent drift the moment the upstream system writes again. The target instance must own its own data.

## Inputs

Given a source object (manifest, dataflow JSON, workflow JSON, page JSON), extract every dataset reference. Each reference has a **source UUID** and usually a **human-readable name** (alias, dataSourceName, label).

## Outputs

A populated mapping table row per reference. Every row ends with one of:

- `target_id = <UUID>` and `confidence ∈ {high, medium, low}` → ready to write.
- `target_id = —` and `confidence = ambiguous` → user must pick from candidates.
- `target_id = —` and `confidence = missing` → manual task; abort.

## Algorithm in detail

```
function bridge(source_ref):
    src_meta = GET source dataset schema (name + columns + types)
    candidates = search_target_by_name(src_meta.name, limit=25)

    if candidates is empty:
        candidates = search_target_by_column_signature(src_meta.columns)

    if len(candidates) == 0:
        return (target_id=None, confidence='missing',
                notes=f"No name or signature match. Need columns: {format(src_meta.columns)}")

    if len(candidates) == 1:
        c = candidates[0]
        tgt_meta = GET target dataset schema for c.id
        sig_score = signature_compare(src_meta.columns, tgt_meta.columns)
        confidence = 'high' if sig_score == 1.0 else 'medium' if sig_score > 0.7 else 'low'
        notes = describe(sig_score, name_match=(src_meta.name == tgt_meta.name))
        return (target_id=c.id, confidence=confidence, notes=notes)

    # len(candidates) > 1
    return (target_id=None, confidence='ambiguous',
            notes=f"{len(candidates)} candidates: " + ", ".join(c.name for c in candidates))
```

## Endpoints

### Source: dataset schema

```bash
DOMO_INSTANCE=<source> DOMO_AUTH_MODE=ryuu-session \
  community-domo-cli datasets schema <SOURCE_DATASET_ID>
```

Returns JSON with `name`, `columns[{name, type}]`, `owner`, `rowCount`.

### Target: search by name (verified)

```bash
curl -s -X POST "https://$TARGET_HOST/api/search/v1/query" \
  -H "X-DOMO-Developer-Token: $TARGET_REFRESH" \
  -H "Content-Type: application/json" \
  -d '{"entities":["DATASET"],"query":"<source_name>","count":25}' \
  | jq '.searchObjects[] | {id: .databaseId, name, columnCount, rowCount, dataProviderType, lastUpdated}'
```

Dataset UUID is in `databaseId`. Other useful fields: `dataProviderType` (e.g., `"API"`, `"Salesforce"`), `columnCount`, `rowCount`, `lastUpdated`, `ownedByName`. The `query` field accepts a partial name and is case-insensitive.

### Target: schema for a candidate

```bash
DOMO_INSTANCE=<target> DOMO_AUTH_MODE=ryuu-session \
  community-domo-cli datasets schema <CANDIDATE_ID>
```

### Target: list-all fallback (column signature search)

If name search returns zero candidates, fall back to listing all datasets and computing column signatures:

```bash
DOMO_INSTANCE=<target> community-domo-cli datasets list > /tmp/target-datasets.json
```

Then for each candidate, fetch its schema and compute the signature. (This is expensive — only do it when name search fails.)

## Column-signature comparison

Define the **signature** of a dataset as the sorted list of `(column_name_lowercased, normalized_type)` tuples. Normalize types as:

| Domo type | Normalized |
|-----------|------------|
| STRING, VARCHAR | string |
| LONG, INTEGER, DECIMAL, DOUBLE | number |
| DATE, DATETIME, TIME | datetime |
| BOOLEAN | bool |

**Match score:** `|intersect| / max(|src|, |tgt|)`.

| Score | Meaning | Confidence |
|-------|---------|------------|
| 1.0 | Identical columns + types | high |
| 0.85 – 0.99 | Most columns match, minor drift (renames, extra columns) | medium |
| 0.7 – 0.85 | Substantial overlap, several mismatches | low |
| < 0.7 | Poor match | reject, prompt user |

## Confidence labelling

Combine name match and signature score:

| Name match | Sig score | Confidence | Notes column |
|------------|-----------|------------|--------------|
| Exact | 1.0 | high | name + signature match |
| Exact | 0.85–1.0 | high | name match, minor signature drift |
| Exact | 0.7–0.85 | medium | name match, partial signature |
| Exact | < 0.7 | low | name match only, columns differ |
| Fuzzy (case/space) | 1.0 | high | name normalized, signature match |
| None | 1.0 | medium | column signature only, name differs |
| None | 0.85–1.0 | low | weak signature match, no name |
| None | < 0.85 | missing | no usable match |

## Prompting the user

Only prompt on rows that are **not** `high`. Format the prompt to make resolution fast:

```
Dataset bridging needs your confirmation:

[ambiguous] alias 'communities' (source: d14df439-…, "Communities")
  Candidates on target:
    1. a7c2bb01-… "Communities (prod)" — 38 rows, 12 cols, signature match 1.0
    2. f3d8...    "Communities — Test" — 5 rows, 12 cols, signature match 1.0
  Pick [1/2/skip]:

[low] alias 'accounts' (source: ae43b0f3-…, "Accounts")
  Best candidate: bb44...  "Accounts_v2" — signature 0.78
  Accept? [y/n/list-all]:

[missing] alias 'cash_requests' (source: 9988..., "Cash Requests")
  No candidates found. Columns needed: req_id (string), community_id (string), amount_cents (number), submitted_at (datetime), status (string).
  Cannot proceed — emit manual-task callout? [y/abort]:
```

If the user picks `skip` / `n` / `abort` on any row, abort the run and emit the manual-task block.

## Manual-task templates

### Missing dataset

```
[target instance] Create dataset "<source_name>" with columns:
  <col1> (<type>), <col2> (<type>), ...
Why: <source_object_kind> references it as alias '<alias>'; no plausible match on target.
Verify:
  community-domo-cli datasets list | grep -i "<source_name>"
```

### Ambiguous dataset (user declined to pick)

```
[target instance] Confirm which dataset alias '<alias>' should map to.
Candidates:
  - <id1>  "<name1>"  (<rows>r, <cols>c, signature <score>)
  - <id2>  "<name2>"  (<rows>r, <cols>c, signature <score>)
Decide and re-run with a mapping override:
  echo "<alias>=<chosen_id>" >> /tmp/clone-<run-id>.mapping
```

### Low-confidence match (user declined to accept)

```
[target instance] Validate alias '<alias>' → <target_name>.
Source columns: <list>
Target columns: <list>
If acceptable, accept on re-run. If not, create a new dataset on target.
```

## Persistence

Write the populated mapping table to `/tmp/clone-<source-obj-short>-<YYYYMMDD-HHMMSS>.tsv` (TSV for easy paste-into-spreadsheet). The user can edit this file between runs to lock in overrides:

```
kind	alias	source_id	source_name	target_id	target_name	confidence	notes
dataset	communities	d14df439-…	Communities	a7c2bb01-…	Communities (prod)	high	name match
dataset	accounts	ae43b0f3-…	Accounts	—	—	missing	MANUAL: create on target first
```

On re-run, read this file first; if any row has been edited (target_id filled in by user), trust it and skip the auto-resolution for that alias.

## Edge cases

- **Federated datasets (Databricks ADC)** — name search returns them; treat the same as native datasets. The federation source (cloud integration) on target must already be configured. When the source object is an ADR dataflow, the prereq detector in [SKILL.md Section 7](../../skills/domo-cross-instance-clone.md#section-7--magic-etl-dataflows) checks that the Databricks integration exists AND federates all the same catalog tables the source dataflow references — abort with a manual task if either is missing.
- **AppDB-backed datasets** — they have a UUID and behave like regular datasets for bridging purposes. The AppDB collection itself is a separate object — see `appdb-collection-create` and [SKILL.md Section 5](../../skills/domo-cross-instance-clone.md#section-5--appdb-collections). Note that a collection's auto-mirror dataset (`<collection_name>__APP_DB`) does NOT exist until the collection has at least one document.
- **Dataviews** — have their own IDs and may reference upstream datasets. Bridge the dataview, not its upstream — the dataview definition embeds the upstream IDs on each instance.
- **Renamed datasets** — Domo dataset names are mutable. If signature matches but name differs widely, log as `medium` and surface to user; common during prod migrations.
- **Schema endpoint differences** — prefer `/api/data/v3/datasources/<id>/schema` (works on federated datasets). `/api/query/v1/datasources/<id>/schema` returns 403 for federated datasets even with a valid token.
- **Output datasets from cloned dataflows** — when a target dataflow runs, its outputs are populated immediately at the UUID level (response carries `outputs[].dataSourceId`) but rows aren't loaded until first SUCCESS. Match outputs to source by **dataSourceName**, never by array index — the CREATE response may reorder outputs.
