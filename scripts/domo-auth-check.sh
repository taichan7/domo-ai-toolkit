#!/usr/bin/env bash

set -euo pipefail

if [[ -n "${INSTANCE:-}" && -n "${DOMO_TOKEN:-}" ]]; then
  echo "Domo auth detected: INSTANCE + DOMO_TOKEN"
  exit 0
fi

if [[ -n "${INSTANCE:-}" && -n "${SID:-}" ]]; then
  echo "Domo auth detected: INSTANCE + SID"
  exit 0
fi

if command -v domo >/dev/null 2>&1; then
  echo "Domo CLI detected. Run 'domo whoami' or 'domo login' for the target instance."
  exit 0
fi

echo "No Domo auth detected."
echo "Set INSTANCE + DOMO_TOKEN, set INSTANCE + SID, or install/login with the Domo CLI."
exit 1
