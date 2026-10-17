#!/usr/bin/env bash
# query-dataset.sh — Run a SQL query against a Domo dataset.
#
# Usage:
#   bash scripts/query-dataset.sh <datasetId> "SELECT * FROM table LIMIT 10"
#
# Examples:
#   bash scripts/query-dataset.sh e39af6f5-fa2f-5f62-8a3a-048a008f25dc "SELECT * FROM table LIMIT 5"
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
domo_require curl

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

RESPONSE=$(curl -sS --max-time 30 -X POST \
  "${DOMO_CURL_AUTH_ARGS[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"sql\": $ESCAPED_SQL}" \
  "https://$INSTANCE/api/query/v1/execute/$DATASET_ID") || domo_neterr
echo "$RESPONSE" | "$PYTHON_BIN" -c "
import json, sys, unicodedata
# 全角(W/F)は端末で2桁ぶん占める。len() ではなく表示幅で列幅計算・パディングしないと
# 日本語を含む列が右へずれて桁が揃わない（TK-007）。
def _dw(s): return sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in str(s))
def _pad(s, n):
    s=str(s)
    if _dw(s)>n:
        out=''
        for c in s:
            if _dw(out)+_dw(c)>n-1: break
            out+=c
        s=out+'…'
    return s+' '*max(0,n-_dw(s))

resp = json.load(sys.stdin)
cols = resp.get('columns', [])
rows = resp.get('rows', [])

if not cols:
    print('No columns returned. Raw response:')
    print(json.dumps(resp, indent=2)[:1000])
    sys.exit(0)

# Compute column widths by display width (全角=2桁)
widths = [max(_dw(c), max((_dw(r[i]) for r in rows), default=0)) for i, c in enumerate(cols)]
widths = [min(w, 40) for w in widths]

# Print header（セパレータは表示幅ぶんのハイフン＝各桁1列で一致）
print('  '.join(_pad(c, widths[i]) for i, c in enumerate(cols)))
print('  '.join('-' * w for w in widths))

# Print rows
for r in rows:
    print('  '.join(_pad(r[i], widths[i]) for i in range(len(cols))))

print()
print(f'{len(rows)} row(s).')
"
