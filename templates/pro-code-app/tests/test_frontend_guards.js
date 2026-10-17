#!/usr/bin/env node
/**
 * pro-code アプリ雛形（templates/pro-code-app/app.js）の DOM-XSS 回帰防止＝ソースレベル静的ガード。
 *
 * 実行: node templates/pro-code-app/tests/test_frontend_guards.js   （node:test が自動実行）
 *   別ファイルを対象にするには TEMPLATE_APP_JS=/path/to/app.js を渡す（prove-the-bug 用）。
 *
 * なぜこのテストか（＝なぜ雛形にこそガードを置くか）:
 *   この app.js は「新しい pro-code アプリを作るとき最初にコピーされる骨格」である。ここに
 *   untrusted 値を innerHTML へ素で差す退行が入ると、以後この雛形から派生する**すべての**アプリに
 *   XSS パターンが伝播する。実際 escapeHtml が在るのに sink 側が呼び忘れて stored-XSS になった事故が
 *   派生アプリ equipment-inventory-app（commit 069fff5b）で起き、その後 rag-chat-app /
 *   security-qa-rag-chat-app（000f6408）・domo-support/new/support-center（1f35ea09）・dataset-exporter で
 *   sink ガードを横展開した。それら 6 アプリの**共通祖先**である本雛形にはガードが無かった——本ファイルで
 *   その最上流の穴を塞ぐ（app.js は一切変更しない＝再 publish 不要の追加専用テスト。派生時にこの
 *   tests/ ごとコピーすれば新アプリもガードを継承できる）。
 *
 * この雛形の untrusted-sink の実像（7 つの innerHTML のうち動的補間は 1 箇所のみ）:
 *   - renderTable … データセットの列名（col）とセル値（cell＝Data/SQL API 由来の untrusted 値）を
 *     `th.textContent = col` / `td.textContent = String(cell)` と **textContent**（createElement→
 *     appendChild）で描き、innerHTML を一切通さない（dataset-exporter renderPreviewTable と同型の
 *     textContent 不変条件）。この関数の innerHTML は `thead.innerHTML=''` / `tbody.innerHTML=''` の
 *     クリアだけで補間は無い。ガードは textContent 経由を positive で要求し、innerHTML 代入へ `${...}`
 *     補間が混入しない（＝untrusted データが innerHTML に乗らない）ことを doesNotMatch で固定する。
 *   - wireButtons の "Query failed" … err.message は失敗した SQL（textarea #sqlInput のユーザー入力）や
 *     サーバのエラー文を反映しうる動的値。innerHTML を書く setEmptyState へ渡す前に
 *     `escapeHtml(err.message || String(err))` を通す。ガードは escapeHtml 経由を positive で要求し、
 *     生の `${err.message}` / `${err}`（escapeHtml 非経由）補間を doesNotMatch で禁止する。
 *
 * スコープ（本ガードで「安全」と主張する範囲）:
 *   setEmptyState 自身は「STATIC/信頼できるマークアップだけを受ける」helper（本体のコメントと
 *   loadPreview の <strong>/<code> ヒントがその契約）。動的値は呼び出し側で escapeHtml 済みにしてから
 *   渡すのが不変条件（"Query failed" 呼び出しがその実例）。本ガードは setEmptyState の中身までは縛らず、
 *   「動的値を innerHTML へ運ぶ 2 関数（renderTable / wireButtons）の sink 安全」を回帰から守る。
 *
 * 方式（dataset-exporter / equipment / RAG・support-center の同型テストと同流儀）:
 *   app.js は素のブラウザ IIFE（トップレベルで DOM を触る）ため丸ごと require すると throw する。
 *   そこで対象関数の本体だけを波括弧マッチで抜き出し、正規表現で不変条件を正負両建てで固定する。
 *   escapeHtml だけは DOM/グローバルに触れない純関数なので、本体を抽出して実行し実挙動も固定する。
 *
 * 抽出の前提:
 *   波括弧カウントは文字列/正規表現/コメント内に不均衡な波括弧が無いことを仮定する。対象関数は
 *   本体内の波括弧が均衡しているため安全。抽出ミス時は末尾 '}' ガードで即落ちる。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

// prove-the-bug では TEMPLATE_APP_JS で退行させたコピーを指せる。既定は同梱の app.js。
const APP_PATH = process.env.TEMPLATE_APP_JS || path.join(__dirname, '..', 'app.js');
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

// ---- renderTable（データセットの列名/セル値を textContent で描く不変条件）----
test('renderTable は列名/セル値を textContent で描き innerHTML へ補間しない（untrusted データの XSS 不変条件）', () => {
  const src = extractFunction('renderTable');
  // ヘッダ列名（col）・データセル（cell）はいずれも textContent 経由で DOM へ入れる。
  assert.match(src, /th\.textContent\s*=\s*col\b/, 'ヘッダ列名が textContent で描かれていない');
  assert.match(src, /td\.textContent\s*=\s*[^;]*\bcell\b/, 'セル値 cell が textContent で描かれていない');
  // この関数の innerHTML はクリア（= ''）だけ＝動的補間 ${...} を innerHTML へ混ぜない。
  assert.doesNotMatch(src, /innerHTML\s*=\s*[^;\n]*\$\{/, 'innerHTML 代入に ${...} 補間が混入（untrusted データが innerHTML に乗る恐れ＝XSS 退行）');
  // セル要素そのものへ innerHTML を使わない（th/td/tr は createElement＋textContent）。
  assert.doesNotMatch(src, /\bth\.innerHTML/, 'th に innerHTML を使っている（textContent 不変条件の破れ）');
  assert.doesNotMatch(src, /\btd\.innerHTML/, 'td に innerHTML を使っている（textContent 不変条件の破れ）');
  assert.doesNotMatch(src, /\btr\.innerHTML/, 'tr に innerHTML を使っている（textContent 不変条件の破れ）');
  // 負アサーションが空振りでない裏取り：表領域のクリアは静的なので存在してよい。
  assert.match(src, /thead\.innerHTML\s*=\s*''/, 'thead のクリアが想定形でない');
  assert.match(src, /tbody\.innerHTML\s*=\s*''/, 'tbody のクリアが想定形でない');
});

// ---- wireButtons（"Query failed" の動的 err を escapeHtml 経由で sink へ差す）----
test('wireButtons は err.message を escapeHtml 経由で setEmptyState へ渡す（生補間の禁止）', () => {
  const src = extractFunction('wireButtons');
  // 動的値（SQL/エラー文＝ユーザー入力を反映しうる）は escapeHtml を通してから innerHTML sink へ。
  assert.match(src, /escapeHtml\(\s*err\.message/, 'err.message を escapeHtml 経由にしていない');
  // 生の ${err.message} / ${err}（escapeHtml 非経由）を差さない。実コードは `${escapeHtml(...`
  // と `${` の直後が escapeHtml なので、下の否定は false-fire しない。
  assert.doesNotMatch(src, /\$\{\s*err\.message/, '生の err.message を補間している（XSS 退行）');
  assert.doesNotMatch(src, /\$\{\s*err\s*\}/, '生の err を補間している（XSS 退行）');
});

// ---- escapeHtml（純関数：5 つの HTML 特殊文字を確実に実体参照化する実挙動）----
test('escapeHtml は 5 つの HTML 特殊文字をすべて実体参照化する（実挙動）', () => {
  const src = extractFunction('escapeHtml');
  // escapeHtml は DOM/グローバルに触れない純関数なので抽出して実行できる。
  // これにより「参照されている」だけでなく「本当に無害化する」ことを固定する。
  const fn = new Function('return (' + src + ')')();
  assert.equal(fn('<script>'), '&lt;script&gt;');
  assert.equal(fn('a & b'), 'a &amp; b');
  assert.equal(fn('"quoted"'), '&quot;quoted&quot;');
  assert.equal(fn("it's"), 'it&#39;s');
  // 攻撃ベクタの複合例：属性 break-out ＋ タグ注入がすべて無害化される。
  assert.equal(
    fn('"><img src=x onerror=alert(1)>'),
    '&quot;&gt;&lt;img src=x onerror=alert(1)&gt;'
  );
  // null/undefined は空文字（雛形の契約）。例外を投げない。
  assert.equal(fn(null), '');
  assert.equal(fn(undefined), '');
});

// ---- setEmptyState（innerHTML sink helper が実在し、想定形であることの anti-vacuous 確認）----
test('setEmptyState は innerHTML sink であり trusted マークアップを受ける helper として実在する', () => {
  const src = extractFunction('setEmptyState');
  // 動的値は呼び出し側で escapeHtml 済みにする契約なので、ここでは sink の実在だけを固定する
  // （renderTable / wireButtons のガードが空振りでない前提＝sink が確かに innerHTML であること）。
  assert.match(src, /tbody\.innerHTML\s*=/, 'setEmptyState が tbody.innerHTML へ書いていない（sink の実像が変わった）');
});
