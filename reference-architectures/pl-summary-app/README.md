# pl-summary-app — 店舗損益AI分析アプリ

> **English summary:** A store P/L AI-analysis reference app — Magic ETL → parallel
> parent/child Workflows with AI agent nodes → AppDB → a fully self-contained
> App Studio card (store selector + KPI/trend/ranking tabs + AI-generated HTML).
> Deployable to your own Domo instance: the canonical guide is
> [docs/setup-guide.md](docs/setup-guide.md) (Japanese), and the provisioning
> scripts remap object IDs by name, so no manual ID edits are needed.

> **対象インスタンス / 別インスタンスへの再現**
> このフォルダは単体で配布され、受け取った人は**自分の Domo インスタンス**へデプロイできる。
> `maintenance-instance.domo.com` は**本リファレンスの保守・検証用インスタンス**であって顧客環境ではない。
> 配布先では `export DOMO_INSTANCE=<your-instance>.domo.com` で対象を指定し、`domo login -i "$DOMO_INSTANCE"`
> で認証する。ソースやスナップショットに埋まった保守用インスタンスの ID は、`sync-manifest`（データ／
> コレクション）と `app-studio`（埋込カードの context mapping）が対象インスタンスの実 ID へ**名称で発見して
> 張り替える**ので手編集は不要。**ゼロからのデプロイ正典は [docs/setup-guide.md](docs/setup-guide.md)**、
> AI エージェントに任せる入口は [prompts/deploy-with-agent.ja.md](prompts/deploy-with-agent.ja.md)。

保守用リファレンス: `maintenance-instance.domo.com`（App Studio: `/app-studio/496788406/pages/623741214`）

---

## アーキテクチャ概要

```
DataFlow (DF-2042)
  └─ ETL: 入力データ整形 → OUT|P/L明細 / OUT|P/L要約
           ↓
Workflow WF-01（reference-app 流・並列サイドブランチ＋終了2つ・dedupe ノードなし）
  開始 → 店舗別SQL ┬─ 店舗ループ(本線): 単一店舗 → 整形 → 15秒待機 → 統合サブWF(report_type=store)
                   │                     → 次店舗あり? ─┬ Yes: 次店舗ID →(戻り)→ 単一店舗
                   │                                    └ No: 終了#1（店舗ループ）
                   └─ 全社ブランチ(並列・フォーク): 全店舗SQL → 整形 → 統合サブWF(report_type=company) → 終了#2（全社）
           ↓
      統合サブWF（WF-02）: 開始 → 5秒待機 → レポート種別?（ゲートウェイ）→ 店舗AI / 全社AI
                            （両AIが pl_report_api(save) で保存。全社AIは Send Email も保持）
           ↓
      AppDB（店舗別損益AI要約）
           ↓
   ┌─────────────────────────────────────────┐
   │  App Studio ページ (page: 623741214)    │
   │                                         │
   │  ・ヘッダー画像                           │
   │  ・Store PL AI Insights（Pro-Code App）  │← 完全自己完結の1カード
   │   店舗セレクター＋概要/事業部別/サマリー3タブ │  （summary/detail/AppDB を直接参照、
   │      （KPI・トレンド・ランキング・         │   自前SVG＋ホバーツールチップ。
   │       ドーナツ／AI HTML）                  │   外部フィルター非依存）
   └─────────────────────────────────────────┘
```

> 現状の App Studio ページには旧構成の KPI カード・Domo AI グラフ8枚も残置。Pro-Code カードが自己完結したため、ヘッダー画像＋Pro-Code カードのみへの整理を推奨（撤去は Domo 画面作業。Pro-Code カードは外部フィルター非依存なので、追加面の有無に関わらず動作する）。

---

## コンポーネント一覧

### DataFlow: `DF｜店舗別損益データフロー`
- **Domo ID**: 2042
- **URL**: https://maintenance-instance.domo.com/datacenter/dataflows/2042/details
- **ローカルファイル**: [dataflow/2042.json](dataflow/2042.json)
- **処理フロー**:
  1. `IN｜P/L入力データ` ← 入力データセット
  2. `PY｜損益データ生成` — Python で店舗×勘定×月のデータ生成
  3. `日付型変更` — Metadata 変換
  4. `OUT｜P/L明細（店舗×勘定×月）` ← 勘定科目レベル明細を出力
  5. `SQL｜要約集計（店舗×月）` — 店舗×月で集計
  6. `PY｜AI入力用テキスト結合` — 各行の店舗別AI入力テキスト（`ai_input_text`）＋全社合算テキスト（`zensha_ai_input`、全行同一値）を整形
  7. `店舗別AIサマリー生成` — TextGeneration（店舗別・`店舗別AIサマリー`列。プロンプト正本: [prompts/prompt_dataflow_store_summary.md](prompts/prompt_dataflow_store_summary.md)）
  8. `AIエラー列を除去(全社前)` — Metadata（`DOMO_AI_BATCH_ERROR` 列を除去）
  9. `全社AIサマリー生成` — TextGeneration（全社合算・`全社AIサマリー`列。全行同一値。経営層向け。`{{zensha_ai_input}}` を入力）
  10. `列を変更` — Metadata（中間列 `ai_input_text` / `zensha_ai_input` / `DOMO_AI_BATCH_ERROR` を除去）
  11. `OUT｜P/L要約（店舗×月）` ← ワークフローが参照するサマリーを出力（`店舗別AIサマリー`＋`全社AIサマリー`列を含む）
  12. `SQL｜トレンド集計（店舗×月）` — `日付型変更` から分岐。レベル1のみ集計 → `OUT｜P/Lトレンド（店舗×月）`（Pro-Code のトレンド live 参照・約2,400行）
  13. `SQL｜事業部別集計（部門×月）` — `日付型変更` から分岐。収益4事業部 FY2025 の売上(L1)/売上原価(L2)/予算差異 → `OUT｜P/L事業部別（部門×月）`（事業部別タブ live 参照・48行）

> `PY｜損益データ生成` は実名店舗にアーキタイプ（スター店/苦戦店/回復基調/下降トレンド/安定店）を付与し、業績・費用構造・季節性に分散を持たせる。改修後は Domo ETL 画面で更新 → dataflow 2042 を実行して summary/detail を再生成する。
> `PY｜AI入力用テキスト結合` は全行に同一の全社合算テキスト（`zensha_ai_input`）をブロードキャストし、`全社AIサマリー生成` タイルが全社視点の要約を `全社AIサマリー` 列に出力する（フロントの「全社」選択時に表示）。

### Workflow WF-01: `WF-01｜店舗損益AIメイン (Loop→Sub)`
- **Domo ID**: `d60ac21b-e1c7-4e6d-bffd-e904e39ac27d`
- **URL**: https://maintenance-instance.domo.com/workflows/models/d60ac21b-e1c7-4e6d-bffd-e904e39ac27d
- **最新バージョン**: v1.0.21（**reference-app の親Workflow 流レイアウトへ再構成**。全社と店舗を**並列**に走らせ、**終了ノードは2つ**〔本線＝店舗ループ／全社ブランチが各々独立終端〕。先頭の **AppDB dedupe CE ノードは撤去済み**〔重複除去は保存CE `pl_report_api(save)` に内包〕。両 SUB_FLOW は統合サブWF **cf3b78c2 v1.0.13** を `report_type="store"/"company"` で呼ぶ。店舗ループに「15秒待機｜同時実行数を平準化」タイマー。座標・経路は数学的レイアウトエンジン〔[scripts/provision_workflows.py](scripts/provision_workflows.py) の `set_grid`/`route_*`/`ci_style_mainflow_definition`〕が算出し、PUT 前に `validate_layout` が重なり0・経路貫通0 をゲートする＝**デプロイしてもレイアウトが崩れない**。配備は `provision_workflows.py mainflow`。レイアウトの数学モデルは `scripts/provision_workflows.py` 内に実装している（配布対象外のワークスペース内部スキルには依存しない））
- **ローカルファイル**: [workflow/WF-01_main_loop.json](workflow/WF-01_main_loop.json)（26 designElements＝13ノード/13エッジ・7 変数）
- **処理フロー**（開始 → 店舗別SQL から2系統へ**フォーク**）:
  1. 開始（`rootNode`・出線1本）→ 店舗別データ取得（`OUT｜P/L要約` に SQL クエリ）
  2. **【並列・全社ブランチ】** 店舗別SQL から分岐 → 全店舗要約データ取得（SQL）→ 全店舗テキスト整形 → **統合サブWF（`report_type="company"`）** → **終了#2（全社）**
  3. **【本線・店舗ループ】** 店舗別SQL → `インデックス=0` から店舗を 1 件取得 → 店舗テキスト整形 → **「15秒待機」タイマー** → **統合サブWF（`report_type="store"`）** → 「次店舗あり？」
  4. 「次店舗あり？」→ Yes: 次店舗ID（インデックス+1）→ ループ戻り / No: **終了#1（店舗ループ）**

### Workflow WF-02（統合サブWF）: `WF-02｜店舗損益AIレポート生成（店舗/全社）`
- **Domo ID**: `cf3b78c2-eed1-4f55-a7d5-8004a36fbe39`（旧 WF-02 モデルを再利用し、旧 WF-03〔全社〕を統合＝サブWFは1本）
- **URL**: https://maintenance-instance.domo.com/workflows/models/cf3b78c2-eed1-4f55-a7d5-8004a36fbe39
- **最新バージョン**: v1.0.13（店舗AIと全社AIを `report_type` 分岐の1本に統合。店舗5値ラベル：好調／堅調／要注意／回復基調／不振〔回復基調＝利益率<0 かつ 前月比利益変化率>0〕・全社4値ラベル：好調≥8%／堅調5-8%／要注意0-5%／不振<0%。状態ラベルは自分で判定せず、入力の機械確定済み `state_label`〔＝ETL `状態ラベル`列〕を**そのまま転記**）
- **ローカルファイル**: [workflow/WF-02_report_ai.json](workflow/WF-02_report_ai.json)
- **AIプロンプト**: 店舗ブランチ [prompts/prompt_wf02_store.md](prompts/prompt_wf02_store.md)／全社ブランチ [prompts/prompt_wf03_summary.md](prompts/prompt_wf03_summary.md)（この2ファイルが2ブランチの instructions。履歴保持のためファイル名は不変）
- **コンテキストデータセット**（両ブランチ共通）: `summary` ＋ `detail`
- **処理フロー**:
  1. 開始（フォーム入力: `CollectionId` / `AiPromptText` / `report_type`）
  2. 「5秒待機｜AI負荷平準化」タイマー
  3. 「レポート種別？」ゲートウェイ（`report_type` で分岐）
  4. **店舗AI**（既定ブランチ・`report_type="store"`）または **全社AI**（`report_type="company"`・経営層向け・問題店舗は純利益ワースト視点）が分析
  5. 結果を Code Engine ツール `pl_report_api(operation="save", request={collection_id, document})` で AppDB に保存（全社AIは追加で `Send Email` ツールを保持し経営層・統括マネージャーに通知）
  6. 終了

### AppDB: `店舗別損益AI要約`
- **Collection ID**: `ca132957-d14d-4fa0-9c69-3e6721d27141`
- **URL**: https://maintenance-instance.domo.com/appDb/ca132957-d14d-4fa0-9c69-3e6721d27141/dataexplorer
- **書き込み元**: 統合サブWF（WF-02）の店舗ブランチ（個別店舗）／全社ブランチ（全社サマリー）が Code Engine ツール `pl_report_api(operation="save", ...)` で保存
- **読み取り元**: Pro-Code App（フロントエンド）
- **doc_key 形式**:
  - 個別店舗: `{store_id}-{period}-{scenario}`（例: `S001-2024-11-Actual`）
  - 全社サマリー: `ALL-{period}-{scenario}`（例: `ALL-2024-11-Actual`）
- **主要フィールド**: `store_id`, `location_name`, `period`, `risk_level`, `total_sales`, `profit_margin`, `personnel_ratio`, `analysis_html`

### Code Engine（保存API・現役）: `report_api.py`
- **ローカルファイル**: [code-engine/report_api.py](code-engine/report_api.py)
- **パッケージ名 / ID**: `店舗別損益AI要約｜レポートAPI` / `43e0a52b-83df-4f52-a2bf-1a3634898215`
- **公開関数**: `pl_report_api(operation, request) -> object` — 統合サブWFの店舗AI・全社AIが**保存ツール**として呼び出す単一ディスパッチャ
  - `operation="save"`（`request = {collection_id, document}`）: レポートを AppDB に保存し、**同一 `doc_key` の旧版（サーバー `createdOn` が今回より厳密に古いもの）だけを削除**する＝**重複除去を保存処理に内包**。これにより従来 WF-01 先頭に置いていた独立 dedupe ノードが不要になった。厳密に古い同一 `doc_key` のみ削除するため、別実行の正レポートを巻き添え削除しない。必須フィールド（`doc_key`/`store_id`/`location_name`/`analysis_html`）欠落の不完全保存は POST 前に弾く門番付き
  - `operation="validate"`（`request = {collection_id, doc_key}`）: 保存前に接続先と識別子だけを軽く検証する補助（任意）
- **認証**: シークレット不要。Domo 提供の `import codeengine` モジュールでランタイムが認証を注入する（旧 `DOMO_TOKEN` シークレットは不要）。`collection_id` は GUID 形状のみ検証＝**インスタンス非依存**（移植先では WF-01 の `CollectionId` 変数だけ差し替える）
- **デプロイ**: [scripts/provision_workflows.py](scripts/provision_workflows.py) `ce`（`--apply` で実行）。詳細は下記「Workflow プロンプト／CE／ワークフロー層の修正」および [AGENT.md](AGENT.md)

### Code Engine（レガシー／フロー非配線）: `appdb_maintenance.py`
- **ローカルファイル**: [code-engine/appdb_maintenance.py](code-engine/appdb_maintenance.py)
- **パッケージ ID**: `4c3f8e59-5fe7-4bb2-b0cd-0959b5efae25`（最新 **v1.0.5**）
- **関数**: `dedupe_appdb_documents(collection_id) -> object` — `collection_id` は必須引数（既定値なし・GUID_REGEX で検証）。`doc_key` ごとに `generated_at` 最新1件のみ残し重複を削除（最新保持型で途中失敗しても安全）
- **現在の位置づけ**: ⚠️ **WF-01 からは配線を外した**（dedupe は現役の保存CE `pl_report_api(save)` に内包）。コレクション全体の一括 dedupe を行う**手動／バッチ用ユーティリティ**としてのみ残置する（現役の保存CEではない）。特性化テスト [tests/test_appdb_maintenance.py](tests/test_appdb_maintenance.py)（12件）はこのレガシー関数を固定する
- **認証**: シークレット不要（`import codeengine`・`collection_id` は必須引数＝インスタンス非依存）
- **デプロイ（手動更新時のみ）**: `scripts/deploy_code_engine.py`（レガシー。詳細は [AGENT.md](AGENT.md)）

### Pro-Code App: `Store PL AI Insights`
- **App ID**: `08463c98-38a9-4caa-a762-b857a37e2826`
- **Card ID**: `416610471`
- **ソース**: [pro-code/](pro-code/)
- **参照データ**:
  - AppDB: `店舗別損益AI要約`（上記）
  - Dataset alias `summary`: `e05581f1-d70a-474d-91f3-f5a2080c9d05`（現在期間の100店舗サマリー。`店舗別AIサマリー`／`全社AIサマリー` 列を含む）
  - Dataset alias `detail`: `a1ba80ca-147e-4ac8-8464-5867d665860e`（24ヶ月明細。trend/dept 集計の元データ）
  - Dataset alias `trend`: DataFlow 出力 `OUT｜P/Lトレンド（店舗×月）`（店舗×月×{rev,profit}・約2,400行。24ヶ月トレンド用）
  - Dataset alias `dept`: DataFlow 出力 `OUT｜P/L事業部別（部門×月）`（部門×月×{rev,cogs,variance}・48行。事業部別タブ用）
  - ※ trend/dept は **live データセット**（旧 `window.__TREND__` / `window.__DEPT__` の静的同梱は廃止）。`fields+limit` で取得し FE で集計/再構成する（生成 SQL は「ローカル開発フロー」参照）
- **動作**（完全自己完結の1カード。App Studio 外部フィルターに非依存）:
  - ヘッダーに シンプルスタイル ロゴ（`pro-code/logo.png`）とタイトルを表示
  - カード内セレクターで店舗を選択（先頭に「全社」＝全店舗合算ビュー）
  - ビューは **概要 / 事業部別 / サマリー の3タブ**（セグメント型トグル。クリック／矢印キー・Home・End で切替。**事業部別は全社ビュー時のみ表示**し、店舗選択時はタブごと非表示＝キーボードナビもスキップ）
    - **概要**タブ: KPI カード群 → 短文AIサマリー（quick-glance）→ チャート群（売上・利益トレンド折れ線／費用構成ドーナツ／店舗別純利益ランキング）
    - **事業部別**タブ【全社ビューのみ】: 事業部別損益セクション（積み上げ棒／売上構成ドーナツ／月次売上トレンド／予算達成テーブル）
    - **サマリー**タブ: AppDB の `analysis_html` を1本の連続レポートとして表示（概要と重複する先頭 `<h1>` 表題は `stripReportTitle()` で除去）。見た目は概要/事業部別と揃えた上品トーン（v0.1.2〜）: 先頭のメタ行（店舗/期間/リスク）は `markReportMeta()` が `.report-meta` の淡い帯へ、`h2` は事業部別見出しと同じ細いアクセントバー、強調（`<b>`）は箱・背景をやめ色＋太字のみ、表は `.dept-table` と同トーン（角丸・淡ヘッダ・ゼブラ）、番号付き対策リストは丸番号付きの淡いカード。AI 出力 HTML 自体は変更しない（スタイルのみ）
  - **事業部別損益セクション**（全社ビュー限定・`dept` データセット由来。ステークホルダーFB対応）:
    - **売上ゼロの間接部門を除外**し、収益4事業部（衣料品／生活雑貨／食品／新規事業部）のみ表示
    - **積み上げ縦棒**（売上原価＋粗利益＝売上）で費用・利益構造を可視化
    - **売上構成ドーナツ**（事業部別売上シェア）
    - **月次売上トレンド**（4事業部の折れ線。3月/7月/12月の季節性）
    - **予算達成状況テーブル**（売上／原価／粗利／予算差異／達成率、粗利ベース）
    - ※ 粗利益＝売上−売上原価。人件費・賃料等の間接費は全社共通のため事業部配賦せず（テーブル脚注に明記）
  - `summary` を `domo.get('/data/v1/summary?...')` で取得 → KPI・費用構成ドーナツ・純利益ランキング・短文AIサマリーを描画（店舗選択時は `店舗別AIサマリー` 列、「全社」選択時は `全社AIサマリー` 列を表示）
  - `trend` データセットを `domo.get('/data/v1/trend?...')` で取得し24ヶ月の売上/利益トレンド折れ線を描画（全社は店舗合算・月次ランキングは月抽出）
  - AppDB を `content.store_id`（全社は `"ALL"`）でクエリし `generated_at` 降順の最新1件の `analysis_html` を描画（未生成時は「準備中」フォールバック）。急な店舗切替でも `state.reqSeq` トークンで応答の順序逆転による誤表示を防ぐ
  - チャートは全て自前SVG（外部CDN・依存なし）。臙脂色アクセントの MUJI 調
  - **チャートホバーで凡例・数値をツールチップ表示**（トレンドは縦ガイド線＋フォーカス点、ドーナツ／ランキングは対象要素を強調）。ツールチップDOMは再描画で消えない親 `.chart-card` に一度だけ配置し、タブ切替時は `clearChartTips()` で残存表示をクリア
  - **チャートクリックでカード内ドリルダウン**（v0.1.0〜）: スライドバー/ポップアップではなくカード自体のビューが切り替わり、パンくず（ドリルパス）で深掘り・遡行できる。詳細は下記「ドリルダウン」節

### ドリルダウン（カード内ドリルパス）— v0.1.0〜

チャートの要素をクリックすると**そのカード自体のビューが切り替わり**（Domo 標準カードのドリルダウン相当）、
カード上部のドリルバーに「← 戻る / 全社 › 2025年6月 › 渋谷店 / ✕ 解除」のパンくずを表示する。パンくずクリックで任意階層へ遡行、
`Enter` / `Space` でも掘り下げ可能（クリック対象は `tabindex` / `role="button"` / `aria-label` 付き）。
ドリル状態はカードごとの独立スタックで、**店舗セレクターの切替時に全カードでリセット**される。

| カード | レベル0（トップ） | クリック | レベル1 | クリック | レベル2 | クリック | レベル3（最終データビュー） |
|---|---|---|---|---|---|---|---|
| 売上・利益トレンド（全社） | 24ヶ月折れ線 | 月 | 店舗別 純利益（当月・上位8/下位5） | 店舗 | その店舗の24ヶ月トレンド | 月 | 月次詳細表（当月/前月/前年同月＋変化率） |
| 売上・利益トレンド（店舗） | 24ヶ月折れ線 | 月 | 月次詳細表 | — | — | — | — |
| 費用構成ドーナツ（全社） | 5区分ドーナツ | 区分 | 区分別 店舗金額（上位10店舗） | 店舗 | その店舗の費用構成ドーナツ | 区分 | 費用内訳表（金額/構成比/対売上比） |
| 費用構成ドーナツ（店舗） | 5区分ドーナツ | 区分 | 費用内訳表 | — | — | — | — |
| 店舗別 純利益ランキング | 上位8/下位5横棒 | 店舗 | その店舗の24ヶ月トレンド | 月 | 月次詳細表 | — | — |
| 事業部別 売上・粗利 | 積み上げ縦棒 | 事業部 | その事業部の月次売上 | 月 | 月次詳細表（当月/前月/FY合計） | — | — |
| 売上構成比（事業部） | ドーナツ | 事業部 | その事業部の月次売上 | 月 | 月次詳細表 | — | — |
| 事業部別 月次売上トレンド | 4系列折れ線 | 月 | 事業部別売上（当月内訳） | 事業部 | その事業部の月次売上 | 月 | 月次詳細表 |

> **データソース**: すべて live データセット。トレンド系（店舗×月）は `trend`、事業部別（部門×月）は `dept`、
> 費用・店舗別金額・KPI 系は `summary`。3データセットを起動時に取得し、ドリルは追加クエリを発生させない（ロード済みデータの再描画・再集計のみ）。
>
> **表示**: SVG はカード実寸（`chartWidth()` = コンテナ `clientWidth`）で描画するため、埋め込み幅が変わっても
> 文字が縮小されない（リサイズ時は現在のドリルフレームのまま再描画）。行高・店舗名/金額カラム幅・月ラベルの間引きは
> カード幅に応じて自動調整する。
>
> **実装**: `app.js` の `drillFrom()` が「`data-drill` の種別 × 現在フレーム」で次フレームを決定し、
> 各カードの `render*Card()` がフレームを描画する。クリック/キーボードは `bindDrill()` の委譲リスナー（innerHTML 再描画に耐える）、
> ツールチップは `bindChartHover()` の仕様ディスパッチ（1ホスト複数マーカー）。純粋モデルは `tests/test_drill_helpers.js` が固定する。
>
> **ユーザー向け文言**: 画面に出る注記は業務用語のみとし、`window.__*`・`analysis_html`・データセット名などの実装用語は表示しない
> （ドリルの出所はパンくずが示すため、脚注で繰り返さない）。

### App Studio ページ
- **App ID**: `496788406`
- **Page ID**: `623741214`
- **URL**: https://maintenance-instance.domo.com/app-studio/496788406/pages/623741214
- **構成**: Pro-Code と標準機能（KPI カード・Domo AI グラフ）を組み合わせたページ

| Card ID | 種別 | タイトル | 役割 |
|---------|------|---------|------|
| `1153881052` | document | image.png | ヘッダー画像 |
| `1374106327` | kpi | 店舗名 | 店舗フィルター |
| `416610471` | domoapp | Store PL AI Insights | Pro-Code App（AI分析HTML表示） |
| `487085362` | kpi | OUT｜P/L要約（店舗×月） | サマリー数値表示 |
| `1074249348` | kpi | 地域別売上高ランキング | Domo AI 生成グラフ |
| `542109670` | kpi | 勘定科目別費用構成 | Domo AI 生成グラフ |
| `511177079` | kpi | 地域別売上構成比 | Domo AI 生成グラフ |
| `168685397` | kpi | 勘定科目名別売上トップ10 | Domo AI 生成グラフ |
| `1815220132` | kpi | 都道府県別売上構成比 | Domo AI 生成グラフ |
| `555913918` | kpi | 部門別利益貢献度 | Domo AI 生成グラフ |
| `1440822836` | kpi | 店舗別利益ランキング（上位10店舗） | Domo AI 生成グラフ |
| `2100790726` | kpi | 地域別パフォーマンス詳細 | Domo AI 生成グラフ |

> Domo AI グラフは `OUT｜P/L要約（店舗×月）` データセットを参照。  
> Pro-Code App のみソースコードをローカル管理し、`domo publish` でデプロイする。  
> KPI カード・Domo AI グラフは App Studio 画面で直接編集する。

---

## 開発ガイド（App Studio ページ2「開発ガイド」）＋ ハンズオンサンドボックス

- **開発ガイド（[dev-guide-app/](dev-guide-app/)）**: VS Code × コーディングエージェントでこのアプリを
  開発・運用する手引きを解説した**純静的 Pro Code**（データ接続なし・縦スクロール1枚・全10節・臙脂ブランド）。
  App Studio の**ページ2「開発ガイド」**として埋め込む（ページ1＝本体カードには一切触れない）。公開＋埋め込みは
  `cd dev-guide-app && domo publish` → `python3 scripts/provision_domo.py embed-guide`（手順は
  [docs/setup-guide.md](docs/setup-guide.md) STEP 7、ガイドアプリ自体の保守は [dev-guide-app/README.md](dev-guide-app/README.md)）。
- **ハンズオンサンドボックス（バックエンド完全隔離）**: 環境変数 `PL_SANDBOX_SUFFIX="検証・<氏名>"` を**1個**
  設定すると、**データ層（seed／AppDB `店舗別損益AI要約`／dedupe・保存の Code Engine／DataFlow／4出力データセット）
  ＋ WF層（統合サブWF／WF-01）＋ FE（App Studio DataApp／カード）**の全オブジェクト名に `（検証・氏名）` が付いて
  一意化され、同一インスタンス（保守用 `maintenance-instance`）上で本番や他参加者と衝突しない。state（`domo-assets.json`）も
  `sandbox-<氏名>/` へ分離。契約（公開関数 `pl_report_api`・alias `summary/detail/trend/dept`・`report_type`・`doc_key`）は
  **不変**。未設定（既定）＝従来挙動を一切変えない。**本番保護ガード**は `maintenance-instance` の本番オブジェクトを名札なしの
  作成/書換から守り（本番メンテナのみ `PL_ALLOW_PRODUCTION=1` で解除）、**顧客が自分のインスタンス（`maintenance-instance` 以外）へ
  配備する通常フロー（STEP 1〜7）は素通し**する。受講者入口＝[prompts/handson-with-agent.ja.md](prompts/handson-with-agent.ja.md)、
  配布 ZIP ビルダー＝`make-handson-zip.sh`（非公開メンテナツール）（親リポ側・配布物には同梱しない）。

---

## サマリーの一貫性設計（4面の AI サマリー）

本アプリは **同じ P/L データに対して 4 面の AI サマリー**を生成する。表現が食い違うと利用者の信頼を損なうため、
語彙・閾値・判定ロジックを単一の正本 [prompts/prompt_shared_conventions.md](prompts/prompt_shared_conventions.md) に集約し、
4 面すべてがそこに従う（＝コントラクト方式）。

| 面 | 生成元 | 出力先 | 粒度・文体 |
|----|--------|--------|-----------|
| 店舗 短文 | ETL タイル `店舗別AIサマリー生成` | `summary.店舗別AIサマリー` 列 | 店舗・1〜2文（quick-glance） |
| 全社 短文 | ETL タイル `全社AIサマリー生成` | `summary.全社AIサマリー` 列 | 全社・1〜2文 |
| 店舗 長文 | 統合サブWF（WF-02）店舗ブランチ AI | AppDB `analysis_html`（`store_id`別） | 店舗・HTML レポート |
| 全社 長文 | 統合サブWF（WF-02）全社ブランチ AI | AppDB `analysis_html`（`ALL`） | 全社・HTML レポート |

**コントラクトの要点**（詳細は正本参照）:
- **状態ラベル＝ETL の決定的列（単一の真実）**: 店舗の状態ラベル（好調／堅調／要注意／回復基調／不振 の5値）は SQL タイル `SQL｜要約集計（店舗×月）` の `CASE` 式で**機械的に確定**し、`状態ラベル` 列として出力する。短文タイルも長文エージェント（WF-02）も**この列を再判定せず一字一句そのまま転記**する。閾値: 好調 利益率≥8%／堅調 5-8%／要注意 0-5%／回復基調 利益率<0 かつ 前月比利益変化率>0／不振 利益率<0 かつ 前月比利益変化率≤0。全社（4値）は集計値のため回復基調を設けない。
- **なぜ列に一元化したか**: 短文は `domogpt-medium`、長文は Claude 系エージェントと**別モデル**のため、境界判定（例: 赤字だが前月比改善は「回復基調」か「不振」か）を各 LLM に委ねると恣意的に食い違う。判定を ETL 列へ寄せ両 LLM を転記に徹させることで、モデル差に関わらず**構造的に一致**を担保する。
- **支配要因**: 3値（売上不足／コスト構造過剰／売上・コスト両面）。
- **問題店舗の視点**: 全社面は**純利益ワースト**（赤字額の大きい順）で問題店舗を論じる。予算差異は全社集計としてのみ言及し、店舗ランキングには使わない。
- **同一店舗・同一期間なら短文と長文の状態ラベルは一致する**（両面が同じ `状態ラベル` 列を転記するため、構造的に保証）。

**整合の担保**: 状態ラベルの規則を変えるときは ①SQL の `CASE` 式（正本）→ ②共通規約 → ③4本のプロンプトの「参考・判定規則」注記 を揃えて更新し、DataFlow 再実行 → WF-01 を実行する（15秒ペーシング＋保存時 per-save 重複除去で1回でおおむね収束。確実を期す場合の2回連続実行は安全網）。検証は summary データセットの
短文列と AppDB 長文レポートから状態ラベルを機械抽出し、店舗ID×期間で突き合わせて一致率を確認する
（過去に ETL 店舗プロンプトへ判定を委ねていた際は境界の赤字店で短文・長文が食い違ったが、決定的列への一元化で解消）。

---

## ローカル開発フロー

### 前提

- Domo CLI インストール済み: `npm install -g ryuu`（`domo` コマンド）、Python 3.9 以上
- **対象インスタンスを指定して認証する**（ゼロからの一連は [docs/setup-guide.md](docs/setup-guide.md) が正典）:

```bash
export DOMO_INSTANCE=<your-instance>.domo.com   # 保守用は maintenance-instance.domo.com
domo login -i "$DOMO_INSTANCE"                  # ブラウザ SSO。トークン不要
```

- `scripts/provision_domo.py`（データ層）と `domo publish` はこのログインだけで動く（configstore を読む）。
- **ワークフロー層（`scripts/provision_workflows.py`）、`SID` を要求するスクリプト
  （`scripts/deploy_dataflow_prompt.py`・レガシー `scripts/deploy_code_engine.py`）、raw curl** は、開発者
  トークンかセッション SID が要る:
  - **開発者トークン**: `config/secrets.env`（gitignore 済み・雛形 `config/secrets.env.example`）に
    `DOMO_DEVELOPER_TOKEN` を置き `set -a; . config/secrets.env; set +a` で読み込む。`provision_workflows.py`
    はこれを直接使い、curl は `-H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN"` で使う。
  - **セッション SID**（`deploy_dataflow_prompt.py` 等が要求する `INSTANCE`＋`SID`）は、上の `domo login`
    セッションから発行できる:

    ```bash
    export INSTANCE="$DOMO_INSTANCE"
    export SID=$(python3 - <<'PY'
    import json,os,pathlib,urllib.parse,urllib.request
    inst=os.environ["INSTANCE"]
    cfg=json.loads((pathlib.Path.home()/".config/configstore/ryuu"/f"{inst}.json").read_text())
    body=urllib.parse.urlencode({"client_id":"domo:internal:devstudio","grant_type":"refresh_token","refresh_token":cfg["refreshToken"]}).encode()
    at=json.loads(urllib.request.urlopen(urllib.request.Request(f"https://{inst}/api/oauth2/token",data=body,method="POST",headers={"content-type":"application/x-www-form-urlencoded;charset=utf-8"})).read())["access_token"]
    print(json.loads(urllib.request.urlopen(urllib.request.Request(f"https://{inst}/api/oauth2/sid",headers={"Authorization":f"Bearer {at}"})).read())["sid"])
    PY
    )
    ```

> ドキュメント中のコマンドは **`pl-summary-app/` 直下**で実行する。`pl-summary-app/scripts/...` と
> 書かれた箇所は、配布フォルダ内では `scripts/...` に読み替える（配布物のルートが `pl-summary-app/` のため）。

### Pro-Code App の修正
```bash
cd pl-summary-app/pro-code

# ローカルプレビュー
domo dev

# 本番デプロイ
domo publish
```

> manifest.json の `id` がアプリ ID。`datasetsMapping` / `collectionsMapping` のエイリアスを変えないこと。

### Workflow プロンプト／CE／ワークフロー層の修正（`provision_workflows.py`）

ワークフロー層（統合サブWF・WF-01・保存CE）は [scripts/provision_workflows.py](scripts/provision_workflows.py) で
再現可能に配備する（サブコマンド: `provision` / `ce` / `subflow` / `mainflow` / `delete-wf03` / `verify` / `all`。`--apply` で実行、
`--release` で PUT 後にリリース。いずれも **draft 作成 → PUT → round-trip 検証 → release** の安全パターン）。

**プロンプト修正**（統合サブWFは AI_AGENT が2つ＝店舗／全社ブランチ）:

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN を読み込む（前提参照）
# 1. 正本 md を編集（prompt_wf02_store.md＝店舗ブランチ／prompt_wf03_summary.md＝全社ブランチ）
# 2. 両ブランチの instructions を md から再取り込み
python3 scripts/provision_workflows.py subflow --apply --release
# 3. WF-01 を新 sub バージョンへ再ピン
python3 scripts/provision_workflows.py mainflow --apply --release
# 4. WF-01 を手動実行してテスト（手順・エンドポイントは AGENT.md 参照）
```

**保存CE（`report_api.py`）修正**: `report_api.py` を編集 → `provision_workflows.py ce --apply` → `subflow` → `mainflow`。

> **環境変数**（配布物には焼き込まない）: `PL_EMAIL_PERSON_RECIPIENTS`（全社ブランチのメール宛先 person ID・
> カンマ区切り）、`PL_PARENT_INTERVAL_SECONDS`（既定15・店舗ループの待機秒）、`PL_CHILD_SETTLE_SECONDS`
> （既定5・サブWF冒頭の待機秒）、`PL_WF01_MODEL_ID` / `PL_SUBFLOW_MODEL_ID` / `PL_WF03_MODEL_ID` /
> `PL_DEDUPE_CE_PACKAGE_ID`。dedupe ノードが無いインスタンスでは撤去は no-op。
>
> **レガシー手順**: `scripts/deploy_wf_prompt.py` は単一 AI_AGENT 置換前提のためレガシー（統合サブWFは
> AI_AGENT が2つ）。`scripts/repin_wf01.py` もレガシー（再ピンは `provision_workflows.py mainflow` が担う）。
> dedupe 用 `scripts/deploy_code_engine.py` もレガシー。いずれも残置するが **新手順（`provision_workflows.py`）を正とする**。
>
> **注意**: ワークフロー定義（`workflow/*.json`）はバージョン定義のスナップショット。  
> ローカルで編集しても自動同期はされない。Domo 画面/API で変更後、再ダウンロードして上書きすること。

### DataFlow の修正
Magic ETL v2（`magic:true`）は Workflow のような draft/version/release がなく **その場編集**（GET→PUT）。用途で手段を分ける:

**(a) TextGeneration タイルのプロンプト（`店舗別AIサマリー生成` / `全社AIサマリー生成`）** — 正本 md を編集し、API で安全にデプロイ（Domo 画面での貼り付け不要）:

```bash
# INSTANCE＋SID は「前提」のセッション SID 発行ヘルパで設定しておく（このスクリプトは SID を要求する）
# 引数: DATAFLOW_ID  TILE_NAME 正本md  [TILE_NAME 正本md ...]。RUN=1 で AI列を再生成する再実行までトリガー
RUN=1 python3 scripts/deploy_dataflow_prompt.py 2042 \
  店舗別AIサマリー生成 prompts/prompt_dataflow_store_summary.md \
  全社AIサマリー生成   prompts/prompt_dataflow_company_summary.md
```

> スクリプトは live 定義をバックアップ → 対象タイルの `instructions` **のみ**差し替え → PUT → GET し直して
> 「アクション数・id 一致／変更は対象タイルのみ／各タイルの instructions 以外と `gui`（視覚グラフ）が無変更」
> を厳密検証する。検証に落ちた場合はバックアップを PUT で復元して中断する。正本 md の指示文は
> ` ``` ` フェンスブロック内に置くこと（スクリプトがそこを抽出する）。

**(b) Python タイル（`PY｜損益データ生成` 等）やタイル構成の変更** — Domo ETL 画面（[URL](https://maintenance-instance.domo.com/datacenter/dataflows/2042/details)）で編集する。

変更後は必ず API で再取得して `dataflow/2042.json` を更新:

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
curl -s -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" \
  "https://$DOMO_INSTANCE/api/dataprocessing/v1/dataflows/2042" \
  -o dataflow/2042.json
```

> `dataflow/2042.json` は live 定義のスナップショット。ローカル編集は自動同期されない。変更は
> (a) スクリプト or (b) Domo 画面で行い、上記 curl で再取得して上書きすること。

### AppDB の確認
```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN
# 全ドキュメント取得（直近10件）。コレクション ID は sync-manifest 後の manifest.json / verify 出力を正とする（インスタンス別）
curl -s -H "X-DOMO-Developer-Token: $DOMO_DEVELOPER_TOKEN" \
  "https://$DOMO_INSTANCE/api/datastores/v1/collections/ca132957-d14d-4fa0-9c69-3e6721d27141/documents?limit=10" \
  | python3 -m json.tool
```

### トレンド／事業部別の集計は DataFlow 出力データセットで materialize（旧・同梱スナップショット廃止）
App Framework proxy は `groupby/sum` 集計を HTTP 400 で拒否するため、**集計を DataFlow 側で materialize** し、Pro-Code は他の live データセットと同じく `fields+limit` で取得する（`app.js` 冒頭の静的同梱 `window.__TREND__` / `window.__DEPT__` は**廃止**。実データ差し替え時にチャートが凍結してドリフトするのを防ぐため）。DataFlow に集計タイル2本を追加済み（`日付型変更` から分岐）:

- **`OUT｜P/Lトレンド（店舗×月）`**（alias `trend`・約2,400行）＝ `SQL｜トレンド集計（店舗×月）`。レベル1（`サマリ区分=1`）のみ集計し二重計上を回避:
  `SELECT 期間 AS period, 店舗ID AS store_id, 店舗名 AS store, 地域 AS region, ROUND(SUM(売上金額)) AS rev, ROUND(SUM(純額)) AS profit ... WHERE is_summary=1 GROUP BY 期間,店舗ID,店舗名,地域`。全社トレンド・月次ランキングは FE 側で合算/抽出。
- **`OUT｜P/L事業部別（部門×月）`**（alias `dept`・48行）＝ `SQL｜事業部別集計（部門×月）`。**売上は勘定科目レベル1、売上原価はレベル2で二重計上を回避**。収益4事業部・FY2025:
  `ROUND(SUM(CASE WHEN 勘定科目種類='Revenue' AND 勘定科目レベル=1 THEN 売上金額 ELSE 0 END)) AS rev, ROUND(SUM(CASE WHEN 勘定科目種類='Expense' AND 勘定科目レベル=2 THEN 費用金額 ELSE 0 END)) AS cogs, ...予算差異... GROUP BY 期間,部門コード,部門`。FE の `buildDept()` が `{fy,from,to,divisions,monthly}` へ再構成（粗利益＝売上−売上原価、予算＝粗利−予算差異、達成率＝粗利/予算×100。間接費は事業部非配賦＝事業部利益は「粗利益」）。

正本は `dataflow/2042.json` の該当タイル。データフロー再実行で trend/dept データセットも自動更新される（`app.js` へのスナップショット貼り付けは不要）。集計値は旧同梱値と円一致（例: trend JPN001 2024-01 = rev 44,579,859 / profit 2,640,845、dept APPA FY2025 = rev 13,841,877,056 / cogs 4,790,768,383）。manifest の alias→物理ID は `scripts/provision_domo.py sync-manifest` がインスタンス別に解決する。

---

## テスト（デプロイ前ローカルゲート）

`tests/test_report_api.py` は**現役の保存CE** `pl_report_api` の特性化テスト（ネットワーク非依存）。`save` が破壊的（同一 `doc_key` の旧版を物理削除）なので、安全不変条件をゴールデン値で固定する——①作成した当の文書は消さない／②サーバー `createdOn` が**厳密に古い**同一 `doc_key` だけ消す（同時刻・未知時刻・新しい側は保持）／③掃除失敗でも作成成功は `ok:True`／④必須フィールド欠落の不完全保存は POST 前に弾き既存の正レポートを巻き添え削除しない／⑤`generated_at` の空・ISO 不正値は現在時刻へ正規化。デプロイ済み CE バンドルには一切触れない。

`tests/test_appdb_maintenance.py` に**レガシー util** `dedupe_appdb_documents` の**特性化テスト 12 件**（ネットワーク非依存）。この関数は AppDB ドキュメントを**物理削除**する破壊的操作なので、現挙動——特に「削除しすぎない」安全不変条件——をゴールデン値で固定する。WF-01 からは配線を外した（dedupe は `pl_report_api(save)` に内包）が、手動／バッチ dedup として残置するためガードは維持する。**test-only 特性化**でありソースは一切変更していない（＝CE バンドル byte 不変・回帰ゼロ）。

> ⚠️ これは **Domo CE エディタ内蔵の単体テスト（＝常に最新版を開く）とは別物**。こちらはローカルで機械実行する回帰ガード。

`import codeengine` を空スタブで通し、`send_request` はテストごとに**インメモリ代役**へ差し替える（GET は与えたページ列を順に返し・短いページで終端 break を再現、DELETE は URL を試行時点で記録＝失敗チャンクの URL も残す）＝実ネットワーク非発生。

```bash
python3 pl-summary-app/tests/test_appdb_maintenance.py   # → Ran 12 tests OK
```

固定している安全不変条件（現挙動をゴールデンで固定）:

- **中核**: 同一 `doc_key` は `generated_at` 最新1件を残し、古い方だけ降順で削除＝**最新は必ず生き残る**。同値は安定ソートで先着保持。
- **削除しすぎない**: `doc_key` 無し・`content` 無しは `__nokey__{id}` で単独グループ化し重複扱いしない；古い側でも `id` が無ければ削除候補に入れない（`if doc_id:` ガード）。
- **部分失敗耐性**: 削除は `_DELETE_CHUNK` 件ずつ分割し、途中チャンクが raise しても継続（`deleted` は成功分のみ・`success=True`＝最新は保持済み・失敗チャンクも URL 記録＝試行はする）。
- **ページング**: 短いページで終端し、ページを跨いで同一 key を集約。
- **入力検証**: `collection_id` は GUID_REGEX で**取得より前**に検証（空・非GUID・バージョン桁違いは `ValueError`＝`send_request` を一度も呼ばない）。
- **出荷定数**: `(_PAGE_SIZE, _DELETE_CHUNK) = (5000, 100)` を（挙動テストが縮小定数へ書き換える前に）別テストで固定＝定数変更はレビュー対象として検知。

いずれも「あるべき」でなく「現にどうか」を固定する特性化テスト＝破壊的操作を挙動不変のままリファクタする際の回帰ガード。

### ドリルダウンの特性化テスト（`tests/test_drill_helpers.js`）

ドリルダウン機能（v0.1.0）の回帰ガード。`node:test` + 波括弧マッチ抽出 + `vm` で app.js の対象関数だけを
DOM 非依存に評価する（app.js は素のブラウザスクリプトでトップレベルが DOM 結合のため丸ごとロードできない）。

```bash
node pl-summary-app/tests/test_drill_helpers.js   # → 30 tests pass
```

固定している契約:
- **純粋モデル**: `shiftPeriod`（年跨ぎ月シフト）／`buildStorePeriodRows`（当月の店舗別集計・純利益降順・利益率）／
  `pickTopBottom`（重複なし上位N+下位N）／`buildMonthDetail`（前月・前年同月の変化率、比較月なし・分母0の境界）／
  `buildStoreCostTable`（構成比・対売上比）／`buildDeptMonthDetail`（前月比・FY構成比、範囲外/未知コードは null）。
- **ドリルパス定義**: `drillFrom` の遷移表（trend/donut/rank/dept の各フレーム×クリック種別）。未知の組合せで
  フレームが増えないこと、店舗ビュー直下の分岐（月→詳細表／区分→費用内訳表）も固定。
- **描画・配線契約**（source-text ガード）: 各 draw 関数が `data-drill` マーカーを出力すること、`bindDrill` が
  click と Enter/Space を拾うこと、`renderDrillBar` が 戻る/パンくず/解除 を持つこと、init が6チャートを配線し、
  `render` が店舗切替時にドリル状態をリセットすること。

### Provisioner の特性化テスト（`tests/test_provision_domo.py`）

`reconcile_app_studio_context`（manifest → 埋込済みカードの App Framework context mapping の冪等同期）の
回帰ガード 4 件（ネットワーク非依存）。**manifest に alias（`trend`/`dept`）を追加しても、既存カードの
context mapping は自動追随しない**（`domo publish` は "Mapping has changed" と警告するだけ）。未マッピングの
alias は proxy で解決できず FE は graceful degrade（トレンド空表示・事業部タブ非表示）に落ちるため、
`provision_domo.py app-studio` が PUT で同期する（2026-09-16 の他インスタンス事象の回帰ガード）。

```bash
python3 pl-summary-app/tests/test_provision_domo.py   # → Ran 4 tests OK
```

固定している契約: 差分なしは PUT しない（`changed:false`）／差分ありは GET→PUT→GET で検証し
mapping・collections を manifest へ揃える／`dataSetId` 空の alias（未 materialize）は送らない／
PUT 後の検証 GET が不一致なら `RuntimeError`／`contextId` 未解決は警告のみで続行。

---

## デプロイチェックリスト

| 対象 | 操作 | コマンド / 場所 |
|------|------|----------------|
| Pro-Code App | `domo publish` | `pl-summary-app/pro-code/` |
| Workflow プロンプト（統合サブWF） | API デプロイ（draft→検証→release） | `scripts/provision_workflows.py subflow` |
| WF-01 子WF再ピン | API デプロイ（draft→検証→release） | `scripts/provision_workflows.py mainflow` |
| 保存 Code Engine（`report_api.py`） | API デプロイ | `scripts/provision_workflows.py ce` |
| DataFlow AI プロンプト | API デプロイ（backup→PUT→round-trip検証） | `scripts/deploy_dataflow_prompt.py` |
| DataFlow Python / タイル構成 | Domo ETL 画面で編集 → curl で 2042.json 再取得 | dataflows/2042 |
| AppDB 確認 | Data Explorer で確認 | appDb/{collection_id} |

---

## ファイル構成

```
pl-summary-app/
├── README.md                     ← このファイル
├── AGENT.md                      ← AI エージェント引き継ぎノート（ID一覧・手順）
├── docs/
│   └── setup-guide.md            ← ゼロからのデプロイ正典（STEP 0→7・前提/認証/別インスタンス再現/失敗対処）
├── config/
│   └── secrets.env.example       ← 任意の開発者トークン雛形（実値は gitignore 済 secrets.env へ・非コミット）
├── pro-code/                     ← 配布する Pro-Code アプリ本体（CDN 非依存・ランタイム同梱）
│   ├── index.html                ← 概要/事業部別/サマリーの3タブ構成。ヘッダーにロゴ。vendor/domo.js を相対参照
│   ├── app.js                    ← IIFE。summary/trend/dept の3データセット＋AppDBを live 取得（loadTrend/loadDept/buildDept）。カード内セレクター・3タブ切替（事業部別は全社ビューのみ表示・ナビもスキップ）・自前SVG描画＋ホバーツールチップ・**カード内ドリルダウン（drillFrom / render*Card / ドリルバー）**・AppDB(store_id)クエリ・事業部別損益（全社ビュー）
│   ├── app.css
│   ├── logo.png                  ← シンプルスタイル ロゴ（ヘッダー表示・バンドル同梱）
│   ├── thumbnail.png             ← App カードのサムネイル
│   ├── manifest.json             ← App ID・データセット・AppDB マッピング
│   └── vendor/                   ← 同梱ランタイム（CDN 非依存）: domo.js（ryuu.js 4.6.0）＋ LICENSE。index.html が相対参照
├── dev-guide-app/                ← 開発ガイド教材（純静的 Pro Code・App Studio ページ2「開発ガイド」）
│   ├── index.html                ← 全10節の縦スクロール視覚教材（データ接続なし・CSS カウンタで採番）
│   ├── app.css                   ← 単一トークン --brand-primary（臙脂 #7F1D2D）から color-mix で濃淡導出
│   ├── app.js                    ← 出現アニメ／コピー／a11y のみ（データ処理なし）
│   ├── manifest.json             ← 版の正本（datasetsMapping 空・配布時は id を外す）
│   ├── thumbnail.png             ← 300×300 サムネイル
│   ├── vendor/                   ← 同梱 ryuu domo.js（CDN 非依存）
│   ├── README.md / INSTRUCTOR.md ← ガイドアプリ保守ノート／3時間ハンズオン講師ノート
│   └── tests/                    ← check.mjs（Chrome 不要の決定的関門）／shoot.mjs／make-thumbnail.mjs／thumbnail.html
├── scripts/
│   ├── provision_domo.py         ← データ層＋App Studio 配備（apply/sync-manifest/app-studio/embed-guide/verify）。名札（PL_SANDBOX_SUFFIX）対応
│   ├── provision_workflows.py    ← ワークフロー層の再現配備（provision/ce/subflow/mainflow/delete-wf03/verify/all・--apply/--release）＝現行の正。名札対応
│   ├── deploy_dataflow_prompt.py ← DataFlow TextGeneration プロンプトのAPIデプロイ（backup→PUT→round-trip検証、RUN=1で再実行）
│   ├── deploy_wf_prompt.py       ← （レガシー）単一AI_AGENTのWFプロンプト置換。統合サブWFは AI_AGENT が2つのため provision_workflows.py subflow を使う
│   ├── repin_wf01.py             ← （レガシー）WF-01 子WF再ピン。provision_workflows.py mainflow が担う
│   └── deploy_code_engine.py     ← （レガシー）dedupe CE パッケージの作成/新バージョン＋リリース
├── workflow/
│   ├── WF-01_main_loop.json      ← メイン（最新: v1.0.21・CI流の並列サイドブランチ＋終了2つ。dedupe ノードなし。店舗ループに15秒待機タイマー。両SUB_FLOWが統合サブWF cf3b78c2 v1.0.13 を report_type 付きで呼び出す。座標は数学的レイアウトエンジンが算出）
│   ├── WF-02_report_ai.json      ← 統合サブWF（最新: v1.0.13・report_type で店舗/全社に分岐・両AIが pl_report_api(save) で保存・全社AIは Send Email も）
│   └── send_email_tool.json      ← 全社ブランチ Send Email ツールのテンプレ（実在の person ID は焼き込まない）
├── dataflow/
│   ├── 2042.json                 ← ETL 定義スナップショット（TextGeneration タイル2枚の instructions を含む）
│   └── pl_data_generator.py      ← `PY｜損益データ生成` タイルの Python ソース（domomagic）
├── dataset/                      ← マップ対象 DataSet のスキーマのみのミラー（列名＋型のみ・行データ／プレビュー／オーナー／列 ID なし・ワークスペース内部ツールで生成した参照用スナップショット・発行対象外）
│   ├── detail.schema.json        ← 明細 DataSet（`detail`）のスキーマ（34列）
│   └── summary.schema.json       ← 概要 DataSet（`summary`）のスキーマ（49列）
├── app-studio/
│   └── page-layout.json          ← App Studio ページレイアウトのエクスポート（参考）
├── prompts/                      ← AIプロンプト正本（4面 + 共通規約）＋ デプロイ入口
│   ├── deploy-with-agent.ja.md             ← 顧客向けデプロイ入口プロンプト（AIエージェントにそのまま渡す）
│   ├── prompt_shared_conventions.md        ← 一貫性コントラクト（語彙・閾値・問題店舗指標の単一の真実）
│   ├── prompt_dataflow_store_summary.md    ← ETL 店舗短文サマリー（`店舗別AIサマリー`列）正本
│   ├── prompt_dataflow_company_summary.md  ← ETL 全社短文サマリー（`全社AIサマリー`列）正本
│   ├── prompt_wf02_store.md      ← 統合サブWF 店舗ブランチ AI システムプロンプト正本（店舗長文）
│   └── prompt_wf03_summary.md    ← 統合サブWF 全社ブランチ AI システムプロンプト正本（全社長文・ファイル名は履歴保持で不変）
├── code-engine/
│   ├── report_api.py                ← 保存API（現役）`pl_report_api(operation,request)`。save が AppDB保存＋同一doc_key旧版削除を内包
│   └── appdb_maintenance.py         ← （レガシー／フロー非配線）AppDB dedupe 関数 `dedupe_appdb_documents`。手動/バッチ用に残置
└── tests/
    ├── test_report_api.py           ← 保存API `pl_report_api` の特性化テスト（save の重複除去内包・必須フィールド門番・エラー整形。ネットワーク非依存）
    ├── test_appdb_maintenance.py    ← （レガシー util の）dedupe_appdb_documents 特性化テスト12件（空スタブ＋scripted send_request・ネットワーク非依存）
    ├── test_provision_domo.py       ← reconcile_app_studio_context の特性化テスト4件（manifest→context mapping 同期・ネットワーク非依存）
    └── test_drill_helpers.js        ← ドリルダウンの特性化テスト30件（純粋モデル＋drillFrom のパス定義＋描画契約。app.js を DOM 非依存で部分評価）
```

> **Pro-Code の正本は `pro-code/app.css` / `app.js` / `index.html` の3ファイル**（＋ `logo.png` / `manifest.json`）。トレンド・事業部別のスナップショットは以前は別ファイル（`trend_data.js` / `dept_data.js`）だったが、配布時のファイル数を絞るため `app.js` 冒頭のバンドルデータ（`window.__TREND__` / `window.__DEPT__`）へ統合済み。再生成手順は下記参照。
