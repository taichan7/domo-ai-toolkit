import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const outputDir = process.argv[2] || path.join(os.tmpdir(), 'inventory-confirmation-shots');

async function browserChecks() {
  const results = [], errors = [];
  const get = (id) => document.getElementById(id);
  const dialog = get('confirm-dialog');
  const wait = () => new Promise((resolve) => setTimeout(resolve, 50));
  const check = (name, condition) => { if (!condition) throw new Error(name); results.push(name); };
  const calls = window.confirmationCalls;
  window.addEventListener('error', (event) => errors.push(event.message));
  window.addEventListener('unhandledrejection', (event) => errors.push(String(event.reason)));
  function open(id) { get(id).focus(); get(id).click(); }
  function checkDialog() {
    check('native modal is open', dialog.open && dialog.matches(':modal'));
    check('cancel receives initial focus', document.activeElement === get('confirm-cancel'));
    get('refresh-button').focus();
    check('background cannot receive focus', document.activeElement === get('confirm-cancel'));
    check('scroll locked', document.body.style.overflow === 'hidden');
    const rect = dialog.getBoundingClientRect();
    check('dialog fits viewport', rect.left >= 0 && rect.right <= window.innerWidth + 1 && rect.top >= 0 && rect.bottom <= window.innerHeight + 1);
    check('confirm action has a 48px touch target', get('confirm-action').getBoundingClientRect().height >= 48);
    check('cancel has a 48px touch target', get('confirm-cancel').getBoundingClientRect().height >= 48);
    check('no horizontal modal overflow', dialog.scrollWidth <= dialog.clientWidth + 1);
  }
  try {
    for (let i = 0; i < 40 && !document.querySelector('#location-options [data-code]'); i += 1) await wait();
    check('demo app loaded', !!document.querySelector('#location-options [data-code]'));
    document.querySelector('#location-options [data-code="LOC-01"]').click();
    document.querySelector('#item-options [data-code="ITEM-001"]').click();
    get('quantity').value = '2';
    get('quantity').dispatchEvent(new Event('input', {bubbles: true}));
    get('reason').value = '棚卸し確認・長いメモでも安全に表示します。'.repeat(8);
    get('reason').dispatchEvent(new Event('input', {bubbles: true}));
    get('review-button').click();
    open('submit-button');
    checkDialog();
    check('registration requires yes', calls.length === 0);
    check('review target and quantity are shown', get('confirm-details').textContent.includes('ITEM-001') && get('confirm-details').textContent.includes('入庫 2 双'));
    const overflowBefore = 'hidden';
    open('submit-button');
    check('repeat click preserves the same confirmation', get('confirm-title').textContent === '入庫を登録しますか？');
    get('confirm-cancel').click(); await wait();
    check('cancel never writes', calls.length === 0 && !dialog.open);
    check('cancel preserves quantity and returns focus', get('quantity').value === '2' && document.activeElement === get('submit-button'));
    check('scroll restored', document.body.style.overflow !== overflowBefore);
    open('submit-button');
    dialog.dispatchEvent(new Event('cancel', {cancelable: true})); await wait();
    check('Escape cancel event never writes', calls.length === 0 && !dialog.open);
    open('submit-button');
    dialog.querySelector('.close-button').click(); await wait();
    check('close button never writes', calls.length === 0 && !dialog.open);
    open('submit-button');
    dialog.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: 0, clientY: 0})); await wait();
    check('backdrop click never writes', calls.length === 0 && !dialog.open);
    open('submit-button');
    get('confirm-action').click(); get('confirm-action').click(); await wait();
    check('registration yes executes once', calls.length === 1 && calls[0].name === 'register_transaction');
    check('registration payload matches review', calls[0].payload.quantity === 2 && calls[0].payload.item_code === 'ITEM-001');
    check('failure preserves draft for retry', get('quantity').value === '2' && !get('submit-button').disabled);
    open('submit-button');
    get('confirm-action').click(); await wait();
    check('retry keeps the same request id', calls.length === 2 && calls[0].payload.request_id === calls[1].payload.request_id);

    document.querySelector('[data-view="dashboard"]').click();
    check('read navigation has no confirmation', !dialog.open);
    open('run-notification');
    checkDialog();
    check('email effect is explicit', get('confirm-message').textContent.includes('メールを送信'));
    get('confirm-cancel').click(); await wait();
    check('notification cancel never starts CE', calls.length === 2);
    open('run-notification');
    get('confirm-action').click(); await wait();
    check('notification yes invokes CE once', calls.length === 3 && calls[2].name === 'start_shortage_notification');

    document.querySelector('[data-view="history"]').click();
    document.querySelector('[data-record="item"]').click();
    get('master-item-code').value = 'ITEM-NEW';
    get('master-item-name').value = '<img src=x onerror=alert(1)>'.repeat(4);
    get('master-item-category').value = '安全用品';
    get('master-item-unit').value = '双';
    open('master-submit');
    checkDialog();
    check('master save is confirmed and escaped', calls.length === 3 && !get('confirm-details').querySelector('img'));
    get('confirm-cancel').click(); await wait();
    check('master cancel retains input', get('master-item-code').value === 'ITEM-NEW' && calls.length === 3);
    open('master-submit');
    get('confirm-action').click(); await wait();
    check('master yes invokes UPSERT_ITEM', calls.length === 4 && calls[3].payload.action === 'UPSERT_ITEM');
    document.querySelector('[data-master-edit="ITEM-001"]').click();
    get('master-active').checked = false;
    open('master-submit');
    check('active change is visible before save', get('confirm-details').textContent.includes('一時停止'));
    get('confirm-cancel').click(); await wait();
    open('master-delete');
    checkDialog();
    check('delete has clear irreversible warning', get('confirm-message').textContent.includes('取り消せません') && get('confirm-action').classList.contains('danger'));
    get('confirm-cancel').click(); await wait();
    check('delete cancel never writes', calls.length === 4);
    open('master-delete');
    get('confirm-action').click(); await wait();
    check('delete yes invokes DELETE_ITEM once', calls.length === 5 && calls[4].payload.action === 'DELETE_ITEM');

    document.querySelector('[data-view="operations"]').click();
    open('submit-button');
    window.dispatchEvent(new Event('pagehide')); await wait();
    check('pagehide cancels the pending action', !dialog.open && calls.length === 5);
    check('no document horizontal overflow', document.documentElement.scrollWidth <= window.innerWidth + 1);
    check('no browser exceptions', errors.length === 0);
    open('submit-button');
    const output = document.createElement('pre');
    output.id = 'confirmation-results';
    output.hidden = true;
    output.textContent = JSON.stringify({passed: results.length, results});
    document.body.appendChild(output);
    return {passed: results.length};
  } catch (error) {
    const output = document.createElement('pre');
    output.id = 'confirmation-results';
    output.textContent = JSON.stringify({passed: results.length, failure: error.message, errors, calls, toasts: get('toast-region').textContent});
    document.body.appendChild(output);
    return {passed: results.length, failure: error.message, errors, calls, toasts: get('toast-region').textContent};
  }
}

const taskDir = fs.mkdtempSync(path.join(os.tmpdir(), 'inventory-confirmations-'));
fs.mkdirSync(outputDir, {recursive: true});
const mock = `<script>
window.confirmationCalls = [];
const originalData = window.InventoryData;
window.InventoryData = {...originalData, callFunction: async (name, request) => {
  if (!['register_transaction', 'start_shortage_notification', 'manage_master'].includes(name)) return originalData.callFunction(name, request);
  window.confirmationCalls.push({name, payload: JSON.parse(request.request_json)});
  return {ok: false, error: {message: 'テスト用通信エラー（実データは変更しません）'}};
}};
</script>`;
const raw = fs.readFileSync(path.join(root, 'pro-code/index.html'), 'utf8');
const html = raw.replace('<head>', `<head><base href="${new URL(`file://${path.join(root, 'pro-code')}/`).href}">`)
  .replace('<script src="app.js"></script>', `${mock}<script src="app.js"></script>`);
const harnessPath = path.join(taskDir, 'confirmations.html');
fs.writeFileSync(harnessPath, html);
const profile = path.join(taskDir, 'chrome-profile');
const browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--remote-debugging-port=0',
  `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], {stdio: 'ignore'});
const exited = once(browser, 'exit');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;
try {
  const portFile = path.join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 100 && !fs.existsSync(portFile) && browser.exitCode === null; i += 1) await sleep(100);
  assert.ok(fs.existsSync(portFile), 'Chrome failed to start its local debugging endpoint');
  const port = fs.readFileSync(portFile, 'utf8').split('\n')[0];
  const response = await fetch(`http://127.0.0.1:${port}/json/list`);
  assert.ok(response.ok, 'Chrome debugging endpoint is not responsive');
  const targets = await response.json();
  const target = targets.find((entry) => entry.type === 'page');
  assert.ok(target?.webSocketDebuggerUrl, 'Chrome page target is missing');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await once(socket, 'open');
  const requests = new Map(), events = new Map();
  let nextId = 0;
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const pending = requests.get(message.id);
      if (!pending) return;
      requests.delete(message.id);
      if (message.error) pending.reject(new Error(JSON.stringify(message.error)));
      else pending.resolve(message.result);
    } else if (events.has(message.method)) {
      const resolve = events.get(message.method);
      events.delete(message.method);
      resolve(message.params);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    requests.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  const event = (name) => new Promise((resolve) => events.set(name, resolve));
  await send('Page.enable');
  for (const width of [1366, 768, 390]) {
    await send('Emulation.setDeviceMetricsOverride', {width, height: 940, deviceScaleFactor: 1, mobile: false});
    const loaded = event('Page.loadEventFired');
    await send('Page.navigate', {url: `file://${harnessPath}`});
    await loaded;
    const evaluated = await send('Runtime.evaluate', {expression: `(${browserChecks.toString()})()`, awaitPromise: true, returnByValue: true});
    assert.ok(!evaluated.exceptionDetails, JSON.stringify(evaluated.exceptionDetails));
    const report = evaluated.result.value;
    assert.ok(!report.failure, `${width}px: ${JSON.stringify(report)}`);
    assert.ok(report.passed >= 50, 'empty or incomplete browser test run');
    for (const key of ['Tab', 'Tab', 'Tab', 'Tab']) {
      await send('Input.dispatchKeyEvent', {type: 'keyDown', key, code: key, windowsVirtualKeyCode: 9});
      await send('Input.dispatchKeyEvent', {type: 'keyUp', key, code: key, windowsVirtualKeyCode: 9});
      const focused = await send('Runtime.evaluate', {expression: "document.getElementById('confirm-dialog').contains(document.activeElement)", returnByValue: true});
      assert.equal(focused.result.value, true, `${width}px: Tab escaped the native dialog`);
    }
    for (let i = 0; i < 4; i += 1) {
      await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, modifiers: 8});
      await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, modifiers: 8});
      const focused = await send('Runtime.evaluate', {expression: "document.getElementById('confirm-dialog').contains(document.activeElement)", returnByValue: true});
      assert.equal(focused.result.value, true, `${width}px: Shift+Tab escaped the native dialog`);
    }
    const shot = await send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(outputDir, `confirmation-${width}.png`), Buffer.from(shot.data, 'base64'));
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await sleep(100);
    const cancelled = await send('Runtime.evaluate', {expression: "!document.getElementById('confirm-dialog').open && window.confirmationCalls.length === 5 && document.activeElement === document.getElementById('submit-button')", returnByValue: true});
    assert.equal(cancelled.result.value, true, `${width}px: real Escape did not cancel and restore focus`);
    console.log(`${width}px: ${report.passed} confirmation assertions passed`);
  }
} finally {
  if (socket) socket.close();
  browser.kill();
  await exited;
  fs.unlinkSync(harnessPath);
  fs.rmSync(profile, {recursive: true, force: true});
  fs.rmdirSync(taskDir);
}
