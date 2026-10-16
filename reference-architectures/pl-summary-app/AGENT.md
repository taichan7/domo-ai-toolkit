# P/L reference app — agent contract

Read [README.md](README.md), [docs/setup-guide.md](docs/setup-guide.md) and
[docs/distribution-readiness.md](docs/distribution-readiness.md) before editing.
The setup guide is the single deployment runbook; this file contains only
project-specific invariants. Follow the enclosing repository's current user
instructions and authorization policy.

## Deployment

- Require explicit `DOMO_INSTANCE` (or `INSTANCE`); never infer a maintenance target.
- Use `PL_SANDBOX_SUFFIX` for isolated hands-on copies. A deliberate deployment
  under shared base names requires `PL_ALLOW_PRODUCTION=1` on every instance.
- Provision data, synchronize its aliases, provision/release Workflows and CE,
  synchronize the CE alias, publish the two Pro Code bundles, then reconcile the
  embedded card context. Use the setup guide's exact sequence.
- Use `provision_workflows.py provision` for fresh instances and sandboxes.
  Maintenance commands resolve existing models by name or explicit environment
  IDs. Legacy deletion additionally requires explicit `PL_WF03_MODEL_ID`.
- `domo-assets.json`, `sandbox-*/`, credentials and session files are local state.
  Never commit or distribute them. Public manifests start unbound; do not publish
  before provisioning and `sync-manifest`.
- Live IDs/versions come from the selected instance and manifests after deployment.
  Snapshot filenames and documentation are not an asset registry.

## Invariants

- Preserve aliases `summary`, `detail`, `trend`, `dept`, `plReportApi`, collection
  name, `report_type`, `doc_key`, and public `pl_report_api(operation, request)`.
- Save creates first, then deletes only strictly older server-timestamped reports
  of the same `doc_key`. Cleanup failure must not turn a successful save into a
  retry that duplicates reports.
- Treat AI/AppDB HTML as untrusted. Keep inert parsing and the rendering allowlist.
- Manual generation runs all stores plus company; the store selector is browsing
  scope. Keep confirmation, cancellation, duplicate-start and uncertain-start guards.
- The operator who runs the update is also emailed the company report: the FE resolves
  their address (People API) and passes `executor_email` into `start`; the CE validates
  it (strict single-address allowlist) and threads it to the Workflow, which places it on
  the company `Send Email` `recipientEmails` (scalar) alongside the configured
  `personRecipients`. It is optional and runtime-only — never persist, log, or bake it in,
  and an unresolved/invalid address must not block the run or the team send. Match the AI
  prompt's exact-shape rule for `recipientEmails` (list vs text) to avoid the 2.1.17+ send
  regression; verify by actual receipt, not COMPLETED status. The recipient is
  caller-supplied and NOT server-verified (same posture as inventory-management-app) — for
  sensitive real data, add server-side caller-binding or restrict who can run the update.
- Resolve latest active parent in CE. Do not restore a parent TIMER schedule.
  Parent SUB_FLOW pins must follow a child release; pacing timers remain.
- Retain the quiet enji UI, chart drill paths and instance-relative progress route.
- Keep runtime dependencies vendored with their license notices.
- Coordinate-only DataFlow changes must preserve logic and never trigger a RUN.
- Retain `appdb_maintenance.py` and legacy deployment entrypoints for compatibility;
  prefer current provisioners. Do not present legacy migration as first-time setup.

## Verification

```bash
python3 -m unittest discover -s tests
node --test tests/test_*.js
node dev-guide-app/tests/check.mjs
```

Live verification: `provision_domo.py verify` and Workflow verification after
provisioning. Local tests do not establish destination grants, email delivery,
physical mobile behavior or production readiness. Record exactly what was tested.
