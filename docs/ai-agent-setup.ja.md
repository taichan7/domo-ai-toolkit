# AI エージェント設定

> English: [ai-agent-setup.md](ai-agent-setup.md)

このリポジトリでは、AI コーディングエージェントが共通のルールを使えるようにしています。最初に `AGENTS.md` を読み、実行は `../scripts/`、エンドポイント詳細は `api-reference.ja.md` を参照します。

## コンテキストファイル

| エージェント / ツール | 渡すもの |
|---|---|
| Codex | `AGENTS.md` |
| Codex Cloud | `AGENTS.md`（自動）。Setup script = `bash ../scripts/cloud-bootstrap.sh`、認証は環境変数（"secret" ではなく env var） |
| Claude Code | `CLAUDE.md` が自動で読み込まれ、`AGENTS.md` へ誘導します |
| Claude Code cloud/web | `CLAUDE.md` → `AGENTS.md`、`.claude/settings.json` の SessionStart hook が bootstrap を実行 |
| Cursor | `AGENTS.md` を添付・メンションするか、codebase を index します |
| Cline / Continue | `AGENTS.md` を project context として添付します |
| Aider | `aider AGENTS.md api-reference.ja.md` |
| 一般的な Web LLM | `AGENTS.md` と `api-reference.ja.md` の必要箇所を貼り付けます |

確認済みDomo MCP serverとclient別設定は [domo-mcp.ja.md](domo-mcp.ja.md) を参照してください。

クラウド/リモート環境（Codex Cloud・Claude Code cloud/web・Codespaces/devcontainer・`@claude`/`@codex` の GitHub bot）では、ローカルのキーチェーンや CLI セッションが使えないため、Domo 認証は環境変数（`INSTANCE` + `DOMO_TOKEN` または `SID`）で渡してください。

## Claude Code

```bash
cd domo-ai-toolkit
claude
```

Claude Code は `CLAUDE.md` を読みます。そのファイルが `AGENTS.md` を読むよう指示します。

エージェント経由で認証します。

```text
bash ../scripts/authenticate.sh your-company.domo.com を実行して認証してください。
```

次に以下を試します。

```text
このインスタンスで row 数が多い dataset を 10 件一覧にしてください。
```

## その他のエージェント

ファイルを読めて shell command を実行できるエージェントには、以下を authoritative context として渡してください。

- `AGENTS.md`
- `api-reference.ja.md`
- `quickstart.ja.md`
- Pro Code アプリ作業では `../templates/pro-code-app/README.md`

## 依頼例

調査:

- "dataset 数を connector type 別に集計してください。"
- "[name] が owner で、90 日以上更新されていない dataset を探してください。"
- "row 数が多い dataset 上位 5 件と schema を出してください。"

診断:

- "失敗中の Magic ETL を error code 別にまとめてください。"
- "dataflow 92 のどこが壊れているか見てください。"
- "この dataflow の last run の失敗原因と修正案を出してください。"

Pro Code:

- "dataset [id] を使った workflow app を作ってください。"
- "`../templates/pro-code-app/` を dataset [id] に bind してください。"

Clone / migrate:

- "`SKILL.md` を読んで、source instance X から target instance Y へこの App Studio app を clone してください。"

## ガードレール

エージェントがブラウザ自動化、endpoint の推測、secrets のファイル書き込みを始めた場合は、こう伝えてください。

```text
AGENTS.md を読み直し、Domo API、認証、安全ルールに従ってください。
```

再利用できる script や pattern を作った場合は、`../scripts/` または `../templates/` に置き、関連する `` または `docs/` を更新します。
