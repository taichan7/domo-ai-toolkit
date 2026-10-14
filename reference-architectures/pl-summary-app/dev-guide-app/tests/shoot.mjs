/**
 * ローカル・レイアウト検証ハーネス（Chrome headless 実描画スクリーンショット）。
 *
 * 開発ガイドは純静的（データ取得なし）なので、index.html を file:// で直接描画するだけでよい。
 * jsdom は CSS レイアウトを評価しないため、実ブラウザで描画して PNG を出力し、
 * PC / タブレット / スマホ幅で崩れが無いか目視する（デプロイ前の必須関門）。
 *
 * 使い方:
 *   node pl-summary-app/dev-guide-app/tests/shoot.mjs
 *   node .../shoot.mjs --widths 1680,1024,390 --height 5600
 *   出力先: OSの一時フォルダ（os.tmpdir()）配下の devguide-shots/doc-<width>.png（--out で変更可・実行時に実パスを表示）
 *
 * 注意（Chrome headless の最小ウィンドウ幅 500px クランプ・macOS）:
 *   500px 未満の幅は device-scale-factor をかけて実 CSS ビューポートを要求幅に一致させる
 *   （headless の最小幅クランプを補正する実証済みの方式）。
 */
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const INDEX = path.join(ROOT, 'index.html');

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
const CHROME = resolveChrome();
const MIN_WIN = 520; // headless(macOS) の最小ウィンドウ幅クランプ(実測500)を上回る安全側の基準幅

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function main() {
  if (!CHROME) { console.error('Chrome が見つかりません。Google Chrome を入れるか、環境変数 CHROME_PATH に chrome(.exe) の場所を設定してください。'); process.exit(2); }
  if (!fs.existsSync(INDEX)) { console.error('index.html が見つかりません:', INDEX); process.exit(2); }
  const widths = arg('--widths', '1680,1024,390').split(',').map(function (w) { return parseInt(w, 10); });
  // headless の --window-size は固定窓で、全スクロールは撮らない。この文書は非常に縦長（1680px 幅でも
  // 2 万 px 超）で、Chrome の 1 枚スクショ上限（約 16384px）を超えるため、どの固定高でも下端は切れる。
  // つまり shoot.mjs は「上から一定量を撮る目視スモーク」であり、全文の構造検査は高さ非依存の
  // tests/check.mjs が担う（参照整合・版の単一ソース）。--height で撮る量を変えられる。
  const CHROME_MAX = 16000; // Chrome の 1 枚スクショ実用上限（~16384）を少し下回る安全値
  const height = parseInt(arg('--height', '12000'), 10);
  const out = arg('--out', path.join(os.tmpdir(), 'devguide-shots'));
  // Linux の CI / コンテナ / root では headless Chrome がサンドボックスで起動できないことが多い。
  const extra = process.platform === 'darwin' ? [] : ['--no-sandbox'];
  fs.mkdirSync(out, { recursive: true });
  console.log('出力先:', out);

  const failures = [];
  widths.forEach(function (width) {
    // 幅 < MIN_WIN は headless の最小窓幅クランプ（macOS 実測 500）に当たるため、device-scale-factor で
    // 実 CSS ビューポートを要求幅へ一致させる。この補正は全プラットフォームへ一律に適用する。
    const narrow = width < MIN_WIN;
    const dpr = narrow ? (MIN_WIN / width) : 1;
    const winW = narrow ? MIN_WIN : width;
    // 狭幅は dpr 倍で縦が伸びるため、Chrome の 1 枚上限でクランプする（超えると撮影自体が失敗しうる）。
    const winH = Math.min(CHROME_MAX, Math.round(height * dpr));
    const target = path.join(out, 'doc-' + width + '.png');
    try {
      execFileSync(CHROME, [
        '--headless=new', '--disable-gpu', '--hide-scrollbars',
      ].concat(extra).concat([
        '--force-device-scale-factor=' + dpr,
        '--window-size=' + winW + ',' + winH,
        '--virtual-time-budget=4000',
        '--screenshot=' + target,
        'file://' + INDEX,
      ]), { stdio: ['ignore', 'ignore', 'inherit'], timeout: 60000 });
      if (!fs.existsSync(target) || fs.statSync(target).size < 2000) {
        throw new Error('PNG が生成されない／極小（空レンダの疑い）');
      }
      console.log('wrote', target, '(css viewport ' + width + 'x' + height + ')');
    } catch (e) {
      // 1 幅が落ちても残りは撮り、最後にまとめて失敗を知らせる（部分成功を成功と誤認しない）。
      console.error('FAILED width=' + width + ': ' + (e && e.message ? e.message : e));
      failures.push(width);
    }
  });
  if (failures.length) { console.error('撮影に失敗した幅: ' + failures.join(', ')); process.exit(1); }
}

main();
