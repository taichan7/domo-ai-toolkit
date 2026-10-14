# Domo Workflow Canvas Layout Skill（BPMN キャンバスの規則ベース配置）

Domo Workflows（BPMN キャンバス）のノード配置を**きれい・読みやすい・交差しない**ように
整えたいときに使う。`magic-etl-graph-ui-layout.md`（Magic ETL 版）の Workflow 版。

**正本実装**: 本リポジトリの親バッチ `企業インテリジェンス｜訪問前レポート要求`
= `reference-app/scripts/provision_platform.py` の `batch_mainflow_definition()`。
2026-09-26 にユーザーが UI でマニュアル配置した **v1.0.14** を読み取り、その設定
（ノード座標・エッジ経路・アンカー・ラベル位置）をビルダーへ完全一致で取り込んだ
（比較検証済み: 差分は UI 保存時に採番されるエッジIDの接尾辞のみ）。

---

## 1. データモデル（`savedJson` / 定義 JSON）

```
{ designElements: [ ...nodes..., ...edges... ], dataList: [...], version: 2, schema: {...} }
```

- **Node**: `{id, type, position:{x,y}, data:{dimensions:{width,height}, title, ...}, index}`
  - type: `rootNode` / `serviceTaskNode` / `conditionalGatewayNode` /
    `intermediateCatchEventNode`（タイマー）/ `SUB_FLOW` / `AI_AGENT` / `endNode`
  - 標準寸法は **200×60**（`data.dimensions`）。
- **Edge**: `type` は `defaultEdge` か `conditionEdge`。
  - `source` / `target`（ノードid）
  - `data.sourcePosition` / `data.targetPosition` / `data.entryPosition` / `data.exitPosition`
    （`top|bottom|left|right` のアンカー。`source/targetPosition` が線の出入り、
    `entry/exit` はラベル接続の向き）
  - `data.path`: **`[[x,y], ...]` の明示ウェイポイント**（省略可だが、付けると折れ線が安定）
  - `data.position`: **ラベルチップを描く座標**（トップレベル `position` は UI が見ない）
  - `data.nodeId`: **エッジ自身の一意ノードID**（後述の落とし穴）
  - `data.splitIndex`: 分岐の枝番（分岐ゲートウェイの edge に付く。テンプレート値を保持）

---

## 2. 実証済みレイアウト（親バッチのループ）

キャンバス座標の一例（ノード 200×60・x=360 の本線・ピッチ 100）:

| ノード | 位置 | 備考 |
|---|---|---|
| 開始（rootNode） | (360, 40) | |
| データ取得（serviceTask） | (360, 140) | |
| 1件取得（serviceTask） | (360, 240) | |
| テキスト整形（serviceTask） | (360, 340) | |
| 待機（timer） | (360, 440) | ループ周期 |
| 子Workflow（SUB_FLOW） | (360, 540) | |
| 分岐（gateway） | (360, 650) | ループ判定 |
| **ループカウンタ** | **(630, 440)** | 待機と同じ段の右 |
| 終了（endNode） | (360, 830) | |

エッジ:

| エッジ | アンカー | path | ラベル(data.position) |
|---|---|---|---|
| 直線（本線の各段） | bottom→top | `[[460, from_y+60],[460, to_y]]` | なし |
| 分岐→終了（全件投入完了） | bottom→top（entry top / exit bottom） | `[[460,710],[460,750],[460,790],[460,830]]` | (360,750) |
| 分岐→カウンタ（次の企業へ） | right→bottom（entry left / exit top） | `[[560,680],[630,680],[730,660],[730,500]]` | (630,660) |
| カウンタ→1件取得（戻り） | **top→right** | `[[730,440],[730,270],[560,270]]` | なし |

読み方: 本線は上→下、ループだけ右側で完結する（交差 0）。戻り線はカウンタ上端から
**中央コリドー x=730**（カウンタ中心）を上がり、1件取得の右辺へ入る。

---

## 2.5 ⭐ 分岐（ゲートウェイ）の縦配置パターン（ユーザー実証 v1.0.37）

「種別で分岐して2つのAIを走らせる」子Workflowの正本レイアウト。**分岐先は同じ段に横並び**に置く:

```
開始(360,40) → 待機(360,140) → ゲートウェイ(360,240)
   ├─ 企業（既定・splitIndex 2）: 本線直下 x=460 → 企業AI(360,440) → 終了(360,640)
   └─ 全社（Advanced・splitIndex 3）: ゲート右(560,270) → 右コリドー x=680 → 全社AI(580,440)
        → 下辺(680,500) → (680,670) → 終了の右辺(560,670)
```

- **全社エッジ**: `sourcePosition=right, targetPosition=top, entryPosition=top, exitPosition=bottom`、
  `path=[[560,270],[680,270],[680,310],[680,350],[680,440]]`、ラベル `data.position={x:580,y:310}`。
- **企業エッジ**: `sourcePosition=top, targetPosition=top, entryPosition=top, exitPosition=top`、
  `path=[[460,240],[460,350],[460,350],[460,440]]`、ラベル `{x:360,y:350}`（本線stub上＝親の「全件投入完了」と同流儀）。
- 2つのAIは**同じ y=440**（企業 x=360 / 全社 x=580）。終了 (360,640) は
  企業から top、全社から right で**合流**してよい。
- `splitIndex` は分岐順（既定=2 / Advanced=3）。`advancedRule` は素朴な比較文で書ける
  （実証: `= report_type = "portfolio"`。変数ノードは
  `{"type":"variable","dataType":"text","id":"var_<name>","name":"<name>"}`）。
- ラベルがゲートやAIに重ならないよう、**チップの座標は curve の外側**に置く（この実証値は
  オフラインの重なり検査を通してある）。

## 2.6 ⭐ 数学的レイアウトエンジン（座標系で「毎回崩れない」配置を自動生成）

§2・§2.5 の手置き座標表は読みやすいが、ノードを足す／デプロイするたびに崩れやすい（Domo は空 path
のエッジを自動ルートし、座標を手直ししても次の PUT で乱れる）。座標を**定数から算出**すれば、毎回
同一・交差0の配置を機械生成できる。**参照実装**: `pl-summary-app/scripts/provision_workflows.py`
（`set_grid` / `route_v` / `route_h` / `route_gw_end` / `route_gw_counter` / `route_loop_back` /
`validate_layout` / `ci_style_mainflow_definition`）。**pl-summary WF-01 v1.0.21（ユーザー実証の美配置）を
出力する正本**＝ビルダー出力はライブ v1.0.21 とノード座標13/13・エッジ経路13/13が完全一致。

### 座標系（X軸＝レーン、Y軸＝行）
- ノード寸法 `W×H = 200×60`、条件エッジのラベルチップ `200×40`。
- **行** `r` → 上辺 `y = Y0 + r*PITCH`（既定 `Y0=40`・`PITCH=100`）。
- **レーン**（列）→ 左辺 `x` を名前で固定: `main=360`（本線）／ `counter=590`（ループカウンタ・中心690）／
  `branch=840`（並列サイドブランチ）。
- ノード水平中心 `cx = x + W/2`、行の垂直中心 `cy = y + H/2`。**全エッジはこの中心を通す**。
  戻りループの縦コリドー `LOOP_X = カウンタ中心 = 690`。

> ⭐⭐ **美配置を決める2つの数学ルール（v1.0.21 ユーザー実証から逆輸入）**
>
> 1. **分岐は「同じ行」に置いて真っ直ぐ水平にする**（折れ曲げない）。サイドブランチの先頭（全社クエリ）を
>    フォーク元（本線クエリ）と**同じ row** に置くと、分岐は `[[x+W, cy], [branch_x, cy]]` の**直線水平**になる。
>    （旧版は branch を1行上に置き「右→上→右」の折れ曲げになっていた＝不美。row を揃えるだけで直線化。）
> 2. **ラベルチップ中心x ＝ 縦コリドーx ＝ 接続先ノード中心x を一致させる**（線の横ジョグ退治）。Domo は
>    条件ラベルの所でエッジを分割し各半分を自動ルートするため、**チップ中心が接続先ノード中心からずれると
>    「チップ→ノード」に横の段差（ジョグ）が入る**。カウンタ（接続先）の中心を「次店舗へ」チップ中心(590+100
>    =690)に合わせる＝カウンタを `x=590`（中心690）に置く。すると線はチップを真っ直ぐ縦に抜ける。
>    ラベルは線の中心に `(中心x−100, 中心y−20)` で中央寄せ（次店舗へ=(590,650)／次店舗なし=(360,750)）。

### エッジ経路（直交折れ線・中心アンカー・すべて計算式）
| 種別 | アンカー | path |
|---|---|---|
| 縦（同一レーン） | bottom→top | `[[cx, y(r0)+H], [cx, y(r1)]]` |
| **水平フォーク（同一行）** | right→left | `[[x+W, cy(r)], [branch_x, cy(r)]]`（ブランチ先頭を同じ row に置く） |
| ゲート→終了（本線直下） | bottom→top | `[[cx, gy+H], [cx, gy+H+50], [cx, ey−50], [cx, ey]]` |
| ゲート→カウンタ（ループ入口） | right→bottom | `[[gw_x+W, cy(gw)], [counter_x, cy(gw)], [LOOP_X, cy(gw)−20], [LOOP_X, y(counter)+H]]`（短い対角でコリドー中心へ寄せる） |
| カウンタ→本線（戻り） | top→right | `[[LOOP_X, y(counter)], [LOOP_X, cy(tgt)], [main_x+W, cy(tgt)]]` |

### 参照レイアウト＝reference-app 流（並列サイドブランチ＋**2終了**）
本線（店舗/企業ループ・`main`）と全社サイドブランチ（`branch`）を**並列**に走らせ、**終了ノードを2つ**
持つ（各ブランチが独立に終端する）。pl-summary WF-01 v1.0.21 の配置:

| ノード | レーン,行 | 位置 | 備考 |
|---|---|---|---|
| 開始 | main,0 | (360,40) | 出線1本のみ（ODY_025） |
| 本線クエリ（店舗別SQL） | main,1 | (360,140) | **ここから全社ブランチへ水平フォーク** |
| 単一取得 / 整形 / 待機 / 子WF(store) | main,2–5 | (360,240..540) | |
| 分岐（gateway） | main,6 | (360,640) | |
| 終了#1（本線） | main,8 | (360,840) | row7 を空けて間隔を作る |
| ループカウンタ | counter,4 | (590,440) | 中心690＝「次店舗へ」チップ中心に一致（ジョグ退治） |
| 全社クエリ / 整形 / 子WF(company) | branch,**1–3** | (840,140..340) | **本線クエリと同じ row1 開始**＝フォークが直線水平 |
| 終了#2（全社） | branch,4 | (840,440) | |

- フォークは**開始ではなく本線クエリの右**から出す（§3 の ODY_025＝開始の分岐は1本まで）。
- 2つの子WF呼び出しは `report_type`（store/company）で**同一の統合サブWF**を呼び分ける（新WFを増やさない）。
- ゲートウェイの条件エッジ（Default＝ループ終了→終了#1 / Advanced＝継続→カウンタ）は、**ロジック
  （`advancedRule` の `index < count(list)` 等・`splitIndex`・`nodeId`）を保持し、経路（path/アンカー）だけ
  再計算**する。`advancedRule`・`nodeId` を書き換えない（§3-1）。

### デプロイ前のオフライン検証（§4 の実装 = `validate_layout`・**ラベルチップも対象**）
`validate_layout(definition)` が ①ノード同士の重なり ②**ラベルチップ(200×40)がノード／他チップに重なる**
③エッジ経路が無関係ノード／**自分以外のラベルチップ**を貫く、を総当たり検査し、1件でもあれば PUT を中止
する（「重なり0・経路貫通0」を**ゲート**にする）。⚠ ノードだけ検査してラベルチップを見ないと「次店舗へ」が
縦コリドーに食い込む崩れを見逃す（今回の実インシデント）。ビルダーは座標を定数から算出するため、ノード
追加・再デプロイでも配置は決定的に再現され、**手直し→逆輸入のループが不要**になる（崩れたら定数か
(lane,row) 割当・ラベル中央寄せ式を直すだけ）。

### 自己確認＝SVG プレビュー（§4）
`python3 ../scripts/preview-wf-layout.py def.json out.html` でノード／エッジ／ラベルチップを SVG 描画し、Chrome
headless（`--headless --screenshot`）で PNG 化して**目視**する。重なり検査(機械)＋目視(人/AI)の二段で
「美しさ」を担保してから PUT する。

---

## 3. ⚠ 落とし穴（実弾インシデント）

1. **`data.nodeId` に source ノードの ID を入れてはならない**（最重要）。
   エッジの `nodeId` は「エッジ自身の一意ノードID」。source のゲートウェイIDと衝突させると
   UI がゲートウェイを描画せず「線が途切れた」見た目になる（2026-09-26 v1.0.11 で実測）。
   → **テンプレートの一意値をそのまま保持**する（新規作成時は `rid("edge")` 等で採番）。
2. **ラベル位置は `data.position`**。トップレベル `position` を書き換えても UI は動かさない
   （テンプレート座標のままゲート真上に重なって見える）。
3. **直線エッジにも明示 `path` + アンカーを書く**。省略でも描画はされるが、
   ノード移動時に折れ線が崩れる／意図しない側から出ることがある。
4. **エッジIDは UI 保存でランダム接尾辞が付く**（`edge-A-B` → `edge-A-B-xxxxxxxx`）。
   ラウンドトリップ比較では **ID をキーにしない**（source/target+layout 値で比較する）。
5. **Timer トリガーは REST 非公開**（`/triggers` 系は 404）。定期実行は UI の Triggers タブ。
   実行は `POST /api/workflow/v1/instances/message`（`messageName` = 開始ノードのタイトル）。
   削除は `DELETE /api/workflow/v2/models/{id}` が使える。
6. **バージョンは不変**。編集は draft 作成→PUT definition→release。
   トリガーはバージョンに紐づくため、上げたら再設定。
7. **開始ノードの分岐は1本まで（ODY_025）**。開始から2本目のエッジを張ると release が
   `ODY_025` で失敗する（実測）。並列サイドブランチを足すときは、開始ではなく
   **先頭のサービスノード（例: 最初のクエリ）の右から分岐**させる。

---

## 4. オフライン検証（デプロイ前に必ず）

ネットワーク不要で「重なり 0・経路が無関係ノードを貫かない」を機械確認する:

```python
# 1) ノード矩形（position + data.dimensions 既定 200x60）とラベル矩形
#    （data.position + 200x40）を作る。
# 2) 総当たりで矩形交差を検査（node-node / chip-node / chip-chip）。
# 3) 各エッジの path を 40 分割し、source/target 以外のノード矩形に入る点がないか検査。
# 4) SVG に描画して Chrome headless で PNG 化し目視（任意）。
```

実例: `/tmp/ci_wf_svg.py`（作業用）。SVG にはノード矩形＋タイトル、`data.position` の
ラベルチップ、path を描き、`overlaps: none` / `edge through unrelated nodes: none` を確認する。

---

## 5. 適用手順

1. **ライブ定義を GET**（`/api/workflow/v1/models/{id}/versions/{ver}` の `savedJson`）。
2. `activate_workflow` 等のビルダーで `designElements` の座標/経路/ラベルのみ書換
   （**ロジック・変数・ルールは 1 bit も変えない**）。
3. §4 のオフライン検証を通す。
4. draft 作成 → PUT → release → GET で layout 値を round-trip 検証（ID ではなく値で）。
5. 単一ノード/少数入力の**テスト用バリアント**で実行確認してから本番実行する。

> 本リポジトリでは `reference-app/scripts/provision_platform.py` の
> `batch_mainflow_definition()` が上表の座標を出力し、`ensure_workflow(..., force_update=True)`
> が draft→PUT→release を行う。**ビルダーが座標の正本**（UI で手直ししたら本スキルの手順で
> 逆輸入してビルダーへ反映する）。
