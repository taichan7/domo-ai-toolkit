# 在庫入出庫管理リファレンスアプリ

> **English summary:** A hands-on reference app showing how Domo features connect —
> Pro Code (PC + mobile UI with QR scanning) → Code Engine API → AppDB → standard
> AppDB-synced DataSet → Magic ETL with per-item AI commentary → dashboard →
> App Studio, plus a server-triggered AI notification Workflow. Deployable to your
> own Domo instance: see [prompts/deploy-with-agent.ja.md](prompts/deploy-with-agent.ja.md)
> (Japanese) — the provisioning scripts remap object IDs by name, so no manual ID
> edits are needed. The rest of this document is in Japanese.

Domoの機能をどのように分担・接続するかを学ぶ、ソフトウェアエンジニア向けのハンズオン用リファレンスです。本番向けのデータ分離や拡張性より、構成の小ささと理解しやすさを優先しています。

> **これを自分のDomoへデプロイしたい方へ**：[prompts/deploy-with-agent.ja.md](prompts/deploy-with-agent.ja.md)
> をコーディングエージェント（Claude Code / Cursor 等）へそのまま渡すと、「認証 → デプロイ → 検証」まで
> 案内します。手順の本体は [AI再構築ランブック](docs/ai-rebuild-runbook.md) が正です。

## 現在の最小構成

```text
Domo Pro Code / Domo Mobile
  → Code Engine: inventory_api（公開1＋私有6関数）
  → AppDB: inventory_management_records（1コレクション）
  → Domo標準AppDB DataSet同期（1入力DataSet）
  → Magic ETL / DataFlow（7タイル・3説明セクション、品目ごとのAI在庫コメント付き）
  → Inventory Management | Dashboard（1分析DataSet）
  → App Studio（2ページ：①在庫入出庫管理／②開発ガイド・各1カード）
```

AppDB内で `ITEM`、`LOCATION`、`RULE`、`TRANSACTION`、`BALANCE`、`ALERT_STATE`、`ALERT_HISTORY` を `record_type` で識別します。入出庫履歴がSource of Truth、残高は再計算可能な投影です。

通知Workflowは「開始 → AI Agent（DataSet参照・通知文作成・Send Email） → 終了」の3タイルに簡素化済みです。AI Agentの知識には既存の分析DataSet `Inventory Management | Dashboard` を1件だけ接続し、メール送信もtool 1件へ統合しています。Code Engineが確定した閾値遷移だけを通知対象とし、**Workflowの起動はCode Engineがサーバー側で行います**（モデルの有効な最新版を実行時に解決して `api/workflow/v1/instances/message` で開始するため、Workflowを改版・releaseしてもカードの再配線・再埋め込みは不要です）。起動結果（`STARTED`＋実行ID／`FAILED`＋理由）は既存の `ALERT_HISTORY` へ記録し、在庫登録の成否と通知開始の成否を分離します。起動は、取引登録の副作用（自動）と、在庫不足パネルの「AI在庫通知を実行」ボタン（`NOTIFY_NOW`）の両方で同じCode Engineの導線を通ります（フロントはWorkflow APIを直接呼びません）。手動起動時は現在の最も深刻な不足を対象に `MANUAL` 種別の `ALERT_HISTORY` を作成します。

## 主な機能

- PCは高密度、Domo Mobileはタッチ優先に切り替わる単一レスポンシブ日本語UI
- 棚QR・品目QRの識別、ライブカメラ、端末カメラ／写真、手入力の段階的フォールバック
- 入庫・出庫
- 管理者向けマスタ管理（品目・ロケーション・基準在庫のCRUD）。削除はAppDBからの物理削除で、依存する基準在庫・現在庫も連鎖削除する（不可逆。追記専用の取引・通知履歴は監査証跡として保持）。一時的に止めたいだけなら `active` を切り替える更新で可逆に停止できる。単一のCode Engine入口 `MANAGE_MASTER` を経由し、コード形式・重複・権限をサーバ側で最終検証
- Domoユーザーの取得、管理者権限、マイナス在庫防止、リクエストIDによる二重登録防止
- シードの内部処理および取引履歴からの残高再計算
- 在庫不足時のメール通知Workflowを、取引登録の副作用（自動）とアプリ画面の「AI在庫通知を実行」ボタン（オンデマンド）から同一の起動経路（Code Engine経由）で開始（フロントはWorkflow APIを直接呼ばない）
- 品目別／棚別在庫、入出庫KPI、7日推移、不足、滞留、通知履歴の分析
- KPI・グラフ・不足／滞留・取引／通知行のホバー情報と詳細ドリルダウン

QR画像と `LOC:`／`ITEM:` 形式はPro Code内で端末処理し、Code Engineへ解析のための通信を行いません。登録時はCode Engineがマスター、権限、数量、在庫、`request_id`を改めて最終検証します。

## フォルダ

- `pro-code/`: 画面、状態管理、QRスキャナ、Domoアクセス層
- `dev-guide-app/`: 開発ガイド（App Studio **ページ2**に載る純静的Pro Code文書。データ非接続。環境準備・アーキ・データモデル・デプロイ・ハンズオンを解説し、バックエンド込みのサンドボックス隔離 `INVENTORY_SANDBOX_SUFFIX` もここで扱う）
- `code-engine/`: 検証・取引登録・残高投影・再計算
- `appdb/`: 単一コレクションのスキーマ
- `datasets/`: 標準同期DataSetと分析DataSetの契約
- `dataset/`: マップ対象DataSetの**スキーマのみのミラー**（列名＋型のみ・24列、行データ／オーナー／列ID無し。`scripts/backup_dataset_schema.py`生成の参照用スナップショット。**複数形`datasets/`の「契約」とは別物**）
- `dataflow/`: 分析用DataSet生成ロジック
- `app-studio/`: 既存App Studioの再配置用JSONスナップショット（2ページ構成）
- `config/`: `secrets.env.example`（任意の開発者トークン雛形。実値はgitignore済の`secrets.env`へ・非コミット）
- `scripts/`: プロビジョニング、検証
- `tests/`: Python／Nodeのテストスイート（Code Engine・DataFlow変換・Pro Codeシェル・QRスキャナ・プロビジョニング。`tests/layout/`はレイアウト撮影ハーネス）
- `docs/`: 設計・セットアップ・モバイル検証・ハンズオン資料
- `workflow/`, `prompts/`: 3タイル通知Workflowの状態とAI Agentプロンプト。`prompts/deploy-with-agent.ja.md`は顧客向けデプロイ入口プロンプト

## ドキュメント

- [設計原則](docs/design-principles.md) — レイヤー構成、公開関数を1本にした理由、UI設計、採用しなかった設計
- [アーキテクチャ](docs/architecture.md) — 即時更新と同期後分析の2経路データフロー
- [データモデル](docs/data-model.md) — 単一AppDBコレクションの `record_type` 別スキーマ
- [Domoアセット台帳](docs/domo-assets.md) — 各Domo資産のIDとManifestエイリアスの対応
- [セットアップガイド](docs/setup-guide.md) — 前提、別インスタンスへの再現、公開、検証
- [ハンズオンガイド](docs/handson-guide.md) — 各レイヤーを読み解く学習ステップとライブデモ手順
- [モバイル試験ガイド](docs/mobile-test-guide.md) — iOS／Android実機での確認手順
- [検証](docs/test-results.md) — 自動テストの実行方法と `verify` が確かめる構造チェックの観点
- [AI再構築ランブック](docs/ai-rebuild-runbook.md) — Claude Code が顧客インスタンスへゼロから再構築するための決定論的手順（ゲート・停止条件・境界つき）

## ローカル確認

ビルドのない素のPro Codeバンドルです。Domoの外（`file:`、localhost、127.0.0.1）では、同梱したローカルデモデータでUIを表示します。Domo上では `ryuu.js` のDomo SDKを必須とし、SDKを読み込めない場合にローカルデータへ黙って切り替えません。

```bash
cd inventory-management-app
python3 -m unittest discover -s tests -v
python3 -m json.tool pro-code/manifest.json >/dev/null
node --check pro-code/app.js
node --check pro-code/domo-access.js
node --check pro-code/qr-scanner.js
node --test tests/test_*.js
```

## Domoへの公開

保守・検証用のリファレンスインスタンスは `maintenance-instance.domo.com` です。別インスタンスへ配布する場合は `export DOMO_INSTANCE=<your-instance>.domo.com` を設定し、`apply` の後に `sync-manifest` でManifestの配線IDを合わせます（手順は [セットアップガイド](docs/setup-guide.md) の「別インスタンスへの再現」）。通知Workflowモデルは `apply` が名称で発見または新規作成するため手作りは不要です（既存モデルに固定したいときだけ `DOMO_WORKFLOW_MODEL_ID` を設定＝任意）。App Studioアプリ＋カードも `app-studio` が名称で発見または新規作成するため、Domo UIでの手作業は不要です（配布既定のappIdが対象に無ければ404を自己修復して発見／作成し、解決した実IDを `domo-assets.json` へ書き戻します）。認証情報はDomo CLIの既存設定を使い、リポジトリに保存しません。

**本番保護ガードと配備モードの選択（書込み系コマンドの前に必ず決める）**：`provision_domo.py` の書込み系コマンド（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）は、対象アセット名が本番名のままだと誤って本番（App Studio「在庫入出庫管理ハンズオン」＋AppDB／Code Engine／DataFlow／出力DataSet／通知Workflow）を上書きしないよう**実行を拒否**します。次のいずれかを設定してから実行してください（読み取り専用の `verify`／`sync-manifest`／`export-app-studio` はガード対象外でそのまま通ります）。

- 共有インスタンスでのハンズオン・検証（自分専用の隔離コピーをバックエンド込みで作る）→ `export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'`。全オブジェクト名へ全角括弧の名札（例「（検証・田中）」）が付き、本番や他参加者と衝突しません。解決した実IDは参加者ごとの状態ディレクトリ `~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/` に書かれ、コミット済みの `domo-assets.json` は汚しません。
- 本番名のままの正規コピーを配備（本リファレンスの保守、または自分のインスタンスへ唯一の正規アプリを立てる）→ `export INVENTORY_ALLOW_PRODUCTION=1`。本番名で書込みます。

```bash
cd inventory-management-app
# 事前に対象インスタンスへログイン（詳細は docs/ai-rebuild-runbook.md）。通知Workflowモデルは apply が自動作成する
# 配備モードを選ぶ（下のどちらか一方。未設定だと apply/app-studio はガードで停止する）
export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'   # ハンズオン: 名札付きの隔離コピー（バックエンド込み）
# export INVENTORY_ALLOW_PRODUCTION=1                     # 本番名で正規コピーを配備するときだけ
python3 scripts/provision_domo.py apply
python3 scripts/provision_domo.py sync-manifest   # 配線IDをManifestへ反映（サンドボックスはFE隔離のためトップレベルidも自動除去）
(cd pro-code && domo publish)                     # サンドボックス=id省略で参加者専用designを新規採番し束縛。本番コピーは初回のみidを空か新規designに
(cd dev-guide-app && domo publish)                # 開発ガイド(ページ2)。純静的・配線不要／既存designを再利用(初回はidを省略)
python3 scripts/provision_domo.py app-studio      # App/カードを発見または作成＋layout整形＋ページ2を自動確保(UI手作業不要)
python3 scripts/provision_domo.py export-app-studio
python3 scripts/provision_domo.py verify
```

`apply` はAppDBの標準DataSet同期を使います。AppDBの内容をコードでDataSetへ書き戻す独自同期はありません。

WiringはManifestの次の4点です。Code Engineは実在するreleased versionをManifestへ固定します。通知Workflowはモデルの物理ID（`modelId`）をManifestへ固定し、**同じIDを `apply` がCode Engineのソースへ焼き込みます**（CEが実行時に有効な最新版を解決して起動するため、Workflowの版はインスタンス依存のままで固定しません。`apply` が名称で発見または新規作成し、実 DataSet／実 sendEmail 版へ接地して release します）。

| 種別 | エイリアス | 接続先 |
|---|---|---|
| AppDB | `inventory_management_records` | 統合レコードコレクション |
| DataSet | `inventoryDashboard` | DataFlow出力 |
| Code Engine | `inventoryApi` | 物理関数 `inventory_api` を持つ1公開関数パッケージ |
| Workflow | `lowStockNotification` | 通知Workflow model（`apply` が名称で発見または新規作成し、物理IDをCode Engineのソースへ焼き込む。物理IDは `manifest.json` が正・インスタンス個別。既存モデルに固定したいときだけ `DOMO_WORKFLOW_MODEL_ID`＝任意） |

シードは `apply` または管理画面から実行でき、キーと `request_id` で再実行時の重複を防ぎます。詳細は [セットアップガイド](docs/setup-guide.md) と [Domoアセット台帳](docs/domo-assets.md) を参照してください。

## 検証状態

- ManifestのPro Code／Code Engine（`inventory_api`）の各バージョン、通知Workflowモデルの**modelId 一致**と**Code Engineソースへの起動先modelIdの焼き込み**（`codeEngineWorkflowModelEmbedded`）、Domo API、AppDB標準同期、DataFlow、分析DataSet、App Studio配置を `verify` で照合し、`ok: true` を確認しています。各バージョンの実値は改修のたびに変わるため、README本文に固定値は書かず `manifest.json` と `verify` 出力を正とします。通知Workflowの**版**はインスタンス依存で動くため（新規インスタンスは seed 1.0.0 から実 DataSet／実 sendEmail 版へ接地して 1.0.1 以降へ作り直し・`sync-manifest` は版欄を書き戻さない）`ok` の条件には含めず、宣言版と live 版の乖離は `workflowWarnings` に可視化するに留めます（CEが起動時に最新の有効版を解決するため、版の一致は動作条件ではありません）。
- App Studioカードはdesignの最新公開版追従（`designVersion: null`）で、外側instance/proxyと内側contextは標準どおり分離されています。参照インスタンスの実ID（カード／design／proxy／context）は [Domoアセット台帳](docs/domo-assets.md)・[domo-assets.json](domo-assets.json)・[app-studio/app-studio.json](app-studio/app-studio.json) を正とし、インスタンスごとに採番されます（本文に固定IDを書きません）。
- App Studioは2ページ構成です。ページ1が在庫入出庫管理（このPro Code）、ページ2が開発ガイド（`dev-guide-app/` の純静的Pro Code文書）で、各ページにカードを1枚ずつ埋め込みます。ページ2のスロットは旧「開発者リファレンス」から**同じdesign ID（`dev-guide-app/manifest.json` の `id`）を再利用して開発ガイドへ中身を差し替えた**もので、`dev-guide-app` を `domo publish` すると同一designの新版が出て、ページ2は `FOLLOW_LATEST` で**再埋め込みなし・孤児カードなし**に更新されます（新しいdesignを採番したり旧ページ2を削除したりはしません）。**アプリ本体・カード・layout・ページ2のすべてを `app-studio` サブコマンドが冪等に発見または作成する**ため、Domo UIでの手作業はありません（`domo-assets.json` の登録appIdが対象インスタンスに無ければ404を自己修復して名称で発見／作成し、解決した実IDを書き戻します）。ページ2のタブ名は、新規インスタンスでは「開発ガイド」で自動作成されますが、既にプロビジョニング済みのインスタンス（`maintenance-instance`）では既存ビューを強制改名しない（統合dataappのPUTを避けるため）ので現行タブ名のまま残ります。改名したい場合はApp Studioで一度だけ手で変える任意の作業です。`verify` は `domo-assets.json` に `appStudio.page2` が登録されているときだけページ2のカード存在と最新版追従を確認し、未デプロイ環境では素通りします。ページ2は自己フィットのスクロール文書のため、layout寸法には過剰適合させません。
- 正常表示する参考designに合わせ、Manifestは1×1で`fullpage`／`allowFullPage`を省略しました。App Studioはカード1枚、静的layout（`isDynamic: false`）、standard 60×82、compact 12×29、終端PAGE_BREAK、`fitToFrame: false`です。現行版ではiframe内の`main`を唯一の縦スクロール領域（100dvhビューポート固定）とします。PC操作を最優先し、カードの`interaction`は既定（未設定＝操作許可）に戻しています。**実機検証（2026-08-08）で、`interaction: DISABLED`はモバイルの青い選択枠を消す一方でPCのクリックも殺す（`editInAppViewer: true`でもPC操作不能）ことが判明したため、v2.4.22の`DISABLED`はv2.4.23で撤回しました。**Domo Mobileでタップ時に出る青い選択枠とスクロールロックは、`interaction`ではなく、iframeを実ビューポート（100dvh）へ固定するCSS＋静的layout＋終端PAGE_BREAKで抑えます。加えて、Web側で無効化できるWebKitのタップハイライト（`-webkit-tap-highlight-color: transparent`）と長押しコールアウト（`-webkit-touch-callout: none`）をbaseで切り、カード内タップ時に青い外枠が描画されるのを抑えます（残るカード選択枠はDomo Mobileホスト側の挙動です）。PC操作確保のため`editInAppViewer: true`（＝ビューアで中身が生きたまま操作可能）を維持します（2.4.19/2.4.20のPCフリーズは`editInAppViewer: false`が原因でした）。QRはライブ映像を全端末（PC／Android／iPhone）の既定にします。ライブ映像は属性版`playsinline`だけでなくIDLプロパティ（`playsInline`／`muted`／`defaultMuted`）も`srcObject`代入前に確定させ、属性版`playsinline`を無視するWKWebViewビルドでもインライン再生を優先します。iPhoneのDomo Mobile（WKWebViewの`allowsInlineMediaPlayback`が無効）ではライブ映像がホスト側で全画面化されますが、全画面のまま読み取りを継続し、成功時は全画面を抜けてこのアプリ画面へ自動で戻ります（`webkitExitFullscreen`＋`dialog.close`）。ホストが全画面を抜けても（`webkitendfullscreen`）、ライブ映像が生きている端末（インライン再生に対応したビルド）では走査をそのまま継続し、動作中の映像の上に［ライブ映像を再開］ボタンを重ねません。インライン再生を続けられず映像が一時停止した端末（利用者が読み取り前に全画面を自分で閉じた等）でだけ、［ライブ映像を再開］ボタンを表示します。端末カメラで1枚撮影する導線（`capture="environment"`）は、ライブ映像を開始できない端末（権限拒否・非セキュアコンテキスト等）でのみ控えとして露出させ、保存画像（写真から選ぶ）と手入力はいずれの端末でも切り替えられます（端末に旧バンドルがキャッシュされていると挙動が変わるため、挙動が古いと感じたらDomoアプリを再起動して最新バンドルを取得してください）。
- スマホアプリ（Domo Mobileホスト）とPCは別ペルソナとして扱います。ハンディ端末での片手操作を想定し、Domo Mobileホスト（`data-domo-platform="mobile"`）では現場作業に不要な導線（管理メニュー）を隠してコアの入出庫だけに絞り、上部タブをタイル状の大きなボタンに、主要ボタン・数量コントロール・選択カード・文字を大きくします。PCは全機能（管理を含む）と高密度レイアウトを維持します。判定はホスト属性のみに依存させ、幅ドリブンの`@media`とは独立させています（同期は`syncRuntimeLayout()`→`applyMobilePersona()`）。品のある小綺麗なUIは共通で維持します。
- Pro CodeはPC 1440px、タブレット768px、スマホ390px／375px、横向き844pxを受入幅として実装・静的検証しています。この作業環境からDomoモバイル実機のカメラを操作できないため、iOS／Android実機試験は [モバイル試験ガイド](docs/mobile-test-guide.md) の手順で実施する手作業項目です。
- 通知Workflowは3タイル・AI Agent 1件・`Send Email` tool 1件・既存DataSet context 1件でrelease／定義検証済みです。Code Engineからの起動（有効な最新版の実行時解決）と既存アラート履歴への`STARTED`／`FAILED`記録も配線済みです。実メール送信試験は、テスト宛先を明示して実施します。
