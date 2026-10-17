# 店舗別損益 AI サマリー

> English: A deployable teaching reference for synthetic store P/L, AI report generation and Domo app provisioning. Read [distribution readiness](docs/distribution-readiness.md) before deployment.

Domo の Pro Code、AppDB、Magic ETL、Code Engine、Workflows、App Studio を組み合わせた
ハンズオン用リファレンスです。架空ブランド「シンプルスタイル」の合成損益データを使います。

## 主な機能

業務担当者が 1 画面で店舗別・全社の損益を把握するためのダッシュボードです。

- **全社／店舗の切替** — 全店舗合算と個店を同じ画面で切り替える。
- **損益サマリー（概要）** — 売上・費用・純利益・利益率の KPI と黒字店舗数。純利益＝売上−営業費用（税金・営業外は含まない）。
- **可視化** — 売上・純利益の 24 ヶ月トレンド（折れ線）、費用内訳（ドーナツ）、店舗別 純利益ランキング（横棒）。
- **事業部別損益**（全社ビュー限定） — 売上・粗利益の積み上げ、売上構成比、月次トレンド、予算達成状況。
- **ドリルダウン** — チャートから月次詳細・費用内訳・店舗内訳へ、各カード内で深掘りする。
- **AI 経営インサイト** — 損益データから長文レポートを**手動**生成（全社／店舗別）。定期実行はしない。

## 配布とセットアップ

複数顧客への配布は、公開 `domo-ai-toolkit` の `reference-architectures/pl-summary-app/` のソースを使います。
配布版ではデザインIDと接続IDを空にし、
対象インスタンスで再解決します。`domo-assets.json`・認証情報・sandbox state は同梱しません。

1. [配布品質と適用範囲](docs/distribution-readiness.ja.md)を確認する。
2. [AI向け入口プロンプト](prompts/deploy-with-agent.ja.md)を渡す。
3. [セットアップガイド](docs/setup-guide.md)の順に配備・検証する。
4. 変更を加えるAIは [AGENT.md](AGENT.md) の不変契約を守る。

接続先は `DOMO_INSTANCE=<your-instance>.domo.com` で明示します。ハンズオンには
`PL_SANDBOX_SUFFIX='検証・氏名'` を使います。名札なしの配備は全インスタンスで
`PL_ALLOW_PRODUCTION=1` が必要です。既定の保守環境へ自動接続しません。

これは教材・参照実装です。顧客本番への適用には、権限・データ分離・負荷・メール宛先・
会計定義・バックアップをその環境で検証する必要があります。

## 構成と正本

```text
AppDB seed → 標準同期 DataSet → Magic ETL → summary / detail / trend / dept
                                         ↓
親Workflow → 店舗・全社サブWorkflow → pl_report_api → AppDBレポート
                                         ↓
                  Pro Code → App Studio（本体＋開発ガイド）
```

| 対象 | 正本・役割 |
|---|---|
| 画面 | `pro-code/`。静かな臙脂UI、全社/店舗切替、損益・推移・ランキング・ドリルダウン |
| 配線 | `pro-code/manifest.json`。alias `summary/detail/trend/dept/plReportApi` |
| データ層 | `scripts/provision_domo.py`。seed・AppDB・DataFlow・App Studioを名称で発見/作成 |
| ワークフロー層 | `scripts/provision_workflows.py provision`。保存CE・統合サブWF・親WFを再束縛して配備 |
| 保存API | `code-engine/report_api.py`。検証・保存・同一キー旧版掃除・手動開始/状況確認 |
| ETLテンプレート | `dataflow/2042.json`。ファイル名は履歴由来で、配備先の物理IDを表さない |
| データ生成 | `dataflow/pl_data_generator.py`。合成損益データ。実顧客データを含まない |
| プロンプト | `prompts/prompt_shared_conventions.md` と各 `prompt_*.md` |
| 教材 | `dev-guide-app/`。App Studioページ2へ同梱ランタイムで公開 |

このアプリが作る Domo アセットの ID 非依存な台帳（名称・alias・個数の契約）は
[Domoアセット台帳](docs/domo-assets.md)にあります（配備後の個数照合に使う）。

## ドキュメント

| 文書 | 役割 |
|---|---|
| [配布品質と適用範囲](docs/distribution-readiness.ja.md) | 配布前チェックと適用範囲（English: [distribution-readiness.md](docs/distribution-readiness.md)） |
| [セットアップガイド](docs/setup-guide.md) | ゼロから自分の Domo へ配備・検証する単一の手順書（着手前の「AIが陥りやすい誤り」を先頭に）|
| [設計原則](docs/design-principles.md) | 優先順位・レイヤー・公開関数を1つにした理由・UI設計・採用しなかった設計 |
| [アーキテクチャと設計判断](docs/architecture.md) | 出力ハブ型2経路・レイヤー境界・単一ディスパッチャCE・保存順・AI HTML 許可リスト |
| [データモデル](docs/data-model.md) | 出力DataSet列・勘定科目レベル・状態ラベル5値・AppDBレポート文書 |
| [Domoアセット台帳](docs/domo-assets.md) | 名称・alias・個数の ID 非依存な契約（配備後の個数照合） |
| [AGENT.md](AGENT.md) | 変更を加える AI が守る不変契約 |
| [prompts/](prompts/) | AI への入口プロンプトと共通規約の正本 |

店舗・全社レポートは親Workflowから生成します。画面の更新ボタンは確認後に**全店舗＋全社**を
開始し、店舗セレクターは閲覧対象だけを切り替えます。定期実行スケジュールは作成しません。
子Workflowの待機タイマーは同時実行負荷の平準化に使います。

保存は新規レポートを作成してから、同じ `doc_key` の厳密に古いサーバー時刻の文書だけを削除します。
AIが作るHTMLは信用せず、画面側の許可リストを通して描画します。
トレンドは勘定レベル1、事業部別原価はレベル2を使い、二重計上を避けます。
会計の詳細はETLのSQLと[共通規約](prompts/prompt_shared_conventions.md)を確認してください。

## 検証と保守

このアプリフォルダで、ネットワークを使わない検証を実行できます。

```bash
python3 -m unittest discover -s tests
node --test tests/test_*.js
node dev-guide-app/tests/check.mjs
```

配備先ではデータ層とワークフロー層の `verify` を実行します。正しい対象インスタンス・版・
接続・レポートの存在を確認してから顧客へ引き渡します。過去の版番号や実行ログは現在の検証結果ではありません。

`scripts/deploy_wf_prompt.py`・`repin_wf01.py`・`deploy_code_engine.py` と
`code-engine/appdb_maintenance.py` は既存運用互換のため残しています。通常は現行の
`provision_domo.py` と `provision_workflows.py provision` を使います。
キャンバスだけの整理は `polish_dataflow.py` でロジックの一致を確認し、DataFlowは再実行しません。
