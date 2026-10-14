# Domo API Reference

> Japanese: [api-reference.ja.md](api-reference.ja.md)

A focused reference for talking to a Domo instance from the command line or from an AI agent. Covers authentication, the most useful endpoints, response shapes, error codes, and common patterns.

---

## Important: How to authenticate

**Never use browser automation (Puppeteer, Playwright) to interact with Domo.** Use the API with one of the three authentication methods below.

### Three authentication methods

| Method | When to use | Header |
|---|---|---|
| **Developer Token** | Long-lived automations, server jobs | `X-DOMO-Developer-Token: <token>` |
| **CLI Session (SID)** | Local development, AI agents on your machine | `X-Domo-Authentication: <SID>` |
| **OAuth Bearer** | Public developer API (`api.domo.com`) | `Authorization: Bearer <access_token>` |

### Method 1 — Developer Token (simplest)

1. In Domo, go to **Admin → Authentication → Access Tokens**
2. Click **Generate access token**, name it, choose an expiry
3. Copy the token immediately (it is shown only once)

```bash
curl -H "X-DOMO-Developer-Token: $TOKEN" \
  "https://$INSTANCE/api/data/v3/datasources?limit=10"
```

### Method 2 — CLI Session Token (recommended for AI agents)

The Domo CLI (`ryuu`) stores a refresh token locally after `domo login`. We exchange that refresh token for an access token, then exchange the access token for a session ID (SID) that works against all instance APIs.

The CLI config file lives at `~/.config/configstore/ryuu/<instance>.domo.com.json` on Mac/Linux, or `%USERPROFILE%\.config\configstore\ryuu\<instance>.domo.com.json` on Windows.

```bash
# Set the instance
INSTANCE="your-company.domo.com"

# Read the refresh token (Windows uses $USERPROFILE; macOS/Linux use $HOME)
REFRESH_TOKEN=$(python -c "import json,os; print(json.load(open(os.path.expanduser('~/.config/configstore/ryuu/$INSTANCE.json')))['refreshToken'])")

# Exchange for an access token
ACCESS_TOKEN=$(curl -s -X POST "https://$INSTANCE/api/oauth2/token" \
  -H "content-type: application/x-www-form-urlencoded;charset=utf-8" \
  -d "client_id=domo:internal:devstudio&grant_type=refresh_token&refresh_token=$REFRESH_TOKEN" \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# Exchange for a SID
SID=$(curl -s "https://$INSTANCE/api/oauth2/sid" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python -c "import json,sys; print(json.load(sys.stdin)['sid'])")

echo "Authenticated to $INSTANCE — SID=$SID"
```

Then use the SID on every request:

```bash
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/data/v3/datasources?limit=50"
```

### Method 3 — OAuth Bearer (public developer API only)

For `api.domo.com` endpoints. Get a client ID + secret from `developer.domo.com → My Account → New Client`, then follow the standard OAuth2 client-credentials flow.

```bash
ACCESS_TOKEN=$(curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
  "https://api.domo.com/oauth/token?grant_type=client_credentials&scope=data" \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://api.domo.com/v1/datasets?limit=10"
```

Note: developer tokens do **not** work against `api.domo.com` (returns 401). Use OAuth for the public API.

---

## Working API endpoints (instance APIs)

All endpoints below assume `INSTANCE` and `SID` are set as shown above.

### Datasets

| Action | Method | Endpoint |
|---|---|---|
| List datasets | `GET` | `/api/data/v3/datasources?limit=50&offset=0` |
| Get dataset metadata | `GET` | `/api/data/v3/datasources/{datasetId}` |

- Max page size is 50. Requesting more returns 400.
- Pagination: increment `offset` by 50 until the returned list has fewer than 50 items.
- Large instances can have 10,000+ datasets. For these, see the **Threaded pagination** section below.

Response (abbreviated):

```json
{
  "dataSources": [
    {
      "id": "uuid",
      "name": "...",
      "type": "DataFlow",
      "state": "SUCCESS",
      "rowCount": 12345,
      "columnCount": 14,
      "owner": { "id": 123, "name": "Jane Doe" },
      "lastUpdated": 1715040000000,
      "cardInfo": { "cardCount": 5 }
    }
  ]
}
```

Key fields on a dataset object:

| Field | Meaning |
|---|---|
| `id` | UUID |
| `name` | Display name |
| `type` / `dataProviderType` | Source connector (`DataFlow`, `webform`, `snowflake`, `salesforce`, etc.) |
| `transportType` | `VIEW`, `CONNECTOR`, `SMTP`, `API`, `WEBFORM`, `CLOUD`, `WORKBENCH`, `FEDERATED` |
| `state` | `IDLE`, `SUCCESS`, `ERROR`, `ACTIVE` |
| `rowCount` / `columnCount` | Current size |
| `owner` | `{ id, name, type }` |
| `lastUpdated` | Epoch ms of last data refresh |
| `cardInfo.cardCount` | How many cards reference this dataset |
| `cryoStatus` | `ADRENALINE` (active) or `CRYO` (archived) |
| `hidden` | Whether the dataset is hidden in the UI |

### Dataset SQL Query

| Action | Method | Endpoint |
|---|---|---|
| Execute SQL | `POST` | `/api/query/v1/execute/{datasetId}` |

Body: `{"sql": "SELECT * FROM table WHERE col = 'val' LIMIT 10"}`

- The table name is always `table` — it refers to the dataset itself.
- Standard SQL supported: `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`, `LIKE`, `IN`, `COUNT`, etc.
- Column names with spaces must be backtick-escaped: `` `Column Name` ``.
- `LIMIT 0` returns columns only — useful for schema discovery.

Response shape:

```json
{
  "columns": ["col_a", "col_b"],
  "rows": [["v1", "v2"], ["v3", "v4"]],
  "metadata": [{ "type": "STRING" }, { "type": "LONG" }]
}
```

### Dataflows (Magic ETL)

| Action | Method | Endpoint |
|---|---|---|
| List all dataflows | `GET` | `/api/dataprocessing/v1/dataflows` |
| Get dataflow details | `GET` | `/api/dataprocessing/v1/dataflows/{id}` |
| Update dataflow | `PUT` | `/api/dataprocessing/v1/dataflows/{id}` |
| Trigger execution | `POST` | `/api/dataprocessing/v1/dataflows/{id}/executions` |
| Execution history | `GET` | `/api/dataprocessing/v1/dataflows/{id}/executions?limit=5&offset=0` |

Notes:

- The list endpoint ignores `limit`/`offset` and returns **all** dataflows in one response.
- Do **not** use `?hydrate=full` — it returns 400 for some dataflows. The non-hydrated GET already includes the full `actions[]` array.
- The PUT replaces the entire dataflow definition. Always GET first, modify, then PUT the full object back.
- Each successful PUT increments `onboardFlowVersion.versionNumber`.

Dataflow object (key fields):

```text
id              numeric dataflow ID
name            display name
runState        "ENABLED" or "DISABLED"
databaseType    "MAGIC" for Magic ETL
lastExecution   { failed, state, errors[] }
actions[]       ETL tiles — each has { id, type, ...config }
```

### Cards and dashboards

| Action | Method | Endpoint |
|---|---|---|
| Get page info | `GET` | `/api/content/v1/pages/{pageId}` |
| Get page cards | `GET` | `/api/content/v1/pages/{pageId}/cards` |
| Get app datastores | `GET` | `/api/datastores/v1/collections?appId={appId}` |

- App IDs and page IDs come from URLs like `/app-studio/{appId}/pages/{pageId}`.
- Page cards return titles and URN IDs but not the backing dataset. Use the DomoStats `Card Datasources` dataset to map cards → datasets.

### Users and groups

| Action | Method | Endpoint |
|---|---|---|
| Get user | `GET` | `/api/content/v2/users/{userId}` |
| Search users | `GET` | `/api/content/v2/users/search?q={query}&limit=50` |
| List groups | `GET` | `/api/content/v2/groups?limit=50` |

### OAuth helpers (used by Method 2 above)

| Action | Method | Endpoint |
|---|---|---|
| Exchange refresh token | `POST` | `/api/oauth2/token` (form: `client_id`, `grant_type=refresh_token`, `refresh_token`) |
| Get SID from access token | `GET` | `/api/oauth2/sid` (header: `Authorization: Bearer <token>`) |

The hardcoded client ID for the CLI flow is `domo:internal:devstudio`.

---

## Custom App SDK (iframe — ryuu.js)

Custom Apps (Pro Code apps) run inside an iframe on Domo. They load `https://unpkg.com/ryuu.js`, which injects a `window.domo` object. The session is bound to the iframe automatically via the `ryuu_sid` query parameter — **never pass auth headers manually inside a Custom App**.

### `domo.get(url)` / `domo.post(url, body, opts)` / `domo.put(url, body)`

All three return a parsed JSON Promise. `opts.contentType` defaults to `application/json`; pass `'text/plain'` when the body is a raw SQL string.

### Verified iframe-callable endpoints

| Capability | Method | URL template | Manifest binding |
|---|---|---|---|
| AI text generation | `POST` | `/domo/ai/v1/text/generation` | none (global) |
| AI text-to-SQL | `POST` | `/domo/ai/v1/text/sql` | none (global) |
| Code Engine function call | `POST` | `/domo/codeengine/v2/packages/<packageAlias>` | `packagesMapping[]` |
| Workflow start | `POST` | `/domo/workflow/v1/models/<workflowAlias>/start` | `workflowsMapping[]` |
| AppDB doc create | `POST` | `/domo/datastores/v1/collections/<name>/documents` | `collectionsMapping[]` |
| AppDB doc get | `GET` | `/domo/datastores/v1/collections/<name>/documents/<id>` | same |
| AppDB doc update | `PUT` | `/domo/datastores/v1/collections/<name>/documents/<id>` | same |
| AppDB doc query | `POST` | `/domo/datastores/v1/collections/<name>/documents/query` | same |
| Dataset row read | `GET` | `/data/v1/<datasetAlias>` (querystring filter) | `datasetsMapping[]` |
| Dataset SQL query | `POST` | `/sql/v1/<datasetAlias>` (body: raw SQL string, `contentType: 'text/plain'`) | `datasetsMapping[]` |
| Dataset query by raw ID | `POST` | `/domo/query/v1/execute/<datasetId>` (body: `{sql}`) | none |
| User lookup | `GET` | `/domo/users/v1/<userId>?includeDetails=true` | none |

### Manifest binding shape

```json
{
  "name": "My App",
  "version": "0.1.0",
  "size": { "width": 1, "height": 1 },
  "fullpage": true,
  "datasetsMapping":   [{ "dataSetId": "<uuid>", "alias": "myDs", "fields": [] }],
  "collectionsMapping":[{ "id": "<uuid>", "name": "my_collection", "syncEnabled": true, "schema": { "columns": [] } }],
  "workflowsMapping":  [{ "alias": "my_workflow", "modelId": "<uuid>" }],
  "packagesMapping":   [{ "name": "DOMO DataSets", "alias": "ceQuery", "packageId": "<uuid>", "parameters": [], "output": {}, "version": "3.1.0", "functionName": "queryWithSql" }]
}
```

Aliases declared in the manifest become the `<alias>` slot in the URL templates above.

### SQL endpoint response shape (iframe vs server)

- **Iframe `POST /sql/v1/<alias>`** returns column-oriented:
  ```json
  { "columns": ["A","B"], "numColumns": 2, "numRows": 25, "rows": [["v1","v2"]] }
  ```
- **Server `POST /api/query/v1/execute/<datasetId>`** returns the same shape plus a `metadata[]` array with column types.
- **Iframe `GET /data/v1/<alias>`** returns row-oriented (array of `{column: value}` objects). Domo lowercases column AS-aliases that match an existing column name, and otherwise preserves case. Use case-insensitive lookup when reading rows.

### Iframe runtime context (`domo.env`)

The platform injects user and session context as URL parameters and on `domo.env`:

- `domo.env.userId`, `domo.env.userName`, `domo.env.userEmail`
- `domo.env.customer` (instance subdomain)
- `domo.env.locale`, `domo.env.platform`

These are also reflected in the iframe URL (`?USER_ID=...&USER_NAME=...&customer=...`) so they are inspectable in browser network traces.

---

## Diagnosing failing ETLs

The common pattern is: fetch all dataflows → filter to failed → drill into the specific tile that broke.

### Step 1 — Find failures

```bash
curl -s -H "X-Domo-Authentication: $SID" "https://$INSTANCE/api/dataprocessing/v1/dataflows" \
  | python -c "
import json, sys
flows = json.load(sys.stdin)
for f in flows:
    le = f.get('lastExecution', {})
    if le.get('failed'):
        errors = le.get('errors', [])
        msgs = [f\"[{e.get('code','?')}] {e.get('localizedMessage','')}\" for e in errors]
        print(f\"{f['id']}: {f['name']} — {' | '.join(msgs) if msgs else '(no detail)'}\")
"
```

### Step 2 — Drill into a specific dataflow

```bash
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/<ID>"
```

Look at `lastExecution.errors[].parameters._actionId` to find the failing tile ID, then find that ID in `actions[]`.

### Common error codes

| Code | Meaning | Typical fix |
|---|---|---|
| `DP-DSNF` / `DP-61100` | Input dataset does not exist | Recreate the dataset or remove the `LoadFromVault` tile |
| `DP-0001` | Column not found | Upstream schema changed — update the column references |
| `DP-0059` | Syntax error in expression | Fix the formula (e.g., missing `END` on a CASE) |
| `DP-0118` | Code/model tile crash | Check the Python script or AI model tile |
| `MYSQL-601072` | Join key missing | Join references a column that no longer exists |
| `DP-TGTFR` | Not enough rows | Batch Text Generation needs at least 100 rows |
| `DP-0000` | Unknown error | Inspect in the Domo UI — no API detail available |

### Drill-down by tile type

When you find the failing `_actionId` in `actions[]`, look at:

| Action type | Field to inspect |
|---|---|
| `ExpressionEvaluator` | `expressions[].expression` |
| `LoadFromVault` | `dataSourceId` |
| `MergeJoin` | `keys1[]` / `keys2[]` |
| `SelectValues` | `fields[].name` |
| `Filter` | `filterList[].leftField` |
| `PythonEngineAction` | `script` |
| `PublishToVault` | `dataSource.guid` |

---

## Modifying an ETL via API

```bash
# 1. GET the current dataflow
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID" > dataflow.json

# 2. Modify dataflow.json (in Python, jq, or by hand)

# 3. PUT it back
curl -s -X PUT \
  -H "X-Domo-Authentication: $SID" \
  -H "Content-Type: application/json" \
  -d @dataflow.json \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID"

# 4. Trigger an execution
curl -s -X POST \
  -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID/executions"

# 5. Check the result
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID/executions?limit=1&offset=0"
```

Send the **full** dataflow object on the PUT — partial updates are not supported.

---

## Threaded pagination (for large instances)

If your instance has thousands of datasets, sequential pagination at 50 per page is slow and the SID may expire mid-run. Fetch 10 pages concurrently:

```python
import json, urllib.request, ssl, sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
instance = os.environ['INSTANCE']
sid = os.environ['SID']
base = f'https://{instance}/api/data/v3/datasources'

def fetch_page(offset):
    req = urllib.request.Request(
        f'{base}?limit=50&offset={offset}',
        headers={'X-Domo-Authentication': sid}
    )
    return json.loads(urllib.request.urlopen(req, context=ctx, timeout=60).read())['dataSources']

all_ds, offset, batch_size, done = [], 0, 10, False
while not done:
    offsets = [offset + i * 50 for i in range(batch_size)]
    with ThreadPoolExecutor(max_workers=batch_size) as ex:
        for fut in as_completed({ex.submit(fetch_page, o): o for o in offsets}):
            page = fut.result()
            all_ds.extend(page)
            if len(page) < 50:
                done = True
    offset += batch_size * 50
    print(f'Fetched {len(all_ds)} so far...', file=sys.stderr)

with open('datasets.json', 'w') as f:
    json.dump(all_ds, f)
print(f'Total: {len(all_ds)}')
```

Notes for very large instances:

- SIDs last roughly an hour. If you get a 401 mid-run, re-authenticate and resume from the last successful offset.
- Save progress to disk as you go — resume by setting `offset = len(all_ds)`.
- Threaded fetch is ~10× faster than sequential.

---

## Endpoints that look right but don't work

These return 404 or redirect — they exist in old docs but are not the right path:

- `/api/data/v1/datasets` → 404
- `/api/dataset/v3/datasources` → 404
- `/api/datasources` → 404
- `/api/content/v1/datasources` → 404
- `/oauth/token` with `refresh_token` grant → 302 redirect (use `/api/oauth2/token`)

---

## Public Developer API vs. instance API

The public developer API at `api.domo.com` is a stable, documented subset. It is the right choice for partner integrations and long-running automations. The endpoints in this reference are the **instance APIs** (`<your-instance>.domo.com/api/...`) — they are the same APIs the Domo UI uses, they are stable, but they are not formally part of the published developer API.

Use the instance APIs when:

- You need data and operations the public API does not expose (dataflow internals, app studio internals, governance datasets)
- You are working as an authenticated user, not as a third-party app

Use the public developer API when:

- You are building a partner integration
- You want a stable, documented contract
- You are calling from outside the user's machine (server-to-server)

You can use both in the same project — just use the right auth header for each (`X-DOMO-Developer-Token` or `X-Domo-Authentication` for instance APIs; `Authorization: Bearer` for `api.domo.com`).

---

## See also

- `../scripts/authenticate.sh` — the auth flow as a runnable script
- `../scripts/list-datasets.sh` — paginate datasets
- `../scripts/query-dataset.sh` — run SQL
- `../scripts/diagnose-etls.sh` — find and categorize failing ETLs
- `../templates/pro-code-app/` — a working Pro Code app skeleton
- `../../AGENTS.md` — how to use this reference with an AI agent
