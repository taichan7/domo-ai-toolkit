# ハンズオン：コーディングエージェントに渡す入口プロンプト

> このファイルを、VS Code のコーディングエージェント（Claude Code / Codex / GitHub Copilot 等）に
> **そのまま渡す**。エージェントは上から順に実行し、環境準備 → 検証用コピー作成 → 「編集 → 公開 →
> 確認」の 1 周を案内する。全体像と図解は `dev-guide-app`（App Studio ページ2「開発ガイド」）が正。

> **最初に自分の OS をエージェントへ伝える**（例：「私の PC は Windows です。コマンドは PowerShell で
> 提示してください」）。以下の例は macOS / Git Bash と Windows PowerShell の両方を併記する。

> **エージェントへ：** まず同梱の `AGENT.md` と `README.md` を読み、以降は**上から 1 ステップずつ**案内する。
> 各ステップで「私がやること（コピペするコマンド）」と「あなたがやること」を分け、私の「できた」を待って次へ進む。
> 本番への `domo publish`・データ変更・削除は**毎回**ユーザーの確認を取る。専門用語は短く補足する。

## 0. このプロンプトでやること

**本番や他参加者に触れずに、自分専用の「サンドボックス」で「エージェントで編集 → `domo publish` →
ブラウザで反映確認」を 1 周**する。鍵は名札 `PL_SANDBOX_SUFFIX`（例「検証・氏名」）＝**バックエンドも含めた
全オブジェクト**（DataFlow・4出力データセット・保存/dedupe の Code Engine・統合サブWF・WF-01・AppDB・
App Studio DataApp/カード）が自分専用名になり、同じインスタンス上でも本番・他参加者と衝突しない。画面(FE)
だけなら軽い／DataFlow・Workflow・CE・AppDB まで自分のコピーにするのは任意（重い・AI クレジットと時間）。

## 1. 環境を確認（足りなければ導入）

```text
# macOS（Homebrew）
brew install node python git
brew install --cask google-chrome     # 開発ガイドの PNG 目視テスト用（任意）

# Windows（PowerShell・winget）
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
winget install Git.Git

# 確認
node --version      # LTS が入っていること
python3 --version   # Windows では python --version の場合が多い（3.9 以上）
git --version
domo --version      # 無ければ: npm install -g ryuu
```

**Python スクリプト（`provision_domo.py` / `provision_workflows.py`）を使う場合は、開発者トークンと
インスタンス名が必須**（`domo login` では動かない面がある）。トークンは Domo の「管理 → セキュリティ →
アクセストークン」で発行し、`config/secrets.env`（gitignore 済み・この 1 ファイルのみ）に置いて読み込む
（チャット・コミットに貼らない）:

```text
cp config/secrets.env.example config/secrets.env
# config/secrets.env に DOMO_INSTANCE= と DOMO_DEVELOPER_TOKEN= を書く
#   macOS / Git Bash
set -a; . config/secrets.env; set +a
#   Windows PowerShell（都度 env へ）
#   $env:DOMO_INSTANCE="<your-instance>.domo.com"; $env:DOMO_DEVELOPER_TOKEN="<発行したトークン>"
```

## 2. デプロイ先インスタンス（不明なら必ず聞く）

**エージェントへ：** デプロイ先の Domo ドメインが会話で示されていなければ、勝手に進めず**一度たずねる**。
接続先は主催者が指定した自分のインスタンス。`https://` やパスが付いていればドメイン部分だけを使う。

```bash
domo login -i "$DOMO_INSTANCE"   # ブラウザ SSO
```

> **再開チェック（休憩後・ターミナルを開き直したら必ず）**：先に ① `domo login`（SID は約 1 時間で失効）
> ② `set -a; . config/secrets.env; set +a`（トークン）③ `export PL_SANDBOX_SUFFIX="検証・氏名"`（名札）を
> 再設定してから続きへ。

## 3. 本番操作は確認してから

`domo publish`・データ/アプリの変更・削除は、**実行前に必ず一言ユーザーへ確認**する（何を・どこへ）。
エージェントの「**常に許可／自動承認**」は選ばない（一度外すと本番 publish・データ書込み・削除が無確認で走る）。

**撤退ライン（講師なしで進めるとき）**：打ち間違い・パス・環境変数・ログインのやり直しは**自分で直す**。
社内プロキシ／SSO／証明書エラー・インストール禁止・管理者権限が無い等は**環境・権限側**＝設定を変えても
同じエラーなら自分では直せない合図。**目安 15 分**で糸口が無ければ運営（いなければ自社の情シス／Domo 管理者）へ。

## 4. 検証用コピーを作り、名札を設定する

```text
# macOS / Git Bash
cp -R pl-summary-app ~/handson-pl
cd ~/handson-pl
export PL_SANDBOX_SUFFIX="検証・<あなたの氏名>"     # ★最重要：これ1個で全スタックが自分専用になる

# Windows PowerShell
Copy-Item -Recurse pl-summary-app $HOME\handson-pl
cd $HOME\handson-pl
$env:PL_SANDBOX_SUFFIX="検証・<あなたの氏名>"
```

- **名札（最重要）**：`PL_SANDBOX_SUFFIX` を設定すると、以降の全スクリプトで DataFlow / 4出力 / CE / 統合サブWF /
  WF-01 / AppDB / DataApp 名に `（検証・氏名）` が付き、本番・他参加者と自動で分離する。未設定だと本番名のまま＝
  `apply` / `provision --apply` は全インスタンスで**拒否**される（本番保護ガード）。
- コピーしたら **VS Code で `~/handson-pl` を開き直す**（ファイル → フォルダーを開く）。以降のターミナルと
  エージェントは必ずこのフォルダで動かす（本番フォルダのまま publish する事故を防ぐ）。
- **`pro-code/manifest.json` の `"id": "…"` 行をキーごと削除する**（`domo publish` が新しい design を採番＝本番と別物。
  空文字 `""` は不可）。アプリ本体のサンドボックスを作る学習ステップ。
- **`dev-guide-app` は実習では publish しない**（コピーするだけで触らない）。公開ソースのdev-guide側のidは未設定であり、万一 publish しても本番ガイドは上書きされないが、学習範囲外。

## 5. 1 周する（編集 → 検証 → 公開 → 確認）

```text
# (1) 見た目で分かる小さな変更をエージェントへ依頼
#     例「ヘッダーのタイトルを◯◯に変えて」「概要タブの KPI 並びを調整して」

# (2) Domo に触れずローカルで確認（砂場・失敗しても無害）
node --check pro-code/app.js
node tests/test_drill_helpers.js          # ドリルダウンの純粋モデル回帰（30件）

# (3) 公開前に3点確認: pwd が ~/handson-pl か ／ 一式そろうか ／ 本番 id が外れているか
#     id 不在チェック（0 なら安全）: mac  grep -c '"id"' pro-code/manifest.json
#                                   Win  (Select-String -Path pro-code\manifest.json -Pattern '"id"').Count
#     ユーザー承認の上で公開
cd pro-code && domo publish && cd -        # Windows は cd pro-code; domo publish; cd ..

# (4) 自分専用の DataApp にカードを埋め込む（名札で名前は自動一意化＝氏名入り DataApp ができる）
python3 scripts/provision_domo.py app-studio
#     出力 APP_STUDIO_RESULT の /app-studio/<自分の id> を控える。2回目以降は domo publish だけで反映（FOLLOW_LATEST）

# (5) /app-studio/<自分の id> をブラウザで開き、変更を自分の目で確認
# (5b) 管理者権限・トークンが無く一人で進めるなら、(4)(5) の代わりに `cd pro-code && domo dev` で
#      ローカルプレビューをブラウザ確認してよい（見た目確認用・ライブデータは出ない場合あり）
```

## 6.（任意）バックエンドも自分のサンドボックスにする

名札（§4）を設定済みなら、データ層とワークフロー層も自分専用に作れる。**AI クレジットと時間を使う**
（約 25 分・DataFlow の Python タイルがダミー P/L データを合成するので外部入力データの用意は不要）ので、
実行前に規模とコストをユーザーへ説明し確認を取る:

```bash
set -a; . config/secrets.env; set +a                 # 開発者トークン
python3 scripts/provision_domo.py apply               # seed/CE/AppDB/DataFlow（すべて名札付き）
python3 scripts/provision_domo.py sync-manifest       # 自分の実IDを manifest へ
python3 scripts/provision_workflows.py provision --apply --release   # 親子WF確保→保存/手動起動CE→WF release（名札付き）
python3 scripts/provision_workflows.py sync-manifest   # plReportApiを対象インスタンスへ配線
cd pro-code && domo publish && cd -                   # Pro-Code 公開（§5(3) と同じ・id は外してある）
python3 scripts/provision_domo.py app-studio          # 自分専用 DataApp にカード埋め込み
python3 scripts/provision_domo.py verify              # ok: true
# AI 長文レポートを出すには WF-01 を手動実行（手順は AGENT.md「ワークフロー操作」）→ 約25分で AppDB に生成
```

> 開発ガイドのタブ（App Studio ページ2）まで自分の DataApp に足すなら:
> `cd dev-guide-app && domo publish && cd -`（初回は manifest の `id` を外す）→ `python3 scripts/provision_domo.py embed-guide`。

## 7. 安全の線引き（名札＝`PL_SANDBOX_SUFFIX` で守る）

- **名札（最重要）**：サンドボックスには `PL_SANDBOX_SUFFIX="検証・<あなたの氏名>"` を必ず設定する。これで
  DataFlow / 4出力 / CE / 統合サブWF / WF-01 / AppDB / DataApp すべてが自分専用名になり、**本番や他参加者を
  上書きしない**（本番インスタンス上に複数のサンドボックスが同居しても安全）。
- `provision_domo.py apply` と `provision_workflows.py provision --apply` は、**名札付きなら自分のサンドボックスに
  実行してよい**。**名札なし（本番名のまま）では全インスタンスでスクリプトが拒否する**（本番上書き防止）。
  本番名で配備するのは本番メンテナのみ（`PL_ALLOW_PRODUCTION=1`）。保守/移行用の `ce`/`subflow`/`mainflow` は
  固定の本番モデルID対象なのでサンドボックスでは使えない（名札運用は `provision`）。
- WF-01 の手動実行・DataFlow 実行は **AI クレジットを使う**。名札はオブジェクト名を分けるだけで、**インスタンスの
  AI/クレジット消費枠は分離しない**（同じインスタンスの枠を共有する）点に注意。
- 本番 design の id を残したまま publish しない（§4 で id を外す）。`dev-guide-app` は実習では publish しない。
- 本番 design・共有資産・**他参加者の名札付き資産**には触れない（閲覧も削除もしない）。
- トークン・SID をチャット/コミットに貼らない。`git add -A` を使わず明示パスで。

## 8. 完了条件

コピー作成 → id 外し → 1 変更 → `node --check` / `node tests/test_drill_helpers.js` → `domo publish` →
自分の DataApp で反映確認、が一通りできれば 1 周完了。あとは同じループで面を広げる（詳細は `dev-guide-app`）。

終了後は**自分のサンドボックスだけ**を片付けてよい（任意）：名札「検証・<あなたの氏名>」の付いた DataApp・
design・（作っていれば）DataFlow・4 出力 DataSet・CE・Workflow・AppDB を、**名前と id を確認してから**削除。
**本番（名札なし）や他参加者（別の名札）の資産には絶対に触らない**。

**最後に必ず（必須）**：当日発行した開発者トークンを**失効**する（管理 → セキュリティ → アクセストークン →
当日分を削除）。DataApp・design の削除は任意だが、**トークン失効は必須**（有効な資格情報を残さない）。
