# INSTRUCTOR.md — 講師ノート（3 時間ハンズオン運用）

対象: Domo 開発の初学者（SE／顧客開発者）/ VS Code × コーディングエージェントで Domo を開発。
教材本体: `dev-guide-app/`（App Studio ページ2・全10節）。配布: `pl-summary-app/` を ZIP
（`handson-pl.zip`）で各自へ。題材アプリは「Store PL AI Insights」（店舗別損益 AIインサイト）。

> 表記約束: 本ノートの `<自社>` は教材 `index.html` の `your-company` と同じ（各自の Domo インスタンス名）。
> §参照の約束: 教材（dev-guide-app）の節は `dev-guide §N`、このファイル自身の節は `本ノート §N`。無印の `§N` は教材（dev-guide）を指す。小節は番号でなく**小節名**で指す（教材は小節番号を表示しないため）。
> 保守・検証インスタンス `maintenance-instance.domo.com` は**顧客環境ではない**。顧客名・顧客データは本教材に出さない。

## 0. 事前に配る文面（チャット/メール用・コピペ可）

```
【事前課題（当日までに 15〜30 分）】当日はすぐ実習に入れるよう、家で「緑」にしておいてください。
0) 配布された pl-summary-app（ZIP）を展開し、分かる場所に置く（以降すべての前提）
1) VS Code を入れて、コーディングエージェント拡張（Claude Code / Codex / GitHub Copilot のどれか）にサインイン
2) Node・Python 3.9+・Git と Domo CLI（npm i -g ryuu）を入れ、`domo login -i <自社>.domo.com` まで通す
3) 自分の名札を決める: export PL_SANDBOX_SUFFIX="検証・<氏名>"（これで全オブジェクトが自分専用名になる）
4) （WF 層＝AI 長文レポートまで触る回のみ）開発者トークンを発行し config/secrets.env に置く
   ＝ データ層＋Pro-Code publish だけの回は domo login だけでトークン不要
5) （任意）PNG 目視をやる回のみ Google Chrome を入れる（dev-guide の決定的関門 node dev-guide-app/tests/check.mjs は Chrome 不要）
※ ターミナルを開き直したら 1〜3 を再設定（domo login の SID は約 1 時間で失効）
詰まったら、その時点の画面スクショを送ってください。当日の冒頭 25 分でも点検します。
```

> 当日どのコピーボタンを押させるか: 環境点検＝dev-guide §1「起点プロンプト」(`prompt-s1-check`)、実習＝dev-guide §7 の
> `prompt-s7-deploy`（サンドボックス一括デプロイ）／`prompt-s7-loop`（編集→公開ループ）／`prompt-s7-verify`／
> `prompt-s7-cleanup`（後片付け）。参加者が自分で全部任せる入口プロンプトは `prompts/handson-with-agent.ja.md`。

## 1. 当日タイムテーブルと到達ゲート

| 時刻 | 内容 | 節 | 到達ゲート（ここまで来たら次へ） |
|---|---|---|---|
| 0:00 | ねらい・全体像 | — | ゴール（店舗別損益 AIインサイト）1 枚が伝わった |
| 0:10 | 事前準備・環境点検（各自） | §1 | **全員が §1「起点プロンプト」(`prompt-s1-check`)をエージェントに渡し、足りないものが出ない**（出す→サポート）。余れば §1末尾のミニ実習（`prompt-s1-t1`〜`t10`）を 3 本だけ |
| 0:30 | 開発モデル（外で作り中で動かす） | §2 | — |
| 0:50 | このアプリの構造（店舗別損益の分解） | §3 | — |
| 1:15 | Domo 開発サーフェス網羅 | §4 | — |
| 1:25 | 休憩 | — | **休憩前に「全端末が緑」を宣言**（赤い人が残れば 10 分延長可） |
| 1:35 | デプロイの 3 段階 | §5 | — |
| 1:55 | エージェント駆動の開発ループと規律 | §6 | — |
| 2:20 | ハンズオン実習（手を動かす） | §7 | **各自の名札付きサンドボックスへ publish され、1 変更が画面に映る**（publish 前に各自 `node --check pro-code/app.js` → `node tests/test_drill_helpers.js`〔30 件〕で砂場確認） |
| 2:50 | 安全・片付け・まとめ | §8（安全ガード）／本ノート §6（片付け）／§10（付録：セルフチェック・FAQ） | **全員が本番保護の線（本ノート §5）を復唱** → 各自 dev-guide §10「理解度セルフチェック」で自己確認 → クリーンアップの号令 → 各自の検証資産を削除（任意） |

> 早く終わった人・待ち時間は dev-guide §9「もっと深く（スキル・MCP・次の一歩）」へ誘導。
>
> ⚠ サマリータブの AI 長文は WF-01 実行で生成され、約 100 店舗 × 15 秒 ≈ **25 分**かかる（本ノート §9）。当日の
> 待ち時間を作らないため、**長文を見せる回はメンテナが前日までに WF-01 を回して populate 済み**にしておく。

## 2. 開始前に埋めるもの（環境・権限チェック）

- [ ] 受講者の Domo ユーザー: **アプリ作成／カード埋め込み権限**（本番ページ1 DataApp の編集可否は不要。新規作成できること）
- [ ] **4 出力 DataSet（summary/detail/trend/dept）と AppDB `店舗別損益AI要約` の閲覧権限**（読めないとカードが空になる）
- [ ] **（バックエンドも各自作る回のみ）AppDB / Code Engine / DataFlow / Pro Code / App Studio の作成・編集権限**（データ層 `apply` と WF 層 `provision` に必要。FE＝`domo publish` だけの回はアプリ作成／カード埋め込み権限で足りる）
- [ ] **Domo AI が有効**（TextGeneration モデルが使える）＝ `apply` の DataFlow が店舗／全社の短文 AI サマリーを生成するため。既定モデルは `DOMO_AI_SUMMARY_MODEL_ID`（既定 `domo.domo_ai.domogpt-medium-v2.2:anthropic`・env で差し替え可。対象モデル不在だと `apply` の DataFlow 実行が失敗）
- [ ] **開発者トークン**を発行できるか（WF 層＝長文 AI を触る回のみ必要。不可なら本ノート §3「トークン無し運用」へ）
- [ ] 社内プロキシの値（npm / git / Domo への到達）
- [ ] **当日端末のソフト導入可否**（会社管理 PC は winget / `npm i -g` が禁止のことがある。不可なら事前に情シス申請、または事前キッティング済みの貸与端末を手配）
- [ ] **会場ネットワークで実機 1 台の事前疎通**（前日までに `npm i -g ryuu` / unzip / `domo login` / `cd pro-code && domo publish` まで通す＝false green 対策。失敗時は許可ドメイン `github.com` / `*.domo.com` を IT へ申請）
- [ ] **後方支援比率**（受講者 6〜8 名ごとに巡回 TA 1 名。環境点検ゲート 0:10-0:30 に人員を厚く）
- [ ] 共有エージェントアカウント（有料枠が無い人のため。**同時実行/利用量に上限**。目安 1 アカウント数名まで。**一斉利用で 429／上限に達し全員同時停止のリスク**→主エージェントは各自の GitHub Copilot 無料枠を既定にし、共有 Claude/Codex は副へ。詰まったら時間差実行）
- [ ] インスタンス名の案内文（`<自社>.domo.com`）

## 3. 認証は 2 系統（トークン無し運用 ↔ 開発者トークン）

**(A) `domo login` の SSO だけで動く**（トークン不要）: `cd pro-code && domo publish`（Pro-Code）と、
`scripts/provision_domo.py` の**データ層**（`apply` / `sync-manifest` / `app-studio` / `embed-guide` /
`verify`）。

**(B) 開発者トークン（または SID）が要る**: `scripts/provision_workflows.py`（**WF 層**＝AI 長文レポート）と、
SID を要求する `scripts/deploy_dataflow_prompt.py`。WF 層は `domo login` の configstore を読まない。
`config/secrets.env` に `DOMO_DEVELOPER_TOKEN` を置き `set -a; . config/secrets.env; set +a` で読み込む。

**人数が多い回の推奨**: (A) だけで完結する「データ層＋Pro-Code＋ETL 短文 AI サマリー」までをゴールに
する（概要／事業部別タブが動く）。(B) の長文 AI（サマリータブ）はメンテナが実演するか省略すれば、
参加者はトークン発行不要で全員が緑まで行ける。長文 AI まで各自でやる回だけ、事前課題④のトークンを配る。

**トークンも管理者権限も無い人のフォールバック**: `provision_domo.py app-studio`（自分の DataApp へ埋込）まで
行けなくても、`cd pro-code && domo dev` のローカルプレビューで見た目の変更は確認できる（ライブデータは出ない
場合あり・見た目確認用）。これで (A) の「編集 → 確認」ループはトークンなしでも回せる。

## 4. 想定つまずき（名指しで先回り）

| 症状 | 原因 | 対処 |
|---|---|---|
| `PL_SANDBOX_SUFFIX が未設定のまま…本番オブジェクトを…` でガード停止 | 名札なしで maintenance-instance の本番名を触ろうとした | `export PL_SANDBOX_SUFFIX="検証・<氏名>"` を設定して再実行（本番メンテナのみ `PL_ALLOW_PRODUCTION=1`） |
| `provision_workflows.py` が「認証情報がありません」で停止 | WF 層は configstore（`domo login`）を読まない | `config/secrets.env` に `DOMO_DEVELOPER_TOKEN` → `set -a; . config/secrets.env; set +a`、または `SID` を env に設定 |
| `Run domo login -i <instance>` で停止 | 未ログイン、または `DOMO_INSTANCE` 未設定 | `export DOMO_INSTANCE=<自社>.domo.com` → `domo login -i "$DOMO_INSTANCE"` |
| `domo publish` 後にアプリが全ツリー構成で壊れる | `pro-code/` の親から publish した（cwd 事故） | 必ず `cd pro-code` してから `domo publish` |
| 初回 publish が design 不在で失敗 | `pro-code/manifest.json` の `id` が保守用の design ID のまま | `id` を空にして publish → 払い出された design ID を `id` に反映 |
| publish 成功なのに画面が変わらない | キャッシュ/追従遅延 | ハードリロード → 数十秒待ち → `version` を上げて再 publish |
| サマリータブが常に「準備中」 | WF 層（§3-(B)）未配備で `analysis_html` 未生成 | WF 層を配備するか、長文不要ならそのまま（概要/事業部別タブはデータ層だけで動く） |
| トレンド空表示・事業部タブが出ない | 埋込カードの context mapping 未同期（`trend`/`dept` alias 未解決） | `python3 scripts/provision_domo.py app-studio` で context を同期 |
| 共有エージェントアカウントが 429／利用上限 | 一斉に同一アカウントを叩きレート超過 | 各自の GitHub Copilot 無料枠へ退避、または時間差実行 |
| `domo publish` が別インスタンスへ出版された | `domo publish` は `-i` を取らず configstore の mtime 最大のインスタンスへ出す | 出版直前に `domo login -i <自社>.domo.com`（または対象 configstore を `touch`）し、出力の `Publishing ... to <instance>` を確認 |
| スクリプトが突然 401／ワークフロー API が 403 | `domo login` の SID 失効（約 1 時間）・ターミナル開き直し | `domo login -i <自社>` で入り直す。WF 層は `set -a; . config/secrets.env; set +a` を再読込（開発者トークン方式は失効が緩い） |

## 5. 絶対に守らせる線（名札で本番保護・復唱させる）

- **名札（`PL_SANDBOX_SUFFIX="検証・<氏名>"`）を全員が必ず設定**＝データ層・WF 層・FE の全オブジェクトが自分専用名になり、本番や他参加者と分離（同一インスタンス上に複数サンドボックスが同居しても安全）。
- `provision_domo.py apply` / `provision_workflows.py provision --apply` 等は、**名札なし（本番名のまま）で maintenance-instance の本番オブジェクトを触ろうとすると＝スクリプトが拒否**する（本番メンテナのみ `PL_ALLOW_PRODUCTION=1`）。顧客が**自分のインスタンス**へ配備する分にはガードは無関係。
- 本番の**開発ガイド design を上書きしない**＝`dev-guide-app` を publish しない（本番ガイドを守る）。参加者はコピー＝自分のサンドボックスでのみ扱う。
- **AI クレジット警告**: 名札は名前を分けるだけで、配備先インスタンスの **AI／クレジット枠は分離しない**。`apply` の DataFlow 実行（TextGeneration 2 枚＝店舗/全社短文）と WF-01 実行（長文 AI）はいずれもクレジットを消費する。多人数回は少数店舗シード＋クレジット枠を事前確認。
- 本番 design・共有資産・**他参加者の名札付き資産**に触れない。
- **エージェントの「常に許可／自動承認／自動実行」を選ばない**（関門が外れ、publish・書込み・削除が無確認で走る）。

## 6. 終了時のクリーンアップ号令

「名札（検証・<氏名>）の付いた自分のサンドボックス資産（App Studio DataApp・Pro-Code design・DataFlow・
4 出力 DataSet・AppDB・CE・Workflow）と、**当日発行した開発者トークン**だけを片付けてください。
名前と id を確認してから削除。**本番（名札なし）や他参加者（別の名札）の資産には触らない**」。
手順は dev-guide §7 末尾「後片付け：自分の検証コピーだけを消す」のコピー用プロンプト（`prompt-s7-cleanup`）を
各自に貼ってもらう（削除は任意・迷う人は残してよい）。**時間内に終わらなければセッション後に各自で実施してよい**
（トークン失効を忘れずに）。不要ならローカルの `~/handson-pl` も削除してよい。

## 7. 進行の小ネタ

- 講師の画面は教材の該当節を開いて投影（本番 DataApp `/app-studio/496788406/pages/623741214` のページ2「開発ガイド」）。
- 受講者が止まったら、まず dev-guide §1「起点プロンプト」(`prompt-s1-check`)を再掲→エージェントに環境を点検させる。
- **休憩後・ターミナルを開き直したら「再開チェック」を全員で**: ① `domo login -i <自社>`（SID は約 1 時間で失効）→ ② `set -a; . config/secrets.env; set +a`（WF 層を触る回だけ）→ ③ `export PL_SANDBOX_SUFFIX="検証・<氏名>"`（名札）。1 つでも抜けると `apply`／`publish` が本番ガードや別インスタンスで転ぶ。
- **撤退ライン（講師が付かないとき）**: 打ち間違い・パス・環境変数・ログインのやり直しは自分で直す。社内プロキシ／SSO／証明書エラー・インストール禁止・管理者権限なしは**環境・権限側**＝設定を変えても同じエラーなら自力解決不可の合図。**目安 15 分**で糸口が無ければ運営（いなければ自社情シス／Domo 管理者）へ。
- 各節の所要が押したら、dev-guide §4（開発サーフェス網羅）の詳解を飛ばして dev-guide §7（実習）を優先（実習が本体）。
- 詰まった人・早く終わった人には dev-guide §10「理解度セルフチェック」(1 分) を回させ、理解を自己確認させる（講師の口頭確認の代替）。ハンズオンを丸ごとエージェントに任せる入口プロンプトは `prompts/handson-with-agent.ja.md`（ゼロからのデプロイ正典に任せるなら `prompts/deploy-with-agent.ja.md`）。

## 8. 配布 ZIP の構成（本番 id の扱い・受領物の確認）

この配布物（`pl-summary-app` の ZIP＝`handson-pl.zip`）は配布元（Domo SE）が
`make-handson-zip.sh`（非公開メンテナツール） で整えて届く。`dev-guide-app/manifest.json` の `id` は
**外してある**（受講者が誤って `cd dev-guide-app && domo publish` しても本番ガイドを上書きしない）。
一方 `pro-code/manifest.json` の本番 design id（`08463c98`）は**意図的に残してある**：受講者が
dev-guide §7 で自分の手で id を外し、新しい design を採番する学習ステップのため。cwd 事故
（本番フォルダのまま publish）の防止は dev-guide §5 のコールアウトと §7 の手順説明に依存する。

受領した配布 ZIP を念のため確認するなら（いずれも期待どおりなら安全）:

```bash
unzip -l <配布>.zip | grep -E 'pytest_cache|__pycache__|DS_Store'                 # 何も出ない
unzip -p <配布>.zip pl-summary-app/dev-guide-app/manifest.json | grep -c '"id"'    # 0（dev-guide の id は除去済み）
unzip -p <配布>.zip pl-summary-app/pro-code/manifest.json | grep -c '08463c98'      # 1（pro-code の本番 design id は学習用に意図的保持）
```

> 展開後の ZIP は親リポジトリ無しで `node dev-guide-app/tests/check.mjs`（版・参照の決定的チェック）が
> 通る（vendor 同梱 SDK を含む）＝「配布 ZIP だけでセルフ完遂」を実機確認済み。ZIP の作成自体は
> 配布元メンテナが親リポジトリで行う。

## 9. AI クレジットを使う操作・誤操作の復旧

- **AI クレジットを使う操作**（押下自体を事前に周知）: (a) データ層 `apply` の DataFlow 実行＝
  TextGeneration タイル2枚（`店舗別AIサマリー生成`／`全社AIサマリー生成`）、(b) WF 層配備後の
  WF-01 実行＝店舗ループ＋全社の長文 AI。どちらも配備先インスタンスのクレジットを消費し、名札は
  課金枠を分離しない。配線だけ更新したいときは `apply --skip-dataflow-run`。WF-01 のディスパッチは
  約 100 店舗 × 15 秒 ≈ **25 分**（デモ前の一回限りの populate・間隔は `PL_PARENT_INTERVAL_SECONDS`）。
  保存 CE が per-save で旧版だけ消すので**「WF-01 を2回実行」は必須でなく安全網**（当日は前日 populate 推奨）。
- **誤って本番を触ろうとしたとき**: `provision_domo.py` / `provision_workflows.py` は名札も
  `PL_ALLOW_PRODUCTION=1` も無いまま本番を触ろうとすると**拒否**する（本番を無言で書き換えない）。
  参加者は必ず名札を付けて実行する。
- **本番 Pro-Code design を上書きした場合（最重要）**: `pro-code` を本番 id 付きのまま publish して
  しまったら手を止めて運営へ。運営がリポジトリ正本の `pro-code`（id 保持）を再 publish すれば
  FOLLOW_LATEST で復元される（着手前に「本番へ publish しない」を全員で復唱）。
- **当日トークンの失効**: 終了時、管理 → セキュリティ → アクセストークン で当日発行分を削除。
- ⚠**完全隔離サンドボックス（バックエンドも各自）をやる回の準備**: 入力は **seed DataSet
  `pl_summary_seed`**（ETL の Python タイルが P/L を合成するため入力行の内容は問わない＝最小シード
  でよい）。短文 AI モデルは `DOMO_AI_SUMMARY_MODEL_ID`（env で差し替え可）、長文 AI は WF 層。
  全社ブランチのメール宛先は `PL_EMAIL_PERSON_RECIPIENTS`（person ID・カンマ区切り・配布物に焼き込ま
  ない）。サンドボックスも同じ配備先インスタンスの AI クレジットを消費し、名札は課金枠を分離しない。
