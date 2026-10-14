# Domo MCP Setup And Verification

> Japanese: [domo-mcp.ja.md](domo-mcp.ja.md)

## Verified Server

| Item | Value |
|---|---|
| Instance | `maintenance-instance.domo.com` |
| Streamable HTTP endpoint | `https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp` |
| Authentication header | `X-Domo-Developer-Token: <developer-token>` |
| MCP server | `domo_basic_mcp` version `0.0.1` |
| Negotiated protocol | `2025-03-26` |
| Capabilities | `tools`, `resources` |

The endpoint was most recently verified on 2026-07-29 with an authenticated `initialize`, initialized notification, `tools/list`, and `resources/list`. The server returned these tools:

| Current tool name | Purpose | Deprecated name observed on 2026-07-13 |
|---|---|---|
| `domo_search` | Search Domo entity metadata by name or description. | `SearchTool` |
| `domo_sql_query` | Answer a natural-language question by querying one or more Datasets. | `DomoSqlQueryTool` |
| `domo_fileset_query` | Return relevant excerpts from indexed FileSet documents. | `FileSetQueryTool` |

Use the current names returned by `tools/list`. The earlier CamelCase names are historical and were no longer advertised on 2026-07-29, even though the server still reported version `0.0.1`.

This manual is specific to `domo_basic_mcp`. The three advertised tools are read/query operations; this endpoint did not expose tools for creating Cards, Workflows, Magic ETL dataflows, or other Domo assets. Do not infer the capabilities of a broader Domo AI toolkit from this basic endpoint.

`resources/list` returned zero static resources. This does not mean resource support is disabled: the initialized server advertised the `resources` capability.

All three current tools were exercised end-to-end with read-only calls on 2026-07-29; see [Verified Tool Behavior](#verified-tool-behavior).

## Repeat The Read-Only Check

From the repository root:

```bash
bash ../scripts/check-domo-mcp.sh
```

Print the live tool descriptions and `inputSchema` values before a tool call:

```bash
bash ../scripts/check-domo-mcp.sh --show-schemas
```

Authentication order:

1. `DOMO_TOKEN` as `X-Domo-Developer-Token`.
2. An explicitly exported `SID`.
3. A temporary SID exchanged in memory from the local `domo login` config for `maintenance-instance.domo.com`.
4. The ignored `../scripts/.sid` session when no local CLI config is available.

The script never prints credentials or response headers, deletes temporary response files on exit, and only calls MCP discovery methods. Override the endpoint when needed:

```bash
DOMO_MCP_ENDPOINT='https://example.domo.com/api/ai/v1/assistant/mcp/toolkits/example' \
  bash ../scripts/check-domo-mcp.sh
```

## Call A Tool

`check-domo-mcp.sh` only performs discovery. To actually invoke a tool, use:

```bash
bash ../scripts/call-domo-mcp-tool.sh <ToolName> '<json-arguments>' [endpoint]
```

Example, verified 2026-07-29:

```bash
bash ../scripts/call-domo-mcp-tool.sh domo_search \
  '{"query":"*","entityTypes":["DATASET"],"count":5}'
```

The script runs the same `initialize` / `notifications/initialized` handshake as the connectivity check, then calls `tools/call` and prints the parsed result to stdout. Authentication uses the same order as `check-domo-mcp.sh`. Unlike the connectivity check, this executes a real tool and can return live Domo data.

Before calling any tool:

1. Run `bash ../scripts/check-domo-mcp.sh --show-schemas` and use the current name and `inputSchema`. The toolkit can change independently of this repository.
2. Confirm the call is read-only, or get explicit user confirmation for anything that could write, delete, or trigger a workflow, per `AGENTS.md`.
3. Treat the result as live Domo data. Do not paste raw tool output into a handoff, issue, PR, or shared notice — summarize it instead.

### Current Input Schemas (2026-07-29)

`domo_search`:

| Field | Current schema |
|---|---|
| `query` | Optional string. Use `*` for wildcard matching. In practice, provide it explicitly. |
| `entityTypes` | Optional array of `APP`, `DATA_APP`, `BEAST_MODE`, `CARD`, `DATASET`, `FILE_SET`, `PAGE`, `WORKFLOW_MODEL`, or `APP_CARD`. In practice, provide it explicitly. |
| `count` | Optional integer, `1`–`100`; default is `20`. |
| `offset` | Optional integer, minimum `0`; default is `0`. |

The tool-level description also mentions `GROUP` and `USER`, but the current `entityTypes` field description does not list them. Treat the field description as the safer contract until those two values are verified.

`domo_sql_query`:

| Field | Current schema |
|---|---|
| `dataSourceIds` | Required array of Dataset ID strings. The tool description says to include every Dataset ID available in the immediate context; the service chooses the relevant source. |
| `userQuestion` | Required natural-language question about the Datasets. |

`domo_fileset_query`:

| Field | Current schema |
|---|---|
| `fileSets` | Required array of `{ "fileSetId": "...", "path": "..." }`. `fileSetId` is required; `path` is optional, must be a full path when set, and may be empty for the root. |
| `query` | Required natural-language semantic-search query. |
| `topK` | Required integer, `1`–`100`. |

### Verified Tool Behavior

The following read-only behavior was observed on 2026-07-29:

- `domo_search` returned Dataset and FileSet metadata, including `id`, `name`, `title`, `description`, and `totalCount`. A typed wildcard search and a typed free-text Dataset search both succeeded.
- `domo_sql_query` returned schema/row-count information for a small sample Dataset, then successfully performed a grouped top-three aggregate from a Japanese natural-language question. This is natural-language-to-query behavior; callers do not send raw SQL.
- `domo_fileset_query` returned ranked matching excerpts with `fileId`, full `path`, and a relevance `score`. A different valid query returned `[]`, so an empty array can mean that no relevant indexed passage was found; it is not by itself a transport failure.
- FileSet query results are excerpts, not complete file downloads. The advertised description refers to a separate `FileSetReadTool` for whole-file reads, but that tool was not exposed by this toolkit on 2026-07-29.

### Response Format Note

Streamable HTTP responses are Server-Sent Events: one or more `data:<json>` lines, and `tools/call` responses can include `notifications/progress` events interleaved with the final result. The `data:` prefix is not always followed by a space (`data:{...}` as well as `data: {...}`), so a parser must strip `data:` and select the JSON-RPC message by matching `id`, not just read the first or last SSE line. `call-domo-mcp-tool.sh` already handles this.

### Observed Error

Calling the deprecated `SearchTool` with a free-text `query` and no `entityTypes` on 2026-07-13 returned HTTP 500. On 2026-07-29, typed searches through `domo_search` succeeded with both `query: "*"` and a free-text query. Always use the current tool name and provide `entityTypes` before concluding that the endpoint is broken.

## Authentication Guidance

For a persistent MCP client, use the Developer Token shown by Domo when enabling the toolkit and send it as `X-Domo-Developer-Token`. Keep the value in an environment variable or the client's protected secret storage; never commit it.

A Domo CLI `refreshToken` is not necessarily a Developer Token. In the verified local configuration, `devToken` was `false`; sending that refresh token directly in `X-Domo-Developer-Token` returned `401`. The connectivity script can exchange this CLI credential for a short-lived SID and use `X-Domo-Authentication`, but a static client configuration should use the toolkit's Developer Token unless the client can refresh Domo sessions.

## Client Configuration

Replace secret placeholders at runtime. Do not add a literal token to this repository.

### Codex

The local Codex CLI supports Streamable HTTP URLs, but its `mcp add` command only exposes Bearer-token authentication. Domo needs a custom header, so use Codex `config.toml` and map the header to an environment variable:

```toml
[mcp_servers.domo_basic]
url = "https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp"
env_http_headers = { "X-Domo-Developer-Token" = "DOMO_TOKEN" }
```

Export `DOMO_TOKEN` in the environment that launches Codex, restart Codex, then confirm the server appears:

```bash
codex mcp list
```

### Claude Code

Claude Code accepts a custom header for an HTTP MCP server:

```bash
claude mcp add --transport http --scope user domo_basic \
  'https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp' \
  --header "X-Domo-Developer-Token: $DOMO_TOKEN"
claude mcp get domo_basic
```

This command may persist the expanded header in the user's Claude configuration. Confirm the storage behavior and file permissions for the installed Claude version. Prefer an environment-variable header reference in clients that support one.

### Claude Desktop, Cursor, VS Code, And Other MCP Clients

Add a remote Streamable HTTP server with:

```json
{
  "url": "https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp",
  "headers": {
    "X-Domo-Developer-Token": "<developer-token-from-secure-storage>"
  }
}
```

The surrounding configuration key and environment-variable substitution syntax differ by client version. Use the client's remote HTTP/Streamable HTTP form, select custom headers, and store the token outside the repository. The server is not a local `stdio` command and the header is not `Authorization: Bearer`.

## Verification Checklist For Another AI

1. Read `AGENTS.md`, `domo-auth.md`, and this document.
2. Confirm the endpoint host is the intended Domo instance.
3. Run `bash ../scripts/check-domo-mcp.sh`; do not print the token or raw headers.
4. Confirm `initialize`, initialized notification, `tools/list`, and `resources/list` are all 2xx.
5. Compare the reported tool names with the current list above. A difference may indicate a toolkit update, not necessarily a failure.
6. Before invoking any tool, run `bash ../scripts/check-domo-mcp.sh --show-schemas` and apply the repository's read/write safety rules.
7. To actually invoke a tool, use `bash ../scripts/call-domo-mcp-tool.sh <ToolName> '<json-arguments>'`; see [Call A Tool](#call-a-tool).
8. Dataset, FileSet, search, or other production mutations still require the same authorization and confirmation as direct Domo API operations.

## Troubleshooting

| Symptom | Likely cause / action |
|---|---|
| `401` | The credential is missing, expired, or a CLI refresh token was incorrectly used as a Developer Token. |
| `initialize` succeeds but later calls return `400` | Preserve `Mcp-Session-Id` and send `notifications/initialized` before discovery calls. |
| Client sends `Authorization: Bearer` | Configure the custom `X-Domo-Developer-Token` header instead. |
| `resources/list` is empty | This was the verified result; use the advertised tools and inspect their schemas. |
| Client cannot define custom HTTP headers | Use a client/version that supports custom headers; do not embed the token in a wrapper committed to git. |
| `tools/call` returns `500` | Re-run schema discovery, use the current snake_case tool name, and retry with a specific request (for example add `entityTypes` to `domo_search`) before assuming the endpoint is down. |
| `domo_fileset_query` returns `[]` | The call can still be healthy; no relevant indexed passage may have matched. Try a clearer query, verify `fileSetId` and full `path`, and confirm that the FileSet is indexed. |
| `tools/call` response fails to parse as JSON | The SSE `data:` prefix may lack a trailing space, and progress notifications share the stream with the result. Match the JSON-RPC message by `id`; see Response Format Note above. |

## Security And Change Boundary

- Do not commit Developer Tokens, SID values, refresh tokens, MCP session IDs, cookies, or raw authenticated logs.
- Treat tool discovery as read-only. The safety of a tool call depends on the selected tool and arguments.
- Inspect tool schemas each time because Domo may update the toolkit independently of this repository.
- Production writes, deletes, deployments, workflow triggers, and other mutations require explicit user confirmation under `AGENTS.md`.

## Additional Toolkits (verified 2026-09-05)

The section above is specific to `domo_basic_mcp`. The same instance exposes three more toolkits under
`https://<instance>/api/ai/v1/assistant/mcp/toolkits/{toolkit}`. All were exercised live on `maintenance-instance`. For the
authoring-oriented summary and the recipe, see the skill [`../skills/domo-mcp-toolkits.md`](../skills/domo-mcp-toolkits.md).

| Toolkit | What it exposes |
|---|---|
| `domo_basic_mcp` | Read/query tools (documented above): `domo_search`, `domo_sql_query`, `domo_document_collection_query`, `FileSetReadTool`, `DocumentListTool`, `DomoDocumentationQueryTool`. |
| `full_card_toolkit` | Card operations (large tool schema). |
| `user_admin_toolkit` | User administration tools. |
| `workspaces_toolkit` | 19 Workspaces tools: `workspace_list/get/create/update/delete`, `workspace_content_*`, `workspace_folder_*`, `workspace_member_*`. |

Key findings from this verification round:

- **`X-Domo-Authentication: <SID>` is sufficient for all four toolkits, reads AND writes** — an admin PAT is not
  required on your own instance. (`X-Domo-Developer-Token` also works where a dev token exists.)
- **The write path is real, not read-only.** `workspace_create` succeeds headless.
- **Destructive tools are unconditionally gated headless.** `workspace_delete` (and peers) hard-refuse with
  *"intra-tool confirmations are not enabled for this agent."* There is no `force`/`confirm` argument, and declaring
  the client capability `capabilities:{elicitation:{}}` does **not** unlock it (the server sends no
  `elicitation/create`; it just refuses). Programmatic teardown of a Workspace is therefore impossible from a
  headless agent — it must be done by a human in the Domo UI. Plan disposable test assets accordingly.
- **Argument names leak through error messages.** A wrong arg returns a Java-flavored error naming the expected
  params — e.g. `workspace_get` needs `workspaceGuids: ["..."]` (array) + `parts`, not `workspaceGuid`. Read the
  error and correct the call.
- **`DomoDocumentationQueryTool` is slow** — allow ~200s timeout.
- **Workspaces has no public REST API** — every `/api/.../workspaces` path probe 404s; the backend is an internal
  "Mako assistant" service. Use the MCP `workspaces_toolkit`, not REST.
- The handshake is identical to `domo_basic_mcp` (initialize → notifications/initialized → tools/list → tools/call;
  `Mcp-Session-Id` response header carried on every subsequent call; SSE `data:` lines matched by JSON-RPC `id`).
