#!/usr/bin/env bash
# Read-only connectivity check for a Domo toolkit exposed over Streamable HTTP MCP.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

DEFAULT_ENDPOINT="https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp"
SHOW_SCHEMAS=false
if [[ "${1:-}" == "--show-schemas" ]]; then
  SHOW_SCHEMAS=true
  shift
fi
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [--show-schemas] [endpoint]" >&2
  exit 2
fi

ENDPOINT="${1:-${DOMO_MCP_ENDPOINT:-$DEFAULT_ENDPOINT}}"
PYTHON_BIN="$(domo_find_python)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/domo-mcp-check.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ! "$ENDPOINT" =~ ^https://([^/]+)(/.*)?$ ]]; then
  echo "ERROR: endpoint must be an HTTPS URL: $ENDPOINT" >&2
  exit 2
fi

INSTANCE="${INSTANCE:-${BASH_REMATCH[1]}}"

mcp_post() {
  local label="$1" body="$2"
  local output="$TMP_DIR/$label.body" headers="$TMP_DIR/$label.headers"
  shift 2
  local code
  code="$(curl -sS --max-time 30 -D "$headers" -o "$output" -w '%{http_code}' \
    -X POST "$ENDPOINT" "${MCP_AUTH_ARGS[@]}" "$@" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    --data "$body")"
  printf '%s HTTP %s\n' "$label" "$code"
  if [[ "$code" -lt 200 || "$code" -ge 300 ]]; then
    echo "ERROR: $label failed; response body was intentionally not printed." >&2
    exit 1
  fi
}

domo_load_mcp_auth
echo "Endpoint: $ENDPOINT"
echo "Authentication: $AUTH_METHOD"

mcp_post initialize \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"domokit-connectivity-check","version":"1.0.0"}}}'

SESSION_ID="$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/{gsub("\r",""); sub(/^[^:]+:[[:space:]]*/,""); print}' "$TMP_DIR/initialize.headers" | tail -1)"
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: initialize response did not contain Mcp-Session-Id." >&2
  exit 1
fi

SESSION_ARGS=(-H "Mcp-Session-Id: $SESSION_ID")
mcp_post initialized \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  "${SESSION_ARGS[@]}"
mcp_post tools-list \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  "${SESSION_ARGS[@]}"
mcp_post resources-list \
  '{"jsonrpc":"2.0","id":3,"method":"resources/list","params":{}}' \
  "${SESSION_ARGS[@]}"

"$PYTHON_BIN" - "$TMP_DIR" "$SHOW_SCHEMAS" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
show_schemas = sys.argv[2].lower() == "true"

def read_message(name, message_id=None):
    text = (root / f"{name}.body").read_text(errors="replace")
    messages = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].lstrip(" ")
            if payload.strip():
                messages.append(json.loads(payload))
    if not messages:
        messages = [json.loads(text)]
    if message_id is not None:
        return next((message for message in messages if message.get("id") == message_id), messages[-1])
    return messages[-1]

initialized = read_message("initialize", 1).get("result", {})
server = initialized.get("serverInfo", {})
print(f"Protocol: {initialized.get('protocolVersion', 'unknown')}")
print(f"Server: {server.get('name', 'unknown')} {server.get('version', '')}".rstrip())
print("Capabilities: " + ", ".join(sorted(initialized.get("capabilities", {}))))

tools = read_message("tools-list", 2).get("result", {}).get("tools", [])
print(f"Tools ({len(tools)}):")
for tool in tools:
    print(f"- {tool.get('name', '<unnamed>')}")
    if show_schemas:
        details = {
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
        }
        print(json.dumps(details, indent=2, ensure_ascii=False))

resources = read_message("resources-list", 3).get("result", {}).get("resources", [])
print(f"Resources ({len(resources)}):")
for resource in resources:
    print(f"- {resource.get('name') or resource.get('uri') or '<unnamed>'}")
PY

echo "Connectivity check passed. No MCP tool was executed."
