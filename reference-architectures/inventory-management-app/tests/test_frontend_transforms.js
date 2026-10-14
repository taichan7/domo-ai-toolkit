#!/usr/bin/env node
/**
 * inventory-management-app フロントエンド（pro-code/app.js）の純粋トランスフォーム特性化テスト。
 *
 * 実行: node inventory-management-app/tests/test_frontend_transforms.js   （node:test が自動実行）
 *   別ファイルを対象にするには INV_APP_JS=/path/to/app.js を渡す（prove-the-bug 用）。
 *
 * なぜこのテストか（coverage island の解消）:
 *   FE の既存テストは concern-scoped で、test_frontend_guards.js は innerHTML sink の XSS 静的ガード、
 *   test_boot_sequence.js は起動シーケンス、test_frontend_shell.js は HTML/CSS/ソース構造の静的検査
 *   （app.js を文字列として読み `assert.match` で突合し、関数を実行しない）だけを固定していた。その結果、
 *   どのファイルも「所有」しない引数純粋なトランスフォーム群が、静的にだけ言及され実挙動は無検証の
 *   coverage island として残っていた——各 fn を `git grep '<fn>(' -- '*test*'` で確認すると、
 *   normalizedSearch(:501)・aiNoteKey(:991)・isShortageRow(:1008) はいずれも test_frontend_shell.js の
 *   静的 `assert.match`（呼び出し形・シグネチャの存在確認）1 件のみで、入力を与えて出力を固定した
 *   behavioral test は 0 件だった。姉妹 app でも同型脚が未固定で、support-center は fmtTime/clip 等 6 本
 *   （d3113861/1cb39cbb）、asset-lifecycle FE は数値ソート脚（6355982b）を behavioral に特性化している。
 *   同型の「200 OK でも出力が黙って変わりうる silent transform」を、この app を一切変更せず
 *   （追加専用・再 publish 不要）source から抽出して実挙動を固定する。
 *
 * 何を pin するか（silent-transform の分岐脚）:
 *   normalizedSearch … 候補ピッカー／ダッシュボード検索の入力正規化。(a) falsy→''（`|| ''` sentinel）
 *     (b) 前後空白 trim (c) toLocaleLowerCase('ja-JP') による小文字化＝大小無視の部分一致を成立させる要。
 *     退行（小文字化脱落）すると検索が黙って大小区別になり "ITEM" で "item" が引けなくなる。
 *   aiNoteKey … AI在庫コメントを品目×ロケーションで相関させる連結キー。(a) 両辺 trim (b) 両辺
 *     toUpperCase()＝入力の大小揺れを吸収して同一記録を1キーに束ねる (c) `::` 区切り。退行（大文字化
 *     脱落）すると 'item-1' と 'ITEM-1' が別キーになり、代表カードの「残り拠点数」集約が黙って崩れる。
 *   isShortageRow … 不足フラグの真偽正規化。多論理項 OR の 2 脚:(1) `is_shortage === true`（boolean）
 *     (2) `String(is_shortage).toLowerCase() === 'true'`（AppDB 返却型ゆらぎ＝文字列 'true'/'TRUE' を
 *     不足と見なす。関数自身のコメントが "boolean と 'true' 文字列が混在しうる" と明言）。第2脚は既存
 *     テスト（静的 match のみ）が一切踏んでおらず、退行すると文字列型で保存された行の不足が 200 OK の
 *     まま黙って見逃される（＝欠品アラート漏れ）典型 silent-corruption 脚。false/未設定/数値は不足に
 *     しない default も併せて固定する。
 *
 * 抽出方式（test_frontend_guards.js と同一・自己完結が本 repo の流儀）:
 *   app.js は素のブラウザ IIFE なので丸ごと require すると throw する。対象の名前付き関数本体だけを
 *   波括弧マッチで抜き出し vm で評価する。上記 3 本はいずれも引数のみに依存する純関数（外部クロージャ
 *   参照なし・String/RegExp の intrinsics だけ）なので、この方式で実挙動をそのまま固定できる。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const APP_PATH = process.env.INV_APP_JS || path.join(__dirname, '..', 'pro-code', 'app.js');
const SOURCE = fs.readFileSync(APP_PATH, 'utf8');

/**
 * 名前付き関数 `function <name>(...) { ... }` の全文を波括弧の対応で抜き出す。
 * （test_frontend_guards.js の同名ヘルパと同一実装。シグネチャ regex は定義だけに当たり
 * 呼び出し `name(...)` には当たらないので、末尾の call-site へ誤爆しない。）
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

/** 引数のみの純関数を vm で取り出す（String/RegExp の intrinsics だけに依存）。 */
function loadPureFn(name) {
  const ctx = {};
  vm.createContext(ctx);
  const fn = vm.runInContext(extractFunction(name) + '\n' + name + ';', ctx);
  assert.equal(typeof fn, 'function', `${name} を関数として取り出せない`);
  return fn;
}

const normalizedSearch = loadPureFn('normalizedSearch');
const aiNoteKey = loadPureFn('aiNoteKey');
const isShortageRow = loadPureFn('isShortageRow');

// ---- normalizedSearch（検索入力の正規化: falsy→''・trim・小文字化）----
test('normalizedSearch は前後空白を trim する（既に小文字の入力で trim 脚を単独固定）', () => {
  assert.equal(normalizedSearch('  abc  '), 'abc');
});

test('normalizedSearch は大文字を小文字化する（既に trim 済の入力で toLocaleLowerCase 脚を単独固定）', () => {
  // 小文字化脱落＝検索が大小区別になり "ITEM" で "item" を引けなくなる silent 退行を捕捉する。
  assert.equal(normalizedSearch('AbC'), 'abc');
});

test('normalizedSearch は falsy 入力（null・undefined・空文字）を "" にする（`|| \'\'` sentinel）', () => {
  assert.equal(normalizedSearch(null), '');
  assert.equal(normalizedSearch(undefined), '');
  assert.equal(normalizedSearch(''), '');
});

// ---- aiNoteKey（品目×ロケーションの相関キー: trim・大文字化・"::" 連結）----
test('aiNoteKey は両辺を大文字化し "::" で連結する（大小揺れ吸収＝同一記録を1キーへ）', () => {
  // 大文字化脱落＝'item-1' と 'ITEM-1' が別キーになり代表カードの拠点数集約が崩れる silent 退行を捕捉。
  assert.equal(aiNoteKey('item-1', 'loc-2'), 'ITEM-1::LOC-2');
});

test('aiNoteKey は両辺を trim する（既に大文字の入力で trim 脚を単独固定）', () => {
  assert.equal(aiNoteKey('  A  ', '  B  '), 'A::B');
});

test('aiNoteKey は falsy な各辺を "" にする（`|| \'\'` sentinel・両 falsy は "::"）', () => {
  assert.equal(aiNoteKey(null, undefined), '::');
  assert.equal(aiNoteKey('', ''), '::');
});

// ---- isShortageRow（不足フラグの真偽正規化: boolean true / 文字列 'true' の2脚）----
test('isShortageRow は boolean true を不足と見なす（第1論理項）', () => {
  assert.equal(isShortageRow({ is_shortage: true }), true);
});

test('isShortageRow は文字列 "true"/"TRUE" を不足と見なす（第2論理項＝AppDB 型ゆらぎ吸収・大小無視）', () => {
  // ★中核の未踏脚: 既存テストは静的 match のみで、文字列 'true' を実際に流して不足判定させたことが
  //   一度も無い。退行（第2脚 or toLowerCase 脱落）で文字列型行の不足が黙って見逃される。
  assert.equal(isShortageRow({ is_shortage: 'true' }), true);
  assert.equal(isShortageRow({ is_shortage: 'TRUE' }), true);
});

test('isShortageRow は false・未設定・数値・文字列 "false" を不足にしない（default 脚）', () => {
  assert.equal(isShortageRow({ is_shortage: false }), false);
  assert.equal(isShortageRow({}), false);                 // 未設定＝undefined→'undefined'!=='true'
  assert.equal(isShortageRow({ is_shortage: 1 }), false); // 数値 1 は不足にしない（true/'true' のみ）
  assert.equal(isShortageRow({ is_shortage: 'false' }), false);
});
