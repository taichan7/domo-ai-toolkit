# AGENTS.md — 在庫入出庫管理リファレンスアプリ

このフォルダは、Domoの各機能（Pro Code／AppDB／Code Engine／DataFlow／Workflow／App Studio）を
最小構成でどう分担・接続するかを学ぶ、**配布可能なリファレンスアプリ**です。特定の本番運用ではなく、
受け取った側が自分のDomoインスタンスへ**データを含めてゼロから再現し、ハンズオンできる**ことを目的に
しています。UIは日本語（在庫入出庫管理）、PCとDomoモバイルアプリの両方で動作します。

## AIエージェントへ（最初に読む）

あなたがこのフォルダを受け取り、顧客インスタンスへセットアップするAIコーディングエージェントなら、
**[docs/ai-rebuild-runbook.md](docs/ai-rebuild-runbook.md) を開き、その手順を上から順に実行する**。
本書はその入口で、全体像・成功条件・全自動デプロイの原則・不変契約だけを示す。版番号やIDの実値は常に
`pro-code/manifest.json` と各コマンド出力を正とし、ドキュメント記載の値は参考（時点スナップショット）
として扱う。

> 顧客が「まず何を渡せばいいか」に迷う場合は、[prompts/deploy-with-agent.ja.md](prompts/deploy-with-agent.ja.md)
> をコーディングエージェントへそのまま渡す。これは「前提確認 → 認証 → 本 runbook 実行 → 検証」を束ねた
> やさしい入口プロンプトで、手順本体は本 runbook が正。

### 一気通貫の流れ（各ステップのゲートと縮退処理は runbook を参照）

```bash
cd inventory-management-app

# 0) ローカル事前検証（Domoへ触れる前に必ず緑にする）
node --test tests/test_*.js
for f in pro-code/*.js; do node --check "$f"; done
python3 -m unittest discover -s tests
python3 -m json.tool pro-code/manifest.json >/dev/null

# 1) 対象インスタンスを選びログイン
export DOMO_INSTANCE=<your-instance>.domo.com
domo login -i "$DOMO_INSTANCE"

# 1.5) 配備モードを選ぶ（下のどちらか一方。未設定だと apply/app-studio/workflow/cleanup-legacy は
#      本番保護ガードで停止する。読み取り専用の verify/sync-manifest/export-app-studio は対象外）
export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'  # ハンズオン: 名札付きの隔離コピー（バックエンド込み）
# export INVENTORY_ALLOW_PRODUCTION=1                    # 本番名で正規コピーを配備する本番メンテナのみ

# 2) （任意）通知Workflowモデルを特定の既存モデルに固定したいときだけ設定。通常は不要
#    ＝apply が名称で発見/作成する（下の「手作業でUIからアセットを作る境界はゼロ」参照）
# export DOMO_WORKFLOW_MODEL_ID=<model-id>

# 3) データ・ロジック層を構築（AppDB / Code Engine / SEED＝データ投入 / 同期 / DataFlow /
#    通知Workflowモデルの発見・作成・配線まで自動）
python3 scripts/provision_domo.py apply

# 4) Manifestの配線ID（alias→物理ID）を対象インスタンスへ合わせる
python3 scripts/provision_domo.py sync-manifest

# 5) Pro Codeを公開
(cd pro-code && domo publish)

# 5.5) 開発ガイド(ページ2)を公開（純静的・配線不要／既存designを再利用。初回のみidを省略）
(cd dev-guide-app && domo publish)

# 6) App Studioアプリを自動で確保しカードを埋め込み→layoutを整える（UI手作業は不要）
#    app-studio が App/ページ1/カード/context を「発見または作成」し、続けてページ2
#    （開発ガイド）も自動で確保する。解決した実IDは domo-assets.json へ書き戻す
python3 scripts/provision_domo.py app-studio
python3 scripts/provision_domo.py export-app-studio

# 7) 成功ゲート
python3 scripts/provision_domo.py verify        # ok: true になれば完了
```

## 成功の唯一の定義

`python3 scripts/provision_domo.py verify` が `ok: true` を返し、runbook §2 の件数・版一致・構造条件を
満たすこと。中間出力のID等は判断材料であって完了条件ではない。

## 手作業でUIからアセットを作る境界はゼロ（全層をCLIで自動再現）

> **弱いAI向けの注意**: 過去に、性能が控えめなモデルが「App／AppDB／Workflow を画面で手作りしてIDを渡して」と
> 誤案内したり、長時間DataFlowを途中でキャンセルしたり、同名の既存資産を削除しようとした。着手前に
> [docs/ai-rebuild-runbook.md](docs/ai-rebuild-runbook.md) §0.5「AIが陥りやすい誤りと正しい対処」を必ず読む。
> **あなたが人手でDomoのUIを開いてアセットを作る必要はない。** AppDB／Code Engine／DataFlow／通知Workflow／
> App Studioアプリ＋カードのすべてを、下記コマンドが「発見または作成」する。あなたの仕事は認証して
> コマンドを順に実行することだけ。顧客や同僚へ「画面で◯◯を作ってIDを教えて」と求めてはならない。

- **App Studioアプリ＋カードは自動（人手境界ではない）。** `app-studio` が Data App 本体を**名称で発見または
  API で新規作成**し、ランディングページに公開済みPro Codeカードを1枚 embed し、静的layout（standard 60×82／
  compact 12×29・終端PAGE_BREAK・`hideWrench:true`・`editInAppViewer:true`）を整える。配布時の
  `domo-assets.json` には参照インスタンスの appId が入っているが、新しいインスタンスでその ID への GET が
  404になっても停止せず、**自動で名称による発見／作成へフォールバック**する（重複は作らない）。解決した実IDは
  `domo-assets.json` へ**書き戻す**ので、以降の `export-app-studio`／`verify` は人手のID貼り付けなしで通る。
  **ページ2＝開発ガイドも `app-studio` が自動で追加する**（`dev-guide-app` の design を同じアプリの
  ページ2として冪等に確保。旧「開発者リファレンス」と同じdesign IDを再利用するため、`dev-guide-app` の
  publish＝同一designの新版で、ページ2は `FOLLOW_LATEST` で再埋め込みなしに更新される。新design採番や
  旧ページ2削除はしない）。
- **通知Workflowモデルも自動。** かつては Domo Workflows で **開始 → AI Agent → 終了** の3タイルモデルを
  手作りして model ID を渡す必要があったが、いまは `apply` が**名称で発見または API で新規作成**し、3タイル
  雛形＋`sendEmail` tool（実 packageVersion をライブ解決）を流し込み、AI Agentの指示文・入力・プロンプト・
  DataSet接地・メール配線まで整える。`DOMO_WORKFLOW_MODEL_ID` は任意（既存モデルに固定したいときだけ設定）。
- **同一インスタンスへ複数名・複数回デプロイしても安全。** すべてのアセットを名称で共有し、重複を作らず、
  他者が作った同名アセットも壊さない（冪等）。App Studioアプリも名称で1つを共有する（各人が別アプリを増やさない）。

Workflowを改版・releaseしても、起動はCode Engineがサーバー側で**最新の有効版を実行時に解決**して行うため、
**カードの再配線・再埋め込みは不要**（`apply` が起動先modelIdをCEソースへ焼き込み、`verify` の
`codeEngineWorkflowModelEmbedded` が配備を確認する）。通知Workflow層を変更したあとは `apply`
（または `workflow` サブコマンドで接地・release）を実行すればよい。

## 不変契約（壊さない）

- **データ移送はAppDB標準同期だけが担う。** DataSet APIへ直接行を書き込まない。
- **Code Engineの公開は `inventory_api` の1関数＋`_` 始まりの私有ヘルパー6件**に固定する。
- **取引台帳は追記専用。** 訂正は逆方向のIN/OUTを追記する（行の編集・削除で直さない）。取引種別は
  入庫(IN)／出庫(OUT)の2種のみ。
- **版の三者一致。** Pro Code Manifest版＝公開latest版＝App Studio実効版。`packagesMapping[].version`
  を変えたら `code-engine/asset.json` の `version` も同値にする（テストが厳密一致を要求する）。
- **App Studioカードに `interaction: DISABLED` を使わない**（モバイルの青枠は消せるがPCのクリックも
  殺す。実機で確認済みのアンチパターン）。
- **リファレンスの清潔さを保つ。** 再配布する場合は、特定の組織名・URL・個人名・メールを、コード／
  ドキュメント／コメント／App Studio JSON／テストへ書かない。対象の切り替えは `DOMO_INSTANCE` 等の
  環境変数と、自分のインスタンスのCLI設定だけで行う。
- **べき等。** `provision_domo.py` は全アセットを名称で「発見または作成」する。再実行しても重複を作らない。
  途中で失敗しても、原因を直して同じコマンドを再実行してよい。
- **本番保護ガード。** 書込み系コマンド（`apply`／`app-studio`／`workflow`／`cleanup-legacy`）は、対象名が
  本番名のままだと実行を拒否する。ハンズオン・検証は `INVENTORY_SANDBOX_SUFFIX='検証・<氏名>'` を付けて
  バックエンド込みの隔離コピーを作り（名札付きの一意名・コミット済み `domo-assets.json` を汚さず参加者ごとの
  状態ディレクトリへID書き戻し）、本番名で正規コピーを配備する本番メンテナだけが `INVENTORY_ALLOW_PRODUCTION=1`
  を明示する。読み取り専用の `verify`／`sync-manifest`／`export-app-studio` はガード対象外。
- git は明示パスのみをstageし、`git add -A`／`-a` を使わない。

## フォルダ

- `pro-code/` — 画面・状態管理・QR・Domoアクセス層（`manifest.json` が配線と版の正）
- `dev-guide-app/` — 開発ガイド（App Studio **ページ2**に載る純静的Pro Code文書。データ非接続。環境準備・アーキ・デプロイ・ハンズオンを解説し、バックエンド込みのサンドボックス隔離 `INVENTORY_SANDBOX_SUFFIX` も扱う）
- `code-engine/` — 検証・取引登録・残高投影・再計算（公開1＋私有6関数）
- `appdb/`・`datasets/`・`dataflow/` — 単一コレクションのスキーマ／DataSet契約／分析生成ロジック（別に `dataset/`（**単数形**）はスキーマのみのミラー＝`backup_dataset_schema.py` 生成の列名＋型のみの参照用スナップショットで、`datasets/` の契約とは別物）
- `app-studio/` — App Studio再配置用JSONスナップショット（2ページ構成）
- `workflow/`・`prompts/` — 3タイル通知WorkflowとAI Agentプロンプト。`prompts/deploy-with-agent.ja.md`
  は顧客がコーディングエージェントへ渡す**デプロイ入口プロンプト**
- `config/` — `secrets.env.example`（任意の開発者トークン雛形。実値の`secrets.env`はgitignore済・非コミット）
- `scripts/provision_domo.py` — 冪等プロビジョナ（`apply`／`sync-manifest`／`app-studio`／
  `export-app-studio`／`workflow`／`verify`／`cleanup-legacy`）
- `tests/` — Python／Nodeテストスイート（`tests/layout/` はレイアウト撮影ハーネス）
- `docs/` — 設計・セットアップ・ハンズオン・検証資料（下記）

## ドキュメントを読む順序

1. [docs/ai-rebuild-runbook.md](docs/ai-rebuild-runbook.md) — AIがゼロから再構築する決定論的手順
   （ゲート・停止条件・境界・環境変数・CLIリファレンス・失敗時の判断表）
2. [docs/setup-guide.md](docs/setup-guide.md) — 前提・別インスタンスへの再現・公開・検証（人間向け）
3. [docs/architecture.md](docs/architecture.md)・[docs/design-principles.md](docs/design-principles.md)
   — 即時更新と同期後分析の2経路データフロー、設計判断
4. [docs/data-model.md](docs/data-model.md)・[docs/domo-assets.md](docs/domo-assets.md)
   — `record_type` 別スキーマ、alias↔物理IDの対応
5. [docs/handson-guide.md](docs/handson-guide.md) — 各レイヤーを読み解く学習ステップとライブデモ手順
6. [docs/mobile-test-guide.md](docs/mobile-test-guide.md)・[docs/test-results.md](docs/test-results.md)
   — 実機確認手順と `verify` の検証観点
