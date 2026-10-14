/**
 * 決定的な静的 DOM／版プローブ（Chrome 不要・CI 安全・外部依存なし）。
 *
 * なぜ: この開発ガイドは縦スクロール 1 枚の静的文書。目視スクショだけでは、空レンダ・壊れた
 * アンカー・スプライト欠落・版ドリフトを検知できない。本スクリプトはブラウザを使わず index.html /
 * thumbnail.html / manifest.json を読み、参照の自己整合（<use>↔<symbol>・data-copy↔id・href#↔id・
 * aria-labelledby↔id）と版の単一ソースを機械チェックする。デプロイ前の決定的な関門。
 *
 *   node inventory-management-app/dev-guide-app/tests/check.mjs
 *   失敗時 exit 1（不整合を列挙）／成功時は検査件数のサマリを出す。
 */
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const INDEX = path.join(ROOT, 'index.html');
const MANIFEST = path.join(ROOT, 'manifest.json');
const THUMB = path.join(HERE, 'thumbnail.html');

const html = fs.readFileSync(INDEX, 'utf8');
const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
const thumb = fs.existsSync(THUMB) ? fs.readFileSync(THUMB, 'utf8') : '';

const errors = [];
function uniq(a) { return Array.from(new Set(a)); }
function matchAll(re, s) { const out = []; let m; while ((m = re.exec(s))) out.push(m[1]); return out; }

// 1) スプライト: <use href="#X"> の参照先 <symbol id="X"> が存在するか。
const symbolIds = new Set(matchAll(/<symbol\s+id="([^"]+)"/g, html));
const useRefs = uniq(matchAll(/<use\s+href="#([^"]+)"/g, html));
useRefs.forEach(function (id) { if (!symbolIds.has(id)) errors.push('スプライト欠落: <use href="#' + id + '"> に対応する <symbol> が無い'); });

// 2) 全 id 集合（コピー対象・アンカー着地・labelledby の検証に使う）。
const ids = new Set(matchAll(/\sid="([^"]+)"/g, html));

// 3) コピー: [data-copy="X"] の X が id として存在するか。
const copyTargets = uniq(matchAll(/data-copy="([^"]+)"/g, html));
copyTargets.forEach(function (id) { if (!ids.has(id)) errors.push('コピー対象欠落: data-copy="' + id + '" に対応する id が無い'); });

// 4) 内部アンカー: href="#X" の着地先 id が存在するか（目次が全節へ着地するか）。
const anchors = uniq(matchAll(/href="#([^"]+)"/g, html));
anchors.forEach(function (id) { if (!ids.has(id)) errors.push('アンカー切れ: href="#' + id + '" に対応する id が無い'); });

// 5) aria-labelledby="X" の参照先 id が存在するか。
const labelledby = uniq(matchAll(/aria-labelledby="([^"]+)"/g, html));
labelledby.forEach(function (ref) { ref.split(/\s+/).forEach(function (one) { if (one && !ids.has(one)) errors.push('aria-labelledby 切れ: "' + one + '" に対応する id が無い'); }); });

// 6) スキップリンク #doc の着地先に tabindex="-1" があるか（フォーカス移動を確実にする）。
if (/href="#doc"/.test(html) && !/id="doc"[^>]*tabindex="-1"/.test(html)) {
  errors.push('スキップリンク: #doc の着地先 <main id="doc"> に tabindex="-1" が無い');
}

// 7) 版の単一ソース: manifest.version が index（colophon＋footer の 2 箇所）と thumbnail に出るか。
const vLit = 'v' + manifest.version;
const vCount = html.split(vLit).length - 1;
if (vCount < 2) errors.push('版表記不足: index.html に ' + vLit + ' が ' + vCount + ' 箇所（colophon と footer の 2 箇所を想定）');
if (thumb && thumb.indexOf(vLit) < 0) errors.push('版不一致: thumbnail.html に ' + vLit + ' が無い');

// 8) 空レンダの軽い代理: 主要ランドマークと最初/サンドボックス/最後の節 id が在ること。
['doc', 's1', 's7', 's10'].forEach(function (id) { if (!ids.has(id)) errors.push('必須 id 欠落: #' + id); });

if (errors.length) {
  console.error('✗ check.mjs: ' + errors.length + ' 件の不整合');
  errors.forEach(function (e) { console.error('  - ' + e); });
  process.exit(1);
}
console.log('✓ check.mjs OK  symbols=' + symbolIds.size + ' use=' + useRefs.length +
  ' data-copy=' + copyTargets.length + ' anchors=' + anchors.length +
  ' labelledby=' + labelledby.length + ' version=' + vLit);
