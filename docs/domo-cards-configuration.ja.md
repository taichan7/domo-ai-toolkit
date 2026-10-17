# 標準カードの設定と作成

> English: [domo-cards-configuration.md](domo-cards-configuration.md)

[標準カードのスキル](../skills/domo-cards.md)の詳細資料です。Appの要件を標準カードへ割り当て、
実カードの設定を読み取り、再利用して作成するために使います。

## 根拠と検索

2026-10-17に、指定された5ダッシュボードの標準カード154件を読み取りました。
チャートコードは71種類、実際に保存されていた設定キーは110種類です。
この調査で検証したのは定義の取得と保存済みの構造です。新規保存や描画は検証していません。

[設定カタログ](reference/domo-card-config-catalog.json)では、実機の観察と公開仕様を分けています。

| 項目 | 根拠と用途 |
|---|---|
| `observed_role_signatures`, `observed_override_keys`, 件数・バージョン | 実カードの定義取得 [LIVE]。使用例を選ぶ根拠 |
| `documented_columns` | Phoenix公開資料 [DOC]。マッピング名、必須・任意、書式対応、最大数 |
| `property_refs` → `properties` | Phoenix公開資料 [DOC]。設定名、型、候補値、依存条件、feature、公開されている範囲の既定値・上下限 |
| `observed_keys_missing_from_active_docs` | 実機にはあるが公開資料のactiveな設定にないキー。未知だからと削除しない |

公開資料は `main.a710eb8e.chunk.js` のスナップショットです。71種類に対し6,933件の
チャートと設定の対応、820種類のキー、1,100種類のスキーマ差分を収録しています。
これは6,933設定を実機で試したという意味ではありません。同じキーもチャートごとに
候補値や前提条件が異なります。featureによる利用可否は対象インスタンスで確認します。

特に、Phoenixの入力契約とAnalyzerの投影は同一ではありません。公開資料の
`badge_line_bar` はITEM/VALUE/SERIESを要求しますが、実カード6件はITEMと複数の
数値SERIESを使い、VALUEはありませんでした。実カードの有効な構造を優先してください。

```bash
python3 scripts/domo-card-tools.py catalog --search gantt
python3 scripts/domo-card-tools.py catalog badge_pivot_table --property total
python3 scripts/domo-card-tools.py catalog badge_line_bar --property line_style
```

カタログ全体を毎回読む必要はありません。対象のチャートと設定だけを検索します。
未収録は未調査を意味し、標準カードで実現不可能という判断材料にはなりません。

## 共有されたダッシュボードの調査

既存の認証ヘルパーを使い、同じインスタンスの `INSTANCE` と `DOMO_TOKEN` または
`SID` をexportします。CLIログイン済みの場合は次の手順です。

```bash
bash scripts/authenticate.sh example.domo.com
source scripts/.sid
export INSTANCE SID
python3 scripts/domo-card-tools.py inspect --page https://example.domo.com/page/123
python3 scripts/domo-card-tools.py inspect --card 456
```

`--page` / `--card` は繰り返し指定できます。調査ツールは指定範囲だけを読み、
標準カード以外を除外し、カードIDを重複排除します。失敗は `failures` と終了コードに出ます。
子ページやドリル先は自動的に調査しません。

レポートは構造・件数・設定キーを記録し、タイトル、列名、数式、値、注釈本文は出しません。
カードIDを含むためインスタンス別の調査資料として非公開で扱います。
このレポート自体は作成用のリクエストではありません。実際の完全定義は
`PUT /api/content/v3/cards/kpi/definition` に
`{dynamicText:true,variables:true,urn:"<cardId>"}` を渡して取得します。
このPUTは取得用で、カードを保存しません。CLI refresh tokenをdeveloper tokenとして
扱わず、認証情報や完全なレスポンスをGitへ保存しないでください。

## 設定レイヤーの読み分け

| 場所 | 内容 |
|---|---|
| `definition.charts.main.chartType` | 正確なチャートコード |
| `definition.charts.main.overrides` | 外観・表示設定 |
| `definition.subscriptions.main.columns[]` | 列順、mapping、aggregation、formulaId、書式 |
| `groupBy/orderBy/filters/limit` | クエリの集計・並び・制限 |
| `dateGrain/dateRangeFilter` | 日付の粒度と対象期間。別々の設定 |
| `subscriptions.big_number` | 存在する場合の独立したサマリークエリ |
| `formulas/conditionalFormats/controls` | 計算式、条件付き書式、カードのコントロール |
| `dynamicTitle/annotations/segments/drillpath` | 動的テキスト、注釈、セグメント、ドリル |
| 外側の `columns[]` | データソースの列情報。投影列とは異なる |

v1のメタデータで `inputTable:null` でも完全定義を取得できます。今回の154件は
`chartVersion:12`、定義内の `inputTable:false` で、subscriptionsに列の割り当てがありました。
返された数式一覧には未使用の式も含まれるため、実際のformulaId参照と依存先を調べます。

## マッピングと標準カードの選択

| 要件 | 候補・確認点 |
|---|---|
| 比較・トレンド・複合グラフ | bar/line/area/stacked/100%/running total。系列順、日付、左右軸、通貨と割合 |
| KPI・目標 | single/multi value、filled/radial/face/bullet。filledはCURRENT、bulletはTARGET/RANGEも使用 |
| 明細・集計表 | `badge_basic_table` はMega Table。pivotはROW/COLUMN/VALUE。折返し、合計、条件付き書式も検討 |
| 相関・バブル | modern bubbleのXはXTIME、YはVALUE、サイズはBUBBLESIZE |
| スケジュール | GanttはITEM/START_DATE/END_DATE、calendarはDATE/EVENT |
| 分布・範囲 | box plot、high-low。分布を集計で消してしまわない |
| 地理・構成比 | map、pie/donut、treemap、funnel。地理キー、集計、表示順を確認 |
| 選択UI | slicer、checkbox、dropdown。ITEMとホストページへのフィルター作用を確認 |

Gantt、calendar、pivot、ゲージ、条件付き書式、選択カードが必要という理由だけで
Pro Codeに切り替えず、対応する標準機能と実例を調べてください。

## 調査で確認したプロパティ

実カードの416個の設定値はすべて文字列でした。`"true"` / `"false"`、数値文字列、
`Hide` / `Default` などの表記を維持します。省略、既定、明示falseは同一視しません。

設定にはデータラベル・hover、凡例、軸と対数、線種、予測・回帰、KPI比較、ゲージ閾値、
地図の色・分布・ズーム、表の合計・折返し、pivotの小計などがあります。
正確なキーと値の候補はカタログで対象チャートに絞って検索してください。
`dependencyOption` / `dependencyValue` は前提条件です。`<ANY>` を書込値に使いません。
`overrides:null` は既定表示であり、設定不能を意味しません。

## 定義を再利用して作成・確認する

対象と同じチャートコードで、列構成が近いテンプレートを選びます。
同一インスタンスの独立コピーは `POST /api/content/v1/cards/{id}/copy` です。
深い設定変更や新規作成では、取得結果をそのまま保存せず、
[完全な変換手順](domo-cards-configuration.md#authoring-reuse-a-graph-then-verify-the-saved-result)
および [native KPI recipe](../skills/domo-cross-instance-clone.md#section-11--native-kpi-cards) を参照します。

列・データソース・formula・日付・sort/filter・条件書式・control・動的テキスト・drillの
参照を明示的にマップします。数式や条件書式にはread→writeのラッパー変換が必要です。
`modified` / `allowTableDrill` を保持し、更新対象も新たに読み取ります。
サマリーがないテンプレートへ `big_number` を勝手に追加しません。
注釈やsegmentを空の差分構造へ変換しただけでは、それらの移行を検証したことになりません。

CREATEは `PUT /api/content/v3/cards/kpi?pageId=<id>`、UPDATEは
`PUT /api/content/v3/cards/kpi/<urn>` です。これらは保存処理です。
共有された分析用の元カードを実験対象にせず、作成先・更新対象について現在の認可に従います。
保存後は対象を再取得して割り当てや設定を照合し、データ、描画、サイズ、フィルター、ドリル、
PDPを必要な範囲で検証します。HTTP 200だけで描画成功とは判断しません。

## Appへの配置

App Studioをコンテナにして標準カードを配置し、標準機能で満たせない独自操作や書戻しを
Pro Codeで実装します。カード作成とレイアウト登録は別工程です。
[App Studioスキル](../skills/domo-appstudio.md)と
[標準カードとPro Codeの併用](../skills/domo-procode-embedded-cards.md)を参照してください。

## 一次資料と今後の追加

[Phoenix公式設定資料](https://domoapps.github.io/domo-phoenix/#/properties)と
[チャートコードのenum](https://github.com/DomoApps/domo-phoenix/blob/master/src/enums/phoenix-chart-type.ts)
が公開仕様の根拠です。実カードでの確認、資料上の可能性、保存や描画の確認を分けます。
新しいURLを追加するときは対象件数・取得失敗を記録し、既存コード、役割、設定を比較します。
新しい仕様は依存条件とfeatureも一緒に残し、元カードIDや完全な定義は公開資料へ含めません。
