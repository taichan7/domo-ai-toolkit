# 在庫入出庫管理アプリを自分の Domo へデプロイする（エージェント向けプロンプト）

> このファイルは、**在庫入出庫管理アプリ（`inventory-management-app`）を自分の Domo インスタンスへ
> デプロイしたい人が、コーディングエージェント（Claude Code / Cursor / Copilot 等）へそのまま渡す**ための
> 入口プロンプトです。エージェントは以下を上から順に実行してください。
>
> このプロンプトは手順を複製しません。**認証を整えたら `docs/ai-rebuild-runbook.md` を開き、その手順を上から
> 実行する**のが基本です。ここでは「環境準備（Domo CLI の導入含む）→ インスタンスの確認 → 認証 →
> ランブック実行 → 検証」を束ね、ダミーデータ生成まで含めて一気に進められるよう案内します。

## 0. このプロンプトでできること

指定した Domo インスタンスへ、**Domo CLI の導入からダミーデータ入りで動くアプリまで**を、**全自動**で構築します。
**Domo の画面を開いてアセットを手作りする作業はありません。** AppDB・Code Engine・DataFlow・通知 Workflow モデル・
**App Studio アプリ＋カード**まで、すべて `apply`／`app-studio` が API で「発見または作成」します（かつては
Workflow モデルと App Studio アプリの手作りが人手境界でしたが、いまはどちらも自動です）。**ダミーデータも
`apply` が自動生成する**ので、事前のデータ準備は不要です。あなた（エージェント）の仕事は、認証してコマンドを
順に実行することだけ。ユーザーへ「画面で◯◯を作って ID を教えて」と求めてはいけません。

### 用意してほしいもの

- `inventory-management-app/` 一式がローカルの VS Code に展開済み。
- `taichan7/domo-ai-toolkit` のスキル一式（Domo API リファレンス等）がローカルに展開済み。
- 対象 Domo インスタンスの**管理者権限**（アプリ作成・カード埋め込み・データフロー実行が可能）。
- 実行環境（**Node.js** / **Python 3.9 以上** / **Domo CLI**）。無ければ次の手順で入れます。

### 実行環境のチェックと自動セットアップ（Domo CLI の確認とインストール）

エージェントはまず環境を確認し、足りないものは可能な範囲で用意してください。

```bash
node --version      # Node.js（未導入なら下の注記へ）
python3 --version   # 3.9 以上（未導入なら python.org / pyenv で導入）
domo --version      # Domo CLI（`ryuu` パッケージ）。バージョンが表示されれば導入済み
```

**`domo --version` が `command not found` などで失敗する（＝Domo CLI が未導入の）場合はインストールします：**

```bash
npm i -g ryuu       # Domo App Dev Studio CLI。`domo` コマンドを提供する公式 CLI
domo --version      # 再確認。バージョンが表示されればインストール成功
```

- `npm` コマンドが無い場合は、先に **Node.js（LTS）** を入れてください（npm が同梱されます）。導入方法は
  [nodejs.org](https://nodejs.org/) のインストーラ、または nvm（`nvm install --lts`）。
- グローバル導入が権限エラー（`EACCES`）になる場合は `sudo` で無理に通さず、nvm などユーザー権限で書ける
  Node 環境へ入れ直すのが安全です（`npm config get prefix` の場所に書き込めるか確認）。
- 導入後に `domo` がまだ見つからないときは、新しいターミナルを開く（PATH 再読込）か、`npm bin -g` のパスが
  `PATH` に含まれているか確認してください。
- 公式ドキュメント：Domo Apps CLI（`ryuu`）— https://developer.domo.com/portal/rmfbkwje8kmqj-domo-apps-cli
- CLI 導入後の認証は次の「2. 認証」で行います（`domo login`）。

## 1. インスタンスの指定（未指定なら必ずユーザーに確認）

このプロンプト内および会話中の `<YOUR_INSTANCE>` は、あなたの Domo インスタンスのドメイン
（例：`acme.domo.com`）に置き換えてください。以降のコマンドの `<YOUR_INSTANCE>` もすべて同じ値です。

**エージェントへ（重要）：デプロイ先インスタンスが分からない場合は、勝手に進めないでください。**
本文の `<YOUR_INSTANCE>` が例のまま置き換えられておらず、会話でも明示されていないときは、
既定値やサンプル値（`maintenance-instance.domo.com` は配布元の保守用インスタンスであって顧客の環境ではありません）で
進めず、**必ず一度たずね、返答を受け取ってから**先へ進みます：

> デプロイ先の Domo のドメインを教えてください（例：`acme.domo.com`）。

- 受け取った値を、以降のすべての `<YOUR_INSTANCE>` と `DOMO_INSTANCE` に用います。
- `https://` やパス（`/app-studio/…`）付きで渡されたら、**ドメイン部分だけ**を取り出します。
- 綴りが不確かなら復唱して確認してから進みます。

## 2. 認証（トークンの扱い）

**デプロイにトークンは不要です。** ブラウザ SSO で完結します：

```bash
domo login -i <YOUR_INSTANCE>
```

これで `domo publish` も `python3 scripts/provision_domo.py` も動きます（provisioner は環境変数が無ければ
CLI のログイン情報を使います）。**トークンをチャットやコマンドラインに貼らないでください。**

### 開発者トークンを使いたい場合のみ（任意）

デプロイ後に API 開発・自動化を行いたい場合に限り、開発者アクセストークンを使えます。使うときは次を守ってください。

1. Domo 管理画面（Admin → Authentication → Access tokens）でトークンを発行する。
2. 雛形をコピーして、**gitignore 済みの `config/secrets.env`** にだけ実値を書く：
   ```bash
   cp config/secrets.env.example config/secrets.env
   # config/secrets.env の DOMO_DEVELOPER_TOKEN= に実トークンを書く（この 1 ファイルのみ）
   ```
   リポジトリ外に置くなら `~/.config/domo-utils/<YOUR_INSTANCE>.env`（`chmod 600`）でも可。
3. 参照は環境変数からのみ：
   ```bash
   set -a; . config/secrets.env; set +a
   ```

**エージェントへの厳守事項：**
- トークンを **echo / 表示 / チャットへ貼り付け / コミット** しない。
- 書き込む前に、`config/secrets.env` が `.gitignore` に載っていることを確認してから書く。
- 書き込み後に `bash ../../scripts/check-secrets.sh`（またはリポジトリ root から `bash scripts/check-secrets.sh`）で漏れがないか確認する。
- `git add -A` / `git add -a` は使わず、**明示パスのみ** stage する。
- もしユーザーがプロンプト本文の `replace_with_your_developer_token` を実トークンに置換して渡してきた場合は、
  **最初にその値を `config/secrets.env` へ退避し、本文（チャット履歴に残る側）からは消す**こと。生トークンをリポジトリや履歴に残さない。

## 3. 本番操作は確認してから

これはあなたの本番インスタンスへの構築です。**`domo publish` やデータ・アプリを変更する操作の前には、必ず
一度確認を取ってから**実行してください（何を・どこへ変更するかを一言添える）。

> 補足：`inventory-management-app` を配布しているワークスペース（社内保守用リポジトリ）の `AGENTS.md` には
> 「無確認で `domo publish`」というルールがありますが、**それは配布元の社内運用専用**です。配布先である
> あなたのインスタンスには適用しません。ここでは確認優先で進めます。

### 配備モードを必ず設定する（本番保護ガード）

`provision_domo.py` の書込み系コマンド（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）は、対象アセット名が
本番名のままだと誤った上書きを防ぐため**実行を拒否**します。`apply` の前に、次のどちらかを同じシェルで `export`
してください（読み取り専用の `verify`／`sync-manifest`／`export-app-studio` はガード対象外）。

- **自分のインスタンスへ唯一の正規アプリを立てる（通常はこちら）** → `export INVENTORY_ALLOW_PRODUCTION=1`。
  本番と同じ分かりやすい名前で全アセットを作ります。
- **1つのインスタンスを複数人で練習に使う／本番名のコピーに触れたくない** → `export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'`。
  全オブジェクト名へ全角括弧の名札（例「（検証・田中）」）が付き、バックエンド（AppDB／Code Engine／DataFlow／
  出力DataSet／通知Workflow）も App Studioアプリ／カードも**自分専用の隔離コピー**になって他の人と衝突しません。

どちらを使うかユーザーに一言確認してから設定してください。未設定のまま `apply` を実行するとガードで停止します
（その場合はこのどちらかを設定して再実行すれば進みます）。

## 4. 実行（ランブックを上から順に）

1. `AGENTS.md`（プロジェクト内）を読み、全体像と「**手作業で UI からアセットを作る境界はゼロ**」を把握する。あわせて
   `docs/ai-rebuild-runbook.md` §0.5「AIが陥りやすい誤りと正しい対処」に**必ず目を通す**（過去に、性能が
   控えめなモデルが「App／AppDB／Workflow を画面で手作りして ID を渡して」と誤案内したり、長時間 DataFlow を
   途中でキャンセルしたり、同名の既存資産を削除しようとした——同じ轍を踏まないため）。
2. `docs/ai-rebuild-runbook.md` を開き、**STEP 0 → 6 を上から順に**実行する。各 STEP の前後で、ランブックが
   指示するローカル検証（Node/Python テスト、JSON 検証）を緑にしてから Domo へ触れる。
3. **ダミーデータも通知 Workflow モデルも自動です**：`apply`（データ・ロジック層の構築）が、AppDB／Code Engine／
   DataFlow／**通知 Workflow モデルの発見・作成・配線**／SEED（デモ用のダミー在庫データ投入）まで実行するので、
   手でデータや Workflow を用意する必要はありません。分析タイルの下限（100 行以上）も自動で満たします。つまり
   「このプロンプト → ランブック」を通せば、指定したインスタンスにダミーデータ入りで動くアプリが立ち上がります。
4. **App Studio アプリ＋カードの作成も自動です**（人手の UI 操作はありません）。`scripts/provision_domo.py app-studio` が：
   - **App Studio アプリ本体を名称で発見または新規作成**し、ページ1へ在庫アプリのカードを 1 枚 embed し、静的 layout を
     整えます（ランブック §3 STEP 5）。配布時の登録 appId が対象インスタンスに無くても（404）停止せず名称で
     発見／作成へ自動フォールバックし、解決した実 ID を `domo-assets.json` へ書き戻します。**ユーザーに「App を作って
     ID を教えて」と求めてはいけません。**
   - **通知 Workflow モデルも手作り不要**：`apply` が名称で発見または API で新規作成し、3タイル（開始→AI Agent→終了）＋
     メール送信 tool の配線まで整えます。「Workflow を手で作って ID を渡して」とユーザーに求めないこと。
   - **ページ2（開発ガイド）も自動**：`app-studio` が開発ガイドを同じアプリのページ2として追加・埋め込みまで
     行います（開発ガイドは事前に `cd dev-guide-app && domo publish` で publish しておく）。
5. 途中で失敗しても慌てなくて大丈夫です。`provision_domo.py` は名称で「発見または再利用」するべき等設計なので、
   原因を直して同じコマンドを再実行できます（重複は作りません）。**同一インスタンスへ複数名が繰り返しデプロイ**
   しても、既存の同名コレクション／モデル／アプリは**そのまま再利用**します（App Studio アプリも名称で 1 つを共有）。
   既存資産が同僚の所有でも、**削除・上書き・再作成は絶対にしない**でください。長時間 DataFlow が `RUNNING` のまま
   返っても失敗ではありません（キャンセル・再トリガーせず、数分おいて `verify` で `SUCCESS` を確認）。詳しい判断は
   runbook §0.5 と §6 を見ます。

## 5. 完了条件

次が通れば完了です：

```bash
python3 scripts/provision_domo.py verify
```

出力に `ok: true` が出ること。あわせて App Studio アプリが **2 ページ**（ページ1＝在庫入出庫管理、
ページ2＝開発ガイド）になっていることをブラウザで確認してください。
