# 検証

このアプリの品質は「実行できる自動テスト」と「`verify` の構造チェック」で担保する。
点数や版番号を本書へ書き写すと陳腐化するため、**実値は常にコマンド出力と `manifest.json` を正**とし、
本書は「何を・どの観点で確かめるか」を示すに留める。

## 自動テスト（ローカル）

`inventory-management-app/` 直下で実行する。

```bash
python3 -m pip install -r tests/requirements.txt
# フロントエンド／SDK契約／Manifest／QR（Node）
node --test tests/test_*.js
# 各Pro Code JSの構文
for f in pro-code/*.js; do node --check "$f"; done
# 業務サービス・DataFlow変換・プロビジョナ（Python）
python3 -m unittest discover -s tests
# 開発ガイド（App Studio ページ2）の静的検査
node dev-guide-app/tests/check.mjs
```

> この5コマンドが**ローカル自動テストの唯一の正本**。README・AGENTS.md・AI再構築ランブックは手順を複製せず本節へリンクする（コマンド列を複数箇所に写すとドリフトし、どれか1つを辿ると `pip install` 抜けで pandas DataFlow テストが黙ってskip・一部JSの構文チェック漏れ・開発ガイド検査の丸ごと欠落が起きる）。

- Node テストは `app.js` / `app.css` / `index.html` / `qr-scanner.js` / `qr-generator.js` /
  `domo-access.js` / `config.js` / `manifest.json` を対象に、Domoランタイム判定・Code Engine
  応答ラッパー展開・フロントが通知Workflowを直接起動しないこと（起動はCode Engineが最新の有効版を
  実行時に解決）・業務UIコントラクト（ステップナビ、マスタCRUDパネル、
  グラフ／履歴ドリル、メニュー内完結、レスポンシブ、WAI-ARIA Tabs、可読性フロア 11px、
  CSSカスタムプロパティ定義漏れ検出）・QR検出とiOSフォールバックを検証する。
- `test_frontend_confirmation.js` は確認を開くだけでは通信しないこと、確定時の単発実行、
  取消・Esc・背景クリック、対象・入力の保持、権限変更、二重クリック、確認部品欠落での停止、
  取消直後の再表示と遅延closeイベントを実行テストで検証する。
- トレンド描画は、不正な日付がHTMLを含んでも要素を生成せず、通常の日付の表示を保つことを
  `test_frontend_guards.js` で検証する。日付formatterの不正値フォールバックは安全な数値とは扱わない。
- Python テストは `MANAGE_MASTER` の UPSERT／物理DELETE（連鎖削除・追記専用台帳の非復活）／
  可逆な `active` 停止、二重登録防止、残高再計算、DataFlow集計（KPI／在庫／トレンド／不足／滞留／
  AIノート）、App Studioプロビジョニング契約を検証する。
- DataFlow変換テストはローカルの pandas を使う。未導入時はskipされるため、全件検証では
  先に `tests/requirements.txt` を導入し、skipがないことを確認する。公開CIも同じ依存を導入する。

## レイアウトハーネス（デプロイ前に必須の目視）

ユニットテストは CSS レイアウトを評価しないため、**FE（CSS/JS/HTML）を触ったら公開前に必ず**、
実ブラウザ（Chrome headless）で各幅を実描画して PNG を目視する。

```bash
node tests/layout/shoot.mjs                 # app（入出庫/ダッシュボード/履歴）＋ devguide を代表幅で
node tests/layout/shoot.mjs --app devguide --widths 1366,390   # ページ2（開発ガイド）だけを限定
node tests/layout/check-confirmations.mjs    # 共通確認の実ブラウザ操作・1366/768/390px・通信はモック
# 出力: /tmp/inv-shots/<app>-<view>-<width>.png（--out で変更可、--height で縦を伸ばす）
```

- 対象は2つの Pro Code アプリ。`app`＝在庫入出庫管理（App Studio ページ1）、`devguide`＝開発ガイド
  （App Studio ページ2の縦スクロール文書）。幅は PC 広/中・タブレット・スマホの
  1680/1366/1024/768/390。
- 生成された PNG を1枚ずつ開いて、崩れ・見切れ・重なり・モバイル幅での可読性を確認する。
- **注意**：スマホ向けの大ボタン化などモバイル・ペルソナはホスト属性 `data-domo-platform="mobile"`
  で切り替わる（幅ではない）。`file://` プレビューにその属性は付かないため、390px の撮影は
  「幅レスポンシブ」の確認であって Domo Mobile ホストのペルソナ確認ではない（実機は
  [mobile-test-guide.md](mobile-test-guide.md)）。

## `verify`（Domo実体の構造チェック）

```bash
python3 scripts/provision_domo.py verify
```

`VERIFY_RESULT` の `ok: true` は、少なくとも次の構造不変条件が満たされたことを意味する
（版番号などの実値は出力と `manifest.json` を参照。ここには具体値を書かない）。

- **版の三者一致**: Pro Code の Manifest 版＝公開 latest 版＝App Studio 実効デザイン版。
- **Code Engine 版の一致**: Manifest が宣言する Code Engine 版＝Domo 上の released 版。
- **通知 Workflow の配線**: Manifest の `modelId`＝Domo 上の通知 Workflow モデル ID、かつ Code Engine
  ソースへ起動先 modelId が焼き込まれている（`codeEngineWorkflowModelEmbedded: true`。版は照合しない）。
  通知 Workflow の**版**はインスタンス依存で動くため `ok` 条件に含めず、宣言版と live 版の乖離は
  非ブロッキング警告（`workflowWarnings`）に可視化するだけ（下記「既知の無害 WARNING」を参照）。
- **Code Engine の表層**: 公開関数は `inventory_api` の1件のみ、`_` 始まりの私有ヘルパーは既定数。
- **AppDB は単一コレクション**: 統合コレクション1つに全レコード種別を格納し、独自同期
  （同期用 Code Engine・Workflow・DataSet 書込み）を持たない。標準同期 DataSet が存在する。
- **App Studio 構造**: outer proxy／inner context の標準2層、静的 layout、standard／compact の
  レイアウトと PAGE_BREAK、`interaction` 既定（未設定＝操作許可）、`hideWrench:true`、
  `editInAppViewer:true`、`FOLLOW_LATEST`。
- **App Studio ページ2（開発ガイド・登録時のみ）**: `domo-assets.json` に `appStudio.page2`
  が在るときだけ、ページ2のカード存在と `FOLLOW_LATEST` を確認する（未デプロイ環境では素通り）。
  ページ2は自己フィットの縦スクロール文書のため layout 寸法には過剰適合しない。

### 既知の無害 WARNING（`ok` を落とさない）

- `workflowWarnings` の「workflow released v… but manifest declares v…」 — 通知 Workflow の released 版が
  Manifest 宣言版と食い違うときに出る想定内メッセージ。通知 Workflow の版はインスタンス依存で動く
  （新規インスタンスは seed の 1.0.0 から実 DataSet／実 sendEmail 版へ接地するため 1.0.1 以降へ作り直され、
  `sync-manifest` は版欄を書き戻さない）ため、一致しないのが正常。`manifest.json` の
  `workflowsMapping[0].version` を手で書き換えたり再 publish したりしない（配布リファレンスへインスタンス
  固有値を焼き込まないため）。
- `workflowRuntimeMatchesDeclared: false` — 直近に実際に起動された版と Manifest 宣言版の乖離を示す
  非ゲートの監視項目。通知 Workflow の版はインスタンス依存で動くため一致しないのが正常
  （下記「Workflow版解決」を参照）。
- `appStudioLayoutDynamic: false` — 静的 layout は意図した設計（モバイルの青枠・スクロール
  ロック抑制のため）。

## Workflow版解決（Code Engineが最新の有効版を実行時に解決）

通知Workflowの起動はCode Engine（`inventory_api` の REGISTER／NOTIFY_NOW）がサーバー側で行う。CE は
モデルの有効（release 済み）な最新版を実行時に解決し、`api/workflow/v1/instances/message`
（`messageName`＝開始タイルのタイトル、`modelId`＋`version` を明示）で開始する。起動される版は
かつてのようにカードの配線（埋め込み時点のトリガースナップショット）に依存しないため、
**Workflow を改版・release するだけで最新版が使われ、カードの再配線・再埋め込みは不要**である。

配備の要点: `apply` が通知Workflowモデルの modelId をCode Engineのソースへ焼き込む
（`__WORKFLOW_MODEL_ID__` プレースホルダを実IDへ置換）。`verify` はこれを
`codeEngineWorkflowModelEmbedded` として `ok` 条件に含めるため、旧CEのままの配備・`--skip-workflow`
での配備漏れは検出される。Workflow の版そのもの（`workflowVersion`／`workflowLastRunVersion`）は
インスタンス依存のため `ok` に含めず、`workflowWarnings` に可視化するだけに留める。

起動結果は同じ `ALERT_HISTORY` 行へ `STARTED`（＋`workflow_instance_id`）／`FAILED`（＋理由）として
確定する。`NOTIFICATION_STATUS` は監査用の互換入口として残るが、通常の画面導線は呼ばない。

## 実機・手作業（自動化対象外）

自動実行環境からはネイティブ WebView を遠隔操作できないため、次は実機で確認する。

- iOS / Android の Domo Mobile でのレイアウト、カメラ、ライブ QR、権限、通信エラー、入出庫登録。
- 明示したテスト宛先での3タイル Workflow 起動と、AI 出力・メール送信の成否。

手順と結果の記録は [mobile-test-guide.md](mobile-test-guide.md) に従う。
