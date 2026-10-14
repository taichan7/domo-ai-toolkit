# ハンズオンガイド

## 学習目標

在庫アプリの完成品を覚えるのではなく、即時更新される業務状態と同期後の分析状態をDomo内でどう分け、エイリアスでどう接続するかを理解する。

## 1. アーキテクチャを読む

1. [architecture.md](architecture.md) の2本の経路を図に書き直す。
2. 「登録直後の残高」と「分析ダッシュボード」が異なるデータ面を読む理由を説明する。
3. 単一AppDBコレクションの利点と本番向けの限界を整理する。

## 2. Pro Codeをローカルで動かす

```bash
cd inventory-management-app/pro-code
domo dev
```

`app.js` はUI、`domo-access.js` はDomo通信、`qr-scanner.js` は端末機能、`config.js` は設定を担当する。Domo外ではローカルデモモードになることを確認する。

## 3. ManifestとWiringを読む

`manifest.json` で次の4エイリアスを探す。

- `inventory_management_records`: AppDB
- `inventoryDashboard`: DataFlow出力DataSet
- `inventoryApi`: Code Engineの唯一公開関数（Manifest上のalias。物理関数名は `inventory_api`）
- `lowStockNotification`: 不足通知Workflow（`manifest.json` が modelId の正。起動はCEが最新の有効版を実行時に解決）

ブラウザコードから物理UUIDを使わないこと、Workflowの起動はフロントではなくCode Engineが行うこと（起動のたびに最新の有効版を実行時に解決するため、改版してもカードの再埋め込みは不要）を確認する。

## 4. AppDB CRUDを追う

1. `schemas.json` で `record_type` とwide schemaを確認する。
2. `inventory_service.py` の単一AppDBゲートウェイ `_records` を読む。
3. `_records` が query／find／create／upsert／delete を集約し、`TRANSACTION` は追記、`BALANCE` と `ALERT_STATE` はキー単位のupsert、`delete` はドキュメントIDを指定した物理削除であることを確認する。
4. 追加(C)・参照(R)・更新(U)・削除(D)の実演として、管理画面のマスタ管理で品目を1件登録し（create）、名称を編集して保存し（update）、状態トグルで一時停止／再開できること（可逆なupdate）を確認する。
5. 続いてその品目を「削除」する。AppDBからドキュメント自体が物理削除され、依存する基準在庫・現在庫（`RULE`／`BALANCE`／`ALERT_STATE`）も連鎖削除される一方、追記専用の取引・通知履歴は監査証跡として残ることを確認する（削除は不可逆）。
6. 「残高を再計算」を実行しても、削除済みマスタの残高は復活しないことを確認する（取引台帳は残るが、マスタの無いキーは再計算対象から除外される）。

## 5. Pro CodeとCode Engineの境界を追う

`domo-access.js` はUI用の操作名を `operation` に変換し、`/domo/codeengine/v2/packages/inventoryApi` を呼ぶ。

実験:

1. `qr-scanner.js` がカメラ／写真を端末内解析し、`LOC:LOC-01` を形式判定することを確認する。ここではCode Engineを呼ばない。
2. `AUTH`／`GET_STATE` のCode Engine実行ラッパーを `domo-access.js` が展開することを確認する。
3. `REGISTER` でINを登録し、Code Engineが有効マスター・権限・数量を再検証することを確認する。
4. 同じ `request_id` を再送し、`duplicate: true` を確認する。
5. 現在庫より多いOUTを送り、`NEGATIVE_INVENTORY` を確認する。

フロントエンドの形式・数量チェックは操作支援、Code Engineの登録時チェックは強制ルールである。同じ検証に見えても、後者をブラウザへ移さない。

## 6. AppDB標準同期を確認する

AppDBコレクションのDataSet同期を開き、標準同期DataSetを確認する。リポジトリ全体でDataSet書込み用のCode EngineやWorkflowがないことを検索する。

新規取引はAppDB画面に即時出るが、標準同期DataSetと分析DataSetへは遅れて反映される。この差を障害と誤解しない。

## 7. Magic ETL / DataFlowを読む

DataFlow（分析集計）を開き、7タイルで構成されていることを確認する。集計とAIコメント生成を1本のフローにまとめ、最後に縦結合して1つのDashboard DataSetへ出力する。

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

`record_type` で取引・残高・アラートを分け、KPI、品目別、棚別、7日推移、不足、滞留、通知行を作る。AI在庫コメントは「在庫全体を1行に要約」せず、残高（品目×ロケーション）1件につき1コメントを生成する per-entity 方式で、UnionAllで集計行と列を揃えて同居する（`ai_summary` はAIコメント行だけが値を持つ）。

キャンバスの「① 準備」「② AI要約」「③ 出力」の3セクションと、7タイルすべての説明notesを開き、処理を増やさず可読性を補っていることを確認する。

## 8. App StudioとDomoモバイルを確認する

App Studioアプリは2ページ構成（ページ1＝在庫入出庫管理／ページ2＝開発ガイド）で、業務機能はページ1の1カードに集約されている。そのページ1・1カードの構成を確認する。カードの内側で、入出庫、分析、履歴、管理（マスタCRUD）を切り替える。compact layoutは12列×29行で、Domo Mobileではヘッダーとナビを保ったままカード内の本文をスクロールし、短いiframeでも全操作へ到達できる。カード操作は既定（`interaction`未設定＝操作許可）とし、`interaction: DISABLED` はPCのクリックも殺すため使わない（2.4.23で撤回）。Domo Mobileの青い選択枠は、iframeを実ビューポート（100dvh）へ固定するCSS＋静的layout＋終端PAGE_BREAKで抑える。保存済み定義は `app-studio/app-studio.json`、実機手順は [mobile-test-guide.md](mobile-test-guide.md) を使う。

## 9. Workflow／AI Agent

通知Workflowを開き、3タイルだけであることを確認する。

```text
Start → AI Agent（DataSet参照・通知文作成・Send Email） → End
```

不足判定はCode Engine、分析DataSetによる定性補足、文章化と送信はAI Agentという境界を説明する。通知は自動（閾値遷移）でも手動（「AI在庫通知を実行」）でも、Code Engineが現時点の不足全件を確定値の入力（`headline`＝見出しの1件、`shortage_lines`＝不足の一覧）に組み立ててWorkflowへ渡すため、複数不足は1通のメールに集約される。AI Agentは入力の品目・数量をそのまま転記し、`Inventory Management | Dashboard` DataSetは傾向などの任意の定性補足にだけ使う（数値・件数は上書きしない）。AI Agentの知識には、すでにPro Codeでも使う `Inventory Management | Dashboard` 1件だけが登録されている。新しいDataSetを増やさず、同じ分析資産をUIとAIで共有できる点を確認する。同期やAppDB更新にはWorkflowを使わない。

## 10. 拡張演習

1. `TRANSFER` を新しい取引種別にする場合、出庫と入庫をどのように監査可能に記録するか設計する。
2. 本番化を想定し、単一コレクションをどの境界で分割するか提案する。
3. 同期遅延をUIで明確にする「運用更新時刻」と「分析更新時刻」の表示を設計する。
4. 3タイルを増やさず、開始失敗とメール送信失敗を監査上どのように区別するか設計する。

## 11. 実演シナリオ（ライブデモ手順）

上の学習ステップで読み解いた構成を、実際の入出庫操作として通しで実演するための手順。

### 事前準備

- App Studioの「在庫入出庫管理ハンズオン」を開く。アプリは2ページ構成で、ページ1が在庫入出庫管理、ページ2が開発ガイド（`dev-guide-app` の純静的文書。環境準備・アーキ・デプロイ・バックエンド込みのサンドボックス隔離まで解説）。
- 自分でこのアプリを配備してハンズオンする場合、共有インスタンスでは `export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'` を設定してから配備する。バックエンド（AppDB／Code Engine／DataFlow／出力DataSet／通知Workflow）とApp Studioアプリ／カードまで自分専用の隔離コピーになり、本番や他参加者と衝突しない（本番名の正規コピーを配備する場合だけ `INVENTORY_ALLOW_PRODUCTION=1`）。手順は[開発ガイド](../dev-guide-app/index.html)または[AI再構築ランブック](ai-rebuild-runbook.md)を参照。
- `LOC:LOC-01` と `ITEM:ITEM-001` を印字したQR（デモマスタのロケーション／品目コードに対応）を別画面または印刷物に用意する。
- デモ前に `python3 scripts/provision_domo.py verify` が `ok: true` になることを確認する（`verify` は読み取り専用でガード対象外）。

### 手順

1. DomoモバイルアプリまたはPCからPro Codeカードを開く。
2. 「ロケーション QRを読む」で `LOC:LOC-01` を読む。カメラが使えない場合は同じ値を手入力する。
3. 「品目 QRを読む」で `ITEM:ITEM-001` を読む。
4. 処理種別を「出庫」にし、現在庫を超えない数量を入れる。
5. 確認画面で「現在庫＋入庫数量＝登録後在庫」の内訳を見せる。
6. 登録を確定する。Pro Codeのチェックに加え、Code EngineがDomoユーザー、マスタ、数量、マイナス在庫、二重登録を再検証することを説明する。
7. `TRANSACTION` がAppDBに追記され、`BALANCE` と `ALERT_STATE` が更新される。画面はAppDBを読み直すため、現在庫と直近操作がすぐ変わる。
8. 基準在庫を跨ぐ出庫では、不足の `ALERT_HISTORY` が1件追加される。さらに出庫しても閾値状態が変わらなければ重複アラートは作られない。
9. 分析画面を開き、直後はAppDBフォールバック、標準同期とDataFlow実行後は分析DataSetから表示されることを説明する。
10. DomoのAppDB標準同期DataSetで取引行を確認する。独自同期ではない。
11. DataFlow（分析集計）を実行し、出力DataSetのKPI、品目別・棚別在庫、推移、不足、滞留、アラートを確認する。
12. 管理画面の「残高を再計算」を使い、取引履歴から投影を復元できることを示す。

### Workflow／AI Agent部分

1. 決定済み不足イベントでWorkflowを起動する。
2. AI Agentが既存のDashboard DataSetを知識として参照し、該当する不足・通知行から補足情報を得る。
3. Workflow入力を今回イベントの正として、AI Agentが件名と本文を整える。
4. AI Agent内の `Send Email` toolが指定メールアドレスへ1回送る。
5. Workflowが3タイルのまま完了することを確認する。Pro CodeはWorkflowを開始した時点を`STARTED`として記録し、これをメール送信完了とは表現しない。

実メール試験では、誤送信を避けるため事前に指定したテスト宛先だけを使用する。
