#!/usr/bin/env bash
# authenticate.sh — Establish a Domo session ID from a CLI refresh token.
#
# Usage:
#   bash scripts/authenticate.sh your-company.domo.com
#
# Prerequisites:
#   - Domo CLI installed (`npm install -g ryuu`)
#   - `domo login` already run for the target instance
#   - python (or python3) available on PATH
#
# What it does:
#   1. Reads the refresh token saved by `domo login` from the ryuu config
#   2. Exchanges it for an access token via /api/oauth2/token
#   3. Exchanges the access token for a session ID (SID) via /api/oauth2/sid
#   4. Exports SID and INSTANCE so subsequent scripts can use them
#
# Output:
#   - Prints "Authenticated to <instance> — SID=<sid>"
#   - Also writes the SID to scripts/.sid so other scripts can source it

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

INSTANCE="${1:-}"
if [[ -z "$INSTANCE" ]]; then
  echo "Usage: bash scripts/authenticate.sh <instance-domain>"
  echo "Example: bash scripts/authenticate.sh your-company.domo.com"
  exit 1
fi

PYTHON_BIN="$(domo_find_python)"

# Find the ryuu config file (cross-platform)
if [[ -n "${USERPROFILE:-}" ]]; then
  CONFIG="$USERPROFILE/.config/configstore/ryuu/$INSTANCE.json"
else
  CONFIG="$HOME/.config/configstore/ryuu/$INSTANCE.json"
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: no ryuu config for $INSTANCE found at $CONFIG"
  echo "Run 'domo login' against $INSTANCE first."
  exit 1
fi

# .get(...,'') で欠落キーを空文字にする。[] 添字だと KeyError が送出され、
# set -e + pipefail が下のフレンドリなエラーガードより先に raw traceback で
# 中断してしまうため（＝ガードが到達不能＝UX が壊れる）。空文字なら下の
# [[ -z ]] ガードが発火し、ユーザに次の一手を案内できる。
REFRESH_TOKEN=$("$PYTHON_BIN" -c "import json; print(json.load(open(r'$CONFIG')).get('refreshToken',''))")

if [[ -z "$REFRESH_TOKEN" ]]; then
  echo "ERROR: no refreshToken in $CONFIG. Run 'domo login' against $INSTANCE again."
  exit 1
fi

# 1. Exchange refresh token for access token
ACCESS_TOKEN=$(curl -s -X POST "https://$INSTANCE/api/oauth2/token" \
  -H "content-type: application/x-www-form-urlencoded;charset=utf-8" \
  -d "client_id=domo:internal:devstudio&grant_type=refresh_token&refresh_token=$REFRESH_TOKEN" \
  | "$PYTHON_BIN" -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")

if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "ERROR: failed to exchange refresh token for access token. Try 'domo login' again."
  exit 1
fi

# 2. Exchange access token for SID
SID=$(curl -s "https://$INSTANCE/api/oauth2/sid" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | "$PYTHON_BIN" -c "import json,sys; print(json.load(sys.stdin).get('sid',''))")

if [[ -z "$SID" ]]; then
  echo "ERROR: failed to exchange access token for SID."
  exit 1
fi

echo "Authenticated to $INSTANCE — SID=$SID"

# Write to scripts/.sid so other scripts can read it. .sid is in .gitignore.
echo "INSTANCE=$INSTANCE" > "$DOMO_SESSION_FILE"
echo "SID=$SID" >> "$DOMO_SESSION_FILE"

echo ""
echo "Session file: $DOMO_SESSION_FILE"
echo "Other scripts can now run, for example: bash scripts/list-datasets.sh"
