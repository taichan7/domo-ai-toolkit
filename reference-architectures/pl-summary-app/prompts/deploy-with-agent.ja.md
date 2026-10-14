# 店舗損益AI分析アプリを自分の Domo へデプロイする（エージェント向けプロンプト）

> このファイルは、**店舗損益AI分析アプリ（`pl-summary-app`）を自分の Domo インスタンスへデプロイしたい人が、
> コーディングエージェント（Claude Code / Cursor / Copilot 等）へそのまま渡す**ための入口プロンプトです。
> エージェントは以下を上から順に実行してください。
>
> このプロンプトは手順を複製しません。**認証を整えたら `docs/setup-guide.md` を開き、その STEP 0→7 を上から
> 実行する**のが基本です。ここでは「環境準備 → インスタンスの確認 → 認証 → セットアップガイド実行 → 検証」を束ねます。

## 0. このプロンプトでできること

指定した Domo インスタンスへ、**ダミーデータ入りで動く店舗損益 AI 分析アプリ**を構築します。構成は
データ層（AppDB／Code Engine／DataFlow）＋ Pro-Code アプリ（概要／事業部別／サマリーの3タブ・自前SVGチャート）
＋ App Studio 埋め込み、そして AI 長文レポートを生成するワークフロー層です。

**正直な範囲（必ず理解すること）**:

- **データ層＋ Pro-Code ＋ ETL 短文 AI サマリー ＋ App Studio 埋め込み**は、このフォルダのスクリプトだけで
  **きれいにデプロイできます**（`docs/setup-guide.md` STEP 1〜5）。これだけで概要／事業部別タブ
  （KPI・チャート・短文サマリー）が動きます。
- **AI 長文レポート（サマリータブの経営インサイト HTML）**は**ワークフロー層**（`provision_workflows.py`）が
  必要です。新規インスタンスへは `python3 scripts/provision_workflows.py provision --apply --release` が
  保存 CE・統合サブWF・WF-01 を**名称で発見または新規作成**し、束縛（AppDB コレクション・クエリ対象データセット・
  子WF参照）を対象環境の実 ID へ張り替えて**ゼロから配備**します（`docs/setup-guide.md` STEP 6）。配備後は
  WF-01 を手動実行し、AppDB に `analysis_html` が生成されるまで待ちます（約 25 分・AI クレジットを消費）。
- **開発ガイド（App Studio ページ2「開発ガイド」）**は `cd dev-guide-app && domo publish` →
  `python3 scripts/provision_domo.py embed-guide` で**タブ**として追加できます（`docs/setup-guide.md` STEP 7・
  ページ1＝本体カードは不変）。複数人で同一インスタンスを使うハンズオンは `PL_SANDBOX_SUFFIX="検証・氏名"` で
  バックエンドごと隔離します（受講者入口＝`prompts/handson-with-agent.ja.md`）。

### 用意してほしいもの

- `pl-summary-app/` 一式がローカルの VS Code に展開済み。
- 対象 Domo インスタンスの**管理者権限**（AppDB／Code Engine／DataFlow／Pro Code／App Studio の作成・編集）。
- 実行環境（**Node.js** / **Python 3.9 以上** / **Domo CLI（`ryuu`）**）。無ければ次で導入します。

### 実行環境のチェックと自動セットアップ

```bash
node --version      # Node.js（未導入なら nodejs.org / nvm で LTS）
python3 --version   # 3.9 以上
domo --version      # Domo CLI。command not found なら次でインストール
npm i -g ryuu       # domo コマンドを提供する公式 CLI（Domo Apps CLI）
domo --version      # 再確認
```

- `npm` が無ければ先に Node.js（LTS）を入れる（npm 同梱）。
- グローバル導入が `EACCES` になる場合は `sudo` で無理に通さず、nvm などユーザー権限の Node 環境へ入れ直す。
- 公式ドキュメント: Domo Apps CLI（`ryuu`）— https://developer.domo.com/portal/rmfbkwje8kmqj-domo-apps-cli

## 1. インスタンスの指定（未指定なら必ずユーザーに確認）

このプロンプト内および会話中の `<YOUR_INSTANCE>` は、あなたの Domo インスタンスのドメイン
（例: `acme.domo.com`）に置き換えてください。

**エージェントへ（重要）: デプロイ先インスタンスが分からない場合は、勝手に進めないでください。**
`<YOUR_INSTANCE>` が例のままで会話でも明示されていないときは、既定値やサンプル値
（`maintenance-instance.domo.com` は配布元の**保守用**インスタンスであって顧客環境ではありません）で進めず、
**必ず一度たずね、返答を受け取ってから**先へ進みます:

> デプロイ先の Domo のドメインを教えてください（例: `acme.domo.com`）。

- 受け取った値を、以降のすべての `<YOUR_INSTANCE>` と `DOMO_INSTANCE` に用います。
- `https://` やパス（`/app-studio/…`）付きで渡されたら、**ドメイン部分だけ**を取り出します。
- 綴りが不確かなら復唱して確認してから進みます。

```bash
export DOMO_INSTANCE=<YOUR_INSTANCE>   # 例: export DOMO_INSTANCE=acme.domo.com
```

## 2. 認証（トークンの扱い）

**データ層・Pro-Code のデプロイにトークンは不要です。** ブラウザ SSO で完結します:

```bash
domo login -i "$DOMO_INSTANCE"
```

これで `domo publish` も `python3 scripts/provision_domo.py`（データ層）も動きます（provisioner は
環境変数が無ければ CLI のログイン情報を使います）。**トークンをチャットやコマンドラインに貼らないでください。**

### 開発者トークンを使う場合（任意／ワークフロー層では必要）

非対話自動化、またはワークフロー層（`provision_workflows.py`。configstore を読まず
`DOMO_DEVELOPER_TOKEN` または `SID` 環境変数が要る）を回すときは、開発者トークンを使います:

```bash
cp config/secrets.env.example config/secrets.env
# config/secrets.env の DOMO_DEVELOPER_TOKEN= に実トークンを書く（この 1 ファイルのみ・gitignore 済み）
set -a; . config/secrets.env; set +a
```

**エージェントへの厳守事項:**
- トークンを **echo / 表示 / チャットへ貼り付け / コミット** しない。
- 書き込む前に `config/secrets.env` が `.gitignore` に載っていることを確認する（済み）。
- `git add -A` / `git add -a` は使わず、**明示パスのみ** stage する。
- ユーザーがプロンプト本文の `replace_with_your_developer_token` を実トークンに置換して渡してきた場合は、
  **最初にその値を `config/secrets.env` へ退避し、チャット履歴に残る本文からは消す**こと。

## 3. 本番操作は確認してから

これはあなたの本番インスタンスへの構築です。**`domo publish` やデータ・アプリ・ワークフローを変更する操作の前には、
必ず一度確認を取ってから**実行してください（何を・どこへ変更するかを一言添える）。

> 補足: `pl-summary-app` を配布しているワークスペース（社内保守用リポジトリ）には「無確認で `domo publish`」という
> ルールがありますが、**それは配布元の社内運用専用**です。配布先であるあなたのインスタンスには適用しません。

## 4. 実行（セットアップガイドを上から順に）

1. `AGENT.md`（プロジェクト内）と `README.md` を読み、全体像（データフロー出力ハブ・4面の AI サマリー・
   ワークフロー2本＋保存CE）を把握する。
2. `docs/setup-guide.md` を開き、**STEP 0 → 7 を上から順に**実行する:
   - **STEP 1** `python3 scripts/provision_domo.py apply` — データ層（seed DataSet／Code Engine／AppDB／DataFlow）を
     構築。ダミーの P/L データと ETL 短文 AI サマリーを自動生成。
   - **STEP 2** `python3 scripts/provision_domo.py sync-manifest` — 対象インスタンスの DataSet／コレクション ID を
     `pro-code/manifest.json` へ張り替え。
   - **STEP 3** `cd pro-code && domo publish && cd ..` — Pro-Code 公開（`vendor/domo.js` 同梱＝CDN 非依存）。
     初回は `manifest.json` の `id` を空にして publish し、払い出された design ID を反映。必ず `pro-code/` 直下で実行。
   - **STEP 4** `python3 scripts/provision_domo.py app-studio` — App Studio アプリ＋カードを名称で発見/作成し、
     埋込カードの context mapping（`summary`/`detail`/`trend`/`dept`）を同期。
   - **STEP 5** `python3 scripts/provision_domo.py verify` — `ok: true` を確認。
3. **AI 長文レポートが必要なら STEP 6（ワークフロー層）** を実施する。新規インスタンスは
   `python3 scripts/provision_workflows.py provision --apply --release`（保存 CE・統合サブWF・WF-01 を名称で
   発見/新規作成し、束縛〔AppDB コレクション・クエリ対象データセット・子WF参照〕を実 ID へ再束縛してゼロから配備）。
   既存 maintenance-instance デモの保守/移行だけ `ce` → `subflow` → `mainflow` を使う。認証は `DOMO_DEVELOPER_TOKEN`
   （`config/secrets.env`）または `SID`。配備後に WF-01 を手動実行し AppDB に `analysis_html` が生成されるのを確認する。
4. **開発ガイドのタブを足すなら STEP 7**: `cd dev-guide-app && domo publish`（初回は manifest の `id` を外す）→
   `python3 scripts/provision_domo.py embed-guide`（App Studio ページ2「開発ガイド」・ページ1＝本体カードは不変）。
   同一インスタンスで複数人がハンズオンする場合は `export PL_SANDBOX_SUFFIX="検証・氏名"` でバックエンドごと隔離する。
5. 途中で失敗しても `provision_domo.py` は名称で「発見または再利用」する冪等設計なので、原因を直して同じ
   コマンドを再実行できます（重複は作りません）。DataFlow が実行継続中でもキャンセル・再トリガーしない。

## 5. 完了条件

```bash
python3 scripts/provision_domo.py verify   # → ok: true
```

- `ok: true` が出れば**データ層＋ Pro-Code ＋ ETL 短文 AI サマリー ＋ App Studio 埋め込み**は完了です。
  ブラウザで App Studio ページを開き、Pro-Code カードの概要／事業部別タブ（KPI・チャート・短文サマリー）を確認します。
- **サマリータブの AI 長文レポート**は STEP 6（ワークフロー層）を回し、WF-01 を手動実行して AppDB に
  `analysis_html` が生成された後に表示されます（手順は `docs/setup-guide.md` STEP 6 と `AGENT.md`）。

## 6. 配布物の取り扱い（厳守）

このフォルダは**顧客に複数配布するリファレンスアーキテクチャのデモ**です。

- 特定顧客の実データ・実名・ホスト名・メール宛先・個人 ID を、コード／ドキュメント／コメント／
  コミットメッセージ／JSON／テストへ**一切焼き込まない・漏らさない**。
- `maintenance-instance.domo.com` は配布元の保守用インスタンスです。顧客インスタンスへは `DOMO_INSTANCE` で必ず差し替え、
  ハードコードされた ID はスクリプト（`sync-manifest`／`app-studio`）に張り替えさせます。
- メール宛先など環境依存の値は環境変数（`PL_EMAIL_PERSON_RECIPIENTS` 等）で与え、ソースへ残しません。
