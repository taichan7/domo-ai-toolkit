# アーキテクチャ

## 目的と前提

本アプリは本番運用用ではなく、Domoの各機能の責務と接続方法を理解するためのリファレンスである。そのため、独立した業務テーブルを多数作る代わりに、1つのAppDBコレクションを `record_type` で論理分割する。

## 構成

```text
「即時反映される運用経路」
Domo Mobile / PC
  → Pro Code（表示・入力・カメラ／QR解析・入力時チェック）
  → Code Engine inventory_api（最終検証・業務処理）
  → AppDB inventory_management_records（Operational Store）

「同期後に反映される分析経路」
AppDB
  → Domo標準AppDB DataSet同期
  → 標準同期DataSet（1件）
  → Magic ETL / DataFlow（1入力）
  → ダッシュボードDataSet（1出力）
  → Pro Code分析画面 / App Studioカード
```

実行時の認証、保存、業務ロジック、分析はすべてDomo内で完結し、外部データベース、外部バックエンド、外部QR解析API、外部AI・メールAPIに依存しない。ブラウザ互換用の静的QRライブラリはversionとSRIを固定し、画像を外部送信せず端末内だけで実行する。

## 各コンポーネントの責務

| コンポーネント | 責務 | 持たない責務 |
|---|---|---|
| Pro Code | 日本語UI、カメラ／写真／QR解析、QR形式判定、候補選択、入力時チェック、状態管理、結果表示 | 最終的な権限・マスター・在庫判定、AppDB更新 |
| Code Engine | Domoユーザー確認、マスタ・数量・権限の最終検証、二重登録防止、取引と残高の更新、再計算 | 端末カメラ制御、QR画像解析、DataSet同期、ダッシュボード集計 |
| AppDB | 小さな即時CRUDのOperational Store、監査履歴 | 分析用の大量集計 |
| 標準同期 | AppDBから分析DataSetへのDomo管理下のデータ移送 | 業務ルール |
| DataFlow | 7タイルで分析行の型変換・集計・派生項目を生成し、品目ごとのAI在庫コメントを付与する | 取引登録、AppDB更新 |
| App Studio | Pro Codeカードの配置とモバイル公開容器 | 業務データの保存 |

Code Engineは公開関数 `inventory_api` の1件だけとし、`operation` で操作を切り替える。私有関数は真偽判定 `_is_true`、宛先メール解決 `_resolve_recipient_email`、AppDBアクセス `_records`、取引登録 `_register`、手動通知 `_notify_now`、管理操作 `_admin`（残高再計算・デモ初期データ投入・マスタCRUDを1つの管理者専用入口に集約）の6件に集約する。

## Pro CodeとCode Engineの境界

判断基準は「端末固有・即時に再実行できる処理」か「改ざんされてもサーバー側で守る必要がある処理」かである。

| 処理 | 実装先 | 理由 |
|---|---|---|
| カメラ権限、背面カメラ、写真選択 | Pro Code | WebView／OS固有であり、サーバーから制御しない |
| QR画像のデコード、`LOC:`／`ITEM:`の形式判定 | Pro Code | 画像を外へ送らず、選択操作のための不要な通信を発生させない |
| 一覧候補との照合、数量プレビュー | Pro Code | 操作支援であり、失敗しても正データを変更しない |
| 実行ユーザー、管理者権限、有効マスター | Code Engine | ブラウザ入力を信頼せず、登録時点の正を確認する |
| 数量上限、マイナス在庫、`request_id`重複 | Code Engine | 同時実行や改ざんを含めて保存前に強制する |
| `TRANSACTION`追記、`BALANCE`／`ALERT_STATE`更新 | Code Engine | AppDB更新を一つの業務入口に集約する |

Pro Codeで同じ形式・数量を先行チェックしても、Code Engineの最終チェックは省略しない。反対に、QR文字列の正規表現判定だけをCode Engineへ送ることもしない。

## 依存方向

```text
UI (app.js)
  → Domo access adapter (domo-access.js)
  → Code Engine dispatcher / AppDB / DataSet alias
  → Domo managed services
```

UIはDomo APIパスや物理IDを知らない。ManifestのAppDB、DataSet、Code Engineエイリアスを通じて差し替える。Workflowも `lowStockNotification` → model の物理ID（`modelId`・実値は `manifest.json` が正）をManifestへ明示し、**起動はCode Engineがサーバー側で行う**（モデルの有効な最新版を実行時に解決し、フロントはWorkflow APIを直接呼ばない。Workflowを改版してもカードの再配線・再埋め込みは不要）。通知Workflowの**版**はインスタンス依存で固定しない（仕組みと `verify` 条件の全体は [test-results.md](test-results.md) の「Workflow版解決」が正、本書の要点は下の「バージョン配線」）。

## バージョン配線

| 層 | 現在の固定／追従規則 |
|---|---|
| Pro Code Manifest | 現行版は `manifest.json` の `version`。App Studioカードが最新公開版を追従し、`verify` が3者一致を確認する |
| Code Engine mapping | alias `inventoryApi` / physical function `inventory_api` / released version固定（解決済みの物理packageIDと版は配備後 `manifest.json`／ローカル生成 `domo-assets.json` にある。名称・aliasの契約は [domo-assets.md](domo-assets.md)＝実IDは持たない） |
| Workflow mapping | alias `lowStockNotification` / 物理 model ID（`modelId`）を固定（解決済みの `modelId` は `manifest.json`。名称・aliasの契約は [domo-assets.md](domo-assets.md)＝実IDは持たない）。同じ modelId を `apply` がCode Engineソースへ焼き込み、CEが起動時に最新の有効版を解決する。**released version は固定しない**＝インスタンス依存で動くため `verify` の `ok` 条件に含めず、宣言版と live 版の乖離は `workflowWarnings` に可視化するだけ |
| App Studio card | `designVersion: null` による最新公開版追従（実効版はManifest最新公開版に一致、`verify`で確認）。1×1／既定`fullpage:false`、compact 12×29、`fitToFrame:false`、カード操作は既定（`interaction`未設定＝操作許可、`editInAppViewer:true`）。card／outer proxy／inner context／design の実IDは `domo-assets.json`（ローカル生成・配布しない）が正（インスタンスごとに採番。名称・構造の契約は [domo-assets.md](domo-assets.md)＝実IDは持たない） |

Code Engineはreleased versionを文字列で固定し、`latest`へ暗黙追従させない。通知Workflowは物理 model ID（`modelId`）だけを固定し、版はインスタンス依存で動くため固定しない（`verify` の `ok` は `modelId` 一致と `codeEngineWorkflowModelEmbedded`＝CEソースへの起動先焼き込みで判定）。App Studioカードだけは同一designの修正版を自動反映する既存contextを維持し、`provision_domo.py verify` が公開latest・Manifest・カード実効版の3者一致を検証する。Workflow版がインスタンス依存である理由・`workflowWarnings` の扱い・改版時にカード再埋め込みが不要な仕組みの**全体は [test-results.md](test-results.md) の「Workflow版解決」が正**（本書は設計上の要点のみ）。

## AppDBとDataSetの使い分け

AppDBは1件単位の追加・更新、登録直後の参照、リクエストIDの検索、通知状態の更新といったOLTP的な処理に使う。DataSetは集計・派生モデル・可視化といったOLAP的な処理に使う。

DataSetだけで業務状態を持つと、小さな更新、特定レコードの上書き、登録直後の状態参照の責務が分析基盤に混在する。一方、AppDBだけでダッシュボードを組むと、毎回のブラウザ集計と分析用モデルの不足を招く。両者をDomo標準同期で接続することで、独自同期を保守しない。

## Source of Truthと更新順序

1. Code Engineが `request_id` の既存取引を確認する。
2. マスタ、権限、数量、マイナス在庫を検証する。
3. `TRANSACTION` を追記する。これが正データである。
4. `BALANCE` と `ALERT_STATE` を投影として更新する。
5. 閾値遷移があれば `ALERT_HISTORY` を追記する。
6. 閾値遷移があればCode Engineが通知Workflowの最新の有効版を解決して起動し、結果（`STARTED`／`FAILED`）を同じ `ALERT_HISTORY` 行へ確定する。
7. 不整合時は `TRANSACTION.signed_quantity` の合計から `BALANCE` を再構築する。

AppDBは一般的なRDBMSと同じトランザクション境界を仮定しない。正データと再構築可能な投影を分け、再計算を回復手段とする。

## 単一コレクションの意図と限界

単一コレクションにより、AppDBと1対1で生成される標準同期DataSetも1件になる。DataFlow入力も1件で、ハンズオンで連携の全体像を追いやすい。

代償としてスキーマは幅広く、各 `record_type` で使わない列が空になる。本番運用では、権限、保持期間、更新頻度、データ量、並行更新の要件に応じて、マスタ、取引、投影、通知を別コレクションへ分割する。本実装の狙いはその最終形ではなく、Domo内の責務境界を最小資産数で示すことにある。

## 標準同期と反映遅延

AppDB更新と標準同期DataSetへの反映は同時ではない。運用画面はAppDBを読み、登録直後の残高を表示する。分析画面はDataFlow出力を読むため、標準同期とDataFlow実行の時間差がある。DataSetがまだ更新されていない場合、Pro CodeはAppDBから同じ最小集計を作る表示フォールバックを持つ。これはDataSetへの書込みではない。

## WorkflowとAI Agentの状態

Code Engineが在庫不足・回復を決定論的に判定し、通知対象なら `ALERT_HISTORY` を作成する。Code Engineは同じ操作の中で、通知Workflowモデルの**有効な最新版を実行時に解決**して起動し、開始成功を`STARTED`、開始失敗を`FAILED`として同じ履歴へ記録する（フロントはWorkflowを直接起動しない）。メール送信の成否を`STARTED`と混同しない。

```text
Start（決定済みの閾値遷移）
  → AI Agent（Dashboard DataSetを知識として参照し、件名・本文を作成してSend Email toolを1回実行）
  → End
```

独立したWorkflow Emailタイルに加え、並列分岐、タイマー、固定文経路、Code Engine呼出し、通知記録タイルを削除した。AI Agentは既存の `Inventory Management | Dashboard` 1件だけを知識として参照する。Workflow入力を今回イベントの正とし、同期遅延があるDataSetは補足に限定することで、AI Agentに在庫計算、登録可否、閾値判定、発注判定を任せない。

## DataFlowの読み方

分析DataFlow（`Inventory Management | Analytics`）は次の7タイルを持つ。集計とAIコメント生成を1本のフローにまとめ、最後に縦結合して1つのDashboard DataSetへ出力する。

```text
在庫管理レコード（LoadFromVault）
  ├→ ダッシュボード行を一括生成（Python）───────────────┐
  └→ 品目ごとのAI入力テキストを生成（Python）            │
        → 品目ごとにAIが在庫コメント（TextGeneration/DomoGPT）
        → 公開する列を選択（SelectValues）              │
                                                        ↓
          ダッシュボード行とAIコメントを結合（UnionAll）
            → Dashboard DataSetへ出力（REPLACE）
```

キャンバスには「① 準備」「② AI要約」「③ 出力」の3セクションを置き、7タイルすべてに役割・入出力・副作用の有無を説明するnotesを付ける。説明メタデータは計算へ影響しない。

AI在庫コメントは「在庫全体を1行に要約」せず、残高（品目×ロケーション）1件につき1コメントを生成する **per-entity** 方式を採る。このインスタンスのAIテキスト生成タイルはバッチ実行のみで、入力が100行未満だと失敗する（`DP-TGTFR`）ためである。デモは残高が100件以上になるようシードしてあり、1品目に1つの助言（不足なら補充、適正なら現状維持、滞留なら見直し、基準未設定なら基準設定）を付けられる。集計行とAIコメント行はUnionAllで列を揃えて1つのDataSetに同居する（`ai_summary` はAIコメント行だけが値を持つ）。
