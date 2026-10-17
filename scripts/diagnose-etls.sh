#!/usr/bin/env bash
# diagnose-etls.sh — Find failing Magic ETL dataflows and categorize errors.
#
# Usage:
#   bash scripts/diagnose-etls.sh             # summary of all failures
#   bash scripts/diagnose-etls.sh <flowId>    # drill into one failing flow
#
# What it does:
#   - Without args: lists all failed dataflows grouped by error code
#   - With a flow ID: shows the failing tile, the expression/join/script, and a recommended fix

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
domo_load_auth
domo_require curl

PYTHON_BIN="$(domo_find_python)"

FLOW_ID="${1:-}"

if [[ -z "$FLOW_ID" ]]; then
  # Summary mode
  RESPONSE=$(curl -sS --max-time 30 "${DOMO_CURL_AUTH_ARGS[@]}" \
    "https://$INSTANCE/api/dataprocessing/v1/dataflows") || domo_neterr
  echo "$RESPONSE" | "$PYTHON_BIN" -c "
import json, sys
from collections import Counter

flows = json.load(sys.stdin)
# /dataflows は成功時に配列を返すが、認証切れ/エラー時は dict を返す。dict を
# `for f in flows` すると各キー（文字列）を反復し、直後の f.get(...) が AttributeError で
# 落ちる。引数なし（summary）は本ツールの既定呼び出しで、SID 失効時に最も踏みやすい。
# 配列でなければ生応答を見せて graceful に終える（下の drill-down 分岐と同じ契約）。
if not isinstance(flows, list):
    print('Unexpected response — not a dataflow list (auth expired, or error). Raw response:')
    print(json.dumps(flows, indent=2)[:1000] if isinstance(flows, (dict, list)) else str(flows)[:1000])
    sys.exit(0)
failed = [f for f in flows if (f.get('lastExecution') or {}).get('failed')]

if not failed:
    print(f'No failing dataflows ({len(flows)} total).')
    sys.exit(0)

print(f'{len(failed)} failing dataflows (of {len(flows)} total)')
print()

# Group by error code
codes = Counter()
for f in failed:
    errors = (f.get('lastExecution') or {}).get('errors', []) or []
    for e in errors:
        codes[e.get('code', 'UNKNOWN')] += 1

print('Error code summary:')
for code, count in codes.most_common():
    print(f'  {code}: {count}')
print()

print('Failing dataflows:')
print('{:<8}  {:<60}  {:<14}  {}'.format('ID', 'NAME', 'CODE', 'MESSAGE'))
print('-' * 120)
for f in failed:
    errors = (f.get('lastExecution') or {}).get('errors', []) or []
    code = errors[0].get('code', '') if errors else ''
    msg = errors[0].get('localizedMessage', '')[:60] if errors else ''
    print('{:<8}  {:<60}  {:<14}  {}'.format(
        str(f.get('id','')),
        (f.get('name','') or '')[:60],
        code,
        msg,
    ))
print()
print('Drill into a specific flow:  bash scripts/diagnose-etls.sh <ID>')
"
  exit 0
fi

# Drill-down mode
RESPONSE=$(curl -sS --max-time 30 "${DOMO_CURL_AUTH_ARGS[@]}" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$FLOW_ID") || domo_neterr
echo "$RESPONSE" | "$PYTHON_BIN" -c "
import json, sys

df = json.load(sys.stdin)
# 妥当な dataflow 応答は必ず 'id' を持つ。存在しない/権限不足/打ち間違いの flowId では
# Domo はエラーオブジェクト（{'status':404,...} 等）を返すため、df['id'] を素で参照すると
# KeyError のトレースバックで落ちる。診断ツールにとって flowId の打ち間違いは最頻の誤用
# なので、summary モードの空チェック（if not failed: ...）と同じく graceful に落として生
# 応答を見せる（同一スクリプト内の兄弟分岐と契約を揃える）。
if not isinstance(df, dict) or 'id' not in df:
    print('Unexpected response — dataflow not found, or not authorized. Raw response:')
    print(json.dumps(df, indent=2)[:1000] if isinstance(df, (dict, list)) else str(df)[:1000])
    sys.exit(0)
print(f'Dataflow {df[\"id\"]}: {df.get(\"name\", \"?\")}')
print(f'State: {df.get(\"runState\")}  |  Last execution: {(df.get(\"lastExecution\") or {}).get(\"state\")}')
print()

errors = (df.get('lastExecution') or {}).get('errors', []) or []
actions = {a['id']: a for a in df.get('actions', [])}

if not errors:
    print('No errors on the last execution.')
    sys.exit(0)

for i, e in enumerate(errors, 1):
    print(f'--- Error {i} ---')
    print(f'Code: {e.get(\"code\")}')
    print(f'Message: {e.get(\"localizedMessage\")}')
    params = e.get('parameters', {}) or {}
    action_id = params.get('_actionId', '')
    prop_path = params.get('_propertyPath', '')
    tile = actions.get(action_id, {})
    if tile:
        print(f'Tile: \"{tile.get(\"name\", \"?\")}\" (type: {tile.get(\"type\", \"?\")})')
        if prop_path:
            print(f'Property: {prop_path}')
        # Show the actual failing content
        ttype = tile.get('type', '')
        if ttype == 'ExpressionEvaluator':
            idx = int(params.get('_exprIndex', 0))
            exprs = tile.get('expressions', [])
            if idx < len(exprs):
                print(f'Expression:')
                print(exprs[idx].get('expression', ''))
        elif ttype == 'PythonEngineAction':
            print(f'Script (first 500 chars):')
            print((tile.get('script') or '')[:500])
        elif ttype == 'MergeJoin':
            print(f'Keys1: {tile.get(\"keys1\")}')
            print(f'Keys2: {tile.get(\"keys2\")}')
        elif ttype == 'LoadFromVault':
            print(f'Input dataset: {tile.get(\"dataSourceId\")}')
    print()
"
