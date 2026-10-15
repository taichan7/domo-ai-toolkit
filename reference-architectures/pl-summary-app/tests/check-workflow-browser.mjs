import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = process.argv[2] || path.join(os.tmpdir(), 'pl-workflow-shots');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'pl-workflow-browser-'));
const profile = path.join(temporary, 'chrome-profile');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const fixture = `<script>
window.workflowCalls = []; window.workflowNavigations = [];
window.mockStatus = {ok:true, status:'IDLE', running:false, progress_path:'/workflows/instances/22222222-2222-4222-8222-222222222222/'};
window.domo = {
  navigate: (path, newTab) => workflowNavigations.push({path,newTab}),
  get: async (url) => url.includes('/trend') ? [{period:'2025-12',store_id:'S001',store:'テスト店舗',region:'試験',rev:1000,profit:100}] :
    url.includes('/dept') ? [] : [{'店舗ID':'S001','店舗名':'テスト店舗','地域':'試験','期間':'2025-12','総売上':1000,'総費用':900,'純利益':100,'利益率':10}],
  post: async (url, body) => {
    if (!url.includes('/codeengine/')) return [{content:{generated_at:'2026-10-15',
      analysis_html:'<h1>テスト分析</h1><h2>損益の確認</h2><p><b>数値</b>を保持します。</p><table><tr><th>売上</th><td>1,000円</td></tr></table><img src=x onerror=\"window.xssExecuted=true\"><script>window.xssExecuted=true</scr'+'ipt><a href=\"javascript:window.xssExecuted=true\">リンク</a><div id=\"workflow-run\" onclick=\"window.xssExecuted=true\">本文</div>'}}];
    workflowCalls.push(body);
    return {result: body.operation === 'start' ? {...mockStatus,instance_id:'test-run',status:'IN_PROGRESS',running:true} : mockStatus};
  }
};
</script>`;
const html = fs.readFileSync(path.join(root, 'pro-code/index.html'), 'utf8')
  .replace('<head>', `<head><base href="file://${path.join(root, 'pro-code')}/">`)
  .replace('<script src="vendor/domo.js"></script>', fixture);
const harness = path.join(temporary, 'harness.html');
fs.writeFileSync(harness, html);
fs.mkdirSync(output, {recursive: true});
const browser = spawn(process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--disable-gpu', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', 'about:blank'],
  {stdio: 'ignore'});
const exited = once(browser, 'exit');
let socket;
try {
  const portFile = path.join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 100 && !fs.existsSync(portFile) && browser.exitCode === null; i += 1) await sleep(100);
  assert.ok(fs.existsSync(portFile), 'Chrome failed to start');
  const port = fs.readFileSync(portFile, 'utf8').split('\n')[0];
  const response = await fetch(`http://127.0.0.1:${port}/json/list`);
  assert.ok(response.ok);
  const target = (await response.json()).find((row) => row.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await once(socket, 'open');
  const pending = new Map(), events = new Map();
  let id = 0;
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const request = pending.get(message.id);
      if (!request) return;
      pending.delete(message.id);
      if (message.error) request.reject(new Error(JSON.stringify(message.error)));
      else request.resolve(message.result);
    } else if (events.has(message.method)) {
      events.get(message.method)(message.params);
      events.delete(message.method);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const key = ++id; pending.set(key, {resolve, reject});
    socket.send(JSON.stringify({id: key, method, params}));
  });
  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const shot = async (name) => {
    const result = await send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(path.join(output, name), Buffer.from(result.data, 'base64'));
  };
  await send('Page.enable');
  for (const width of [1366, 768, 390]) {
    await send('Emulation.setDeviceMetricsOverride', {width, height: 940, deviceScaleFactor: 1, mobile: false});
    const loaded = new Promise((resolve) => events.set('Page.loadEventFired', resolve));
    await send('Page.navigate', {url: `file://${harness}`}); await loaded; await sleep(250);
    const get = (id) => `document.getElementById(${JSON.stringify(id)})`;
    assert.equal(await evaluate(`!${get('dashboard')}.classList.contains('hidden')`), true, 'dashboard failed to load');
    assert.equal(await evaluate('window.xssExecuted !== true'), true, 'stored report HTML executed code');
    assert.equal(await evaluate(`${get('analysis-container')}.querySelector('img,script,[onclick],[href],[id]') === null`), true, 'active report markup remains');
    assert.equal(await evaluate(`${get('analysis-container')}.querySelector('table td').textContent === '1,000円'`), true, 'report table content changed');
    assert.equal(await evaluate(`document.querySelector('.workflow-toolbar') === null && ${get('workflow-status')}.getBoundingClientRect().width === 1`), true, 'unnecessary status band returned');
    assert.equal(await evaluate('workflowCalls.every(c => c.operation === "status")'), true);
    await evaluate(`${get('workflow-check')}.click()`);
    assert.equal(await evaluate('workflowNavigations.length === 1 && workflowNavigations[0].newTab === true && workflowNavigations[0].path.startsWith("/workflows/instances/")'), true);
    await shot(`overview-${width}.png`);
    await evaluate(`${get('workflow-run')}.focus(); ${get('workflow-run')}.click()`);
    assert.equal(await evaluate(`${get('workflow-confirm')}.matches(':modal') && document.activeElement === ${get('workflow-cancel')}`), true);
    assert.equal(await evaluate(`${get('workflow-confirm-yes')}.getBoundingClientRect().height >= 48`), true);
    assert.equal(await evaluate(`(() => {const r=${get('workflow-confirm')}.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+1 && r.bottom<=innerHeight+1;})()`), true);
    for (let i = 0; i < 5; i += 1) {
      await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9});
      await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9});
      assert.equal(await evaluate(`${get('workflow-confirm')}.contains(document.activeElement)`), true);
    }
    await shot(`confirmation-${width}.png`);
    await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
    await sleep(100);
    assert.equal(await evaluate(`!${get('workflow-confirm')}.open && document.activeElement === ${get('workflow-run')}`), true);
    assert.equal(await evaluate('workflowCalls.filter(c => c.operation === "start").length'), 0);
    await evaluate(`${get('workflow-run')}.click(); ${get('workflow-confirm-yes')}.click()`); await sleep(100);
    assert.equal(await evaluate('workflowCalls.filter(c => c.operation === "start").length'), 1);
    assert.equal(await evaluate(`${get('workflow-run')}.disabled && ${get('workflow-run')}.textContent === "更新中…"`), true);
    await evaluate(`${get('workflow-check')}.click()`);
    assert.equal(await evaluate('workflowNavigations.length === 2'), true);
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), true, `${width}px horizontal overflow`);
    console.log(`${width}px: quiet UI, relative new-tab navigation, modal/keyboard and single-execution checks passed`);
  }
} finally {
  if (socket) socket.close();
  browser.kill(); await exited;
  fs.unlinkSync(harness);
  fs.rmSync(profile, {recursive: true, force: true});
  fs.rmdirSync(temporary);
}
