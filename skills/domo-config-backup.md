# Domo Config Backup Skill

Use this skill whenever you **create or change a Domo-side object** — a Magic ETL DataFlow, a Workflow model, a Dataset, an App Studio page / DataApp, a Code Engine package, a Pro Code app, or an AppDB collection. In the **same increment** as the change, mirror that object's **definition** to a local file so it is committed to git and backed up on GitHub.

This is a **safety skill**. The point is disaster recovery and change traceability, not convenience:

- Domo-side definitions live inside the instance. If the instance breaks, a version is lost, or someone overwrites your work in the UI, the local mirror + git history is the recovery point.
- A committed definition is **diff-able**: you can see exactly what changed between deploys, and roll back to a known-good JSON.
- Guiding rule: **config, not content (設定はコード、データは持ち込まない).** Mirror the *definition* (schema, tile logic, step shapes, layout). Never mirror live row data, previews, or credentials.

## The one rule that makes this safe

Raw Domo exports can embed secrets and PII: developer tokens, SIDs, account/connection credentials, OAuth secrets, PATs, webhook URLs with embedded keys, dataset row previews with personal data, and customer-identifying values. **Committing a raw export can leak all of that.**

So every mirrored file passes a **mandatory sanitization gate before commit**:

1. **Strip / redact secrets** — developer tokens, SIDs, session IDs, account & connection credentials/passwords, OAuth client secrets, PATs, access tokens, webhook URLs that contain keys. Replace with a placeholder (`"REDACTED"`) or remove the field.
2. **Exclude data, not just secrets** — never commit dataset **row data** or previews (PII risk), publish bundles / generated zips, downloaded credential files, `.env*`, `.sid`. Mirror the **schema** (columns + types), not the rows.
3. **Redact customer identity** on customer deployments — company name, user emails, instance host — unless the project is explicitly a generic reference app. (Same principle that keeps customer decks/materials out of git.)
4. **Scan and eyeball** — run `bash ../scripts/check-secrets.sh` and read the diff before committing. Stage **explicit paths only**; never `git add -A` / `.` / `-a`.

If you cannot sanitize a file with confidence, do **not** commit it — note the gap in the handoff instead.

## The other leak: real PII hand-typed into source

The gate above targets **exports/mirrors**. A second, easily-missed leak is **real personal data pasted straight into source** — a demo/test/sample payload a developer filled from a real document while testing (real name, email, receipt/booking contents, real instance GUIDs, a real `*.domo.com` host). These live in manual entry-points, fixtures, and `__main__` / notebook blocks that the test suite never exercises, so they pass both the export-gate and code review unnoticed. Before committing any hand-authored sample payload:

1. **Use synthetic, internally-consistent placeholders**, never real values: RFC-reserved emails (`taro.yamada@example.com`), obvious fake names (`TARO YAMADA`), all-zero / all-one GUIDs (`00000000-…`, `11111111-…`), generic vendor/venue names, round sample amounts — and keep them mutually consistent (dates, nights, totals) so the payload still exercises the real code path.
2. **Mark it synthetic** with a one-line comment that also tells the runtime user to substitute their own values.
3. **Sweep for candidates**, then eyeball — this finds candidates, it does not auto-fix: `git grep -nE '@[a-z0-9.-]+\.(com|co\.jp|net|org)' -- '*.py' '*.js' | grep -vE '@example\.(com|org|net)'`. A *deliberate functional contact* in a doc (e.g. "request a PAT via <person>@company") is not leaked test-PII — leave it. Also scan sample payloads for real-looking person names and non-placeholder GUIDs. Reference: `u2s-doc-summary-app/jupyter-workspace/u2s_extract_classify_normalize.py` `run_jupyter_mode` sample payload (commit a38a5c88).
4. **History caveat** — sanitizing removes the value from HEAD only. If real PII was ever committed, it persists in **git history**; scrubbing history (`git filter-repo` / BFG + force-push) is destructive and outward-facing — flag it for explicit user Go, never do it silently.

## What to mirror, per surface

Endpoints and full round-trip details live in the per-surface skill (linked). This skill is the *backup discipline* that wraps them.

| Surface | Export (GET) | Local mirror path | Keep / drop |
|---|---|---|---|
| Magic ETL DataFlow | `GET /api/dataprocessing/v1/dataflows/{id}` (see `domo-magic-etl.md`) | `<project>/dataflow/dataflow-<id>.json` | Keep tile graph & config. Drop embedded account refs/credentials. |
| Workflow model version | `GET /api/workflow/v1/models/{id}/versions/{ver}` (see `domo-workflow.md`) | `<project>/workflow/<name>-v<ver>.json` | Keep step/gateway shapes. Drop trigger IDs, session IDs, secrets. |
| Dataset | schema only (columns + types) — **not** rows | `<project>/dataset/<name>.schema.json` | Keep column names/types. Drop all row data & previews. |
| App Studio page / DataApp | layout / DataApp definition JSON | `<project>/app-studio/<name>.layout.json` | Keep layout, card refs. Drop instance-only IDs if customer-identifying. |
| Code Engine | `code-engine/asset.json` + function source | already local — keep canonical | Source is the mirror; keep it current with the deployed version. |
| Pro Code app | `pro-code/manifest.json` + bundle source | already local — keep canonical | Preserve manifest aliases; do not commit build zips. |
| AppDB collection | collection name + schema + SETTING/seed docs | `<project>/appdb/<collection>.seed.json` | Content only. Drop the system envelope and any secret in content. |

Prefer editing the existing mirror over creating a new file when a definition already lives locally (keep one canonical copy per object, not many near-duplicates).

## When to do it (fits the loop)

Mirror in the **same increment** as the Domo-side change — a deploy without an updated local mirror is an **incomplete increment**. This dovetails with the autonomous-improvement-loop's "commit & push every increment" and "keep indexes truthful": the local mirror is part of what makes an increment a clean, recoverable stop point. When you bump a DataFlow/Workflow version in Domo, re-export and commit the new definition so the git history mirrors the instance history.

## Validation

Before committing a mirrored definition:

```bash
python3 -m json.tool <project>/<path>.json >/dev/null   # valid JSON
bash ../scripts/check-secrets.sh                          # no secrets/tokens
git diff --staged -- <project>/<path>.json                # eyeball: no data, no credentials, no customer identity
```

- If a surface could not be exported (auth missing, endpoint returned an error), **say so** and commit nothing for it — never commit a partial or empty file that looks like a backup but is not one.
- Record which objects were mirrored (IDs, versions) in the handoff so the next agent knows the local copy is authoritative as of that commit.

## Relationship to the per-surface "never commit exports" rule

`domo-magic-etl.md` and `domo-workflow.md` historically said "never commit full dataflow/workflow JSON exports." That rule exists to stop **secret/PII leakage**, not to forbid backups. Under this skill the rule is precise: **never commit an *unsanitized* export or a publish bundle; a *sanitized* definition mirror IS committed for backup.** When those skills mention exports, defer to this skill's sanitization gate.
