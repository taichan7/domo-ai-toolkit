# Magic ETL Graph-UI Layout Skill（規則ベースのキャンバス座標 再配置）

Use this when a Magic ETL dataflow's canvas (`useGraphUI`) has messy tile/section placement
— **①セクション同士が重なる ②タイルがセクションからはみ出る ③タイル同士が重なる
④配置が歪で空白だらけ ⑤処理の流れ（入力→出力）が左→右に読めない** — and you must re-lay it out
**beautifully & compactly & left-to-right by rule-based coordinate calculation**, WITHOUT touching
any data logic.

⭐ **最重要ルール（鄭さん 2026-09-05）＝「入力データセットは左に。出力データセットは右に。左から右に
処理が流れていく」。** ETL は有向グラフ（DAG）なので、レイアウトは**フロー方向**を尊重しなければ
ならない：入力ソース（`LoadFromVault`）を最左・出力（`PublishToVault`）を最右に置き、処理が
左→右へ流れるように並べる。これは「コンパクトさ（空白最小）」と両立させる（＝フローを保ったまま
最も密に詰める）。**フロー方向はコンパクトさより優先**（コンパクトのために入力を右へ飛ばしてはならない）。

姉妹スキル [`domo-magic-etl.md`](domo-magic-etl.md) は「全タイルは Section 内に置く」ことを
必須ルールにするが、**どう座標を決めるか**は言わない。本スキルがその幾何を機械保証で埋める。

**Reference implementation（本 repo・本番 dataflow でライブ検証済み）:**
- `production-priority-app/dataflow/graph_ui_layout.py`（内部ワークスペース・非同梱）
  — 純幾何エンジン（ネットワーク非依存・import して再利用可）。
- `production-priority-app/dataflow/deploy_layout_3063.py`（内部ワークスペース・非同梱）
  — 「純コスメティック」デプロイヤ（多重ゲート G0–G4）。
- **2 例目（2026-10-09・DF3210 でライブ検証）**:
  `subscription-analytics-app/dataflow/flow_layout.py`（内部ワークスペース・非同梱）
  ＝共有エンジンの薄いラッパ（対象フロー向けの `max_cols` 上書き・`TARGET_FLOW_ASPECT` 固定）と
  `deploy_layout_3210.py`（内部ワークスペース・非同梱）（同型 deployer）。
  DF3210（81 タイル/14 セクション・最深 8 depth）では **`max_cols=8` が全セクションを
  折返しなしの左→右一本道**にし、7 深さの登録チェーン（テスト除外→日付化）の折返し/逆行が消えた
  （`max_cols=4/5` では 2 バンドへ折返し後段が左へ戻る）。builder（`build_dataflow.py`）も
  同じ `flow_layout` を呼び、**焼込み座標とライブ再配置の座標差分 0** を確認。回帰網は
  `subscription-analytics-app/dataflow/test_layout_3210.py`（内部ワークスペース・非同梱）。

---

## 0. 大前提 — なぜ「座標だけ」でよいのか

Magic ETL のキャンバス座標は **データを 1 bit も変えない**。だから座標再配置は
**RUN 不要**（~69 分の再実行を伴わない）で、定義 PUT だけで反映される。
これが本テクニックの安全性の源泉：最悪でも「見た目が変わるだけ」で計算結果は不変。
→ この不変性を **機械証明** するのが下記ゲートの役目。

---

## 1. まず理解すべきデータモデル

`dataflow.gui` の構造（実測）:

```
gui = {
  useGraphUI: true, version: "1.0",
  elements:  [ ...Section..., ...Tile... ],   # 平坦リスト（Section 群→Tile 群の順）
  canvases:  { default: { elements: [...] } }, # ↑と byte 一致の複製
  disabledActions: [...]
}
```

- **Section** = `{id, type:"Section", x, y, width, height, name, backgroundColor}` — 矩形。
- **Tile** = `{id, type:"Tile", x, y, color}` — **width/height を持たない**（点＝左上アンカーのみ）。
- **タイル↔セクションの所属は純粋に幾何的**（タイルの左上 (x,y) がどの Section 矩形に内包されるか）。
  明示的な親子キーは無い。

### ⭐ 座標が住む「3 箇所」— lockstep で書き換える

同じ座標が **3 箇所に重複** して存在する。1 箇所でも取りこぼすと不整合になる：

1. `gui.elements[*]`（平坦リスト）
2. `gui.canvases.default.elements[*]`（1 の byte 一致複製）
3. `actions[*].gui.x / .y`（**全 action** が同 id の Tile に対応・w/h は持たない）

Tile の id 集合 == action の id 集合。3 箇所すべてを同じ値へ書き、検証も 3 箇所を剥がして行う。

---

## 2. エンジンが機械保証する不変条件（`verify_layout` / `verify_flow`）

`relayout(elements, flow_rank=None)` は「所属だけ信頼して幾何を全再計算」する。手置き座標は**所属
シグナルとしてのみ**使い、実座標は全部捨てる（所属回復＝アンカー内包・orphan があれば即例外）。
`flow_rank`（＝各タイルの DAG 深さ・§3.0）を渡すと**左→右フロー配置**、省略すると**面積降順パッキング**
（compact だがフローを崩す）にフォールバックする。出力保証:

- **V1**: セクション矩形同士は重ならない。
- **V2**: 全タイル本体 (TILE_W×TILE_H) が所属セクション矩形に完全内包（はみ出し 0）。
- **V3**: タイル本体同士は重ならない（列内は縦積み・列間/行間は footprint+gap の一様ピッチ）。
- **V4（努力目標）**: コンパクト＝空白最小。高さ/幅バジェットをスイープして bbox 面積最小を自動選択。
- **V5（分離）**: セクション枠とタイル本体/**ラベル**がくっつかない。`PAD_*` で枠内余白・
  `*_GAP` でタイル間余白を確保する。⚠ 実 Domo タイルは本体アイコンの**下にデータセット名ラベル**
  （最大2行折返し）を描き、footprint(TILE_W×TILE_H)の外へはみ出す。footprint だけ詰めると
  ラベルが隣タイル/セクション枠に触れる（鄭さん 2026-09-05 指摘＝「くっついている」）。
- **⭐V6（左→右フロー・`flow_rank` を渡したときのみ）**: 「入力＝左・出力＝右・処理は左→右」。
  - **V6a**: セクション代表 flow-rank（所属タイルの平均 DAG 深さ）が小さいほど左＝x が rank に対し
    単調非減少（同列＝`COL_PITCH` 未満のズレは許容）。
  - **V6b**: 入力タイル群（depth 最小）の最右 x < 出力タイル群（depth 最大）の最左 x。

`verify_layout()` は V1/V2/V3 を、`verify_flow(elements, flow_rank)` は V6a/V6b を文字列リストで
返す（空＝健全）。**両方をデプロイ前・build 時アサーションで必ず呼ぶ。** V4/V5 は連続量なので

**Per-edge check (2026-10-15, P/L reference)**: V6a is a section-average check and V6b compares
the minimum/maximum depth. They do **not** prove that every `dependsOn` edge points right.
Small flows can be stacked into one section column and pass both while individual edges run backward.
Before claiming left-to-right layout, additionally assert `upstream.x < downstream.x` for **every**
edge, and choose `max_cols` large enough to avoid depth-band folding. The standalone
`pl-summary-app/scripts/polish_dataflow.py` reuses the shared engine for internal geometry, then
places named branch lanes using actual dependency constraints and section gaps before validating all edges.**両方をデプロイ前・build 時アサーションで必ず呼ぶ。** V4/V5 は連続量なので
`bbox` 面積比・充填率・最小 gap を print して目視する（下記チューニング参照）。

---

## 3. アルゴリズム（graph_ui_layout.py）

### 3.0 ⭐ フロー信号 = DAG のトポロジカル深さ（`flow_rank`）
「左→右に処理が流れる」を機械保証するには、各 action が入力からどれだけ下流かを表す**一次元の
順序シグナル**が要る。Magic ETL の `actions[*].dependsOn`（＝upstream action id のリスト）が DAG を
成すので、**最長入力パス長**を深さとする：

```
depth(a) = 0                              (dependsOn 無し＝入力ソース LoadFromVault / FixedInput)
         = 1 + max(depth(u) for u in a.dependsOn)   (それ以外)
```

builder 側の `_compute_flow_rank(actions)`（メモ化 DFS・循環は訪問中集合で検出し 0 に丸める安全弁）が
`{tile_id: depth}` を返し、`relayout(elements, flow_rank)` に渡す。**手置き x 座標をフロー代理に
使ってはならない**（ビルダーの x 順は実測で最大 53% がフローと逆＝信頼できない）。DAG が唯一の真実。

### 3.1 配置手順
1. **所属回復** `_recover_membership`：各タイルの左上を内包する Section へ割当。多重内包は
   最小面積 Section。orphan があれば **即例外**（所属破損）。
2. **セクション内レイアウト** `_layout_section_tiles(tiles, rank_of)`：
   - `rank_of`（＝flow_rank）あり: **列＝flow-depth の昇順**（dense-rank）で左→右に並べる。
     同 depth のタイルは同列で縦積み（＝並列ブランチ）。⭐これでセクション内も入力左・出力右。
   - `rank_of` なし（フォールバック）: 既存 x をクラスタリング→列（ビルダー処理順の近似）。
   - 列数が `MAX_COLS` 超なら band へ折返し（fan-out を畳む）。列内は y ソートで縦積み（重なり 0）。
3. **セクション配置**：
   - **flow_rank あり** → `_best_flow_packing`：セクションを **(flow-rank 昇順, 面積降順)** で並べ、
     `_pack_flow_columns` で**縦シェルフ**（上→下に積み、溢れたら右の新列へ）に置く。列インデックスは
     投入順（＝flow 昇順）に単調増加するので、**x はフローに対し単調非減少＝左→右が保証される**。
     高さバジェットを 28 分割スイープし bbox 面積最小を選ぶが、**どのバジェットでも並び順（＝フロー）は
     不変**なので compact と flow を両立する。⚠ 面積最小だけ追うと**縦長**（portrait）が選ばれ「左→右」の
     意図を損なうため、`TARGET_FLOW_ASPECT=2.0` / `FLOW_ASPECT_WEIGHT=0.35` で **landscape（横長・多段）を
     優先**する（一般 `TARGET_ASPECT=1.4`/係数 0.05 より強い）。実測: 縦長 4668×5544(aspect0.84) を退け
     横長 9172×2920(aspect3.14・6 段)を選択＝前回の praised 3512 より**むしろ低い**高さで左→右になった。
   - **flow_rank なし** → `_best_packing`：**面積降順** skyline bottom-left（大→小で棚の穴を埋める）。
     幅バジェットをスイープし bbox 面積最小。⚠ これは compact だが**フローを積極的に崩す**（小セクションが
     余白埋めで離れた段へ飛ぶ）＝フロー要求があるなら必ず flow_rank を渡すこと。
4. **書き戻し** `relayout`：座標(x/y/width/height)**だけ**書換え。id/type/color/name/背景色は保持。
   返り値は要素リストで、**順序は入力を保持**（配置は sid/tile_id キーで計算するので順序に非依存）。

### チューニング定数（footprint とピッチ・px）— V5「くっつかない」の主ノブ
`TILE_W=176 / TILE_H=112`（**Domo の公式タイル寸法ではなく**、重なりを生まなかった実測下限を
footprint として採用した値。⚠ タイル下ラベルは含まない）。`COL_GAP=44 / ROW_GAP=48` → ピッチ 220/160。
`ROW_GAP` は**縦積みタイルの下ラベル(最大2行≒36px)を吸収**する実効クリアランス。
`PAD_L=PAD_R=48` / `PAD_T=72`（セクション名帯＋同期アイコン）/ `PAD_B=48`（末尾タイル下ラベル）。
`SEC_GUTTER=ROW_GUTTER=56`。`MAX_COLS=12`。フロー配置の形は `TARGET_FLOW_ASPECT`/`FLOW_ASPECT_WEIGHT`。
**これらは調整可能なノブ**であって Domo 仕様ではない〔[REPO]/[INFER]〕。**新しいキャンバスでは充填率と
最小 gap を必ず実測して微調整する**（値をコピーするな）。

### ⚠ 保証すること / しないこと（over-claim 回避）
- ✅ **保証する**：V1/V2/V3（重なり・はみ出し 0）。`flow_rank` を渡せば **V6a/V6b（左→右フロー・
  入力左・出力右）も保証**（縦シェルフは全バジェットで x 単調非減少）。
- ⚠ **保証しない**：**V4/V5（コンパクト・分離）は連続量＝努力目標**で、絶対最小は保証しない
  （バジェット離散スイープ＋aspect ペナルティの近似）。また `flow_rank` **を渡さない**フォールバックは
  面積降順で**読み順を積極的に崩す**（compact 優先）＝この場合「左→右」を主張してはならない。

### 3.2 ⭐ 接続性 tail-pass — 同一列内でセクション縦順(Y)だけを並べ替え「線を短く／無関係タイルを繋げない」
鄭さん 2026-09-06 要望①「関係ないタイルが繋がって**見える**（実は無関係＝保守性が悪い）」②「繋がるタイルは
処理関連ゆえ近くに置き線を短く」への座標ベース対応。**`_best_flow_packing`（§3.1 step3）の後段に挟む純コスメ
tail-pass** で、§3.1 で得た左→右フロー配置を**一切崩さず**接続性だけを磨く（＝「これまでの改善はそのまま」）。

**⭐ Y だけが唯一の“自由な自由度”（他は全部ハード制約に固定済み）** — なぜ全制約を保ったまま安全か：
- **x/幅/高さを一切触らない** → V6（入力=左・出力=右の x-単調性）が**構造的に不変**。
- **列高 = Σ(高さ + ROW_GUTTER) は並び順に依らず一定**（順列不変量）→ **bbox（キャンバス面積）が厳密に不変**
  ＝コンパクトさ(V4/V5)を1 px も悪化させない。実測 9172×2920 → 9172×2920（完全同一）。
- セクション内の相対レイアウトは保ち、**タイルは所属セクションと剛体で縦移動** → V1/V2/V3・membership 不変。
- 初期順はパッキングの**決定的 y 昇順を種**にし、タイル位置も layout 空間（`local_pos`）から組む＝**入力の実座標を
  一切読まない** → 決定的・座標非依存・冪等（再適用は不動点）。

**目的関数 = 列を跨ぐタイル間エッジの総長 最小化**（＝要望②「線を短く」そのもの）：
```
minimize  Σ_{(u,v)∈cross}  hypot( xc(u)−xc(v),  y(sec_of[u])+relY(u) − y(sec_of[v])−relY(v) )
```
`xc`（x-中心）は固定・`relY`（セクション原点からの相対 y）は剛体で不変ゆえ、動く変数は**各列のセクション縦順**が
決める `y(sec)` だけ。**同一セクション内エッジは剛体移動で長さ不変 → 目的から除外**（argmin 不変・O(E) を軽くする）。
⭐**要望①（赤エッジ＝無関係タイルを貫く線）は目的に入れていないのに副次的に減る**：長い線ほど多くの無関係タイルを
薙ぐので、総長を縮めると貫きも減る。実測でこの単一目的が赤エッジ最小化の代理として最も素直だった（§9 メタ教訓）。

**最適化＝列ごと網羅 × 座標降下**：列サイズ ≤ `exhaustive_cap(=8)` は**全順列**を試し**列内大域最適**（貪欲局所最適でない）。
超過列は隣接 swap（総長が減るときだけ採択）にフォールバック。列を跨ぐ結合があるので**1列最適化→他列固定のまま
反復**（座標降下・`rounds=6`・不変で早期終了）。tie は順列の id 列辞書順で決定的。

**API（後方互換・追加のみ）**：
```python
edges = graph_ui_layout.edges_from_actions(actions)   # dependsOn から [(upstream_id, downstream_id)]
new_elements = graph_ui_layout.relayout(elements, flow_rank, edges)   # 第3引数 edges を渡すと tail-pass 有効
# edges 省略時は従来どおり並べ替えなし＝完全後方互換（既存テスト/経路を壊さない）
```
`edges_from_actions` は `compute_flow_rank` と**同じ dependsOn 解釈**（欠損/None は空・存在しない upstream は無視）に
揃える＝「フロー方向を決める依存」と「線長を測る依存」が同一グラフになる。builder(`_finalize_layout`)と
コスメ deployer(`deploy_layout_3063.py`)の**両経路が同じ `edges_from_actions`+`relayout(edges=)`**を呼ぶ＝
焼込み座標とライブ再配置の並べ替えが一致（落とし穴 C と同じ「1実装を共有」原則）。

**実測（DF3063・[REPO] 自己再測定＋3体の独立反証エージェント＋合成が収束）**：
- 総エッジ長 254279 → 232320（**−8.64%**）／赤エッジ 107 → 93／貫き延べ 355 → 301／交差 858 → 562（**−34.5%**）。
- **bbox 26.78M 厳密不変**・V1-3=0・V6=0・決定的/座標非依存/冪等 いずれも True。

**⚠ 正直な限界（over-claim 回避・[REPO]）＝ここは本レバーで動かない**：`max_edge_len` は 6857 → 6802（**−0.80%＝ほぼ不変**）。
支配的な最長束は **⑦(x892)/⑬ → ⑫（最終親サマリー・内部 rank 3→62 で平均 rank が高く最右へ固定）** の ~6000px を
**raking する 8 本前後**で、これは**フロー(x)が強制する束**＝**セクション縦順(Y)では縮まない**。除去には
**鄭さんゲートの設計判断**が要る（V6a のセクション代表 rank を AVERAGE→**MIN-entry rank** に緩める／⑫の membership を
分割する／エッジ配線を変える）。**本 tail-pass は「Y で縮む線」だけを縮める**と正しく述べ、「全部短くした」と誇張しない。

**赤エッジの分類（どれが可約か）**：
- **flow 強制・ほぼ水平**（⑦→⑫ の raking 束）＝ x が支配 → **本レバーでは不可約**（max_edge_len に現れる）。
- **ほぼ垂直/斜め**（同一 or 近接列内）＝ Y が支配 → **本レバーで可約**（total_len/赤の −8.64%/107→93 はここ由来）。

**（別レバー・出荷しない）rank-列再割当**：`max_edge_len` に効く**唯一**のレバー（−11.6%）だが、コンパクト性を
壊す（bbox +3.4%〜+14.7%）＝**トレードオフを鄭さんゲート**に上げるだけで自動出荷しない。本 tail-pass は
「bbox 不変で total を縮める Pareto 安全域」に留まる。

---

## 4. 「純コスメティック」デプロイの多重ゲート（deploy_layout_3063.py）

logic 用の `deploy_3063.py` とは**別スクリプト**にする（あちらは RUN=1 の外科的マージ）。
座標のみ変更なので **RUN を絶対にトリガしない**（定義 PUT だけ）。

- **G0** INSTANCE ガード（対象インスタンス固定）。
- **G1** RUN in-flight 検査：実行中に定義 PUT すると実行が壊れうる→実行中なら中止。
  ⭐応答形が bare list でも既知 envelope でもなければ「実行なし」と**誤判定せず安全側で中止**
  （`_extract_exec_list` が不明形に None を返す）。
- **G2** 純コスメティック証明（**PRE-PUT**）：`out=deepcopy(live)` に座標のみ 3 箇所へ書込み、
  **座標を全部剥がした out と live が完全一致**することを表明＝座標以外は 1 bit も変わらない機械証明。
  （PRE-PUT なので top-level は live と一致し、文書全体比較で正しく証明できる。）
- **G3** 幾何不変条件 `verify_layout`（V1/V2/V3=0）＋ bbox 面積比を print。
- **G3b** 左→右フロー `verify_flow`（V6a/V6b=0）＝入力最左・出力最右・rank 昇順で x 単調非減少。
  ⭐**幾何 clean(V1/V2/V3=0)でもフローは逆行しうる**ので独立ゲートにする（落とし穴 C）。
- **G4** round-trip verify（**POST-PUT**）：GET し直して
  (a) action/element id 集合不変 (b) 座標が送信値通り（**3 箇所すべて**）
  (c) 座標以外の内容がライブと不変 (d) ライブでも V1/V2/V3 保持。
  失敗なら backup を PUT で原状復帰して非ゼロ終了（fail-safe＝データ不変のまま撤退）。

---

## 5. ⚠ 二つの落とし穴（両方ともここで実弾インシデント寸前になった）

### 落とし穴 A（CRITICAL）— round-trip で「文書全体」を比較すると毎回自己巻き戻す
Domo は**定義 PUT のたびに top-level を必ず bump** する：`modified`(タイムスタンプ)、
`onboardFlowVersion`(id がインクリメントする新オブジェクト)、`lastExecution` 等。
G4(c) を「座標を剥がした**文書全体**の一致」で書くと、この bump で**毎回** false mismatch →
backup を復元 → exit 2 → **コスメティック変更が全 deploy で自己巻き戻る**（DRY 以外で永遠に着地しない）。

✅ **修正 = per-object canon**：我々が touch する **action / element だけを id 毎に**非座標比較する
（`_action_canon` は `tables`+gui座標を drop、`_elem_canon` は座標を drop、それぞれ `json.dumps(sort_keys)`）。
top-level は個々の object に含まれないので bump では発火しない。これは `deploy_3063.py` の
per-action canon 方針と同旨（そちらは元々正しかった。文書全体比較への移植でこの保護が落ちていた）。
⭐ライブ実測でも「非座標 action/element 内容 == backup（diff=[]）」＝Domo は per-object を bump しないと確認済み。

### 落とし穴 B（実行時クラッシュ）— Python 3.9 で PEP 604 注釈が即時評価される
実行環境は **Python 3.9.6**。`def f() -> str | None:` の `str | None` は注釈が**即時評価**され
`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` を実行時に投げる。
`py_compile`（構文のみ）も import-only テスト（main を呼ばない）も**見逃す**。
✅ **修正 = ファイル冒頭に `from __future__ import annotations`**（注釈を遅延評価）。
教訓：**その関数を実際に呼ぶオフラインテストを書く**（compile だけ／import だけでは注釈評価バグを捕れない）。

### 落とし穴 C（CRITICAL・実弾寸前）— deployer は builder の焼込み座標に頼らず「ライブ再配置」するので flow_rank を独立に算出せよ
コスメティック deployer（`deploy_layout_3063.py`）は **committed JSON の焼込み座標を送らず**、
**ライブ定義を GET → 座標だけ書換えて送り返す**設計（builder↔ライブの非座標ドリフトを一切運ばないため）。
この設計は正しいが、**`relayout(live_elements)` を flow_rank 無しで呼ぶと面積降順フォールバックになり、
幾何は clean(V1/V2/V3=0)のままフローだけ逆行した座標を PUT してしまう**（＝builder では左→右に直した
のに deploy 経路だけ元の症状に戻る）。実際これで「DRY の bbox が landscape でなく縦長」で気づいた。

✅ **修正 = deployer 側でもライブ `actions` の `dependsOn` から flow_rank を独立算出して `relayout` へ渡す**。
`compute_flow_rank` を **engine(graph_ui_layout)に置き builder と deployer が共有**する＝flow_rank の
単一の真実（別実装だと焼込みとライブ再配置がずれる）。**さらに deploy ゲートに G3b(`verify_flow`)を
足す**：幾何ゲート(V1/V2/V3)は重なり/はみ出ししか見ず、**フロー逆行を検知しない**。フロー要求がある
なら「幾何 clean」を「フロー OK」と誤認してはならない＝フロー検証は独立ゲートとして必ず持つ。
教訓：**flow_rank を使う経路が2つ以上あるなら（焼込み build と ライブ deploy）実装を1つに共有し、
各経路のゲートに geometry と flow の両方を課す。**

---

## 6. DO / DO-NOT

- ✅ 座標(x/y/width/height)**以外**は 1 bit も変えない。G2 で PRE-PUT 機械証明する。
- ✅ 3 箇所（gui.elements / canvases.*.elements / actions[*].gui）を lockstep で書き、両側で剥がして検査。
- ✅ RUN は起動しない（座標変更にデータ再計算は不要）。G1 で in-flight RUN を避ける。
- ✅ round-trip 比較は **per-object canon**（top-level bump を無視）。
- ✅ その関数を**呼ぶ**オフライン特性化テストで守る（Py3.9 注釈・自己巻き戻しを機械再現）。
- ✅ **ETL は左→右フロー＝入力(LoadFromVault)を最左・出力(PublishToVault)を最右に置く**。フロー信号は
  `dependsOn` の DAG 深さ（`flow_rank`）＝**手置き x をフロー代理に使わない**（実測で最大 53% が逆）。
- ✅ フロー配置は `_best_flow_packing`（縦シェルフ・landscape 優先）＝`verify_flow(V6a/V6b)` で機械保証。
- ✅ **接続性は「同一列内のセクション縦順(Y)だけ」で磨く**（§3.2 tail-pass・`relayout(elements, flow_rank, edges)`）。
  x/幅/高さを触らないので **bbox・V6・V1-3・membership が全て不変**＝コンパクトさもフローも 1 bit も悪化させない
  “Pareto 安全域”。目的は**列を跨ぐエッジ総長の最小化**（線を短く＝要望②）＝赤エッジ（要望①）も副次的に減る。
- ✅ **`max_edge_len` が動かない線は正直にそう言う**：flow(x)が強制する最長束（例 ⑦→⑫ raking）は Y 並べ替えでは
  縮まない。「全部短くした」と誇張せず、`max_edge_len` を縮める案（rank-列再割当）は bbox を悪化させる
  トレードオフ＝**業務オーナーゲート**に上げる（自動出荷しない）。
- ✅ flow_rank を使う経路が複数（焼込み build と ライブ deploy）あるなら `compute_flow_rank` を engine に
  置き**実装を1つ共有**し、**各経路のゲートに geometry(V1/V2/V3)と flow(V6)の両方**を課す（落とし穴 C）。
- ✅ V4/V5（compact/分離）は連続量＝充填率・bbox 面積比・最小 tile↔枠 gap を**実測 print** して微調整。
- ⛔ 文書全体を round-trip 比較しない（毎回自己巻き戻す）。
- ⛔ `verify_layout`/`verify_flow` を省略しない（V1/V2/V3＋V6 は唯一の幾何・フロー保証）。
- ⛔ TILE_W/H 等を「Domo 公式寸法」と称さない（実測 footprint＝調整ノブ・タイル下ラベルを含まない）。
- ⛔ footprint(TILE_W/H)を膨らませて「くっつき」を直そうとしない（セクションが肥大化し空白過多に逆戻り）。
      分離は **PAD_*（枠内）と ROW_GAP/COL_GAP（タイル間・ラベル吸収）** で行う。
- ⛔ **フロー要求があるのに `flow_rank` を渡さない**（面積降順フォールバックは読み順を積極的に崩す）。
- ⛔ **コンパクトさのためにフロー方向を犠牲にしない**（入力を右へ飛ばさない）。フロー＞コンパクト。
- ⛔ 面積最小だけで形を選ばない（縦長に落ちて「左→右」が読めなくなる）＝landscape を優先ペナルティで担保。
- ⛔ `str | None` 等 PEP604 注釈を future-import 無しで書かない（Py3.9 で実行時 TypeError）。

---

## 7. 実行手順

```bash
# オフライン特性化（ネットワーク無し・毎回 PASS を確認）
python3 /path/to/test_deploy_layout_g4.py

# エンジン(graph_ui_layout.py)を変えたら焼込み JSON を再生成（committed==build 不変条件）
python3 production-priority-app/dataflow/build_dataflow_3063.py       # dataflow-3063.json を再ビルド
python3 -m pytest production-priority-app/dataflow/test_build_layout_postpass.py -q  # 5 tests（含 committed==build）

# DRY（PUT せず G1/G2/G3 とボディ構築のみ・ライブ実データで事前確認）
set -a; . ~/.config/domo-utils/<instance>.env; set +a   # INSTANCE / DOMO_TOKEN を供給
test "$INSTANCE" = "<expected-host>" || exit 9           # G0 相当のガード
DRY=1 python3 production-priority-app/dataflow/deploy_layout_3063.py

# 本番（G1→G2→G3→PUT(RUN無し)→G4 round-trip）
python3 production-priority-app/dataflow/deploy_layout_3063.py

# 事後検証（G4 が未実行/クラッシュした場合の GET-only 後追い確認）
#   sandbox 内 urllib が不安定なら curl で live を取得し LIVE_JSON= で渡す
```
⭐ builder(`_finalize_layout`)も deployer も **`edges_from_actions`+`relayout(elements, flow_rank, edges)` を
自動で呼ぶ**ので、接続性 tail-pass(§3.2)を有効にするための CLI 引数追加は不要。エンジンを触ったら必ず
JSON を再ビルドして `test_committed_json_matches_builder` を通す（焼込み座標とビルダー出力の乖離を防ぐ）。

**auth 規約**：トークンは `~/.config/domo-utils/<instance>.env`。サブシェルで
`set -a; . file; set +a`、INSTANCE ガード、存在確認は `test -n "${DOMO_TOKEN:+x}"`
（**シークレットに `${VAR:-fallback}` を使わない**）、ヘッダ `X-DOMO-Developer-Token`。
トークンをサブエージェント/引数に渡さない・エコーしない。トークン認証 Domo 呼出は main 単独。

## 8. 汎用化のヒント
本エンジンは DF 固有値をハードコードしていない（`relayout` は任意の `gui.elements` を取る）。
他 dataflow へ流用するには：(1) その dataflow を GET → `gui.elements` を `relayout` に渡す、
(2) **`flow_rank` を `dependsOn` から算出して渡す**（§3.0 の depth 式・§9 の再利用スニペット）＝
左→右フローを得る、(3) 定数（TILE_W/H・GAP・MAX_COLS・`TARGET_FLOW_ASPECT`）を対象キャンバスの密度へ
微調整、(4) デプロイヤの INSTANCE/DATAFLOW_ID を差し替え。所属回復が orphan 例外を出す場合は入力座標の
所属シグナルが壊れている（＝手置きが崩壊済み）ので、まず所属を人手で正すか membership を明示する。

---

## 9. 🔁 ナレッジシェア — フロー配向レイアウト（Sugiyama 系）の要点（他 AI 向け）
「有向グラフを左→右に読ませる」レイアウトは、Domo の Magic ETL に限らず**あらゆる DAG 可視化**
（パイプライン図・依存グラフ・ワークフロー）に効く汎用テクニック。核は 3 段：

1. **フロー信号を 1 次元へ落とす** — ノードの**最長入力パス長（トポロジカル深さ）**を求める。
   これが「入力からの距離」＝左→右の座標順序になる。エッジ（依存）さえ取れれば計算できる：
   ```python
   def flow_rank(nodes, edges_into):        # edges_into[n] = n の upstream ノード集合
       depth, visiting = {}, set()
       def d(n):
           if n in depth: return depth[n]
           ups = edges_into.get(n) or []
           if not ups: return depth.setdefault(n, 0)
           if n in visiting: return 0        # 循環辺は 0 に丸める安全弁（無限再帰防止）
           visiting.add(n); depth[n] = 1 + max(d(u) for u in ups if u in edges_into); visiting.discard(n)
           return depth[n]
       return {n: d(n) for n in nodes}
   ```
   ⚠ **手置き座標をフロー代理に使わない**（実測で最大 53% が実フローと逆＝ノイズ）。エッジが真実。

2. **深さ→列にマップし、単調性を構造で保証する** — 深さ昇順にグループを「縦シェルフ」で置く
   （上→下に積み、溢れたら**右の新列へ**）。列は投入順（＝深さ昇順）に必ず右へ増えるので、
   **x は深さに対し単調非減少**が**アルゴリズム的に保証**される（後段の検証頼みでなく構造で担保）。
   ソートやパッキングのバジェットを変えても並び順は不変なので、**compact 調整とフロー保証が直交**する。

3. **形（aspect）は別ノブで最適化** — フロー図は本質的に横長。面積最小だけ追うと縦長に落ちて
   「左→右」が読めなくなるので、**landscape を優先する aspect ペナルティ**を面積スコアに掛ける
   （`area * (1 + w*|log(aspect/target)|)`, target≈2.0）。これで「最も密な landscape」を選ぶ。

4. **接続性は“制約に固定されていない残りの自由度”だけで磨く** — フロー(x)・compact(bbox)を確定させた後、
   まだ動かせるのは **同一列内のノード縦順(Y)** だけ。ここは (a) x を触らない＝フロー不変、(b) 列高は順序不変量＝
   bbox 不変、(c) ノードは剛体移動＝重なり/所属不変、という**三重の「効かない」保証**が揃う唯一の軸。だから
   「線を短く／交差を減らす」を**他の全ハード制約をゼロ悪化で**達成できる。目的関数は**素直に総エッジ長**にする
   （交差数やバリセンタの代理でなく）＝長い線ほど無関係ノードを薙ぐので、総長最小化が“無関係ノードを貫く線”も
   一緒に減らす。列サイズが小さければ**全順列**（列内大域最適）、大きければ隣接 swap。列間結合は**座標降下**で回す。

**検証は 2 種を分離**：幾何健全性（重なり/はみ出し 0）と**フロー単調性**（深さ昇順で x 非減少・
入力群が出力群の左）。後者を `verify_flow` として独立に持つと、compact 調整でフローが壊れた瞬間に
落ちる回帰網になる。**「入力=左・出力=右」は over-claim しやすいので必ず機械検証で裏打ちする**
（主張だけ書かない）。フォールバック（フロー信号が無い場合）は面積降順パッキングで compact のみ担保し、
その時は「左→右」を主張しない — これも over-claim 回避の一部。

**🧭 メタ教訓（over-claim 補正・“正しいレバーを試したか”）**：接続性改善の探索で、当初「赤エッジ数は 107 で不変」
「Pareto 勝者なし」と結論しかけたが、それは**セクション内タイル行の軸**でしか試していなかった＝**間違った自由度**。
実際の勝ちレバーは**セクション順(Y)の軸**で、そこでは red 107→93・交差 −34.5%・bbox 不変の明確な勝ちがあった。
教訓：**「効かない」と結論する前に、動かせる自由度を列挙し尽くしたか自問する**（membership/x/bbox に固定された軸で
試して「不変」と言うのは自明であって発見ではない）。加えて **direct-objective（総エッジ長）は proxy（バリセンタ/
交差数）に勝つ**ことが多い。そして**「枯渇した/これ以上縮まない」も over-claim**：`max_edge_len` の flow 強制束は
本レバーで不可約だが、それは「別レバー（rank 再割当・業務ゲート）なら動く」ことと両立する＝**不在の証明ではない**。
