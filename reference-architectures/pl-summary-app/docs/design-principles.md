# 設計原則（店舗別損益AIインサイト）

姉妹アプリ（在庫入出庫管理）の `docs/design-principles.md` と同じ骨組みで、本アプリの**既存の**設計判断と原則を記述する。構造の詳細は [architecture.md](architecture.md)、データの詳細は [data-model.md](data-model.md)、資産の棚卸しは [domo-assets.md](domo-assets.md) を正とし、本書は重複を避けて「なぜこの形か」に絞る。

## 優先順位

1. Domo 内で完結する（表示直読と保存 CE 経由の書込みに閉じ、外部 AI・外部メール送信サービスへ画像や明細を出さない）。
2. SSO だけで 1 周できる。データ層の配備・`domo publish`・App Studio 埋め込みは `domo login`（SSO）で動き、開発者トークンは AI 長文レポートのワークフロー層だけに要る任意とする。
3. 受講者が各 Domo 機能（Pro Code / Code Engine / Workflow / DataFlow / AppDB / App Studio）の責務を追える。
4. 参照アセット数を小さく保つ（公開 Code Engine 関数は 1 本、出力 DataSet は 4 本）。
5. テストしやすく、障害時に正データ（DataFlow 出力・AppDB）から回復できる。

## レイヤー

| レイヤー | ファイル／Domo機能 | 責務 |
|---|---|---|
| Presentation | `index.html`, `app.css`, `app.js` | 表示、店舗/全社切替、タブ、ドリル、手描き SVG チャート |
| Workflow trigger | `workflow-run.js` | AI 長文レポート更新の起動と進捗ポーリング（実行は確認ダイアログの後） |
| Domo access | `vendor/domo.js`（ryuu SDK・同梱） | Manifest エイリアス、App Framework proxy、Code Engine 実行 |
| Application / Domain | Code Engine `pl_report_api` | 操作のディスパッチ、レポートの保存・取得、業務ルール |
| Operational data | AppDB コレクション「店舗別損益AI要約」 | AI 長文レポート（`analysis_html`）の正本 |
| Analytical data | DataFlow、出力 DataSet 4 本 | 損益の集計形式（summary / detail / trend / dept） |
| Composition | App Studio | Domo 内の配置、業務利用者が開ける URL |

上位レイヤーは下位の物理 ID を持たず、Manifest エイリアスまたはサーバー内設定を使う。経路図と依存方向は [architecture.md](architecture.md) を参照。

## 公開関数を1つにした理由

Pro Code が呼ぶ Code Engine の物理関数を操作ごとに増やすと、Manifest Wiring・バージョン・ハンズオンの説明が増える。公開契約は `operation + request` の 1 関数（`pl_report_api`）に限定し、私有ヘルパはファクトリ `_service` の中へネストして top-level の `def` を 2 つ（`_service` と `pl_report_api`）だけに保つ（`_` 始まりは Domo が version 作成時に Manifest の `functions[]` から除く）。設計判断の全文は [architecture.md](architecture.md)（「設計判断 ＞ 公開関数を1つにした理由」）を正とする。

## Code Engineの入出力型

公開（persist）する関数は `pl_report_api` の 1 つだけで、入出力型を明示する。

| 変数 | 種別 | 型 | 省略 |
|---|---|---|---|
| `operation` | 入力 | text | 可（既定 `"save"`） |
| `request` | 入力 | object | 可（既定 `null`） |
| `result` | 出力 | object | 可 |

エディタで公開契約を確認・実演するときは `pl_report_api` を選ぶ。ここだけが型付き契約を持つ。

## 型とスキーマ

- 出力 DataSet の列・会計レベル・状態ラベルは [data-model.md](data-model.md) を正とする。
- 日時は UTC で保存し、UI だけがローカル表示する。桁区切り・数字形は `toLocaleString("ja-JP")` で閲覧者ロケール非依存に固定する。
- AI 長文レポートは AppDB の `analysis_html`（1 レポート 1 文書）に保存し、閲覧者は App Framework proxy で直読する。
- 使わない列が空になることはリファレンス構成の意図的な代償とする。

## エラー設計

Code Engine は成功時に `ok: true`、業務エラー時に次の形を返す。

```json
{ "ok": false, "error": { "code": "...", "message": "日本語UIメッセージ", "details": {} } }
```

`code` は制御、`message` は日本語 UI、`details` は安全な追加情報のみに使う。予期しない例外はログに記録し、ユーザーにスタックや認証情報（実行者メール等の実行時 PII）を返さない。

## レポートの保存と鮮度

- 保存は「作成してから同一 `doc_key` の古い版だけを削除する」順序とし、保存成功を「重複を生む再試行」に化けさせない（不変契約）。全社レポートは予約識別子 `store_id="ALL"` を使い店舗 ID と衝突させない。
- AI 長文レポートは手動更新のみ（定期実行しない）。鮮度は DataFlow が全社出力に発行する生成日時列と各レポートの `generated_at` で示し、閲覧者が metadata を読めなくても画面に生成時刻を出せるようにする。
- 取り消し操作は CE / Workflow を呼ばない（確認ダイアログで「はい」を押したときだけ課金ジョブが走る）。

## UI設計

- 色・余白・フォント・角丸・影・状態色は `app.css` の CSS カスタムプロパティに集約する。ブランド色（臙脂 `--accent #7F1D2D`／セージ `--profit #4C6552` 他）は JS 側の単一の真実源 `BRAND` と対応させ、CSS リテラルには「== JS BRAND.xxx」ミラーコメントを付けて手動同期対象を明示する。
- MUJI 的なミニマルを指針とする。ベースは暖かいオフホワイト（`--bg #F5F4F2`）、文字は濃いインク、損益の正負は臙脂（売上・赤字）と抑えたセージ（純利益・黒字）で表す。グラデーションは使わない。特定顧客のブランド色や CSS は複製しない。
- 日本語フォントは `Noto Sans JP` を先頭に、OS 標準フォントへフォールバックする**代替指定つきのスタック**で、外部 CDN を実行時に読まない（オフライン／社内 NW／CDN 障害でも壊れない）。チャートも外部ライブラリに頼らず手描き SVG で描く。配布物を自己完結に保つ（CDN 非依存）。
- 状態は色だけに頼らない。折れ線は破線パターン＋終端マーカー形状＋線キー凡例で系列を区別し（WCAG 1.4.1）、黒字/赤字はドット凡例でも示す。本文テキストは可読性のため 11px を下限とする。
- アクセシビリティを基本装備とする。動的生成する表は `<caption>` と `scope` を持ち、SVG チャートは `role="group"＋aria-labelledby`（内側ドリルボタンを AT に残すため `role="img"` は使わない）、読み込み/選択失敗は `role="alert"` で読み上げ、`prefers-reduced-motion` を尊重する。見出しは `<header>`/`<main>` のランドマークと skip-link で辿れる。
- 概要／事業部別／サマリーの 3 タブ構成。事業部別は全社ビュー限定で、店舗選択時は**隠さず理由付きで無効化**してレイアウトを保つ。ドリルは各カード内で完結させ、強制遷移させない。
- 通信中はローディング表示と二重送信防止を使い、失敗後に再試行できる。

## ビジュアル資産

`pro-code/thumbnail.png` は外部画像を使わず独自に生成する。ヘッダーのブランドマークは、inventory-management-app と同じく**ニュートラルな単線インライン SVG**（`#icon-brand`）を enji（`--accent`）で塗った差し替え前提のプレースホルダで、実在顧客の名称・ロゴ・配色ではない（架空のサンプル小売ブランド名やラスター `logo.png` は廃止＝採用者が自社ロゴへ差し替えやすく、ラスターの誤認やパレット非追従も避ける）。画面に表示されるのはアプリ名「店舗別損益 AIインサイト／Store P/L AI Insights」のみ。CSS・文言・ロゴは外部サイトから複製していない。

## 採用しなかった設計

| 設計 | 不採用の理由 |
|---|---|
| 操作ごとの複数公開 Code Engine 関数 | Wiring とバージョン管理が増えるため、1 本のディスパッチャに集約 |
| 画像や明細を送る外部 AI・外部メール送信サービス | Domo 内完結とデータ境界に反する。AI 長文はサーバー側 Workflow で生成し、通知は実行者宛てに閉じる |
| レポートの多重保存（古い版を残す） | 同一 `doc_key` の重複で「どれが最新か」が崩れる。保存は作成→古い版削除の順にする |
| チャート描画の外部ライブラリ／フォント CDN | 配布物の自己完結（CDN 非依存）に反する。手描き SVG とローカル／OS フォントで賄う |
| 系列を色だけで区別する折れ線 | 色覚特性・白黒印刷で判別不能。破線・終端形状・線キーの第2チャネルを足す |

## 過剰設計を避ける基準

新しい AppDB コレクション、出力 DataSet、Code Engine 公開関数、DataFlow 中間出力を追加する前に、次のいずれかを満たすかを問う。

- 権限や保持期間が現行データと異なる。
- スキーマ変更頻度またはデータ量が現行資産を圧迫する。
- 独立した再利用契約または障害境界が必要である。
- 追加しないと責務が混在し、テストや回復が困難になる。

単に説明しやすそう、または将来使うかもしれないという理由だけでは追加しない。不変契約の要約は [AGENTS.md](../AGENTS.md) を正とする。
