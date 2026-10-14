# Domo MCP セットアップ・疎通確認

> English: [domo-mcp.md](domo-mcp.md)

## 確認済みサーバー

| 項目 | 値 |
|---|---|
| Instance | `maintenance-instance.domo.com` |
| Streamable HTTP endpoint | `https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp` |
| 認証header | `X-Domo-Developer-Token: <developer-token>` |
| MCP server | `domo_basic_mcp` version `0.0.1` |
| Negotiated protocol | `2025-03-26` |
| Capabilities | `tools`, `resources` |

2026-07-29 に認証付きの `initialize`、initialized notification、`tools/list`、`resources/list` を再確認しました。現在の公開toolは次の3件です。

| 現在のtool名 | 用途 | 2026-07-13に確認されたDeprecated名 |
|---|---|---|
| `domo_search` | 名前・説明からDomo entity metadataを検索する。 | `SearchTool` |
| `domo_sql_query` | 自然言語の質問を1件以上のDatasetへ問い合わせる。 | `DomoSqlQueryTool` |
| `domo_fileset_query` | index済みFileSet文書から関連excerptを返す。 | `FileSetQueryTool` |

必ず `tools/list` が現在返す名前を使ってください。server versionは引き続き`0.0.1`でしたが、2026-07-29時点では以前のCamelCase名は公開されず、snake_case名が公開されています。

このmanualは`domo_basic_mcp`専用です。公開された3 toolはいずれもread/query操作で、Card、Workflow、Magic ETL dataflow、その他Domo assetを作成するtoolはこのendpointにありません。より広いDomo AI toolkitの機能を、このbasic endpointへ推測で当てはめないでください。

`resources/list` の静的resourceは0件でした。ただし初期化応答は `resources` capabilityを広告しており、resource機能自体が無効という意味ではありません。

2026-07-29に現在の3 toolすべてをread-onlyでend-to-end検証しました。詳細は[確認済みのtool挙動](#確認済みのtool挙動)を参照してください。

## Read-only疎通確認の再実行

repository rootで実行します。

```bash
bash ../scripts/check-domo-mcp.sh
```

tool実行前にliveのdescriptionと`inputSchema`も表示します。

```bash
bash ../scripts/check-domo-mcp.sh --show-schemas
```

認証の優先順は次のとおりです。

1. `DOMO_TOKEN` を `X-Domo-Developer-Token` として使用。
2. 明示的にexportされた `SID` を使用。
3. `maintenance-instance.domo.com` のローカル `domo login` 設定をメモリ内で一時SIDへ交換。
4. ローカルCLI設定がない場合のみ、git対象外の `../scripts/.sid` を使用。

scriptはcredentialやresponse headerを表示せず、終了時に一時response fileを削除し、MCP discovery methodだけを呼びます。別endpointは次のように指定できます。

```bash
DOMO_MCP_ENDPOINT='https://example.domo.com/api/ai/v1/assistant/mcp/toolkits/example' \
  bash ../scripts/check-domo-mcp.sh
```

## Toolの呼び出し方

`check-domo-mcp.sh` はdiscoveryのみです。実際にtoolを呼び出すには次を使います。

```bash
bash ../scripts/call-domo-mcp-tool.sh <ToolName> '<json-arguments>' [endpoint]
```

例（2026-07-29に検証済み）:

```bash
bash ../scripts/call-domo-mcp-tool.sh domo_search \
  '{"query":"*","entityTypes":["DATASET"],"count":5}'
```

このscriptは疎通確認と同じ `initialize` / `notifications/initialized` handshakeを行った後、`tools/call` を呼び出し、parseした結果をstdoutへ出力します。認証の優先順は `check-domo-mcp.sh` と同じです。疎通確認と異なり、これは実際のtoolを実行するため、Domoの実データが返る可能性があります。

tool実行前に必ず次を行ってください。

1. `bash ../scripts/check-domo-mcp.sh --show-schemas` を実行し、現在のtool名と`inputSchema`を使う。toolkitはrepositoryとは独立に更新される可能性がある。
2. read-onlyであることを確認するか、write・delete・workflow triggerなど可能性がある操作は `AGENTS.md` に従い明示的なユーザー確認を得る。
3. 結果はDomoの実データとして扱う。生のtool出力をhandoff、issue、PR、shared noticeへ貼り付けず、要約すること。

### 現在のinput schema（2026-07-29）

`domo_search`:

| field | 現在のschema |
|---|---|
| `query` | optional string。wildcardは`*`。運用上は明示する。 |
| `entityTypes` | optional array。`APP`、`DATA_APP`、`BEAST_MODE`、`CARD`、`DATASET`、`FILE_SET`、`PAGE`、`WORKFLOW_MODEL`、`APP_CARD`。運用上は明示する。 |
| `count` | optional integer、`1`–`100`。defaultは`20`。 |
| `offset` | optional integer、最小`0`。defaultは`0`。 |

tool全体のdescriptionには`GROUP`と`USER`も記載されていますが、現在の`entityTypes` field descriptionには含まれていません。これら2値を検証するまではfield description側を安全なcontractとして扱ってください。

`domo_sql_query`:

| field | 現在のschema |
|---|---|
| `dataSourceIds` | required。Dataset ID stringのarray。tool descriptionでは、直近contextで利用可能なDataset IDをすべて含め、service側に関連sourceを選ばせるよう指示されている。 |
| `userQuestion` | required。Datasetに対する自然言語の質問。 |

`domo_fileset_query`:

| field | 現在のschema |
|---|---|
| `fileSets` | required。`{ "fileSetId": "...", "path": "..." }`のarray。`fileSetId`はrequired。`path`はoptionalだが、指定する場合はfull path、rootは空文字で指定できる。 |
| `query` | required。semantic search用の自然言語query。 |
| `topK` | required integer、`1`–`100`。 |

### 確認済みのtool挙動

2026-07-29に次のread-only挙動を確認しました。

- `domo_search`はDatasetとFileSetのmetadata（`id`、`name`、`title`、`description`、`totalCount`）を返した。型を明示したwildcard検索と、型を明示した自由文Dataset検索の両方が成功した。
- `domo_sql_query`は小規模sample Datasetのschema・row countを返し、その後、日本語の自然言語質問からgroup別top 3集計にも成功した。callerがraw SQLを渡すtoolではない。
- `domo_fileset_query`は`fileId`、full `path`、関連度`score`付きのmatching excerptを返した。別の正常なqueryでは`[]`が返ったため、空arrayは「関連するindex済みpassageが見つからない」場合があり、transport failureとは限らない。
- FileSet queryのresultはexcerptであり、file全体のdownloadではない。descriptionは全文取得用に別の`FileSetReadTool`を案内しているが、このtoolkitでは2026-07-29時点で公開されていない。

### レスポンス形式の注意点

Streamable HTTPのレスポンスはServer-Sent Eventsで、`data:<json>` 形式の行が1つ以上含まれます。`tools/call` のレスポンスには `notifications/progress` イベントが最終resultと同じstreamに混在することがあります。`data:` prefixの後にspaceがない場合（`data: {...}` だけでなく `data:{...}` もある）があるため、parserは `data:` を取り除いたうえで、SSEの最初や最後の行を単純に使うのではなく `id` が一致するJSON-RPC messageを選ぶ必要があります。`call-domo-mcp-tool.sh` はこれに対応済みです。

### 確認されたエラー

2026-07-13にはDeprecated名`SearchTool`へ`entityTypes`なしの自由文`query`を送るとHTTP 500になりました。2026-07-29には現在名`domo_search`へ`entityTypes`を明示すると、`query: "*"`と自由文queryの両方が成功しました。endpointが壊れていると判断する前に、現在のtool名を使い、`entityTypes`を明示してください。

## 認証の注意点

常設のMCP clientでは、Domoでtoolkitを有効にした際に示されるDeveloper Tokenを `X-Domo-Developer-Token` で送ってください。値はenvironment variableまたはclientの保護されたsecret storageに置き、commitしないでください。

Domo CLIの `refreshToken` は必ずしもDeveloper Tokenではありません。今回確認したローカル設定は `devToken: false` で、このrefresh tokenを直接 `X-Domo-Developer-Token` に指定すると `401` になりました。疎通確認scriptはCLI credentialを短命SIDへ交換して `X-Domo-Authentication` で利用できますが、静的なclient設定には、そのclient自身がDomo sessionをrefreshできない限りtoolkit用Developer Tokenを使います。

## Client設定

secret placeholderは実行時に置き換えてください。tokenをrepositoryへ直接書かないでください。

### Codex

ローカルCodex CLIはStreamable HTTP URLに対応していますが、`mcp add` commandが直接公開する認証optionはBearer Tokenです。Domoにはcustom headerが必要なため、Codexの `config.toml` でenvironment variableをheaderへmapします。

```toml
[mcp_servers.domo_basic]
url = "https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp"
env_http_headers = { "X-Domo-Developer-Token" = "DOMO_TOKEN" }
```

Codexを起動する環境で `DOMO_TOKEN` をexportし、Codexを再起動して確認します。

```bash
codex mcp list
```

### Claude Code

Claude CodeはHTTP MCP serverへcustom headerを指定できます。

```bash
claude mcp add --transport http --scope user domo_basic \
  'https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp' \
  --header "X-Domo-Developer-Token: $DOMO_TOKEN"
claude mcp get domo_basic
```

このcommandは展開後のheaderをuserのClaude設定へ保存する可能性があります。導入済みClaude versionの保存方式とfile permissionを確認してください。environment-variable header参照を使えるclientではそちらを優先します。

### Claude Desktop、Cursor、VS Code、その他のMCP client

remote Streamable HTTP serverとして次を指定します。

```json
{
  "url": "https://maintenance-instance.domo.com/api/ai/v1/assistant/mcp/toolkits/domo_basic_mcp",
  "headers": {
    "X-Domo-Developer-Token": "<developer-token-from-secure-storage>"
  }
}
```

外側の設定keyやenvironment-variable展開記法はclient versionごとに異なります。remote HTTP/Streamable HTTP設定を選び、custom headerを追加し、tokenはrepository外に保存してください。このserverはlocal `stdio` commandではなく、認証headerも `Authorization: Bearer` ではありません。

## 他のAI向け確認checklist

1. `AGENTS.md`、`domo-auth.md`、この文書を読む。
2. endpoint hostが対象Domo instanceと一致することを確認する。
3. tokenやraw headerを表示せず `bash ../scripts/check-domo-mcp.sh` を実行する。
4. `initialize`、initialized notification、`tools/list`、`resources/list` がすべて2xxであることを確認する。
5. 表示されたtool名を上記の確認済み一覧と比較する。差分は障害ではなくtoolkit更新の可能性もある。
6. tool実行前に `bash ../scripts/check-domo-mcp.sh --show-schemas` を実行し、repositoryのread/write安全ルールを適用する。
7. 実際にtoolを呼び出すには `bash ../scripts/call-domo-mcp-tool.sh <ToolName> '<json-arguments>'` を使う。[Toolの呼び出し方](#toolの呼び出し方)を参照。
8. Dataset、FileSet、search、その他production mutationには、Domo APIを直接使う場合と同じ承認・確認ルールを適用する。

## Troubleshooting

| 症状 | 主な原因 / 対応 |
|---|---|
| `401` | credential未設定・期限切れ、またはCLI refresh tokenをDeveloper Tokenとして誤使用している。 |
| `initialize` 成功後のcallが `400` | `Mcp-Session-Id` を保持し、discovery call前に `notifications/initialized` を送る。 |
| clientが `Authorization: Bearer` を送る | custom `X-Domo-Developer-Token` headerへ変更する。 |
| `resources/list` が空 | 今回も0件で正常。公開toolとそのschemaを確認する。 |
| clientがcustom HTTP header非対応 | 対応client/versionを使う。tokenを埋め込んだwrapperをgitへ追加しない。 |
| `tools/call` が `500` を返す | schema discoveryを再実行し、現在のsnake_case tool名を使い、具体的なrequest（例: `domo_search`へ`entityTypes`を追加）で再試行する。 |
| `domo_fileset_query` が `[]` を返す | call自体は正常な場合がある。明確なqueryへ変更し、`fileSetId`とfull `path`を確認し、FileSetがindex済みか確認する。 |
| `tools/call` のresponseがJSONとしてparseできない | SSEの `data:` prefixにspaceがない場合がある。また、progress notificationがresultと同じstreamに混在する。`id` が一致するJSON-RPC messageを選ぶこと。上記「レスポンス形式の注意点」を参照。 |

## Securityと変更境界

- Developer Token、SID、refresh token、MCP session ID、cookie、認証済みraw logをcommitしない。
- tool discoveryはread-onlyだが、tool callの安全性は選択したtoolとargumentで決まる。
- Domo側でtoolkitがrepositoryとは独立に更新される可能性があるため、毎回tool schemaを確認する。
- production write、delete、deploy、workflow triggerなどのmutationには `AGENTS.md` に従い明示的なユーザー確認が必要。
