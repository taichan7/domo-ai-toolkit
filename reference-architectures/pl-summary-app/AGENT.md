# pl-summary-app — AI Agent 引き継ぎノート

このファイルは AI エージェントが本プロジェクトを引き継ぐための情報をまとめたものです。
全体像・デプロイ手順は [README.md](README.md) を参照してください。

---

## インスタンス・認証

> **対象インスタンス / 別インスタンスへの再現**: `maintenance-instance.domo.com` は**保守・検証用のリファレンス
> インスタンス**で顧客環境ではない。配布先では `export DOMO_INSTANCE=<your-instance>.domo.com` で対象を
> 指定し、`domo login -i "$DOMO_INSTANCE"` で認証する。下の「重要 ID 一覧」は保守用インスタンスの実値で、
> `sync-manifest`（データ／コレクション）と `app-studio`（埋込カードの context mapping）が対象インスタンスの
> 実 ID へ**名称で発見して張り替える**ため手編集は不要。**ゼロからのデプロイ正典は
> [docs/setup-guide.md](docs/setup-guide.md)。**

```bash
export DOMO_INSTANCE=<your-instance>.domo.com   # 保守用は maintenance-instance.domo.com
domo login -i "$DOMO_INSTANCE"                  # ブラウザ SSO。トークン不要
```

- `scripts/provision_domo.py`（データ層）と `domo publish` はこのログインだけで動く（configstore を読む）。
- **`scripts/provision_workflows.py`（ワークフロー層）、raw curl、`SID` を要求するスクリプト
  （`scripts/deploy_dataflow_prompt.py`・レガシー `scripts/deploy_code_engine.py`）** は、開発者トークンか
  セッション SID が要る:
  - **開発者トークン**: `config/secrets.env`（雛形 `config/secrets.env.example`・gitignore 済み）に
    `DOMO_DEVELOPER_TOKEN` を置き、`set -a; . config/secrets.env; set +a` で読み込む。`provision_workflows.py`
    はこれを直接使い、curl は `-H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN"` で使う。
  - **セッション SID**（`INSTANCE`＋`SID` を要求するスクリプト用）は、`domo login` セッションから発行する
    （ヘルパは [README.md](README.md) の「ローカル開発フロー › 前提」）。

---

## 重要 ID 一覧

| リソース | ID / 値 |
|----------|---------|
| DataFlow | `2042` |
| AppDB Collection ID | `ca132957-d14d-4fa0-9c69-3e6721d27141` |
| AppDB Collection 名 | `店舗別損益AI要約` |
| WF-01 Model ID | `d60ac21b-e1c7-4e6d-bffd-e904e39ac27d` |
| 統合サブWF（WF-02）Model ID | `cf3b78c2-eed1-4f55-a7d5-8004a36fbe39`（旧 WF-02 を再利用・旧 WF-03〔全社〕を統合） |
| 保存CE パッケージ ID（`report_api.py` / `pl_report_api`） | `43e0a52b-83df-4f52-a2bf-1a3634898215` |
| dedupe CE パッケージ ID（`appdb_maintenance.py`・レガシー/フロー非配線） | `4c3f8e59-5fe7-4bb2-b0cd-0959b5efae25` |
| App Studio App ID | `496788406` |
| App Studio Page ID | `623741214` |
| App Studio URL | https://maintenance-instance.domo.com/app-studio/496788406/pages/623741214 |
| Pro-Code App ID | `08463c98-38a9-4caa-a762-b857a37e2826` |
| Pro-Code Card ID | `416610471` |
| 開発ガイド design ID（`dev-guide-app`・App Studio ページ2） | `cd dev-guide-app && domo publish` で払い出し → `dev-guide-app/manifest.json` の `id` に反映（配布時は builder が除去） |
| Dataset alias `summary` | `e05581f1-d70a-474d-91f3-f5a2080c9d05` |
| Dataset alias `detail` | `a1ba80ca-147e-4ac8-8464-5867d665860e` |
| Dataset alias `trend` | `9e330baf-c643-4414-a2ec-2e9ef773c8d0`（`OUT｜P/Lトレンド（店舗×月）`・2,400行） |
| Dataset alias `dept` | `d297d01a-0003-45fa-b9f9-7a65727f26e2`（`OUT｜P/L事業部別（部門×月）`・48行） |

---

## データフロー（出力ハブ）

DataFlow 2042（Magic ETL v2）が生成する 4 つの出力データセットが全体のハブ:

| データセット名 | 用途 |
|--------------|------|
| `OUT｜P/L明細（店舗×勘定×月）` | 勘定科目レベル明細。統合サブWF（WF-02）の AI がコンテキスト（alias `detail`）として参照 |
| `OUT｜P/L要約（店舗×月）` | 店舗×月サマリー。WF-01 が SQL クエリで取得して統合サブWF（WF-02）へ渡す。統合サブWF の AI もコンテキスト（alias `summary`）として参照。`店舗別AIサマリー`／`全社AIサマリー` 列（ETL の TextGeneration タイル生成）と、SQL `CASE` で機械確定した `状態ラベル` 列（短文・長文が転記する単一の真実）を含む |
| `OUT｜P/Lトレンド（店舗×月）` | `SQL｜トレンド集計（店舗×月）` が生成する店舗×月×{rev,profit}。Pro-Code のトレンドチャート／ランキングドリルが live 参照（alias `trend`） |
| `OUT｜P/L事業部別（部門×月）` | `SQL｜事業部別集計（部門×月）` が生成する部門×月×{rev,cogs,variance}。Pro-Code の事業部別タブが live 参照（alias `dept`） |

Magic ETL v2 は draft/version/release がなく **その場編集**（GET→PUT）。TextGeneration タイル2枚
（`店舗別AIサマリー生成`／`全社AIサマリー生成`）のプロンプトは正本 md から `scripts/deploy_dataflow_prompt.py`
で安全にデプロイする（backup→対象タイルの `instructions` のみ差替→PUT→round-trip 厳密検証→復元可能。
`RUN=1` で AI 列再生成の再実行までトリガー）。Python タイルやタイル構成は Domo ETL 画面で編集。

DataFlow 定義の再取得:
```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
curl -s -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" \
  "https://$DOMO_INSTANCE/api/dataprocessing/v1/dataflows/2042" \
  -o dataflow/2042.json
```

---

## AppDB スキーマ

統合サブWF（WF-02）の店舗/全社ブランチが `pl_report_api(operation="save", request={collection_id, document})` で保存するドキュメント構造:

```jsonc
{
  "doc_key": "S001-2024-11-Actual",   // "{store_id}-{period}-{scenario}" or "ALL-{period}-{scenario}"
  "store_id": "S001",                 // 全社サマリーは "ALL"
  "location_name": "渋谷店",          // 全社サマリーは "全店舗サマリー"
  "period": "2024-11",
  "risk_level": "High",
  "prefecture": "東京都",
  "city": "渋谷区",
  "scenario": "Actual",
  "region": "関東",
  "generated_at": "2024-11-30T12:00:00Z",
  "source_table": "OUT｜P/L要約（店舗×月）",
  "total_sales": 12345678,
  "profit_margin": -2.3,
  "personnel_ratio": 28.5,
  "analysis_html": "<h1>渋谷店 分析</h1>..."
}
```

フロントエンドは `content.store_id`（店舗は `店舗ID`、全社は `"ALL"`）で検索し、`generated_at` 降順の最新1件の `content.analysis_html` を描画する。店舗名（`location_name`）は改名の影響を受けるため検索キーには使わない（`store_id` は不変）。

AppDB ドキュメント確認:
```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
# コレクション ID は sync-manifest 後の manifest.json / verify 出力を正とする（インスタンス別）
curl -s -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" \
  "https://$DOMO_INSTANCE/api/datastores/v1/collections/ca132957-d14d-4fa0-9c69-3e6721d27141/documents?limit=10" \
  | python3 -m json.tool
```

---

## ワークフロー操作

### 最新定義の再取得（全2本）

統合により live モデルは **2本**（WF-01＋統合サブWF）。旧 WF-03（`d35c9b64-...`）は削除済みなので取得しない。

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
H="X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN"

for WF_ID in \
  d60ac21b-e1c7-4e6d-bffd-e904e39ac27d \
  cf3b78c2-eed1-4f55-a7d5-8004a36fbe39; do

  ACTIVE=$(curl -s -H "$H" \
    "https://$DOMO_INSTANCE/api/workflow/v2/models/$WF_ID" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['activeVersions'][-1])")

  curl -s -H "$H" \
    "https://$DOMO_INSTANCE/api/workflow/v2/models/$WF_ID/versions/$ACTIVE/definition" \
    -o "workflow/${WF_ID}_definition.json"
  echo "Downloaded $WF_ID v$ACTIVE"
done
```

ダウンロード後、WF-01 は `WF-01_main_loop.json`、統合サブWF は `WF-02_report_ai.json` にリネームすること（README 参照）。

### WF-01 を手動実行（全店舗 AI 生成トリガー）

手動トリガーは `instances/message` エンドポイントで行う（検証済み。`messageName` は `"manual"`）:

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
curl -s -X POST -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" -H "Content-Type: application/json" \
  "https://$DOMO_INSTANCE/api/workflow/v1/instances/message" \
  -d '{"messageName":"manual","modelId":"d60ac21b-e1c7-4e6d-bffd-e904e39ac27d"}' \
  | python3 -m json.tool   # -> 起動した instance {id, modelVersion} を返す
```

### 実行ステータス確認

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
curl -s -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" \
  "https://$DOMO_INSTANCE/api/workflow/v1/instances/{INSTANCE_ID}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])"
# IN_PROGRESS / COMPLETED / 等を返す。/status サフィックスや v2 は 403/404 になるので使わない
```

> **注意**: セッション SID は数分で失効する。`me` エンドポイントが 401、または workflow エンドポイントが 403 を返したら `domo login -i "$DOMO_INSTANCE"` で入り直す（SID を使う場合は README「ローカル開発フロー › 前提」のヘルパで再発行）。開発者トークン方式（`X-DOMO-Developer-Token`）は失効が緩く非対話向き。

> **カバレッジと収束**: 統合サブWF（店舗ブランチ）は非同期（`wait:False`）で投入されるため、AI 書込みの一時失敗により 1 回の実行では一部店舗（従来実測 10〜15%）が再生成されないことがあった。現在は WF-01 の店舗ループに **「15秒待機｜同時実行数を平準化」タイマー**を挿入して非同期投入のペースを抑え、さらに保存CE `pl_report_api(save)` が **per-save で同一 `doc_key` の厳密に古い版だけを削除**する（取りこぼしても既存の正レポートは消えない＝前回分が残りフロント表示は途切れない）ため、1 回の実行でおおむね収束する。約 100 店舗 × 15 秒 ≈ **25 分**がディスパッチ所要（デモ前の一回限りの populate）。間隔は `PL_PARENT_INTERVAL_SECONDS` で調整可。**よって「WF-01 を2回連続実行」は必須ではなく安全網**（確実な全再生成を期す場合のみ）。


---

## Pro-Code App デプロイ

```bash
# 対象インスタンスへログイン済みであること（domo publish は configstore mtime 最大のインスタンスへ出版する）
domo login -i "$DOMO_INSTANCE"
# 複数インスタンス併用時は出版直前に対象 configstore を touch して mtime を最大化:
touch ~/.config/configstore/ryuu/"$DOMO_INSTANCE".json

cd pro-code && domo publish && cd ..
```

- `manifest.json` の `collectionsMapping[0].name` は `"店舗別損益AI要約"` を維持すること
- `datasetsMapping` の `alias` (`summary`, `detail`, `trend`, `dept`) を変えないこと
- **必ず `pro-code/` 直下で実行する**（親ディレクトリから実行すると `findManifest` が `*/manifest.json` を拾い、
  バンドルが `pro-code/` プレフィックス付きの全ツリー構成で出版されてアプリが壊れる）
- **`domo publish` は configstore の mtime 最大のインスタンスへ出版する**（`-i` フラグなし）。複数インスタンスを
  並行使用中は出版直前に対象の configstore を `touch` し、直後に出力の `Publishing ... to <instance>` を確認する
- **alias を追加/変更したら `provision_domo.py app-studio` で context mapping を同期する**: 埋込済みカードの
  App Framework context は manifest 変更に自動追随せず、未マッピングの alias は proxy で 400
  `DA0004: ... not be found in the mapping section of the design or app manifest.json file` を返す。
  **context mapping が空のインスタンスは manifest がフォールバックとして使われる**（maintenance-instance の現行カードがこれに該当＝同期不要）
  が、**非空の mapping は manifest を上書きする**ため、その場合は全 alias（trend/dept 含む）を同期しないと新 alias が使えない
  （2026-09-16 に他インスタンスで発生 → `reconcile_app_studio_context` を追加。テストは `tests/test_provision_domo.py`）

---

## AI プロンプト修正手順（API デプロイ）

**一貫性コントラクト**: 4面の AI サマリー（ETL 店舗短文・ETL 全社短文・統合サブWF 店舗ブランチ長文・統合サブWF 全社ブランチ長文）は
語彙・閾値・問題店舗指標を [prompts/prompt_shared_conventions.md](prompts/prompt_shared_conventions.md)（単一の真実）に
揃える。プロンプトを触る前に必ず読むこと。要点: 全社は4値（好調≥8%／堅調5-8%／要注意0-5%／不振<0%）、
店舗は5値（＋回復基調＝利益率<0 かつ 前月比利益変化率>0）。**店舗の状態ラベルは SQL `CASE` で機械確定した
`状態ラベル`（=`state_label`）列が正本で、ETL 短文タイルも WF-02 長文も再判定せず転記する**（別モデル間の
境界判定の食い違いを構造的に排除）。全社の問題店舗視点は **純利益ワースト**、予算差異は全社集計としてのみ言及。

### Workflow プロンプト（統合サブWF＝店舗/全社の2ブランチ）

統合サブWF（WF-02）は AI_AGENT が **2つ**（店舗ブランチ＝`prompt_wf02_store.md`／全社ブランチ＝
`prompt_wf03_summary.md`）。プロンプトは Domo 画面での貼り付け不要で、`scripts/provision_workflows.py`
が正本 md から両ブランチの `instructions` を再取り込みし、WF-01 を新 sub バージョンへ再ピンするところまで担う
（リリース済みは不変なので新 draft を作って昇格する安全パターン）。

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN を読み込む（インスタンス・認証 参照）

# 1. 正本 md を編集（prompt_wf02_store.md＝店舗ブランチ / prompt_wf03_summary.md＝全社ブランチ）
# 2. 両ブランチの instructions を md から再取り込み（draft→PUT→round-trip検証→release）
python3 scripts/provision_workflows.py subflow --apply --release
# 3. WF-01 を新 sub バージョンへ再ピン
python3 scripts/provision_workflows.py mainflow --apply --release
# --release を付けないと draft 検証まで（round-trip 確認）で停止する
```

デプロイ後、WF-01 を手動実行して AppDB に期待通りのドキュメントが生成されるか確認する。

> **レガシー**: `scripts/deploy_wf_prompt.py` は AI_AGENT が1つの前提のためレガシー（統合サブWFは2つ）。
> `scripts/repin_wf01.py` もレガシー（再ピンは `provision_workflows.py mainflow` が担う）。

### DataFlow の TextGeneration プロンプト（ETL 短文サマリー）

ETL 側の店舗／全社短文サマリー（`店舗別AIサマリー`／`全社AIサマリー` 列）は正本 md
（`prompt_dataflow_store_summary.md` / `prompt_dataflow_company_summary.md`）を編集し
`scripts/deploy_dataflow_prompt.py` でデプロイする（詳細は [README.md](README.md#dataflow-の修正) 参照）:

```bash
# INSTANCE＋SID は「インスタンス・認証」のセッション SID 発行ヘルパで設定しておく（このスクリプトは SID を要求する）
RUN=1 python3 scripts/deploy_dataflow_prompt.py 2042 \
  店舗別AIサマリー生成 prompts/prompt_dataflow_store_summary.md \
  全社AIサマリー生成   prompts/prompt_dataflow_company_summary.md
```

正本 md の指示文は ` ``` ` フェンスブロック内に置く（スクリプトがそこを抽出する）。live 定義を
backup → 対象タイルの `instructions` のみ差替 → PUT → GET round-trip 厳密検証（アクション数・id・
`gui` 無変更、変更は対象タイルのみ）。検証失敗時は backup を PUT で復元して中断する。

---

## Code Engine（保存API `report_api.py` ＋ レガシー `appdb_maintenance.py`）

### 保存API（現役）: `report_api.py` / `pl_report_api`

- **パッケージ名 / ID**: `店舗別損益AI要約｜レポートAPI` / `43e0a52b-83df-4f52-a2bf-1a3634898215`
- **公開関数**: `pl_report_api(operation, request)`（統合サブWFの店舗AI・全社AIが保存ツールとして呼ぶ単一ディスパッチャ）
  - `operation="save"`（`request={collection_id, document}`）: AppDB 保存＋**同一 `doc_key` の旧版（サーバー `createdOn` が厳密に古いもの）だけを削除**＝重複除去を保存に内包。必須フィールド（`doc_key`/`store_id`/`location_name`/`analysis_html`）欠落は POST 前に弾き、既存の正レポートを巻き添え削除しない門番付き
  - `operation="validate"`（`request={collection_id, doc_key}`）: 保存前の軽い識別子検証（任意）
- 認証はランタイム注入（`import codeengine`）。`collection_id` は GUID 形状のみ検証＝**インスタンス非依存**
- **デプロイ**: `scripts/provision_workflows.py ce --apply`（draft→PUT→round-trip検証→release）。CE 更新後は `ce → subflow → mainflow` の順で流す（`subflow` が AI エージェントの保存ツール配線を担う）

### レガシー（フロー非配線）: `appdb_maintenance.py` / `dedupe_appdb_documents`

⚠️ **WF-01 からは配線を外した**（dedupe は現役の `pl_report_api(save)` に内包）。コレクション全体の一括 dedupe を行う**手動／バッチ用ユーティリティ**としてのみ残置する。

- **パッケージ ID**: `4c3f8e59-5fe7-4bb2-b0cd-0959b5efae25`（`dedupe_appdb_documents(collection_id)`・最新 v1.0.5・`collection_id` は必須引数＝既定値なし）
- 認証はランタイム注入（`import codeengine`）。旧 `DOMO_TOKEN` シークレットは不要
- デプロイ（レガシー・新バージョン作成＋リリース）:

```bash
# INSTANCE＋SID は「インスタンス・認証」のセッション SID 発行ヘルパで設定しておく（このレガシースクリプトは SID を要求する）
RELEASE=1 python3 scripts/deploy_code_engine.py version \
  4c3f8e59-5fe7-4bb2-b0cd-0959b5efae25 \
  code-engine/appdb_maintenance.py 1.0.6
# 新規パッケージ作成は: create NAME DESC CODE_FILE "fnName:fnDesc"
# 既存最新は v1.0.5。新 semver は既存・過去に削除した版と重複させないこと（重複は HTTP 500 を返す）
```

> **移植（他インスタンス）**: 現行 v1.0.5 は `DEFAULT_COLLECTION_ID` を廃止し `collection_id` を
> **必須引数**化したので、ソースにコレクション GUID を持たない＝**インスタンス非依存**。移植先では正本
> `appdb_maintenance.py` をそのままデプロイし、CE ノード入力 `collection_id` を移植先の変数
> （dataList のコレクション ID）へマッピングするだけでよい（GUID の書き換えは不要）。
> **単体テストは入力に `collection_id` を必ず与える**（必須引数のため未指定だと実行できない）。
> CE の**単体テストは常に「最新版」を開く**点に注意（最新版が壊れていると単体テストが失敗する）。
>
> ⚠️ 参考（解消済みの過去事例）: v1.0.3 は Domo UI での手編集で 35 行目の既定値 `DEFAULT_COLLECTION_ID`
> が消え `def dedupe_appdb_documents(collection_id: str = ) -> Dict[str, Any]:` となり構文エラー
> （`ast.parse` NG）になった。破損版が最新だと単体テストで
> `SyntaxError at line 62 of /var/task/executor.py: invalid syntax (function.py, line 35)` ＋ 空入力由来の
> `JSONDecodeError at line 49 of /var/task/app.py`（`/var/task/app.py`・`executor.py` は Domo ランタイム
> 土台＝自コードではない）が出た。既定値ごと廃止した現行版では同種の破損は起きない。**正本ソースから
> コピーする**（壊れた最新版からコピーしない）原則は不変。

REST で手動 dedupe する場合は `content.doc_key` ごとに `content.generated_at` 文字列降順の
最新1件を残し、残りを `DELETE /api/datastores/v1/collections/{id}/documents/{docid}` で削除する。

### WF-01 の改修とワークフロー層の配備（`provision_workflows.py`）

WF-01（最新 **v1.0.21**）は **reference-app の親Workflow 流**に再構成した: 全社と店舗を
**並列**に走らせ、**終了ノードは2つ**（本線＝店舗ループ／全社ブランチが各々独立終端）。`開始 → 店舗別SQL`
を起点に、本線（店舗ループ: 単一店舗→整形→15秒待機→店舗子WF→次店舗?→終了#1、戻りはカウンタ経由）と、
店舗別SQL から**フォークした全社サイドブランチ**（全店舗SQL→整形→全社子WF→終了#2）を並走させる。先頭の
`AppDB重複除去` CE ノードは撤去済み（dedupe は保存CE `pl_report_api(save)` に内包）。2つの SUB_FLOW は
統合サブWF `cf3b78c2` v1.0.13 を `report_type`（本線=`store`／全社=`company`）付きで呼ぶ。
**座標・エッジ経路は数学的レイアウトエンジン**（`set_grid`/`route_*`/`ci_style_mainflow_definition`）が
グリッド（レーン×行）から算出し、PUT 前に `validate_layout` が重なり0・経路貫通0 をゲートする＝再デプロイ
してもレイアウトが崩れない。数学モデルは `scripts/provision_workflows.py` 内に実装している（配布対象外のワークスペース内部スキルには依存しない）。

これらの改修・再ピン・旧 WF-03 削除は `scripts/provision_workflows.py` が担う（サブコマンド `provision` /
`ce` / `subflow` / `mainflow` / `delete-wf03` / `verify` / `all`、`--apply` 実行・`--release` でリリース。いずれも
**発見/作成（または draft 作成）→ PUT → GET round-trip 検証 → release** の安全パターンで、検証失敗時は
release せず active 版を無傷に保つ。悪い draft は `DELETE .../versions/{draft}` で破棄）。

- **`provision`**: ⭐**ゼロからの（空の）インスタンスへ全ワークフロー層を配備**（CI の provision_platform.py 相当）。
  CE・統合サブWF・WF-01 を**名称で発見または新規作成**（`ensure_model`＝inventory の ensure_workflow_model
  相当・他人作成でも再利用し重複作成しない）→ 新規モデルは版 1.0.0 を建て、既存は次 patch → **束縛を対象
  インスタンスの実 ID へ再束縛**（`build_wf01_definition`: CollectionId 変数値＋全 DATASET_QUERY_TASK の
  `dataset.value` を `resolve_collection_id()`／manifest の summary へ張替＝保守用 GUID を顧客環境へ焼き込まない。
  未存在モデルは `workflow/WF-01_main_loop.json` を seed に）→ `validate_layout` → release。**前提: 先に
  `provision_domo.py` でデータ層を作る**。`--apply` 時、AppDB コレクション／summary DS が未解決なら**明示失敗**
  （門番）。既存インスタンスでは発見・再利用するので移行にも使える単一経路。live 実証済み（使い捨て
  `zz-pl-dist-test-*` モデルで create→版1.0.0→round-trip→release→正しい再束縛/再ピンを確認後に削除）。
- **`subflow`**: 統合サブWFの両ブランチ instructions（md）・保存ツール `pl_report_api` 配線・コンテキスト
  （`summary`/`detail`）・冒頭の待機タイマー（既定5秒）を再構築
- **`mainflow`**: WF-01 を CI 流（並列サイドブランチ＋終了2つ）へ再構成＝役割同定（type/functionName/配線）
  →グリッド配置→エッジ経路算出→`validate_layout`→新 sub バージョンへ再ピン。dedupe ノードは撤去（無ければ no-op）
- **`delete-wf03`**: 不要になった旧 WF-03 モデル（`d35c9b64-...`）を削除
- 環境変数（配布物には焼き込まない）: `PL_EMAIL_PERSON_RECIPIENTS`・`PL_PARENT_INTERVAL_SECONDS`（既定15）・
  `PL_CHILD_SETTLE_SECONDS`（既定5）・`PL_WF01_MODEL_ID`/`PL_SUBFLOW_MODEL_ID`/`PL_WF03_MODEL_ID`・
  `PL_DEDUPE_CE_PACKAGE_ID`・`PL_WF01_MODEL_NAME`/`PL_SUBFLOW_NAME`/`PL_BUSINESS_COLLECTION`（`provision` の
  発見キー＝名称。別名デモや使い捨てテスト時に差し替え）

> **子WF（統合サブWF）を更新したら WF-01 を再ピンする**: WF-01 は各 SUB_FLOW ノードの `data.modelVersion`
> で呼び出す子バージョンを固定している。サブWFを bump したら `provision_workflows.py mainflow --apply --release`
> で再ピンしないと旧バージョンを呼び続ける。現行 WF-01 v1.0.21 は統合サブWF v1.0.13 をピンし、店舗別クエリに
> `状態ラベル AS 'state_label'` を保持（AI が転記する決定的ラベルの供給元）。`scripts/repin_wf01.py` はレガシー。

> **generated_at の TZ 不整合に注意**: サブWF の AI が書く `generated_at` は同一実行内でも `+09:00` と
> `+00:00` が混在しうる（例: `10:33:02+00:00` と `10:33:06+09:00`）。フロントの最新選択
> （`?sort=content.generated_at&descending=true`）は文字列降順ソートで一貫させること。なお保存CE
> `pl_report_api(save)` の旧版削除判定はサーバー付与の `createdOn`（厳密に古いもの）で行うため、この TZ
> 混在の影響を受けない。

---

## Pro-Code デプロイの検証（API）

`domo publish` 後、配信中のアセットを ZIP で取得して中身を確認できる:

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
H="X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN"
D=$(python3 -c "import json;print(json.load(open('pro-code/manifest.json'))['id'])")   # 対象インスタンスの design ID（manifest.json）
V=$(curl -s -H "$H" "https://$DOMO_INSTANCE/api/apps/v1/designs/$D" \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['latestVersion'])")
# ファイル一覧
curl -s -H "$H" "https://$DOMO_INSTANCE/api/apps/v1/designs/$D/versions/$V"
# 全アセットを ZIP で取得（index.html 等を展開して差分確認）
curl -s -H "$H" \
  "https://$DOMO_INSTANCE/api/apps/v1/designs/$D/versions/$V/assets/" -o /tmp/procode.zip
```


---

## 開発ガイド（App Studio ページ2）とハンズオンサンドボックス

### 開発ガイド（`dev-guide-app/`）
純静的 Pro Code（データ接続なし・全10節・臙脂ブランド `#7F1D2D`）。App Studio の**ページ2「開発ガイド」**として埋め込む。

- **公開**: `cd dev-guide-app && domo publish`（初回は `manifest.json` の `id` を外して新規採番 → 払い出された id を `manifest.json` へ反映）。必ず `dev-guide-app/` 直下で実行。
- **埋め込み**: `python3 scripts/provision_domo.py embed-guide`（同じ DataApp のページ2へ・**ページ1＝本体カードは不変**・冪等）。
- **ローカル検証**: `node dev-guide-app/tests/check.mjs`（Chrome 不要の決定的関門）。版は4箇所（`manifest.json`／index colophon／index footer／`tests/thumbnail.html`）を揃える。
- **配布**: `make-handson-zip.sh`（非公開メンテナツール）（`git archive HEAD` → dev-guide の `id` 外し → 6点検証 → zip。親リポ側＝配布物には同梱しない）。⚠**必ずこのビルダー経由で配布**し、生フォルダを Finder 等で zip しない。builder は `git archive HEAD` を使うので gitignore 済みの `domo-assets.json`（保守用 App/Card ID）・`config/secrets.env`・`sandbox-*/`・`__pycache__` を確実に除外する。生 zip だとこれらが混入し、顧客側 `app-studio` が保守用 App ID を掴んで失敗する。

### サンドボックス（バックエンド完全隔離）— `PL_SANDBOX_SUFFIX`
`PL_SANDBOX_SUFFIX="検証・<氏名>"` を**1個**設定すると、`provision_domo.py`（seed／AppDB／dedupe・保存 CE／DataFlow／4出力／App Studio DataApp・カード）と `provision_workflows.py`（保存 CE／統合サブWF／WF-01／業務コレクション）の**全オブジェクト名**に `（検証・氏名）` が付く。両スクリプトが同じ名札を読むので**バックエンド全体が1つの名札で揃う**。state は `sandbox-<氏名>/domo-assets.json` へ分離。契約（公開関数 `pl_report_api`・alias `summary/detail/trend/dept`・`report_type`・`doc_key`）は**不変**。未設定（既定）＝従来挙動を一切変えない。

**本番保護ガード（instance-aware）**: 保守用 `maintenance-instance` で**名札なし**の本番書込みは `provision_domo.py`（apply／app-studio／embed-guide）・`provision_workflows.py provision` が**拒否**する。本番メンテナのみ `PL_ALLOW_PRODUCTION=1` で解除。**顧客が自分のインスタンス（`maintenance-instance` 以外）へ配備する通常フローは素通し**（ガードは maintenance-instance の本番だけを守る）。固定モデルID対象の `ce`/`subflow`/`mainflow`/`delete-wf03` はサンドボックス不可（名札運用は `provision` を使う）。回帰ガード＝[tests/test_sandbox_isolation.py](tests/test_sandbox_isolation.py)（19 件）。

**環境変数**（配布物に焼き込まない）: `PL_SANDBOX_SUFFIX`（名札）、`PL_ALLOW_PRODUCTION`（本番メンテナ解除）、`DOMO_PL_GUIDE_PAGE_TITLE`／`DOMO_PL_GUIDE_CARD_TITLE`（ガイドのページ/カード名の上書き。既定「開発ガイド」／「店舗別損益｜開発ガイド」）、`DOMO_ASSETS_PATH`（registry 保存先の上書き）。

---

## 注意事項

- `workflow/*.json` はスナップショット。ローカル編集しても Domo には反映されない（Domo 画面/API で編集後に再取得する）
- AppDB ドキュメントの重複時はフロントエンドが `generated_at` 降順（文字列ソート）で最新を取得する
- Pro-Code カードのヘッダーには シンプルスタイル ロゴ（`pro-code/logo.png`、バンドル同梱）を表示。ダッシュボードは **概要 / 事業部別 / サマリーの3タブ**構成: **概要** = KPI ＋ 短文AIサマリー ＋ チャート群（トレンド／費用ドーナツ／ランキング、ホバーで凡例・数値をツールチップ表示）、**事業部別**【全社ビューのみ】= 事業部別損益セクション（積み上げ棒／構成ドーナツ／月次トレンド／予算達成テーブル。店舗選択時はタブごと非表示＝`updateDeptTab()` がキーボードナビからも除外し、そのタブ表示中なら概要へフォールバック）、**サマリー** = AppDB `analysis_html` を1本のレポートとして表示（先頭 `<h1>` は `stripReportTitle()` で除去）。ロゴ差し替え時は `logo.png` を置換して `domo publish`
- **事業部別損益セクション**（全社ビュー限定・`dept` データセット由来）: 収益4事業部のみを積み上げ棒（売上原価＋粗利益）／売上構成ドーナツ／月次トレンド／予算達成テーブルで表示。売上は勘定科目レベル1・売上原価はレベル2で集計し二重計上を回避（レベル1売上＝レベル2子科目合計）。事業部利益は**粗利益**（間接費は事業部非配賦のため純利益ではない）。集計は DataFlow タイル `SQL｜事業部別集計（部門×月）`→ `OUT｜P/L事業部別（部門×月）` が正本、FE の `buildDept()` が DEPT オブジェクトへ再構成。詳細は [README.md](README.md) の「トレンド／事業部別の集計は DataFlow 出力データセットで materialize」参照
- トレンド・事業部別は **live データセット**（`trend` / `dept`）から取得する（旧 `window.__TREND__` / `window.__DEPT__` の `app.js` 静的同梱は廃止＝実データ差し替え時の凍結ドリフト防止）。集計は DataFlow 側で materialize（proxy は groupby/sum が 400 のため）。LINE 通知等の外部連携はこのリポジトリのソースには含まない（統合サブWF の全社ブランチが `Send Email` で経営層に通知）
- **サマリー（AI レポート）の表示（v0.1.2〜）**: AppDB `analysis_html` は内容そのまま（AI 出力は変更しない）で、CSS のみで概要/事業部別と揃えたトーンにする。先頭メタ行（店舗/期間/リスク）は `markReportMeta()`（判定は純粋関数 `isReportMeta`）が `.report-meta` を付与して帯状に整形。`h2` は細いアクセントバー、`<b>` 強調は箱なし（色＋太字）、表は `.dept-table` 同トーン、`ol` は丸番号カード。スタイルの契約は `tests/test_drill_helpers.js` が source-text で固定する
- **ドリルダウン（カード内ドリルパス、v0.1.0〜）**: チャートクリックで**カード自体のビューが切り替わる**（スライドバー/ポップアップではない）。カードごとの独立フレームスタック `DRILL` ＋ ドリルバー（`renderDrillBar`、パンくず/戻る/解除）で表現し、遷移の正本は `drillFrom()`（`data-drill` 種別 × 現フレームで次フレームを決定）。店舗セレクター切替時に全カードのドリル状態をリセットする。掘り下げ可能な要素は `data-drill` マーカー＋`tabindex`/`role="button"`/`aria-label` を付け、`bindDrill()` の委譲リスナー（click / Enter / Space）が拾う。パス定義の表は [README.md](README.md) の「ドリルダウン」節が正本、純粋モデルとパス定義は `tests/test_drill_helpers.js`（30件）が固定する。ドリルは追加クエリを発生させない（ロード済み `summary` / `trend` / `dept` の再描画・再集計のみ）
