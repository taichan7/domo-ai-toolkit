# Domo API リファレンス

> English: [api-reference.md](api-reference.md)

コマンドラインや AI エージェントから Domo インスタンスと対話するための、実用本位のリファレンスです。認証、よく使うエンドポイント、レスポンスの構造、エラーコード、一般的なパターンを扱います。

---

## 重要: 認証方法

**Puppeteer や Playwright などのブラウザ自動化ツールを Domo の操作に使用しないでください。** 以下の 3 つのいずれかの認証方法で API を直接呼び出してください。

### 3 つの認証方法

| 方法 | 適した用途 | ヘッダー |
|---|---|---|
| **Developer Token (開発者トークン)** | 長期間の自動化、サーバージョブ | `X-DOMO-Developer-Token: <token>` |
| **CLI Session (SID)** | ローカル開発、お手元の AI エージェント | `X-Domo-Authentication: <SID>` |
| **OAuth Bearer** | パブリック Developer API (`api.domo.com`) 用 | `Authorization: Bearer <access_token>` |

### 方法 1 — Developer Token (最も簡単)

1. Domo で **管理者 → 認証 → アクセストークン** に移動
2. **アクセストークンを生成** をクリックし、名前と有効期限を設定
3. 表示されたトークンを直ちにコピー (一度しか表示されません)

```bash
curl -H "X-DOMO-Developer-Token: $TOKEN" \
  "https://$INSTANCE/api/data/v3/datasources?limit=10"
```

### 方法 2 — CLI セッショントークン (AI エージェント利用時に推奨)

Domo CLI (`ryuu`) は `domo login` 実行後、ローカルにリフレッシュトークンを保存します。このリフレッシュトークンをアクセストークンと交換し、さらにすべてのインスタンス API で使えるセッション ID (SID) と交換します。

CLI の設定ファイルは以下に保存されます:
- macOS / Linux: `~/.config/configstore/ryuu/<instance>.domo.com.json`
- Windows: `%USERPROFILE%\.config\configstore\ryuu\<instance>.domo.com.json`

```bash
# インスタンスを指定
INSTANCE="your-company.domo.com"

# リフレッシュトークンを読み込み (Windows は $USERPROFILE、macOS/Linux は $HOME を使用)
REFRESH_TOKEN=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.config/configstore/ryuu/$INSTANCE.json')))['refreshToken'])")

# アクセストークンと交換
ACCESS_TOKEN=$(curl -s -X POST "https://$INSTANCE/api/oauth2/token" \
  -H "content-type: application/x-www-form-urlencoded;charset=utf-8" \
  -d "client_id=domo:internal:devstudio&grant_type=refresh_token&refresh_token=$REFRESH_TOKEN" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# SID と交換
SID=$(curl -s "https://$INSTANCE/api/oauth2/sid" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['sid'])")

echo "Authenticated to $INSTANCE （SID 取得済み — 画面には表示しません。コピー・共有しないでください）"
```

その後は、すべてのリクエストで SID を使用します:

```bash
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/data/v3/datasources?limit=50"
```

### 方法 3 — OAuth Bearer (パブリック Developer API のみ)

`api.domo.com` のエンドポイント専用です。`developer.domo.com → My Account → New Client` でクライアント ID とシークレットを取得し、標準的な OAuth2 client-credentials フローで認証します。

```bash
ACCESS_TOKEN=$(curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
  "https://api.domo.com/oauth/token?grant_type=client_credentials&scope=data" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://api.domo.com/v1/datasets?limit=10"
```

注意: Developer Token は `api.domo.com` では使用できません (401 を返します)。パブリック API には OAuth を使用してください。

---

## 利用可能な API エンドポイント (インスタンス API)

以下のエンドポイントはすべて、`INSTANCE` と `SID` が上記の通り設定済みであることを前提とします。

### データセット

| 操作 | メソッド | エンドポイント |
|---|---|---|
| データセット一覧 | `GET` | `/api/data/v3/datasources?limit=50&offset=0` |
| データセットのメタデータ取得 | `GET` | `/api/data/v3/datasources/{datasetId}` |

- ページサイズは最大 50 件。それ以上を要求すると 400 を返します。
- ページング: 返却件数が 50 未満になるまで `offset` を 50 ずつ増やします。
- 大規模インスタンスではデータセットが 10,000 件を超える場合があります。後述の **スレッド化されたページネーション** を参照してください。

レスポンス例 (抜粋):

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

データセットオブジェクトの主なフィールド:

| フィールド | 意味 |
|---|---|
| `id` | UUID |
| `name` | 表示名 |
| `type` / `dataProviderType` | ソースコネクタ (`DataFlow`、`webform`、`snowflake`、`salesforce` など) |
| `transportType` | `VIEW`、`CONNECTOR`、`SMTP`、`API`、`WEBFORM`、`CLOUD`、`WORKBENCH`、`FEDERATED` |
| `state` | `IDLE`、`SUCCESS`、`ERROR`、`ACTIVE` |
| `rowCount` / `columnCount` | 現在のサイズ |
| `owner` | `{ id, name, type }` |
| `lastUpdated` | 最終データ更新時刻 (epoch ms) |
| `cardInfo.cardCount` | このデータセットを参照するカード数 |
| `cryoStatus` | `ADRENALINE` (有効) または `CRYO` (アーカイブ済) |
| `hidden` | UI で非表示かどうか |

### データセットの SQL クエリ

| 操作 | メソッド | エンドポイント |
|---|---|---|
| SQL の実行 | `POST` | `/api/query/v1/execute/{datasetId}` |

ボディ: `{"sql": "SELECT * FROM table WHERE col = 'val' LIMIT 10"}`

- テーブル名は常に `table` です — データセット自身を指します。
- 標準 SQL がサポートされます: `SELECT`、`WHERE`、`GROUP BY`、`ORDER BY`、`LIMIT`、`LIKE`、`IN`、`COUNT` など。
- スペースを含む列名はバッククォートで囲んでください: `` `Column Name` ``
- `LIMIT 0` は列定義のみを返します — スキーマの確認に便利です。

レスポンス構造:

```json
{
  "columns": ["col_a", "col_b"],
  "rows": [["v1", "v2"], ["v3", "v4"]],
  "metadata": [{ "type": "STRING" }, { "type": "LONG" }]
}
```

### データフロー (Magic ETL)

| 操作 | メソッド | エンドポイント |
|---|---|---|
| データフロー一覧 | `GET` | `/api/dataprocessing/v1/dataflows` |
| データフロー詳細取得 | `GET` | `/api/dataprocessing/v1/dataflows/{id}` |
| データフロー更新 | `PUT` | `/api/dataprocessing/v1/dataflows/{id}` |
| 実行をトリガー | `POST` | `/api/dataprocessing/v1/dataflows/{id}/executions` |
| 実行履歴 | `GET` | `/api/dataprocessing/v1/dataflows/{id}/executions?limit=5&offset=0` |

注意事項:

- 一覧エンドポイントは `limit` / `offset` を無視し、**すべての**データフローを 1 回のレスポンスで返します。
- `?hydrate=full` は**使用しないでください** — 一部のデータフローで 400 を返します。通常の GET でも `actions[]` 全体を含みます。
- PUT はデータフロー定義全体を置き換えます。必ず GET → 修正 → 完全なオブジェクトを PUT の流れで行ってください。
- PUT が成功するたびに `onboardFlowVersion.versionNumber` がインクリメントされます。

データフローオブジェクト (主なフィールド):

```text
id              データフローの数値 ID
name            表示名
runState        "ENABLED" または "DISABLED"
databaseType    Magic ETL の場合 "MAGIC"
lastExecution   { failed, state, errors[] }
actions[]       ETL タイル — 各要素に { id, type, ...config }
```

### カードとダッシュボード

| 操作 | メソッド | エンドポイント |
|---|---|---|
| ページ情報取得 | `GET` | `/api/content/v1/pages/{pageId}` |
| ページ内カード取得 | `GET` | `/api/content/v1/pages/{pageId}/cards` |
| アプリのデータストア取得 | `GET` | `/api/datastores/v1/collections?appId={appId}` |

- App ID とページ ID は `/app-studio/{appId}/pages/{pageId}` のような URL から取得できます。
- ページ内カードはタイトルと URN ID を返しますが、バックエンドのデータセットは返しません。カードとデータセットの対応関係には DomoStats の `Card Datasources` データセットを使用してください。

### ユーザーとグループ

| 操作 | メソッド | エンドポイント |
|---|---|---|
| ユーザー取得 | `GET` | `/api/content/v2/users/{userId}` |
| ユーザー検索 | `GET` | `/api/content/v2/users/search?q={query}&limit=50` |
| グループ一覧 | `GET` | `/api/content/v2/groups?limit=50` |

### OAuth 補助エンドポイント (方法 2 で使用)

| 操作 | メソッド | エンドポイント |
|---|---|---|
| リフレッシュトークンの交換 | `POST` | `/api/oauth2/token` (form: `client_id`、`grant_type=refresh_token`、`refresh_token`) |
| アクセストークンから SID を取得 | `GET` | `/api/oauth2/sid` (header: `Authorization: Bearer <token>`) |

CLI フローのクライアント ID は `domo:internal:devstudio` で固定です。

---

## Custom App SDK (iframe — ryuu.js)

Custom App (Pro Code アプリ) は Domo 上の iframe 内で実行されます。`https://unpkg.com/ryuu.js` を読み込むと `window.domo` オブジェクトが注入されます。セッションは `ryuu_sid` クエリパラメータ経由で iframe に自動的にバインドされるため、**Custom App 内では認証ヘッダーを手動で渡さないでください**。

### `domo.get(url)` / `domo.post(url, body, opts)` / `domo.put(url, body)`

いずれもパース済みの JSON を返す Promise です。`opts.contentType` のデフォルトは `application/json` で、ボディが生 SQL 文字列の場合は `'text/plain'` を渡します。

### iframe から呼び出せる検証済みエンドポイント

| 機能 | メソッド | URL テンプレート | マニフェストバインディング |
|---|---|---|---|
| AI テキスト生成 | `POST` | `/domo/ai/v1/text/generation` | なし (グローバル) |
| AI text-to-SQL | `POST` | `/domo/ai/v1/text/sql` | なし (グローバル) |
| Code Engine 関数呼び出し | `POST` | `/domo/codeengine/v2/packages/<packageAlias>` | `packagesMapping[]` |
| Workflow 起動 | `POST` | `/domo/workflow/v1/models/<workflowAlias>/start` | `workflowsMapping[]` |
| AppDB ドキュメント作成 | `POST` | `/domo/datastores/v1/collections/<name>/documents` | `collectionsMapping[]` |
| AppDB ドキュメント取得 | `GET` | `/domo/datastores/v1/collections/<name>/documents/<id>` | 同上 |
| AppDB ドキュメント更新 | `PUT` | `/domo/datastores/v1/collections/<name>/documents/<id>` | 同上 |
| AppDB クエリ | `POST` | `/domo/datastores/v1/collections/<name>/documents/query` | 同上 |
| データセット行読み取り | `GET` | `/data/v1/<datasetAlias>` (クエリ文字列でフィルタ) | `datasetsMapping[]` |
| データセット SQL クエリ | `POST` | `/sql/v1/<datasetAlias>` (ボディ: 生 SQL、`contentType: 'text/plain'`) | `datasetsMapping[]` |
| 生 ID でデータセットクエリ | `POST` | `/domo/query/v1/execute/<datasetId>` (ボディ: `{sql}`) | なし |
| ユーザー取得 | `GET` | `/domo/users/v1/<userId>?includeDetails=true` | なし |

### マニフェストのバインディング構造

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

マニフェストで宣言した alias が、上記の URL テンプレートの `<alias>` 部分になります。

### SQL エンドポイントのレスポンス構造 (iframe vs サーバー)

- **iframe `POST /sql/v1/<alias>`** は列指向で返します:
  ```json
  { "columns": ["A","B"], "numColumns": 2, "numRows": 25, "rows": [["v1","v2"]] }
  ```
- **サーバー `POST /api/query/v1/execute/<datasetId>`** は同じ構造に加えて、列の型情報を含む `metadata[]` を返します。
- **iframe `GET /data/v1/<alias>`** は行指向 (`{column: value}` オブジェクトの配列) を返します。Domo は AS 別名が既存の列名と一致する場合は小文字化し、それ以外は大文字小文字を保持します。行を読むときは大文字小文字を区別しない参照を使用してください。

### iframe ランタイムコンテキスト (`domo.env`)

プラットフォームはユーザーとセッションの情報を URL パラメータと `domo.env` の両方に注入します:

- `domo.env.userId`、`domo.env.userName`、`domo.env.userEmail`
- `domo.env.customer` (インスタンスのサブドメイン)
- `domo.env.locale`、`domo.env.platform`

これらは iframe URL (`?USER_ID=...&USER_NAME=...&customer=...`) にも反映されるため、ブラウザのネットワークトレースから確認できます。

---

## 失敗した ETL の診断

一般的な手順: すべてのデータフローを取得 → 失敗したものに絞り込み → 失敗した具体的なタイルに掘り下げる。

### ステップ 1 — 失敗を検出

```bash
curl -s -H "X-Domo-Authentication: $SID" "https://$INSTANCE/api/dataprocessing/v1/dataflows" \
  | python3 -c "
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

### ステップ 2 — 個別のデータフローを掘り下げ

```bash
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/<ID>"
```

`lastExecution.errors[].parameters._actionId` を確認して失敗したタイル ID を取得し、その ID を `actions[]` の中から探します。

### よくあるエラーコード

| コード | 意味 | 一般的な修正方法 |
|---|---|---|
| `DP-DSNF` / `DP-61100` | 入力データセットが存在しない | データセットを再作成するか、`LoadFromVault` タイルを削除 |
| `DP-0001` | 列が見つからない | 上流のスキーマが変更された — 列参照を更新 |
| `DP-0059` | 式の構文エラー | 数式を修正 (例: CASE 文の `END` 漏れ) |
| `DP-0118` | コード / モデルタイルのクラッシュ | Python スクリプトまたは AI モデルタイルを確認 |
| `MYSQL-601072` | 結合キーの欠落 | 存在しない列を参照する結合 — 結合キーを更新 |
| `DP-TGTFR` | 行数が不足 | バッチテキスト生成には 100 行以上が必要 |
| `DP-0000` | 不明なエラー | Domo の UI で確認 — API レベルの詳細情報なし |

### タイルタイプ別の確認箇所

失敗した `_actionId` を `actions[]` から見つけたら、以下を確認してください:

| アクションタイプ | 確認するフィールド |
|---|---|
| `ExpressionEvaluator` | `expressions[].expression` |
| `LoadFromVault` | `dataSourceId` |
| `MergeJoin` | `keys1[]` / `keys2[]` |
| `SelectValues` | `fields[].name` |
| `Filter` | `filterList[].leftField` |
| `PythonEngineAction` | `script` |
| `PublishToVault` | `dataSource.guid` |

---

## ETL を API 経由で修正する

```bash
# 1. 現在のデータフローを GET
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID" > dataflow.json

# 2. dataflow.json を修正 (Python、jq、手作業など)

# 3. PUT で保存
curl -s -X PUT \
  -H "X-Domo-Authentication: $SID" \
  -H "Content-Type: application/json" \
  -d @dataflow.json \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID"

# 4. 実行をトリガー
curl -s -X POST \
  -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID/executions"

# 5. 実行結果を確認
curl -s -H "X-Domo-Authentication: $SID" \
  "https://$INSTANCE/api/dataprocessing/v1/dataflows/$ID/executions?limit=1&offset=0"
```

PUT には**データフローオブジェクト全体**を送信してください。部分更新はサポートされていません。

---

## スレッド化されたページネーション (大規模インスタンス向け)

数千件のデータセットを持つインスタンスでは、50 件ずつ順次取得すると遅く、途中で SID が失効する可能性があります。10 ページを並列に取得するパターン:

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

大規模インスタンスでの注意事項:

- SID の有効期間は約 1 時間です。実行途中で 401 が返ったら、再認証して最後に成功した offset から再開してください。
- 進捗をディスクに保存しながら処理してください — `offset = len(all_ds)` に設定すれば再開できます。
- 並列取得は順次取得の約 10 倍高速です。

---

## 正しそうに見えるが動かないエンドポイント

以下は 404 やリダイレクトを返します。古いドキュメントには記載されていますが、現在は使えません:

- `/api/data/v1/datasets` → 404
- `/api/dataset/v3/datasources` → 404
- `/api/datasources` → 404
- `/api/content/v1/datasources` → 404
- `/oauth/token` に `refresh_token` グラント → 302 リダイレクト (代わりに `/api/oauth2/token` を使用)

---

## パブリック Developer API とインスタンス API の使い分け

`api.domo.com` で提供されるパブリック Developer API は、安定して文書化されたサブセットです。パートナー連携や長期間動作する自動化に適しています。本リファレンスのエンドポイントは**インスタンス API** (`<your-instance>.domo.com/api/...`) で、Domo の UI が内部で使っているのと同じ API です。安定はしていますが、公式に公開されている Developer API には正式には含まれていません。

インスタンス API を使う場合:

- パブリック API では公開されていないデータや操作が必要なとき (データフロー内部、App Studio 内部、Governance データセットなど)
- サードパーティアプリではなく、認証されたユーザーとして作業するとき

パブリック Developer API を使う場合:

- パートナー統合を構築する
- 安定した文書化された契約を求める
- ユーザーのマシン外から呼び出す (server-to-server)

同じプロジェクト内で両方を併用することも可能です。それぞれに正しい認証ヘッダーを使ってください (インスタンス API には `X-DOMO-Developer-Token` または `X-Domo-Authentication`、`api.domo.com` には `Authorization: Bearer`)。

---

## 関連リソース

- `../scripts/authenticate.sh` — 認証フローの実行可能スクリプト
- `../scripts/list-datasets.sh` — データセットのページング取得
- `../scripts/query-dataset.sh` — SQL の実行
- `../scripts/diagnose-etls.sh` — 失敗した ETL の検出と分類
- `../templates/pro-code-app/` — 動作する Pro Code アプリの雛形
- `../../AGENTS.md` — このリファレンスを AI エージェントと併用する方法
