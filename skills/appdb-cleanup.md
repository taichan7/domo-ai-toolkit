# AppDB Cleanup Skill

Use this skill when asked to delete or prune AppDB documents — e.g. "昨日より以前のログを削除", "古いドキュメントを整理", "X日以前のレコードを削除".

## Safety rules

- Always count and show the documents to be deleted **before** deleting.
- AppDB deletes are permanent. Require explicit user confirmation if count > 100, or if the collection is one your organization treats as high-risk (if you keep such a list).
- Never delete documents from the current day without explicit confirmation.
- For recurring cleanup, prefer the fast script in `../scripts/appdb-prune-latest.py`; it defaults to dry-run and uses parallel DELETE workers only after explicit confirmation.

## Fast path: keep latest N documents

Use this path when the user asks to keep only the most recent records, for example "直近10件だけ残して削除".

### 1. Dry-run and show the count

```bash
python3 ../scripts/appdb-prune-latest.py \
  --collection-url "https://maintenance-instance.domo.com/appDb/5cd3224e-d440-5b80-9128-d47825799db6/dataexplorer" \
  --collection-name "【PROD】marketdata AI自動売買実行ログ" \
  --keep 10 \
  --concurrency 10
```

Dry-run prints:

- total document count
- number of documents to keep and delete
- UTC date distribution by `createdOn`
- exact keep candidates
- delete candidate sample

Show those counts to the user. If delete count is over 100, current-day documents are included, or the collection is one your organization treats as high-risk, require explicit confirmation before running the execute command.

### 2. Execute after explicit confirmation

```bash
python3 ../scripts/appdb-prune-latest.py \
  --collection-url "https://maintenance-instance.domo.com/appDb/5cd3224e-d440-5b80-9128-d47825799db6/dataexplorer" \
  --collection-name "【PROD】marketdata AI自動売買実行ログ" \
  --keep 10 \
  --concurrency 10 \
  --execute \
  --confirmed
```

Important behavior:

- `--execute` is rejected unless `--confirmed` is also present.
- The script re-fetches documents immediately before deleting, so the latest N documents are based on the current AppDB state.
- Documents are sorted newest-first by `createdOn` by default; use `--sort-field <field>` only if the collection's business timestamp is different.
- DELETE calls run in parallel. Default `--concurrency 10` is the recommended speed/safety balance; increase only if rate limits are not observed.
- After the first delete batch, the script performs enforcement passes so logs created during cleanup are handled and only the latest N remain.
- The script verifies by re-fetching the collection and exits non-zero if more than N documents remain or any delete fails.
- It never prints SID, refresh token, developer token, or other secrets.

### 3. Report verification

Report the final verification lines:

- `Deleted or already gone`
- `Failed deletes`
- `Remaining documents`
- remaining `createdOn` range
- remaining docs newest first

Do not claim success unless `Failed deletes: 0` and `Remaining documents` is at or below the requested keep count.

## Day-based retention (preferred for recurring logs)

Use this when the collection is an append-only operational log (for example the marketdata
execution log) and the requirement is "keep the last N days", not "keep the last N rows".

```bash
# Dry-run first (default). Shows total / keep / delete counts and the cutoff.
python3 ../scripts/appdb-prune-latest.py \
  --collection-url "https://maintenance-instance.domo.com/appDb/5cd3224e-d440-5b80-9128-d47825799db6/dataexplorer" \
  --collection-name "【PROD】marketdata AI自動売買実行ログ" \
  --keep-days 60 \
  --concurrency 10
```

Then execute after showing the counts and getting explicit confirmation:

```bash
python3 ../scripts/appdb-prune-latest.py ... --keep-days 60 --execute --confirmed
```

Day-mode contract (also implemented in Code Engine `pruneAppDBDocuments(collectionId,
keepDays)` in `Custom AppDB Collections`):

- Deletes only documents whose `createdOn` is older than `now - keepDays`.
- **Keeps** documents whose timestamp is missing/invalid (unknown age is never a delete
  reason) and counts them in `kept_unknown_age_count`.
- Verification fails (exit 3) if any dated document older than the cutoff remains.
- `--keep` (count mode) and `--keep-days` (day mode) are mutually exclusive.

Recommended retention for the marketdata execution log: **60 days** (covers the full
forward-observation window and the offline A/B horizon). Do not use `keep-latest-10` style
pruning on this collection: a count floor silently deletes most of one session.

**Measured volume (2026-09-20, read-only, AppDB 881 docs).** ~28 KB/document; the 5-minute
Workflow writes **288 docs on a US session day** (78 CORE + 66 PRE + 96 NIGHT + 48 ATH) and
~180 on a closed day → **~8 MB/day (≈250 MB/month)**. Steady-state projections:

| Retention | Documents | JSON size | Prune scan (full-scan design) |
|---|---:|---:|---:|
| 60 days | ~15,000 | ~430 MB | ~154 GET pages @100, all docs held in memory |
| 180 days | ~46,000 | ~1.3 GB | ~460 GET pages — memory/time risk |
| 365 days | ~94,000 | ~2.6 GB | ~940 GET pages — not viable |

`pruneAppDBDocuments` (CE `Custom AppDB Collections`) currently **fetches every document**
in 100-doc pages and filters by age in memory, so the daily job's cost scales with the
**collection size**, not with the number of deletions. At the 60-day steady state (arriving
~mid-November 2026) that is ~15k docs / ~430 MB JSON held in one CE invocation — a latent
memory/time risk. Before extending retention beyond 60 days, change the prune to a
cutoff-filtered design (`documents/query` with a `run_timestamp_utc`/`createdOn` `$lt`
filter + batched deletes) so cost tracks daily deletions (~8 MB/day). See
`internal-apps/marketdata/docs/strategy-improvement-proposals-v2-3surface-2026-09-20.md` §7.

## Manual fallback procedure

Use this only if `../scripts/appdb-prune-latest.py` cannot be used or the cleanup rule is not "keep latest N".

### 1. Identify the collection

Identify the collection from the URL or name the user provides (if your organization keeps an AppDB catalog, cross-check it there).

URL pattern: `https://<instance>/appDb/<collectionId>/dataexplorer`

The UUID in the URL is the **collection ID**.

### 2. Authenticate

```bash
INSTANCE="maintenance-instance.domo.com"   # replace with target instance

# Re-login if needed (session lasts ~8 hours)
domo login -i $INSTANCE

REFRESH=$(jq -r '.refreshToken' ~/.config/configstore/ryuu/$INSTANCE.json)

ACCESS_TOKEN=$(curl -s -X POST "https://$INSTANCE/api/oauth2/token" \
  -H "content-type: application/x-www-form-urlencoded;charset=utf-8" \
  -d "client_id=domo:internal:devstudio&grant_type=refresh_token&refresh_token=$REFRESH" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

SID=$(curl -s "https://$INSTANCE/api/oauth2/sid" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['sid'])")
```

Smoke test:
```bash
curl -s "https://$INSTANCE/api/data/v3/datasources?limit=1" \
  -H "X-Domo-Authentication: $SID" | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK' if d.get('dataSources') else 'FAIL')"
```

### 3. Count documents by date

```python
import json, urllib.request

SID = "<paste SID>"
INSTANCE = "<instance>"
COLLECTION_ID = "<uuid>"
BASE_URL = f"https://{INSTANCE}/api/datastores/v2/collections/{COLLECTION_ID}/documents"

all_docs = []
offset = 0
limit = 100
while True:
    req = urllib.request.Request(
        f"{BASE_URL}?limit={limit}&offset={offset}",
        headers={"X-Domo-Authentication": SID}
    )
    with urllib.request.urlopen(req) as resp:
        batch = json.loads(resp.read())
    if not batch:
        break
    all_docs.extend(batch)
    if len(batch) < limit:
        break
    offset += limit

print(f"Total: {len(all_docs)}")

from collections import Counter
counts = Counter(d['createdOn'][:10] for d in all_docs if d.get('createdOn'))
for date, n in sorted(counts.items()):
    print(f"  {date} UTC: {n}")
```

### 4. Set cutoff and confirm delete count

```python
from datetime import datetime, timezone

# "昨日より以前" = before yesterday (今日 = 2026-06-13 → cutoff = 2026-06-12T00:00:00Z)
CUTOFF = datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc)

to_delete = [
    d['id'] for d in all_docs
    if datetime.fromisoformat(d['createdOn'].replace('Z', '+00:00')) < CUTOFF
]
print(f"To delete: {len(to_delete)},  To keep: {len(all_docs) - len(to_delete)}")
```

Show the count to the user. For high-risk collections (if your organization keeps such a list) or counts > 100, pause for explicit confirmation before proceeding.

### 5. Bulk delete

For large deletes, prefer `../scripts/appdb-prune-latest.py` or adapt its `ThreadPoolExecutor` pattern. The old one-by-one loop below is intentionally conservative and can be too slow for thousands of documents.

```python
import time, urllib.error

deleted, failed = 0, []

for i, doc_id in enumerate(to_delete):
    url = f"{BASE_URL}/{doc_id}"
    req = urllib.request.Request(url, method='DELETE', headers={"X-Domo-Authentication": SID})
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                deleted += 1
            else:
                failed.append((doc_id, resp.status))
    except urllib.error.HTTPError as e:
        failed.append((doc_id, e.code))

    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(to_delete)}: deleted={deleted} failed={len(failed)}")
    time.sleep(0.05)   # avoid rate-limiting

print(f"Done: deleted={deleted}, failed={len(failed)}")
```

### 6. Verify

```python
# Re-fetch after deletion
all_docs_after = []
offset = 0
while True:
    req = urllib.request.Request(
        f"{BASE_URL}?limit={limit}&offset={offset}",
        headers={"X-Domo-Authentication": SID}
    )
    with urllib.request.urlopen(req) as resp:
        batch = json.loads(resp.read())
    if not batch:
        break
    all_docs_after.extend(batch)
    if len(batch) < limit:
        break
    offset += limit

print(f"Remaining: {len(all_docs_after)}")
counts_after = Counter(d['createdOn'][:10] for d in all_docs_after if d.get('createdOn'))
for date, n in sorted(counts_after.items()):
    print(f"  {date} UTC: {n}")
```

## Key endpoints (instance API, auth: `X-Domo-Authentication: $SID`)

| Action | Method | Path |
|---|---|---|
| List documents | `GET` | `/api/datastores/v2/collections/<collectionId>/documents?limit=100&offset=0` |
| Query documents | `POST` | `/api/datastores/v2/collections/<collectionId>/documents/query` |
| Delete document | `DELETE` | `/api/datastores/v2/collections/<collectionId>/documents/<docId>` |

> **Note**: Use collection **UUID**, not name, for v2 API. The `/domo/datastores/v1/` path requires a browser session and is not accessible via SID. Use `/api/datastores/v2/` instead.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| GET returns HTML (login page) | Using `/domo/datastores/v1/` path | Switch to `/api/datastores/v2/` |
| 401 on token exchange | Ryuu session expired | Run `domo login -i <instance>` |
| DELETE returns 404 | Doc already deleted or wrong collection | Verify collection ID in URL |
| `/api/content/v1/user` returns nulls | Endpoint doesn't return user for SID; harmless | Test with `/api/data/v3/datasources?limit=1` instead |
