/**
 * Pro Code サムネイル（300x300）を thumbnail.html から実描画で生成する。
 *
 * なぜ: App Studio のカード一覧で見える唯一の画像で、publish に必須。開発ガイド（ハンズオン）の
 * 見た目（calm-blue 紺青・ターミナル・調べる→直す→公開→確認のフロー）に合わせる。
 * 工程: Chrome headless で実描画（600 CSS px × device-scale-factor 2 ＝ 1200px）→ macOS 標準 sips で
 *       300x300 へ縮小する（sips に依存するため本スクリプトは macOS 専用）。
 * 注意: thumbnail.html は Google Fonts（Noto Sans JP）をネットワークから読む。オフライン/低速時は
 *       OS 標準ゴシックにフォールバックして描画される（書体だけが変わる・寸法は不変）。
 * 版の単一ソース: manifest.json の version を正とし、thumbnail.html の版表記が一致しなければ
 *                描画前に失敗する（画像に第2の版ソースが焼き込まれるドリフトを防ぐ）。
 *
 * 使い方:
 *   node inventory-management-app/dev-guide-app/tests/make-thumbnail.mjs
 *   出力: inventory-management-app/dev-guide-app/thumbnail.png（300x300）
 */
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SOURCE = path.join(HERE, 'thumbnail.html');
const TARGET = path.join(ROOT, 'thumbnail.png');
const MANIFEST = path.join(ROOT, 'manifest.json');
/** Chrome 実体の場所を OS ごとに解決する（macOS / Windows / Linux）。CHROME_PATH で上書き可。 */
function resolveChrome() {
  const candidates = [];
  if (process.env.CHROME_PATH) candidates.push(process.env.CHROME_PATH);
  if (process.platform === 'darwin') {
    candidates.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
  } else if (process.platform === 'win32') {
    candidates.push(
      path.join(process.env['PROGRAMFILES'] || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(process.env['LOCALAPPDATA'] || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    );
  } else {
    candidates.push('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser');
  }
  return candidates.find(function (p) { return p && fs.existsSync(p); }) || '';
}
const SIZE = 300;      // 最終サイズ（App Studio 要件）
const SUPERSAMPLE = 2; // 600 CSS px × DSF 2 ＝ 1200px で描画し、sips で 300px へ縮小（輪郭を滑らかに）

function main() {
  // 縮小は macOS の sips に依存するため本スクリプトは macOS 専用。無駄な描画を避け、最初に判定する。
  if (process.platform !== 'darwin') {
    console.error('300x300 への縮小は macOS の sips が必要です（macOS で実行してください）。');
    process.exit(2);
  }
  const chrome = resolveChrome();
  if (!chrome) {
    console.error('Chrome が見つかりません。Google Chrome を入れるか、環境変数 CHROME_PATH に chrome(.exe) の場所を設定してください。');
    process.exit(2);
  }
  // 版の単一ソース化: manifest.json の version を正とし、thumbnail.html の版表記と一致しなければ描画しない。
  const version = JSON.parse(fs.readFileSync(MANIFEST, 'utf8')).version;
  const srcHtml = fs.readFileSync(SOURCE, 'utf8');
  if (!srcHtml.includes('v' + version)) {
    console.error('版の不一致: manifest.json=' + version + ' が thumbnail.html に見つかりません。thumbnail.html のフッター版表記を v' + version + ' に更新してください。');
    process.exit(1);
  }

  // 一意な一時ディレクトリへ描画し、成否によらず finally で片付ける（固定名の残骸を再利用しない）。
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'devguide-thumb-'));
  const tmp = path.join(tmpDir, 'render.png');
  const win = 600; // headless(macOS) の最小ウィンドウ幅 500 を上回る
  try {
    execFileSync(chrome, [
      '--headless=new', '--disable-gpu', '--hide-scrollbars',
      `--force-device-scale-factor=${SUPERSAMPLE}`,
      `--window-size=${win},${win}`,
      '--virtual-time-budget=4000',
      `--screenshot=${tmp}`,
      'file://' + SOURCE,
    ], { stdio: ['ignore', 'ignore', 'inherit'], timeout: 60000 });
    if (!fs.existsSync(tmp) || fs.statSync(tmp).size < 1000) {
      console.error('Chrome が描画 PNG を生成しませんでした（空／極小）。');
      process.exit(1);
    }
    execFileSync('sips', ['-z', String(SIZE), String(SIZE), tmp, '--out', TARGET], { stdio: ['ignore', 'ignore', 'inherit'] });
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
  // 寸法は整数で厳密比較する（部分一致の正規表現だと 3000 が 300 に化けて通る）。
  const dims = execFileSync('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', TARGET], { encoding: 'utf8' });
  const w = Number((dims.match(/pixelWidth:\s*(\d+)/) || [])[1]);
  const h = Number((dims.match(/pixelHeight:\s*(\d+)/) || [])[1]);
  console.log('wrote', TARGET, '(v' + version + ')');
  console.log('pixelWidth: ' + w + ' | pixelHeight: ' + h);
  if (w !== SIZE || h !== SIZE) {
    console.error('期待サイズ ' + SIZE + 'x' + SIZE + ' になりませんでした（実測 ' + w + 'x' + h + '）');
    process.exit(1);
  }
}

main();
