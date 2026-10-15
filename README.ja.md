# domo-ai-toolkit

> **English version → [README.md](README.md)**

**AI コーディングエージェントと一緒に Domo 開発を進めるための、実戦検証済みツールキット。**

このリポジトリの内容はすべて、実際の Domo インスタンス上で本番アプリを作りながら
開発・検証されたものです。そのノウハウを、AI エージェント（Claude Code、Cursor、
Copilot、Codex などシェルアクセスを持つもの）が読めばすぐに「認証・クエリ・
診断・構築」の方法が分かる形でパッケージしています。

3つの層で構成されています：

| 層 | パス | 内容 |
|---|---|---|
| **スターターキット** | [`docs/`](docs/), [`scripts/`](scripts/), [`templates/`](templates/) | 認証フロー、API リファレンス、実行可能なシェル/Python ヘルパー、Pro Code アプリ雛形 |
| **スキルライブラリ** | [`skills/`](skills/) | 55 件の作業メモ — Domo の各機能面（DataSets、Magic ETL、Workflows、Code Engine、Pro Code、AppDB、App Studio、AI Services 等）＋汎用エージェント作業スキル |
| **リファレンスアーキテクチャ** | [`reference-architectures/`](reference-architectures/) | Pro Code + Code Engine + AppDB + Magic ETL + Workflows + App Studio の接続方法を示す、デプロイ可能な2つの完成アプリ |
| **依頼テンプレート** | [`prompts/`](prompts/) | AI エージェントに実装・レビュー・プロンプト改訂を依頼するときのコピペ用テンプレート |

## 対象読者

- Domo を使っている企業のエンジニア・アナリストで、AI エージェントに自分のインスタンスを操作させたい方
- Pro Code アプリをゼロからではなく雛形から作りたい開発者
- 顧客向けハンズオンやリファレンス実装を準備する SE

シニア開発者である必要はありません。AI ツールとターミナルと Domo ログインがあれば十分です。

## クイックスタート

### Step 1 — Domo CLI をインストール

Domo デベロッパーポータル（`管理 → 開発者 → CLI`）からダウンロードしてください。

### Step 2 — ターミナルから認証

```bash
bash scripts/authenticate.sh your-company.domo.com
```

`Authenticated to your-company.domo.com — SID=...` と表示されれば OK です。

### Step 3 — 最初の API コール

```bash
bash scripts/list-datasets.sh
```

インスタンス内のデータセット一覧が表示されれば、コマンドラインから Domo と
会話できています = シェルアクセスを持つ AI エージェントも同じことができます。

### Step 4 — AI エージェントにこのリポジトリを読ませる

キーファイルは **[AGENTS.md](AGENTS.md)** です。エージェントにこのリポジトリの
作法を伝えます。Claude Code は [CLAUDE.md](CLAUDE.md)（AGENTS.md へのポインタ）を
自動で読みます。あとは頼むだけです：

- 「失敗している Magic ETL を一覧して原因を教えて」→ エージェントが
  `scripts/diagnose-etls.sh` と `skills/domo-magic-etl.md` を使います
- 「データセット X の上に Pro Code アプリを作って」→ `templates/pro-code-app/` から
  `skills/domo-procode-app.md` に沿って構築します
- 「在庫管理リファレンスアプリを自分のインスタンスにデプロイして」→
  `reference-architectures/inventory-management-app/docs/` の手順に従います

## リファレンスアーキテクチャ

本番品質の2アプリ。どちらも自己完結しており、AI エージェントの案内で
自分のインスタンスにデプロイできます：

- **[inventory-management-app](reference-architectures/inventory-management-app/)** —
  在庫入出庫管理：Pro Code UI（PC + Domo Mobile、QR スキャン対応）、Code Engine API、
  AppDB、品目別 AI コメント付き Magic ETL、サーバーサイド起動の AI 通知 Workflow。
- **[pl-summary-app](reference-architectures/pl-summary-app/)** —
  店舗損益 AI 分析：Magic ETL → 親子並列 Workflow（AI エージェント付き）→ AppDB →
  完全自己完結の App Studio カード。

両アプリとも、対象インスタンスのオブジェクト ID を**名前で発見して張り替える**
プロビジョニングスクリプト付き。デプロイ前に ID を手編集する必要はありません。

## FAQ

**Q: 更新はどう追えばよいですか？**
[CHANGELOG.md](CHANGELOG.md) と [Releases](https://github.com/taichan7/domo-ai-toolkit/releases)
を参照してください。バージョン管理されているので、手元のコピーが最新かどうか分かります。

**Q: Domo 公式プロダクトですか？**
いいえ。Domo SE が作ったフィールドキットです。使われている API は Domo プラットフォーム
内部と同じもの＋公開デベロッパー API で、安定していますが、すべてが公開 API として
正式ドキュメント化されているわけではありません。各スキルファイルは主張を
`[DOC]`（ドキュメント済み）・`[REPO]`（コードで検証済み）・`[KB]`（ナレッジベース）・
`[INFER]`（推論）に分類しているので、どこまで信用できるか分かるようになっています。

**Q: 公開 Domo デベロッパー API でも使えますか？**
はい。デベロッパートークンがあれば CLI セッションの代わりに使えます。
ヘッダーの違いは [docs/api-reference.md](docs/api-reference.md) を参照してください。

**Q: リファレンスアプリを本番にデプロイできますか？**
あくまでリファレンスであり、理解しやすさと安全な並行デプロイ（環境変数の「名札」で
全オブジェクトを一意化可能）を優先しています。本番インスタンスに向ける前に
各アプリの README を読んでください。

**Q: 関連プロジェクトは？**
Will West による [domo-ai-starter](https://github.com/Willwwest/domo-ai-starter) は
兄弟プロジェクトの最小構成スターターキットです。より軽量な入り口としておすすめです。

## ライセンス

MIT — [LICENSE](LICENSE) を参照。自由に使い、フォークし、出荷してください。
クレジット表記は歓迎しますが必須ではありません。
