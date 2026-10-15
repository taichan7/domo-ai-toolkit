# セットアップガイド（ゼロから自分の Domo へデプロイ）

このフォルダ（`pl-summary-app/`）は**単体で配布**され、受け取った人は自分の Domo インスタンスへ
デプロイできる。本書は、**まっさらなインスタンスに対して SE／顧客がゼロから立ち上げる**ための
順序付き手順書である。各 STEP にはゲート（成否判定）があり、緑になってから次へ進む。

> **このガイドが扱う範囲**
> - **データ層＋ Pro-Code ＋ ETL 短文 AI サマリー**は、このフォルダのスクリプトだけで**きれいに**
>   デプロイできる（STEP 1〜5）。`apply` →データの`sync-manifest`→Workflow配備・CE配線→
`domo publish`→`app-studio`→`verify`。
> - **AI 長文レポート（AppDB `analysis_html`）**は**ワークフロー層**（WF-01 メイン＋統合サブWF＋保存CE）が
>   必要で、これも `scripts/provision_workflows.py provision` が**まっさらなインスタンスへゼロから配備**できる
>   （初回はSTEP 3、詳細はSTEP 6）。CE・統合サブWF・WF-01 を**名称で発見または新規作成**し、保守用インスタンスの GUID を
>   焼き込まないよう束縛を対象環境の実 ID へ張り替える。
> - ワークフロー層が未配備でも、Pro-Code カードの**サマリータブ**が「準備中」フォールバックになるだけで、
>   概要／事業部別タブ（KPI・チャート・ETL 短文サマリー）はデータ層だけで動作する。

---

## 対象インスタンス / 別インスタンスへの再現

- このフォルダは特定インスタンスに固定されない。すべてのコマンドは環境変数 `DOMO_INSTANCE` で
  対象を切り替える。**ドキュメント中の `${DOMO_INSTANCE}` は自分のインスタンスに読み替える。**
- `maintenance-instance.domo.com` は**本リファレンスの保守・検証用インスタンス**であり、顧客の環境ではない。
  配布物のソースやスナップショットに保守用インスタンスのホスト名／ID が残っていても、スクリプトは
  資産を**名称で発見または作成**し、`sync-manifest` が物理 ID を対象インスタンスへ合わせる。
- `pro-code/manifest.json` と `scripts/*.py` に埋まっている保守用インスタンスの ID（App ID・
  DataSet ID・AppDB コレクション ID 等）は、`sync-manifest`（データ／コレクション）と
  `app-studio`（埋込カードの context mapping）が対象インスタンスの実 ID へ**自動で張り替える**。
  手で書き換える必要はない。
- このフォルダは**顧客に複数配布するリファレンスアーキテクチャのデモ**である。特定顧客の実データ・
  実名・ホスト名・メール宛先を、コード／ドキュメント／コミットへ**焼き込まない**。

---

## STEP 0 — 前提・インスタンス指定・認証

### 前提

```bash
node --version      # Node.js（未導入なら nodejs.org / nvm で LTS を入れる）
python3 --version   # 3.9 以上
domo --version      # Domo Dev Studio CLI。未導入なら次でインストール
npm i -g ryuu       # domo コマンド（Domo Apps CLI）を提供。既に入っていれば不要
```

- 対象インスタンスに **AppDB / Code Engine / DataFlow / Pro Code / App Studio** の作成・編集権限が必要。
- **Domo AI が有効**で、TextGeneration が使えるモデルが利用可能なこと。STEP 1 の DataFlow が
  店舗／全社の短文 AI サマリーを TextGeneration タイルで生成するため、Domo AI 未契約や対象モデル不在だと
  `apply` の DataFlow 実行が失敗する。既定モデルは `provision_domo.py` の `DOMO_AI_SUMMARY_MODEL_ID`
  （環境変数で差し替え可）。長文 AI レポート（STEP 6・ワークフロー層の AI エージェント）も Domo AI を使う。
- 認証トークンはリポジトリやファイルへ追記しない（下記）。

### 自分のインスタンスを指定する

```bash
export DOMO_INSTANCE=<your-instance>.domo.com   # 例: export DOMO_INSTANCE=acme.domo.com
export PL_SANDBOX_SUFFIX='検証・<あなたの氏名>'   # 初回検証は隔離コピー
# 本番名で配備する担当者のみ、名札の代わりに PL_ALLOW_PRODUCTION=1 を明示する
```

- 以降のコマンドの `${DOMO_INSTANCE}` はこの値を使う。
- デプロイ先が不明なときは**勝手に進めず、必ず確認してから**設定する（`maintenance-instance.domo.com` は
  配布元の保守用で顧客環境ではない）。

### 認証（ブラウザ SSO。トークンは不要）

```bash
domo login -i "$DOMO_INSTANCE"
```

- `domo publish` と `python3 scripts/provision_domo.py`（データ層）はこのログインだけで動く
  （provisioner は環境変数が無ければ CLI の configstore 認証を使う）。
- **トークンをチャットやコマンドラインに貼らない。**
- **非対話（CI 等）・ワークフロー層では開発者トークンを使う**（任意）。`config/secrets.env.example` を
  コピーして実トークンを書く（この 1 ファイルのみ・gitignore 済み）:

  ```bash
  cp config/secrets.env.example config/secrets.env
  # config/secrets.env の DOMO_DEVELOPER_TOKEN= に実トークンを書く
  set -a; . config/secrets.env; set +a      # DOMO_INSTANCE / DOMO_DEVELOPER_TOKEN を環境へ読み込む
  ```

  provisioner は `DOMO_DEVELOPER_TOKEN` があれば `X-DOMO-Developer-Token` ヘッダで直接認証し、
  SSO ログインより優先する。**ワークフロー層（STEP 6・`provision_workflows.py`）はこの開発者トークン、
  または別途セットした `SID` 環境変数が必要**で、`domo login` の configstore は読まない点に注意。

> すべてのコマンドは `pl-summary-app/` の直下で実行する（スクリプトは自身の親フォルダを
> プロジェクトルートとして解決する）。

---

## STEP 1 — データ・ロジック層の構築（`apply`）

```bash
python3 scripts/provision_domo.py apply
```

`apply` が依存順に次を**名称で発見または作成**する（冪等・再実行で重複を作らない）:

1. **seed DataSet**（`pl_summary_seed`）— Magic ETL の入力に使う最小の AppDB 標準同期 DataSet。
   ETL の Python タイルが P/L データを合成するため、入力行自体は内容を問わない。
2. **保存Code EngineはWorkflow層で配備**する。旧 `appdb_maintenance.py` は手動保守互換で残すが、
   データ層のapplyでは未使用のdedupeパッケージを新規作成しない。

3. **AppDB コレクション**（`店舗別損益AI要約`・`syncEnabled:false`）— AI 長文レポート（`analysis_html`）の
   保存先。書き込みは STEP 6 のワークフロー層が担う。Pro-Code のサマリータブが読む。
4. **DataFlow**（`DF｜店舗別損益データフロー`・Magic ETL v2）— `dataflow/2042.json` から再構築。
   出力 DataSet（`OUT｜P/L明細` / `OUT｜P/L要約` ＋ トレンド／事業部別）を生成し、2枚の TextGeneration
   タイルが**店舗／全社の短文 AI サマリー**を出力する。これが Pro-Code の KPI・チャート・短文の供給源。

- **ゲート**: 出力の `ASSET_RESULT` に seed DataSet / AppDB コレクション / DataFlow の
  各 ID が並ぶこと。DataFlow 実行が長引く場合でも、サーバ側で継続するので**キャンセル・再トリガーしない**。
- 配線だけ更新して DataFlow 実行を省きたいときは `--skip-dataflow-run` を付ける。
- DataSet API へ直接書き込まない。AppDB のデータ移送は Domo 標準同期だけが担当する。

---

## STEP 2 — Manifest の配線を対象インスタンスへ合わせる（`sync-manifest`）

```bash
python3 scripts/provision_domo.py sync-manifest
```

`pro-code/manifest.json` の alias→物理 ID（`datasetsMapping[].dataSetId`／`collectionsMapping[].id`）を、
STEP 1 で確定した対象インスタンスの ID へ書き込む。名称で発見した ID を ID 欄へ入れるだけの冪等処理で、
既に一致していれば差分は出ない。

- **ゲート**: `git diff pro-code/manifest.json`（または目視）で、`summary`／`detail`（＋ `trend`／`dept`）の
  `dataSetId` とコレクション `id` が対象インスタンスの値へ更新されている（または既に一致）こと。

> **保守用インスタンスの ID が気になる場合**: 配布時の `manifest.json` には保守用インスタンスの
> DataSet / コレクション ID が入っているが、このコマンドが対象インスタンスの実 ID へ張り替えるので、
> 手編集は不要。

---

## STEP 3 — Workflow・CEの配線とPro Codeの公開

```bash
python3 scripts/provision_workflows.py provision --apply --release
python3 scripts/provision_workflows.py sync-manifest
cd pro-code && domo publish && cd ..
```

手動実行ボタンが参照する`plReportApi`を、**先に対象インスタンスへ配備・配線**する。
Workflow層の認証とメール宛先はSTEP 6を読む。`provision`は親/子のモデルを先に確保してから
CEソースへ両IDを焼き込み、保存・手動起動・実行状況の1公開関数をreleaseする。
親のTIMERは作成せず、既存の定期TIMERがあれば対象モデルだけ削除する。
これにより配布元のCE GUIDを別インスタンスへ持ち込まない。

- Pro-Code は**ランタイムで外部 CDN を一切読まない**（inventory-management-app と同基準）: Domo SDK は
  `vendor/domo.js`（ryuu.js 4.6.0）をローカル同梱、チャートは手書き SVG、日本語書体は `app.css` の
  font-family で `"Noto Sans JP"`（ローカルにあれば）→ システム日本語フォント（Hiragino／游ゴシック等）へ
  フォールバックする。したがってオフライン／社内ネットワーク／CDN 障害でも壊れない（書体はシステム
  フォントに置き換わるだけ）。
- **必ず `pro-code/` 直下で実行する**。親フォルダから実行すると `findManifest` が `*/manifest.json` を拾い、
  バンドルが全ツリー構成で出版されてアプリが壊れる。
- **`domo publish` は `-i` フラグを取らず、configstore の mtime 最大のインスタンスへ出版する**。
  STEP 0 で `domo login -i "$DOMO_INSTANCE"` 済みなら対象が最新。複数インスタンスを並行使用中は、
  出版直前に対象の configstore を `touch` し、出力の `Publishing ... to <instance>` を確認する。
- **初回（新規インスタンス）**: `pro-code/manifest.json` トップレベルの `id`（＝保守用インスタンスの
  Pro Code design ID）はそのインスタンスに存在しないので、**空にするか**新規 design に合わせて publish する。
  Domo が払い出した design ID を控え、`manifest.json` の `id` に反映する。
- **更新（同一インスタンス）**: `id` はそのまま残して publish する。
- **ゲート**: publish 成功。払い出された design が対象インスタンスに存在すること。

---

## STEP 4 — App Studio への埋め込み（`app-studio`）

```bash
python3 scripts/provision_domo.py app-studio
```

`app-studio` は App Studio アプリ本体を**名称（`店舗別損益AIインサイト`）で発見または新規作成**し、
Pro-Code カードを 1 枚 embed（または既存を再利用）し、カード metadata を検証して layout を整え、
埋込カードの App Framework context mapping（`summary`／`detail`／`trend`／`dept` alias→DataSet ID と
AppDB コレクションと`plReportApi`のCode Engine配線）を `manifest.json` へ**冪等に同期**する。解決した実 ID（App／Page／Card／proxy／
context）は `domo-assets.json`（gitignore 済み・配布されない）へ**書き戻す**ので、再実行や `verify` が
そのまま通る。

- **context mapping の同期がなぜ要るか**: Pro-Code の manifest に alias を増やしても、埋込済みカードの
  context は自動追随しない（`domo publish` は "Mapping has changed" と警告するだけ）。未マッピングの
  alias は proxy で 400（`DA0004`）となり、FE はトレンド空表示・事業部タブ非表示へ graceful degrade する。
  `app-studio` がこれを PUT で揃える（回帰ガードは `tests/test_provision_domo.py`）。
- `domo-assets.json` は配布されないので、**新規インスタンスでは registry 未登録＝名称で発見／作成**になる。
- **ゲート**: `APP_STUDIO_RESULT` に App／カード／context の実 ID が出力され、エラーなく終了すること。

> **参考**: 保守用インスタンスの App Studio ページには、Pro-Code カードに加えて KPI カードや
> Domo AI 生成グラフが並ぶが、これらは Domo 画面で手作りした**任意の追加面**であり、Pro-Code カードは
> それらに依存せず完全自己完結で動く（外部フィルター非依存）。顧客インスタンスで必須ではない。

---

## STEP 5 — 検証（成功ゲート）

```bash
python3 scripts/provision_domo.py verify
```

出力 `VERIFY_RESULT` の `ok: true` を確認する。`verify` は次を照合する:

- seed DataSet / AppDB コレクション / Code Engine（公開関数数 1）/ DataFlow（入力数 1）が存在。
- `summary`・`detail` 出力 DataSet が存在し、行数 > 0。
- `manifest.json` の `summary`／`detail` DataSet ID とコレクション ID が、live の実 ID と一致。

ここまでで**データ層＋ Pro-Code ＋ ETL 短文 AI サマリー**が動く状態になる。概要／事業部別タブの
KPI・チャート・短文サマリーが表示される。AI 長文レポート（サマリータブ）は STEP 6 で生成する。

---

## STEP 6 — Workflow層の詳細・再配備・手動実行（初回配備はSTEP 3）

AI 長文レポート（AppDB `analysis_html`。Pro-Code の**サマリータブ**に出る経営インサイト HTML）は、
次の3資産からなる**ワークフロー層**が生成する:

- **保存 Code Engine**（`code-engine/report_api.py` の `pl_report_api`）— AI の結果を AppDB へ保存し、
  同一 `doc_key` の旧版だけを削除（重複除去を保存に内包）。`collection_id` は配備時に解決した保存先と照合し、未設定・別コレクションは通信前に拒否する。
- **統合サブWF（WF-02）**（`workflow/WF-02_report_ai.json`）— 開始→待機→レポート種別ゲートウェイ→
  店舗AI／全社AI→保存。両 AI が `pl_report_api(save)` で保存し、全社 AI は `Send Email` も保持。
- **メイン WF（WF-01）**（`workflow/WF-01_main_loop.json`）— reference-app 流の
  **並列サイドブランチ＋終了2つ**。開始→店舗別SQL から、本線（店舗ループ：単一店舗→整形→15秒待機→
  統合サブWF(store)→次店舗?→終了#1）と、フォークした全社ブランチ（全店舗SQL→整形→統合サブWF(company)→
  終了#2）を並走させる。座標・経路は `provision_workflows.py` の数学的レイアウトエンジンが算出し、
  PUT 前に重なり0・経路貫通0 をゲートする。

### 配備コマンド（新規インスタンスはこれ 1 本）

まっさらなインスタンスは **`provision`** が CE・統合サブWF・WF-01 を**名称で発見または新規作成**し、
束縛（AppDB コレクション・クエリ対象データセット・子WF参照）を対象環境の実 ID へ再束縛して配備する
（いずれも **発見/作成 → PUT → round-trip 検証 → release** の安全パターン。`--apply` で実行・`--release` で
リリース。既存インスタンスでは各資産を発見して再利用するので、移行にも保守にも同じコマンドで足りる）:

```bash
set -a; . config/secrets.env; set +a   # DOMO_INSTANCE ＋ DOMO_DEVELOPER_TOKEN（または SID）を読み込む

# まず dry-run（ネットワーク読み取りのみ・PUT しない）で組み立て結果を確認:
python3 scripts/provision_workflows.py provision                   # /tmp/plwf に subflow/WF-01 定義を書き出す
# 問題なければ適用（CE→統合サブWF→WF-01 を発見/作成し release まで）:
python3 scripts/provision_workflows.py provision --apply --release
python3 scripts/provision_workflows.py sync-manifest               # plReportApiの実ID・公開版を更新
(cd pro-code && domo publish)
python3 scripts/provision_domo.py app-studio                       # 実カードのCE配線を同期
python3 scripts/provision_workflows.py verify                      # scheduleCount: 0 を含む構造チェック
# 実行はアプリの「AIレポートを更新」→確認→実行。取消だけではCE/Workflowを呼ばない
```

- **前提**: STEP 1〜2（データ層・`sync-manifest`）を先に済ませること。`provision --apply` は AppDB
  コレクションと `summary` データセットが見つからなければ**明示的に失敗**する（保守用 GUID を顧客環境へ
  焼き込まないための門番）。
- **メール宛先**（全社ブランチの `Send Email`）は配布物に焼き込まず env で渡す:
  `export PL_EMAIL_PERSON_RECIPIENTS=<person ID・カンマ区切り>`。**未設定なら宛先ゼロで配備し**、`provision` が
  大きく警告する（AI は宛先を創作せずメール送信を**スキップ**＝WF は `COMPLETED` でもメールは届かない。保存・
  レポート生成は正常）。「成功したのにメールが来ない」を避けるため、メールを使うなら必ず設定する。
  - **person ID の調べ方**: Domo 管理画面 **Admin → People** で対象ユーザーを開くと URL 末尾が person ID（数値）。
    または API `GET https://${DOMO_INSTANCE}/api/content/v2/users`（開発者トークン/SID 認証）で `email` → `id` を
    引く。複数人へ送るならカンマ区切り（例 `<person-id-1>,<person-id-2>`）。宛先はメールアドレスではなく **person ID**。
  - 設定の有無は `provision` のログ（「personRecipients に N 件を束縛」／「未設定 — …送信されません」）で確認できる。
- `workflow/*.json`（WF-01／WF-02／`send_email_tool.json`）は**バージョン定義のスナップショット**。
  `provision` はモデルが未存在のとき WF-01 をこのスナップショットから seed し、束縛を張り替える。

### 保守/移行用サブコマンド（既存 maintenance-instance デモ向け）

既存の WF-01／WF-02／WF-03 がある保守用デモを統合形へ**移行**する場合や、プロンプトだけ差し替える場合は
個別サブコマンドを使う（`provision` と同じ安全パターン）:

```bash
python3 scripts/provision_workflows.py ce        --apply            # 保存CE report_api.py を配備/更新
python3 scripts/provision_workflows.py subflow   --apply --release  # 統合サブWF（両ブランチ instructions＋保存ツール配線）
python3 scripts/provision_workflows.py mainflow  --apply --release  # WF-01 を並列ブランチ構成へ再構成＋サブWF再ピン
python3 scripts/provision_workflows.py delete-wf03 --apply          # 旧 WF-03（全社単体）を削除
```

既存モデル GUID を上書きしたいときは env で差し替え可（`PL_WF01_MODEL_ID` / `PL_SUBFLOW_MODEL_ID` /
`PL_WF03_MODEL_ID` / `PL_DEDUPE_CE_PACKAGE_ID`）。重複除去ノードが無いインスタンスでは撤去は no-op。

> サブコマンド一覧: `provision`（ゼロから）/ `ce` / `subflow` / `mainflow` / `delete-wf03` /
> `sync-manifest`（CE配線）/ `manual-only`（対象親の定期TIMERだけを削除）/ `verify` / `all`。
> ワークフロー層の認証は `DOMO_DEVELOPER_TOKEN`（推奨）または `SID` 環境変数で、`domo login` の
> configstore は読まない。開発者トークンを `config/secrets.env` に置いて読み込むのが自己完結で確実。

「実行状況 ↗」はCode Engineが解決したサブモデルの相対UIパス
`/workflows/instances/<sub-model-id>/` を別タブに開く。フロントへホスト名やモデルIDを固定しない。
起動は利用者自身のDomo権限で行うため、親WorkflowのREAD/EXECUTEとCEの実行権限を確認する。
メインWorkflowの完了と非同期の個別レポート反映は同義ではない。初回の動作確認では
親の終端状態、子の実行結果、全店舗＋全社のAppDB保存まで照合する。

### DataFlowの付箋・セクションを保守する

```bash
python3 scripts/polish_dataflow.py          # 読み取り・ローカルの幾何/ロジック不変検証だけ
python3 scripts/polish_dataflow.py --apply  # 全オブジェクトGET→付箋/GUIだけ更新→PUT→再GET照合
```

15タイルすべてに`notes[].body`、5つの処理単位にSectionを持たせる。
同梱した共通エンジンとラッパで枠・ラベル余白、全エッジの前進、座標3コピーの一致を検証する。
ロジック・入出力GUID・SQL/Python・AIプロンプト・スケジュールは保持し、装飾だけの変更ではRUNしない。

---

## STEP 7 — 開発ガイド（App Studio ページ2「開発ガイド」）の公開＋埋め込み

このアプリには、**VS Code × コーディングエージェントでこのアプリを開発・運用する手引き**を解説した
**純静的な開発ガイド**（[dev-guide-app/](../dev-guide-app/)・データ接続なし・縦スクロール1枚・全10節）が
同梱される。App Studio の**ページ2「開発ガイド」**として埋め込むと、業務アプリ（ページ1）と並ぶ**タブ**で開ける。

```bash
# 1) 開発ガイド design を公開（初回は dev-guide-app/manifest.json の "id" を外して publish＝新規採番）。
#    必ず dev-guide-app/ 直下で実行する（pro-code と同じ findManifest の罠）。
cd dev-guide-app && domo publish && cd ..
#    払い出された design ID を dev-guide-app/manifest.json の "id" へ反映（2回目以降はそのまま）。

# 2) 同じ App Studio DataApp のページ2として埋め込む（ページ1＝本体カードには一切触れない）。
python3 scripts/provision_domo.py embed-guide
```

- **ゲート**: `GUIDE_RESULT` に appId／ページ2の viewId／cardId が出力され、`/app-studio/<appId>` の
  2枚目タブに開発ガイドが表示されること。冪等（再実行してもページ・カードは増えない）。
- 開発ガイドは `datasetsMapping` 空の純静的 Pro Code。context mapping の同期は不要（カード作成＋レイアウト整形のみ）。
- ローカル検証（Chrome 不要の決定的関門）: `node dev-guide-app/tests/check.mjs`。版は4箇所
  （manifest／colophon／footer／thumbnail）を揃える（詳細は [dev-guide-app/README.md](../dev-guide-app/README.md)）。
- **配布時**は `make-handson-zip.sh`（非公開メンテナツール） が dev-guide の design id を外す（受講者の誤 publish から本番ガイドを守る）。

---

## ハンズオン運用 — サンドボックスでバックエンドごと隔離する（`PL_SANDBOX_SUFFIX`）

複数人が**同じインスタンス**（例: 保守用 `maintenance-instance.domo.com`）で同時にハンズオンする場合、環境変数
`PL_SANDBOX_SUFFIX="検証・<氏名>"` を**1個**設定するだけで、**バックエンドも含めた全オブジェクト名**
（seed データストア/コレクション・AppDB コレクション `店舗別損益AI要約`・dedupe/保存の Code Engine・
DataFlow `DF｜店舗別損益データフロー`・4出力データセット・統合サブWF・WF-01・App Studio DataApp/カード）に
`（検証・氏名）` が付いて一意化され、本番や他参加者と衝突しない。state（`domo-assets.json`）も
`sandbox-<氏名>/` へ自動分離する。契約（公開関数 `pl_report_api`・データセット alias
`summary/detail/trend/dept`・`report_type`・`doc_key`）は**不変**なので FE/CE/WF の配線は壊れない。

```bash
export DOMO_INSTANCE="<your-instance>.domo.com"
export PL_SANDBOX_SUFFIX="検証・<あなたの氏名>"     # ← これ1個で全スタック（データ層＋WF層＋FE）が自分専用になる
set -a; . config/secrets.env; set +a               # 開発者トークン（CE/AppDB/WF の配備に必要）

python3 scripts/provision_domo.py apply             # seed/CE/AppDB/DataFlow（すべて名札付き）
python3 scripts/provision_domo.py sync-manifest     # 自分の実IDを manifest へ
cd pro-code && domo publish && cd ..                # Pro-Code 公開
python3 scripts/provision_domo.py app-studio        # 自分専用 DataApp にカード埋め込み
python3 scripts/provision_workflows.py provision --apply --release   # 保存CE・統合サブWF・WF-01（名札付き）
cd dev-guide-app && domo publish && cd ..           # 開発ガイド（自分で試すなら）
python3 scripts/provision_domo.py embed-guide       # 自分の DataApp のページ2へ
python3 scripts/provision_domo.py verify            # ok: true
```

**本番保護ガード**: 名札なしの書込みは**全インスタンスで拒否**します。ハンズオンでは
`PL_SANDBOX_SUFFIX` を付け、本番名で配備する担当者だけ `PL_ALLOW_PRODUCTION=1` を明示します。
`DOMO_INSTANCE` は必須で、未指定時の保守環境への自動接続はありません。保守用
`ce`/`subflow`/`mainflow` は対象のモデルを名称または明示IDで解決し、サンドボックスでは使いません。
旧WF削除は追加で `PL_WF03_MODEL_ID` が必要です。通常の配備は `provision` を使います。
保存CEは対象コレクションへ固定され、AIの引数で他コレクションへ変更できません。

> ⚠ 名札はオブジェクト名を分けるだけで、**インスタンスの AI/クレジット消費枠は分離しない**（同じ
> インスタンスの枠を共有する）。DataFlow 実行・WF-01 手動実行は AI クレジットを消費する点に注意。

---

## 失敗時の対処表

| 症状 | 原因 | 対応 |
|---|---|---|
| `provision_domo.py` が `Run domo login -i <instance>` で停止 | 対象インスタンスへ未ログイン、または `DOMO_INSTANCE` 未設定 | `export DOMO_INSTANCE=<your-instance>.domo.com` → `domo login -i "$DOMO_INSTANCE"` |
| API が 401/403 | SSO セッション失効、または権限不足 | `domo login -i "$DOMO_INSTANCE"` で入り直す。管理権限（AppDB/CE/DataFlow/App Studio）を確認 |
| `verify` の `ok` が false・`summaryRowCount`/`detailRowCount` が 0 | DataFlow 未実行、または実行継続中 | 数分おいて `apply`（または `apply --skip-dataflow-run` を外して）再実行し DataFlow 完了を待つ |
| `verify` で manifest の ID が live と不一致 | `sync-manifest` 未実行、または publish 前に実行していない | `sync-manifest` → `cd pro-code && domo publish` → `app-studio` を順に再実行 |
| `domo publish` 後にアプリが全ツリー構成で壊れる | `pro-code/` の親から publish した | 必ず `cd pro-code` してから `domo publish` |
| 初回 publish が design 不在で失敗 | `manifest.json` の `id` が保守用インスタンスの design ID のまま | `id` を空にして publish → 払い出された design ID を `id` に反映 |
| `app-studio` が「Registered App ... is missing / refusing to create a duplicate」で停止 | `domo-assets.json` に別インスタンスの App/Card ID が残っている | `domo-assets.json` の `appStudio` を対象の実 ID へ上書き、または `appStudio` を空にして発見/作成させる（新規配布では通常 `domo-assets.json` が無いので起きない） |
| サマリータブが常に「準備中」 | ワークフロー層（STEP 6）未配備で `analysis_html` が未生成 | STEP 6 を実施。概要／事業部別タブはデータ層だけで動くので、長文が不要ならそのままでも可 |
| トレンドが空表示・事業部タブが出ない | 埋込カードの context mapping が未同期（`trend`/`dept` alias が proxy で解決不可） | `python3 scripts/provision_domo.py app-studio` で context mapping を同期 |
| `provision_workflows.py` が「認証情報がありません」で停止 | ワークフロー層は configstore を読まない | `config/secrets.env` に `DOMO_DEVELOPER_TOKEN` を置いて `set -a; . config/secrets.env; set +a`、または `SID` を環境変数で設定 |
| `embed-guide` が「開発ガイド design … 未公開」で停止 | 開発ガイド design が未 publish、または manifest の `id` が未反映 | `cd dev-guide-app && domo publish` → 払い出された id を `dev-guide-app/manifest.json` に反映 → 再実行 |
| `apply`／`provision`／`embed-guide` が「`PL_SANDBOX_SUFFIX` が未設定…」で停止 | 名札なしの本番書込みを全インスタンスで拒否 | ハンズオンは `export PL_SANDBOX_SUFFIX='検証・氏名'`。本番メンテナは `PL_ALLOW_PRODUCTION=1`。配備先にかかわらず必要 |
| `ce`／`subflow`／`mainflow` がサンドボックスで拒否 | 固定の本番モデルID対象ゆえ名札で隔離できない | 名札運用は `provision`（名称で自分専用の CE/WF を発見・作成）を使う |

---

## まとめ（デプロイ範囲）

- ✅ **フォルダ単体できれいにデプロイできる**: データ層（seed/CE/AppDB/DataFlow）、Pro-Code（CDN 非依存）、
  ETL 短文 AI サマリー、App Studio 埋め込み＋ context 同期、`verify` までの一連（STEP 1〜5）。
- ✅ **ワークフロー層もゼロから配備できる**: AI 長文レポート（AppDB `analysis_html`・サマリータブ）は
  `provision_workflows.py provision` が CE・統合サブWF・WF-01 を名称で発見/新規作成し、束縛を対象環境の
  実 ID へ張り替えて release する（STEP 6）。メール宛先だけ env（`PL_EMAIL_PERSON_RECIPIENTS`）で渡す。
- ✅ **開発ガイドをタブとして追加できる**: `cd dev-guide-app && domo publish` → `provision_domo.py embed-guide` で
  App Studio の**ページ2「開発ガイド」**に埋め込む（STEP 7・ページ1＝本体カードは不変）。
- ✅ **ハンズオンはバックエンドごと隔離できる**: `PL_SANDBOX_SUFFIX='検証・氏名'` 1個で、データ層・WF層・FE の
  全オブジェクト名を参加者ごとに一意化（同一インスタンス上で本番/他参加者と非衝突）。本番保護ガード付き
  （全インスタンスで本番名への無言の書込みを拒否）。受講者への入口は
  [prompts/handson-with-agent.ja.md](../prompts/handson-with-agent.ja.md)。

AI エージェント（Claude Code 等）にこのフォルダを渡してデプロイさせる場合は、
[prompts/deploy-with-agent.ja.md](../prompts/deploy-with-agent.ja.md) を入口プロンプトとして渡す。


### 現行verifyの対象

`verify` はmanifestの `plReportApi` に接続した**現役の保存APIの指定版**・固定保存先と、
4出力（summary/detail/trend/dept）の存在/件数/alias一致を検証します。旧dedupe CEの有無は合格条件ではありません。
従来配備に専用seedコレクションがない場合、生成タイルが参照する既存DataFlowの1入力を確認し、
`seedMode=existing-flow-input` と明示します。新規配備ではAppDB標準同期の専用seedを作ります。
