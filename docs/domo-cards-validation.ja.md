# 標準カードの実機検証・ドリルパス・App Studio

> English: [domo-cards-validation.md](domo-cards-validation.md)

カード作成、保存後の表示不良、クリックによるドリルダウンを扱うときの詳細資料です。
[設定と作成](domo-cards-configuration.ja.md)および
[App Studio](../skills/domo-appstudio.md)と合わせて使います。コード例のIDはプレースホルダーです。

## 根拠と完了条件

2026-10-17、指定された1つのデータセットを使い、対象Appに**35枚・最終31種類の標準カード**と
2段のドリルビューを作成しました。全35枚でDomo側のPNG描画とクエリ結果を確認しました。
当初32種類目だった旧形式の `badge_heatmap_table` は保存・データ取得に成功しても描画が400になり、
参照元でも同じ結果だったため、条件付き書式を持つ標準のMega Tableへ置き換えました。
これは今回のレンダラーの検証結果で、全バージョンの画面で利用不能という意味ではありません。

検証したのは、保存定義、データセット参照、独立したSQLとの集計照合、ネイティブ画像、
ドリルの順序・親子関係・条件付き結果、App設定の再取得、1タブ構成、2種類のレイアウトです。
**ブラウザでのクリック操作とApp全体のスクリーンショットは未検証**です。

1. 保存後の定義で、種類・mapping・集計・数式・プロパティを確認します。
2. データを独立したSQLや既知の件数と照合します。
3. ネイティブ画像を生成し、HTTP成功だけでなく描かれた値・軸・ラベルを確認します。
4. ページ所属、レイアウトへの登録、interactionは別々に確認します。
5. ブラウザ検証が認可され利用できる場合は、フィルター、ドリル、戻る、幅変更、compact表示を操作します。
   実施できていない項目を完了扱いにしません。

## ネイティブ描画で動作したリクエスト

```http
PUT /api/content/v1/cards/kpi/<card-urn>/render?parts=image,queryResult
Content-Type: application/json

{"width":900,"height":600}
```

SID認証、数値のカードID、`dr:<view-id>:<root-card-id>` 形式のドリルURNで動作しました。
今回のインスタンスでは**widthとheightの両方**が必要でした。
widthのみ、heightのみ、寸法を含まない公開例はいずれも400でした。

```json
{
  "image":{"data":"<base64 PNG>","notAllDataShown":false},
  "queryResult":{
    "type":"ordered-column-list","limited":false,
    "data":{"datasource":"<dataset-id>","rows":[],"numRows":0,"metadata":[]}
  },
  "limited":false,"notAllDataShown":false
}
```

位置依存の配列ではなく、名前付きのpartでした。base64をデコードするのは `image.data` です。
クエリ結果は構造化データです。データセット、件数、型、各limitフラグを確認します。
フラグがfalseでも、保存した `limit` による打切りや表の表示領域まで保証されるわけではありません。

```bash
python3 scripts/domo-card-tools.py verify --instance example.domo.com --card 123 \
  --width 900 --height 600 --expected-dataset '<dataset-id>'
python3 scripts/domo-card-tools.py verify --instance example.domo.com --card dr:456:123
```

このコマンドは定義と描画結果を読み、行の値を含めず構造だけを出力します。保存・コピー・削除はしません。
集計の意味やブラウザ操作まで自動判定するコマンドではありません。

## 試行錯誤で判明したこと

| 失敗・誤解しやすい結果 | 修正と確認 | 適用範囲 |
|---|---|---|
| 全体KPIに案件IDのgroupByがある | groupByを外しCOUNT DISTINCT。1行の結果をSQLと照合 | 指標の粒度を先に決める |
| イベントごとの数量を合計して過大計上 | 計画数量は作成イベントだけ、案件明細はMAX数量 | 反復する属性と加算できる実績を区別 |
| STRINGの日時をそのまま日付軸に使う | `DATE(STR_TO_DATE(\`event_time\`,'%Y-%m-%d %H:%i:%s'))` をDATE型のカード数式にする | GanttのMIN/MAX日時はDATETIME |
| dateGrainをMONTHにしても日別の結果 | `STR_TO_DATE(CONCAT(LEFT(\`event_time\`,7),'-01'),'%Y-%m-%d')` で明示的に月初へまとめる。12か月の結果を確認 | 保存値だけを信用しない |
| カレンダー作成で500 | DATE/EVENT/VALUE1構成に `main.dateGrain:{column:<DATE-formula-id>}` だけを追加すると成功 | 再試行前に作成済みでないことを確認 |
| カレンダーが意図しない期間になる | `dates_from:"User Specified"`, `user_year:"Specified"`, `selected_year:"<year>"`, `user_month:"Aug"`, `view:"Month"` と明示的な月フィルター | first_month_displayedはYear表示の依存設定 |
| multi-value作成で500 | VALUE→ITEMの列順と明示的な月初数式を同時に修正して保存・描画成功 | 2変更を同時にしたため単独原因は未確定 |
| radialのデータ値は正しいのに画像が誤解を招く | 定数ITEMの投影・groupBy、Half表示、値ラベルを明示するとSQLと一致する画像に改善 | 複数変更による修正。ITEMだけが原因とは断定しない |
| 箱ひげ図の入力が500件に見える | `/cards/{id}/data?limit=20000` でも500件。renderのqueryResultは9,006件すべてを返した | プレビューを母集団と誤認しない |
| subscriptionをquery APIへ直接送ると失敗、またはフィルターが消える | 旧形式のsubscriptionをquery-v1の式へ推測変換しない。保存カードのrenderか明示的SQLを使う | HTTP 200でも意味が違う場合がある |
| カタログのvalueListがhex色を拒否する | radialのrange色は公開の名前付き候補にないhex値でも保存・描画に成功した。別途、一部のnon-select_list色には資料UI側のhex picker変換もある | 候補値を残し、資料UIの変換とチャート別の実機結果を区別 |
| 数値の条件付き書式保存で400 | `GREATER_THAN_OR_EQUAL` は失敗。旧形式の `GREAT_THAN_EQUALS_TO` で成功 | 他のフィルターAPIのenumと混ぜない |
| 作成・更新は成功したのにページ所属がない | 実際のページとlayoutを作成台帳と照合する | 成功レスポンスだけで配置完了にしない |
| 古いフレームを消すと末尾の仮想カードとして復活 | layoutからの省略は所属解除ではない。認可された旧コンテンツを整理して再確認 | レイアウト保存はカード削除ではない |

新規カードのformula/conditionalFormatsラッパーは設定ガイドの手順を使います。
更新前には対象の新しい `modified` を取得します。作成の500では、結果を確認せず同じ作成を連打しません。
分析用として共有された元ダッシュボードのカードは実験で変更しません。

## ドリルパスにある2種類の「パス」

製品上の仕組みは、Domo公式の
[ドリルパスの追加](https://www.domo.com/docs/ja/s/article/360042924094)と
[データをドリルダウンする](https://www.domo.com/docs/ja/s/article/360042923994)を参照します。
選択したカテゴリー・系列の条件が次のビューに渡り、さらにクリックすると条件が累積します。
同じ指標は各段で再利用できます。別データセットへのドリルでは、絞り込み列の名前と値の互換性が必要です。
Beast Modeは親カードで作成します。公式資料は子ビューだけで新規作成した式が保存後に消えると注意しています。
ファネルの親や前期比の子チャートには制約があります。既定の最終データ表はカード詳細で利用するもので、
ダッシュボードのin-place drillでは利用できません。明示的に作る表のドリルビューとは別物です。

以下は実機で確認したインスタンスAPIです。公開Platform APIの契約と同一視しません。

| 対象・操作 | 確認した形式 |
|---|---|
| ドリルビュー作成 | `PUT /api/content/v3/cards/kpi?parentUrn=<root-card-id>`。通常の新規カードbodyを使い、pageIdは付けない |
| 作成結果 | `urn:"dr:<drill-view-id>:<root-card-id>"`。数値IDとURNは役割が異なる |
| 子の取得・更新・描画 | 数値のview IDではなく、完全なドリルURNを渡す |
| 子孫の確認 | `GET /api/content/v1/cards?urns=<root-id>&parts=drillPath,drillPathURNs,drillParents,metadata` |
| 親のメタデータ | `drillPathURNs` が子孫の順序、`drillPath.paths` が数値view IDをキーにした階層 |
| 定義取得の外側のdrillpath | 要求したビューの**祖先**。親カードは子があっても `[]` になる |
| 並び替え | クライアントの公開配信bundleに `PUT /api/content/v1/cards/<root-id>/drillviews/reorder` とID配列がある [SOURCE]。今回は未実行 |

今回、同じ親IDをparentUrnに指定して順番に2ビューを作ると、直列のドリルパスになりました。
2段目の定義には親と1段目が祖先として記録されました。作成後に実際の階層を再取得します。
App Studioの `viewIds` へドリルビューを登録しません。ナビゲーションのタブやpage drillとは別のオブジェクトです。

親の棒を `site`、次の棒を物理列 `line`、最後をイベント明細表とする場合：

1. 標準カードのテンプレートから子を作成します。可能なら物理列を使います。
2. 親の子孫順序と各子の祖先を確認します。子をメインページへ配置しません。
3. 親のlayout contentに `interaction:{type:"DRILL",config:{}}`、
   `editInAppViewer:true`、`compactInteractionDefault:true` を設定します。
   STANDARDの既定動作はフィルターや詳細表示になることがあります。
4. 1段目をsite条件、最後をsiteとlineの両条件で描画します。

   ```json
   {"width":1000,"height":600,"queryOverrides":{"filters":[
     {"column":"site","dataSourceId":"<dataset-id>","values":["<selected-site>"],
      "operand":"IN","dataType":"string","filterType":"LEGACY"},
     {"column":"line","dataSourceId":"<dataset-id>","values":["<selected-line>"],
      "operand":"IN","dataType":"string","filterType":"LEGACY"}
   ]}}
   ```

5. 最終表に条件の列も表示して、全行が両条件に一致することを検査します。
   独立したSQLとイベント数・重複排除した案件数を照合します。
   今回は4,683イベント・1,161案件が一致しました。saved limitによる打切りにも注意します。
   この確認はクエリと条件伝播の仕組みの検証です。クリック発火・戻る・解除の操作検証は別途必要です。

選択枠を消すためにinteractionをDISABLEDにしません。
`allowTableDrill` は意図して設定します。最終表を隠してもPDPの代わりにはなりません。
今回はPDPや異なるデータセット間のドリルは検証していません。

## App Studioでは対象の形式を維持する

以前の[複製時の記録](reference/app-studio-clone.md)と今回の対象では、保存形式が異なりました。
今回は**GETした全体を維持し、変更するフィールドだけを変えてPUT**すると成功しました。
`type:"app"`、数値のview ID、navigationの `entity` を維持しています。
旧記録の `type:"dataapp"`、文字列IDのscaffolding、entityTypeを強制すると400でした。
片方の記録を全インスタンス共通のDTOとして扱ったり、混ぜたりしません。

テーマはcollection単位で切り分けて保存しました。cards、tables、fonts、pages、navigation、headersは成功しました。
AUTOMATIC_COLORをRGB_HEXへ置き換えると400でした。light/darkの参照を維持し、既存のRGB_HEXだけ変更すると成功しました。
カードは `{sourceId:"ca2"}`、表は `{sourceId:"t2"}`、見出しは `{sourceId:"h1"}`、ページは `{sourceId:"p0"}`
のstyleを参照します。navigationのfit/alignment、枠・区切り線、page densityはサーバーが正規化する場合があるため再取得します。

複数タブを1つにする場合、残すページに必要なカードを先に登録・検証してから、
`DELETE /api/content/v1/dataapps/<app-id>/views/<extra-view-id>` で不要なviewを削除します。
今回は3タブを削除し、ちょうど1viewになりました。非表示の切替ではなく削除なので、認可とバックアップが必要です。
今回は既知の新規カード作成で配置し直しました。カード更新へpageIdを付ける方法や、推測したページcardIdsの送信では
所属を確認できませんでした。

最後に既存のcard/header contentKeyを保ち、standard/compactのフレームを配置し、virtual/virtualAppendixをfalseにします。
writelock取得→layout PUT→finallyでlock DELETEの順に処理します。
旧コンテンツの整理後に、所属・contentKeyの重複・範囲外・重なりがないことを再取得して確認します。
検証の数合わせで無関係なカードを消しません。最終ページは35枚、4つの標準見出し、1タブです。
