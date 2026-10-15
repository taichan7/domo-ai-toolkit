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
#   4. Saves SID and INSTANCE so subsequent scripts can use them
#
# Output:
#   - Reports success without printing credentials
#   - Writes an owner-only session file for the other scripts

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

domo_validate_instance "$INSTANCE"
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

domo_refresh_sid "$INSTANCE" "$CONFIG"
SID="$DOMO_AUTH_SID"
unset DOMO_AUTH_SID

# Existing files must also be tightened; umask alone only protects new files.
umask 077
touch "$DOMO_SESSION_FILE"
chmod 600 "$DOMO_SESSION_FILE"
printf 'INSTANCE=%q\nSID=%q\n' "$INSTANCE" "$SID" > "$DOMO_SESSION_FILE"
unset SID

echo "Authenticated to $INSTANCE"
echo ""
echo "Session file: $DOMO_SESSION_FILE"
echo "Other scripts can now run, for example: bash scripts/list-datasets.sh"
