/**
 * test_boot_sequence.js — pro-code の起動配線（ロード順・グローバル公開）のスモークテスト。
 *
 * なぜ必要か:
 *   `verify`（プロビジョニング検証）も他の単体テストも、各ファイルを「個別に」読むため、
 *   index.html が定める <script> 読込順で連結・実行したときに壊れる不具合（IIFE 境界の破損、
 *   ロード順依存の未定義参照、白画面）を捕捉できない。ここでは 6 本の pro-code JS を実際の
 *   読込順で 1 つの共有コンテキストへ流し込み、
 *     (1) 読込中に例外を投げないこと
 *     (2) 各層が期待どおりのグローバル（InventoryBoot/Config/Data/QR/QrScanner）を公開すること
 *     (3) app.js が起動配線（DOMContentLoaded 登録）まで到達すること
 *   を機械的に保証する。ファイル統廃合（連結バンドル化）を安全に行うための回帰網。
 *
 * 設計メモ:
 *   - vendor（domo.js / jsQR.js）は第三者製で統廃合対象外のため、提供するグローバル
 *     （domo / jsQR）をモックし、監査対象の自作 6 本だけを読む。
 *   - document.readyState='loading' にすると app.js は DOMContentLoaded を「登録」するだけで
 *     init() を走らせない＝DOM 依存の初期化を発火させずにトップレベル実行だけを検証できる。
 *   - realm 差の落とし穴（[[project-...]]）を避け、assert.deepEqual は使わず typeof/存在/凍結のみ確認。
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PRO = path.join(__dirname, '../pro-code');

// index.html の <script> 順（vendor を除く自作 6 本）。ここが唯一の順序定義源。
const LOAD_ORDER = [
  'boot-diagnostics.js',
  'config.js',
  'domo-access.js',
  'qr-generator.js',
  'qr-scanner.js',
  'app.js'
];

function readSource(file) {
  return fs.readFileSync(path.join(PRO, file), 'utf8');
}

/**
 * index.html の <script src="..."> を「登場順」で抽出する。
 * これで LOAD_ORDER を index.html の実体と突き合わせ、ファイル統廃合で <script> を
 * 足し引きしたのに LOAD_ORDER の更新を忘れる（＝スモークテストが古い順序のまま素通りする）
 * ドリフトを機械的に捕捉する。
 */
function indexHtmlScriptSrcs() {
  const html = fs.readFileSync(path.join(PRO, 'index.html'), 'utf8');
  const srcs = [];
  const re = /<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi;
  let match;
  while ((match = re.exec(html)) !== null) {
    srcs.push(match[1]);
  }
  return srcs;
}

/** ブラウザ最小モックを備えた共有コンテキストを作る。window===self===global===globalThis に統一。 */
function createBrowserContext() {
  const registered = {};
  const noop = () => {};
  const mediaQuery = { matches: false, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop };
  const documentElement = { setAttribute: noop, getAttribute: () => null, style: { setProperty: noop } };
  const documentMock = {
    readyState: 'loading', // これにより app.js は init を即実行せず DOMContentLoaded を登録するだけ
    addEventListener(type, listener) { registered['document:' + type] = listener; },
    removeEventListener: noop,
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ style: {}, setAttribute: noop, appendChild: noop, addEventListener: noop }),
    documentElement,
    body: { appendChild: noop, addEventListener: noop, classList: { add: noop, remove: noop } }
  };
  const sandbox = {
    console,
    setTimeout: () => 0,
    clearTimeout: noop,
    setInterval: () => 0,
    clearInterval: noop,
    requestAnimationFrame: () => 0,
    cancelAnimationFrame: noop,
    location: { protocol: 'https:', hostname: 'maintenance-instance.domo.com', reload: noop },
    navigator: { userAgent: 'node-boot-test', mediaDevices: {} },
    matchMedia: () => mediaQuery,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    addEventListener(type, listener) { registered['window:' + type] = listener; },
    removeEventListener: noop,
    document: documentMock,
    // vendor 提供分のモック（読込時には未使用だが将来の init 検証のため用意）
    domo: { get: () => Promise.resolve([]), post: () => Promise.resolve({}), env: {} },
    jsQR: () => null,
    __registered: registered
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.global = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  return sandbox;
}

/** 起動後のコンテキストが、期待どおりのグローバル配線を持つことを検証する共通アサート。 */
function assertWiring(ctx, label) {
  assert.equal(typeof ctx.InventoryBoot, 'object', `${label}: InventoryBoot 未公開`);
  assert.equal(typeof ctx.InventoryBoot.ready, 'function', `${label}: InventoryBoot.ready 欠落`);
  assert.equal(typeof ctx.InventoryBoot.fail, 'function', `${label}: InventoryBoot.fail 欠落`);

  assert.equal(typeof ctx.InventoryConfig, 'object', `${label}: InventoryConfig 未公開`);
  assert.ok(Object.isFrozen(ctx.InventoryConfig), `${label}: InventoryConfig が凍結されていない`);
  assert.equal(typeof ctx.InventoryConfig.ui.listPageSize, 'number', `${label}: config.ui.listPageSize 欠落`);
  assert.equal(typeof ctx.InventoryConfig.network.queryPageSize, 'number', `${label}: config.network.queryPageSize 欠落`);
  assert.equal(typeof ctx.InventoryConfig.analytics.trendWindowDays, 'number', `${label}: config.analytics.trendWindowDays 欠落`);

  assert.equal(typeof ctx.InventoryData, 'object', `${label}: InventoryData 未公開`);
  ['getCollection', 'callFunction', 'buildDashboardRows'].forEach((fn) => {
    assert.equal(typeof ctx.InventoryData[fn], 'function', `${label}: InventoryData.${fn} 欠落`);
  });

  assert.equal(typeof ctx.InventoryQR, 'object', `${label}: InventoryQR 未公開`);
  assert.equal(typeof ctx.InventoryQR.encode, 'function', `${label}: InventoryQR.encode 欠落`);
  assert.equal(typeof ctx.InventoryQR.toSvg, 'function', `${label}: InventoryQR.toSvg 欠落`);

  assert.equal(typeof ctx.InventoryQrScanner, 'function', `${label}: InventoryQrScanner 未公開（class 期待）`);

  assert.equal(typeof ctx.__registered['document:DOMContentLoaded'], 'function',
    `${label}: app.js が起動配線（DOMContentLoaded 登録）に到達していない`);
}

test('LOAD_ORDER は index.html の実 <script src> 順を正確に写している（統廃合ドリフトの番人）', () => {
  // vendor/* は第三者製で統廃合対象外＝自作分だけを比較する。
  const selfAuthored = indexHtmlScriptSrcs().filter((src) => !src.startsWith('vendor/'));
  // realm 差の落とし穴を避けるため配列は文字列化して比較する（[[project-...]] 参照）。
  assert.equal(selfAuthored.join(','), LOAD_ORDER.join(','),
    'index.html の自作 <script src> 順と LOAD_ORDER が不一致。ファイル統廃合で <script> を足し引き' +
    'したら LOAD_ORDER も同時に更新すること（このテストがそのロックである）。');
});

test('pro-code を index.html の読込順で共有コンテキストに流すと無例外で全グローバルが配線される', () => {
  const ctx = createBrowserContext();
  LOAD_ORDER.forEach((file) => {
    const source = readSource(file);
    assert.doesNotThrow(
      () => vm.runInContext(source, ctx, { filename: file }),
      `${file} の読込で例外が発生した`
    );
  });
  assertWiring(ctx, '順次読込');
});

test('6本を連結して単一スクリプトとして実行しても配線は同一（バンドル統廃合の等価性）', () => {
  const ctx = createBrowserContext();
  // 実際のバンドル化を模して、読込順のまま連結。IIFE は自己完結なので境界に区切りのセミコロンを挟む。
  const bundle = LOAD_ORDER.map(readSource).join('\n;\n');
  assert.doesNotThrow(
    () => vm.runInContext(bundle, ctx, { filename: 'pro-code.bundle.js' }),
    '連結バンドルの読込で例外が発生した'
  );
  assertWiring(ctx, '連結バンドル');
});

test('config を先に読まないと domo-access は InventoryConfig 依存で失敗する（順序不変条件の番人）', () => {
  const ctx = createBrowserContext();
  // わざと config.js を飛ばして domo-access.js を読む。domo-access.js は IIFE 冒頭（ロード時）に
  // `const config = global.InventoryConfig;` → `config.network.requestTimeoutMs` を参照するため、
  // config 不在なら TypeError で即例外になる。これが「config を先に読め」という順序不変条件の実体。
  vm.runInContext(readSource('boot-diagnostics.js'), ctx, { filename: 'boot-diagnostics.js' });
  let threw = false;
  try {
    vm.runInContext(readSource('domo-access.js'), ctx, { filename: 'domo-access.js' });
  } catch (error) {
    threw = true; // config 不在で即例外＝順序依存の証拠
  }
  // 以前は `threw || wiredWithoutConfig` の OR で「たまたま通っても可」としており、実質無効化していた。
  // 実際にはロード時参照で必ず throw するため、番人として厳密に「throw する」ことを固定する。
  // もし将来 config 参照が遅延化されて throw しなくなったら、このテストが落ちて順序前提の変化を知らせる。
  assert.ok(threw,
    'config.js 不在で domo-access.js がロード時例外を投げなかった＝InventoryConfig 依存の順序前提が崩れている');
});
