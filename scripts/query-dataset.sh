#!/usr/bin/env bash
# query-dataset.sh — Run a SQL query against a Domo dataset.
#
# Usage:
#   bash scripts/query-dataset.sh <datasetId> "SELECT * FROM table LIMIT 10"
#
# Examples:
#   bash scripts/query-dataset.sh 12345678-1234-1234-1234-123456789abc "SELECT * FROM table LIMIT 5"
#   bash scripts/query-dataset.sh <id> "SELECT \`Column Name\` FROM table WHERE status = 'open'"
#   bash scripts/query-dataset.sh <id> "SELECT * FROM table LIMIT 0"   # schema only
#
# Notes:
#   - The table name is always `table` — it refers to the dataset itself.
#   - Column names with spaces must be backtick-escaped: `Column Name`
#   - LIMIT 0 returns columns only (useful for schema discovery).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
domo_load_auth

DATASET_ID="${1:-}"
SQL="${2:-SELECT * FROM table LIMIT 10}"

if [[ -z "$DATASET_ID" ]]; then
  echo "Usage: bash scripts/query-dataset.sh <datasetId> \"<sql>\""
  echo "Example: bash scripts/query-dataset.sh abc123-... \"SELECT * FROM table LIMIT 5\""
  exit 1
fi

PYTHON_BIN="$(domo_find_python)"

# JSON-escape the SQL safely
ESCAPED_SQL=$("$PYTHON_BIN" -c "import json,sys; print(json.dumps(sys.argv[1]))" "$SQL")

curl -s -X POST \
  "${DOMO_CURL_AUTH_ARGS[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"sql\": $ESCAPED_SQL}" \
  "https://$INSTANCE/api/query/v1/execute/$DATASET_ID" \
  | "$PYTHON_BIN" -c "
import json, sys

resp = json.load(sys.stdin)
cols = resp.get('columns', [])
rows = resp.get('rows', [])

if not cols:
    print('No columns returned. Raw response:')
    print(json.dumps(resp, indent=2)[:1000])
    sys.exit(0)

# Compute column widths
widths = [max(len(str(c)), max((len(str(r[i])) for r in rows), default=0)) for i, c in enumerate(cols)]
widths = [min(w, 40) for w in widths]

# Print header
print('  '.join(c[:widths[i]].ljust(widths[i]) for i, c in enumerate(cols)))
print('  '.join('-' * w for w in widths))

# Print rows
for r in rows:
    print('  '.join(str(r[i])[:widths[i]].ljust(widths[i]) for i in range(len(cols))))

print()
print(f'{len(rows)} row(s).')
"
