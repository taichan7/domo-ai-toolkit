#!/usr/bin/env bash

DOMO_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DOMO_REPO_ROOT="$(cd -- "$DOMO_SCRIPT_DIR/.." && pwd)"
DOMO_SESSION_FILE="${DOMO_SESSION_FILE:-$DOMO_SCRIPT_DIR/.sid}"

domo_find_python() {
  local candidate
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  echo "ERROR: no python executable found on PATH (tried python3, python, py)" >&2
  return 1
}

domo_load_auth() {
  if [[ -n "${DOMO_TOKEN:-}" && -n "${INSTANCE:-}" ]]; then
    DOMO_CURL_AUTH_ARGS=(-H "X-DOMO-Developer-Token: $DOMO_TOKEN")
    return 0
  fi

  if [[ -f "$DOMO_SESSION_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$DOMO_SESSION_FILE"
  elif [[ -f "$DOMO_REPO_ROOT/.sid" ]]; then
    # Compatibility for sessions created before scripts lived under scripts/.
    # shellcheck disable=SC1090
    source "$DOMO_REPO_ROOT/.sid"
  fi

  if [[ -z "${INSTANCE:-}" || -z "${SID:-}" ]]; then
    echo "ERROR: no Domo auth found." >&2
    echo "Run 'bash scripts/authenticate.sh <instance>' from the repo root, or set INSTANCE and DOMO_TOKEN." >&2
    return 1
  fi

  DOMO_CURL_AUTH_ARGS=(-H "X-Domo-Authentication: $SID")
}

# Resolves auth for a Domo MCP toolkit call. Requires INSTANCE and PYTHON_BIN
# to already be set by the caller. Sets MCP_AUTH_ARGS and AUTH_METHOD.
domo_load_mcp_auth() {
  if [[ -n "${DOMO_TOKEN:-}" ]]; then
    MCP_AUTH_ARGS=(-H "X-Domo-Developer-Token: $DOMO_TOKEN")
    AUTH_METHOD="Developer Token"
    return
  fi

  if [[ -n "${SID:-}" ]]; then
    MCP_AUTH_ARGS=(-H "X-Domo-Authentication: $SID")
    AUTH_METHOD="SID environment variable"
    return
  fi

  local config refresh access sid
  config="${DOMO_RYUU_CONFIG:-$HOME/.config/configstore/ryuu/$INSTANCE.json}"
  if [[ -f "$config" ]]; then
    refresh="$($PYTHON_BIN -c 'import json,sys; print(json.load(open(sys.argv[1]))["refreshToken"])' "$config")"
    access="$(curl -fsS --max-time 30 -X POST "https://$INSTANCE/api/oauth2/token" \
      -H 'content-type: application/x-www-form-urlencoded;charset=utf-8' \
      --data-urlencode 'client_id=domo:internal:devstudio' \
      --data-urlencode 'grant_type=refresh_token' \
      --data-urlencode "refresh_token=$refresh" \
      | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    unset refresh
    sid="$(curl -fsS --max-time 30 "https://$INSTANCE/api/oauth2/sid" \
      -H "Authorization: Bearer $access" \
      | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["sid"])')"
    unset access

    MCP_AUTH_ARGS=(-H "X-Domo-Authentication: $sid")
    AUTH_METHOD="temporary SID from local ryuu login"
    unset sid
    return
  fi

  if [[ -f "$DOMO_SESSION_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$DOMO_SESSION_FILE"
    if [[ -n "${SID:-}" ]]; then
      MCP_AUTH_ARGS=(-H "X-Domo-Authentication: $SID")
      AUTH_METHOD="SID session file"
      return
    fi
  fi

  if [[ ! -f "$config" ]]; then
    echo "ERROR: no Domo authentication found for $INSTANCE." >&2
    echo "Set INSTANCE + DOMO_TOKEN, set SID, or run 'domo login' for the instance." >&2
    # `exit` ではなく `return` で失敗を通知する。ここは source される共有ライブラリで、
    # 姉妹関数 domo_find_python / domo_load_auth も return 1 で揃えている。exit だと
    # `if domo_load_mcp_auth` や `domo_load_mcp_auth || fallback` の条件文で握れず、
    # 呼び出し側シェルを問答無用で終了させてしまう（＝ライブラリ関数の非対称・再利用阻害）。
    # 現行の2呼び出し元は set -e 下で素の呼び出しのため、return 1 でも従来どおり中断する。
    return 1
  fi
}
