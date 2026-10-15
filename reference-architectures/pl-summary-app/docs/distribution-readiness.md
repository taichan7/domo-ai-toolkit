# Distribution readiness

[日本語](distribution-readiness.ja.md)

This is a deployable teaching reference using synthetic store P/L data. It is
not an accounting close system or a hosted multi-tenant service. Each customer
deploys and verifies an independent stack in their own Domo instance.

## Source distribution contract

- Use the current public toolkit source checkout.
- Manifests omit design IDs and leave tenant bindings empty. Provision data,
  Workflows and CE, synchronize aliases, then publish and reconcile card context.
- Snapshot UUIDs are consistently replaced examples; Domo shared utility package
  IDs retain their platform meaning. `dataflow/2042.json` is a historical filename,
  not the destination DataFlow ID.
- Exclude `domo-assets.json`, sandbox state, credentials, sessions, caches and raw
  customer exports. Keep bundled runtime license notices.
- Require an explicit target and use `PL_SANDBOX_SUFFIX` for hands-on copies.
  Shared base-name writes require `PL_ALLOW_PRODUCTION=1` on every instance.
- Maintenance commands discover models by name or explicit environment IDs.
  Legacy deletion requires an explicit `PL_WF03_MODEL_ID`.

## Validation scope

Offline tests cover save validation and preservation of newer reports, HTML
allowlisting, chart drill paths, manual start/cancellation, provisioning, geometry
and sandbox isolation. A clean checkout must run without local deployment state.

Follow the setup guide on the destination. Verify data and Workflow bindings,
release pins, grants, available AI models/consumption, actual report completeness,
and intended email recipients/delivery. The store selector limits browsing;
manual generation processes all stores and company. No parent schedule is created.

## Production limits

Before loading real financial data, validate accounting levels, double-counting
rules, fiscal periods, budget semantics, currency and organizational sharing/PDP.
The sample's definitions are not automatically correct for another customer's books.
The store selector is a display filter. The AppDB report collection is shared
among authorized app users; DataSet PDP does not secure its records. Add server-side
record authorization or separate collections for restricted store/department access.

Manual-start duplicate prevention is best effort, not a distributed atomic lock.
AppDB creation and older-report cleanup are separate operations; cleanup can be
incomplete and requires monitoring. Preserve backups and test recovery.

AI prose may be wrong and is not a financial approval. Rendering rejects active
HTML; preserve that allowlist. Real mobile/accessibility checks, concurrent use,
load, feature availability and mail delivery require destination verification.
