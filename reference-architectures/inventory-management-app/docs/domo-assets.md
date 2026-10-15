# Domo アセットと配線

物理IDは配備先ごとに異なります。この文書には実環境のIDを記録しません。
名称・alias・構造は契約、解決済みIDはローカル生成物です。

| Domo機能 | 発見キー・alias | 責務 |
|---|---|---|
| Pro Code | `pro-code/manifest.json` | 入出庫・QR・履歴・分析・マスタ管理 |
| AppDB datastore | `inventory-management-app` | アプリのストア |
| AppDB collection | `inventory_management_records` | `record_type` で7種の論理レコードを保存 |
| 標準同期DataSet | AppDBコレクションの標準ミラー | 独自の行書き込みは禁止 |
| Code Engine | `Inventory Management \| Transaction Service` / `inventoryApi` | 公開 `inventory_api` と私有サービスヘルパー |
| DataFlow | `Inventory Management \| Analytics` | 分析とAI短文の生成 |
| 分析DataSet | `Inventory Management \| Dashboard` / `inventoryDashboard` | 同期後のKPI・明細・AIコメント |
| Workflow | `Inventory Management \| Low Stock Notification` | 開始→AI Agent→終了、CEが最新有効版を起動 |
| App Studio | `在庫入出庫管理ハンズオン` | 本体と開発ガイドの2ページ |

名札運用ではオブジェクト名にサフィックスを付けます。aliasは変えません。
詳しい手順は [AI再構築ランブック](ai-rebuild-runbook.md) を参照してください。

## 状態の保存先

- `domo-assets.json`: provisionerが生成するローカル台帳。Git・配布物には含めません。
- `pro-code/manifest.json`: 配備後の対象インスタンスへの接続と版。
- `dev-guide-app/manifest.json`: 公開したガイドのデザインと版。
- `app-studio/app-studio.json`: レイアウト参照スナップショット。実IDの再利用指示ではありません。
- `code-engine/asset.json`・`dataflow/asset.json`・`workflow/status.json`: 構造の参照資料。

配布版のmanifestにはデザインIDがなく、DataSet/AppDB/CE/Workflow接続は未設定です。
`apply` → `sync-manifest` → publish → `app-studio` → `verify` で配備先の値を解決します。
台帳の `instance` が選択先と異なる場合、provisionerはその台帳を使用しません。

## 埋込と検証

本体・ガイドのカードは `FOLLOW_LATEST` とし、標準60×82・compact12×29の静的layoutを使います。
`interaction: DISABLED` はクリックまで無効にするため使いません。
`verify` でmanifest・公開latest・埋込実効版の一致を確認します。
過去の検証日やスクリーンショットを配備先の成功証拠にはしません。
