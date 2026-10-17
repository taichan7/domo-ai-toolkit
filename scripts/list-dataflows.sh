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
domo_require curl

FILTER="${1:-all}"
# 引数は all / failed のみ受け付ける（TK-026）。これで (a) 任意値を Python ソースへ
# 補間する脆弱さを断ち、(b) 'failures' のようなタイポが黙って all に化けて「失敗だけ」と
# 誤認させる事故を防ぐ。
if [[ "$FILTER" != "all" && "$FILTER" != "failed" ]]; then
  echo "usage: list-dataflows.sh [all|failed]" >&2
  exit 2
fi

PYTHON_BIN="$(domo_find_python)"

RESPONSE=$(curl -sS --max-time 30 "${DOMO_CURL_AUTH_ARGS[@]}" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows") || domo_neterr
echo "$RESPONSE" | "$PYTHON_BIN" -c "
import json, sys, unicodedata
# 全角(W/F)は端末で2桁ぶん占めるため表示幅でパディング/切り詰めする（TK-007）。
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

print('{}  {}  {}  {}  {}'.format(_pad('ID',8), _pad('NAME',60), _pad('STATE',10), _pad('FAILED',10), 'LAST_ERROR'))
print('-' * 120)

for f in flows:
    le = f.get('lastExecution', {}) or {}
    failed = le.get('failed', False)
    if filter_mode == 'failed' and not failed:
        continue
    errors = le.get('errors', []) or []
    last_err = errors[0].get('code', '') if errors else ''
    print('{}  {}  {}  {}  {}'.format(
        _pad(f.get('id',''), 8),
        _pad(f.get('name','') or '', 60),
        _pad(f.get('runState','') or '', 10),
        _pad('YES' if failed else 'no', 10),
        last_err,
    ))

print()
total = len(flows)
failed_count = sum(1 for f in flows if (f.get('lastExecution') or {}).get('failed'))
print(f'Total: {total} dataflows, {failed_count} failed.')
"
