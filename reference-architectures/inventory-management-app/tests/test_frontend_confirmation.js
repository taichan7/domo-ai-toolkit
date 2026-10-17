const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../pro-code/app.js'), 'utf8');
const configSource = fs.readFileSync(path.join(__dirname, '../pro-code/config.js'), 'utf8');

function harness() {
  const nodes = new Map(), calls = [];
  let document;
  function node() {
    const listeners = new Map(), classes = new Set();
    let html = '', text = '';
    return {
      hidden: true, open: false, disabled: false, value: '', checked: true, isConnected: true,
      style: {}, dataset: {}, children: [], lastChild: {textContent: ''},
      classList: {add: (...names) => names.forEach((name) => classes.add(name)), remove: (...names) => names.forEach((name) => classes.delete(name)), toggle: (name, on) => on ? classes.add(name) : classes.delete(name), contains: (name) => classes.has(name)},
      get innerHTML() { return html || text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); },
      set innerHTML(value) { html = value; },
      get textContent() { return text; }, set textContent(value) { text = String(value); html = ''; },
      addEventListener(type, handler) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(handler); },
      dispatch(type, event = {}) { for (const handler of listeners.get(type) || []) handler(event); },
      focus() { document.activeElement = this; }, setAttribute() {}, removeAttribute() {},
      querySelector: () => node(), querySelectorAll: () => [], appendChild() {}, remove() {}, scrollTo() {},
      showModal() { this.open = true; },
      close(value = '') { this.returnValue = value; this.open = false; queueMicrotask(() => this.dispatch('close')); },
      getBoundingClientRect: () => ({left: 100, right: 500, top: 100, bottom: 500})
    };
  }
  const get = (id) => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  document = {
    readyState: 'loading', activeElement: null, body: {style: {overflow: 'auto'}},
    addEventListener() {}, querySelectorAll: () => [], querySelector: () => node(),
    getElementById: get, createElement: node, documentElement: {dataset: {}, style: {setProperty() {}}}
  };
  const context = {
    document, console, Intl, setTimeout: () => 0, clearTimeout() {}, addEventListener() {}, scrollTo() {},
    location: {hostname: 'localhost'}, navigator: {userAgent: ''},
    matchMedia: () => ({matches: false}),
    InventoryData: {async callFunction(name, request) { calls.push({name, payload: JSON.parse(request.request_json)}); return {ok: false, error: {message: 'テスト用通信エラー'}}; }}
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(configSource, context);
  const exposed = 'window.testApp = {state, elements, cacheElements, bindEvents, showActionConfirmation, cancelConfirmation, handleConfirmClose, confirmTransaction, confirmShortageNotification, submitMaster, confirmMasterDelete, invalidateReview, switchView};';
  assert.ok(source.endsWith('})(window, document);\n'));
  vm.runInContext(source.replace('})(window, document);', `${exposed}\n})(window, document);`), context);
  const app = context.testApp;
  app.cacheElements();
  app.bindEvents();
  app.state.user = {isAdmin: true, email: 'operator@example.invalid', name: '利用者'};
  app.state.location = {location_code: 'LOC-01', location_name: '第1倉庫', active: true};
  app.state.item = {item_code: 'ITEM-01', item_name: '安全手袋', unit: '双', active: true};
  app.state.quantity = 2;
  app.state.requestId = 'request-fixed';
  app.state.data.balances = [{location_code: 'LOC-01', item_code: 'ITEM-01', quantity: 10}];
  app.state.data.locations = [app.state.location];
  app.state.data.items = [app.state.item];
  return {app, get, document, calls};
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('registration and notification clicks open confirmation without making API calls', () => {
  for (const button of ['submit-button', 'run-notification']) {
    const h = harness();
    h.get(button).dispatch('click');
    assert.equal(h.get('confirm-dialog').open, true);
    assert.equal(h.document.activeElement, h.get('confirm-cancel'));
    assert.equal(h.document.body.style.overflow, 'hidden');
    assert.equal(h.calls.length, 0);
  }
});

test('取引モーダルは最終ゲートとして純増減だけに絞り（INV-016）、はいで1回だけ実行する', async () => {
  const h = harness();
  h.app.state.reason = '<img src=x onerror=alert(1)>';
  h.app.confirmTransaction();
  // INV-016: STEP4 が全掲するロケーション/品目/数量/理由はモーダルで再掲しない。純増減だけ残す。
  assert.match(h.get('confirm-details').innerHTML, /10 → 12 双/);
  assert.doesNotMatch(h.get('confirm-details').innerHTML, /第1倉庫（LOC-01）/);
  assert.doesNotMatch(h.get('confirm-details').innerHTML, /理由・メモ/);
  // 理由（自由入力）はモーダルに再掲しないため、ここに未エスケープの生タグも持ち込まれない
  //（STEP4 review-list 側の escape は test_frontend_guards の reviewTransaction テストで担保）。
  assert.doesNotMatch(h.get('confirm-details').innerHTML, /<img/);
  // 操作と数量はタイトルに出す（最終ゲートとして何を確定するか明示）。
  assert.match(h.get('confirm-title').textContent, /入庫 2 双 を登録しますか？/);
  // 二重送信防止・サーバ在庫再チェックは温存＝確定で register_transaction を request_id 付きで1回だけ。
  h.get('confirm-dialog').close('default');
  await settle();
  h.app.handleConfirmClose();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].name, 'register_transaction');
  assert.equal(h.calls[0].payload.request_id, 'request-fixed');
  assert.equal(h.calls[0].payload.quantity, 2);
  assert.equal(h.app.state.pendingConfirm, null);
  assert.equal(h.document.activeElement, h.get('submit-button'));
  assert.equal(h.document.body.style.overflow, 'auto');
});

test('cancel, Escape and backdrop dismiss without calls or lost input', async () => {
  for (const cancel of [
    (h) => h.get('confirm-dialog').close('cancel'),
    (h) => h.get('confirm-dialog').dispatch('cancel', {preventDefault() {}}),
    (h) => h.get('confirm-dialog').dispatch('click', {target: h.get('confirm-dialog'), clientX: 0, clientY: 0})
  ]) {
    const h = harness();
    h.app.confirmTransaction();
    cancel(h);
    await settle();
    assert.equal(h.calls.length, 0);
    assert.equal(h.app.state.quantity, 2);
    assert.equal(h.app.state.requestId, 'request-fixed');
    assert.equal(h.app.state.pendingConfirm, null);
    assert.equal(h.document.body.style.overflow, 'auto');
    assert.equal(h.document.activeElement, h.get('submit-button'));
  }
});

test('notification states the recipient and email effect; yes invokes only the CE route', async () => {
  const h = harness();
  h.app.confirmShortageNotification();
  assert.match(h.get('confirm-details').innerHTML, /operator@example.invalid/);
  assert.match(h.get('confirm-message').textContent, /メールを送信/);
  h.get('confirm-dialog').close('default');
  await settle();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].name, 'start_shortage_notification');
  assert.equal(h.calls[0].payload.operator_email, 'operator@example.invalid');
});

test('all master saves, including active changes, require confirmation and retain the exact snapshot', async () => {
  for (const tab of ['item', 'location', 'rule']) {
    const h = harness();
    h.app.state.masterTab = tab;
    h.app.state.masterEditKey = 'existing';
    h.get('master-active').checked = false;
    h.get('master-item-code').value = 'ITEM-01';
    h.get('master-item-name').value = '更新品目';
    h.get('master-location-code').value = 'LOC-01';
    h.get('master-location-name').value = '更新倉庫';
    h.get('master-rule-location').value = 'LOC-01';
    h.get('master-rule-item').value = 'ITEM-01';
    h.get('master-rule-minimum').value = '5';
    h.app.submitMaster({preventDefault() {}});
    assert.equal(h.calls.length, 0);
    assert.match(h.get('confirm-details').innerHTML, /停止中/);  // INV-027: 無効化状態は「停止中」へ統一
    h.get('master-item-name').value = '確認後の未承認変更';
    h.get('confirm-dialog').close('default');
    await settle();
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].name, 'manage_master');
    assert.equal(h.calls[0].payload.action, `UPSERT_${tab.toUpperCase()}`);
    assert.equal(h.calls[0].payload.active, false);
    if (tab === 'item') assert.equal(h.calls[0].payload.item_name, '更新品目');
    if (tab === 'rule') assert.equal(h.calls[0].payload.minimum_quantity, 5);
  }
});

test('master deletion uses the same cancel-safe dialog with destructive styling and warnings', async () => {
  for (const tab of ['item', 'location', 'rule']) {
    const h = harness();
    const code = tab === 'rule' ? 'LOC-01|ITEM-01' : `${tab}-01`;
    h.app.confirmMasterDelete(tab, code, '削除対象');
    assert.equal(h.calls.length, 0);
    assert.equal(h.get('confirm-action').classList.contains('danger'), true);
    assert.match(h.get('confirm-message').textContent, /取り消せません/);
    h.get('confirm-dialog').close('default');
    await settle();
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].payload.action, `DELETE_${tab.toUpperCase()}`);
  }
});

test('invalid inputs and non-admin saves do not open confirmation or call CE', () => {
  const h = harness();
  h.app.state.quantity = 0;
  h.app.confirmTransaction();
  assert.equal(h.app.state.pendingConfirm, null);
  h.app.submitMaster({preventDefault() {}});
  assert.equal(h.app.state.pendingConfirm, null);
  h.app.state.user.isAdmin = false;
  h.app.confirmMasterDelete('item', 'ITEM-01', '品目');
  assert.equal(h.calls.length, 0);
});

test('missing confirmation components fail closed instead of skipping the user decision', () => {
  for (const id of ['confirm-dialog', 'confirm-title', 'confirm-message', 'confirm-details', 'confirm-action', 'confirm-cancel']) {
    const h = harness();
    h.app.elements[id] = null;
    h.app.confirmShortageNotification();
    assert.equal(h.calls.length, 0);
    assert.equal(h.app.state.pendingConfirm, null);
  }
  const h = harness();
  h.get('confirm-dialog').showModal = () => { throw new Error('showModal failed'); };
  h.app.confirmTransaction();
  assert.equal(h.calls.length, 0);
  assert.equal(h.app.state.pendingConfirm, null);
  assert.equal(h.document.body.style.overflow, 'auto');
});

test('double clicks do not replace the pending action, and no new confirmation opens while busy', async () => {
  const h = harness();
  h.app.confirmTransaction();
  h.app.confirmShortageNotification();
  assert.match(h.get('confirm-title').textContent, /入庫/);
  h.get('confirm-dialog').close('default');
  await settle();
  assert.equal(h.calls.length, 1);
  h.get('loading-overlay').hidden = false;
  h.app.confirmShortageNotification();
  assert.equal(h.get('confirm-dialog').open, false);
});

test('draft changes and view changes discard pending actions, including queued close events', async () => {
  const h = harness();
  h.app.confirmTransaction();
  h.app.invalidateReview();
  h.app.confirmShortageNotification();
  await settle();
  assert.equal(h.get('confirm-dialog').open, true);
  assert.ok(h.app.state.pendingConfirm);
  assert.equal(h.document.body.style.overflow, 'hidden');
  h.app.switchView('operations');
  await settle();
  assert.equal(h.calls.length, 0);
  assert.equal(h.app.state.pendingConfirm, null);
});

test('changed registration draft or revoked master permission cannot execute a stale approval', async () => {
  const h = harness();
  h.app.confirmTransaction();
  h.app.state.quantity = 3;
  h.get('confirm-dialog').close('default');
  await settle();
  assert.equal(h.calls.length, 0);
  h.get('master-item-code').value = 'ITEM-01';
  h.get('master-item-name').value = '品目';
  h.app.submitMaster({preventDefault() {}});
  h.app.state.user.isAdmin = false;
  h.get('confirm-dialog').close('default');
  await settle();
  assert.equal(h.calls.length, 0);
});

test('マスタ物理削除の確認に影響範囲（連鎖削除の現在庫・拠点数・基準在庫件数）を定量表示する（INV-017）', () => {
  const h = harness();
  h.app.state.data.balances = [
    {item_code: 'ITEM-01', location_code: 'LOC-01', quantity: 1000},
    {item_code: 'ITEM-01', location_code: 'LOC-02', quantity: 250},
    {item_code: 'ITEM-09', location_code: 'LOC-01', quantity: 3},
  ];
  h.app.state.data.rules = [
    {item_code: 'ITEM-01', location_code: 'LOC-01', rule_key: 'LOC-01|ITEM-01'},
    {item_code: 'ITEM-01', location_code: 'LOC-02', rule_key: 'LOC-02|ITEM-01'},
  ];
  h.app.confirmMasterDelete('item', 'ITEM-01', '安全手袋');
  const details = h.get('confirm-details').innerHTML;
  assert.match(details, /影響範囲/);
  assert.match(details, /2拠点に現在庫 計1,250 \/ 基準在庫2件を同時削除/);
  // 基準在庫（rule）単体の削除は在庫を道連れにしないため、影響範囲行は出さない。
  const h2 = harness();
  h2.app.confirmMasterDelete('rule', 'LOC-01|ITEM-01', 'LOC-01 / ITEM-01');
  assert.doesNotMatch(h2.get('confirm-details').innerHTML, /影響範囲/);
});

test('マスタ編集に未保存入力があると新規ボタンは破棄確認を挟み、確定で初めて初期化する（INV-018）', async () => {
  const h = harness();
  h.app.state.masterTab = 'item';
  // 編集途中（dirty）を再現：フォームに入力があったことにする（input で masterDirty=true）。
  h.get('master-form').dispatch('input', {});
  assert.equal(h.app.state.masterDirty, true);
  // 新規ボタン：dirty なので即初期化せず破棄確認を出す（まだ破棄していない）。
  h.get('master-new').dispatch('click');
  assert.equal(h.get('confirm-dialog').open, true);
  assert.equal(h.app.state.masterDirty, true);
  assert.equal(h.calls.length, 0);
  // 「破棄して移動」確定で初めて dirty 解消＋新規初期化（通信はしない）。
  h.get('confirm-dialog').close('default');
  await settle();
  assert.equal(h.app.state.masterDirty, false);
  assert.equal(h.calls.length, 0);
});

test('未保存入力が無ければ新規ボタンは確認を挟まず直接初期化する（INV-018 の無退行）', () => {
  const h = harness();
  h.app.state.masterDirty = false;
  h.get('master-new').dispatch('click');
  assert.equal(h.get('confirm-dialog').open, false);
});
