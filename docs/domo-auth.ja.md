# Domo 認証とデプロイ

本ワークスペースは Domo の CLI／API ファーストなワークフローを前提とします。ブラウザ自動操作は Domo を操作する既定の手段ではありません。

## 認証の優先順位

次の順で使います:

1. `INSTANCE` + `DOMO_TOKEN`
2. `INSTANCE` + `SID`
3. `domo login`
4. `bash ../scripts/authenticate.sh <instance>`

ヘッダー対応表:

| 方式 | ヘッダー |
|---|---|
| 開発者トークン | `X-DOMO-Developer-Token: $DOMO_TOKEN` |
| CLI SID | `X-Domo-Authentication: $SID` |
| 公開 API OAuth | `Authorization: Bearer $ACCESS_TOKEN` |

## 絶対に保存しないもの

次のものを git に保存しないでください:

- `.env`, `.env.*`
- `.sid`
- `.domo/`
- `*.token`
- `*.pem`, `*.key`
- `sid.txt`
- `access_token.txt`
- リフレッシュトークン
- 開発者トークン
- ワークフロー管理用 PAT
- ダウンロードした publish バンドルや生成された zip ファイル

実行:

```bash
bash ../scripts/check-secrets.sh
```

## Pro Code のデプロイ

デプロイコマンド:

```bash
cd <project>/pro-code
domo publish
```

ルール:

- `domo publish` の前にユーザーの明示的な確認を取る。
- 先に対象インスタンスを確認する。
- `manifest.json` のエイリアスを保持する。
- clone したアプリを publish する前に、古いソースインスタンスの ID を除去または書き換える。
- ビルド生成物を git に publish しない。

## Code Engine とワークフローのシークレット

シークレットは Domo 管理の設定、ワークフローの環境変数、またはユーザー提供の環境変数に置きます。シークレットの値ではなく名前を文書化します。

README には次のように書きます:

```md
必要な環境変数:

- `DOMO_TOKEN` - データセット読み取り権限を持つ Domo 開発者トークン。
- `OPENAI_API_KEY` - Domo のワークフロー／Code Engine シークレットに設定。
```

## Dataflow への書き込み

Magic ETL／dataflow を変更する場合:

1. オブジェクト全体を GET する。
2. メモリ上で変更する。
3. オブジェクト全体を PUT で書き戻す。
4. トリガーまたは実行する。
5. 実行結果を検証する。

破壊的な dataflow の変更は確認なしに行わない。
