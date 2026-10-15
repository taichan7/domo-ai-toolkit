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

domo_validate_instance() {
  if [[ ! "${1:-}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?\.domo\.com$ ]]; then
    echo "ERROR: specify a Domo instance hostname (example.domo.com), without a URL or path." >&2
    return 1
  fi
}

domo_read_session() {
  local INSTANCE="" SID=""
  # shellcheck disable=SC1090
  source "$1" || return 1
  DOMO_CACHED_INSTANCE="$INSTANCE"
  DOMO_CACHED_SID="$SID"
}

domo_refresh_sid() {
  local instance="$1" config="$2" refresh access sid
  unset DOMO_AUTH_SID
  domo_validate_instance "$instance" || return 1
  refresh="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("refreshToken") or "")' "$config")" || {
    echo "ERROR: cannot read the Domo CLI login. Run 'domo login -i $instance' again." >&2
    return 1
  }
  if [[ -z "$refresh" ]]; then
    echo "ERROR: no refresh token in the Domo CLI login. Run 'domo login -i $instance' again." >&2
    return 1
  fi
  access="$(set -o pipefail; curl -fsS --max-time 30 -X POST "https://$instance/api/oauth2/token" \
    -H 'content-type: application/x-www-form-urlencoded;charset=utf-8' \
    --data-urlencode 'client_id=domo:internal:devstudio' \
    --data-urlencode 'grant_type=refresh_token' \
    --data-urlencode "refresh_token=$refresh" \
    | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("access_token") or "")')" || {
    echo "ERROR: failed to exchange the Domo CLI refresh token." >&2
    return 1
  }
  unset refresh
  if [[ -z "$access" ]]; then
    echo "ERROR: the token exchange returned no access token." >&2
    return 1
  fi
  sid="$(set -o pipefail; curl -fsS --max-time 30 "https://$instance/api/oauth2/sid" \
    -H "Authorization: Bearer $access" \
    | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("sid") or "")')" || {
    echo "ERROR: failed to establish a Domo session." >&2
    return 1
  }
  unset access
  if [[ -z "$sid" ]]; then
    echo "ERROR: the session exchange returned no SID." >&2
    return 1
  fi
  DOMO_AUTH_SID="$sid"
}

domo_load_auth() {
  if [[ -n "${DOMO_TOKEN:-}" && -n "${INSTANCE:-}" ]]; then
    domo_validate_instance "$INSTANCE" || return 1
    DOMO_CURL_AUTH_ARGS=(-H "X-DOMO-Developer-Token: $DOMO_TOKEN")
    return 0
  fi

  if [[ -n "${SID:-}" && -n "${INSTANCE:-}" ]]; then
    domo_validate_instance "$INSTANCE" || return 1
    DOMO_CURL_AUTH_ARGS=(-H "X-Domo-Authentication: $SID")
    return 0
  fi

  local selected="${INSTANCE:-}"
  if [[ -f "$DOMO_SESSION_FILE" ]]; then
    domo_read_session "$DOMO_SESSION_FILE" || return 1
  elif [[ -f "$DOMO_REPO_ROOT/.sid" ]]; then
    # Compatibility for sessions created before scripts lived under scripts/.
    domo_read_session "$DOMO_REPO_ROOT/.sid" || return 1
  fi

  if [[ -n "$selected" && -n "${DOMO_CACHED_INSTANCE:-}" && "$selected" != "$DOMO_CACHED_INSTANCE" ]]; then
    echo "ERROR: cached session belongs to a different instance; authenticate for $selected." >&2
    unset DOMO_CACHED_INSTANCE DOMO_CACHED_SID
    return 1
  fi
  INSTANCE="${selected:-${DOMO_CACHED_INSTANCE:-}}"
  SID="${DOMO_CACHED_SID:-}"
  unset DOMO_CACHED_INSTANCE DOMO_CACHED_SID
  if [[ -z "$INSTANCE" || -z "$SID" ]]; then
    echo "ERROR: no Domo auth found." >&2
    echo "Run 'bash scripts/authenticate.sh <instance>' from the repo root, or set INSTANCE and DOMO_TOKEN." >&2
    return 1
  fi

  domo_validate_instance "$INSTANCE" || return 1
  DOMO_CURL_AUTH_ARGS=(-H "X-Domo-Authentication: $SID")
}

# Resolves auth for a Domo MCP toolkit call. Requires INSTANCE and PYTHON_BIN
# to already be set by the caller. Sets MCP_AUTH_ARGS and AUTH_METHOD.
domo_load_mcp_auth() {
  domo_validate_instance "${INSTANCE:-}" || return 1
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

  local config
  config="${DOMO_RYUU_CONFIG:-$HOME/.config/configstore/ryuu/$INSTANCE.json}"
  if [[ -f "$config" ]]; then
    domo_refresh_sid "$INSTANCE" "$config" || return 1
    MCP_AUTH_ARGS=(-H "X-Domo-Authentication: $DOMO_AUTH_SID")
    AUTH_METHOD="temporary SID from local ryuu login"
    unset DOMO_AUTH_SID
    return
  fi

  if [[ -f "$DOMO_SESSION_FILE" ]]; then
    domo_read_session "$DOMO_SESSION_FILE" || return 1
    if [[ "$DOMO_CACHED_INSTANCE" != "$INSTANCE" ]]; then
      echo "ERROR: cached session belongs to a different instance; authenticate for $INSTANCE." >&2
      unset DOMO_CACHED_INSTANCE DOMO_CACHED_SID
      return 1
    fi
    if [[ -n "$DOMO_CACHED_SID" ]]; then
      MCP_AUTH_ARGS=(-H "X-Domo-Authentication: $DOMO_CACHED_SID")
      AUTH_METHOD="SID session file"
      unset DOMO_CACHED_INSTANCE DOMO_CACHED_SID
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
