const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const QR = require('../pro-code/qr-generator.js');
const jsQR = require('../pro-code/vendor/jsQR.js');

/**
 * 生成したモジュール行列を、jsQR が読める RGBA バッファ（quiet zone 付き・整数倍拡大）へ
 * 展開する。生成→デコードの往復で「実際に読み取れるQR」であることを機械的に保証する。
 */
function renderToRgba(text, scale, quiet) {
  const {size, modules} = QR.encode(text);
  const dimension = (size + quiet * 2) * scale;
  const buffer = new Uint8ClampedArray(dimension * dimension * 4).fill(255);
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (!modules[r][c]) continue;
      for (let dy = 0; dy < scale; dy++) {
        for (let dx = 0; dx < scale; dx++) {
          const px = (((r + quiet) * scale + dy) * dimension + ((c + quiet) * scale + dx)) * 4;
          buffer[px] = 0;
          buffer[px + 1] = 0;
          buffer[px + 2] = 0;
          buffer[px + 3] = 255;
        }
      }
    }
  }
  return {buffer, dimension};
}

function decode(text) {
  const {buffer, dimension} = renderToRgba(text, 4, 4);
  const result = jsQR(buffer, dimension, dimension, {inversionAttempts: 'attemptBoth'});
  return result ? result.data : null;
}

test('サイドバーのテスト用QR（LOC / ITEM）は同梱jsQRで読み取れる', () => {
  // ユーザーがサイドバーに求めたテスト用ペイロードそのものが往復すること。
  assert.equal(decode('LOC:LOC-01'), 'LOC:LOC-01');
  assert.equal(decode('ITEM:ITEM-001'), 'ITEM:ITEM-001');
});

test('QR形式の代表パターンとバージョン境界を往復できる', () => {
  // バージョン1（〜14バイト）とバージョン2（〜26バイト）の両方を通す。
  const samples = ['LOC:LOC-99', 'ITEM:ITEM-12345', 'ITEM:ITEM-0001-LONG-CODE-XYZ'];
  for (const text of samples) assert.equal(decode(text), text);
});

test('日本語（マルチバイト）ロケーション名もUTF-8で往復できる', () => {
  assert.equal(decode('中央倉庫'), '中央倉庫');
});

test('encodeは最小バージョンを選び、行列は正方・boolean行列になる', () => {
  const short = QR.encode('LOC:LOC-01');
  assert.equal(short.version, 1);
  assert.equal(short.size, 21);
  assert.equal(short.modules.length, 21);
  assert.equal(short.modules[0].length, 21);
  assert.equal(typeof short.modules[0][0], 'boolean');

  const longer = QR.encode('ITEM:ITEM-12345');
  assert.equal(longer.version, 2);
  assert.equal(longer.size, 25);
});

test('空文字や長すぎる入力は黙って壊れず例外にする', () => {
  assert.throws(() => QR.encode(''), /空/);
  assert.throws(() => QR.encode('x'.repeat(200)), /長すぎ/);
});

test('v3の容量境界（42バイト）まで往復でき、超過入力は非対応v4を作らず例外にする', () => {
  // このアプリのQR値は数〜十数バイトだが、生成器の上限（v3=42バイト）付近も確実に読み取れること。
  // かつては非対応のv4を単一ブロックで組み立てて黙って読み取れないQRを吐く不具合があったため、
  // v3までに限定し、上限超えは黙って壊さず例外にする方針を回帰テストで固定する。
  const maxPayload = 'ITEM:' + 'X'.repeat(37); // 42バイト = v3データ容量の上限
  assert.equal(maxPayload.length, 42);
  const encoded = QR.encode(maxPayload);
  assert.equal(encoded.version, 3); // v4へ繰り上がらない
  assert.equal(decode(maxPayload), maxPayload);

  // 43バイト以上はv3に収まらない。非対応バージョンを黙って作らず例外にする。
  assert.throws(() => QR.encode('ITEM:' + 'X'.repeat(38)), /長すぎ/);
});

test('toSvgはquiet zone込みの正方SVGを返し、外部リソースに依存しない', () => {
  const svg = QR.toSvg('LOC:LOC-01', {moduleSize: 4, quietZone: 4, title: 'テストQR'});
  assert.match(svg, /^<svg /);
  assert.match(svg, /<\/svg>$/);
  // 21モジュール + 上下左右4モジュールのquiet zone = 29モジュール、×4px = 116px 四方。
  assert.match(svg, /width="116" height="116"/);
  assert.match(svg, /aria-label="テストQR"/);
  // 画像やスクリプトの外部参照を持たない（配布リファレンスとして自己完結）。
  assert.doesNotMatch(svg, /https?:\/\/(?!www\.w3\.org)/);
  assert.doesNotMatch(svg, /<image|<script/);
});

test('生成器はビルド不要のプレーンJSで、外部QRライブラリに依存しない', () => {
  const source = fs.readFileSync(path.join(__dirname, '../pro-code/qr-generator.js'), 'utf8');
  assert.doesNotMatch(source, /require\(|import\s|from\s+['"]/);
});
