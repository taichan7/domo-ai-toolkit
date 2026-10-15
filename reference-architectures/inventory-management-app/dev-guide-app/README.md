# dev-guide-app — 開発ガイド（App Studio ページ2）

`inventory-management-app`（在庫入出庫管理アプリ）と **同じ App Studio DataApp のページ2**に
載る、純静的な Domo Pro Code アプリ。VS Code とコーディングエージェント（Claude Code / Codex /
GitHub Copilot 等）で Domo を開発する流れを、**環境準備からステップバイステップ**で辿るハンズオン
教材。データセットやワークフローには一切つながず、縦スクロール1枚の視覚ガイド（図・表・ポンチ絵主体）
だけを表示する（データ接続を持たない静的 Pro Code アプリ）。

- 種別: Pro Code（純静的・`datasetsMapping` 空）
- 配色: calm-blue（紺青 `#2b569c`）基調。`app.css` の `--brand-primary` 1 行から
  `color-mix()` で全色を導出し、在庫入出庫管理アプリ本体と同じ落ち着いた青系の面にそろえる。
- 絵文字は使わない（線アイコンの `<svg><symbol>` スプライトで表現）。
- SDK: `vendor/`（ryuu.js 4.6.0）同梱（CDN 参照は禁止）。本アプリは Domo API を呼ばないが、
  Pro Code バンドルの標準構成として同梱する。
- 対象読者: 在庫入出庫管理アプリを配布された開発者＝Domo コーディングエージェント開発の初学者。

## 構成

| ファイル | 役割 |
|---|---|
| `index.html` | 文書本体（1ページの縦スクロール・全10節 s1〜s10） |
| `app.css` | スタイル（calm-blue 系・`--brand-primary` から機械導出） |
| `app.js` | 上部バーのランニングヘッダ（現在の §N）・コピー・トースト・入場アニメの安全網（軽い挙動のみ） |
| `manifest.json` | Pro Code design 定義（`datasetsMapping` は空＝純静的・`version` が版の正） |
| `thumbnail.png` | 300×300 サムネイル（publish に必須） |
| `vendor/` | 同梱 SDK（ryuu.js 4.6.0） |
| `tests/check.mjs` | 決定的チェック（Chrome 不要・下記「ローカル確認」） |
| `tests/make-thumbnail.mjs` ＋ `tests/thumbnail.html` | `thumbnail.png` の再生成元（macOS 専用） |

## publish 方法（配布元メンテナ専用）

> ⚠ **ハンズオン参加者は実行しない。** この `dev-guide-app` の publish は、本番のガイド
> design を上書きする。受講者はコピーして読むだけで触らない（§7 の実習対象は在庫入出庫管理アプリ本体のみ）。

`manifest.json` の `id` を**保持したまま** publish すると、同じ design が更新される。この design は
App Studio のページ2「開発ガイド」に埋め込み済みのため、**publish がそのまま画面へ即反映**される
（カードの貼り直しは不要・FOLLOW_LATEST）。

```bash
cd dev-guide-app
domo publish
```

- **更新（同一インスタンス・通常運用）**：`manifest.json` の `id` はそのまま残して publish。
- **初回（別インスタンスへ複製）**：`manifest.json` の `id` を省略して publish すると新規 design が
  採番され、`id` が manifest へ書き戻る。その後 `sync-manifest` で確定 ID を定着させる。
- `tests/` はリポジトリ／配布 ZIP には残すがアプリの実行資産ではない。CLI の MJS 配信が 0 バイトに
  なる実測を踏まえ、publish 物は HTML/CSS/JS/画像・Markdown・SDK の照合可能なファイルに限定する。

publish 後、この design を在庫入出庫管理 DataApp の**ページ2「開発ガイド」**へ埋め込む
（ページ1＝業務アプリ本体には触れない・冪等）:

```bash
# リポジトリ直下から
python3 inventory-management-app/scripts/provision_domo.py app-studio
# dev-guide-app に居るまま実行するなら: python3 ../scripts/provision_domo.py app-studio
```

## ローカル確認（Domo 非接続）

`dev-guide-app` フォルダ内で実行する（上の publish ブロックと同じ場所）:

```bash
node --check app.js            # JS 構文
node tests/check.mjs           # 決定的チェック: <use>↔<symbol>・data-copy↔id・href#↔id・版の単一ソース（Chrome 不要）
node tests/make-thumbnail.mjs  # thumbnail.png を再生成（版を bump したら必須・macOS 専用）
```

`tests/check.mjs` が決定的な関門（空レンダ・壊れた参照・版ドリフトを機械検知）。参照の自己整合に加え、
先頭節 `s1`（事前準備）・中盤節 `s7`（ハンズオン実習）・最終節 `s10`（付録）の存在と、版の単一ソースを検査する。

## 版を上げるとき（単一ソースにする）

版は `manifest.json` の `version` を正とし、次の 3 箇所を**同時に**合わせる:

1. `manifest.json` の `version`（例 `2.1.0`）＝正
2. `index.html` の colophon（`<dt>版</dt><dd>…</dd>`）とフッター ＝ `v` ＋フル版（colophon は日付付き、例 `v2.1.0（2026-10-15）`）
3. `tests/thumbnail.html` のフッター（`<span>v2.1.0</span>`）＝ `v` ＋フル版

その後 `node tests/make-thumbnail.mjs` で **thumbnail.png を再生成**する（版を画像へ焼き込むため）。
`make-thumbnail.mjs` は `manifest.json` と `thumbnail.html` の版が食い違うと失敗し、`node tests/check.mjs` は
index.html（colophon＋フッターの 2 箇所）と `thumbnail.html` に `v`＋`manifest` のフル版が現れるかを検査する（ズレたらデプロイ前に落ちる）。

## 配布方針（重要）

このフォルダはそのまま複数の顧客へ配布する汎用リファレンスです。**顧客固有の社名・URL・個人名・
メールアドレス・生トークン、および固定のホスト名／design ID を、コード・コメント・ドキュメント・
`manifest.json` のプロンプト文に焼き込まない**でください（本番ホストや ID は環境変数・`manifest.json` の
データ欄・`domo-assets.json` が持つ）。

## 注意

- 本番のガイド design（ページ2）は、配布元メンテナ以外は**上書きしない**。業務アプリ本体（ページ1）は別 design。
- 生トークン・SID をコード／コミットに残さない（ユーザー設定領域・`.gitignore` 済みの場所に置く）。
