#!/usr/bin/env bash
# list-dataflows.sh — List all Magic ETL dataflows in the instance.
#
# Usage:
#   bash scripts/list-dataflows.sh
#   bash scripts/list-dataflows.sh failed   # only print dataflows whose last execution failed
#
# The list endpoint returns ALL dataflows in one response, no pagination needed.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
domo_load_auth

FILTER="${1:-all}"

PYTHON_BIN="$(domo_find_python)"

curl -s "${DOMO_CURL_AUTH_ARGS[@]}" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows" \
  | "$PYTHON_BIN" -c "
import json, sys

flows = json.load(sys.stdin)
# /dataflows は成功時に配列を返すが、認証切れ/エラー時はエラーオブジェクト（dict）を返す。
# dict をそのまま `for f in flows` すると各キー（文字列）を反復し、直後の f.get(...) が
# 'str' object has no attribute 'get' で落ちる。診断ツールで SID 失効は最頻の失敗なので、
# 配列でなければ graceful に生応答を見せて終える（diagnose-etls.sh と同じ契約）。
if not isinstance(flows, list):
    print('Unexpected response — not a dataflow list (auth expired, or error). Raw response:')
    print(json.dumps(flows, indent=2)[:1000] if isinstance(flows, (dict, list)) else str(flows)[:1000])
    sys.exit(0)
filter_mode = '$FILTER'

print('{:<8}  {:<60}  {:<10}  {:<10}  {}'.format('ID', 'NAME', 'STATE', 'FAILED', 'LAST_ERROR'))
print('-' * 120)

for f in flows:
    le = f.get('lastExecution', {}) or {}
    failed = le.get('failed', False)
    if filter_mode == 'failed' and not failed:
        continue
    errors = le.get('errors', []) or []
    last_err = errors[0].get('code', '') if errors else ''
    print('{:<8}  {:<60}  {:<10}  {:<10}  {}'.format(
        str(f.get('id','')),
        (f.get('name','') or '')[:60],
        (f.get('runState','') or '')[:10],
        'YES' if failed else 'no',
        last_err,
    ))

print()
total = len(flows)
failed_count = sum(1 for f in flows if (f.get('lastExecution') or {}).get('failed'))
print(f'Total: {total} dataflows, {failed_count} failed.')
"
