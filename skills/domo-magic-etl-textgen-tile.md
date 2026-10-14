# Domo Magic ETL — Text Generation tile: column bindings (alias trap)

Use when authoring or repairing a **Text Generation (TextGeneration) tile** in a Magic ETL DataFlow
via API/JSON (`build_*.py`), or when a tile shows `?` badges in the prompt editor.

## The trap (learned 2026-10-07, reference-app)

A Text Generation tile JSON has `prompt` (template) + `parameters` (map). Two authoring styles exist:

| Style | prompt | parameters | UI rendering |
|---|---|---|---|
| **UI-created / proven** | `{{列名}}` | `{ "列名": "列名" }` | typed chip (123/ABC badge) — verified column |
| **Alias mapping (trap)** | `{{english_alias}}` | `{ "english_alias": "列名" }` | `?` badge — the editor cannot resolve an alias to a column |

- The runtime **does** substitute aliases (observed outputs contained real values, 0 placeholder leaks),
  but the editor cannot visually verify them, so operators cannot audit the tile. Treat alias-style
  authoring as a defect even when the run succeeds: it is unverifiable and one bad mapping away from
  silently feeding empty values to the model.
- Correct form = the one the UI writes when you use **値の挿入 (Insert Value)**: placeholder name IS the
  column name. Official docs: "Use the Insert Value dropdown to choose the column".
- **The `?` badge can be transient.** After a JSON PUT, the open editor may keep showing `?` for chips
  until the tile/editor is reloaded (the schema is re-resolved then). Confirm by reloading before
  concluding the binding is broken; verified case: both tiles showed typed chips after reload with
  `{列名: 列名}`. Judge the binding by the JSON + schema-walk test, not by the first screenshot.
- Also set `"executionPreference": "BATCH"` for high-volume inputs (the UI sets BATCH; non-batch is
  forced under 100 rows).


## Required verification (do not skip)

For every `TextGeneration` action in the built flow:

1. `parameters` is `{column: column}` for every entry (no `alias != value`).
2. Every `parameters` value exists in the tile's **input schema**. Reconstruct the schema by walking
   `dependsOn`/`input` through the action graph (LoadFromVault roots seeded with the raw dataset
   columns; ExpressionEvaluator adds `fieldName`; GroupBy = groups + fields; MergeJoin = left + right
   minus `schemaModification2` removals (right side only); SelectValues = rename-or-name; Metadata
   applies rename/remove).
3. Every `{{...}}` placeholder in `prompt` (including lines appended by enrichment modules such as
   `decision_facts.py` / `lbc_enrichment.py`) is a key of `parameters`.
4. Run the flow and confirm `placeholderLeaks == 0` and non-empty AI output in `--verify`.

Regression test: `reference-app/tests/test_textgen_parameters.py` implements this check
against `build_body()` output. Keep it green.

## Repairing a tile corrupted by a manual UI save

A manual save can append experimental chips to the prompt and drop parameters the editor could not
resolve (observed: junk `{{...}}` run appended to the last line, 5 candidate-name params removed).
The builder is the source of truth: re-PUT the full flow definition
(`python3 dataflow/build_ci_dataflow.py --run`) and re-verify; do not hand-merge UI edits.

## Checklist

- [ ] `{列名: 列名}` parameters, `{{列名}}` prompt — no English aliases.
- [ ] `executionPreference: "BATCH"` for >100-row inputs.
- [ ] Schema-walk verifier passes (test above).
- [ ] Run → `--verify`: placeholderLeaks 0, AI text non-empty, generation mode AI.
- [ ] When changing enrichment modules, update their injected prompt lines to the same column-name form.
