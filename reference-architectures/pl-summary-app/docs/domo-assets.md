# Domo アセットと配線

物理IDは配備先ごとに異なります。この文書には実環境のIDを記録しません。
名称・alias・構造は契約、解決済みIDはローカル生成物です。配備後に「正しい個数と名前」を
照合するための、ID 非依存のアセット台帳です（レビューの固定制約＝**Domoアセットの個数を変えない**）。

| Domo機能 | 発見キー・alias | 責務 |
|---|---|---|
| Pro Code | `pro-code/manifest.json`（アプリ名 `Store PL AI Insights`） | 静かな臙脂UIの店舗別損益AIインサイト（全社/店舗切替・損益・推移・ランキング・ドリルダウン） |
| seed DataSet | `provision_domo.py` が作る小さな入力 | Magic ETL の入力専用。Pythonタイルが合成P/Lを生成し入力行は無視する（任意の読める DataSet で代替可） |
| AppDB collection | `店舗別損益AI要約`（`syncEnabled: false`） | ワークフロー層が AI 長文レポート `analysis_html` を書き込む（Pro Code のサマリータブの供給源） |
| 標準同期DataSet | seed コレクションの標準ミラー | ETL の入力。独自の行書き込みはしない |
| Code Engine | `plReportService` / alias `plReportApi` / 公開関数 `pl_report_api` | **単一ディスパッチャ**（公開1関数＋非公開 `_service`）。検証・保存・同一 `doc_key` 旧版の掃除・手動開始/実行状況確認 |
| DataFlow | `DF｜店舗別損益データフロー`（Magic ETL v2・`dataflow/2042.json` から再構築） | 合成P/Lの集計と ETL 短文 AI サマリー生成。4本の出力 DataSet を発行 |
| 分析DataSet × 4 | alias `summary` / `detail` / `trend` / `dept`（＝要約・明細・トレンド・事業部） | 同期後の KPI・チャート・短文の供給源。Pro Code が直読する |
| 統合サブWorkflow | `report_type` 分岐（`store`＝店舗 / `company`＝全社）の2 AI エージェント | AI 長文レポートを生成し、どちらも CE 経由で AppDB へ保存する |
| メインWorkflow | WF-01（店舗一覧ループ → 統合サブWF → 保存CE） | AI 長文を全店舗＋全社ぶん生成（アプリから手動実行・約25分・AIクレジット消費） |
| App Studio | DataApp（本体ページ＋開発ガイドページの2ページ） | Pro Code カードと開発ガイドを埋め込む |
| 開発ガイド | `dev-guide-app/`（同梱ランタイムで公開） | App Studio ページ2の教材 |

名札運用（`PL_SANDBOX_SUFFIX`）ではオブジェクト名にサフィックスを付けます。alias は変えません。
詳しい手順は [セットアップガイド](setup-guide.md) を参照してください。

## 状態の保存先

- `domo-assets.json`: provisioner が生成するローカル台帳。`.gitignore` 済みで Git・配布物には含めません（実IDのみ・現在の証拠ではない）。
- `pro-code/manifest.json`: 配備後の対象インスタンスへの接続（`summary`/`detail`/`trend`/`dept`/`plReportApi`）と版。
- `dev-guide-app/manifest.json`: 公開した開発ガイドの design と版。
- `code-engine/`・`dataflow/2042.json`・`workflow/`: 構造の参照資料。物理IDは表しません。

配布版の manifest には design ID が無く、DataSet/AppDB/CE/Workflow 接続は未設定です。
データ層は `apply` → `sync-manifest` → publish → `app-studio` → `verify`、ワークフロー層は
`provision_workflows.py provision --apply --release`（名称で発見または新規作成し、インスタンス非依存へ再束縛）で
配備先の値を解決します。配備後、この台帳の名称・alias・個数が live と一致することを `verify` と App Studio で確認します。
