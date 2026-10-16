# Domo Magic ETL — Text Generation tile: column bindings (alias trap)

Use when authoring or repairing a **Text Generation (TextGeneration) tile** in a Magic ETL DataFlow
via API/JSON (`build_*.py`), when a tile shows `?` badges in the prompt editor, or when investigating
long AI execution times. Read this BEFORE changing a tile, not after a failed full-volume rerun.

## Preserve the required architecture

- An existing AI tile is a required feature unless the user explicitly approves changing it.
  **Never remove, bypass, cap its input population, or replace it with deterministic text merely to
  make a slow flow finish.** A fast run that omits required AI is not a performance fix.
- When an app ships multiple AI tiles (e.g. one per report scope), treat **every** required tile,
  its existing native architecture, and full-volume processing as mandatory unless the user explicitly
  approves a change.
- Roll back a rejected workaround in **all** affected surfaces: live definition, builder, generated
  snapshot, enrichment helpers, tests, frontend, guide and documentation. Definition rollback alone
  does not restore already-published output data; regenerate using the restored architecture.

## The trap (learned 2026-10-07)

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
  until the tile/editor is reloaded or its preview resolves input types. Do NOT assume this explains
  a particular screenshot. Verify the actual upstream schema and require fresh **ABC/123/date**
  badges in both tiles, by permitted browser verification or the user's manual confirmation.
  Persisted JSON/schema checks alone do not prove that the editor's `?` has disappeared.
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

Regression test: if the app ships a parameters test (e.g. `tests/test_textgen_parameters.py`) that
walks `build_body()` output, keep it green.

## Diagnose before an expensive full-volume rerun

1. **Identify the exact known-successful execution**, including start/end times. Read its saved
   design, not just Git or today's builder. The observed internal route is
   `GET /api/dataprocessing/v2/dataflows/{flowId}/versions/{versionId}`.
   Check the response's outer `id`, `timeStamp`, `versionNumber` and `onboardFlowId`; an ID is not
   the displayed version number, and embedded `dataFlow.onboardFlowVersion` may reference an older
   version. Compare both AI objects field-by-field, wiring, engine settings and input/output IDs.
2. Check live `{{column}}` tokens and `{column: column}` bindings, then reconstruct input schemas
   from **actual source schemas**, not synthetic test seeds alone. Unused bindings are not the
   same as unbound prompt tokens; report the distinction instead of deleting fields speculatively.
3. If type resolution is uncertain, use an isolated **native-only preview** up to the AI inputs:
   remove AI/Publish actions from that preview, set source `previewRowLimit`, and publish no outputs.
   Require the actual result schema to contain every bound column with a known type.
4. Exercise the **unchanged AI tiles** with a bounded preview and no Publish actions. Confirm each
   AI action succeeds, output row counts match input, values are substituted, and no `{{...}}`
   placeholders leak. Keep preview rows/private AI text outside Git and stdout.
5. Require fresh typed-chip evidence before declaring the editor issue fixed. A code-equal historic
   design does not establish present UI correctness. If browser verification is unavailable, say so
   and obtain the user's confirmation; do not claim an unobserved visual fix.
6. Once settings are verified and execution is authorized, start **one** full-volume run and monitor
   every terminal state, including **KILLED**. A run-only refresh uses `POST .../executions` with `{}`;
   do not re-PUT a verified definition merely to run it. Respect user stops; do not silently restart.
   Accept only after SUCCESS plus all-output metric, identity and AI-quality audits.

**Evidence discipline:** a `?` screenshot alone proves neither a broken runtime binding nor a
provider-side latency cause. Successful small previews prove substitution on that sample, not
full-volume performance. Distinguish observed facts, hypotheses and unresolved backend causes.

### Evidence discipline, in practice

A tile that succeeded once at full volume — both AI objects identical to the live definition, native
previews resolving every binding with known types, a bounded AI preview producing rows — still does
not, by itself, establish the cause of a *separate* long AI delay. When a run succeeds after a
workaround was rejected, do not rewrite that success as proof that a changed binding caused the earlier
delay; record such a cause as unconfirmed. Require the operator's ABC/123 screenshots of each tile
before authorizing a full-volume rerun.

## Repairing a tile corrupted by a manual UI save

A manual save can append experimental chips to the prompt and drop parameters the editor could not
resolve (observed: junk `{{...}}` run appended to the last line, 5 candidate-name params removed).
The builder is the source of truth: re-PUT the full flow definition
(e.g. `python3 dataflow/build_*.py --run`) and re-verify; do not hand-merge UI edits.

## Checklist

- [ ] `{列名: 列名}` parameters, `{{列名}}` prompt — no English aliases.
- [ ] `executionPreference: "BATCH"` for >100-row inputs.
- [ ] Schema-walk verifier passes (test above).
- [ ] Actual upstream types resolve; both editors show fresh ABC/123/date chips, not `?`.
- [ ] Small unchanged-AI preview passes before any large diagnostic rerun.
- [ ] Required AI tiles, full input population, public schemas and aliases are preserved.
- [ ] Run → `--verify`: placeholderLeaks 0, AI text non-empty, generation mode AI.
- [ ] When changing enrichment modules, update their injected prompt lines to the same column-name form.
