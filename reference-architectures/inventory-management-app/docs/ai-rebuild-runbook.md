# AI再構築ランブック（Claude Code 向け）

このリポジトリの在庫入出庫管理リファレンスアプリを、**顧客のDomoインスタンスにゼロから立ち上げる**
ための、AIコーディングエージェント（Claude Code）向けの決定論的手順書である。人間向けの解説は
[setup-guide.md](setup-guide.md) を、設計背景は [architecture.md](architecture.md) と
[design-principles.md](design-principles.md) を参照する。本書はそれらと重複する説明を避け、
「どの順序で何を実行し、各段でどう成否を判定し、いつ止まるか」に絞る。

## 0. 前提と原則

- **べき等**: `provision_domo.py` は全アセットを名称で「発見または作成」する。同じインスタンスで
  再実行しても重複を作らない。途中で失敗しても、原因を直して同じコマンドを再実行してよい。
- **配備構造の成功ゲート**: `verify` が `ok: true` を返し、かつ §2 の件数条件を満たすこと。
  中間出力のIDだけで成功としない。このゲートは本番適用の認定ではない。
  [distribution-readiness.ja.md](distribution-readiness.ja.md) の権限・並行更新・負荷・通知・実機確認も配備先で行う。
- **人手でUIからアセットを作る境界はゼロ**: AppDB／Code Engine／DataFlow／**通知Workflowモデル**／
  **App Studioアプリ本体＋ページ1カード埋め込み**／**ページ2＝開発ガイド**まで、すべて
  `provision_domo.py` がDomo APIで「発見または作成」する。文書化範囲はAPIごとに異なり、配備先での検証が必要。あなたが Domo の画面を開いてアセットを
  手作りしたり、生成したIDを人に尋ねたりする必要は**一切ない**。かつては ①通知Workflowモデルの事前作成、
  ②App Studioアプリの作成とページ1カード埋め込み、が人手境界だったが、①は `apply`（§3 STEP 1）が、
  ②は `app-studio`（§3 STEP 5）が、それぞれ名称で発見または API で新規作成するようになり、**どちらも
  人手不要**になった。公開ソースには `domo-assets.json` を同梱しない。
  対象インスタンスの資産を名称で解決し、実IDをそのインスタンス・名札専用のローカル台帳へ保存する。
- **配布物に固有名を残さない**: 顧客名・URL・個人名・メールを、コード／ドキュメント／コメント／
  コミットメッセージ／App Studio JSON／テストに**一切書かない**。
  `DOMO_INSTANCE` は必須で、未設定時の保守環境への自動接続はない。
- **本番保護ガードと配備モード**: 書込み系コマンド（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）は、
  対象アセット名が本番名（名札なし）のままだと、誤って本番の在庫入出庫管理アセット（App Studio
  「在庫入出庫管理ハンズオン」＋AppDB／Code Engine／DataFlow／出力DataSet／通知Workflow）を上書き
  しないよう**実行を拒否**する。着手前に次のどちらかを設定する。①共有インスタンスでのハンズオン・検証は
  `export INVENTORY_SANDBOX_SUFFIX='検証・<氏名>'`——全オブジェクト名へ全角括弧の名札（例「（検証・田中）」）が
  付き、バックエンド（AppDB datastore＋collection／Code Engine／DataFlow／出力DataSet／通知Workflowモデル）と
  App Studioアプリ／カードまで丸ごと**自分専用の隔離コピー**になる（本番や他参加者と非衝突。alias値・operation名・
  タイル/セクションid・Workflow入力名などコード内部の契約は不変）。解決した実IDは参加者ごとの状態ディレクトリ
  `~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/` に書かれ、
  台帳は共有しない。②本番名の正規コピーを配備する本番メンテナだけ `export INVENTORY_ALLOW_PRODUCTION=1`
  を明示する（名札なし＝本番と byte 一致の従来挙動）。読み取り専用の `verify`／`sync-manifest`／`export-app-studio`
  はガード対象外でそのまま通る。
- **開始前に読む**: 本書 → [setup-guide.md](setup-guide.md) →
  [domo-assets.md](domo-assets.md)（alias↔物理IDの対応）→ [data-model.md](data-model.md)。
  版番号などの実値は常に `manifest.json` と各コマンド出力を正とする。

## 0.5 AIが陥りやすい誤りと正しい対処（着手前に必ず読む）

このリファレンスはAIエージェントが配備を支援できるように作ってある。不要な手作業や
対象資産の取り違えを防ぐため、着手前に次の5つを確認する。

1. **「App／AppDB／Workflow を画面で手作りしてIDを渡して」と言わない**（最頻の誤り）。
   AppDBコレクション・Code Engine・DataFlow・**通知Workflowモデル**・**App Studioアプリ＋カード**は、
   すべて `apply`／`app-studio` がDomo APIで作成する。**通常の配備手順ではUIからの手作りは不要。**
   どれも「手で作れ」「IDを教えて」と求めるのは誤り。まず `apply`（§3 STEP 2）→ `app-studio`（§3 STEP 5）を
   実行する。`app-studio` は対象インスタンス・名札の資産を名称で発見／作成するので、
   保守用IDをコピーする必要はない。

2. **1時間規模の DataFlow 実行をキャンセル・再トリガーしない**。分析のAIテキスト生成タイルは残高件数と
   インスタンス負荷に比例して伸び、実測で数分〜1時間規模になり得る。`apply` はインラインで
   `DOMO_DATAFLOW_WAIT_SECONDS`（既定1800秒）まで待つが、**超過して `RUNNING` のまま返っても失敗ではない**
   ——実行はサーバ側で継続する。待ち切れないときは数分おいて `verify` で `SUCCESS` を確認するか、
   `DOMO_DATAFLOW_WAIT_SECONDS` を延ばして再待機する。決してキャンセルや二重トリガーをしない
   （二重起動は無駄な実行を増やすだけ）。本当の失敗は `FAILED`／`ABORTED`／`ERROR` 等の終端状態だけ。

3. **AppDB の 403 を「AppDBが無効」と結論しない**。AppDBエンドポイントの 403 は、ほぼ認証スコープ不足か
   所有者違い（他人所有のコレクションを触ろうとした）が原因で、**機能が無効化されている証拠ではない**。
   `domo login -i <instance>` で入り直し、対象インスタンスへの管理権限と、自分が操作するのは自分の
   コレクションかを確認する。「このインスタンスはAppDB非対応」といった誤結論で止まらない。

4. **同名の既存資産を削除・再作成しない（同僚のデータを壊さない）**。同一インスタンスへ複数名が練習で
   繰り返しデプロイするのは想定内。`provision_domo.py` は全資産を**名称で「発見または再利用」**する冪等設計で、
   既存の同名コレクション／モデル／アプリがあれば**そのまま再利用**する（重複を作らない）。既存資産が
   自分でなく同僚の所有でも、**削除・上書き・再作成は絶対にしない**（他者のデータと履歴を破壊する）。
   衝突を「作り直して解決」しようとしないこと——再利用が正しい挙動。

5. **SEED の一時的な整合エラーを致命扱いしない**。AppDBは作成直後に検索索引へ即時反映されないこと
   （結果整合性）があり、SEEDはこの反映を待つバリアを内蔵する。もし SEED が
   `APPDB_CONSISTENCY_TIMEOUT` を返したら、それは**反映待ちが予算内に終わらなかった一時的状態**で、
   コードの欠陥でも `INVALID_ITEM`（品目不正）でもない。数十秒おいて `apply`／SEED を**再実行**すれば
   よい（作成済みデータは冪等に再利用され、重複投入は起きない）。

**全自動デプロイ契約**: 上記を守れば、あなたは STEP 0→6 を通してユーザーに手作業を**一切**求めることなく、
ダミーデータ入りで動くアプリまで自動で到達できる（App Studioアプリの作成・カード埋め込みも `app-studio` が
自動で行う）。迷ったら「手で作らせる」前に、該当コマンドを実行するか §6 の判断表を見る。



すべて満たすまで先へ進まない。

```bash
cd inventory-management-app
python3 --version            # 3.9 以上
node --version               # インストール済み
domo --version               # Domo Dev Studio CLI（未導入なら npm i -g ryuu で導入）
# 対象インスタンスへログイン済みか（未ログインなら §3 STEP 0 でログインする）
ls ~/.config/configstore/ryuu/   # <instance>.json が対象インスタンス分あるか
```

- 対象Domoインスタンスに AppDB／Code Engine／DataFlow／Pro Code／App Studio の作成・編集権限があること。
- 認証トークンをリポジトリやファイルへ書き込まないこと。CLIの既存設定（上記 configstore）または
  一時的な `SID`／`INSTANCE` 環境変数だけを使う。

**ローカル事前検証（Domoへ触れる前に必ず緑にする）**:

自動テストの正本手順は [検証](test-results.md#自動テストローカル) §自動テスト（ローカル）の5コマンドに一本化（`pip install` → `node --test` → 全 `pro-code/*.js` の `node --check` → `unittest` → `node dev-guide-app/tests/check.mjs`）。デプロイ前はこれを緑にしたうえで、デプロイ用JSONの妥当性も確認する:

```bash
python3 -m json.tool pro-code/manifest.json >/dev/null
python3 -m json.tool dev-guide-app/manifest.json >/dev/null   # 開発ガイド(ページ2)
python3 -m json.tool domo-assets.json >/dev/null
```

ここが赤ならDomoへ何も送らない。まずローカルを直す。

## 2. 不変契約（「完了」の定義）

`python3 scripts/provision_domo.py verify` が `ok: true` を返し、出力が次を満たすこと
（実値は出力を正とし、本書に固定値を書かない — 件数の下限のみ示す）。

- **版の三者一致**: `proCodeManifestVersion` ＝ `proCodePublishedLatestVersion` ＝
  `appStudioEffectiveDesignVersion`。
- **released版の宣言一致**: `manifestCodeEngineVersion` ＝ `codeEngineVersion`。
- **通知Workflowの配線**: `manifestWorkflowModelId` ＝ `workflowModelId`、かつ
  **`codeEngineWorkflowModelEmbedded: true`**（Code Engineソースに起動先modelIdが焼き込まれている）。
  Workflowの起動はフロントではなくCEが行い、起動のたびに有効な最新版を実行時に解決する。
  **Workflowの版は `ok` の条件に含めない。** この版はインスタンス依存で動く（新規インスタンスは seed の
  1.0.0 から実 DataSet／実 sendEmail 版へ接地するため 1.0.1 以降へ作り直され、`sync-manifest` は版欄を
  書き戻さない）。したがって `manifestWorkflowVersion` と `workflowVersion` は一致しないのが正常で、
  乖離は `workflowWarnings` に可視化されるだけで `verify` は失敗しない。健全性は下記の内容検証で担保する。
- **Code Engine表層**: `codeEngineFunctionCount: 1`、`codeEnginePrivateHelperCount: 6`、
  `codeEngineWorkflowModelEmbedded: true`。
- **DataFlow**: `dataflowInputCount: 1`、`dataflowTileCount: 7`、`dataflowSectionCount: 3`、
  `dataflowDocumentedTileCount: 7`。
- **Workflow**: `workflowTileCount: 3`、`workflowAiAgentCount: 1`、
  `workflowAiAgentEmailToolCount: 1`、`workflowAiAgentDatasetContextCount: 1`、
  `workflowAiAgentDatasetContextIds` が `dashboardDatasetId` だけを含む。
- **App Studio**: `appStudioCardPresent: true`、`appStudioCardVersionMode: FOLLOW_LATEST`、
  `appStudioInteractionType` が `DISABLED` でない、`appStudioHideWrench: true`、
  `appStudioEditInAppViewer: true`、`appStudioLayoutDynamic: false`、
  `appStudioStandardLayout: [60, 82]`、`appStudioCompactLayout: [12, 29]`、
  `appStudioStandardPageBreakY: 82`、`appStudioCompactPageBreakY: 29`。
- **App Studio ページ2（開発ガイド・登録時のみ検証）**: `domo-assets.json` に `appStudio.page2`
  が在るときだけ確認する（未デプロイなら素通り）。`appStudioPage2Present: true`、
  `appStudioPage2CardPresent: true`、`appStudioPage2CardVersionMode: FOLLOW_LATEST`。ページ2の
  layout寸法には過剰適合しない（自己フィットの縦スクロール文書のため）。
- **AppDB単一化**: `legacyCollectionsRemaining: []`、`standardSyncDatasetId` と
  `dashboardDatasetId` が空でない。
- **シード最小件数**: ITEM 30 / LOCATION 6 / RULE 30 / TRANSACTION 135以上 / BALANCE 131以上（下限は `scripts/provision_domo.py` の `required` 件数が正）
  （BALANCEはAIテキスト生成タイルの100行下限を満たすための規模）。

## 3. 手順（各ステップにゲート）

### STEP 0 — 対象インスタンスの選択とログイン

```bash
export DOMO_INSTANCE=<customer-instance>.domo.com    # 未設定なら maintenance-instance.domo.com（保守用）
domo login -i "$DOMO_INSTANCE"
```

### STEP 1 — 通知Workflowモデル（`apply` が自動作成・人手不要）

**この STEP に人手の操作はない。** かつては Domo Workflows で **Start → AI Agent → End** の3タイルモデルを
手作りして model ID を渡す必要があったが、いまは `apply`（STEP 2）が担う。`apply` は通知Workflowモデルを
**名称（`Inventory Management | Low Stock Notification`）で発見し、無ければ API で新規作成**する。作成時は
3タイル雛形（開始→AI Agent→終了）と `sendEmail` tool（このインスタンスの実 packageVersion をライブ解決）を
流し込み、続けてAI Agentの指示文・入力・プロンプト・DataSet接地を整える。**UIでの手作りも model ID の
受け渡しも不要**で、同一インスタンスへ複数回・複数名がデプロイしても同名モデルを1つ共有する（重複を
作らない・他者のモデルを壊さない）。

```bash
# 通常は何も設定しなくてよい。既存の特定モデルに固定したいときだけ（任意）:
# export DOMO_WORKFLOW_MODEL_ID=<model-id>   # 指定すると apply は発見/作成せずこのIDを使う（pin）
# 任意: TextGenerationタイルのDomoGPTモデルを差し替える場合
# export DOMO_AI_SUMMARY_MODEL_ID=<instance-valid-model-id>
```

- `DOMO_WORKFLOW_MODEL_ID` は**任意**。未設定なら `apply` が名称で発見/作成する（推奨）。設定した場合のみ、
  そのモデルを尊重して pin する（既存運用の互換用）。pin したモデルが空でも `apply` が雛形を流し込む。
- **STOP条件はない**。この STEP のために止まらず、そのまま STEP 2 の `apply` へ進む。

### STEP 2 — データ・ロジック層の構築

着手前に配備モードを設定しておく（§0「本番保護ガードと配備モード」）。未設定だと `apply` は本番名の上書きを
防ぐガードで停止する。ハンズオン・検証は `export INVENTORY_SANDBOX_SUFFIX='検証・<氏名>'`（名札付きの隔離コピー）、
本番名の正規コピーを配備する本番メンテナだけ `export INVENTORY_ALLOW_PRODUCTION=1` を明示する。

```bash
python3 scripts/provision_domo.py apply
```

`apply` はAppDB collection再利用→スキーマ＋`syncEnabled`適用→通知Workflowモデルの発見/作成→Code Engine差分リリース（起動先modelIdを焼き込み）→`SEED`→AppDB標準同期の即時キック＋反映待ち→DataFlow配線＋notes適用→DataFlow実行→Workflow 3タイル整形（実DataSet接地・release）までを行う（詳細は [setup-guide.md](setup-guide.md) §3）。DataSet APIへ直接書き込まない。

**AppDB標準同期DataSetの自動生成（DataFlowの入力）**: collection に `syncEnabled: true` を適用すると、
Domoが AppDB→DataSet の**標準同期DataSet**（`ASSET_RESULT.collection.datasetId` ＝ `verify` の
`standardSyncDatasetId`）を自動生成する。これが **DataFlow の唯一の入力**になる。`apply` は `SEED` 直後に
このDataSetのexportを即時キックし、反映（数百行の到達）を待ってから DataFlow を配線・実行する
（既定の約15分間隔スケジュールを待たない）。このDataSet名はDomo管理で改名できない
（[architecture.md](architecture.md) 参照）。DataSet APIへ直接行を書かず、データ投入はAppDB(`SEED`)＋
標準同期だけが担う。

- **ゲート**: 出力 `ASSET_RESULT` に collection／標準同期DataSet／dashboard DataSet／Code Engine
  package／Workflow model のIDが並ぶこと。`workflowAi.status` は `READY`（`--skip-workflow` 時のみ
  `SKIPPED`）。DataFlow実行 `lastExecutionState` は `SUCCESS` が理想だが、**`RUNNING`／`QUEUED` は失敗では
  ない**（下記）。
- **`RUNNING` のまま返っても止めない（キャンセル・再トリガー禁止）**: `apply` はインラインで
  `DOMO_DATAFLOW_WAIT_SECONDS`（既定1800秒）まで実行を待つ。分析のAIテキスト生成タイルは数分〜1時間規模に
  なり得るため、待ち上限を超えて `lastExecutionState: RUNNING`／`QUEUED` で返ることがある。これは
  **正常**で、実行はサーバ側で継続する。数分おいて `verify` の `dataflowLastRunState` で `SUCCESS` を確認するか、
  `DOMO_DATAFLOW_WAIT_SECONDS` を延ばして再待機する。**同じ `apply` を再実行して二重起動しない。**
- **本当の失敗のときだけ停止**: `lastExecutionState` が `FAILED`／`FAILED_DATA_FLOW`／`ABORTED`／
  `CANCELLED`／`ERROR` のときは停止して原因を調べる（多くは AppDB同期反映待ちのタイムアウトか
  DomoGPTモデルID不正 → §6）。
- **縮退（コールドインスタンス）**: 標準同期がまだ `datasourceId` を払い出していない場合、`apply` は
  DataFlow生成をスキップし `lastExecutionState: WAITING_FOR_STANDARD_SYNC` を返して**正常終了**する
  （例外は投げない）。数分待って `apply` を再実行すれば、同期反映後に DataFlow が生成・実行される
  （べき等）。
- **縮退（SEED反映待ち）**: SEED が `APPDB_CONSISTENCY_TIMEOUT` を返した場合は、AppDBの検索反映が予算内に
  終わらなかった一時的状態（コード欠陥ではない）。数十秒おいて `apply` を再実行する（冪等・重複なし）。

### STEP 3 — Manifestの配線を対象インスタンスへ合わせる

```bash
python3 scripts/provision_domo.py sync-manifest
```

`manifest.json` の alias→物理ID（`collectionsMapping.id`／`datasetsMapping.dataSetId`／
`packagesMapping.packageId`／`workflowsMapping.modelId`）を STEP 2 で確定したIDへ書き込む。
名称で発見したIDをID欄へ入れるだけのべき等処理。

- **ゲート**: `git diff pro-code/manifest.json` を見て、alias配線IDが対象インスタンスのIDへ
  更新されている（または既に一致）こと。`sync-manifest` は4つの接続ID・版だけを書き、版フィールド
  （`packagesMapping[0].version`／`workflowsMapping[0].version`）は触れない。版の突き合わせは
  STEP 4 と §2 の `verify` で行う。

### STEP 4 — Pro Codeの公開

初回公開では `manifest.json` トップレベルの `id`（Pro Code design ID）を、空にするか対象インス
タンスの新規designに合わせる。既存の保守用instanceのdesign IDを他インスタンスへ流用しない。

```bash
cd pro-code && domo publish && cd ..
```

- **ゲート**: Domoが払い出した design ID を `manifest.json` トップレベル `id` に反映する。
  さらに、`apply` が新規インスタンスでCEを参照版と異なる版（例: 初回は `1.0.0`）で
  リリースした場合は、`manifest.json` の `packagesMapping[0].version`（FEが呼ぶCE版）を、
  `apply` の `ASSET_RESULT.codeEngine.version`（＝`verify` の `codeEngineVersion`）へ手で一致させてから、
  必要なら再度 `domo publish` する。`sync-manifest` はこの版欄を書き換えないため、§2 の
  「released版の宣言一致」はこの手動突き合わせで満たす（値は必ずライブ出力から取り、本書やコードに
  固定値を書かない）。**通知Workflowの版（`workflowsMapping[0].version`）は合わせなくてよい** —
  CEが起動のたびに最新の有効版を実行時に解決するため動作に影響せず、乖離は `workflowWarnings` に
  可視化されるだけである。
  `packagesMapping[0].version` を live 値へ合わせるときは、`code-engine/asset.json` の `version` も
  同じ値へ更新する（`tests/test_frontend_shell.js` が両者の厳密一致を要求するため、片方だけ変えると
  ローカル事前検証（§ ローカル事前検証）が赤化する）。

### STEP 4.5 — 開発ガイド（dev-guide-app）の公開

App Studio のページ2に載る開発ガイド（`dev-guide-app/`）も Pro Code バンドルなので
publish が要る。データセット・ワークフローには一切つながない純静的文書のため配線は不要。この
ページ2は旧「開発者リファレンス」から**同じ design を再利用して開発ガイドへ中身を差し替えた**もの。

```bash
cd dev-guide-app && domo publish && cd ..
```

- **初回（新規インスタンス）**: `dev-guide-app/manifest.json` の `id` を省略して publish する
  （新規 design が採番される）。払い出された design ID を `manifest.json` の `id` に反映する。
- **更新（同一インスタンス・既存の `maintenance-instance` を含む）**: `id`（`aeb6e8d5-…`）はそのまま残して publish する。
  同一 design の新版が出るだけなので、ページ2のカードは `FOLLOW_LATEST` で**再埋め込みなし・孤児カードなし**に
  更新される。新しい design を採番したり旧ページ2を削除したりはしない。
- **ゲート**: publish が成功し design が対象インスタンスに存在すること。未公開のまま STEP 5 の
  `app-studio` を走らせると、ページ2作成時に「dev-guide-app を publish してから再実行」で停止する。

### STEP 5 — App Studio 埋め込み（`app-studio` が全自動・人手不要）

**この STEP に人手のUI操作はない。** `app-studio` が Data App 本体を**名称（`APP_STUDIO_NAME`）で発見または
API で新規作成**し、ランディングページに STEP 4 のPro Codeカードを1枚 embed し、layoutを整え、続けて
ページ2（開発ガイド）も確保する。あなたが Domo UI でアプリを作ったり、生成IDを人に尋ねたりする
必要はない。

`app-studio` も書込み系なので本番保護ガードの対象。STEP 2 で設定した配備モード（`INVENTORY_SANDBOX_SUFFIX`
または `INVENTORY_ALLOW_PRODUCTION=1`）を同じシェルで保ったまま実行する（§0「本番保護ガードと配備モード」）。
`app-studio` のガードは解決後の対象名で判定するため、名札（`INVENTORY_SANDBOX_SUFFIX`）を付ければ
App Studioアプリ／カードも名札付きの隔離コピーになる。

- 配布版に `domo-assets.json` は含めない。ローカルに台帳があっても、
  対象インスタンスにそのIDが**在れば再利用**、**無ければ**（GETが404）停止せず**名称による発見／作成へ
  自動フォールバック**する（重複は作らない）。IDを手で書き換える必要はない。
- 解決した実ID（appId／viewId／cardId／proxyId／contextId とページ2の各ID）は `app-studio` が
  `domo-assets.json` へ**書き戻す**ので、続く `export-app-studio`／`verify` は人手のID貼り付けなしで通る。
- カードも同様に、登録cardIdが対象に在れば再利用、無ければカードタイトル（`APP_STUDIO_CARD_TITLE`）で
  発見、それも無ければ新規作成する。

```bash
python3 scripts/provision_domo.py app-studio
python3 scripts/provision_domo.py export-app-studio
```

`app-studio` は静的layout（`isDynamic: false`）、standard 60×82・compact 12×29、終端PAGE_BREAK、
`fitToFrame: false`、`interaction`既定（未設定＝操作許可）、`hideWrench: true`、
`editInAppViewer: true` を設定する。**`interaction: DISABLED` は採用しない**（モバイルの青枠は
消せるがPCクリックも殺す。実機確認済みのアンチパターン）。`export-app-studio` は再配置用JSONを
`app-studio/app-studio.json` へ書き出す（利用者・所有者・日時・認証情報は保存しない）。

**ページ2＝開発ガイドも自動**: `app-studio` はページ1を整えた後、STEP 4.5 で公開した
dev-guide design を**同じアプリのページ2として冪等に確保**する（登録ピン→カードタイトルで既存
発見→無ければページ追加＋カード埋込＋layout）。ページ2は静的layout・standard 60×82／compact 12×29
（モバイルで低すぎる現行 12×6 を上書き）・終端PAGE_BREAK で整える。ページ2のタブ名は、新規インスタンスでは
「開発ガイド」で自動作成されるが、既にプロビジョニング済みのインスタンス（`maintenance-instance`）では既存ビューを
強制改名しない（統合dataappのPUTを避けるため）ので現行タブ名のまま残る。改名したいときは App Studio で
一度だけ手で変える任意の作業。`export-app-studio` は2ページ・各ページのPro Code contextを
`app-studio/app-studio.json` に含める（ページ2の context を解決できない環境では空許容）。

### STEP 6 — 検証（成功ゲート）

```bash
python3 scripts/provision_domo.py verify
```

§2 の全条件と `ok: true` を確認する。落ちた場合は §6 の判断表に従う。

## 4. 環境変数リファレンス

| 変数 | 既定 | 用途 |
|---|---|---|
| `DOMO_INSTANCE` | （未設定・必須） | 対象インスタンス。未設定・不正なら認証前に停止 |
| `INVENTORY_SANDBOX_SUFFIX` | （未設定） | 設定すると全Domoオブジェクト名へ全角括弧の名札（例「（検証・田中）」）を付け、バックエンド（AppDB datastore＋collection／Code Engine／DataFlow／出力DataSet／通知Workflowモデル）とApp Studioアプリ／カードまで**自分専用の隔離コピー**を作る。共有インスタンスでのハンズオン・検証用。解決IDは `~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/` へ（ローカル生成の `domo-assets.json` を汚さない）。未設定＝本番と byte 一致の従来挙動 |
| `INVENTORY_ALLOW_PRODUCTION` | （未設定） | `1`／`true`／`yes` で本番保護ガードを明示解除し、本番名のまま書込み系（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）を実行する。**本番名の正規コピーを配備する本番メンテナのみ**。名札（`INVENTORY_SANDBOX_SUFFIX`）を付ける場合は不要 |
| `DOMO_WORKFLOW_MODEL_ID` | （未設定） | **任意**。未設定なら `apply` が通知Workflowモデルを名称で発見/作成する（推奨）。設定したときだけ、そのモデルにpin（発見/作成せず尊重）。**インスタンス個別** |
| `DOMO_AI_SUMMARY_MODEL_ID` | `domo.domo_ai.domogpt-medium-v2.2:anthropic` | TextGenタイルのDomoGPTモデル。無効なら差し替え |
| `DOMO_SEND_EMAIL_VERSION` | `2.1.12` | 通知WFの sendEmail tool に使う既知良好のスカラー宛先版。**掲載スカラー版が無い（list 版のみの）インスタンス**で既定が実行できないときだけ、そのインスタンスで送信できる sendEmail 版へ上書きする。掲載スカラー版があれば自動採用されるので通常は不要。**インスタンス個別** |
| `DOMO_DATAFLOW_WAIT_SECONDS` | `1800` | `apply` がDataFlow実行をインラインで待つ上限秒。**超過して `RUNNING` でも失敗ではない**（サーバ側で継続）。低速インスタンスや大きめシードで長く待ちたいとき延長 |
| `SID` / `INSTANCE` | （未設定） | CLI設定を使わず一時セッションIDで認証する場合のみ。両方を対で設定 |
| `DOMO_DEVELOPER_TOKEN` | （未設定） | **任意**。デプロイには不要（`domo login` で足りる）。デプロイ後のAPI開発・非対話自動化用。実値は`config/secrets.env`（gitignore済）にだけ置き、コミットしない |

## 5. CLIサブコマンドリファレンス

`python3 scripts/provision_domo.py <command>`。

| command | 役割 | いつ使うか |
|---|---|---|
| `apply` | データ・ロジック層を構築（AppDB/CE/DataFlow/Workflow/SEED/同期/DF実行） | 初回、およびCE・DataFlow・スキーマ・シードを変えたとき |
| `sync-manifest` | alias→物理IDをManifestへ反映 | 別インスタンス初回、または配線IDがずれたとき |
| `app-studio` | App Studioアプリ＋ページ1カードを発見または作成しlayoutを整え、ページ2（開発ガイド）を冪等に確保。解決した実IDを `domo-assets.json` へ書き戻す（`appStudio.appId` があれば再利用、無ければ・404なら名称で発見/作成） | STEP 4.5（`dev-guide-app` publish）の後。人手のUI操作は不要 |
| `export-app-studio` | App Studio定義（2ページ・各ページのPro Code context）を再配置用JSONへ書き出す | layout確定後のスナップショット取得 |
| `workflow` | 通知Workflowを3タイル定義へ整形（`apply` の一部を単独実行） | Workflow定義だけを再適用したいとき |
| `verify` | 配備構造チェック（本番適用の認定とは別） | 各段の後、特に最終確認 |
| `cleanup-legacy` | 旧・分割コレクションの残骸を掃除 | 旧構成からの移行時のみ |

書込み系（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）は本番保護ガードの対象で、本番名のままでは
`INVENTORY_SANDBOX_SUFFIX`（名札付き隔離コピー）か `INVENTORY_ALLOW_PRODUCTION=1`（本番メンテナのみ）を
設定しないと停止する（§0）。読み取り専用（`verify`／`sync-manifest`／`export-app-studio`）はガード対象外。

`--skip-dataflow-run` を `apply` に付けるとDataFlow実行を省略できる（配線だけ更新したいとき）。
`--skip-workflow` を付けると通知Workflowモデルの発見/作成・配線を省き、データ・ロジック層だけを先に
構築する（通常は不要。新規インスタンスの段階的立ち上げ用）。

## 6. 失敗時の判断表

| 症状 | 原因 | 対応 |
|---|---|---|
| `verify` の版三者（`proCode*`）が不一致 | publish未反映、または `sync-manifest` 未実行 | `sync-manifest`→`domo publish`→`app-studio` を順に再実行 |
| `manifestCodeEngineVersion` が `codeEngineVersion` と不一致 | 新規インスタンスでCEが参照版と異なる版でリリースされた（`sync-manifest` は版欄を書かない） | `manifest.json` の `packagesMapping[0].version` を `verify` の `codeEngineVersion` に合わせて `domo publish`→`verify`（STEP 4 参照） |
| `verify` の `workflowWarnings` に「workflow released v… but manifest declares v…」が出る | **正常。失敗ではない。** 通知Workflowの版はインスタンス依存（seed 1.0.0→実 DataSet/実 sendEmail 版へ接地して 1.0.1 以降へ作り直し・`sync-manifest` は版欄を書き戻さない）で、`ok` の条件に含めていない（CEが起動時に最新の有効版を解決するため動作条件でもない） | 何もしない。`manifest.json` の `workflowsMapping[0].version` を手で書き換えたり `domo publish` し直したりしない（インスタンス固有値を配布物へ焼き込まないため）。健全性は modelId 一致＋`codeEngineWorkflowModelEmbedded`＋Workflow内容検証で担保済み |
| `apply` が `WAITING_FOR_STANDARD_SYNC` で終了しDataFlow未生成 | 標準同期DataSetの `datasourceId` が未払い出し（コールド／反映が遅い） | 数分待って `apply` を再実行（同期反映後にDataFlowが生成・実行される。べき等） |
| DataFlow実行が `RUNNING`／`QUEUED` のまま `apply` が返った | インライン待ち上限（`DOMO_DATAFLOW_WAIT_SECONDS`）を超えたが実行はサーバ側で継続中 | **失敗ではない。キャンセル・再トリガーしない。** 数分後に `verify` で `SUCCESS` を確認、または `DOMO_DATAFLOW_WAIT_SECONDS` を延長して再待機 |
| DataFlow実行が `FAILED`／`ABORTED`／`ERROR`（本当の失敗） | AppDB同期反映待ちのタイムアウト／DomoGPTモデルID不正 | 数分後に `apply` 再実行、または `DOMO_AI_SUMMARY_MODEL_ID` を対象インスタンスで有効なDomoGPTモデルIDへ差し替え（利用可能なモデルは対象インスタンスのAI設定で確認） |
| SEED が `APPDB_CONSISTENCY_TIMEOUT` を返す | 作成直後のAppDB検索反映（結果整合性）が予算内に終わらなかった一時的状態（コード欠陥でない） | 数十秒おいて `apply`／SEED を再実行（作成済みデータは冪等に再利用され重複しない）。`INVALID_ITEM` と誤認しない |
| AppDBエンドポイントが 403 | 認証スコープ不足、または他人所有コレクションへのアクセス（＝AppDB無効ではない） | `domo login -i <instance>` で入り直し、管理権限と自分の所有コレクションかを確認。「AppDB非対応」と結論しない |
| 同名の既存コレクション／モデル／アプリがある | 同一インスタンスへ複数回・複数名がデプロイ済み（想定内） | **削除・再作成しない。** 名称で再利用されるのが正しい挙動（`apply` は冪等）。他者所有でも壊さない |
| 書込み系（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）が「本番の在庫入出庫管理アセットを上書きします」で停止する | 配備モード未設定（名札も `INVENTORY_ALLOW_PRODUCTION` も無く、対象名が本番名のまま）＝本番保護ガード | ハンズオン・検証は `export INVENTORY_SANDBOX_SUFFIX='検証・<氏名>'`、本番名の正規コピーを配備する本番メンテナは `export INVENTORY_ALLOW_PRODUCTION=1` を設定して再実行（§0。読み取り専用コマンドはガード対象外） |
| `app-studio` が別インスタンスで停止する | ほとんど起きない。`appStudio.appId` が対象に無くても404を自己修復して名称で発見／作成する。停止するのは dev-guide design 未公開（STEP 4.5 未実施）など前提未達のとき | メッセージに従い前提を満たして再実行（例: `cd dev-guide-app && domo publish` の後に `app-studio`）。`appStudio` のIDを人手で書き換える必要はない |
| BALANCEが131行未満で失敗 | シード規模不足、または既存データ衝突で生成デモがスキップされた | 空のcollectionで `apply` を再実行し `SEED` を通す（件数は生成デモの決定論的出力に対応。AIテキスト生成タイルの100行下限を満たすため131が必要） |
| Code Engine関数数が1でない | ソースに公開関数を増やした | 公開は `inventory_api` 1本＋`_`始まり6ヘルパーへ戻す |
| RECIPIENT_EMAIL_MISSING | 通知宛先が空 | FEのPeople API解決メールへフォールバック配線を確認（CE `_resolve_recipient_email`） |
| 通知Workflowが起動後に `FAILED`／メールが届かない | 配備先インスタンスが採用した sendEmail 版を実行できない、または宛先の型不一致（2.1.17+ の list 宛先を AI がスカラー入力から構築できず送信失敗する既知事象） | `apply`／`workflow` は**掲載された最高スカラー版（<2.1.17）を自動採用**し、list 版しか無いインスタンスでは既定の既知良好版 `2.1.12` へ固定する。それでも送信できない（配備先に 2.1.12 が無い等）場合は、**そのインスタンスで送信できる sendEmail 版**を調べて `export DOMO_SEND_EMAIL_VERSION=<その版>` を設定し `apply`（または `workflow`）を再実行する。`instances/message` で1回起動して `COMPLETED`＋実着信まで確認する（`verify` の構造OKだけで出荷しない） |
| 「AI在庫通知を実行」が通知を開始できない／`verify` の `codeEngineWorkflowModelEmbedded: false` | Code Engineソースに起動先modelIdが焼き込まれていない（旧CEのまま、または `--skip-workflow` 配備） | `apply` を再実行してCEを再配備し、`verify` で `codeEngineWorkflowModelEmbedded: true` を確認する。カードの再配線・再埋め込みは不要（CEが最新の有効版を実行時に解決する） |

## 7. 既知の無害な警告（追いかけない）

`ok: true` を落とさない。矯正しようとしない。

- `workflowRuntimeMatchesDeclared: false` — 直近に実際に起動された版と Manifest 宣言版の乖離を示す。
  通知Workflowの版はインスタンス依存で動く（seed 1.0.0→接地で 1.0.1 以降へ作り直し）ため一致しない
  のが正常。CEは起動時に最新の有効版を解決するので動作条件ではない。`verify` は乖離を
  `workflowWarnings` に可視化するだけで失敗させない（詳細は [test-results.md](test-results.md)
  「Workflow版解決」）。
- `appStudioLayoutDynamic: false` — モバイルの青枠・スクロールロック抑制のための意図した静的layout。
- `workflowLastRunVersion` の宣言版との差 — 「過去の起動」を映す読み取り専用の事後情報。

## 8. 絶対にやらないこと（境界）

- DataSet APIへ直接書き込まない。AppDBのデータ移送はDomo標準同期だけが担当する。
- `interaction: DISABLED` を使わない（PCクリックを殺す）。
- 配布物に顧客名・URL・個人名・メールを書かない（コメント／コミット／JSONを含む）。
- Code Engineの公開関数を増やさない（`inventory_api` 1本＋`_`始まり6ヘルパー固定）。
- 台帳の直接編集・削除で訂正しない。取引（`TRANSACTION`）は追記専用の正本として書き換えない。
- git は明示パスのみstageし、`git add -A`／`-a` を使わない。コミットには
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` を付ける。
- FEのみ（CSS/JS/HTML）の変更では `apply` を実行しない（Manifest版を上げて publish→app-studio→
  export→verify）。CE・バックエンド・DataFlow python変更のときだけ `apply` から始める。

## 9. Workflow版を上げたときの手順（カード再埋め込みは不要）

通知Workflowの起動はCode Engineがサーバー側で行う。CEは起動のたびにモデルの**有効（release済み）な
最新版**を解決し、`api/workflow/v1/instances/message`（`messageName`＝開始タイルのタイトル、
`modelId`＋`version` を明示）で開始する。起動される版を決めるのはカードの配線ではないため、
**Workflowを改版・releaseするだけで、次回の通知から最新版が使われる。カードの再配線・再埋め込み・
旧カード削除は不要**である。

1. 新しいWorkflow版をリリースする（Domo Workflowsで編集→リリース。`python3 scripts/provision_domo.py
   workflow` は接地・入力契約の整備と release を自動で行う）。
2. `python3 scripts/provision_domo.py verify` を実行し、`ok: true` と
   `codeEngineWorkflowModelEmbedded: true`（CEソースへの起動先modelIdの焼き込み）を確認する。
3. モデルを作り直した等で modelId 自体が変わった場合だけ、`python3 scripts/provision_domo.py apply`
   を再実行してCEを再配備する（起動先IDを更新する。データ・ロジック層は冪等に再利用される）。
   `sync-manifest` は版を書き戻さない（modelId が変わっていれば `sync-manifest` でManifestの配線も更新する）。

> 背景（旧実装）: 以前はフロントが `/domo/workflow/v1/models/{alias}/start` で起動していたため、
> 起動される版が App Studio カードの配線（埋め込み時点のトリガースナップショット）に固定され、版を
> 上げるたびにカードを作り直して再埋め込みする必要があった。現在はCEが実行時に版を解決するため、
> この手作業の境界は無い。
>
> 通知が開始できないときは `ALERT_HISTORY` の `notification_status: FAILED` と `error_message` を
> 確認する（接続先未設定＝`apply` 未実施／有効版なし＝未release／API失敗＝開始結果の確認が必要）。
> `verify` は版の乖離を `workflowWarnings` に可視化するが失敗にはしない（§7）。
