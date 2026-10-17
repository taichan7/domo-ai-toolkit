# クイックスタート - 15 分で Domo データを確認し AI エージェントに渡す

> English: [quickstart.md](quickstart.md)

このガイドでは、本リポジトリを使って自分の Domo データに手を動かして触れます。読み終わるころには以下を達成できます:

1. ターミナルから Domo インスタンスへの認証
2. データセットの一覧表示と SQL クエリ実行
3. 失敗中の Magic ETL dataflow の診断
4. 同じ作業を自然な日本語で AI エージェントに依頼

最初の Pro Code アプリづくりは次の一歩です — 末尾の **次のステップ** を参照してください。

---

## 必要なもの

- インスタンスにログインできる Domo アカウント
- ターミナル (macOS の Terminal、Windows の PowerShell または Git Bash、Linux の任意のシェル)
- Node.js (Domo CLI 用)
- Python 3 (helper script 用)
- **Domo CLI** にログイン済みであるか、管理画面から取得した **Developer Token** のいずれか

---

## ステップ 1 — Domo CLI をインストール (初回のみ)

```bash
npm install -g ryuu
```

ログイン:

```bash
domo login
```

ブラウザウィンドウが開きます。インスタンスを選択し、サインインして CLI を承認してください。CLI はリフレッシュトークンをローカルに保存するため、このインスタンスに対して再度ログインする必要はありません。

確認:

```bash
domo whoami
```

インスタンスとユーザー情報が表示されれば成功です。

---

## ステップ 2 — リポジトリのスクリプトで認証

```bash
cd domo-ai-toolkit
bash scripts/authenticate.sh your-company.domo.com
```

(`your-company.domo.com` は実際のインスタンスドメインに置き換えてください。)

指定したインスタンスで認証成功と表示されれば準備完了です。スクリプトは所有者のみが読める、Git 管理外の `../scripts/.sid` ファイルを保存し、他のスクリプトが自動的に読み込みます。認証情報（SID）は画面に表示しません。SID や認証ヘッダーをコピー・共有しないでください。

---

## ステップ 3 — データセットの一覧表示

```bash
bash scripts/list-datasets.sh
```

インスタンス内の最初の 50 件のデータセットが ID、名前、タイプ、行数、所有者とともに表示されます。さらに多くを取得するには件数を渡してください:

```bash
bash scripts/list-datasets.sh 200   # 50 件ずつのページングで最初の 200 件を取得
```

---

## ステップ 4 — データセットに対して SQL を実行

上記の一覧から任意のデータセット ID を選択し、以下を実行します:

```bash
bash scripts/query-dataset.sh <dataset-id> "SELECT * FROM table LIMIT 5"
```

テーブル名は常に `table` です — データセット自身を指します。標準的な SQL がそのまま使えます:

```bash
bash scripts/query-dataset.sh <id> "SELECT COUNT(*) FROM table"
bash scripts/query-dataset.sh <id> "SELECT * FROM table WHERE status = 'open' LIMIT 10"
bash scripts/query-dataset.sh <id> "SELECT \`Column Name\` FROM table LIMIT 5"
```

`LIMIT 0` を使うと列情報のみを取得できます (スキーマの確認に便利):

```bash
bash scripts/query-dataset.sh <id> "SELECT * FROM table LIMIT 0"
```

---

## ステップ 5 — 失敗した ETL の診断

```bash
bash scripts/diagnose-etls.sh
```

直近の実行に失敗した Magic ETL データフローをエラーコードごとにグループ化して一覧表示します。特定の失敗を掘り下げるには:

```bash
bash scripts/diagnose-etls.sh <flow-id>
```

失敗したタイル、関連する式や結合キー、返されたエラーコードが表示されます。コードを `api-reference.ja.md` の表と照らし合わせて推奨される修正方法を確認してください。

---

## ステップ 6 — すべてを AI エージェントに任せる

リポジトリを Claude Code、Codex、Cursor などの AI コーディングエージェントで開いてください。エージェントは最初に `AGENTS.md` を読む前提です。Claude Code は `CLAUDE.md` から始まり、そこから `AGENTS.md` に誘導されます。

例えばこう尋ねてみてください:

> 「私のインスタンスで行数が多い順にデータセット 10 件を表示してください。」

> 「失敗中の Magic ETL をすべて検出し、エラーコードでグループ化してください。」

> 「データフロー 92 を確認してください — 何が壊れていて、どう修正すべきですか?」

エージェントは今学んだスクリプトとパターンを内部で使います。違いは、それらを連鎖させ、結果を要約し、得られた情報をもとに次のクエリを書ける点です。

詳細なエージェント設定は `ai-agent-setup.ja.md` を参照してください。

---

## よくある問題

**`domo: command not found`**
CLI はインストールされていますが PATH に含まれていません。macOS / Linux ではターミナルを再起動してください。Windows では PowerShell を再起動してください。

**`ERROR: no ryuu config for X found`**
そのインスタンスに対して `domo login` を実行していません。実行して正しいインスタンスを選択してください。

**認証は成功するが list-datasets で何も表示されない**
アカウントがこのインスタンスのどのデータセットにも読み取り権限を持っていない可能性があります。Domo 管理者に確認してください。

**実行中に `401 Unauthorized`**
SID の有効期限 (約 1 時間) が切れています。`bash scripts/authenticate.sh <instance>` を再実行してください。

**SQL クエリで列が返らない**
SQL が有効か確認してください — まず Domo の Analyzer で試してみてください。スペースを含む列名はクォートではなくバッククォート (`` `Column Name` ``) で囲む必要があります。

---

## 次のステップ

- 完全なエンドポイント一覧とパターンは `api-reference.ja.md`
- `../templates/pro-code-app/` に動作する Pro Code アプリの雛形があります。これをベースに構築できます
- AI エージェントを本リポジトリ向けに設定するには `ai-agent-setup.ja.md`
