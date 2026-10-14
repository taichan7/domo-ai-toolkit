#!/usr/bin/env bash
# Call one tool on a Domo toolkit exposed over Streamable HTTP MCP.
#
# Unlike check-domo-mcp.sh (discovery only), this executes a real tool call
# and can return live Domo data. Confirm the tool name, arguments, and
# authorization with the user before running anything beyond a read-only
# search/query. See docs/domo-mcp.md for the full procedure.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <ToolName> ['<json-arguments>'] [endpoint]" >&2
  echo "Example: $0 domo_search '{\"query\":\"*\",\"entityTypes\":[\"DATASET\"],\"count\":5}'" >&2
  exit 2
fi

TOOL_NAME="$1"
TOOL_ARGS_JSON="${2:-{\}}"
DEFAULT_ENDPOINT="https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp"
ENDPOINT="${3:-${DOMO_MCP_ENDPOINT:-$DEFAULT_ENDPOINT}}"
PYTHON_BIN="$(domo_find_python)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/domo-mcp-call.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ! "$ENDPOINT" =~ ^https://([^/]+)(/.*)?$ ]]; then
  echo "ERROR: endpoint must be an HTTPS URL: $ENDPOINT" >&2
  exit 2
fi
INSTANCE="${INSTANCE:-${BASH_REMATCH[1]}}"

# Validate tool arguments are well-formed JSON before sending anything.
if ! "$PYTHON_BIN" -c 'import json,sys; json.loads(sys.argv[1])' "$TOOL_ARGS_JSON" 2>/dev/null; then
  echo "ERROR: tool arguments are not valid JSON: $TOOL_ARGS_JSON" >&2
  exit 2
fi

mcp_post() {
  local label="$1" body="$2"
  local output="$TMP_DIR/$label.body" headers="$TMP_DIR/$label.headers"
  shift 2
  local code
  code="$(curl -sS --max-time 60 -D "$headers" -o "$output" -w '%{http_code}' \
    -X POST "$ENDPOINT" "${MCP_AUTH_ARGS[@]}" "$@" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    --data "$body")"
  printf '%s HTTP %s\n' "$label" "$code" >&2
  if [[ "$code" -lt 200 || "$code" -ge 300 ]]; then
    echo "ERROR: $label failed; response body was intentionally not printed." >&2
    exit 1
  fi
}

domo_load_mcp_auth
echo "Endpoint: $ENDPOINT" >&2
echo "Authentication: $AUTH_METHOD" >&2
echo "Tool: $TOOL_NAME" >&2
echo "Arguments: $TOOL_ARGS_JSON" >&2

mcp_post initialize \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"domoutils-mcp-call","version":"1.0.0"}}}'

SESSION_ID="$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/{gsub("\r",""); sub(/^[^:]+:[[:space:]]*/,""); print}' "$TMP_DIR/initialize.headers" | tail -1)"
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: initialize response did not contain Mcp-Session-Id." >&2
  exit 1
fi
SESSION_ARGS=(-H "Mcp-Session-Id: $SESSION_ID")

mcp_post initialized \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  "${SESSION_ARGS[@]}"

CALL_BODY="$("$PYTHON_BIN" -c '
import json, sys
args = json.loads(sys.argv[2])
print(json.dumps({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": sys.argv[1], "arguments": args},
}))
' "$TOOL_NAME" "$TOOL_ARGS_JSON")"

mcp_post tools-call "$CALL_BODY" "${SESSION_ARGS[@]}"

"$PYTHON_BIN" - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
text = (root / "tools-call.body").read_text(errors="replace")

# Streamable HTTP responses are SSE: one or more "data:<json>" lines.
# Progress notifications share the stream with the final result, and the
# "data:" prefix is not always followed by a space, so strip it manually.
messages = []
for line in text.splitlines():
    if line.startswith("data:"):
        payload = line[len("data:"):].lstrip(" ")
        if payload.strip():
            messages.append(json.loads(payload))
if not messages:
    messages = [json.loads(text)]

result_message = next((m for m in messages if m.get("id") == 2), messages[-1])
result = result_message.get("result")
error = result_message.get("error")

if error is not None:
    print("Tool call returned a JSON-RPC error:", file=sys.stderr)
    print(json.dumps(error, indent=2, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

if result and result.get("isError"):
    print("Tool reported isError=true:", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

for item in (result or {}).get("content", []):
    if item.get("type") == "text":
        text_payload = item["text"]
        try:
            print(json.dumps(json.loads(text_payload), indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(text_payload)
    else:
        print(json.dumps(item, indent=2, ensure_ascii=False))
PY

echo "Tool call complete. Review the output above before pasting it elsewhere -- it may contain live Domo data." >&2
