# ハンズオン教材＋配布サンドボックス 横展開プレイブック

> **このドキュメントの目的** — 顧客の本番 Domo インスタンス上で、本番や他参加者を一切壊さずに
> 「VS Code × コーディングエージェントで Domo アプリを開発する」ハンズオンを実施し、その教材＋アプリ一式を
> ZIP で配布するための**再利用可能な設計パターン**を、別の顧客・別の AI がゼロから再現できる粒度で記録する。
>
> **参照実装（リファレンス）** = 本リポジトリ同梱の `reference-architectures/inventory-management-app/` と
> `reference-architectures/pl-summary-app/`（どちらも本パターンで配布可能な形に整備済み）。
>
> なお本書の一部の節では元になった参照実装を `reference-app/` と表記している。本公開版では
> そのフォルダ自体は同梱していないが、対応する実装は以下で読み替えられる:
> `reference-app/scripts/provision_platform.py` ≈ `pl-summary-app/scripts/provision_workflows.py` ＋ `provision_domo.py`、
> `reference-app/scripts/app_studio.py` ≈ `pl-summary-app/scripts/provision_domo.py`（app-studio 機能）、
> `reference-app/dataflow/build_ci_dataflow.py` ≈ `pl-summary-app/dataflow/`、
> `reference-app/dev-guide-app/` ≈ 各アプリの `dev-guide-app/`。
>
> **いつ使うか** — 新しい顧客向けに「本番を借りて安全に手を動かすハンズオン」や「サンドボックス付きの配布アプリ」を
> 作るとき。同梱の参照実装を複製して定数を差し替える／同型を新規 scaffold する、どちらにも使える。
>
> ⚠ 用語の衝突注意: 本書の「サンドボックス」は **環境変数の名札で全オブジェクト名を参加者ごとに一意化する隔離**であり、
> Domo 標準機能の **Sandbox（インスタンス間の昇格・`domo-sandbox.md`）とは別物**。本書のサンドボックスは
> *同一（しばしば本番）インスタンス上*で成立する。

---

## 0. 30秒で全体像

```
         ┌─────────────────── 配布キット（1 顧客フォルダ） ───────────────────┐
         │                                                                      │
  教材    │  dev-guide-app/      純静的 Pro Code（データ接続なし）の縦スクロール  │
 (ガイド) │                      1枚・全10節の視覚教材 → App Studio の「ページ2」 │
         │                                                                      │
  アプリ  │  pro-code/           業務アプリ本体（Pro Code・FE）→ App Studio ページ1 │
 (本体)   │  dataflow/           Magic ETL ＋ 5出力 DataSet                       │
         │  code-engine/        Code Engine（公開1関数 report_api）               │
         │  scripts/            provision_platform.py（CE/AppDB/親子WF/Timer）     │
         │                      app_studio.py（DataApp にカード埋め込み）          │
         │  tests/              契約・特性化・名札隔離の回帰テスト                 │
         │  prompts/ AGENTS.md README.md INSTRUCTOR.md  … 運用・規約・講師ノート   │
         └──────────────────────────────────────────────────────────────────────┘
                 │                                           │
     配布 ───────┘                                           └─────── 実行（名札で隔離）
   ../scripts/make-handson-zip.sh                   CI_SANDBOX_SUFFIX="検証・氏名"
   git archive HEAD → id外し → 5点検証 → ZIP          を付けると全オブジェクト名に
   （PDF は dev-guide を印刷CSS注入して Chrome で出力） （検証・氏名）が付き本番/他者と非衝突
```

**3本柱**：

1. **名札隔離（nameplate isolation）** — 環境変数 `CI_SANDBOX_SUFFIX` 1個で、FE/DataFlow/5出力/CE/親子WF/AppDB/
   スケジュール/state 保存先の**全名前空間**を参加者ごとに一意化。未設定（既定）なら本番挙動は一切変わらない。
2. **本番保護ガード** — 配備入口スクリプトが「**解決後の対象名 == 本番名**なら拒否」という結果ベースの不変条件で
   本番書き込みを止める。本番メンテナのみ `CI_ALLOW_PRODUCTION=1` で解除。
3. **自己完結の配布＋自走できる教材** — 作業ツリーを汚さず ZIP 化（`git archive`）し、本番 id を適切に外し／残し、
   5点自動検証でゲート。教材は純静的 Pro Code で講師なし自走でき、Chrome 不要の決定的 QA で関門化。

---

## 1. アーキテクチャ（配布キットの構成）

参照実装 `reference-app/` の役割分担（横展開時はこの構成を骨格として流用する）：

| ディレクトリ/ファイル | 役割 | 層 |
|---|---|---|
| `pro-code/` | 業務アプリ本体（Pro Code・`manifest.json`＋html/js/css＋`vendor/domo.js`） | FE（App Studio ページ1） |
| `dev-guide-app/` | 開発ガイド教材（純静的 Pro Code・データ接続なし・縦スクロール1枚・全10節） | FE（App Studio ページ2） |
| `dataflow/build_ci_dataflow.py` | Magic ETL ＋ 5出力 DataSet 生成・AI 洞察 | バック（DataFlow） |
| `code-engine/report_request_guard.py` | 公開1関数 `report_api`（CE ソース） | バック（Code Engine） |
| `scripts/provision_platform.py` | AppDB コレクション／CE パッケージ／親子 Workflow／Timer を冪等配備 | バック（配備） |
| `scripts/app_studio.py` | App Studio DataApp にカード（App instance）として埋め込む／`--embed-guide` でページ2 | 配備（FE 公開） |
| `tests/` | 契約・特性化・名札隔離（`test_sandbox_isolation.py`）の回帰テスト | QA |
| `prompts/handson-with-agent.ja.md` | 受講者がコーディングエージェントにそのまま渡す起点プロンプト | 運用 |
| `AGENTS.md` / `README.md` / `CLAUDE.md` | 開発規約・アーキ・安全規約の正本（AI はまず `AGENTS.md`） | 運用 |
| `dev-guide-app/INSTRUCTOR.md` | 3時間ハンズオンの講師ノート（事前課題文面・タイムテーブル・つまずき表・配布ZIP確認） | 運用 |
| `../scripts/make-handson-zip.sh` | 配布ZIPビルダー（**親リポ側＝配布物には同梱しない**） | 配布 |

**設計前提（最重要）**: `domo publish` は design（アプリの実体）を配るだけで**「開けるURL」を作らない**。
業務利用者が URL（`/app-studio/<appId>`）で開くには、App Studio DataApp のページ上に**カード（＝App instance）として埋め込む**
必要がある。この「publish ＝ 配布」「app_studio.py ＝ 開けるようにする」の分離が構成全体の土台。

---

## 2. 名札隔離（サブシステム1：CI_SANDBOX_SUFFIX）

### 2.1 仕組み

3つの配備スクリプト（`build_ci_dataflow.py` / `provision_platform.py` / `app_studio.py`）が**同一の環境変数**
`CI_SANDBOX_SUFFIX` を読む。各モジュール先頭に同一パターンのヘルパを持つ：

```python
def _sandbox_suffix() -> str:
    return (os.environ.get("CI_SANDBOX_SUFFIX") or "").strip()

SANDBOX = bool(_sandbox_suffix())

def _sx(base: str) -> str:                      # app_studio.py では _sandbox_name(base)
    s = _sandbox_suffix()
    return f"{base}（{s}）" if s else base       # ← 全角丸括弧 U+FF08/U+FF09
```

- **名札あり**（例 `CI_SANDBOX_SUFFIX="検証・田中"`）→ 対象名が `企業インテリジェンス（検証・田中）` のように一意化。
- **名札なし（既定）** → `base` をそのまま返す＝**本番と完全同名＝従来挙動を一切変えない**。

名札が付く定数（＝参加者ごとに複製される名前空間）：

| スクリプト | 一意化される定数 |
|---|---|
| `build_ci_dataflow.py` | `DATAFLOW_NAME`, `SUMMARY_NAME`, `TREND_NAME`, `BREAKDOWN_NAME`, `DETAIL_NAME`, `PORTFOLIO_NAME`（5出力DataSet） |
| `provision_platform.py` | `COLLECTION_NAME`(AppDB), `DATASTORE_NAME`, `PACKAGE_NAME`(CE), `SUBFLOW_NAME`(子WF), `MAINFLOW_NAME`(親WF), `SCHEDULE_NAME`(Timer) |
| `app_studio.py` | `APP_NAME`, `CARD_TITLE`（DataApp名／カード名。既定 `_sandbox_name(PRODUCTION_APP_NAME)`） |

### 2.2 名札で**変わらない**もの（契約の不変性）

下流（FE/CE/WF/テスト）の契約を壊さないため、以下は名札でも**不変**：

- `OUTPUT_ALIASES` の**値** `{summary, trend, breakdown, detail, portfolio}`（キー＝出力DataSet名は名札で変わるが、
  FE/CE/WF が参照する **alias 値**は固定）。
- `FUNCTION_NAME = 'report_api'`（CE 公開単一ディスパッチャの内部契約名。operation = validate/save/status/request/data_freshness）。
- タイル id。

→ `tests/test_sandbox_isolation.py` が `sorted(OUTPUT_ALIASES.values())==['breakdown','detail','portfolio','summary','trend']`
と `FUNCTION_NAME=='report_api'` を**名札ありでも**固定であることを assert。

### 2.3 state（解決ID）の参加者分離

3スクリプトとも `_slugify(text)`（英数と `-_` 以外を `-` に畳み、空なら `unknown`）で名札をパス安全化し、
state 保存先を切り替える：

```
~/.config/domo-utils/{INSTANCEの先頭セグメント}-deploy/reference-app/
    └── sandbox-<_slugify(suffix)>/          ← SANDBOX のときだけ挟む
         ├── dataflow-assets.json            （build_ci_dataflow.py）
         └── domo-assets.json                （provision_platform.py / app_studio.py）
```

override 環境変数: build=`CI_DATAFLOW_ASSETS_PATH`、provision/app_studio=`DOMO_ASSETS_PATH`。
これにより同一インスタンス・同一マシンでも参加者間で `*-assets.json` を上書きしない。

### 2.4 横展開（変える／変えない）

- **変えない（骨格）**: `_sandbox_suffix()`/`_sx()`/`_sandbox_name()`/`_slugify()`、`SANDBOX = bool(suffix)` の
  「既定無害・ON で分離」パターン、state_path に `sandbox-<slug>/` を挟む構造、`test_sandbox_isolation.py` の観点。
- **変える（顧客固有）**: 各 `*_NAME` 定数の base 文字列（DataFlow/5出力/AppDB/CE/親子WF/schedule を顧客アプリ名へ）。
  ただし `OUTPUT_ALIASES` の**値**と `FUNCTION_NAME` は契約として極力維持する。

---

## 3. 本番保護ガード（サブシステム2：設計パターン）

### 3.1 不変条件は「対象名 == 本番名」で書く（最重要の設計教訓）

本番書き込みを止めるガードは、**入力（env）の有無で分岐してはいけない**。「解決後の対象名が本番名そのものか」という
**結果ベースの不変条件**で書く。入力有無で分岐すると「名札だけ付けた」「明示名に本番名を打った」等の組合せで**ホールが残る**。

`app_studio.py` の確定形（単一ソース `PRODUCTION_APP_NAME` を基準にする）：

```python
PRODUCTION_APP_NAME = "企業インテリジェンス"   # 本番 DataApp 名＝ガード基準の単一ソース
APP_NAME = (os.environ.get("APP_STUDIO_NAME") or _sandbox_name(PRODUCTION_APP_NAME)).strip()
# ...
if (APP_NAME == PRODUCTION_APP_NAME
        and os.environ.get("CI_ALLOW_PRODUCTION", "").strip().lower() not in ("1", "true", "yes")):
    raise SystemExit("…本番 DataApp を書き換えます。名札を付けてください / 本番メンテナのみ CI_ALLOW_PRODUCTION=1…")
```

この1本で全ケースを正しく捌く：

| 状況 | APP_NAME | 判定 |
|---|---|---|
| 名札なし・APP_STUDIO_NAME なし | `企業インテリジェンス` | **拒否** |
| `APP_STUDIO_NAME=本番名`・名札なし | `企業インテリジェンス` | **拒否** |
| 名札あり ＋ `APP_STUDIO_NAME=本番名` | `企業インテリジェンス` | **拒否**（←ここが「not SANDBOX」分岐だと素通りする穴） |
| `CI_ALLOW_PRODUCTION=1`（本番メンテナ） | 任意 | 許可 |
| 名札あり（APP_STUDIO_NAME なし） | `企業インテリジェンス（検証・氏名）` | 許可（自動一意化） |
| 明示サンドボックス名 | `企業インテリジェンス（検証・花子）` | 許可 |

> **教訓の由来**: 当初ガードを `not SANDBOX and APP_NAME==本番名` と書いたところ、「名札あり＋`APP_STUDIO_NAME`に本番名」
> で `not SANDBOX` が False になり素通りした。`not SANDBOX` を外し**純・本番名基準**にして完全に閉じた
> （`test_app_studio_refuses_production_name_even_with_suffix` が固定）。

### 3.2 3経路すべてに対称なガード

本番を書き換えうる**配備入口は3つ**。すべてに対称のガードを置く：

| スクリプト | 行 | ガード |
|---|---|---|
| `app_studio.py` main() | 〜813 | `APP_NAME == PRODUCTION_APP_NAME` かつ `CI_ALLOW_PRODUCTION ∉ {1,true,yes}` → `SystemExit` |
| `build_ci_dataflow.py` main() | 〜1741 | create/update 到達パス（既定・`--run`）で `not SANDBOX` かつ `CI_ALLOW_PRODUCTION ∉ {…}` → `SystemExit` |
| `provision_platform.py` run() | 〜1202 | `apply=True`(`--apply`) かつ `not SANDBOX` かつ `CI_ALLOW_PRODUCTION ∉ {…}` → `RuntimeError` |

- 読み取り系はガードを通す: build の `--verify`/`--status`/`--print-state`/`--dump-only`/`--sync-manifest`、
  provision の dry-run（`--apply` なし）、`app_studio.py --discover`。
- `CI_ALLOW_PRODUCTION` の判定は `.strip().lower()` 後の完全一致 `{1, true, yes}`。`y`/`on`/`0` は通らない。

### 3.3 その他の安全不変条件

- **危険な既定先の封じ込め**: `FORBIDDEN_INSTANCES = {"", "maintenance-instance.domo.com"}`。`_guard()`/`run()` 冒頭で
  TOKEN 未設定 or INSTANCE が禁止集合なら拒否（開発トークン未 export 時に ryuu/configstore が暗黙に叩く既定先への無言書込み防止）。
- **前方一致フォールバックの事故防止**: `find_dataapp()` は `APP_STUDIO_NAME` 明示時または `SANDBOX` 時は**厳密一致のみ**を使い、
  前方一致（prefix=target[:8]）を使わない。名札付き初回に prefix `企業インテリジェ` が本番 `企業インテリジェンス` を掴む事故を防ぐ（該当なしは `None`→新規作成）。
- **`--sync-manifest` は SANDBOX 専用**（`not SANDBOX` なら即 `SystemExit`）＝本番 manifest の ID 上書き防止。
- **スナップショット保護**: `build` の `dump_snapshot()` は SANDBOX のとき本番 `dataflow/ci-company-intelligence.json` を書き換えない。
- **秘密情報はソース非焼込・環境変数のみ**: `INSTANCE`/`TOKEN` は env からのみ、顧客固有 ID は `manifest.json` から読むだけ、解決 ID は `~/.config` へ。

### 3.4 横展開

- **変えない**: 「対象名==本番名で拒否・`CI_ALLOW_PRODUCTION` のみ解除・3経路対称・既定無害」というガードのロジック。
- **変える**: `PRODUCTION_APP_NAME` の値（＝新顧客の本番アプリ名。**最初に確認すべき単一ソース**）。

---

## 4. 3段階デプロイ ＆ App Studio 埋め込み（サブシステム3）

### 4.1 3段階

```
段階1  cd pro-code && domo publish                    design を配布（開けるURLは作らない）
段階2  python3 scripts/app_studio.py                   App Studio DataApp にカード埋め込み → /app-studio/<id> で開ける
段階3  （任意・バックエンドも自分のものにするなら）
        build_ci_dataflow.py --run                     DataFlow＋5出力を作成・実行
        build_ci_dataflow.py --sync-manifest           5出力 ID を manifest へ
        provision_platform.py --apply                  CE/AppDB/親子WF を配備
        build_ci_dataflow.py --sync-manifest           CE packageId/AppDB collection を manifest へ（2回目）
```

### 4.2 App Studio 埋め込みの詳細フロー（`app_studio.py ensure_app_studio()`）

1. **design 公開確認** `GET api/apps/v1/designs/{design_id}`（未公開なら明確に失敗）。
2. **ensure_dataapp()** — `find_dataapp()` で名前発見（全ページ走査）、無ければ `POST api/content/v1/dataapps` で作成。
3. **ensure_view()** — landing view 取得、無ければ `POST .../views`（`type=dataappview`, `hasLayout=true`,
   `appPageDataSourceId='null'` ＝**文字列 "null"**であって JSON null ではない）。
4. **create_card()** — `POST domoapps/apps/v2/contexts` で designId＋datasetsMapping(alias)＋collectionsMapping を束ねた
   context を作成 → `POST domoapps/apps/v2?fullpage&pageId&cardTitle` に `{contextId}` を渡しカード（App instance＝proxyId 採番）を作成。
   ⚠ `contextId` を card 作成の **id として送らない**（Domo に別の proxyId を採番させる。`proxyId==contextId` は非標準インスタンスとして `RuntimeError`）。
5. **reconcile_context()** — manifest の全 mapping を `PUT domoapps/apps/v2/contexts/{id}`。**宣言外の既存配線は保持**（他機能を壊さない。検証は宣言分の subset 充足のみ）。
6. **configure_layout()** — `GET/PUT api/content/v4/pages/{view}/layouts` でカード1枚をビュー全面に静的ピン。
   `isDynamic:false`、standard `(60,82)` / compact `(12,29)`、`PAGE_BREAK`、`interaction` キーは **pop して未設定へ**（`interaction:DISABLED` は PC クリックを殺す）。

**冪等性**: すべて「名前で発見→無ければ作成」。同じコマンドを何度でも実行可（DataApp もカードも増えない）。
解決 ID（appStudioId/viewId/cardId/proxyId/contextId）は `~/.config/.../domo-assets.json` へ保存。

**`--embed-guide`** = 同一 DataApp の「ページ2＝開発ガイド」に dev-guide-app design を埋め込む（`ensure_guide_page`）。
**ページ1（業務アプリ本体）には一切触れない**。本番メンテナ専用（`CI_ALLOW_PRODUCTION=1` が要る）。

### 4.3 FOLLOW_LATEST と datasetsMapping の罠

- 既定は **FOLLOW_LATEST**（context に designVersion を送らない）→ 2回目以降は `domo publish` だけでコード（design版）が自動反映。
  `APP_STUDIO_PIN_VERSION` を立てた時だけ designVersion を PIN。
- ⚠ **FOLLOW_LATEST はコードを追従するが、埋め込み済みカードの data mapping（context）は作成時の alias 集合のまま追従しない**。
  alias 集合（datasetsMapping/collectionsMapping/packagesMapping）を変えたら `app_studio.py` を再実行して `reconcile_context` で
  `PUT contexts/{id}` する。**列追加だけなら再マッピング不要**（プロキシが列をクエリ時に動的解決）。

### 4.4 認証2系統（横展開でも必ず文書化する）

| 系統 | 使う所 | 認証 |
|---|---|---|
| **ryuu（Domo CLI）** | `domo publish` / `domo dev` / `domo ls` | `domo login`（ブラウザ SSO 既定。`-t <token>` でトークン認証も可）。SID は内部で自動更新・logout まで持続（生 SID 直使いのみ約1h失効） |
| **開発者トークン（REST）** | Python 配備スクリプト（`app_studio.py`/`provision_platform.py`/`build_ci_dataflow.py`） | `DOMO_DEVELOPER_TOKEN`(別名 `DOMO_TOKEN`)＋`DOMO_INSTANCE`。ヘッダ `X-DOMO-Developer-Token` |

- Python 配備スクリプトは **`domo login` だけでは動かない**（開発者トークン必須）。これがハンズオン最大のつまずき。
- **CE/Workflow/AppDB は `domo publish` では配備できない**（REST=開発者トークンのみ）。
- `developer.domo.com` の client_id/secret（OAuth2）は開発者トークン（管理→セキュリティ→アクセストークン）とは**別物**。本教材では使わない。
- エラー切り分け: **401 = トークン/インスタンス不一致、403 = 権限不足**。

---

## 5. 配布 ZIP 生成（サブシステム4：make-handson-zip.sh）

### 5.1 仕組み（`../scripts/make-handson-zip.sh`・親リポ側＝ZIP 非同梱）

```bash
bash ../scripts/make-handson-zip.sh [出力.zip]          # 省略時 $ROOT/handson.zip
```

1. `set -euo pipefail`。`BUILD=$(mktemp -d)` ＋ `trap 'rm -rf "$BUILD"' EXIT`。
2. **作業ツリー非改変の核心**: `git archive HEAD "$APP" | tar -x -C "$BUILD"`（`APP=reference-app`）で
   **コミット済み HEAD の中身だけ**を一時領域へ展開。ローカル未コミット変更も並行エージェントの auto-commit も巻き込まない。
   **リポ上の `manifest.json` を絶対に書き換えない**のが設計上の最重要点。
3. **dev-guide id 除去**: 一時領域の `dev-guide-app/manifest.json` に対し `python3` で `d.pop("id", None)`（**キーごと削除**。空文字 `""` は不可）。
   元リポの dev-guide id（`a34993b4…`）は `--embed-guide` 用に保持したまま。
4. **pro-code id は残す**: 本番 design id `90b76229…`（name=企業インテリジェンス）は剥がさず、**学習者が §7 で自分の手で外す学習ステップ**のため ZIP に意図的に残す。
5. `zip -rq`（最上位エントリ＝`reference-app/`。展開すると親リポ無しの単体フォルダ）。

### 5.2 配布前5点検証（1つでも失敗で `exit 1`）

| # | 検査 | 期待 |
|---|---|---|
| 1 | dev-guide id 除去 `unzip -p … dev-guide-app/manifest.json \| grep -c '"id"'` | **0** |
| 2 | pro-code 本番 id 保持 `… pro-code/manifest.json \| grep -c '90b76229'` | **1**（←除去ではなく**保持**を要求。非対称） |
| 3 | junk 無し `grep -cE 'pytest_cache\|__pycache__\|\.pyc\|DS_Store'` | 0 |
| 4 | 実トークン・秘密鍵 無し（下記 regex・`grep -icE`） | 0 |
| 5 | 他案件・他顧客データ 無し `grep -cE 'pl-summary\|production-priority\|WF-01_main_loop\|news-summary'` | 0 |

- 秘密検出 regex（**プレースホルダ/変数参照は意図的に除外**）: `DOMO_(DEVELOPER_)?TOKEN=["']?[A-Za-z0-9]{20,}` / `xoxb-` / `-----BEGIN (RSA|OPENSSH|PRIVATE) `。
  → `="<...>"` や `="$VAR"` は実値でないので誤検知しない。regex を安易に広げるとテンプレ記述で誤爆する。
- 各 `grep` に `|| true` を付け、0件ヒット時の `grep exit=1` が `set -o pipefail` でスクリプトを誤って落とさないようにする。
- 合格時のみ「✅ 配布可能（展開後は親リポ無しで `node tests/layout/shoot.mjs` が動くことも確認済み）」。

### 5.3 自己完結性（親リポ無しで動く）

展開ディレクトリ単体で `node tests/layout/shoot.mjs` が PNG を出せる＝**npm 依存ゼロ（node 組込みのみ）**、SDK は `pro-code/vendor/domo.js` を**同梱**、
`shoot.mjs` が ryuu/domo.js の `<script>` を除去して `window.domo` をモック注入する。→ 受講者は配布 ZIP だけでローカル1周できる。

### 5.4 「剥がす主体」の非対称（混同しやすい）

- **dev-guide id = 配布時にメンテナが外す**（受講者が誤って `cd dev-guide-app && domo publish` しても本番ガイド design を上書きしない保護）。
- **pro-code id = 学習者が後で自分で外す**（§7 の学習ステップ。だから ZIP には**残す**）。
- cwd 事故（本番フォルダのまま publish）はスクリプトではガードできない → 教材 §5/§7 のコールアウト＋手順で防ぐ。

### 5.5 横展開

- **変える**: `APP` 変数（新顧客フォルダ名）、検証(2)の保持 id 値（`90b76229`→新顧客の pro-code 実 id）、検証(5)の他案件 regex。
- **変えない**: `git archive HEAD → mktemp → 一時領域でだけルール適用 → zip` の骨格、id 外しは pop（空文字不可）、`exit 1` ゲート、
  各 grep に `|| true`、秘密検出はプレースホルダ除外 regex、ビルダーは**配布フォルダの外**（親リポ `../scripts/`）に置き ZIP 非同梱、
  「展開後に親リポ無しで検証ハーネスが動く＝SDK を vendor 同梱・npm 依存ゼロ」。

---

## 6. 開発ガイド教材 ＆ QA ハーネス（サブシステム5：dev-guide-app）

### 6.1 教材の形式と5観点

- **形式** = **純静的 Pro Code**（`manifest.json` の `datasetsMapping:[]` 空・`size{1,1}`）。Domo API を一切呼ばないので
  Domo 上でも `file://` ローカルでも同一に動き QA が容易。SDK `vendor/domo.js`(ryuu) は呼ばなくても標準構成として**同梱（CDN 参照禁止）**。
- **全10節**（縦スクロール1枚）: §1 事前準備（6つ整える）/§2 開発モデル/§3 アプリの構造（3層・Magic ETL タイル分解）/
  §4 外から到達できる15面/§5 デプロイ3段階/§6 開発ループと規律/§7 ハンズオン実習（サンドボックス）/§8 安全ガード/§9 もっと深く（スキル・Domo MCP 比較）/§10 付録（用語集・FAQ・チートシート・完了チェック）。
- **設計5観点**（コンテンツ品質のゴール。横展開でも維持する型）:
  1. **講師なし自走** — §10 困ったとき・撤退ライン（15分目安）・理解度セルフチェック・事前課題で家で緑に。
  2. **コピペ優しさ** — `[data-copy]` ボタンで手入力不要・**画面の見えるテキスト＝コピー内容の単一ソース**・OS 別ブロック併記。
  3. **視覚多め** — 図・表・ポンチ絵が主役、本文は要点のみ。
  4. **ステップバイステップ** — ①準備→②つかむ→③作って確かめる→④安全に続ける。
  5. **デザイン統一** — `app.css` の `--brand-primary` **1色**から `color-mix()` で全濃淡を機械導出。

### 6.2 番号は CSS カウンタが唯一のソース

§N・§N.M・図N・表N・目次番号はすべて CSS カウンタ（`counter-reset: sec fig tbl` / `.sec__no::before{content:counter(sec)}` /
`figcaption{content:"図" counter(fig)}` 等）。**HTML に数字を書かず JS も振らない**（図の増減・節の並べ替えで二重採番事故を防ぐ）。

### 6.3 版の単一ソース（手書き4箇所を機械で突合）

`manifest.json` の `version`（例 `0.5.21`）が**正典**。同じ版が手書きで載る4箇所を同時更新する：
(1) `index.html` colophon `<dd>v0.5.21（日付）</dd>` (2) `index.html` footer `… ・ v0.5.21` (3) `manifest.version`
(4) `tests/thumbnail.html` フッター。版 bump 後は `make-thumbnail.mjs` で `thumbnail.png` を再生成。

### 6.4 QA ハーネス（`dev-guide-app/tests/`）

| ツール | 役割 | 要点 |
|---|---|---|
| `check.mjs` | **Chrome 不要・外部依存ゼロの決定的関門** | 正規表現で**7検査**（番号コメントは8ブロックだが #2 は id 集合の構築で assert を持たない）: ①`<use href="#X">`↔`<symbol id="X">` ②`data-copy="X"`↔`id="X"` ③`href="#X"`↔id ④`aria-labelledby`↔id ⑤`<main id="doc" tabindex="-1">` ⑥版の単一ソース ⑦必須id #doc/#s1/#s10。失敗で `exit 1`＋不整合列挙 |
| `shoot.mjs` | Chrome headless 実描画 PNG 目視 | 既定 `--widths 1680,1024,390 --height 12000`。⚠ 大画面は Chrome 1枚スクショ上限 ~16384px を超え**下端が必ず切れる**＝上部スモークのみ。構造検査は高さ非依存の `check.mjs` が担う。PNG<2000byte は空レンダ失敗 |
| `make-thumbnail.mjs` | 300×300 サムネイル生成（**macOS 専用・sips 依存**） | `manifest.version` と `thumbnail.html` の版不一致なら描画前に `exit 1`。寸法は `sips -g pixelWidth/pixelHeight` で**整数厳密比較**（部分一致 regex だと 3000 が 300 に化けて通る） |

- `app.js` の役割は3点のみ（**データ処理なし**）: ①IntersectionObserver（出現アニメ＋現在地 runningHead）
  ②コピー（`copyText`→`navigator.clipboard` 失敗時 `execCommand` の2段構え・常に真偽値へ解決）
  ③a11y 一括補正（`.ic` に `aria-hidden`、リストに `role=list`、はみ出す要素だけ `tabindex=0`＋`role=region`）。
- **入場アニメの安全網**: IO 非対応なら全節 `.is-in`、`setTimeout 2000ms` で無条件に全節表示、`reduce-motion` で `.reveal` を付けない
  （スクロール無し/IO 不発/描画キャプチャでも本文が隠れたまま残らない）。
- **ryuu の 0バイト化拡張子**（`.LICENSE`/`.mjs`/`.txt` は content-type 未登録で live が空になる既知 footgun）は `manifest.ignore` で publish 除外する。⚠ 参照実装の `manifest.ignore` が実際に挙げているのは **vendor の `.LICENSE` 1件のみ**（`.mjs` はテスト用で `tests/` 配下にあり実行時非参照、`.txt` は存在しない）。該当拡張子を**バンドル直下に同梱する場合に** `ignore` 対象へ足す、というルールであって「3拡張子を常に列挙する」の意ではない。

### 6.5 横展開

- **変えない（型）**: 純静的 Pro Code（datasetsMapping 空）、版の単一ソース＋`check.mjs` の正規表現検査（Chrome 不要で CI 安全）、
  番号は CSS カウンタ、5観点のコンテンツ設計、`--brand-primary` 1色からの color-mix 導出。
- **変える（顧客固有）**: `--brand-primary`（現 Daiwa 深紅 `#741826`）、ブランド文言、保護対象 design id、
  §3/§4 の具体値（タイル数・出力本数・15面の面構成）、§7 の作業パス（`~/handson-ci`）・スクリプト名・実インスタンス名。

---

## 7. PDF 生成（サブシステム6：教材の配布用 PDF）

`index.html` は画面用で印刷 CSS を持たない（横スクロール要素が印刷で右端切れする）。配布 PDF は**一時 `_print.html` に印刷CSSを注入**して Chrome headless で出力する（**再現手順**）：

```bash
cd reference-app/dev-guide-app
# 1) index.html の </head> 直前に @media print を注入した _print.html を作る（作業ツリーは汚さない一時ファイル）
python3 - <<'PY'
import pathlib
d = pathlib.Path(".")
html = (d/"index.html").read_text(encoding="utf-8")
inject = '''<style media="print">
@page { size: A4; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }   /* 背景色を保持 */
.callout, .tile, .cmd, .vs, .boundary, .try { break-inside: avoid; }
tr { break-inside: avoid; }
.demotable td, .demotable th { white-space: normal; }                 /* ⭐幅広4列表の縦1文字化＋空白頁化を解消 */
</style>
</head>'''
assert html.count("</head>") == 1
(d/"_print.html").write_text(html.replace("</head>", inject, 1), encoding="utf-8")
PY
# 2) Chrome headless で PDF 出力（app.css の @media print{.cmd__body{…}} は <link> 経由で自動適用される）
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=20000 --run-all-compositor-stages-before-draw \
  --print-to-pdf="$HOME/Desktop/<教材名>.pdf" "file://$PWD/_print.html"
# 3) 後片付け
rm _print.html
```

**注意**:
- `app.css` に `@media print { .cmd__body { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; } }`
  が**コミット済み**（コマンド本文が印刷で右端切れするのを防ぐ）。これは `<link href="app.css">` 経由で `_print.html` にも効く。
- ⛔ `figure { break-inside: avoid; }` は入れない（幅広表を丸ごと次頁へ押し出し**空白頁**を生む）。
- **検証（空白頁なし）**: `pdfinfo` で頁数・A4 を確認 → `pdftoppm -r 12 -png` で全頁を低解像描画 → 各 PNG の非白画素率を測り、
  **最小インク率が十分 >0%（例 2%+）**なら空白頁なし。さらに `pdftotext` で版文字列と主要語（名札・サンドボックス等）が
  テキスト層にあるか grep して、意図した版・内容から生成されたことを確認する（タイムスタンプだけに頼らない）。

---

## 8. 自律改善サイクル ＆ 敵対レビュー ＆ 検証規律（サブシステム7）

教材・アプリを「席を外しても安全に磨き続ける」ための運用規律。正本 = `autonomous-improvement-loop.md`・
`../docs/autonomous-loop.md`・`code-review.md`。

### 8.1 1増分サイクル（成果単位＝「緑・コミット済み・プッシュ済み」）

```
Choose（最高価値1件・batch しない） → Implement（最小増分）
  → Validate（落ちたら先に直す） → Commit & Push（明示パス）
  → Record & tidy → step1 へ
```

- **ローカル検証例**: `node --check pro-code/app.js` / `node tests/test_pure_helpers.js` / `python3 -m pytest tests/ -q` /
  `node tests/layout/shoot.mjs`（PNG 目視） / dev-guide は `node tests/check.mjs`・`node tests/make-thumbnail.mjs`。
- **常時**: `bash ../scripts/check-secrets.sh` と `bash ../scripts/validate-workspace.sh`（`.githooks/pre-push` が push 前に自動実行）。
- **FE/live 変更の順序**（この案件の確立パターン）: ローカル検証 → **版 bump（4箇所）** → `domo publish`（ryuu footgun：
  現インスタンス確認 → publish → 別案件インスタンスへ復帰） → **live 検証**（`domo download -i <id> -d latest` で committed と byte 一致） → commit/push。
- ⚠ **doc/script/test だけの変更で `index.html` 不変なら、dev-guide の再 publish は不要**（LIVE 版維持＋ZIP 再構築のみ）。
  doc・script・test は ZIP/git 配布で ryuu 非対象。

### 8.2 敵対的レビューで配布適性を監査

`code-review.md` の Review Priorities（既存 README/manifest/prompt/公開関数契約との矛盾、公開 API/alias/
Dataset/AppDB/WF 名の予期せぬ変更、Domo 破壊的書込み、秘密情報、エラー処理、AI 向け返り値の曖昧さ、テスト）を
**多観点 finder → refute（反証）多数決 verify** で回し、refute を通ったものだけ採用（`ReportFindings` の verdict=CONFIRMED/PLAUSIBLE）。
workspace 実証の高シグナル lens（sibling-branch 契約一貫性 / grep-exit=2 の false-clean / mutate-before-validate /
非原子 multi-step mutation / set -e 下の到達不能ガード / CE closure は API path で監査）。「No findings」は実際に該当ファイルを見た時だけ。

> この案件では配布直前に敵対再監査を実施し、**自分の是正が生んだ回帰**（本番保護ガード追加で本番メンテナ手順ドキュメントが
> コード挙動と矛盾）を検出・是正した。**教訓: 変更はコードとドキュメントの両方を同時に動かす。doc 追従漏れは「現 doc と矛盾する変更」
> として同クラスの新矛盾になる**（嘘をつく索引は無い索引より悪い）。

### 8.3 飽和検出 → 正直 report + idle

収量逓減時は増分を捏造しない。owned dir の recency scan（全 owned <24h touch）＋同一 identity 確認＋in-progress/
shared-notices のレーン確認＋7日窓で false-idle 除外 → 飽和なら handoff に一度だけ記録し idle（≠恒久 stop・新 FB/別観点で再開）。
clean な discovery/verification pass も valid な outcome。

### 8.4 git 規律（並行エージェント対策）

- **commit は明示パスのみ**。`git add -A` / `git add .` / `git commit -a` 禁止（並行エージェント/ユーザーの無関係変更の巻込回避）。
- commit 前に `git status` ＋ `git log origin/main..HEAD` ＋ `git diff --cached` を確認。切り分け不能なら自分のパスだけ commit し残りは handoff。
- commit メッセージの `-m "msg"` は `-- <paths>` の**前**に置く（後置するとメッセージが pathspec 扱いで失敗する）。
- 機械的一括適用（bulk edit）の前に対象集合を列挙し旧パスを grep で洗う。LLM の proposedText を機械適用する前は
  **指示メモ混入（instruction-note）を疑って内容を事前 scan** してから当てる。

---

## 9. 新顧客への横展開手順（ステップバイステップ）

> 前提: 既存 `reference-app/` を複製して定数差し替え、が最短。以下は「変える値」を順に潰す手順。

1. **フォルダ複製** → 新顧客名のフォルダへ。`AGENTS.md`/`README.md`/`CLAUDE.md`/`INSTRUCTOR.md`/`prompts/` の顧客名・文面を更新。
2. **ガード基準の単一ソースを差し替え** → `app_studio.py` の `PRODUCTION_APP_NAME` を**新顧客の本番アプリ名**へ。
   これがガードの基準なので最初に確定する。
3. **全オブジェクト名定数を顧客用語へ** → `build_ci_dataflow.py`（DataFlow/5出力）・`provision_platform.py`
   （AppDB collection・datastore/CE package/親子WF/schedule）。**`OUTPUT_ALIASES` の値と `FUNCTION_NAME` は契約として維持**。
4. **manifest 群** → `pro-code/manifest.json` と `dev-guide-app/manifest.json` の design id・`datasetsMapping`・
   `packagesMapping`・`collectionsMapping` を新顧客の実 ID へ（横展開初期は id を外して新規採番でもよい）。
5. **ブランド** → `dev-guide-app/app.css` の `--brand-primary` 1行を顧客ブランド色へ（全体が追従）。
6. **入力・ロジック** → 入力 DataSet（`CI_INPUT_DATASET_ID`/`CI_MASTER_DATASET_ID`）、集計タイル、`prompts/`、AI モデル（`CI_AI_MODEL_ID`）。
7. **名前契約テストを緑に** → `tests/test_sandbox_isolation.py` のスナップショット期待値（本番名・alias・`report_api`）を顧客値へ更新し緑化。
8. **配布ビルダーの id チェック値更新** → `make-handson-zip.sh` の `APP` 変数・保持 id（`90b76229`→新 pro-code id）・他案件 regex。配布前5検証を緑に。
9. **教材の版4箇所同期＋thumbnail 再生成** → `check.mjs` 緑・`make-thumbnail.mjs` で thumbnail 再生成。
10. **配備1周の実機確認（サンドボックスで）** →
    ```bash
    export DOMO_INSTANCE=<顧客>.domo.com DOMO_DEVELOPER_TOKEN=<token>
    export CI_SANDBOX_SUFFIX="検証・<氏名>"
    cd pro-code && domo publish && cd -
    python3 scripts/app_studio.py --discover         # 読取のみで疎通
    python3 scripts/app_studio.py                    # 名札で DataApp 名も自動一意化
    # 任意（バックエンドも）: build_ci_dataflow.py --run → --sync-manifest → provision_platform.py --apply → --sync-manifest
    ```
    本番メンテナが本番へ反映する時だけ名札なし＋`CI_ALLOW_PRODUCTION=1`。
11. **ドキュメントを同じ増分で追従** → コード/定数を変えたら AGENTS/README/INSTRUCTOR/prompt を同時更新（doc 矛盾を残さない）。

---

## 10. 新顧客展開チェックリスト（配布前に必ず確認）

- [ ] **(1)** 配布 ZIP/コピーで **pro-code の本番 design id を学習者が自分で外す手順**を教材（§7）に明記したか。dev-guide 側 id は配布時に外し（publish 対象外）か。
- [ ] **(2)** `PRODUCTION_APP_NAME` と全オブジェクト名定数を顧客アプリ名へ更新し、**ガードの基準が実在する本番名を単一ソースで指す**か。
- [ ] **(3)** **本番書込み3経路**（`build --run` / `provision --apply` / 画面の「作成・再作成」）すべてに名札ガードが掛かるか。
      FE のみサンドボックス（バックエンド未構築＝manifest が本番 CE/AppDB を指す）で③が本番を叩かないか。
- [ ] **(4)** 開発者トークン/SID が env のみで、コミット/チャット/サンプルデータに秘密が無いか（`check-secrets.sh`）。
- [ ] **(5)** public CE 関数名・alias・DS/AppDB/WF 名を変更していないか（下流影響が広い）。
- [ ] **(6)** ryuu の **0バイト化拡張子（`.mjs`/`.LICENSE`/`.txt`）**をバンドルに同梱していないか、必要なら `manifest.ignore` 済みか。
- [ ] **(7)** 本番・他参加者・複数サンドボックスが**同一本番インスタンス上に同居**しても衝突しない名前・state 分離になっているか。
- [ ] **(8)** ハンズオン終了手順に**当日発行トークンの失効（必須）**を入れたか。
- [ ] **(9)** ガード発火を実機で確認したか（名札も `APP_STUDIO_NAME` も無しで `app_studio.py` → `SystemExit` が正しい挙動）。6シナリオ（名札なし/本番名明示/名札+本番名/メンテナ allow/名札のみ/明示 sandbox 名）を実測。
- [ ] **(10)** doc（AGENTS/README/INSTRUCTOR/prompt）がコード挙動と矛盾しないか（本番メンテナ手順に `CI_ALLOW_PRODUCTION=1` が反映済みか）。

---

## 11. 落とし穴（gotchas）集約

- **publish ≠ 開けるURL**: `domo publish` は design を配るだけ。`app_studio.py` のカード埋め込みが別途必須。
- **cwd 事故**: 本番フォルダのまま publish すると本番 design を上書き。検証は必ず `~/handson-ci` にコピーし VS Code で開き直す。publish 前3点確認（pwd・一式・`grep -c '"id"' pro-code/manifest.json` が 0）。
- **id は pop（キーごと削除）が正**。空文字 `""` は ryuu publish が失敗。id 省略で新規採番。
- **dev-guide と pro-code で id の扱いが逆**（dev-guide=配布時に外す／pro-code=学習者が後で外すので残す）。make-handson-zip の検証(2)は「除去」ではなく「保持=1」。
- **認証2系統の取り違え**が最頻つまずき: Python 配備は開発者トークン必須（`domo login` では動かない）。CE/WF/AppDB は REST のみ（publish 不可）。SID は約1h 失効。
- **FOLLOW_LATEST の context 非追従**: datasetsMapping の alias 集合を変えたら `app_studio.py` 再実行で `reconcile_context`。列追加だけなら再マッピング不要。
- **ryuu 0バイト化拡張子**: `.mjs`/`.LICENSE`/`.txt` は content-type 未登録で live が空になる。`manifest.ignore` へ。`domo download -i <id> -d latest`（`-d latest` 必須）で byte 突合。
- **appPageDataSourceId は文字列 `"null"`**（JSON null ではない）。
- **contextId を card の id として送らない**（proxyId を別採番させる。`proxyId==contextId` は非標準インスタンスとして `RuntimeError`）。
- **build --run は 368社ぶんの AI TextGen**（自分のクレジット・時間。E2E 実測 1社≈60秒、Domo AI バッチは 6h タイムアウト有）。小規模化は `CI_INPUT_DATASET_ID` でシード縮小。
- **名札サフィックスは全角丸括弧（）**であり半角 `()` ではない（grep/照合時に注意）。
- **state slug はインスタンス名の先頭セグメント**。別インスタンスへ切替えると別 state ツリーになり以前のサンドボックス資産 ID を見失う。
- **Workflow の text 変数に改行が入ると**カスタム CE ステップ呼び出しが失敗する（親→子へ渡す context_json に改行入りの長文を載せない）。
- **AppDB 保存はコレクション名でなく UUID**。sort は環境により無視される（`createdOn` 最大で最新選択）。
- **make-thumbnail.mjs は macOS の sips 依存**（他 OS は縮小手段を差し替え）。
- **shoot.mjs は大画面で下端が切れる**（1枚スクショ上限 ~16384px）＝上部スモークのみ。構造検査は `check.mjs`。
- **Bash の cwd 持続挙動が列挙を偽 empty 化**しうる（絶対パス＋件数確認で担保）。`grep exit=2` は no-match(1) でなくファイル不可/オプション誤＝false-clean。

---

## 12. 参照ファイル索引（リファレンス実装）

| ファイル | 要点 |
|---|---|
| `reference-app/AGENTS.md` | 開発規約・3段デプロイ・安全規約・検証コマンドの正本（AI はまず読む） |
| `reference-app/scripts/app_studio.py` | App Studio 埋め込み＋本番保護ガード。`PRODUCTION_APP_NAME`(57)、`FORBIDDEN_INSTANCES`(76)、ガード(〜813)、`find_dataapp` 厳密一致(214)、`ensure_*`/`reconcile_context`/`configure_layout`/`ensure_guide_page` |
| `reference-app/dataflow/build_ci_dataflow.py` | Magic ETL＋5出力。`_sx`/名札(96-111)、`--run` ガード(〜1741)、`sync_manifest` SANDBOX専用(〜1590)、`dump_snapshot` 保護 |
| `reference-app/scripts/provision_platform.py` | AppDB/CE/親子WF/Timer 配備。名札(39-77)、`FUNCTION_NAME='report_api'`、`--apply` ガード(〜1202)、危険インスタンス拒否 |
| `reference-app/tests/test_sandbox_isolation.py` | 名札隔離の命名契約を固定（既定不変/全名一意化/alias・report_api 不変/state 分離/本番 DataApp 誤捕捉防止/本番名書込み拒否 複数ケース） |
| `reference-app/dev-guide-app/index.html` | 教材本体（純静的 Pro Code・全10節・CSS カウンタ・版は colophon/footer 手書き2箇所） |
| `reference-app/dev-guide-app/app.css` | `--brand-primary` 1色→color-mix 導出・CSS カウンタ・`@media print{.cmd__body{…}}`(527) |
| `reference-app/dev-guide-app/tests/check.mjs` | Chrome 不要の決定的関門（参照整合＋版単一ソース） |
| `reference-app/dev-guide-app/tests/shoot.mjs` / `make-thumbnail.mjs` | PNG 目視 / 300×300 サムネイル（macOS 専用） |
| `reference-app/dev-guide-app/INSTRUCTOR.md` | 3時間講師ノート・配布ZIP構成確認（§8） |
| `reference-app/prompts/handson-with-agent.ja.md` | 受講者がエージェントに渡す起点プロンプト（1周構成） |
| `../scripts/make-handson-zip.sh` | 配布ZIPビルダー（git archive→id外し→5点検証・親リポ側＝ZIP非同梱） |
| `autonomous-improvement-loop.md` / `../docs/autonomous-loop.md` | 自律改善ループの振る舞い契約・運用（sentinel/loop-control/Stopフック） |
| `code-review.md` | 敵対的レビューの型（Review Priorities・高シグナル lens・Output Shape） |
| `../docs/domo-auth.md` | 認証優先順位・ヘッダ対応表・git 非保存リスト・Pro Code デプロイ規則 |
| `domo-procode-app.md` / `domo-code-engine.md` / `domo-appstudio.md` | Pro Code / CE / App Studio の個別スキル |

---

**メンテナンス**: このプレイブックは参照実装 `reference-app` の実挙動を正とする。実装を変えたら本書の該当節も
同じ増分で更新する（§8.2 の「コードと doc は同時に動かす」をこの文書自身にも適用）。事実（定数・行番号・id）は時間で陳腐化しうるので、
横展開前に参照ファイルで裏取りすること。

**第2の適用例（2026-10-06）**: 本パターンを `production-priority-app`（ヤマハ 鄭さんチーム・生産優先度分析）へ移植した。
このアプリは Code Engine／Workflow／AppDB を持たない **2 層（Magic ETL DataFlow 3063 ＋ Pro Code FE）** のため、
名札隔離・本番保護ガードの対象は **FE（`scripts/app_studio.py` の DataApp／カード・名札＋`CI_ALLOW_PRODUCTION` ガード、
`--embed-guide` でページ2）** と **DataFlow（`dataflow/deploy_3063.py` に名札サンドボックス新規作成＋本番保護ガードを追加）** の
2 経路に縮約される（CI の build/provision/5出力/親子WF/AppDB に対応する節は FE＋DataFlow へ読み替える）。配布 ZIP は
`../scripts/make-ppa-handson-zip.sh`（検証(2)保持 id＝`282e5125`、検証(5)の他案件 regex は反転＝`production-priority` を外し
CI 等の実資産 id／ブランドを列挙）。横展開時の「変える値／縮約する節」の実例として参照できる。
