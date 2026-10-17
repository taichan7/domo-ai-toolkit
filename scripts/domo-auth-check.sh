#!/usr/bin/env bash
# domo-auth-check.sh — Report whether the kit's data scripts can authenticate.
# Its verdict must match what the real scripts (list-datasets.sh etc.) accept.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"   # DOMO_SESSION_FILE 等を共有（検出ロジックを一本化）

if [[ -n "${INSTANCE:-}" && -n "${DOMO_TOKEN:-}" ]]; then
  echo "Domo auth detected: INSTANCE + DOMO_TOKEN (environment)"
  exit 0
fi

if [[ -n "${INSTANCE:-}" && -n "${SID:-}" ]]; then
  echo "Domo auth detected: INSTANCE + SID (environment)"
  exit 0
fi

# authenticate.sh が書くセッションファイル（.sid）。list-datasets/query-dataset などは
# common.sh の domo_load_auth 経由でこれを実際に消費する。存在すれば認証済みと判定する（TK-006）。
# これが無いと、正しく authenticate.sh を実行したのに（domo CLI が PATH に無い環境で）
# 「No auth detected」と誤判定していた。
if [[ -s "$DOMO_SESSION_FILE" ]]; then
  echo "Domo auth detected: session file ($DOMO_SESSION_FILE, written by authenticate.sh)"
  exit 0
fi

if command -v domo >/dev/null 2>&1; then
  echo "Domo CLI detected. Run 'domo whoami' or 'domo login' for the target instance."
  exit 0
fi

echo "No Domo auth detected."
echo "First try:  bash scripts/authenticate.sh your-company.domo.com"
echo "Or set INSTANCE + DOMO_TOKEN, set INSTANCE + SID, or install/login with the Domo CLI."
exit 1
