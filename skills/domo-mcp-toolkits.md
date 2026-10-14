# Domo MCP Toolkits Skill

Use this when driving Domo's hosted **MCP toolkits** (Model Context Protocol servers exposed by a Domo instance) to read or mutate Domo objects from an agent. Companion background doc: [`../docs/domo-mcp.md`](../docs/domo-mcp.md).

> **Evidence tiers:** `[DOC]` = in Domo's public docs / OpenAPI; `[KB]` = documented product behavior; `[REPO]` = observed only on a live instance (maintenance-instance, 2026-09-05), **absent from public docs** — reverse-engineered, instance-/version-fragile, re-verify per instance. **The MCP-toolkit surface is not covered by any public Domo API doc found — treat this whole skill as `[REPO]` unless a line says otherwise.** The one failure mode to avoid: presenting a single-instance observation as a documented, portable contract.

## What exists (verified live on maintenance-instance, 2026-09-05)

Four toolkits under `https://<instance>/api/ai/v1/assistant/mcp/toolkits/{toolkit}`:

| Toolkit | Purpose | Notable tools |
|---|---|---|
| `domo_basic_mcp` | Read/query building blocks. | `domo_sql_query`, `domo_document_collection_query` (AppDB), `FileSetReadTool`, `domo_search`, `DocumentListTool`, `DomoDocumentationQueryTool`. |
| `full_card_toolkit` | Card operations (large schema). | card read/manage tools. |
| `user_admin_toolkit` | User administration. | user read/manage tools. |
| `workspaces_toolkit` | Workspaces content hub (19 tools). | `workspace_list/get/create/update/delete`, `workspace_content_*`, `workspace_folder_*`, `workspace_member_*`. |

## Protocol (Streamable HTTP + SSE)

One endpoint per toolkit; POST JSON-RPC, responses stream back as `text/event-stream` (`data:` lines).

1. `initialize` → server returns a `Mcp-Session-Id` **response header** — capture it.
2. `notifications/initialized` (send with the session header; no id).
3. `tools/list` → enumerate tools + input schemas.
4. `tools/call` with `{name, arguments}` → result streams on the same POST.

Required headers on every call:

```
Content-Type: application/json
Accept: application/json, text/event-stream
X-Domo-Authentication: <SID>          # observed to auth all 4 toolkits (reads+writes) on maintenance-instance; access follows the caller's own grants [REPO]
Mcp-Session-Id: <from initialize>     # all calls after initialize
```

Parse `data:` lines out of the streamed body; match the object whose `id` equals your request id.

## Concrete sequence (copy, don't guess)

Every message below is POSTed to the toolkit URL with the headers above. `<SID>` and `<SESSION>` are secrets — never commit them.

```jsonc
// 1) initialize — read the Mcp-Session-Id from the RESPONSE HEADERS of this call
{ "jsonrpc":"2.0", "id":1, "method":"initialize",
  "params": { "protocolVersion":"2025-03-26", "capabilities":{},
              "clientInfo":{ "name":"my-agent", "version":"1.0" } } }

// 2) initialized notification — no id, send with Mcp-Session-Id header
{ "jsonrpc":"2.0", "method":"notifications/initialized" }

// 3) list tools + their input schemas
{ "jsonrpc":"2.0", "id":2, "method":"tools/list" }

// 4) call a READ tool (headless-safe)
{ "jsonrpc":"2.0", "id":3, "method":"tools/call",
  "params": { "name":"workspace_list", "arguments":{} } }

// 4b) call a WRITE tool (headless-safe: create succeeds)
{ "jsonrpc":"2.0", "id":4, "method":"tools/call",
  "params": { "name":"workspace_create",
              "arguments":{ "name":"zz-verify-ws", "description":"disposable" } } }
```

Minimal Python transport (stdlib only; prints the JSON-RPC object matching each request id):

```python
import json, urllib.request
URL = f"https://{INSTANCE}/api/ai/v1/assistant/mcp/toolkits/{TOOLKIT}"
def post(body, session=None):
    h = {"Content-Type":"application/json",
         "Accept":"application/json, text/event-stream",
         "X-Domo-Authentication": SID}
    if session: h["Mcp-Session-Id"] = session
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=200) as r:      # 200s: DomoDocumentationQueryTool is slow
        sid, raw = r.getheader("Mcp-Session-Id"), r.read().decode("utf-8","replace")
    msgs = [json.loads(l[5:].lstrip()) for l in raw.splitlines()
            if l.startswith("data:") and l[5:].strip()]
    return sid, msgs
sid, _ = post({"jsonrpc":"2.0","id":1,"method":"initialize",
               "params":{"protocolVersion":"2025-03-26","capabilities":{},
                         "clientInfo":{"name":"a","version":"1"}}})
post({"jsonrpc":"2.0","method":"notifications/initialized"}, sid)
_, out = post({"jsonrpc":"2.0","id":3,"method":"tools/call",
               "params":{"name":"workspace_list","arguments":{}}}, sid)
```

## Auth

- `X-Domo-Authentication: <SID>` was **observed** to authenticate all four toolkits (reads and writes) on maintenance-instance — access follows the **caller's own Domo grants**, so no separate admin PAT was needed there `[REPO]`. `X-Domo-Developer-Token` also worked where a dev token exists. This is a single-instance observation, not a documented auth contract — re-confirm on any other instance.
- Never commit the SID or the `Mcp-Session-Id`. Treat MCP tool output as sensitive — summarize, don't paste raw into handoffs/PRs.

## What's headless-safe vs blocked (verified)

- **Reads** (`*_list`, `*_get`, `domo_sql_query`, doc/collection queries, search): work headless.
- **Non-destructive writes** (e.g. `workspace_create`): work headless — the MCP write path is real, not read-only.
- **DESTRUCTIVE tools** (`workspace_delete`, and peers): **hard-refuse headless** with *"intra-tool confirmations are not enabled for this agent."* Observed as a server-side policy on maintenance-instance:
  - No `force`/`confirm` argument was found that unlocks it.
  - Declaring the client `capabilities:{elicitation:{}}` did **not** unlock it in the one test run — **but that test is inconclusive.** MCP elicitation was introduced in protocol revision **2025-06-18**, and the handshake above negotiates **2025-03-26**, so the server would not attempt an `elicitation/create` round-trip regardless of the client capability. Whether a **2025-06-18** handshake with an elicitation-capable client changes the outcome is **UNVERIFIED** — do not claim elicitation "doesn't help" as a settled fact.
  - Under the tested (2025-03-26) handshake, programmatic teardown of a Workspace (and similar destructive ops) did **not** succeed from a headless agent — treat it as **blocked headless for now** and plan for a human to do it in the Domo UI. A newer-protocol elicitation handshake is the untested path that might change this.

## Gotchas

- **Argument names leak via errors, use them.** A wrong arg name returns a Java-flavored error naming the expected params/classes. Example: `workspace_get` needs `workspaceGuids: ["..."]` (array) + `parts`, **not** `workspaceGuid`. Read the error, correct the args.
- **`DomoDocumentationQueryTool` is slow** — allow ~200s timeout or it appears to hang.
- **Workspaces has no public REST API** `[REPO]`. Every `/api/.../workspaces` path probe returned 404 on maintenance-instance, so use the MCP toolkit (not REST) for Workspaces. The backing service's internal name is not confirmed — don't assert one.
- **SSE parsing:** a single logical result may span multiple `data:` lines, and progress notifications share the stream with the result — always match by JSON-RPC `id`; also handle a plain-JSON body fallback when the server doesn't stream.

## Do NOT claim as documented fact

Everything here is single-instance observation on maintenance-instance. Do **not** state any of these as a documented, portable Domo contract:

- That `X-Domo-Authentication: <SID>` is a *supported* auth method for the MCP toolkits — it was only *observed to work*.
- That the four toolkit names, their tool sets, or the "19-tool" Workspaces count are fixed — the catalog is instance-/version-dependent; always enumerate with `tools/list`.
- That destructive tools are *unconditionally* impossible headless — only the 2025-03-26 handshake was tested; the elicitation path (protocol 2025-06-18+) is untested.
- Any internal backend/service name for Workspaces or the toolkits.
- That `/api/ai/v1/assistant/mcp/toolkits/{toolkit}` is a stable public API path — it is undocumented and may change.

## Safety

- On shared instances (`maintenance-instance`), create only disposable, clearly-named test objects you own, and delete them when done — but remember destructive MCP tools are gated headless (above), so prefer test objects whose teardown you can do via REST (dataflows/datasets/workflow models) over Workspaces.
- Never delete or inventory objects you did not create.
- Do not run destructive tools against production objects.
