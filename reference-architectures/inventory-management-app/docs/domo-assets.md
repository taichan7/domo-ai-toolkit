# Domoアセット台帳

最終検証日: 2026-08-09／インスタンス: `maintenance-instance.domo.com`

## 現行アセット

| Domo機能 | 名称 | ID／バージョン | 責務 |
|---|---|---|---|
| Pro Code | 在庫入出庫管理 | design `3c156897-8ddb-4761-9664-9073a9f2aa90`（版は `manifest.json` が正） | 操作、QR、履歴、分析UI、管理者マスタCRUD |
| AppDB datastore | `inventory-management-app` | `a253e9d9-e3f0-4ba4-bab2-347c50694054` | ハンズオン用ストア |
| AppDB collection | `inventory_management_records` | `b76a1233-038d-4f99-aa19-1705469b7f7e` | 7種の論理レコードを保存 |
| 標準同期DataSet | `inventory_management_records_inventory-management-app_APP_DB` | `5402ecee-34f4-4caf-be2f-9ce09fa0dad8` | AppDBのDomo標準ミラー |
| Code Engine | `Inventory Management \| Transaction Service` | package `ba587df4-66a1-41e4-abe9-7af3e4a474d3`（released version固定・実値は `manifest.json` が正） | 公開1＋私有6関数の業務処理ディスパッチャ |
| DataFlow | `Inventory Management \| Analytics` | `2246` | 7タイル・3説明セクションで分析行を生成し、品目ごとのAI在庫コメントを付与 |
| 分析DataSet | `Inventory Management \| Dashboard` | `6f407387-7980-44b4-b1fd-3e4b12ec3d34` | KPI、品目別・棚別、推移、不足、滞留、通知、品目ごとのAI在庫コメント |
| Workflow | `Inventory Management \| Low Stock Notification` | model `0c61146c-9e04-4a9b-bc5e-7c43384d06d6`（released版は `manifest.json` が正） | Start → AI Agent（Dashboard DataSet＋`sendEmail` tool） → End |
| App Studio | 在庫入出庫管理ハンズオン | app `1468477910`, view `1828849038`, layout `381523384` | 静的layout、standard 60×82、compact 12×29、終端PAGE_BREAK |
| Pro Code card | 在庫入出庫管理 | card `935895512`, proxy `d4ffb9db-1eb8-40c2-8cc5-5d4362fbd2b0`, context `cda96048-2d39-47c0-acc7-5b003e3e4582` | `FOLLOW_LATEST`、実効版はManifest最新公開版に一致、1×1／既定`fullpage:false`、`fitToFrame:false`、カード操作は既定（未設定＝操作許可、`editInAppViewer:true`） |
| Pro Code（開発ガイド） | 在庫管理リファレンス ガイド | design `aeb6e8d5-2548-4636-a7c2-7e1eeadd4ce1`（版は `dev-guide-app/manifest.json` が正） | App Studio **ページ2**に載る純静的な開発ガイド文書（データ非接続。旧「開発者リファレンス」から同じdesignを再利用して中身を差し替え） |
| App Studio ページ2 | 開発ガイド | view `41450484`, card `417954969`, layout `69282970` | 開発ガイド（`dev-guide-app`）のカードを1枚埋込。静的layout、standard 60×82、compact 12×29、終端PAGE_BREAK、`FOLLOW_LATEST` |

機械可読版は [domo-assets.json](../domo-assets.json) にある。

## Wiring

```text
Pro Code collectionsMapping
  inventory_management_records
    → AppDB b76a1233-038d-4f99-aa19-1705469b7f7e

Pro Code packagesMapping
  inventoryApi
    → Code Engine ba587df4-66a1-41e4-abe9-7af3e4a474d3 / released version（manifest.json が正）/ inventory_api

Pro Code workflowsMapping
  lowStockNotification
    → Workflow 0c61146c-9e04-4a9b-bc5e-7c43384d06d6 / released版は manifest.json が正 / 不足通知を開始

Pro Code datasetsMapping
  inventoryDashboard
    → DataSet 6f407387-7980-44b4-b1fd-3e4b12ec3d34

AppDB standard sync
  collection b76a1233-038d-4f99-aa19-1705469b7f7e
    → DataSet 5402ecee-34f4-4caf-be2f-9ce09fa0dad8

DataFlow 2246
  input:  5402ecee-34f4-4caf-be2f-9ce09fa0dad8
  output: 6f407387-7980-44b4-b1fd-3e4b12ec3d34
```

App Studioカードは外側instance/proxyと内側contextを別UUIDで持つ標準2層構造にした。Code Engine／Workflowの参照は公開designのManifestにあり、Code Engineはreleased version（実値は `manifest.json` が正）を固定する。通知Workflowは物理 model ID（`modelId`・同じく `manifest.json` が正）を固定し、版はインスタンス依存で動くため固定しない（`verify` の `ok` は `modelId` 一致で判定し、版の乖離は非ブロッキング警告として可視化する）。カードcontextの `designVersion` はnullで同一designの最新公開版を追従し、実効版はManifest最新公開版に一致することを `verify` で確認した。ManifestのCode Engineエイリアスは `inventoryApi`、物理関数は `inventory_api`、入力エイリアスは `requestJson`、物理入力は `request_json` である。

## AppDB標準同期

- `syncEnabled: true`
- AppDBコレクションが生成する標準DataSetのみを使用
- 現在の標準同期DataSetは355行。最終DataFlow execution `2063473` はこの355行を入力に読み、252行（集計行＋品目×ロケーションごとのAI在庫コメント）を出力した。AIテキスト生成タイルの100行下限を満たすため、残高が100件以上になるようシード済み。
- 同期用Code Engine、Workflow、API書込み、Pro Codeによる二重書込みは存在しない
- `apply` はSEED直後に標準同期を即時起動（`POST api/datastores/v1/export/{datastoreId}`、空ボディ）し、標準同期DataSetへ全件反映されるのを待ってからDataFlowを回す。既定の約15分間隔スケジュールを待たないための前倒し実行で、DataSetへ行を直接書き込む独自同期ではない
- **DataSet名 `inventory_management_records_inventory-management-app_APP_DB` はDomoが `{コレクション名}_{データストア名}_APP_DB` で自動採番する管理下の名前**であり、DataSet側のリネームAPI（`PUT api/data/v3/datasources/{id}` は405、`/properties` PUTは`name`を無視）では変更できない。コレクション名を変えても既存DataSet名には遡及しない（検証済み）。全配線はDataSet **ID** で行うため機械名は表示上のもので、変更が必要ならDomo UIから手動リネームする。分析面の可読名はDataFlow出力 `Inventory Management | Dashboard` が担う。

## Code Engine公開契約

`inventory_api(operation, request_json="{}")` の1関数のみ。

ソース内の私有関数も `_is_true`, `_resolve_recipient_email`, `_records`, `_register`, `_notify_now`, `_admin` の6件だけである（旧 `_master` のマスタCRUDは `_admin` に統合済み）。

| `operation` | 用途 | 権限 |
|---|---|---|
| `AUTH` | Domoユーザーと管理者状態を返す | ログインユーザー |
| `GET_STATE` | 残高と基準在庫の取得 | ログインユーザー |
| `REGISTER` | 入庫・出庫の検証と登録 | — |
| `NOTIFY_NOW` | 現在の最も深刻な不足に対し手動で通知Workflowを起動（CEが最新の有効版を実行時に解決） | ログインユーザー |
| `NOTIFICATION_STATUS` | 通知状態の監査用更新（通常導線ではCEが起動結果を自動記録。互換・手動補正用） | イベント作成者 |
| `RECALCULATE` | 取引正本から残高を再構築 | 管理者 |
| `SEED` | 冗等なデモデータ投入 | 管理者 |
| `MANAGE_MASTER` | 品目・ロケーション・基準在庫の登録／更新／物理削除（`action` を内包） | 管理者 |

カメラ、写真、QR画像解析、`LOC:`／`ITEM:`形式判定はPro Codeの `qr-scanner.js` が端末内で処理する。無関係なはがきQRも文字列検出までは成功し、その後にアプリ用ではないと拒否する。Code Engineはブラウザ入力を信頼せず、`REGISTER` 時に有効マスター、権限、数量、在庫、重複を最終検証する。

## App Studioスナップショット

`app-studio/app-studio.json` にData App、Page stack、カード、standard／compact layout、Pro Code context mappingを保存した。利用者・所有者・日時・writelock・認証情報は除外している。`python3 scripts/provision_domo.py export-app-studio` で同じ登録済みIDから再取得できる。

このアプリは2ページ構成である。**ページ1**（landing view `1828849038`）が在庫入出庫管理（`3c156897-…` のPro Codeカード）、**ページ2**（view `41450484`）が開発ガイド（`aeb6e8d5-…` の dev-guide Pro Codeカード）。ページ2のスロットは旧「開発者リファレンス」から**同じ design ID を再利用して開発ガイドへ中身を差し替えた**もので、`dev-guide-app` の publish＝同一designの新版、ページ2は `FOLLOW_LATEST` で再埋め込みなしに追従する（新design採番・旧ページ2削除はしない）。ページ2は `app-studio` サブコマンドが冪等に確保する（登録ピン→カードタイトル一致で既存発見→無ければページ追加＋カード埋込＋layout）。ページ2のタブ名は、新規インスタンスでは「開発ガイド」で自動作成されるが、既存の `maintenance-instance` では既存ビューを強制改名しない（統合dataappのPUTを避けるため）ので現行タブ名のまま残る（改名はApp Studioでの任意の一度きり手作業）。`domo-assets.json` の `appStudio.page2` にページ2の実ID（design／view／card／layout）を保持し、`proxyId`／`contextId` は解決できたインスタンスでのみ埋める（参照インスタンスでは空）。なお `INVENTORY_SANDBOX_SUFFIX` を付けたサンドボックス実行では、解決したIDはこのコミット済み `domo-assets.json` ではなく参加者ごとの状態ディレクトリ（`~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/`）へ書かれる。ページ2は自己フィットのスクロール文書のため、layout寸法（standard 60×82／compact 12×29）は現行 compact 12×6 がモバイルで低すぎるのを上書きする目的で整えるが、`verify` では過剰適合させない。

## Workflow／AI Agent

| 項目 | 現在値 |
|---|---|
| 状態 | `RUNTIME_WIRING_DEPLOYED` |
| Pro Codeからの実行呼出し | 閾値遷移時（自動）と在庫不足パネルの手動ボタン（`NOTIFY_NOW`）から Code Engine を呼ぶ（Workflow の起動はフロントではなく CE が行う） |
| Code Engineからの起動 | あり。モデルの**有効な最新版**を実行時に解決し、`api/workflow/v1/instances/message`（`modelId`＋`version`・`messageName`）で起動する（カードの再埋め込みは不要） |
| メール送信 | AI Agent内の`sendEmail` toolが1回実行 |
| 不足履歴 | CE が起動結果を `STARTED`／`FAILED` で保存（起動しない場合は `SKIPPED`） |
| モデル | `0c61146c-9e04-4a9b-bc5e-7c43384d06d6`（released版は `manifest.json` が正。3タイル、AI Agent 1件） |
| AI Agent tool | `sendEmail` 1件（package v2.1.12） |
| AI Agent DataSet context | `Inventory Management \| Dashboard` 1件（`6f407387-7980-44b4-b1fd-3e4b12ec3d34`） |

通知Workflowは3タイルと `sendEmail` toolを維持し、既存のDashboard DataSetをAI Agentの知識へ1件だけ接続した。新規DataSetは作成していない。Workflow入力は確定値5件（`event_type`／`headline`＝見出しの1件／`shortage_lines`＝通知対象の不足を1行1件で列挙した確定一覧／`recipient_email`／`occurred_at`）で、プロンプトは `headline` と `shortage_lines` を今回通知の唯一の正とする。自動（閾値遷移）通知も手動通知（`NOTIFY_NOW`）も、Code Engineが現時点の不足全件を `shortage_lines` に確定値として組み立てて渡すため、複数不足は1通のメールに集約される（品目・数量はDataSetではなく入力から転記する）。DataSetの `SHORTAGE`／`ALERT`／傾向は同期遅延のある任意の定性補足に限定し、入力の数値・件数を上書きしない。この集約はプロンプトと入力契約を反映した新しいWorkflow版をリリースすれば有効になる（起動はCode Engineが最新の有効版を実行時に解決するため、カードの再埋め込みは不要）。実メールの端から端までの試験は指定したテスト宛先で行う。

## 削減済み資産

2026-08-07に以下を削除した。

- 旧AppDBコレクション7件
- 各コレクションの旧標準同期DataSet 7件
- 初期版および重複した最小構成版のApp Studioカード2件（`908623114`, `593330986`）
- 作業中に誤作成した重複App Studioアプリ1件（`1481079764`、作成直後に削除し404を確認）

削除前に現行DataFlowの1入力化、正常完了、旧DataSetのカード参照数0を確認した。
