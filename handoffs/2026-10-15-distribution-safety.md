# 2026-10-15 public distribution safety

## Agent
Codex

## Environment
Local macOS; offline release validation plus authenticated maintenance-instance API verification.
No customer instance deployment, report-generation run or email delivery test.

## Changes
See CHANGELOG v1.1.1. Portable manifests omit design IDs and tenant bindings;
provisioners resolve destination IDs and versions. Resolved registries are excluded.
One release transform sanitizes identifiers, private paths and PNG metadata.
The public CI gate checks state, hosts, bindings, image metadata and content hashes.

P/L saving is bound to one deployment collection. Verify now checks the active
report API and all four outputs. Inventory resolves fresh-instance package and
active Workflow versions. Both clients require an explicit target and prevent
cross-origin credential forwarding. Raw error bodies are suppressed. Local
registries require matching instance and sandbox tags; fresh writes retain that scope.

## Verification
- 444 Python tests and 192 Node tests pass; both guide checks pass.
- Isolated ZIPs: inventory 333 Python / 151 Node; P/L 111 Python / 41 Node.
  No parent workspace, local registry or source-instance bindings needed for tests.
- Release gate, secret scan, relative links/anchors, JSON/Python/JavaScript/shell
  syntax and source synchronization checks pass.
- Live inventory and P/L verification pass. Inventory v2.4.107 (12 assets),
  P/L v0.3.3 (8), guide v0.3.2 (7): downloaded bytes match source.
- P/L CE 1.0.4 accepts its configured collection and rejects a foreign collection
  with validation-only calls. Parent/child releases 1.0.22/1.0.14; zero parent schedules.
- Credential scans include repository history. Generated SHA256 values and a
  synthetic store-period test key were verified false positives. GitHub secret
  scanning and push protection are enabled; open secret alerts were zero.

Inventory trend date injection was reproduced with actual script execution in
local Chrome, fixed at the output boundary and confirmed non-executable afterward.
DataFrame regression dependencies are installed explicitly in CI to avoid silent skips.

## Limits
These are teaching/reference distributions. Read each app's distribution-readiness
documents before production use. Stock reservation is not atomic; selectors/PDP do
not authorize AppDB records. Validate destination permissions, sharing, concurrency,
accounting, features/costs, physical mobile behavior and actual mail delivery.
Fresh-instance integration was not exercised against a second live instance.
Earlier revisions retain reference metadata; use the latest release for distribution.
