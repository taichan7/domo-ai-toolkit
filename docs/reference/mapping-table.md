# Mapping Table Reference

Shared conventions for the mapping table that every clone run produces. The table is the single source of truth for "what becomes what" across instances.

## Where it lives

- **In-memory during the run** — the skill builds it as it inventories references.
- **On disk for the run** — written to `/tmp/clone-<source-obj-short>-<YYYYMMDD-HHMMSS>.tsv` after auto-resolution and before user confirmation.
- **Surfaced to user** — printed in the chat as a Markdown table for review.

## Schema

TSV columns, in order:

| # | Column | Required | Notes |
|---|--------|----------|-------|
| 1 | `kind` | yes | one of `dataset`, `card`, `page`, `workflow`, `sub_workflow`, `beast_mode`, `variable`, `env_var` |
| 2 | `alias` | yes | source-side handle: manifest alias, action input name, card title, env var name |
| 3 | `source_id` | yes | source instance ID; for env vars use `env:<name>` |
| 4 | `source_name` | yes | source display name |
| 5 | `target_id` | yes-by-resolution | target ID, `—` if unresolved, `(recreate)` if a fresh create is required, `(redact)` for secrets |
| 6 | `target_name` | conditional | target display name when target_id is resolved |
| 7 | `confidence` | yes | `high` / `medium` / `low` / `ambiguous` / `missing` / `n/a` |
| 8 | `notes` | yes | short reason for the confidence rating; manual-task hint if missing |

## Kind-specific rules

### `dataset`

- Resolution is driven by [dataset-bridging.md](dataset-bridging.md).
- `confidence = high` only when name match OR signature == 1.0.
- `missing` is fatal — abort the run.

### `card`

- Cards always recreate. `target_id = (recreate)`, `confidence = n/a`.
- The card's dataset binding is a separate `dataset` row (which must resolve first).
- Beast modes used by the card become `beast_mode` rows.

### `page`

- Pages always create new on target. `target_id = (recreate)`, `confidence = n/a`.
- The user can also map to an existing target page if they want to add cards to a page they already have. Prompt them.

### `workflow` (top-level, the object being cloned)

- The workflow itself doesn't appear in the mapping table — it's the subject of the run.

### `sub_workflow` (referenced by the workflow being cloned)

- Resolve by name on target.
- `missing` is fatal unless the user chooses to also clone the sub-workflow (recursive — out of scope for v1; emit manual task).

### `beast_mode`

- Beast modes that reference dataset-specific columns are fragile after dataset bridging.
- If the target dataset has all columns referenced in the formula → `high`, transferable.
- If any referenced column is missing → `missing`, emit a manual task with the formula and the missing columns.

### `variable`

- App Studio page variables. Recreate on target. `target_id = (recreate)`, `confidence = n/a`.
- If a variable's default value references a specific dataset row (rare), flag it for user review.

### `env_var` (workflow environment variables)

- Name-based; no UUID involved.
- If the var name matches `/(?i)(secret|password|token|key|credential|apikey|auth|bearer|private)/`, set `target_id = (redact)` and `confidence = n/a`, with a manual-task note to re-enter on target.
- Otherwise transfer the value as-is.

## Confidence rubric

| Label | When |
|-------|------|
| `high` | Exact name match AND signature ≥ 0.85, OR signature == 1.0 |
| `medium` | One of name/signature is exact, the other is partial |
| `low` | Weak match on both, but still plausible |
| `ambiguous` | Multiple plausible candidates; user must choose |
| `missing` | No plausible candidate |
| `n/a` | Resolution doesn't apply (e.g., always-recreate kinds) |

## Output formats

### TSV (persisted)

```
kind	alias	source_id	source_name	target_id	target_name	confidence	notes
dataset	communities	d14df439-…	Communities	a7c2bb01-…	Communities (prod)	high	name match
dataset	accounts	ae43b0f3-…	Accounts	—	—	missing	MANUAL: create on target first
card	kpi_burnrate	card-456	Burn Rate KPI	(recreate)	—	n/a	recreate via card-creation skill
env_var	—	env:SECRET_API_KEY	SECRET_API_KEY	(redact)	—	n/a	MANUAL: re-enter on target
```

### Markdown (for chat)

```
| kind    | alias         | source_id    | source_name        | target_id    | target_name        | confidence | notes                          |
|---------|---------------|--------------|--------------------|--------------|--------------------|------------|--------------------------------|
| dataset | communities   | d14df439-…   | Communities        | a7c2bb01-…   | Communities (prod) | high       | name match                     |
| dataset | accounts      | ae43b0f3-…   | Accounts           | —            | —                  | missing    | MANUAL: create on target first |
| card    | kpi_burnrate  | card-456     | Burn Rate KPI      | (recreate)   | —                  | n/a        | recreate via card-creation     |
| env_var | —             | env:SECRET…  | SECRET_API_KEY     | (redact)     | —                  | n/a        | MANUAL: re-enter on target     |
```

## User overrides

The TSV is editable. On re-run, the skill reads the existing TSV first and treats any row where the user has filled in `target_id` as authoritative — even if auto-resolution would have produced a different answer. This lets the user pin a specific mapping that name/signature search wouldn't catch (e.g., a dataset that's been renamed and re-columned but is semantically the right one).

Override syntax (simpler form for quick fixes from the command line):

```bash
echo "communities=a7c2bb01-..." >> /tmp/clone-<run-id>.mapping
echo "accounts=bb44eedd-..."    >> /tmp/clone-<run-id>.mapping
```

The skill applies these on top of the TSV; mappings file wins on conflict.

## Abort rules

Abort the run before any write to target if any of:

- Any `dataset` row is `missing`.
- Any `dataset` row is `ambiguous` and user did not pick.
- Any `sub_workflow` row is `missing`.
- Any `beast_mode` row is `missing` and the user has not explicitly chosen to drop the beast mode.

`env_var` redactions and `card`/`page`/`variable` recreations are not abort conditions — they're expected.
