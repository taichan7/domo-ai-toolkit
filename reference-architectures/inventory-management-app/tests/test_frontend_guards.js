#!/usr/bin/env node
/**
 * inventory-management-app フロントエンド（pro-code/app.js）の stored-XSS 回帰防止＝ソースレベル静的ガード。
 *
 * 実行: node inventory-management-app/tests/test_frontend_guards.js   （node:test が自動実行）
 *   別ファイルを対象にするには INV_APP_JS=/path/to/app.js を渡す（prove-the-bug 用）。
 *
 * なぜこのテストか:
 *   escapeHtml が単体で正しく実体参照化することと、innerHTML へ差し込む各 sink が実際に
 *   escapeHtml / escapeAttribute を呼んでいることは別問題である。姉妹アプリ equipment-inventory-app
 *   では escapeHtml が在るのに sink 側が呼び忘れて stored-XSS になった（commit 069fff5b）。同型の
 *   sink-enforcement ガードは owned FE の兄弟（support-center 1f35ea09 / dataset-exporter 8d6b957d /
 *   asset-lifecycle aed43f78 / rag+security-qa 000f6408 / equipment 069fff5b）＋共通祖先の雛形
 *   （templates/pro-code-app b534b4ab）に既に在るが、この汎用配布リファレンスアプリだけ
 *   sink-enforcement テストが無かった（従来は boot（test_boot_sequence.js）と shell/レイアウト
 *   （test_frontend_shell.js）のみで、FE の escape 呼び出しを固定するものが無かった）。品目名・
 *   ロケーション名・担当者名・理由メモ・AI在庫コメント（LLM 出力）等、AppDB / People API 由来の
 *   untrusted 文字列を多数の innerHTML sink へ流すため、sink が escapeHtml を落とす退行（＝XSS 穴の
 *   再発）を、この app を一切変更せず（再 publish 不要の追加専用テスト）source レベルで検知する。
 *
 * 方式（support-center の test_frontend_guards.js と同流儀＝ソースレベル静的ガード）:
 *   app.js は素のブラウザ IIFE（トップレベルで DOM を触る）ため丸ごと require すると throw する。
 *   そこで対象関数の本体だけを波括弧マッチで抜き出し、①escapeHtml/escapeAttribute(<untrusted 式>) を
 *   positive assert.match、②escapeHtml 非経由の生の差し込み（このアプリはほぼテンプレートリテラルなので
 *   生 `${field}`）を assert.doesNotMatch の正負両建てで固定する。
 *
 * このアプリ固有の注意:
 *   - escapeHtml は **DOM ベース**（`node.textContent = String(value ?? ''); return node.innerHTML`）で、
 *     ブラウザの textContent→innerHTML 往復で実体参照化する。純関数の string 版（support-center 等）と
 *     違い document が要るため vm での実挙動テストは行わず、代わりに実装形（DOM 往復＋`?? ''` sentinel）
 *     を静的に固定する（手組み replace への退行＝取りこぼしを防ぐ）。escapeAttribute は escapeHtml を
 *     包んだ上で `"`→&quot; / `'`→&#39; を追加（属性値コンテキストの引用符ブレイクアウト封鎖）。
 *   - 大半の sink は**テンプレートリテラル**（`${escapeHtml(field)}`）。よって生差し込みの退行形は
 *     `${field}`（escapeHtml を挟まない生の補間）である。
 *   - **wrapped-concat（memory nuance f）**: reviewTransaction の value と masterRowHtml の label は
 *     内部で生の `location_name`/`item_name` を連結して組み立てるが、sink 側で **文字列全体を一括 escape**
 *     （`escapeHtml(value)` / `escapeAttribute(label)`）するため安全。naive な `+ location_name` 負ガードは
 *     この安全な現状で false-fire するので入れず、sink の一括 escape を positive で固定する。
 *   - **pre-escaped 束縛**: aiNoteCards の placeLabel / masterTableHtml の body は escape 済みの部分文字列を
 *     組んでから `${placeLabel}` / `${body}` を差す。これらは束縛経由なので `${placeLabel}` 等は禁止せず、
 *     束縛を作る側の escapeHtml と、生のソースフィールド（`${row.ai_summary}` 等）の不在を固定する。
 *
 * このテストが固定する innerHTML sink（＝untrusted 値を escape 経由で差し込む経路。列挙して分母を明示する）:
 *   リーフ builder ＝ optionHtml / reviewTransaction / renderHistory / renderPager / showChartTooltip /
 *   renderMasterRuleOptions / aiNoteCards / masterTableHtml / masterRowHtml。
 *   ドリルダウン詳細ペインの builder ＝ detailDefinition（reason / operator_name / notification_body /
 *   error_message ＝ 姉妹アプリ equipment-inventory-app 069fff5b と同じ field class）・detailTable（全
 *   ドリルダウン表の item_name / location_name）・detailMeta（監査参照ID）。
 *   ダッシュボードの builder ＝ barRowHtml（品目/ロケーション表示名 row.label）・renderDashboard 内の
 *   kpi-grid / 在庫不足 / 滞留 の行ビルダ（row.label / item_name / location_name）・renderRecent（直近の登録）・
 *   dashboardEmpty（検索ボックスの反射入力 shown）・toast（品目/拠点名を含みうるメッセージ）・
 *   renderStockPreview（品目マスタの自由入力 unit）。
 *   ⚠ 抽出上の注意: detailDefinition / detailMeta / reviewTransaction の `<dd>${escapeHtml(value)}</dd>` と、
 *     detailTable / masterRowHtml の `<td>${escapeHtml(value)}</td>` は互いに byte-identical。必ず
 *     extractFunction(<関数名>) で関数スライスへ限定して突合する（全文 regex は取り違える＝memory nuance g）。
 *     renderDashboard 内の在庫不足/滞留/KPI 行ビルダは無名クロージャで個別抽出できないため、外側の
 *     renderDashboard を抽出し sink コンテキスト（`class="kpi-label"` / `<strong>` / `<small>`）限定で固定する。
 *
 * 意図的にガード対象から除外する sink（memory nuance e＝安全でない/注入不能な sink を「済み」と偽らない）:
 *   - **renderTestQrCodes**（app.js:267/271）: `${svg}`（内製 QR 生成器 InventoryQR.toSvg の出力）を生補間する。
 *     payload は HTML に静的に焼かれた data-qr 属性（作者管理・runtime untrusted でない）で、コメント通り
 *     起動時に一度だけ描くサンプル表示。生 `${svg}` を「escapeHtml 済み」と偽って positive 固定はしない。
 *     ⚠ これは data-qr が作者静的である限りの前提。data-qr が runtime データで埋まるなら、`${svg}` と
 *     InventoryQR の title（payload を埋め込む）は再検討を要する。
 *   - **真に数値のみの補間**（number.format、detailStats・balanceFlow・棒トラック幅）は対象外。
 *     日付formatterは不正値をそのまま返す分岐があるため、数値と同じ扱いにしない。
 *     トレンドの日付HTMLは下の実描画回帰テストで悪意のある文字列と正常日付を検証する。
 *     ※ barRowHtml と kpi-grid は「数値のみ」に見えて実際は untrusted な**表示名** row.label を escape して
 *     いるため**除外しない**＝上で固定する（初版はここを number-only と誤記して両者を取りこぼしていた。
 *     adversarial-refute で検出＝両刃の under-claim を是正）。
 *   - **静的クリア/静的リテラル**（`innerHTML = ''`、空状態メッセージ）と、別関数で組んだ**済み** markup を
 *     innerHTML へ差すだけの wrapper（fillDetailPane / fillContextDetail の detail-content 等）自身は untrusted な
 *     補間を持たない。ただしその markup を**組む** builder（detailDefinition / detailTable / detailMeta）は上で固定する。
 *
 * 抽出の前提:
 *   波括弧カウントは文字列/正規表現/コメント内に不均衡な波括弧が無いことを仮定する。対象関数は本体内の
 *   波括弧が均衡しているため安全。抽出ミス時は末尾 '}' ガードで即落ちる。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// prove-the-bug では INV_APP_JS で退行させたコピーを指せる。既定は同梱の app.js。
const APP_PATH = process.env.INV_APP_JS || path.join(__dirname, '..', 'pro-code', 'app.js');
const SOURCE = fs.readFileSync(APP_PATH, 'utf8');

/**
 * 名前付き関数 `function <name>(...) { ... }` の完全なソース文字列を波括弧の対応で抜き出す。
 * @param {string} name 関数名
 * @returns {string} `function name(...){...}` の全文
 */
function extractFunction(name) {
  const sig = new RegExp('function\\s+' + name + '\\s*\\(');
  const start = SOURCE.search(sig);
  assert.ok(start >= 0, `関数 ${name} が app.js に見つからない`);
  const open = SOURCE.indexOf('{', start);
  assert.ok(open > start, `関数 ${name} の本体開始 { が見つからない`);
  let depth = 0;
  let end = -1;
  for (let i = open; i < SOURCE.length; i++) {
    const ch = SOURCE[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) { end = i + 1; break; }
    }
  }
  assert.ok(end > open, `関数 ${name} の本体終了 } が見つからない`);
  const text = SOURCE.slice(start, end);
  assert.ok(text.endsWith('}'), `関数 ${name} の抽出が } で終わっていない（抽出ミス）`);
  return text;
}

// ---- escapers（XSS: innerHTML / 属性値へ差し込む untrusted 値の無害化）----
// このアプリの escapeHtml は DOM ベース（textContent→innerHTML 往復）。document 依存で vm 実行できないため
// 実装形を静的に固定する（手組み文字列 replace への退行＝取りこぼしを防ぐ）。

test('escapeHtml は DOM 往復（textContent→innerHTML）で実体参照化し ?? sentinel で null/undefined のみ空に潰す', () => {
  const src = extractFunction('escapeHtml');
  // textContent へ代入 → innerHTML を読む、というブラウザ標準の往復エンコードを使う（自前 replace でない）。
  assert.match(src, /\.textContent\s*=\s*String\(\s*value\s*\?\?\s*''\s*\)/, 'textContent = String(value ?? \'\') 形が崩れている');
  assert.match(src, /return\s+[A-Za-z_$][\w$]*\.innerHTML/, 'innerHTML を読み取って返す DOM 往復が失われている');
  // `?? ''` は null/undefined のみ空文字化し 0/false を保持する sentinel（|| への退行を禁止）。
  assert.doesNotMatch(src, /value\s*\|\|\s*''/, 'value || \'\' への退行（0/false を空へ潰す）');
});

test('escapeAttribute は escapeHtml を包み " と \' を追加でエンティティ化する（属性ブレイクアウト封鎖）', () => {
  const src = extractFunction('escapeAttribute');
  assert.match(src, /escapeHtml\(\s*value\s*\)/, 'escapeAttribute が escapeHtml を経由していない');
  assert.match(src, /replace\(\s*\/"\/g\s*,\s*'&quot;'\s*\)/, '" → &quot; の置換が無い（属性値の " ブレイクアウト）');
  assert.match(src, /replace\(\s*\/'\/g\s*,\s*'&#39;'\s*\)/, "' → &#39; の置換が無い（属性値の ' ブレイクアウト）");
});

// ---- innerHTML シンクが untrusted 値を必ず escapeHtml / escapeAttribute 経由で差し込む（XSS 退行の source ガード）----

test('optionHtml は品目/ロケーションの code を escapeAttribute、name/code/meta を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('optionHtml');
  assert.match(src, /data-code="\$\{escapeAttribute\(\s*code\s*\)\}"/, 'data-code 属性に生の code（属性ブレイクアウト）');
  assert.match(src, /escapeHtml\(\s*name\s*\)/, 'name（品目名/ロケーション名）が escape されていない');
  assert.match(src, /escapeHtml\(\s*code\s*\)/, 'code（表示テキスト）が escape されていない');
  assert.match(src, /escapeHtml\(\s*meta\s*\)/, 'meta（カテゴリ/ゾーン）が escape されていない');
  // 生の ${name} / ${meta} / ${code}（escapeHtml 非経由の補間）を差し込まない。
  assert.doesNotMatch(src, /\$\{\s*name\s*\}/, '生の name を差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*meta\s*\}/, '生の meta を差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*code\s*\}/, '生の code を差し込んでいる（XSS 退行）');
});

test('reviewTransaction は確認リストの label/value を escapeHtml 経由で差し込む（value は一括 escape）', () => {
  const src = extractFunction('reviewTransaction');
  // value は内部で `${location_name} (${location_code})` 等を生連結して組むが、sink で一括 escape する
  //（wrapped-concat）。よって value 側の生連結は禁止せず、sink の escapeHtml(value) を固定する。
  assert.match(src, /escapeHtml\(\s*label\s*\)/, 'label が escape されていない');
  assert.match(src, /escapeHtml\(\s*value\s*\)/, 'value（品目名/ロケーション名/理由を含む）が escape されていない');
  assert.doesNotMatch(src, /<dd>\$\{\s*value\s*\}/, '生の value を <dd> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<dt>\$\{\s*label\s*\}/, '生の label を <dt> へ差し込んでいる（XSS 退行）');
});

test('renderHistory は通知/取引の行で item_name・location_name・reason・operator・subject を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('renderHistory');
  // 2 系統の行ビルダ（通知履歴 / 取引履歴）を含む。両系統に共通の untrusted フィールドを固定する。
  assert.match(src, /escapeAttribute\(\s*row\.item_name\b/, 'aria-label の item_name が escapeAttribute されていない');
  assert.match(src, /escapeHtml\(\s*row\.item_name\b/, 'item_name が escape されていない');
  assert.match(src, /escapeHtml\(\s*row\.location_name\b/, 'location_name が escape されていない');
  assert.match(src, /escapeHtml\(\s*row\.reason\b/, 'reason（取引メモ・自由入力）が escape されていない');
  assert.match(src, /escapeHtml\(\s*row\.operator_name\b/, 'operator_name（担当者名）が escape されていない');
  assert.match(src, /escapeHtml\(\s*row\.notification_subject\b/, 'notification_subject（通知件名）が escape されていない');
  // 生差し込みの負ガードは **HTML sink コンテキストに限定** する（`<td>` セル / `aria-label="` 属性）。
  // renderHistory は同じ関数内に検索ハイスタック（`${row.item_name || ''}` を並べ .includes(query) で
  // 突合するだけの非 sink 文字列）を持つため、関数全体への裸 `${row.field}` 負ガードは false-fire する
  // （memory nuance f/g）。sink の escapeHtml/escapeAttribute を落とすと `<td>${row.field}` /
  // `aria-label="${row.field}` になる — その退行だけを捕える。
  assert.doesNotMatch(src, /<td>\$\{\s*row\.item_name\b/, '生の row.item_name を <td> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /aria-label="\$\{\s*row\.item_name\b/, '生の row.item_name を aria-label へ差し込んでいる（属性ブレイクアウト）');
  assert.doesNotMatch(src, /<td>\$\{\s*row\.location_name\b/, '生の row.location_name を <td> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<td>\$\{\s*row\.reason\b/, '生の row.reason を <td> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<td>\$\{\s*row\.operator_name\b/, '生の row.operator_name を <td> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<td>\$\{\s*row\.notification_subject\b/, '生の row.notification_subject を <td> へ差し込んでいる（XSS 退行）');
});

test('renderPager はページャの statusText を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('renderPager');
  assert.match(src, /escapeHtml\(\s*statusText\s*\)/, 'statusText が escape されていない');
  assert.doesNotMatch(src, /\$\{\s*statusText\s*\}/, '生の statusText を差し込んでいる（XSS 退行）');
});

test('showChartTooltip はツールチップの title/detail を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('showChartTooltip');
  assert.match(src, /escapeHtml\(\s*title\s*\)/, 'title が escape されていない');
  assert.match(src, /escapeHtml\(\s*detail\s*\)/, 'detail が escape されていない');
  assert.doesNotMatch(src, /\$\{\s*title\s*\}/, '生の title を差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*detail\s*\}/, '生の detail を差し込んでいる（XSS 退行）');
});

test('renderMasterRuleOptions はセレクト option の value を escapeAttribute、表示名を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('renderMasterRuleOptions');
  assert.match(src, /value="\$\{escapeAttribute\(\s*row\.location_code\s*\)\}"/, 'location option の value が escapeAttribute されていない');
  assert.match(src, /value="\$\{escapeAttribute\(\s*row\.item_code\s*\)\}"/, 'item option の value が escapeAttribute されていない');
  assert.match(src, /escapeHtml\(\s*row\.location_name\b/, 'location_name（表示名）が escape されていない');
  assert.match(src, /escapeHtml\(\s*row\.item_name\b/, 'item_name（表示名）が escape されていない');
  // option の value 属性・表示テキストへ生フィールドを差し込まない（属性ブレイクアウト/タグ注入）。
  assert.doesNotMatch(src, /value="\$\{\s*row\.location_code\s*\}"/, '生の location_code を value へ差し込んでいる');
  assert.doesNotMatch(src, /value="\$\{\s*row\.item_code\s*\}"/, '生の item_code を value へ差し込んでいる');
  assert.doesNotMatch(src, /\$\{\s*row\.location_name\b/, '生の location_name を差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*row\.item_name\b/, '生の item_name を差し込んでいる（XSS 退行）');
});

test('aiNoteCards は AI在庫コメント（LLM 出力 ai_summary）と品目名/拠点名を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('aiNoteCards');
  // ai_summary は分析 DataSet 経由の LLM 生成テキスト＝最も untrusted。innerHTML へ移す u2s 型の穴を封鎖。
  assert.match(src, /escapeHtml\(\s*String\(\s*row\.ai_summary/, 'ai_summary（LLM 出力）が escape されていない');
  assert.match(src, /escapeHtml\(\s*item\s*\)/, 'item（品目名）が escape されていない');
  assert.match(src, /escapeHtml\(\s*place\s*\)/, 'place（拠点名）が escape されていない');
  assert.match(src, /escapeHtml\(\s*itemCode\s*\)/, 'itemCode が escape されていない');
  // 生の ${row.ai_summary} / ${row.item_name}（束縛前の生フィールド）を本文へ差し込まない。
  assert.doesNotMatch(src, /\$\{\s*row\.ai_summary\b/, '生の row.ai_summary を差し込んでいる（LLM 出力の XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*row\.item_name\b/, '生の row.item_name を差し込んでいる（XSS 退行）');
});

test('masterTableHtml はヘッダセルを escapeHtml 経由で差し込む', () => {
  const src = extractFunction('masterTableHtml');
  assert.match(src, /escapeHtml\(\s*header\s*\)/, 'header が escape されていない');
  assert.doesNotMatch(src, /<th[^>]*>\$\{\s*header\s*\}/, '生の header を <th> へ差し込んでいる（XSS 退行）');
});

test('masterRowHtml はセル値を escapeHtml、code/label を escapeAttribute 経由で差し込む（label は一括 escape）', () => {
  const src = extractFunction('masterRowHtml');
  assert.match(src, /escapeHtml\(\s*value\s*\)/, 'セル値（マスタデータ）が escape されていない');
  assert.match(src, /data-master-edit="\$\{escapeAttribute\(\s*code\s*\)\}"/, 'data-master-edit へ生の code（属性ブレイクアウト）');
  // label は呼び出し側で `${name} / ${name}` を生連結して組むが、ここで一括 escapeAttribute する（wrapped-concat）。
  assert.match(src, /aria-label="\$\{escapeAttribute\(\s*label\s*\)\}/, 'aria-label の label が escapeAttribute されていない');
  assert.doesNotMatch(src, /<td>\$\{\s*value\s*\}<\/td>/, '生の value を <td> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /aria-label="\$\{\s*label\s*\}/, '生の label を aria-label へ差し込んでいる（属性ブレイクアウト）');
});

// ---- ドリルダウン詳細ペインの builder（fillDetailPane/fillContextDetail の innerHTML wrapper へ流す実 escape 点）----
// wrapper 自身は済み markup を差すだけだが、その markup を組む detailDefinition/detailTable/detailMeta が
// untrusted 値（reason・operator_name・通知本文・エラー文・item_name/location_name・監査ID）の escape 点。

test('detailDefinition はドリルダウン詳細の label/value（reason・operator・通知本文・エラー文＝069fff5b と同 field class）を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('detailDefinition');
  assert.match(src, /escapeHtml\(\s*label\s*\)/, 'label が escape されていない');
  assert.match(src, /escapeHtml\(\s*value\s*\)/, 'value（reason/operator_name/notification_body/error_message を含む）が escape されていない');
  // `<dd>${escapeHtml(value)}</dd>` は reviewTransaction:644 / detailMeta と byte-identical。関数スライス限定で突合する。
  assert.doesNotMatch(src, /<dt>\$\{\s*label\s*\}/, '生の label を <dt> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<dd>\$\{\s*value\s*\}/, '生の value を <dd> へ差し込んでいる（XSS 退行）');
});

test('detailTable は全ドリルダウン表の header とセル値（item_name/location_name）を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('detailTable');
  // renderBalanceDetails / renderDetailTransactions / openKpiDetail の在庫不足表が共通で通す escape choke point。
  assert.match(src, /<th[^>]*>\$\{escapeHtml\(\s*header\s*\)\}<\/th>/, 'header が escape されていない');
  assert.match(src, /<td>\$\{escapeHtml\(\s*value\s*\)\}<\/td>/, 'セル値（品目名/ロケーション名）が escape されていない');
  assert.doesNotMatch(src, /<th[^>]*>\$\{\s*header\s*\}/, '生の header を <th> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<td>\$\{\s*value\s*\}<\/td>/, '生の value を <td> へ差し込んでいる（XSS 退行）');
});

test('detailMeta は監査参照値（取引ID/リクエストID/通知ID）を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('detailMeta');
  assert.match(src, /escapeHtml\(\s*label\s*\)/, 'label が escape されていない');
  assert.match(src, /escapeHtml\(\s*value\s*\)/, 'value（AppDB 由来のID）が escape されていない');
  assert.doesNotMatch(src, /<dd>\$\{\s*value\s*\}/, '生の value を <dd> へ差し込んでいる（XSS 退行）');
});

// ---- ダッシュボードの builder（renderDashboardPanel / kpi-grid / trend の innerHTML へ流す）----
// barRowHtml と kpi-grid は数値でなく untrusted な表示名 row.label を escape する（初版ヘッダの number-only 誤記を是正）。

test('barRowHtml は品目/ロケーションの棒ラベル row.label（表示名＝数値でない）を escapeHtml/escapeAttribute 経由で差し込む', () => {
  const src = extractFunction('barRowHtml');
  // row.label は品目名/ロケーション名（untrusted）。line 913 の trend チャート（number.format/formatDisplayDate）とは別物。
  assert.match(src, /class="bar-label">\$\{escapeHtml\(\s*row\.label\s*\)\}/, 'bar-label の row.label が escape されていない');
  assert.match(src, /data-tooltip-title="\$\{escapeAttribute\(\s*row\.label\s*\)\}/, 'tooltip-title の row.label が escapeAttribute されていない');
  assert.doesNotMatch(src, /class="bar-label">\$\{\s*row\.label\s*\}/, '生の row.label を bar-label へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /data-tooltip-title="\$\{\s*row\.label\s*\}/, '生の row.label を tooltip-title へ差し込んでいる（属性ブレイクアウト）');
});

test('renderDashboard inline builders（kpi-grid/在庫不足/滞留の行ビルダ）は label・item_name・location_name を escape 経由で差し込む', () => {
  const src = extractFunction('renderDashboard');
  // kpi-grid（無名 .map）: row.label は DataSet 由来の表示名。sink コンテキスト（class="kpi-label"）限定で固定する
  //（barRowHtml も renderDashboard 内にネストされ row.label を escape するため、class 限定で kpi と bar を弁別する）。
  assert.match(src, /class="kpi-label">\$\{escapeHtml\(\s*row\.label\s*\)\}/, 'kpi-label の row.label が escape されていない');
  assert.doesNotMatch(src, /class="kpi-label">\$\{\s*row\.label\s*\}/, '生の row.label を kpi-label へ差し込んでいる（XSS 退行）');
  // 在庫不足/滞留の行ビルダ（無名クロージャ）: item_name/location_name。両ビルダ共通の sink 形を固定する。
  assert.match(src, /escapeAttribute\(\s*row\.item_name\s*\|\|\s*row\.item_code\s*\)/, '行 tooltip の item_name が escapeAttribute されていない');
  assert.match(src, /<strong>\$\{escapeHtml\(\s*row\.item_name\s*\|\|\s*row\.item_code\s*\)\}<\/strong>/, '行見出しの item_name が escape されていない');
  assert.match(src, /<small>\$\{escapeHtml\(\s*row\.location_name\s*\|\|\s*row\.location_code\s*\)\}/, '行の location_name が escape されていない');
  // sink コンテキスト限定の負ガード（1ビルダだけ escape を落とす退行も捕える。tooltip の wrapped-concat には false-fire しない）。
  assert.doesNotMatch(src, /<strong>\$\{\s*row\.item_name\b/, '生の row.item_name を <strong> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<small>\$\{\s*row\.location_name\b/, '生の row.location_name を <small> へ差し込んでいる（XSS 退行）');
});

test('日付の形式が不正でもトレンドのHTMLは実行可能な要素を作らず通常の日付を保つ', () => {
  const payload = '<img src="data:image/png,broken" onerror="document.body.dataset.xss=1">';
  const encode = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  function render(value) {
    const context = {
      state: {dashboardRows: [{record_type: 'TREND', date_key: value, inbound_quantity: 4, outbound_quantity: 2}], dashboardDrilldowns: {}},
      elements: {'kpi-grid': {}, 'trend-chart': {}},
      config: {analytics: {trendWindowDays: 7, dormantThresholdDays: 30}},
      number: new Intl.NumberFormat('ja-JP'),
      escapeHtml: encode, escapeAttribute: encode,
      filterDashboardRows: (rows) => rows, renderDashboardPanel: () => {},
      dashboardEmpty: (markup) => markup, emptyHtml: () => '',
      renderAiNotes: () => {}, scheduleDashboardEqualize: () => {},
    };
    vm.runInNewContext(['formatDisplayDate', 'formatShortDate', 'barPct', 'renderDashboard'].map(extractFunction).join('\n') + '\nrenderDashboard();', context);
    return context.elements['trend-chart'].innerHTML;
  }
  const hostile = render(payload);
  if (process.env.INV_TREND_RENDER_OUT) fs.writeFileSync(process.env.INV_TREND_RENDER_OUT, '<!doctype html><html lang="ja"><body>' + hostile + '</body></html>');
  assert.doesNotMatch(hostile, /<img\b/i);
  assert.ok(hostile.includes('<small>' + encode(payload) + '</small>'));
  assert.match(render('2026-10-15'), /<small>10\/15<\/small>/);
});

test('renderRecent は直近の登録行で item_name/location_name を escapeHtml、aria-label を escapeAttribute 経由で差し込む', () => {
  const src = extractFunction('renderRecent');
  assert.match(src, /aria-label="\$\{escapeAttribute\(\s*row\.item_name\s*\|\|\s*row\.item_code\s*\)\}/, 'aria-label の item_name が escapeAttribute されていない');
  assert.match(src, /<strong>\$\{escapeHtml\(\s*row\.item_name\s*\|\|\s*row\.item_code\s*\)\}<\/strong>/, 'item_name が escape されていない');
  assert.match(src, /<small>\$\{escapeHtml\(\s*row\.location_name\s*\|\|\s*row\.location_code\s*\)\}/, 'location_name が escape されていない');
  assert.doesNotMatch(src, /aria-label="\$\{\s*row\.item_name\b/, '生の row.item_name を aria-label へ差し込んでいる（属性ブレイクアウト）');
  assert.doesNotMatch(src, /<strong>\$\{\s*row\.item_name\b/, '生の row.item_name を <strong> へ差し込んでいる（XSS 退行）');
  assert.doesNotMatch(src, /<small>\$\{\s*row\.location_name\b/, '生の row.location_name を <small> へ差し込んでいる（XSS 退行）');
});

test('dashboardEmpty は検索ボックスの反射入力 shown を escapeHtml 経由で差し込む（reflected XSS 退行の source ガード）', () => {
  const src = extractFunction('dashboardEmpty');
  assert.match(src, /escapeHtml\(\s*shown\s*\)/, 'shown（検索ボックスの反射入力）が escape されていない');
  assert.doesNotMatch(src, /\$\{\s*shown\s*\}/, '生の shown を差し込んでいる（reflected XSS 退行）');
});

test('toast はメッセージ（品目名/拠点名を含みうる）を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('toast');
  // submitTransaction / scan-select 等の呼び出し側が item_name/location_name を message へ連結する（wrapped-concat）。
  assert.match(src, /escapeHtml\(\s*message\s*\)/, 'message が escape されていない');
  assert.doesNotMatch(src, /<span>\$\{\s*message\s*\}<\/span>/, '生の message を <span> へ差し込んでいる（XSS 退行）');
});

test('renderStockPreview は品目マスタの unit を escapeHtml 経由で差し込む', () => {
  const src = extractFunction('renderStockPreview');
  // unit 以外の補間は number.format（数値のみ）と静的 suffix。untrusted なのは品目マスタ自由入力の unit。
  assert.match(src, /escapeHtml\(\s*unit\s*\)/, 'unit（品目マスタの自由入力）が escape されていない');
  assert.doesNotMatch(src, /\$\{\s*unit\s*\}/, '生の unit を差し込んでいる（XSS 退行）');
});
