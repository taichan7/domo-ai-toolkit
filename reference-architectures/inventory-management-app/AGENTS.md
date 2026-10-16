# Inventory reference app — agent contract

Read [README.md](README.md), [docs/ai-rebuild-runbook.md](docs/ai-rebuild-runbook.md)
and [docs/distribution-readiness.md](docs/distribution-readiness.md) first.
The rebuild runbook is the single deployment procedure; this file contains only
project-specific invariants. Follow the enclosing repository's current user
instructions and authorization policy.

## Deployment

- Require explicit `DOMO_INSTANCE` (or `INSTANCE`); never infer a maintenance target.
- Use `INVENTORY_SANDBOX_SUFFIX` for each hands-on copy. Shared base names require
  deliberate `INVENTORY_ALLOW_PRODUCTION=1` and explicit `DOMO_INSTANCE`.
- The provisioner discovers/creates AppDB, CE, DataFlow, notification Workflow and
  App Studio by name. Do not ask the user to hand-create assets or paste their IDs.
- Provision, synchronize the manifest, publish both Pro Code bundles, embed, then
  verify, following the runbook's gates. Do not cancel an already-running DataFlow.
- `domo-assets.json` is generated local state for the selected instance. It is
  ignored by Git, is not a distribution input and must not be copied between customers.
- Public manifests have no design ID or tenant bindings. Never publish before
  provisioning and `sync-manifest`.
- IDs and versions come from the target instance and deployed manifests. Historical
  docs and snapshots are not live verification.

## Invariants

- AppDB standard synchronization owns data movement. Never write its mirror DataSet.
- Preserve `inventory_api`, existing operations, manifest aliases, AppDB names and
  the six private service helpers.
- Transactions are append-only; corrections use compensating IN/OUT entries.
- Enforce admin operations in CE using execution identity, not client role claims.
- Keep confirmation/cancellation and duplicate submission guards at mutation boundaries.
- Keep frontend HTML escaping and the vendored runtimes with license notices.
- CE resolves the latest active notification Workflow; frontend must not pin its
  runtime execution to a stale host trigger or accept arbitrary server start targets.
- Never use App Studio `interaction: DISABLED`; it disables desktop clicks too.
- Preserve explicit staging paths; do not use `git add -A` or `git add -a` here.

## Verification

Run the single canonical local test sequence in
[docs/test-results.md](docs/test-results.md#自動テストローカル) §自動テスト（ローカル）
(`pip install` → `node --test` → `node --check` on all `pro-code/*.js` → `unittest`
→ `node dev-guide-app/tests/check.mjs`). Do not duplicate the command list here —
one source prevents the skipped-DataFlow / missing-dev-guide drift that four partial
copies cause.

Deployment completion requires `provision_domo.py verify` returning `ok: true`.
A passing reference test suite does not establish atomic stock reservations,
production authorization, destination email delivery or physical mobile behavior.
Record the exact checks and their limits in a dated handoff.
