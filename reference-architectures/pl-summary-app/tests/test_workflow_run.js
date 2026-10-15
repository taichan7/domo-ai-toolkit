const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../pro-code/workflow-run.js'), 'utf8');
const settle = () => new Promise((resolve) => setImmediate(resolve));

const progressPath = '/workflows/instances/22222222-2222-4222-8222-222222222222/';
function harness(status = {ok: true, status: 'IDLE', running: false, progress_path: progressPath}) {
  const nodes = new Map(), calls = [], saved = new Map();
  let document;
  function get(id) {
    if (!nodes.has(id)) {
      const listeners = new Map();
      nodes.set(id, {
        open: false, disabled: false, isConnected: true, textContent: '', returnValue: '',
        addEventListener(type, fn) { listeners.set(type, fn); },
        dispatch(type, event = {}) { if (listeners.has(type)) listeners.get(type)(event); },
        focus() { document.activeElement = this; },
        setAttribute() {}, classList: {toggle() {}}, showModal() { this.open = true; },
        close(value) { this.open = false; this.returnValue = value; queueMicrotask(() => this.dispatch('close')); },
        querySelectorAll: () => [get('close'), get('workflow-cancel'), get('workflow-confirm-yes')],
        getBoundingClientRect: () => ({left: 100, top: 100, right: 500, bottom: 500})
      });
    }
    return nodes.get(id);
  }
  const events = {};
  document = {body: {style: {overflow: 'auto'}}, hidden: false, activeElement: null,
    getElementById: get, addEventListener(type, fn) { events[type] = fn; }};
  const navigations = [];
  const context = {document, console, Date, Promise, Event: class {}, setTimeout: () => 0, clearTimeout() {},
    sessionStorage: {getItem: (key) => saved.get(key) || null, setItem: (key, value) => saved.set(key, value)},
    addEventListener(type, fn) { events[type] = fn; }, dispatchEvent() {},
    domo: {navigate: (path, newTab) => navigations.push({path, newTab}), async post(url, body) {
      calls.push({url, body});
      return {result: body.operation === 'start'
        ? {ok: true, instance_id: 'test-instance', status: 'IN_PROGRESS', running: true, progress_path: progressPath}
        : status};
    }}};
  context.window = context;
  vm.createContext(context);
  const marker = source.lastIndexOf('})();');
  assert.ok(marker > 0);
  vm.runInContext(source.slice(0, marker) + 'window.testRun = {state, els, call, checkStatus, confirmRun, startWorkflow, closeConfirmation, finishConfirmation};' + source.slice(marker), context);
  events.DOMContentLoaded();
  return {app: context.testRun, context, get, calls, saved, events, document, navigations};
}

test('startup is read-only and confirmation itself never starts a workflow', async () => {
  const h = harness();
  await settle();
  h.get('workflow-run').dispatch('click');
  assert.equal(h.get('workflow-confirm').open, true);
  assert.equal(h.document.activeElement, h.get('workflow-cancel'));
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].body.operation, 'status');
  assert.equal(h.calls[0].url, '/domo/codeengine/v2/packages/plReportApi');
});

test('yes is the only execution path and duplicate close/click cannot post twice', async () => {
  const h = harness();
  await settle();
  h.app.confirmRun();
  h.get('workflow-confirm').close('default');
  await settle();
  h.app.finishConfirmation();
  h.app.startWorkflow();
  assert.equal(h.calls.filter((call) => call.body.operation === 'start').length, 1);
  assert.equal(h.app.state.running, true);
  assert.equal(h.get('workflow-run').disabled, true);
  assert.equal(h.document.body.style.overflow, 'auto');
  assert.equal(h.document.activeElement, h.get('workflow-run'));
  assert.equal(JSON.parse(h.saved.get('pl-workflow-run')).instanceId, 'test-instance');
});

test('cancel, Escape and pagehide discard the action and restore scroll/focus', async () => {
  for (const dismiss of [
    (h) => h.get('workflow-confirm').close('cancel'),
    (h) => h.get('workflow-confirm').dispatch('cancel', {preventDefault() {}}),
    (h) => h.events.pagehide()
  ]) {
    const h = harness();
    await settle();
    h.app.confirmRun();
    dismiss(h);
    await settle();
    assert.equal(h.calls.filter((call) => call.body.operation === 'start').length, 0);
    assert.equal(h.app.state.pending, null);
    assert.equal(h.document.body.style.overflow, 'auto');
  }
});

test('missing confirmation or unsupported dialog fails closed', async () => {
  const h = harness();
  await settle();
  h.app.els.dialog = null;
  h.app.confirmRun();
  assert.equal(h.calls.length, 1);
  assert.match(h.get('workflow-status').textContent, /確認画面を表示できません/);
});

test('existing in-progress run disables execution but still allows status checks', async () => {
  const h = harness({ok: true, instance_id: 'existing', status: 'IN_PROGRESS', running: true});
  await settle();
  h.app.confirmRun();
  assert.equal(h.get('workflow-confirm').open, false);
  assert.equal(h.get('workflow-run').disabled, true);
  await h.app.checkStatus();
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].body.request.instance_id, 'existing');
});

test('ambiguous start locks resubmission and never retries automatically', async () => {
  const h = harness();
  await settle();
  h.context.domo.post = async (url, body) => {
    h.calls.push({url, body});
    return {result: {ok: false, error: {code: 'START_UNCONFIRMED', message: '実行状況を確認してください'}}};
  };
  await h.app.startWorkflow();
  assert.equal(h.app.state.unknown, true);
  assert.equal(h.get('workflow-run').disabled, true);
  h.app.startWorkflow();
  assert.equal(h.calls.filter((call) => call.body.operation === 'start').length, 1);
});

test('status failure cannot silently enable the execute button', async () => {
  const h = harness({ok: false, error: {code: 'INTERNAL_ERROR', message: '権限を確認してください'}});
  await settle();
  assert.equal(h.get('workflow-run').disabled, true);
  assert.match(h.get('workflow-status').textContent, /権限を確認/);
});

test('queued close after cancellation cannot consume a reopened confirmation', async () => {
  const h = harness();
  await settle();
  h.app.confirmRun();
  h.app.closeConfirmation();
  h.app.confirmRun();
  await settle();
  assert.equal(h.get('workflow-confirm').open, true);
  assert.ok(h.app.state.pending);
  assert.equal(h.calls.length, 1);
});

test('frontend contains no direct workflow start URL or production model id', () => {
  assert.doesNotMatch(source, /instances\/message|workflow\/v1\/models|d60ac21b/);
  const html = fs.readFileSync(path.join(__dirname, '../pro-code/index.html'), 'utf8');
  assert.match(html, /全店舗と全社/);
  assert.match(html, /メール通知/);
  assert.match(html, /value="cancel" autofocus/);
});

test('progress opens the server-resolved relative child Workflow path in a new tab without execution', async () => {
  const h = harness();
  await settle();
  h.get('workflow-check').dispatch('click');
  assert.deepEqual(h.navigations, [{path: progressPath, newTab: true}]);
  assert.equal(h.calls.length, 1);
});

test('untrusted external progress URL is not navigable', async () => {
  const h = harness({ok: true, status: 'IDLE', running: false, progress_path: 'https://example.invalid/'});
  await settle();
  assert.equal(h.get('workflow-check').disabled, true);
  h.get('workflow-check').dispatch('click');
  assert.equal(h.navigations.length, 0);
});
