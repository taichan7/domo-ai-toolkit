# アーキテクチャと設計判断（店舗別損益AIインサイト）

参照アーキテクチャでは「なぜこの形か」が成果物です。本書は、コード内に既にある根拠
（`code-engine/report_api.py` のモジュール docstring）と [AGENT.md](../AGENT.md) の不変契約を、
配布先の SE / AI が読める形に surface します。アセットの名称・alias・個数は [Domoアセット台帳](domo-assets.md)、
配備手順は [セットアップガイド](setup-guide.md) を正とします。

## 全体像 — 出力ハブ型の2経路

```
データ層（即時）         DataFlow                  分析 DataSet × 4            Pro Code（FE）
seed DataSet ──▶ DF｜店舗別損益データフロー ──▶ summary / detail / trend / dept ──▶ KPI・チャート・短文を直読
                   （合成P/L集計＋ETL短文AIサマリー）

AI 長文層（手動・約25分）
WF-01（店舗一覧ループ）──▶ 統合サブWF（report_type=store / company の2 AIエージェント）
                               │  保存CE pl_report_api（ツール呼び出し）
                               ▼
                         AppDB「店舗別損益AI要約」（analysis_html）──▶ Pro Code のサマリータブが直読
```

- **データ層**は `provision_domo.py` が構築し、DataFlow が4本の出力 DataSet（alias `summary`/`detail`/`trend`/`dept`）と ETL 短文 AI サマリーを出す。FE の KPI・チャート・短文はここを直読する。
- **AI 長文層**は `provision_workflows.py` が配備し、手動起動で全店舗＋全社の経営インサイト HTML を AppDB に書く。FE のサマリータブはここを直読する。
- 2経路は疎結合：長文層が未配備でも、概要／事業部別タブはデータ層だけで動く。

## レイヤー境界（Pro Code / Code Engine / Workflow）

| 層 | 役割 | 境界 |
|---|---|---|
| Pro Code（FE） | 表示と手動起動の**トリガーのみ** | Workflow API を直接呼ばない。更新は CE の `start` を叩く |
| Code Engine `pl_report_api` | **単一公開関数のディスパッチャ**。保存・検証・手動起動・実行状況確認 | AI エージェントが**ツール**として呼ぶ。認証トークン不要（ランタイムが注入） |
| Workflow（WF-01＋統合サブWF） | AI 長文生成 | 起動は CE がサーバー側で**最新の有効版を実行時に解決**。版はインスタンス依存で固定しない |

## 設計判断（なぜこの形か）

### 公開関数を1つにした理由（単一ディスパッチャ）
CE は公開 `pl_report_api(operation, request)` 1関数で `save`／`validate` を分岐し、実処理は非公開
ヘルパに委ねる。reference-app と同じ「**AI エージェントが CE ツールで検証・保存まで完結する**」
構成に揃えたもの。関数を増やすとツール配線・権限・契約面が増え、AGENT.md が守る「アーキテクチャを変えない」
制約に反する。適応する SE / AI が `pl_report_api` を複数関数に「分割改善」しないための根拠がこれ。

### 保存が「作成してから古い版だけ削除」する理由
`operation="save"` は**先に新規レポートを作成**し、その後**同じ `doc_key` のサーバー時刻が厳密に古い**
ドキュメントだけを削除する（重複除去を保存処理に内包）。これにより従来 WF-01 先頭にあった独立した
重複除去ノードが不要になった。順序が逆（先に削除）だと、保存失敗時にデータが消える。また掃除が失敗しても
**保存成功を「重複を生む再試行」に化けさせない**（AGENT.md 不変）。予約識別子 `store_id="ALL"` の衝突回避も
同じ `doc_key` 単一性の帰結（詳細は [prompt_shared_conventions.md](../prompts/prompt_shared_conventions.md)）。

### AI の HTML を許可リストで描く理由
AI／AppDB 由来の HTML は**信用しない**。不活性にパースし、描画は FE 側の**許可リスト**を通す。生成物を
そのまま innerHTML しないことで、プロンプト注入や将来のモデル変更が XSS 経路にならない。

## 不変契約（要約）
alias（`summary`/`detail`/`trend`/`dept`/`plReportApi`）・コレクション名・`report_type`・`doc_key`・公開
`pl_report_api` を保つ。手動生成は全店舗＋全社（店舗セレクターは閲覧スコープ）。実行者メールは runtime 限り
（永続・ログ・焼き込み禁止）。CE は最新の有効な親を解決し親 TIMER を復活させない。静かな臙脂 UI・ドリル経路・
同梱ランタイム（ライセンス注記つき）を維持。DataFlow の座標のみ変更はロジックを変えず RUN を起こさない。
全文は [AGENT.md](../AGENT.md) を正とする。
