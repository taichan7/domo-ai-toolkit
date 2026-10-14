# INSTRUCTOR.md — 講師ノート（3 時間ハンズオン運用）

対象: 在庫入出庫管理アプリを配布された開発者向け / VS Code × コーディングエージェントで Domo を開発。
教材本体: `dev-guide-app/`（App Studio ページ2「開発ガイド」）。配布: `inventory-management-app/` を ZIP で各自へ。
土台スターターキット: `domo-ai-starter`。

> 表記約束: 本ノートの `<自社>` は教材 `index.html` のインスタンス名プレースホルダ（各自の Domo インスタンス名）と同じ。
> §参照の約束: 教材（dev-guide-app）の節は `dev-guide §N`、このファイル自身の節は `本ノート §N`。無印の `§N` は教材を指す。
> 小節は番号でなく**小節名**で指す（教材は小節番号を表示しないため）。

## 0. 事前に配る文面（チャット/メール用・コピペ可）

```
【事前課題（当日までに 15〜30 分）】当日はすぐ実習に入れるよう、家で「緑」にしておいてください。
0) 配布された inventory-management-app（ZIP）を展開し、分かる場所に置く（以降すべての前提）
1) VS Code を入れて、コーディングエージェント拡張（Claude Code / Codex / GitHub Copilot のどれか）にサインイン
2) Node・Python・Git と Domo CLI（npm install -g ryuu）を入れ、`domo login -i <自社>.domo.com` まで通す
3) domo-ai-starter を clone（dev-guide §1「土台を置く」、または starter リポジトリの README）
4) 開発者トークンを発行し、環境変数（DOMO_INSTANCE / DOMO_DEVELOPER_TOKEN）に設定
   （運営が参加者ぶんのサンドボックスを用意する回はトークン不要）
5) Google Chrome を入れ、`node tests/layout/shoot.mjs` を1回動かして PNG が出ることを確認（業務アプリ本体の目視）
6) （任意・多人数回は推奨）実習用コピーを作り、`pro-code/manifest.json` の id を外して `domo publish` まで
詰まったら、その時点の画面スクショを送ってください。当日の冒頭 25 分でも点検します。
```

## 1. 当日タイムテーブルと到達ゲート

| 時刻 | 内容 | 節 | 到達ゲート（ここまで来たら次へ） |
|---|---|---|---|
| 0:00 | ねらい・全体像 | — | ゴール 1 枚が伝わった（端末→可視化の流れ） |
| 0:10 | 環境点検（各自） | §1 | **全員が「起点プロンプト」をエージェントに渡し、足りないものが出ない**（出る→サポート）。時間が余れば §1 末尾のミニ実習を数本 |
| 0:35 | 開発モデル | §2 | — |
| 0:50 | アプリの構造（3層・2経路・データモデル） | §3 | — |
| 1:10 | 作れるもの／デプロイの 3 段階 | §4・§5 | — |
| 1:30 | 休憩 | — | **休憩前に「全端末が緑」を宣言**（赤い人が残っていれば 10 分延長可） |
| 1:40 | エージェントの回し方と規律 | §6 | — |
| 2:00 | 実習（手を動かす） | §7 | **各自の名札付きサンドボックスが配備・publish され、1 変更が画面に映る** |
| 2:40 | 安全・片付け・まとめ | §8（安全）／§7 末尾（片付け）／§10（付録：セルフチェック・FAQ） | **全員が本番保護の線（名札 `INVENTORY_SANDBOX_SUFFIX` 必須／本番 design 上書き禁止／名札なしの書込コマンドは拒否／AI クレジットの扱い／dev-guide publish 禁止／他参加者の名札付き資産禁止／エージェントの「常に許可」を選ばない）を復唱** → dev-guide §10 のセルフチェック → クリーンアップの号令 → 各自の検証資産を削除（任意） |

## 2. 開始前に埋めるもの（環境・権限チェック）

- [ ] 受講者の Domo ユーザー: **アプリ作成／カード埋め込み権限**（本番 DataApp の編集可否は不要。新規作成できること）
- [ ] **出力 DataSet（`Inventory Management | Dashboard`）と AppDB の閲覧権限**（読めないとカードが空になる）
- [ ] **開発者トークン**を発行できるか（できない場合は本ノート §3「トークン無し運用」へ）
- [ ] 社内プロキシの値（npm / git / Domo への到達）
- [ ] **当日端末のソフト導入可否**（会社管理 PC は winget / `npm install -g` が禁止のことがある。不可なら事前に情シス申請、または事前キッティング済みの貸与端末を手配）
- [ ] **会場ネットワークで実機 1 台の事前疎通**（前日までに `npm install -g ryuu` / `git clone` / `domo login` / `domo publish` まで通す＝false green 対策。失敗時は許可ドメイン `fonts.googleapis.com` / `github.com` / `*.domo.com` を IT へ申請）
- [ ] **後方支援比率**（受講者 6〜8 名ごとに巡回 TA 1 名。環境点検ゲート 0:10-0:35 に人員を厚く。早く終わった人は dev-guide §9「もっと深く」へ誘導）
- [ ] 共有エージェントアカウント（有料枠が無い人のため。**同時実行/利用量に上限**。目安 1 アカウント数名まで。**一斉利用で 429／上限に達し全員同時停止のリスク**→主エージェントは各自の無料枠を既定にし、共有枠は副へ。詰まったら時間差実行）
- [ ] インスタンス名の案内文（`<自社>.domo.com`）

## 3. トークン無し運用（推奨・人数が多い回）

参加者ぶんのサンドボックスをバックエンドまで各自に作らせない（または作れない）場合のフォールバック:

1. 各参加者は事前に実習用コピーを作り、`pro-code/manifest.json` の id を外して `domo publish`（事前課題に含める。`domo publish` は OAuth/SID の `domo login` だけで通り、開発者トークンは不要）。
2. 当日は運営が 1 台ずつ、参加者名の名札を付けて `INVENTORY_SANDBOX_SUFFIX='検証・<氏名>' python3 scripts/provision_domo.py app-studio` で DataApp（ページ1 業務アプリ＋ページ2 開発ガイド）を発見または作成する（開発者トークンは運営端末のみ）。
3. 以降の実習は `domo publish` だけで反映（FOLLOW_LATEST）。バックエンド（AppDB/CE/DataFlow/通知WF）は本番の読取に乗せる想定で、書込を伴う `apply`／`workflow` は運営のみが名札付きで実行する。

## 4. 想定つまずき（名指しで先回り）

| 症状 | 原因 | 対処 |
|---|---|---|
| `DOMO_DEVELOPER_TOKEN が未設定です` | Python スクリプトは `domo login` では動かない | dev-guide §1 の②でトークン発行＋env 設定（ターミナルを開き直したら再設定） |
| `危険な既定先/未設定インスタンス '' …` | `DOMO_INSTANCE` 空 | `$env:DOMO_INSTANCE="<自社>.domo.com"` / `export …` |
| `shoot.mjs が Chrome を見つけられない` | Chrome 未導入（Edge のみ） | Chrome を導入。応急は `CHROME_PATH` を `msedge.exe` へ（保証外） |
| publish 成功なのに画面が変わらない | キャッシュ/追従遅延 | ハードリロード → 数十秒待ち → version を上げて再 publish |
| カードは出るが中身が空 | 出力 DataSet／AppDB の閲覧権限 or context 未同期 | 権限確認 → 名札付きで `provision_domo.py app-studio` を一度実行 → dev-guide §4 の読取プロンプトで疎通確認 |
| 本番フォルダのまま publish した | cwd 事故 | 直ちに `domo publish` を止め、実習用コピーを VS Code で開き直す（本番 design は dev-guide §7 の手順なら id 無しで別採番される） |
| `.sh が動かない`（Windows） | bash が無い | VS Code の既定ターミナルを Git Bash に（dev-guide §1「Node・Python・Git を入れる」の注記） |
| 書込コマンドが「本番名のため拒否」で止まる | 名札（`INVENTORY_SANDBOX_SUFFIX`）未設定で `apply`/`app-studio`/`workflow`/`cleanup-legacy` を実行 | 名札を設定して自分のサンドボックスへ（本番メンテナのみ `INVENTORY_ALLOW_PRODUCTION=1`） |
| 共有エージェントアカウントが 429／利用上限 | 一部屋が一斉に同一アカウントを叩きレート超過 | 各自の無料枠へ退避、または時間差実行 |

## 5. 絶対に守らせる線（名札で本番保護・復唱させる）

- **名札（`INVENTORY_SANDBOX_SUFFIX="検証・<氏名>"`）を全員が必ず設定**＝AppDB・Code Engine・DataFlow・出力 DataSet・通知 Workflow・App Studio の**全オブジェクトが自分専用名（全角括弧の名札付き）**になり、本番や他参加者と分離（同じインスタンス上に複数サンドボックスが同居しても安全）。未設定（既定）は本番と byte 同一のため、名札を付けずに書込コマンドを走らせない。
- 本番のガイド design・業務アプリ design を**上書きしない**（コピーで id を外す）。
- `provision_domo.py` の**書込コマンド（`apply` / `app-studio` / `workflow` / `cleanup-legacy`）は名札付きなら自分のサンドボックスにのみ実行**。**名札なし（本番名のまま）は実行を拒否**（本番メンテナのみ `INVENTORY_ALLOW_PRODUCTION=1` で明示解除）。**読取（`verify` / `sync-manifest` / `export-app-studio`）は常に通る**。
- **AI クレジットを使う処理に注意**：分析 DataFlow（品目×ロケーション残高ごとの per-entity AI 在庫コメント生成）と通知 Workflow（AI Agent の本文組立）はクレジットを消費する。**サンドボックスも配備先インスタンスのクレジットを消費し、名札は課金枠を分離しない**。実習は少数品目で試す。
- `dev-guide-app` を publish しない（本番ガイド design を守る）。
- **エージェントの「常に許可／自動承認／自動実行」を選ばない**（関門が外れ、publish・書込み・削除が無確認で走る）。
- 本番 design・共有資産・**他参加者の名札付き資産**に触れない。
- ⚠**完全隔離サンドボックス（バックエンドも各自）をやる回の準備**：分析 DataFlow の**1 入力 DataSet（AppDB の標準同期）の読取権限**と、AI クレジット枠を確認。残高 1 件ごとに per-entity の在庫コメントを AI 生成するため、**少数品目の入力とクレジット枠**を用意する。

## 6. 終了時のクリーンアップ号令

「名札（検証・<氏名>）の付いた自分のサンドボックス資産（App Studio DataApp・design・作っていれば DataFlow・出力 DataSet・CE・通知 Workflow・AppDB）と、**当日発行した開発者トークン**だけを片付けてください。
名前と id を確認してから削除。**本番（名札なし）や他参加者（別の名札）の資産には触らない**」。
手順は dev-guide §7 末尾の「後片付け」プロンプトを各自に貼ってもらう（削除は任意。迷う人は残してよい）。
片付けは自分の名札付きオブジェクトのみ＝`provision_domo.py cleanup-legacy` も名札付きで自分のサンドボックスにしか効かない。
**時間内に終わらなければセッション後に各自で実施してよい**（トークン失効を忘れずに）。
不要ならローカルの実習用コピーも削除してよい。

## 7. 進行の小ネタ

- 講師の画面は教材の該当節を開いて投影（App Studio のページ2「開発ガイド」）。
- 受講者が止まったら、まず「起点プロンプト」を再掲→エージェントに点検させる。
- 各節の所要が押したら、dev-guide §4 の詳細（詳解カード）を飛ばして dev-guide §7 を優先（実習が本体）。
- 詰まった人・早く終わった人には dev-guide §10「理解度セルフチェック」(1 分) を回させ、理解を自己確認させる（講師の口頭確認の代替）。
- デプロイの正順（dev-guide §5）は **`provision_domo.py apply` →（別インスタンスのみ）`sync-manifest` →（`cd pro-code && domo publish`）→（`cd dev-guide-app && domo publish`）→ `provision_domo.py app-studio` → `verify`（ok:true）**。`domo publish` は design を配るだけで開ける URL は作らない＝`app-studio` の埋め込みで初めて開ける、を強調する。

## 8. 配布 ZIP の構成（本番 id の扱い・受領物の確認）

この配布物（`inventory-management-app` の ZIP）は配布元（Domo SE）が整えた状態で届く。作成は配布元メンテナが
親リポジトリ直下で **`bash make-handson-zip.sh（非公開メンテナツール）`** を実行して行う（内部で `git archive HEAD` を
一時領域へ展開＝作業ツリーを汚さず・`pytest_cache` / `__pycache__` / `.DS_Store` を含めない。配布ルール適用後に
5項目の配布前検証を自動実行し、1つでも失敗すれば `exit 1`）。手で `git archive` するだけでは下記の id 除去は行われない。

- `dev-guide-app/manifest.json` の `id` はビルダーが**外す**（受講者が誤って `cd dev-guide-app && domo publish` しても
  本番ガイド design `aeb6e8d5` を上書きせず、使い捨ての新 design が採番されるだけ）。
- `pro-code/manifest.json` の本番 design id は、受講者が dev-guide §7 で**自分の手で id を外し、新しい design を採番する**学習ステップのため意図的に残す（cwd 事故の防止は dev-guide §7 の手順説明と dev-guide §5 のコールアウトに依存）。

受領した配布 ZIP を念のため確認するなら（いずれも期待どおりなら安全）:

```bash
unzip -l <配布>.zip | grep -E 'pytest_cache|__pycache__|DS_Store'                                  # 何も出ない
unzip -p <配布>.zip inventory-management-app/dev-guide-app/manifest.json | grep -c '"id"'           # 0（dev-guide の id は除去済み）
unzip -p <配布>.zip inventory-management-app/pro-code/manifest.json     | grep -c '"id"'            # 1 以上（業務アプリ本体の design id は学習用に意図的保持）
```

> 展開後の ZIP は親リポジトリ無しで `node tests/layout/shoot.mjs`（PNG 目視）が動く（vendor 同梱 SDK を含む）
> ＝「配布 ZIP だけでセルフ完遂」を実機確認する。詳しい読み解きは `docs/handson-guide.md`、配布の入口プロンプトは `prompts/deploy-with-agent.ja.md`。

## 9. 版同期（版の単一ソース）

教材の版は `dev-guide-app/manifest.json` の `version`（本書 **v2.0.1**）を正とする。配布元メンテナが版を上げるときは、
次の 3 箇所を**同時に**合わせてから `node tests/make-thumbnail.mjs` で `thumbnail.png` を再生成する:

1. `dev-guide-app/manifest.json` の `version`（例 `2.0.1`）＝正
2. `dev-guide-app/index.html` の colophon（`<dt>版</dt><dd>…</dd>`）＝ `major.minor`（例 `2.0`）
3. `dev-guide-app/tests/thumbnail.html` のフッター（`<span>v2.0.1</span>`）＝ `v` ＋フル版

`node tests/check.mjs` は colophon が `manifest` の `major.minor` と一致するか（版ドリフト）を、
`node tests/make-thumbnail.mjs` は `manifest` と `thumbnail.html` の版一致を、それぞれデプロイ前に機械検査する。
バックエンド（CE/DataFlow/通知WF）の版は `provision_domo.py` が別系統で扱い、`sync-manifest` は版欄を書き戻さない（想定どおりで verify は落ちない）。
