#!/usr/bin/env bash
# list-datasets.sh — List datasets in the authenticated Domo instance.
#
# Usage:
#   bash scripts/authenticate.sh your-company.domo.com   # do this once
#   bash scripts/list-datasets.sh                        # then this
#   bash scripts/list-datasets.sh 100                    # fetch the first 100
#
# Prints: id, name, type, rowCount, owner

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
domo_load_auth
domo_require curl

MAX="${1:-50}"
OFFSET=0
FETCHED=0

PYTHON_BIN="$(domo_find_python)"

printf "%-40s  %-50s  %-20s  %12s  %-25s\n" "ID" "NAME" "TYPE" "ROWS" "OWNER"
printf "%-40s  %-50s  %-20s  %12s  %-25s\n" "----------------------------------------" "--------------------------------------------------" "--------------------" "------------" "-------------------------"

while (( FETCHED < MAX )); do
  # 今回ページで取る件数は「残り予算（MAX-FETCHED）」と 50 の小さい方＝引数 N を厳密な上限にする（TK-025）。
  PAGELIMIT=$(( (MAX - FETCHED) < 50 ? (MAX - FETCHED) : 50 ))
  RESPONSE=$(curl -sS --max-time 30 "${DOMO_CURL_AUTH_ARGS[@]}" \
    "https://$INSTANCE/api/data/v3/datasources?limit=$PAGELIMIT&offset=$OFFSET") || domo_neterr

  echo "$RESPONSE" | "$PYTHON_BIN" -c "
import json, sys, unicodedata
# 全角(W/F)は端末で2桁ぶん占めるため、len() でなく表示幅でパディング/切り詰めする（TK-007）。
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
data = json.load(sys.stdin)
# 認証切れ/エラー時、/api/data/v3/datasources は 'dataSources' を持たないエラー dict を返す。
# bare な data.get('dataSources', []) だと空リストに化けて '0 datasets' と黙って成功に見え、
# 本当に空のインスタンスと区別できない（＝失効したユーザーが「うちは空」と誤解する）。姉妹の
# list-dataflows.sh / diagnose-etls.sh と契約を揃え、キー不在なら生応答を見せて graceful に終える。
# 'dataSources' が在れば空リストでも正当な 0 件なので、そのまま下のループが空表を出す。
if not isinstance(data, dict) or 'dataSources' not in data:
    print('Unexpected response — not a dataset list (auth expired, or error). Raw response:')
    print(json.dumps(data, indent=2)[:1000] if isinstance(data, (dict, list)) else str(data)[:1000])
    sys.exit(0)
rows = data['dataSources']
for d in rows:
    owner = d.get('owner', {}) or {}
    print('{}  {}  {}  {:>12,}  {}'.format(
        _pad(d.get('id',''), 40),
        _pad(d.get('name','') or '', 50),
        _pad(d.get('type','') or '', 20),
        d.get('rowCount', 0) or 0,
        _pad(owner.get('name','') or '', 25),
    ))
"

  PAGE_COUNT=$(echo "$RESPONSE" | "$PYTHON_BIN" -c "import json,sys; print(len(json.load(sys.stdin).get('dataSources', [])))")
  FETCHED=$((FETCHED + PAGE_COUNT))

  if (( PAGE_COUNT < PAGELIMIT )); then break; fi
  OFFSET=$((OFFSET + PAGE_COUNT))
done

echo ""
echo "Fetched $FETCHED datasets."
