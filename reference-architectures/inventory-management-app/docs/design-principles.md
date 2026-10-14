# 設計原則

## 優先順位

1. Domo内で完結する。
2. AppDBからDataSetはDomo標準同期だけを使う。
3. 受講者が各Domo機能の責務を追える。
4. 参照アセット数を小さく保つ。
5. テストしやすく、障害時に正データから回復できる。

## レイヤー

| レイヤー | ファイル／Domo機能 | 責務 |
|---|---|---|
| Presentation | `index.html`, `app.css`, `app.js` | 表示、入力、ナビゲーション |
| Device adapter | `qr-scanner.js` | カメラ、写真選択、QR検出・形式判定、手入力 |
| Domo access | `domo-access.js` | Manifestエイリアス、Code Engine実行ラッパー展開、Domo API応答、ローカルデモ |
| Application / Domain | Code Engine `inventory_api` | 操作のディスパッチ、業務ルール、権限、冪等性 |
| Operational data | AppDB | 取引正本、投影、マスタ、監査イベント |
| Analytical data | 標準同期DataSet、DataFlow、出力DataSet | 分析形式と集計 |
| Composition | App Studio | Domo内の配置、モバイル起動 |

上位レイヤーは下位の物理IDを持たず、Manifestエイリアスまたはサーバー内設定を使う。

## 公開関数を1つにした理由

Pro Codeが呼ぶCode Engineの物理関数を操作ごとに増やすと、Manifest Wiring、バージョン、ハンズオンの説明が増える。公開契約は `operation + request_json` の1関数に限定した。

私有ヘルパは責務ごとに絞り、いずれも下記のファクトリ `_service` の中にネストして定義する。`_is_true` は真偽正規化、`_resolve_recipient_email` は在庫通知の宛先メール解決、`_records` はAppDB操作（追加・参照・更新・物理削除の全CRUD）、`_register` は取引登録、`_notify_now` は手動通知イベント作成、`_admin` は管理者専用の入口として再計算・デモ投入に加えマスタ（品目・ロケーション・基準在庫）のCRUDと物理削除（依存の連鎖削除・台帳保持）までを1つに集約する。認証と状態取得は短い処理として公開dispatcher内に置き、端末だけで完結するQR画像・形式解析はCode Engineへ持ち込まない。

## Code Engineの入出力型

このパッケージが公開（persist）する関数は `inventory_api` の1つだけで、入出力型を明示している。

| 変数 | 種別 | 型 | 省略 |
|---|---|---|---|
| `operation` | 入力 | text | 不可 |
| `request_json` | 入力 | text | 可（既定 `"{}"`） |
| `result` | 出力 | object | 可 |

私有ヘルパは全て引数なしのファクトリ `_service()` の中へネストして定義し、top-level の `def` を `_service` と `inventory_api` の**2つだけ**に保つ。`_service` は「名前→関数」の dict を返し、公開 `inventory_api` は `svc = _service()` で受けて `svc["register"]` のように名前で辿る。ヘルパ同士はクロージャスコープ内で素の名前のまま呼び合う。

- 公開面は `inventory_api` の1関数に限定し続ける（`_` 始まりはDomoが命名規約で自動 private 化し、version作成時にManifestの `functions[]` から除かれる。GETは `inventory_api` 1件のみ返す）。
- ヘルパは素直な良分割のPythonのまま `_service` 内に保つ。
- エディタで公開契約を確認・実演するときは `inventory_api` を選ぶ。ここだけが `operation`／`request_json`／`result` の型付き契約を持つ。

## 型とスキーマ

- AppDBの物理型は `appdb/schemas.json` を正とする。
- DataSetの境界は `datasets/contracts.json` に記録する。
- 日時はUTC ISO 8601で保存し、UIだけがローカル表示する。
- 統合コレクションのboolean表現は標準同期のwide schemaで安定して扱えるよう `true` / `false` 文字列も許容する。
- 使用しない列が空になることはリファレンス構成の意図的な代償とする。
- Code Engineの公開レスポンスはAppDBの内部フィールド（`_document_id` などアンダースコア始まり）を含めない。`find`/`query` は更新・物理削除のため内部IDを付けて返すが、FEへ渡す返り値（`LIST_MASTERS`／`GET_STATE`／重複リプレイの `transaction` など）では取り除く。専用のヘルパ関数は足さず（公開1＋私有6の面を崩さないため）、各返却点で同じ内包表記を使う。

## エラー設計

Code Engineは成功時に `ok: true`、業務エラー時に次の形を返す。

```json
{
  "ok": false,
  "error": {
    "code": "NEGATIVE_INVENTORY",
    "message": "在庫数を超える出庫は登録できません。",
    "details": {}
  }
}
```

`code` は制御、`message` は日本語UI、`details` は安全な追加情報のみに使う。予期しない例外はログに記録するが、ユーザーにスタックや認証情報を返さない。

## 台帳と訂正

- 取引（`TRANSACTION`）は追記型の正本とし、登録済みの行は書き換えない。残高（`BALANCE`）は取引を畳み込んだ投影であり、`RECALCULATE` はいつでも取引正本から再構築できる。
- 取引種別は入庫（`IN`）と出庫（`OUT`）の2つだけとし、在庫の増減はこの2種別で説明する。リファレンスアーキテクチャとして仕組みを分かりやすく保つため、調整・棚卸のような追加種別は持たない。
- マスタの物理削除（`DELETE_ITEM`／`DELETE_LOCATION`／`DELETE_RULE`）は本体と派生状態（残高の基準在庫・不足数・不足フラグ、アラート状態）を消すが、追記型の取引・通知履歴は監査証跡として残す。したがって同じコードでマスタを作り直すと、白紙ではなく残っていた台帳・現在庫を再び引き継ぐ（削除は不可逆で、復元導線は持たない）。この境界を「削除して作り直せば履歴が消える」と誤解しないこと。
- ルールの新設・編集・停止（`UPSERT_RULE`）は、対になる残高の派生値（基準在庫・不足数・不足フラグ）と対応するアラート状態を即時に再投影する。次の取引や `RECALCULATE` を待たずに、古いしきい値のまま通知・ダッシュボードが判断する「据え置き幽霊」を作らないため。現在庫そのものは取引正本由来なので保持する。

## UI設計

- 色、余白、フォント、角丸、影、状態色は `app.css` のCSSカスタムプロパティに集約する。
- 情報密度は高くとも詰め込みすぎない、落ち着いた日本語タイポグラフィ、抑制された面表現、業務状態の明快な可視化を指針とする。特定アプリのブランド色やCSSは複製しない。
- 日本語フォントは `Noto Sans JP`, `Meiryo UI`, Meiryo, `Hiragino Sans`, `Zen Kaku Gothic New` の順で端末フォントを使う。
- ベースは白と暖かいライトグレー、文字は濃いスレート、操作アクセントは彩度を抑えた青緑とする。グラデーションは使わない。
- 通常面は6〜8pxの角丸、1pxの罫線、1〜2px相当の浅い影に留める。浮上感はモーダルと通知だけに使う。
- ナビゲーション、更新、QR、検索、管理操作は同一ストロークの線画SVGを使い、絵文字やフォント依存記号を使わない。
- 操作パネルは内容の高さで止め、現在の選択パネルだけをデスクトップで追従させる。不要な空白を作らず、入力対象と現在状態を並べて確認できるようにする。
- 状態は色だけでなく、文字、バッジ、アイコンで示す。
- 本文テキストは可読性のため 11px を下限とし、極小フォントを使わない。寸法・色・フォントは `app.css` のカスタムプロパティに集約する。
- アクセシビリティを基本装備とする。動的生成する表は見出しセルに `scope="col"` を付け、件数や同期状態などの更新は `aria-live` で通知し、アイコンだけのボタンには `aria-label`、キーボード操作にはフォーカスリングを与える。
- モバイルでは場所 → 品目 → 数量 → 確認の4ステップに限定する。
- UI候補（場所・品目）は先頭30件までに制限する。AppDB・ダッシュボードの読み込みは上限付きの単一リクエストで取得し、独自のページング機構は持たない。
- 通信中はオーバーレイと二重送信防止を使い、失敗後に再試行できる。
- ダッシュボードはホバー／フォーカスで内訳を示す。ドリルダウン明細は各メニュー内で完結させ、履歴タブへ強制遷移させない。履歴ビューでは一覧の右側の詳細ペイン（`#detail-pane`）へ、ダッシュボード・入出庫では本文先頭のインライン詳細カード（`#context-detail`）へ描く。履歴条件があるときだけ「履歴で詳しく見る」導線を添えるが、遷移はユーザー操作に委ね強制しない（モーダル／スライダー／ドロワーは使わない）。
- Domo MobileではApp Studioカードを`fitToFrame: false`とし、カード操作は既定（`interaction`未設定＝操作許可、`editInAppViewer: true`）に戻す。`interaction: DISABLED`はモバイルの青い選択枠を消す一方でPCのクリックも殺すため採用しない（2.4.22で試行→2.4.23で撤回）。Pro Codeはiframeを実ビューポート（`100dvh`）へ固定し、`main`だけを明示的な縦スクロール領域にする。タップ時にDomo Mobileが描く青い選択枠は、`interaction`ではなく静的layout（`isDynamic: false`）＋終端PAGE_BREAK＋WebKitのタップハイライト無効化（`-webkit-tap-highlight-color`／`-webkit-touch-callout`）で抑える。JavaScriptの`visualViewport`値はソフトウェアキーボード・回転時のモーダル最大高の算出にだけ使う。

## ビジュアル資産

`pro-code/thumbnail.png` はブランドや外部画像を使わず、箱、QR、入出庫矢印を組み合わせた独自ビットマップとして生成した。生成プロンプトの要旨:

> Square Domo inventory management app thumbnail, clean enterprise flat illustration, white background, navy and teal palette with a small orange accent, warehouse box, QR symbol, inbound and outbound arrows, no text, no logo, high contrast at 300 by 300 pixels.

画面のCSS・文言・ロゴは外部サイトから複製していない。

## 採用しなかった設計

| 設計 | 不採用の理由 |
|---|---|
| 7つのAppDBコレクション | 7つの標準同期DataSetとDataFlow入力が必要になり、リファレンスとして過大 |
| 操作ごとの複数公開Code Engine関数 | Wiringとバージョン管理が増えるため、ディスパッチャに集約 |
| AppDBからDataSetへの独自同期 | Domo標準同期と責務が重複し、二重書込みの危険がある |
| 画像を送信する外部QR解析API・外部AI・メールサービス | Domo内完結とデータ境界に反する。QRはversion／SRI固定のクライアントライブラリで端末内解析する |
| Workflow内へ通知記録用タイルを追加 | タイルを増やさず、既存`ALERT_HISTORY`をCode Engineの同じ公開ディスパッチャで更新する |
| 取引履歴の直接編集（登録済み行の上書き） | 残高投影とズレて台帳整合性が壊れる。取引は追記型の正本として書き換えない |

## 過剰設計を避ける基準

新しいAppDBコレクション、DataSet、Code Engine公開関数、DataFlow中間出力を追加する前に、次のいずれかを満たすかを問う。

- 権限や保持期間が現行データと異なる。
- スキーマ変更頻度またはデータ量が現行資産を圧迫する。
- 独立した再利用契約または障害境界が必要である。
- 追加しないと責務が混在し、テストや回復が困難になる。

単に説明しやすそう、または将来使うかもしれないという理由だけでは追加しない。
