# Distribution readiness

[日本語](distribution-readiness.ja.md)

This is a deployable teaching reference, with synthetic seed data. Distribution
does not certify it as a production warehouse system or a multi-tenant service.
Deploy an independent stack in each customer's Domo instance; do not share a
maintainer's deployment state or credentials.

## Source distribution contract

- Use the current public toolkit source checkout.
- Distributed manifests omit design IDs and leave tenant bindings empty. Run
  provisioning and `sync-manifest` before publishing either bundle.
- Snapshot UUIDs are illustrative, consistently replaced identifiers. Snapshot
  metadata is not a target-instance registry. Domo shared utility package IDs
  retain their platform meaning.
- `domo-assets.json`, sandbox state, credentials, session files, caches and raw
  exports are excluded even if accidentally added to version control.
- Require an explicit Domo instance. Authenticated provisioning rejects external
  origins and redirects. Use a name tag for hands-on copies; deliberately shared
  base names require `INVENTORY_ALLOW_PRODUCTION=1`.
- Keep vendor license notices. Each bundle is intentionally self-contained.

## Validation scope

Offline tests cover service validation, admin authorization boundaries, duplicate
request handling, frontend escaping, confirmation/cancellation, QR helpers,
provisioning and sandbox isolation. They run without a maintainer's local state.

On the destination, run the rebuild runbook and require `verify` to report
`ok: true`. Verify intended users/groups and AppDB/DataSet/card access, notification
recipient and actual delivery, AI feature availability and costs, expected data
volumes, and real mobile camera permission/QR behavior. Do not use broad admin
credentials in the browser.

## Production limits

AppDB balance projection, request-id lookup and transaction creation are separate
operations. The implementation does not provide an atomic reservation or a
distributed lock: concurrent requests may observe the same pre-update state.
For concurrent production stock control, validate or replace that write path
with a transactional system and reconcile projections from the append-only ledger.

The app collection is shared among its authorized users. A name tag separates
deployments; it does not supply row-level authorization inside one deployment.
Define destination sharing/PDP and retention rules before loading real data.
DataSet PDP does not authorize AppDB records. If users must see different stock
records, add server-side record authorization or isolate their collections.

Keep seed/demo operations away from live stock. Test recovery and backup using
disposable copies. AI commentary is supplementary to deterministic stock events.
