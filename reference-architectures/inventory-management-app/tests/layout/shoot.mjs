/**
 * ローカル・レイアウト検証ハーネス（Chrome headless 実描画スクリーンショット）。
 *
 * なぜ必要か:
 *   このパッケージは複数顧客へフォルダごと配布するため、改修のたびに全幅でレイアウトが崩れて
 *   いないことを「デプロイ前に」目視できねばならない。jsdom は CSS レイアウトを評価しないため、
 *   実ブラウザ（Chrome headless）で実際に描画し PNG を出力する（ユニットテストでは捕まらない）。
 *
 * 対象は 2 つの Pro Code アプリ:
 *   app         … 在庫入出庫管理 UI（App Studio ページ1）。file:// では同梱デモデータで全描画。
 *                 入出庫／ダッシュボード／履歴の各ビューを nav ボタンで切り替えて撮影する。
 *   devguide    … 開発ガイド（App Studio ページ2）。縦スクロール1枚の静的文書。
 *                 データ非接続。既定はページ最上部フォールドを撮る（各幅で崩れないかを確認）。
 *
 * 使い方:
 *   node tests/layout/shoot.mjs                          # 両アプリ×代表幅
 *   node tests/layout/shoot.mjs --app app                # アプリ限定（app / devguide）
 *   node tests/layout/shoot.mjs --widths 1440,390        # 幅限定
 *   node tests/layout/shoot.mjs --app app --views dashboard   # ビュー限定
 *   node tests/layout/shoot.mjs --height 1400            # 縦を伸ばしてスクロール文書を長く撮る
 *   出力先: /tmp/inv-shots/<app>-<view>-<width>.png（--out で変更可）
 *
 * 注意（モバイル・ペルソナ）:
 *   在庫アプリのモバイル向け大ボタン化は、幅ではなくホスト属性 data-domo-platform="mobile" で
 *   切り替わる（applyMobilePersona）。file:// プレビューにその属性は付かないため、390px の撮影は
 *   「幅レスポンシブ」の確認であって Domo Mobile ホストのペルソナ確認ではない（実機は mobile-test-guide.md）。
 */

import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const NL = String.fromCharCode(10);  // ソースに逆スラッシュを入れないための改行定数
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
// 表示高。既定 940 は App Studio iframe の代表的な表示高。スクロール文書（開発ガイド）を
// 長く撮りたいときは --height を上げる。低い値で撮ると縦詰めの安全マージンも確認できる。
const DEFAULT_HEIGHT = 940;

// アプリごとの index.html と撮影ビュー。
//   app         … 在庫入出庫管理。nav の data-view でビュー切替（operations 既定）。
//   devguide    … 開発ガイド（単一スクロール文書）。ビューは 'main' のみ。
const APPS = {
  app: { dir: path.join(ROOT, 'pro-code'), views: ['operations', 'dashboard', 'history'] },
  devguide: { dir: path.join(ROOT, 'dev-guide-app'), views: ['main'] },
};
// レスポンシブ境界の内外を代表する幅（PC 広/中・タブレット・スマホ）。
const ALL_WIDTHS = [1680, 1366, 1024, 768, 390];

function parseArgs(argv) {
  const out = { apps: Object.keys(APPS), widths: ALL_WIDTHS, out: '/tmp/inv-shots', views: null, height: DEFAULT_HEIGHT };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const val = argv[i + 1];
    if (key === '--app' && val) { out.apps = val.split(',').map(function (s) { return s.trim(); }).filter(Boolean); i += 1; }
    else if (key === '--widths' && val) { out.widths = val.split(',').map(function (s) { return Number(s.trim()); }).filter(Boolean); i += 1; }
    else if (key === '--views' && val) { out.views = val.split(',').map(function (s) { return s.trim(); }).filter(Boolean); i += 1; }
    else if (key === '--height' && val) { out.height = Number(val) || DEFAULT_HEIGHT; i += 1; }
    else if (key === '--out' && val) { out.out = val; i += 1; }
  }
  return out;
}

// 起動後に目的ビューへ切り替え、描画完了で window.__HARNESS_DONE__ を立てる注入スクリプト。
//   app         … nav の data-view ボタンをクリックして該当ビューを表示。dashboard は KPI が
//                  描画される（#kpi-grid が空でなくなる）のを待つ。
//   devguide    … スクロール文書なので切替不要。DOM 構築後に少し待って完了扱い。
function switchScript(app, view) {
  if (app === 'app') {
    return `<script>(function(){
  var VIEW=${JSON.stringify(view)};
  function fillReady(){
    var grid=document.getElementById('kpi-grid');
    return VIEW!=='dashboard' || (grid && grid.children && grid.children.length>0);
  }
  function go(n){
    var btn=document.querySelector('.nav-item[data-view="'+VIEW+'"]');
    if(btn){ btn.click(); }
    if(fillReady()){ window.__HARNESS_DONE__=true; return; }
    if(n<100){ setTimeout(function(){ go(n+1); }, 60); return; }
    window.__HARNESS_DONE__=true;
  }
  function start(){ setTimeout(function(){ go(0); }, 300); }
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', start); } else { start(); }
})();</script>`;
  }
  return `<script>(function(){
  function done(){ window.__HARNESS_DONE__=true; }
  function start(){ setTimeout(done, 500); }
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', start); } else { start(); }
})();</script>`;
}

// index.html を正本として読み、<base> でアセットを解決し、末尾に注入スクリプトを足す。
function buildHarness(app, view) {
  const dir = APPS[app].dir;
  const raw = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  const baseTag = `<base href='file://${dir}/'>`;
  let html = raw.replace('<head>', `<head>${NL}  ${baseTag}`);
  html = html.replace('</body>', `  ${switchScript(app, view)}${NL}</body>`);
  return html;
}

function main() {
  const args = parseArgs(process.argv);
  if (!fs.existsSync(CHROME)) { console.error('Chrome が見つかりません:', CHROME); process.exit(2); }
  const tmpDir = path.join(os.tmpdir(), 'inv-layout');
  fs.mkdirSync(tmpDir, { recursive: true });
  fs.mkdirSync(args.out, { recursive: true });

  const produced = [];
  for (const app of args.apps) {
    if (!APPS[app]) { console.log('SKIP 不明なアプリ: ' + app); continue; }
    const views = args.views || APPS[app].views;
    for (const view of views) {
      const harnessPath = path.join(tmpDir, 'harness-' + app + '-' + view + '.html');
      fs.writeFileSync(harnessPath, buildHarness(app, view), 'utf8');
      for (const width of args.widths) {
        const outPath = path.join(args.out, app + '-' + view + '-' + width + '.png');
        try {
          execFileSync(CHROME, [
            '--headless=new', '--disable-gpu', '--hide-scrollbars',
            '--force-device-scale-factor=1', '--run-all-compositor-stages-before-draw',
            '--window-size=' + width + ',' + args.height,
            '--virtual-time-budget=7000',
            '--screenshot=' + outPath,
            'file://' + harnessPath,
          ], { stdio: ['ignore', 'ignore', 'ignore'], timeout: 45000 });
          const ok = fs.existsSync(outPath) && fs.statSync(outPath).size > 0;
          produced.push({ app, view, width, ok });
          console.log((ok ? 'OK  ' : 'FAIL') + ' ' + app + ' [' + view + '] @ ' + width + 'px -> ' + outPath);
        } catch (err) {
          produced.push({ app, view, width, ok: false });
          console.log('FAIL ' + app + ' [' + view + '] @ ' + width + 'px (' + String((err && err.message) || err).slice(0, 80) + ')');
        }
      }
    }
  }
  const okCount = produced.filter(function (p) { return p.ok; }).length;
  console.log('');
  console.log(okCount + '/' + produced.length + ' screenshots produced in ' + args.out);
  if (okCount === 0) { process.exit(1); }
}

main();
