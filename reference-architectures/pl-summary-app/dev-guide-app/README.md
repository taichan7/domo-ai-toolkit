# dev-guide-app — 開発ガイド（App Studio ページ2）

`pl-summary-app`（「Store PL AI Insights」＝店舗別損益 AIインサイト）と **同じ App Studio
DataApp のページ2**に載る、純静的な Domo Pro Code アプリ。VS Code とコーディングエージェント
（Claude Code / Codex / GitHub Copilot 等）で Domo を開発する流れを、**環境準備からデプロイ・
片付けまでステップバイステップ**で辿るハンズオン教材。データセットやワークフローには一切つながず、
縦スクロール1枚の視覚ガイド（図・表・ポンチ絵主体・全10節 §1〜§10）だけを表示する
（データ接続を持たない静的 Pro Code アプリ）。

- design 名: `店舗別損益｜開発ガイド`（manifest 版 **0.3.0**）
- design id: `531a3c0f-bf42-500c-a4ce-87b60c743414`（**保守用 `maintenance-instance` 固有の実 id**・リポジトリに保持）。
  公開ソースには含めない。別インスタンスへ複製する時も `id` を外して採番し直す（下記「publish 方法」「注意」）。
- 種別: Pro Code（純静的・`datasetsMapping` 空＝データに紐づかない）
- 配色: 本体アプリと揃えた臙脂（enji）系。`app.css` の `--brand-primary`（`#7F1D2D`）**1行**から
  全濃淡を `color-mix()` で機械導出する（手で hex を置かない＝ブランド替えは1トークンの差し替えで済む）。
- SDK: `vendor/domo.js`（ryuu.js 4.6.0）同梱（CDN 参照は禁止）。本アプリは Domo API を
  呼ばないが、Pro Code バンドルの標準構成として同梱する。
- 保守・検証インスタンス: `maintenance-instance.domo.com`（**顧客環境ではない**・再利用可能なリファレンス
  デモ）。
- 対象読者: Domo コーディングエージェント開発の初学者（SE／顧客開発者）。

## 構成

| ファイル | 役割 |
|---|---|
| `index.html` | 文書本体（1ページの縦スクロール・全10節 §1〜§10）＝唯一の実行資産 |
| `app.css` | スタイル（臙脂系・`--brand-primary` 1トークンから機械導出） |
| `app.js` | 上部バーのランニングヘッダ（現在の §N）・コピー・トースト・入場アニメの安全網（軽い挙動のみ・Domo API 非呼出） |
| `manifest.json` | Pro Code design 定義（`datasetsMapping` 空＝データ非依存・`id` と `ignore` を保持） |
| `thumbnail.png` | 300×300 サムネイル（publish に必須・`tests/make-thumbnail.mjs` で生成） |
| `vendor/` | 同梱 SDK（`domo.js` = ryuu.js 4.6.0・CDN 非依存・ライセンス同梱） |
| `tests/` | ローカル確認ゲート（Domo 非接続・下記内訳） |

`tests/` の内訳:

| ファイル | 役割 |
|---|---|
| `check.mjs` | 決定的関門（Chrome 不要）: `<use>↔<symbol>`／`data-copy↔id`／`href#↔id`／`aria-labelledby↔id`・版の単一ソース・`#doc`/`#s1`/`#s10` の存在を機械検査 |
| `shoot.mjs` | Chrome headless で**この開発ガイド自身**を実描画 → PNG を目視（メンテナ用の補助） |
| `make-thumbnail.mjs` | `thumbnail.html` を実描画して `thumbnail.png`（300×300）を再生成（macOS/sips 専用） |
| `thumbnail.html` | サムネイルの描画元（版表記を内包＝版の第2ソース。`check.mjs`／`make-thumbnail.mjs` が manifest と一致を検査） |

## publish 方法（配布元メンテナ専用）

> ⚠ **ハンズオン参加者は実行しない。** この `dev-guide-app` の publish は、ライブの本番ガイド
> design（`8b61c346-…`）を上書きする。参加者はコピー＝自分のサンドボックス内でのみ扱い、メンテナの
> ライブ design には触れない（dev-guide §7・§8）。

```bash
cd pl-summary-app/dev-guide-app
domo publish
```

- **初回**：`manifest.json` から `id` を省略して publish（ryuu が新規 design を採番する）。
  メンテナは採番された id を `manifest.json` に書き戻す。
- **更新**：`manifest.json` の `id` はそのまま残して publish（同じ design を更新）。
- **別インスタンスへ複製**：`id` を外して publish＝新規採番（複製先ごとに独立した design になる）。

publish 後、この design を本体 DataApp の**ページ2「開発ガイド」**として埋め込む
（ページ1＝本体カードには一切触れない・冪等）。`pl-summary-app/` 直下から実行する:

```bash
# 本番 DataApp へ（メンテナのみ・本番書込みを明示）
PL_ALLOW_PRODUCTION=1 python3 scripts/provision_domo.py embed-guide
# 自分のサンドボックス DataApp へ（参加者・名札付き）
PL_SANDBOX_SUFFIX="検証・<氏名>" python3 scripts/provision_domo.py embed-guide
```

`embed-guide` は同じ App Studio DataApp に**ページ2＝開発ガイド**を冪等に追加／更新する
（ページ1＝本体カードは触らない・純静的なので context mapping の同期は不要＝カード作成＋レイアウト整形のみ）。
先に `cd dev-guide-app && domo publish` で design を発行していないと（manifest に id が無い、または対象
インスタンスで未公開だと）**明確なエラーで止まる**（門番）。ゼロからのデプロイ正典は
`../docs/setup-guide.md` STEP 7。

## ローカル確認（Domo 非接続・`pl-summary-app/dev-guide-app/` 内で実行）

```bash
node --check app.js            # JS 構文（壊れた JS を publish 前に弾く）
node tests/check.mjs           # 決定的チェック: <use>↔<symbol>・data-copy↔id・href#↔id・版の単一ソース（Chrome 不要）
node tests/shoot.mjs           # Chrome headless で実描画 → PNG を目視（出力先は実行時に表示。--out で変更可）
node tests/make-thumbnail.mjs  # thumbnail.png を再生成（版を bump したら必須・macOS/sips）
```

- `tests/check.mjs` が決定的な関門（空レンダ・壊れた参照・版ドリフトを Chrome 無しで機械検知）。
  `tests/shoot.mjs` は目視補助で、**この開発ガイド自身**を撮る（メンテナ用）。
- 本体 Pro-Code アプリ（`pl-summary-app/pro-code/`）のローカルテストはこれとは別物
  （`tests/test_drill_helpers.js` 等）。親 `README.md` / `docs/setup-guide.md` 参照。

## 版を上げるとき（単一ソース＝手書き4箇所）

版は現状 4 箇所に手書きされる。上げるときは**同時に**更新する:

1. `manifest.json` の `version`
2. `index.html` の colophon（`<dd>v0.2.x（日付）</dd>`）
3. `index.html` の footer（`… ・ v0.2.x`）
4. `tests/thumbnail.html` のフッター（`<span>v0.2.x</span>`）

その後 `node tests/make-thumbnail.mjs` で **thumbnail.png を再生成**する（版を画像へ焼き込むため）。
`make-thumbnail.mjs` は `manifest.json` と `thumbnail.html` の版が食い違うと**描画前に失敗**し、
`node tests/check.mjs` は版が `index.html` に**2回以上**（colophon＋footer）＋ `tests/thumbnail.html` に
**1回**現れ `manifest.json` と一致するかを検査する（ズレたらデプロイ前に落ちる）。現行は全箇所 `v0.3.0`。

## バックエンド隔離（ハンズオン・同一インスタンス相乗り）

ハンズオンは `maintenance-instance.domo.com` を複数人で共有する。環境変数 `PL_SANDBOX_SUFFIX="検証・<氏名>"`
を設定すると、データ層・WF 層・FE の**全オブジェクト名**（seed データストア／コレクション・
AppDB `店舗別損益AI要約`・dedupe CE・保存CE・DataFlow `DF｜店舗別損益データフロー`・4出力
DataSet〔summary/detail/trend/dept〕・統合サブWF・WF-01・App Studio DataApp／カード）に
`（検証・氏名）` が付き、本番や他参加者と衝突しない。未設定（既定）なら名前は一切変えない。
配備は `scripts/provision_domo.py`（データ層: apply/sync-manifest/app-studio/embed-guide/verify）と
`scripts/provision_workflows.py`（WF 層: provision/ce/subflow/mainflow/verify）。本番保護ガードは、
**名札なし**で maintenance-instance の本番オブジェクトを作成／書き換えようとすると**拒否**する（本番メンテナ
のみ `PL_ALLOW_PRODUCTION=1`）。この保護は**全インスタンス**に適用される。顧客の初回検証でも名札を付ける。

## 落とし穴（運用の罠）

- **`cd dev-guide-app` してから `domo publish`。** 親ディレクトリから叩くと ryuu の `findManifest` が
  `*/manifest.json` を拾い、バンドルがツリー全体の構成で出版されてアプリが壊れる（本体 `pro-code/` と同じ罠）。
- **ryuu の 0 バイト化拡張子は `manifest.ignore` で回避。** 未登録 content-type のファイルは live で空になるため、
  `manifest.json` の `ignore` に `vendor/ryuu.js-4.6.0.LICENSE` を入れている（読める版は `.md` 版を同梱）。
  `index.html`／`app.css`／`app.js`／`vendor/domo.js`／`thumbnail.png` は無傷。
- **doc／script／test だけの変更は再 publish 不要。** `tests/` やドキュメントを直しても
  **`index.html` と公開ランタイム資産（css/js/vendor/thumbnail/manifest）が不変**なら、ライブ design は変わらない。

## 注意

- 本番の**開発ガイド design（`8b61c346-…`）を上書きしない**（参加者は自分のサンドボックスで扱う）。
  ページ1＝本体カードにも触れない（`embed-guide` はページ2専用・冪等）。
- 生トークン・SID をコード／コミット／ドキュメントに残さない。
- 公開ソースでは本体・ガイドのdesign IDと接続IDは未設定。対象インスタンスで
  provision・`sync-manifest` を行ってからpublishする。保守用のmanifestを流用しない。

## 関連ドキュメント

- `../docs/setup-guide.md` STEP 7 — 公開＋埋め込みの正典（ゼロからのデプロイ手順）
- `../AGENT.md` — pl-summary-app 全体の引き継ぎノート（重要 ID 一覧・サンドボックス隔離の詳細）
- `../README.md` — 本体アプリの全体像とデプロイ
