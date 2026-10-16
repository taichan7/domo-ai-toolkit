#!/usr/bin/env node
/**
 * pl-summary-app Pro-Code「Store PL AI Insights」のドリルダウン機能の特性化テスト。
 *
 * 実行: node pl-summary-app/tests/test_drill_helpers.js   （node:test が自動実行）
 *
 * なぜこのテストか:
 *   本機能はカード内でビューが切り替わるドリルパス（Domo 標準カード相当）を Pro Code で実装する
 *   もので、(a) どのクリックがどのフレームへ進むかを決める分岐（drillFrom）と、(b) フレーム描画に
 *   渡すデータモデル（月次詳細・費用内訳・事業部月次）が要。app.js は素のブラウザスクリプト
 *   （トップレベルで document.getElementById / addEventListener を実行する）ため丸ごとロードできず、
 *   対象関数のソースを波括弧マッチで抜き出して DOM 非依存の vm サンドボックスで評価する。
 *
 * 固定する契約:
 *   - ドリルパス定義（drillFrom）: チャート別・現フレーム別の遷移。未知の組合せは push しない。
 *   - 純粋モデル: shiftPeriod / buildStorePeriodRows / pickTopBottom / buildMonthDetail /
 *     buildStoreCostTable / buildDeptMonthDetail の集計・変化率・境界（前月/前年なし）。
 *   - 描画契約: 各 draw 関数が data-drill マーカーを出力し、init が6チャートを bindDrill /
 *     bindChartHover に配線していること（マーカーを消す改修を検知する source-text ガード）。
 *
 * 抽出の前提: 対象関数は文字列/正規表現/コメント内に不均衡な波括弧を持たない（末尾 '}' ガード）。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const APP_PATH = path.join(__dirname, '..', 'pro-code', 'app.js');
const CSS_PATH = path.join(__dirname, '..', 'pro-code', 'app.css');
const SOURCE = fs.readFileSync(APP_PATH, 'utf8');
const CSS = fs.readFileSync(CSS_PATH, 'utf8');

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

// ---- 純粋モデルのロード（依存関数も同順で連結。関数宣言は hoist される）----
const PURE_FNS = [
  'shiftPeriod', 'num', 'byProfitDesc', 'costField', 'pctChange',
  'buildStorePeriodRows', 'pickTopBottom', 'buildMonthDetail',
  'buildStoreCostTable', 'buildDeptMonthDetail', 'chartWidth'
];
const pureCtx = vm.createContext({});
vm.runInContext(PURE_FNS.map(extractFunction).join('\n'), pureCtx);
function pure(name) {
  const fn = vm.runInContext(name, pureCtx);
  assert.equal(typeof fn, 'function', `${name} を関数として取り出せない`);
  return fn;
}
// vm レルムを跨ぐ object/array は prototype が異なるため JSON 化して比較する（挿入順も固定できる）。
const json = (v) => JSON.stringify(v);

const shiftPeriod = pure('shiftPeriod');
const buildStorePeriodRows = pure('buildStorePeriodRows');
const pickTopBottom = pure('pickTopBottom');
const buildMonthDetail = pure('buildMonthDetail');
const buildStoreCostTable = pure('buildStoreCostTable');
const buildDeptMonthDetail = pure('buildDeptMonthDetail');
const chartWidth = pure('chartWidth');

// ---- drillFrom のロード（モジュール状態はコンテキスト注入で差し替え）----
const DRILL_SRC = ['topFrame', 'monthDetailFrame', 'deptByCode', 'drillFrom'].map(extractFunction).join('\n');

function fakeEl(attrs) {
  return {
    getAttribute: function (n) {
      return Object.prototype.hasOwnProperty.call(attrs, n) ? attrs[n] : null;
    }
  };
}

function makeDrillEnv(opts) {
  opts = opts || {};
  const DRILL = { trend: [], donut: [], rank: [], deptBar: [], deptDonut: [], deptTrend: [] };
  (opts.seed || []).forEach(function (s) { DRILL[s.key].push(s.frame); });
  const ctx = vm.createContext({
    DRILL: DRILL,
    state: opts.state || { isAll: true, sel: '全社', view: { name: '全社' } },
    DEPT: opts.dept || null,
    PALETTE: { rev: '#7F1D2D' },
    drillPush: function (key, frame) { DRILL[key].push(frame); }
  });
  vm.runInContext(DRILL_SRC, ctx);
  const drillFrom = vm.runInContext('drillFrom', ctx);
  return { drillFrom: drillFrom, DRILL: DRILL };
}

/* ================= 純粋モデル ================= */

test('shiftPeriod は年を跨いで YYYY-MM を加減算する', () => {
  assert.equal(shiftPeriod('2025-01', -1), '2024-12');
  assert.equal(shiftPeriod('2025-01', -12), '2024-01');
  assert.equal(shiftPeriod('2025-12', 1), '2026-01');
  assert.equal(shiftPeriod('2024-12', 12), '2025-12');
  assert.equal(shiftPeriod('', 1), '');
  assert.equal(shiftPeriod('not-a-period', 1), '');
});

test('buildStorePeriodRows は指定月の店舗別に集計し純利益降順で返す', () => {
  const rows = buildStorePeriodRows([
    { period: '2025-06', store_id: 'JPN002', store: '新宿', rev: 100, profit: 10 },
    { period: '2025-06', store_id: 'JPN001', store: '銀座', rev: 200, profit: -5 },
    { period: '2025-06', store_id: 'JPN002', store: '新宿', rev: 50, profit: 5 },
    { period: '2025-05', store_id: 'JPN001', store: '銀座', rev: 999, profit: 999 }
  ], '2025-06');
  assert.equal(rows.length, 2, '他月を混ぜてはいけない');
  assert.equal(json(rows.map(function (r) { return r.id; })), json(['JPN002', 'JPN001']));
  assert.equal(rows[0].rev, 150, '同一店舗の複数行を合算する');
  assert.equal(rows[0].profit, 15);
  assert.equal(rows[0].margin, 10, '利益率＝純利益/売上×100');
  assert.equal(rows[1].margin, -2.5);
  assert.equal(json(buildStorePeriodRows([], '2025-06')), json([]));
});

test('pickTopBottom は上位N＋下位Nを重複なく取り純利益降順に整列する', () => {
  const rows = [];
  for (let i = 1; i <= 6; i++) rows.push({ id: 'S' + i, name: '店' + i, profit: 10 - i });
  const picked = pickTopBottom(rows, 2, 2);
  assert.equal(json(picked.map(function (r) { return r.id; })), json(['S1', 'S2', 'S5', 'S6']));
  const small = pickTopBottom(rows.slice(0, 3), 2, 2);
  assert.equal(json(small.map(function (r) { return r.id; })), json(['S1', 'S2', 'S3']), '行数不足でも重複しない');
});

test('buildMonthDetail は当月・前月・前年同月と変化率を返す', () => {
  const rows = [
    { period: '2024-06', store_id: 'S1', rev: 80, profit: 4 },
    { period: '2025-05', store_id: 'S1', rev: 100, profit: 5 },
    { period: '2025-06', store_id: 'S1', rev: 120, profit: 12 }
  ];
  const m = buildMonthDetail(rows, 'S1', '2025-06');
  assert.equal(m.period, '2025-06');
  assert.equal(m.prevPeriod, '2025-05');
  assert.equal(m.yoyPeriod, '2024-06');
  assert.equal(m.sales.cur, 120);
  assert.equal(m.sales.prev, 100);
  assert.equal(m.sales.yoy, 80);
  assert.equal(m.sales.momPct, 20, '前月比 +20%');
  assert.equal(m.sales.yoyPct, 50, '前年同月比 +50%');
  assert.equal(m.profit.cur, 12);
  assert.equal(m.profit.momPct, 140);
  assert.equal(m.margin.cur, 10);
  assert.equal(m.margin.prev, 5);
  assert.equal(m.margin.yoy, 5);
});

test('buildMonthDetail は比較月が範囲外なら null を返し変化率を落とす', () => {
  const m = buildMonthDetail([
    { period: '2025-06', store_id: 'S1', rev: 120, profit: 12 }
  ], 'S1', '2025-06');
  assert.equal(m.prevPeriod, null);
  assert.equal(m.yoyPeriod, null);
  assert.equal(m.sales.momPct, null);
  assert.equal(m.sales.yoyPct, null);
  assert.equal(m.margin.prev, null);
  assert.equal(buildMonthDetail([], 'S1', '2025-06'), null, '当月行がなければ null');
});

test('buildMonthDetail は前月売上0のとき変化率を null にする（ゼロ除算回避）', () => {
  const m = buildMonthDetail([
    { period: '2025-05', store_id: 'S1', rev: 0, profit: -3 },
    { period: '2025-06', store_id: 'S1', rev: 120, profit: 12 }
  ], 'S1', '2025-06');
  assert.equal(m.sales.momPct, null, '分母0の売上変化率は算出不能');
  // 利益は前月 -3 → 当月 12。pctChange は |基準| で割るため +500%（ゼロ除算ではない）。
  assert.equal(m.profit.momPct, 500);
});

test('buildStoreCostTable は金額・構成比・対売上比と合計を返す', () => {
  const store = { sales: 1000, cogs: 300, labor: 200, facility: 100, marketing: 50, admin: 50 };
  const model = buildStoreCostTable(store, [
    { key: '商品原価', label: '商品原価', color: '#7F1D2D' },
    { key: '総人件費', label: '総人件費', color: '#B23A48' },
    { key: '施設費', label: '施設費', color: '#C97B84' },
    { key: 'マケ費用', label: 'マケ費用', color: '#D8A7AC' },
    { key: '管理費用', label: '管理費用', color: '#E4C9CC' }
  ]);
  assert.equal(model.total, 700);
  assert.equal(model.sales, 1000);
  assert.equal(model.rows.length, 5);
  assert.equal(json(model.rows.map(function (r) { return r.key; })), json(['商品原価', '総人件費', '施設費', 'マケ費用', '管理費用']));
  assert.equal(Math.round(model.rows[0].share * 10) / 10, 42.9);
  assert.equal(model.rows[0].toSales, 30);
  assert.equal(buildStoreCostTable(null, []), null, '店舗なしは null');
});

test('buildDeptMonthDetail は当月・前月・FY合計と前月比・FY構成比を返す', () => {
  const dept = {
    fy: 2025,
    divisions: [{ code: 'APPA', name: '衣料品事業部', color: '#7F1D2D' }],
    monthly: {
      periods: ['2025-01', '2025-02', '2025-03'],
      series: [{ code: 'APPA', name: '衣料品事業部', color: '#7F1D2D', rev: [100, 150, 250] }]
    }
  };
  const m = buildDeptMonthDetail(dept, 'APPA', '2025-03');
  assert.equal(m.name, '衣料品事業部');
  assert.equal(m.rev, 250);
  assert.equal(m.prevRev, 150);
  assert.equal(m.prevPeriod, '2025-02');
  assert.equal(m.mom, 66.66666666666666);
  assert.equal(m.fyTotal, 500);
  assert.equal(m.share, 50);
  assert.equal(m.prevShare, 30);
  assert.equal(buildDeptMonthDetail(dept, 'APPA', '2024-12'), null, '範囲外の月は null');
  assert.equal(buildDeptMonthDetail(dept, 'NOPE', '2025-03'), null, '未知の事業部は null');
  assert.equal(buildDeptMonthDetail(null, 'APPA', '2025-03'), null);
});

test('chartWidth はコンテナ幅を返し、取れない環境は 760 にフォールバックする', () => {
  assert.equal(chartWidth({ clientWidth: 640 }), 640, '実測幅をそのまま使う');
  assert.equal(chartWidth({ clientWidth: 0 }), 760, '0 はフォールバック');
  assert.equal(chartWidth(null), 760);
  assert.equal(chartWidth(null, 300), 300, 'フォールバック値は指定可能');
});

/* ================= ドリルパス定義（drillFrom） ================= */

test('trend: 全社rootの月クリックは店舗別フレームへ、店舗rootは月次詳細へ進む', () => {
  const all = makeDrillEnv({ state: { isAll: true, sel: '全社', view: { name: '全社' } } });
  all.drillFrom('trend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-06' }));
  assert.equal(json(all.DRILL.trend), json([{ type: 'storesForPeriod', period: '2025-06' }]));

  const one = makeDrillEnv({ state: { isAll: false, sel: 'JPN003', view: { name: '渋谷店' } } });
  one.drillFrom('trend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-06' }));
  assert.equal(json(one.DRILL.trend), json([{ type: 'monthDetail', storeId: 'JPN003', storeName: '渋谷店', period: '2025-06' }]));
});

test('trend: 店舗別フレームの店舗クリック→店舗トレンド→月次詳細と深掘りできる', () => {
  const env = makeDrillEnv({ seed: [{ key: 'trend', frame: { type: 'storesForPeriod', period: '2025-06' } }] });
  env.drillFrom('trend', fakeEl({ 'data-drill': 'store', 'data-store-id': 'JPN003', 'data-name': '渋谷店' }));
  assert.equal(json(env.DRILL.trend[1]), json({ type: 'storeTrend', storeId: 'JPN003', storeName: '渋谷店' }));
  env.drillFrom('trend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-03' }));
  assert.equal(json(env.DRILL.trend[2]), json({ type: 'monthDetail', storeId: 'JPN003', storeName: '渋谷店', period: '2025-03' }));
});

test('trend: 未知の組合せ（店舗別フレームでの月クリック等）では進まない', () => {
  const env = makeDrillEnv({ seed: [{ key: 'trend', frame: { type: 'storesForPeriod', period: '2025-06' } }] });
  env.drillFrom('trend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-05' }));
  env.drillFrom('trend', fakeEl({ 'data-drill': 'slice', 'data-key': '商品原価' }));
  assert.equal(env.DRILL.trend.length, 1, '不正な遷移でフレームが増えてはいけない');
});

test('donut: 全社root→カテゴリ別店舗→店舗費用構成→費用内訳表と深掘りできる', () => {
  const env = makeDrillEnv({ state: { isAll: true, sel: '全社', view: { name: '全社' } } });
  env.drillFrom('donut', fakeEl({ 'data-drill': 'slice', 'data-key': '商品原価', 'data-label': '商品原価' }));
  assert.equal(json(env.DRILL.donut[0]), json({ type: 'storesForCategory', catKey: '商品原価', catLabel: '商品原価' }));
  env.drillFrom('donut', fakeEl({ 'data-drill': 'cat-store', 'data-store-id': 'JPN003', 'data-name': '渋谷店' }));
  assert.equal(json(env.DRILL.donut[1]), json({ type: 'storeCosts', storeId: 'JPN003', storeName: '渋谷店', catKey: '商品原価', catLabel: '商品原価' }));
  env.drillFrom('donut', fakeEl({ 'data-drill': 'slice', 'data-key': '総人件費', 'data-label': '総人件費' }));
  assert.equal(json(env.DRILL.donut[2]), json({ type: 'storeCostTable', storeId: 'JPN003', storeName: '渋谷店', catKey: '総人件費', catLabel: '総人件費' }));
});

test('donut: 店舗ビューのスライスクリックは費用内訳表へ直行する', () => {
  const env = makeDrillEnv({ state: { isAll: false, sel: 'JPN003', view: { name: '渋谷店' } } });
  env.drillFrom('donut', fakeEl({ 'data-drill': 'slice', 'data-key': '施設費', 'data-label': '施設費' }));
  assert.equal(json(env.DRILL.donut), json([{ type: 'storeCostTable', storeId: 'JPN003', storeName: '渋谷店', catKey: '施設費', catLabel: '施設費' }]));
});

test('rank: 店舗クリック→店舗トレンド→月次詳細', () => {
  const env = makeDrillEnv();
  env.drillFrom('rank', fakeEl({ 'data-drill': 'rank', 'data-store-id': 'JPN010', 'data-name': '横浜店' }));
  assert.equal(json(env.DRILL.rank[0]), json({ type: 'storeTrend', storeId: 'JPN010', storeName: '横浜店' }));
  env.drillFrom('rank', fakeEl({ 'data-drill': 'month', 'data-period': '2025-08' }));
  assert.equal(json(env.DRILL.rank[1]), json({ type: 'monthDetail', storeId: 'JPN010', storeName: '横浜店', period: '2025-08' }));
});

test('dept: 積み上げ棒/ドーナツの事業部クリック→月次、月クリック→月次詳細', () => {
  const dept = {
    fy: 2025,
    divisions: [{ code: 'LIFE', name: '生活雑貨事業部', color: '#B23A48' }],
    monthly: { periods: ['2025-01', '2025-02'], series: [{ code: 'LIFE', name: '生活雑貨事業部', color: '#B23A48', rev: [10, 20] }] }
  };
  const bar = makeDrillEnv({ dept: dept });
  bar.drillFrom('deptBar', fakeEl({ 'data-drill': 'dept', 'data-key': 'LIFE' }));
  assert.equal(json(bar.DRILL.deptBar[0]), json({ type: 'deptMonthly', code: 'LIFE', name: '生活雑貨事業部' }));
  bar.drillFrom('deptBar', fakeEl({ 'data-drill': 'month', 'data-period': '2025-02' }));
  assert.equal(json(bar.DRILL.deptBar[1]), json({ type: 'deptMonthDetail', code: 'LIFE', name: '生活雑貨事業部', period: '2025-02' }));

  const donut = makeDrillEnv({ dept: dept });
  donut.drillFrom('deptDonut', fakeEl({ 'data-drill': 'slice', 'data-key': 'LIFE' }));
  assert.equal(json(donut.DRILL.deptDonut[0]), json({ type: 'deptMonthly', code: 'LIFE', name: '生活雑貨事業部' }));
});

test('deptTrend: 月クリック→事業部内訳→事業部月次→月次詳細', () => {
  const dept = {
    fy: 2025,
    divisions: [{ code: 'FOOD', name: '食品事業部', color: '#5F7A64' }],
    monthly: { periods: ['2025-01', '2025-02'], series: [{ code: 'FOOD', name: '食品事業部', color: '#5F7A64', rev: [10, 20] }] }
  };
  const env = makeDrillEnv({ dept: dept });
  env.drillFrom('deptTrend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-02' }));
  assert.equal(json(env.DRILL.deptTrend[0]), json({ type: 'deptMonthBreakdown', period: '2025-02' }));
  env.drillFrom('deptTrend', fakeEl({ 'data-drill': 'dept', 'data-key': 'FOOD' }));
  assert.equal(json(env.DRILL.deptTrend[1]), json({ type: 'deptMonthly', code: 'FOOD', name: '食品事業部' }));
  env.drillFrom('deptTrend', fakeEl({ 'data-drill': 'month', 'data-period': '2025-01' }));
  assert.equal(json(env.DRILL.deptTrend[2]), json({ type: 'deptMonthDetail', code: 'FOOD', name: '食品事業部', period: '2025-01' }));
});

/* ================= 描画・配線の契約（source-text ガード） ================= */

test('各 draw 関数は data-drill マーカーを出力する（クリック配線の契約）', () => {
  assert.match(extractFunction('drawTrend'), /data-drill="month"/, 'トレンドの月ヒットバンド');
  assert.match(extractFunction('drawDeptTrend'), /data-drill="month"/, '事業部トレンドの月ヒットバンド');
  assert.match(extractFunction('donutInto'), /data-drill="slice"/, 'ドーナツのスライス');
  assert.match(extractFunction('drawDivergingBars'), /data-drill=/, '店舗別横棒');
  assert.match(extractFunction('drawHBars'), /data-drill=/, 'カテゴリ/事業部の横棒');
  assert.match(extractFunction('drawDeptBar'), /data-drill="dept"/, '事業部積み上げ棒');
});

test('PL-001: ドリル帯の aria-label に数値を畳み込み、フォーカスでもツールチップを出す', () => {
  // マウス専用の是正: SR/キーボード利用者がドリル動作だけでなく金額も得られること。
  // 各帯の aria-label 連結に金額整形（jpMoney）が入っているかを source-text で固定する。
  assert.match(extractFunction('drawTrend'), /aria-label="' \+[\s\S]{0,120}jpMoney\(/, 'トレンド帯の aria-label に金額がない');
  assert.match(extractFunction('drawDivergingBars'), /aria-label="' \+[\s\S]{0,160}jpMoney\(/, 'ランキング/店舗別横棒の aria-label に金額がない');
  assert.match(extractFunction('drawDeptBar'), /aria-label="' \+[\s\S]{0,120}jpMoney\(/, '事業部積み上げ棒の aria-label に金額がない');
  assert.match(extractFunction('drawDeptTrend'), /aria-label="' \+[\s\S]{0,120}jpMoney\(/, '事業部トレンド帯の aria-label に金額がない');
  // キーボード focus でもホバーと同じツールチップを出す配線（bbox 基準で配置）。
  const hover = extractFunction('bindChartHover');
  assert.match(hover, /"focusin"/, 'focusin 配線がない');
  assert.match(hover, /"focusout"/, 'focusout 配線がない');
  assert.match(hover, /getBoundingClientRect/, 'focus 時の配置が bbox 基準でない');
});

test('横棒のクリック要素は店舗名を data-name で持つ（ドリルフレームの店舗名 null 防止）', () => {
  // 過去に data-label しか持たず drillFrom の data-name 読みが null になった回帰のガード。
  assert.match(extractFunction('drawHBars'), /data-name="' \+ esc\(r\.name\)/);
});

test('SVG はコンテナ実寸（chartWidth）で描画し、リサイズで再描画する', () => {
  ['drawTrend', 'drawDivergingBars', 'drawHBars', 'drawDeptBar', 'drawDeptTrend'].forEach((name) => {
    assert.match(extractFunction(name), /chartWidth\(/, `${name} が実寸描画になっていない`);
  });
  assert.match(SOURCE, /window\.addEventListener\("resize"/, 'リサイズ再描画のリスナーがない');
  assert.match(SOURCE, /var xStep = W < 480/, '狭幅時の月ラベル間引きがない');
});

test('bindDrill は click と Enter/Space の両方で data-drill を拾う', () => {
  const src = extractFunction('bindDrill');
  assert.match(src, /"click"/);
  assert.match(src, /"keydown"/);
  assert.match(src, /"Enter"/);
  assert.match(src, /" "/);
  assert.match(src, /data-drill/);
});

test('renderDrillBar は 戻る / パンくず(to) / 解除(reset) を持つ', () => {
  const src = extractFunction('renderDrillBar');
  assert.match(src, /data-drill-act="pop"/);
  assert.match(src, /data-drill-act="to"/);
  assert.match(src, /data-drill-act="reset"/);
});

test('init は6チャートすべてをドリル対象として配線している', () => {
  ['trend', 'donut', 'rank', 'deptBar', 'deptDonut', 'deptTrend'].forEach(function (k) {
    assert.match(SOURCE, new RegExp('\\["' + k + '", els\\.' + k + '\\]'), `${k} がドリル対象にない`);
  });
  assert.match(SOURCE, /bindChartHover\(els\.trend, els\.tipTrend, \[trendLineSpec, storeBarSpec\]\)/);
  assert.match(SOURCE, /bindChartHover\(els\.rank, els\.tipRank, \[rankSpec, trendLineSpec\]\)/);
  assert.match(SOURCE, /bindChartHover\(els\.deptBar, els\.tipDeptBar, \[deptBarSpec, deptLineSpec\]\)/);
  assert.match(SOURCE, /bindChartHover\(els\.deptTrend, els\.tipDeptTrend, \[deptLineSpec, deptMonthSpec\]\)/);
});

test('render は店舗切替時にドリル状態をリセットする（古いフレームの持ち越し防止）', () => {
  assert.match(extractFunction('render'), /DRILL_KEYS\.forEach\(function \(k\) \{ DRILL\[k\]\.length = 0; \}\)/);
});

/* ================= サマリー（AI レポート）整形の契約 ================= */

test('isReportMeta はメタ行だけを識別する（本文段落を帯にしない）', () => {
  const isReportMeta = vm.runInContext(extractFunction('isReportMeta') + '\nisReportMeta;', vm.createContext({}));
  assert.equal(isReportMeta('店舗: 銀座 | 期間: 2025-12 | リスク: 中', true), true, 'ラベル＋|区切りの短い行');
  assert.equal(isReportMeta('対象: 全社（全店舗合算） | 期間: 2025-12', true), true);
  assert.equal(isReportMeta('売上35,995,906円、純利益4,016,083円。' + 'あ'.repeat(320), true), false, '長文は本文');
  assert.equal(isReportMeta('店舗: 銀座', true), false, '| がなければ本文扱い');
  assert.equal(isReportMeta('店舗: 銀座 | 期間: 2025-12', false), false, 'ラベル(<b>)なしは本文扱い');
  assert.equal(isReportMeta('', true), false);
  assert.equal(isReportMeta(null, true), false);
});

test('render は h1 除去後にメタ行へ .report-meta を付与する', () => {
  const src = extractFunction('render');
  const strip = src.indexOf('stripReportTitle(els.analysis)');
  const mark = src.indexOf('markReportMeta(els.analysis)');
  assert.ok(strip >= 0 && mark >= 0, 'stripReportTitle / markReportMeta の呼び出しがない');
  assert.ok(mark > strip, 'メタ行判定は h1 除去の後に行う');
});

test('サマリーのスタイルは上品トーン（.report-meta / 強調の箱なし / 角丸表）を保つ', () => {
  assert.match(CSS, /#analysis-container > p\.report-meta\{/, 'メタ帯スタイルがない');
  assert.match(CSS, /#analysis-container strong, #analysis-container b\{[^}]*background: none/, '強調の箱が復活している');
  assert.match(CSS, /#analysis-container h2::before\{ content: none; \}/, '見出しの ▶ が復活している');
  assert.match(CSS, /#analysis-container table\{[^}]*border-radius: 10px/, '表が角丸トーンでない');
  // AI 出力の <table border="1"> は UA がセルへ格子線を当てるため、四辺リセットがないとグリッド表示になる
  assert.match(CSS, /#analysis-container th, #analysis-container td\{[^}]*border: 0;[^}]*border-bottom: 1px solid/, 'セルの格子線リセットがない');
  assert.match(CSS, /#analysis-container table\{[^}]*font-size: 13px/, '表の文字サイズが事業部別(13px)と不一致');
});

/* ================= live 化: trend/dept データセット取得への繋ぎ替え ================= */
// 旧 window.__TREND__ / window.__DEPT__（app.js 冒頭に焼き込んでいた集計スナップショット）を廃止し、
// DataFlow の集計出力データセット（alias: trend / dept）から live 取得するよう繋ぎ替えた。
// 凍結スナップショットが実データ差し替え時に黙って FAKE 化するのを防ぐのが目的。以下はその契約を固定する。

test('buildDept は 部門×月 行を DEPT オブジェクト（divisions=FY合計 / monthly=系列）へ再構成する', () => {
  const deptCtx = vm.createContext({});
  vm.runInContext(
    'var DEPT_COLORS = { APPA:"#7F1D2D", LIFE:"#B23A48", FOOD:"#5F7A64", NEW:"#B8863B" };\n' +
    extractFunction('num') + '\n' + extractFunction('buildDept'),
    deptCtx
  );
  const buildDept = vm.runInContext('buildDept', deptCtx);

  assert.equal(buildDept([]), null, '空行は null（事業部タブが自動的に隠れる）');
  assert.equal(buildDept(null), null);

  const rows = [
    { period: '2025-01', code: 'APPA', name: '衣料品事業部', rev: 100, cogs: 40, variance: 5 },
    { period: '2025-02', code: 'APPA', name: '衣料品事業部', rev: 120, cogs: 50, variance: -3 },
    { period: '2025-01', code: 'FOOD', name: '食品事業部', rev: 60, cogs: 20, variance: 2 }
  ];
  const d = buildDept(rows);
  assert.equal(d.fy, 2025);
  assert.equal(d.from, '2025-01');
  assert.equal(d.to, '2025-02');
  assert.equal(json(d.monthly.periods), json(['2025-01', '2025-02']), '期間は昇順の distinct');

  // divisions は出現順（APPA→FOOD）。FY 合計・粗利・予算・達成率・配色を固定。
  assert.equal(json(d.divisions.map((x) => x.code)), json(['APPA', 'FOOD']));
  const appa = d.divisions[0];
  assert.equal(appa.rev, 220);          // 100+120
  assert.equal(appa.cogs, 90);          // 40+50
  assert.equal(appa.gross, 130);        // rev-cogs
  assert.equal(appa.variance, 2);       // 5+(-3)
  assert.equal(appa.budget, 128);       // gross-variance
  assert.equal(appa.achieve, 101.6);    // round(130/128*1000)/10
  assert.equal(appa.color, '#7F1D2D');  // DEPT_COLORS[APPA]
  assert.equal(appa.name, '衣料品事業部');

  // monthly.series は各事業部の月次売上（欠測月は 0 埋め）。
  const appaSeries = d.monthly.series.find((s) => s.code === 'APPA');
  const foodSeries = d.monthly.series.find((s) => s.code === 'FOOD');
  assert.equal(json(appaSeries.rev), json([100, 120]));
  assert.equal(json(foodSeries.rev), json([60, 0]), '2月に FOOD 行が無ければ 0 埋め');

  // 未知コードの配色フォールバック。
  const unknown = buildDept([{ period: '2025-01', code: 'XYZ', name: '謎', rev: 1, cogs: 0, variance: 0 }]);
  assert.equal(unknown.divisions[0].color, '#8896A6');
});

test('埋め込み集計スナップショット（window.__TREND__= / window.__DEPT__=）は廃止されている', () => {
  assert.doesNotMatch(SOURCE, /window\.__TREND__\s*=\s*\[/, '旧 __TREND__ 配列が残存している');
  assert.doesNotMatch(SOURCE, /window\.__DEPT__\s*=\s*\{/, '旧 __DEPT__ オブジェクトが残存している');
});

test('trend/dept は live データセットから取得する（loaders 配線＋読取点が TREND/DEPT を参照）', () => {
  // ローダーとブートストラップ配線
  assert.match(SOURCE, /function loadTrend\(\)/, 'loadTrend がない');
  assert.match(SOURCE, /function loadDept\(\)/, 'loadDept がない');
  assert.match(SOURCE, /function buildDept\(/, 'buildDept がない');
  assert.match(SOURCE, /\/data\/v1\/trend\?fields=/, 'trend データセットを proxy 取得していない');
  assert.match(SOURCE, /\/data\/v1\/dept\?fields=/, 'dept データセットを proxy 取得していない');
  assert.match(SOURCE, /Promise\.all\(\[loadSummary\(\), loadCompanyAi\(\), loadTrend\(\), loadDept\(\)\]\)/, 'ブートストラップに loadTrend/loadDept が合流していない');
  assert.match(SOURCE, /TREND = res\[2\]/, 'TREND へ代入していない');
  assert.match(SOURCE, /DEPT = res\[3\]/, 'DEPT へ代入していない');
  // 読取点は window.__TREND__ ではなくモジュール変数 TREND を使う
  assert.match(SOURCE, /buildStorePeriodRows\(TREND, period\)/);
  assert.match(SOURCE, /buildMonthDetail\(TREND, f\.storeId, f\.period\)/);
  assert.doesNotMatch(SOURCE, /window\.__TREND__\s*\|\|/, '読取点がまだ window.__TREND__ を参照している');
  // フィールド定数
  assert.match(SOURCE, /TREND_FIELDS\s*=\s*\["period", "store_id"/);
  assert.match(SOURCE, /DEPT_FIELDS\s*=\s*\["period", "code"/);
});
