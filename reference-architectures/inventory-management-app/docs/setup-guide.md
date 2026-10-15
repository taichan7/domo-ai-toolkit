# セットアップガイド

## 1. 前提

- Domo Dev Studio CLI（npm の `ryuu` パッケージが提供する `domo` コマンド。認証情報は `~/.config/configstore/ryuu/<instance>.json`）とNode.jsがインストール済み
- Python 3.9以上
- 対象Domoインスタンスへ Domo CLI でログイン済み
- AppDB、Code Engine、DataFlow、Pro Code、App Studioの作成・編集権限

公開toolkitのソースを使い、最初に対象インスタンスと検証用の名札を明示する。既定の接続先はない。
認証はDomo CLIを使い、実トークンをソースやチャットに書かない。

```bash
export DOMO_INSTANCE=<your-instance>.domo.com
export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'
domo login -i "$DOMO_INSTANCE"
```

### 別インスタンスへの再現

このフォルダは特定インスタンスに固定されない。プロビジョニングは全アセットを名称で「発見または作成」する冪等処理のため、新しいインスタンスでも同じ構成を再生成できる。手順は次の通り。

1. 上記の対象インスタンスを設定してログインする（`domo login -i "$DOMO_INSTANCE"`）。
2. `export DOMO_INSTANCE=<your-instance>.domo.com` を設定する。あわせて**配備モード**を選ぶ：共有インスタンスでのハンズオン・検証は `export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'`（全Domoオブジェクト名へ全角括弧の名札が付き、バックエンド＝AppDB／Code Engine／DataFlow／出力DataSet／通知Workflowモデルも、App Studioアプリ／カードも**自分専用の隔離コピー**になって本番・他参加者と衝突しない。解決IDは参加者ごとの状態ディレクトリ `~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/` へ書かれ、ローカル生成の `domo-assets.json` を汚さない）、本番名の正規コピーを配備する本番メンテナだけ `export INVENTORY_ALLOW_PRODUCTION=1`。未設定だと `apply`／`app-studio` などの書込み系コマンドは本番の上書きを防ぐガードで停止する（読み取り専用の `verify`／`sync-manifest`／`export-app-studio` はガード対象外）。
3. （任意）通知Workflowモデルは `apply` が名称で発見または API で新規作成するため、事前の手作りは不要。作成時は **Start → AI Agent → End** の3タイル雛形と「メール送信（sendEmail）」toolを流し込み、AI Agentの指示文・入力・プロンプト・DataSet接地（実DataSetの実IDへ後付け）・メール配線まで整える。**既存の特定モデルに固定したいときだけ** `export DOMO_WORKFLOW_MODEL_ID=<model-id>`（任意）を設定する（指定すると `apply` は発見/作成せずそのIDを尊重し、空モデルなら雛形を流し込む）。
4. `apply` を実行し、出力の `ASSET_RESULT` に並ぶ作成済みID（collection／dashboard DataSet／Code Engine package／Workflow model）を確認する。
5. `sync-manifest` を実行する。`pro-code/manifest.json` の alias→物理ID（`collectionsMapping.id`／`datasetsMapping.dataSetId`／`packagesMapping.packageId`／`workflowsMapping.modelId`）を対象インスタンスの新IDへ合わせる。Domo資産は変更せず、名称で発見したIDをID欄へ書き込むだけの冪等処理で、既に一致していれば差分は出ない。**サンドボックス（名札付き）ではこのとき FE 完全隔離のため、配線に加えてトップレベルの `id` を自動で外す**（＝次の `domo publish` が id 省略で“参加者専用デザイン”を新規採番し、名札バックエンドへ束縛する。これで App Studio のカードも参照バックエンドではなく自分のバックエンドを指す）。
6. `domo publish` を実行する。**サンドボックスでは手順5が既にトップレベル `id` を外しているので、そのまま publish すれば Domo が参加者専用 design を新規採番し、その実IDを `manifest.json` へ書き戻す**（本番名の正規コピーを配備する場合のみ、初回は `id` を空にするか対象インスタンスの新規designに合わせる）。Domoが払い出したdesign IDを控える。
7. `app-studio` → `export-app-studio` を実行する。`app-studio` は App Studioアプリ本体を**名称で発見または新規作成**し、ページ1の本体カードとページ2の開発ガイドを配置する（両Pro Codeの事前公開が必要）。公開ソースに `domo-assets.json` は同梱しない。解決した実IDは対象インスタンス・名札に対応するローカル台帳へ保存し、次回の `verify` で使う。他顧客や他参加者の台帳をコピーしない。
8. `verify` を実行し `ok: true` を確認する。公開latest・Manifest・App Studio実効版の3者一致と、レコード最小件数を検証する。

対象ホストが未設定・不正なら、認証やAPI書込み前に停止する。`DOMO_WORKFLOW_MODEL_ID` は任意で、
未設定なら通知Workflowを名称で発見/作成する。公開manifestのdesign IDと接続IDは未設定なので、
provision・alias同期後に両Pro Codeを公開し、App Studioへ配置する。

AIコーディングエージェント（Claude Code）が再構築を実行する場合は、ゲート・停止条件・境界を明示した [AI再構築ランブック](ai-rebuild-runbook.md) に従う。

## 2. ローカル開発

```bash
cd inventory-management-app/pro-code
domo dev
```

正常なモバイル対応designと同じ1×1既定カードにするため、Manifestの`fullpage`／`allowFullPage`は省略する。データ、AppDB、Code Engineはそれぞれ `inventoryDashboard`, `inventory_management_records`, `inventoryApi` のエイリアスで参照する。Code Engineの物理関数名は `inventory_api`、物理入力名は `request_json` だが、Pro Code Editor向けエイリアスは記号を含まない `inventoryApi`／`requestJson` とする。ブラウザJavaScriptへ物理IDを書かない。

Code Engineはreleased version（実値は `manifest.json` が正）をManifestへ明示する。通知Workflowは物理model ID（`modelId`・同じく `manifest.json` が正）をManifestへ固定し、版はインスタンス依存で動くため固定しない（`verify` の `ok` は `modelId` 一致とCEソースへの起動先焼き込み `codeEngineWorkflowModelEmbedded` で判定）。Workflowの起動はフロントではなくCode Engineが行い、起動のたびにモデルの有効な最新版を実行時に解決する（Workflowを改版してもカードの再埋め込みは不要）。

Domoの外では `domo` がないため、同梱したローカルデモデータでUIを表示する。このモードはUI開発用であり、Domoの権限やデータ保存の代替ではない。

## 3. Domoアセットの作成・更新

`apply` は書込み系コマンドなので、本番の上書きを防ぐガードが働く。実行前に配備モード（上記「別インスタンスへの再現」step 2）を設定しておく：ハンズオン・検証は `INVENTORY_SANDBOX_SUFFIX='検証・<氏名>'`、本番名の正規コピーを配備する本番メンテナは `INVENTORY_ALLOW_PRODUCTION=1`。未設定だと本番名の上書きを拒否して停止する。

```bash
cd inventory-management-app
python3 scripts/provision_domo.py apply
```

`apply` の処理は次の通り。

1. `inventory-management-app` datastore内の `inventory_management_records` を名称で再利用する。
2. スキーマと `syncEnabled: true` を適用する。
3. Code Engineの最新ソースが異なる場合だけ新バージョンをリリースする。
4. `SEED` を実行する。既存のマスタキーと `SEED-*` リクエストは重複しない。
5. WorkflowをStart → AI Agent（既存DataSet context 1件＋`sendEmail` tool 1件） → Endの3タイルへ保つ。
6. `SEED` 直後にAppDB標準同期を即時キック（`POST api/datastores/v1/export/{datastoreId}`、空ボディ）し、標準同期DataSetへ全件反映されるまで待つ。既定の約15分間隔スケジュールを待たず、DataFlowが最新のDataSetを読めるようにするための前倒し実行で、DataSetへ行を直接書き込む独自同期ではない。
7. AppDB標準同期DataSetをDataFlowの唯一入力に配線し、3セクションと7タイルの説明notesを適用する。
8. DataFlowを実行し、`SUCCESS`以外なら失敗として終了する。

DataSet APIへの書込みは行わない。AppDBのデータ移送はDomo標準同期だけが担当する。

初期マスタは `SEED` が投入するが、公開後は管理者が画面の「マスタ管理」から品目・ロケーション・基準在庫をCRUDできる（Code Engine `MANAGE_MASTER` 経由、削除はドキュメント自体をAppDBから消す物理削除で依存データも連鎖削除。取引・通知履歴は保持）。再プロビジョニングは既存マスタを重複投入せず、管理者が追加・更新した行を保持する。

## 4. Pro Codeの公開

```bash
cd inventory-management-app/pro-code
domo publish
```

公開後、デザインIDとPro Code versionは `manifest.json` と `domo-assets.json` に記録する。`packagesMapping[].version` はDomo上のCode Engine released versionと一致させる（`packagesMapping[].version` を変えたときは `code-engine/asset.json` の `version` も同値へ更新する。`tests/test_frontend_shell.js` が両者の厳密一致を要求するため）。`workflowsMapping[].version` はインスタンス依存で動くため手で一致させる必要はない（`verify` の `ok` 条件に含めず、乖離は `workflowWarnings` に可視化するだけ。詳細は下の完了条件を参照）。

別インスタンスでは `domo publish` の前に `python3 scripts/provision_domo.py sync-manifest` を実行し、`apply` が作成した collection／dashboard DataSet／Code Engine package／Workflow model のIDを `manifest.json` の alias 配線へ合わせる（詳細は「別インスタンスへの再現」）。

## 5. App Studio配置

`app-studio` も書込み系で、同じ本番保護ガードが働く（§3 と同じく `INVENTORY_SANDBOX_SUFFIX` か `INVENTORY_ALLOW_PRODUCTION=1` を設定してから実行する）。事前に `cd dev-guide-app && domo publish` でページ2の開発ガイドを公開しておく（未公開だとページ2確保時に停止する）。

```bash
cd inventory-management-app
python3 scripts/provision_domo.py app-studio
```

同名の最小構成カードがある場合は再利用し、重複作成しない。参照インスタンスの現行カード／outer proxy／inner context IDは `domo-assets.json`（ローカル生成・配布しない） の `appStudio` に記録する（別インスタンスでは新しいIDが採番される）。

対象インスタンスのローカル台帳と名称からApp／Page／Cardを解決する。新規カードではcontextとouter proxyを分離し、
既存layoutはwritelock下で更新する。`interaction: DISABLED` はPCのクリックも無効にするため使わない。
カードmetadataは1×1／`fullpage:false`を検証し、詳細な配置契約は
[architecture.md](architecture.md) と [AI再構築ランブック](ai-rebuild-runbook.md) を参照する。

現行contextは `designVersion: null` の最新公開版追従である。`app-studio` と `verify` の出力に `versionMode`, `effectiveDesignVersion` を表示し、Manifest／Domo公開latest／カード実効版が一致しない場合は `ok: false` とする。

App Studio定義を将来の再配置用JSONへ再取得する場合は次を実行する。

```bash
python3 scripts/provision_domo.py export-app-studio
```

出力は `app-studio/app-studio.json` で、Data App、Page stack、カード、standard／compact layout、Pro Code context mappingを含む。利用者・所有者・日時・編集ロック・認証情報は保存しない。

## 6. 確認

```bash
python3 scripts/provision_domo.py verify
```

`ok: true` に加えて次を確認する。

- `codeEngineFunctionCount: 1`
- `codeEnginePrivateHelperCount: 6`
- `dataflowInputCount: 1`
- `dataflowTileCount: 7`, `dataflowSectionCount: 3`, `dataflowDocumentedTileCount: 7`
- `workflowTileCount: 3`, `workflowAiAgentCount: 1`
- `workflowAiAgentEmailToolCount: 1`, `workflowAiAgentDatasetContextCount: 1`
- `workflowAiAgentDatasetContextIds` が `dashboardDatasetId` だけを含む
- `proCodeManifestVersion`, `proCodePublishedLatestVersion`, `appStudioEffectiveDesignVersion` が一致する
- `manifestCodeEngineVersion` と `codeEngineVersion` が一致する（同一の released version）
- `manifestWorkflowModelId` と `workflowModelId` が一致する（通知Workflowモデルの同一性を固定）。**Workflowの版（`manifestWorkflowVersion` と `workflowVersion`）は `ok` の条件に含めない**：この版はインスタンス依存で動く（新規インスタンスは seed の 1.0.0 から実 DataSet／実 sendEmail 版へ接地するため 1.0.1 以降へ作り直され、`sync-manifest` は版欄を書き戻さない）ので、一致しないのが正常。乖離は `workflowWarnings` に可視化されるだけで `verify` は失敗しない。
- `workflowLastRunVersion` は直近に実際に起動されたWorkflowインスタンスの解決版を映す読み取り専用値である。起動はCode Engineがサーバー側で行い、モデルの有効な最新版を実行時に解決するため、Workflowを改版・releaseするだけで次回の通知から最新版が使われる（カードの再配線・再埋め込みは不要）。版の乖離（宣言版 vs live版）は `verify` の `workflowWarnings` に可視化されるが失敗にはせず、代わりに `codeEngineWorkflowModelEmbedded`（Code Engineソースへの起動先modelIdの焼き込み）を `ok` 条件に含める（詳細は [test-results.md](test-results.md) の「Workflow版解決」）。
- `appStudioCardPresent: true`, `appStudioCardVersionMode: FOLLOW_LATEST`
- `appStudioInteractionType` が `DISABLED` ではない（既定＝未設定）, `appStudioHideWrench: true`, `appStudioEditInAppViewer: true`
- `appStudioLayoutDynamic: false`, `appStudioStandardLayout: [60, 82]`, `appStudioCompactLayout: [12, 29]`
- `appStudioStandardPageBreakY: 82`, `appStudioCompactPageBreakY: 29`
- `legacyCollectionsRemaining: []`
- `standardSyncDatasetId` と `dashboardDatasetId` が空でない
- ITEM 30、LOCATION 6、RULE 30、TRANSACTION 136以上、BALANCE 131以上（BALANCEはAIテキスト生成タイルの100行下限を満たすためのシード規模）

DataFlow出力はQuery APIで `record_type` ごとの行数とKPI値を確認できる。運用画面の即時反映と分析画面の同期後反映には時間差がある。

## 7. Workflow／AI Agent

3タイルの通知Workflowには、AI Agent内の `sendEmail` toolと既存Dashboard DataSet context 1件を設定済みである。閾値遷移時にCode Engineが最新の有効版を実行時に解決して開始し、既存 `ALERT_HISTORY` へ開始成否（`STARTED`／`FAILED`）を記録する。タイルを増やさず、在庫更新の成否と非同期通知の成否を分離する。実メール試験は明示したテスト宛先だけで行う。

`sendEmail` tool の版はインスタンスごとに提供版が異なるため、プロビジョナが**掲載された最高のスカラー宛先版（<2.1.17）を自動採用**する（2.1.17以降は宛先が list 型になり、AI Agentがスカラー入力から list を構築する際に送信失敗する事象を根本回避するため）。スカラー版が掲載されない（list 版のみの）インスタンスでは既知良好版 `2.1.12` へ固定する。配備先がこの版を実行できない場合のみ、`export DOMO_SEND_EMAIL_VERSION=<そのインスタンスで送信できる版>` を設定して `apply`（または `workflow`）を再実行する（詳細は [ai-rebuild-runbook.md](ai-rebuild-runbook.md) の失敗時の判断表・環境変数表）。
