/**
 * qr-generator.js — 自己完結型のQRコード生成器（バイトモード / 誤り訂正レベルM）。
 *
 * なぜ内製するのか:
 *   配布先に追加依存を持ち込まないよう、外部QRライブラリに頼らず純粋JSで生成する。読み取り側の
 *   同梱 jsQR デコーダと揃え、encode→jsQR decode の往復テストで正しさを機械的に検証できる。
 *
 * 対応範囲:
 *   バイトモード・ECレベルM・バージョン1〜3（最大 42 バイト）。QR形式サンプル
 *   （例: "LOC:LOC-01" / "ITEM:ITEM-001"）の掲示が目的なので、単純さと正しさを優先し
 *   数字/英数字モードや大容量バージョンは持たない。長い入力は例外にして黙って壊さない。
 *
 * 公開API（window.InventoryQR）:
 *   encode(text)        -> {version, size, modules}  … modules は boolean の2次元配列
 *   toSvg(text, opts)   -> SVG文字列（PC掲示用・quiet zone付き）
 *
 * アルゴリズムは標準仕様（ISO/IEC 18004）に忠実な最小実装（Reed-Solomon・8マスク評価・BCH）。
 */
(function (global) {
  'use strict';

  // --- GF(256) 演算テーブル（原始多項式 0x11d, 原始元 2）------------------------
  // Reed-Solomon の乗算を log/antilog で O(1) 化するための事前計算。
  var EXP = new Array(256);
  var LOG = new Array(256);
  (function initGaloisField() {
    var x = 1;
    for (var i = 0; i < 255; i++) {
      EXP[i] = x;
      LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d; // 8ビットを超えたら原始多項式で畳み込む
    }
    EXP[255] = EXP[0]; // 巡回させて添字計算を安全にする
  })();

  /** GF(256) の乗算。0 を含む積は 0。 */
  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return EXP[(LOG[a] + LOG[b]) % 255];
  }

  // --- バージョン別パラメータ（ECレベルM・単一ブロック）------------------------
  // dataCodewords: データ語数, ecCodewords: 誤り訂正語数。合計が全コードワード数。
  // バージョン1〜3はMレベルだと全て単一ブロック構成なので、ブロック分割・インターリーブは不要。
  // v4以降は複数ブロックのインターリーブが必須になるため扱わない（pickVersion が v3 の42バイト超を例外化）。
  var VERSIONS = {
    1: {dataCodewords: 16, ecCodewords: 10, align: []},
    2: {dataCodewords: 28, ecCodewords: 16, align: [6, 18]},
    3: {dataCodewords: 44, ecCodewords: 26, align: [6, 22]}
  };
  var MAX_VERSION = 3;

  /** 入力バイト数を収容できる最小バージョンを選ぶ。収まらなければ例外。 */
  function pickVersion(byteLength) {
    for (var v = 1; v <= MAX_VERSION; v++) {
      // モード指標4bit + 文字数指標8bit(v1-9) + データ本体。
      var availableBits = VERSIONS[v].dataCodewords * 8 - 4 - 8;
      if (byteLength * 8 <= availableBits) return v;
    }
    throw new Error('QRペイロードが長すぎます（最大' + (VERSIONS[MAX_VERSION].dataCodewords - 2) + 'バイト）: ' + byteLength);
  }

  /** 文字列をUTF-8バイト列へ。QR値は基本ASCIIだが、日本語ロケーション名も安全に扱う。 */
  function toUtf8Bytes(text) {
    var out = [];
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code < 0x80) {
        out.push(code);
      } else if (code < 0x800) {
        out.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      } else if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
        // サロゲートペア（絵文字など）を4バイトへ結合する。
        var hi = code;
        var lo = text.charCodeAt(++i);
        var cp = 0x10000 + ((hi - 0xd800) << 10) + (lo - 0xdc00);
        out.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3f), 0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
      } else {
        out.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      }
    }
    return out;
  }

  // --- Reed-Solomon 誤り訂正 --------------------------------------------------
  /** 次数 degree の生成多項式。係数 g[0] が最高次。 */
  function rsGeneratorPoly(degree) {
    var g = [1];
    for (var i = 0; i < degree; i++) {
      var next = new Array(g.length + 1);
      for (var k = 0; k < next.length; k++) next[k] = 0;
      for (var j = 0; j < g.length; j++) {
        next[j] ^= g[j]; // g[j]·x
        next[j + 1] ^= gfMul(g[j], EXP[i]); // g[j]·α^i
      }
      g = next;
    }
    return g;
  }

  /** データ語列に対する ecLen 個の誤り訂正語を計算する（多項式除算の剰余）。 */
  function rsEncode(data, ecLen) {
    var gen = rsGeneratorPoly(ecLen);
    var res = data.slice();
    for (var p = 0; p < ecLen; p++) res.push(0);
    for (var i = 0; i < data.length; i++) {
      var coef = res[i];
      if (coef !== 0) {
        for (var j = 0; j < gen.length; j++) res[i + j] ^= gfMul(gen[j], coef);
      }
    }
    return res.slice(data.length);
  }

  // --- データ符号化（バイトモード）--------------------------------------------
  /** ペイロードをコードワード列（データ語 + 誤り訂正語）へ変換する。 */
  function buildCodewords(bytes, version) {
    var params = VERSIONS[version];
    var bits = [];
    function pushBits(value, length) {
      for (var i = length - 1; i >= 0; i--) bits.push((value >> i) & 1);
    }
    pushBits(0x4, 4); // バイトモード指標 0100
    pushBits(bytes.length, 8); // 文字数指標（バージョン1-9は8bit）
    for (var b = 0; b < bytes.length; b++) pushBits(bytes[b], 8);

    var capacityBits = params.dataCodewords * 8;
    pushBits(0, Math.min(4, capacityBits - bits.length)); // 終端子（最大4bit）
    while (bits.length % 8 !== 0) bits.push(0); // バイト境界へ整列

    // 余りは規定のパッドバイト 0xEC/0x11 を交互に詰める。
    var padToggle = 0;
    while (bits.length < capacityBits) {
      pushBits(padToggle % 2 === 0 ? 0xec : 0x11, 8);
      padToggle++;
    }

    var dataCw = [];
    for (var i = 0; i < bits.length; i += 8) {
      var byte = 0;
      for (var k = 0; k < 8; k++) byte = (byte << 1) | bits[i + k];
      dataCw.push(byte);
    }
    return dataCw.concat(rsEncode(dataCw, params.ecCodewords));
  }

  // --- モジュール行列の組み立て -----------------------------------------------
  function createMatrix(version) {
    var size = version * 4 + 17;
    var modules = new Array(size);
    var reserved = new Array(size); // 機能パターン領域（マスク・データ配置の対象外）
    for (var r = 0; r < size; r++) {
      modules[r] = new Array(size);
      reserved[r] = new Array(size);
      for (var c = 0; c < size; c++) {
        modules[r][c] = false;
        reserved[r][c] = false;
      }
    }
    return {size: size, modules: modules, reserved: reserved};
  }

  function setFunction(grid, row, col, dark) {
    grid.modules[row][col] = dark;
    grid.reserved[row][col] = true;
  }

  function placeFinder(grid, topRow, leftCol) {
    // 7×7のファインダ本体 + 周囲1マスの分離帯（白）を機能領域として確保する。
    for (var dr = -1; dr <= 7; dr++) {
      for (var dc = -1; dc <= 7; dc++) {
        var r = topRow + dr;
        var c = leftCol + dc;
        if (r < 0 || r >= grid.size || c < 0 || c >= grid.size) continue;
        var inBorder = dr === 0 || dr === 6 || dc === 0 || dc === 6;
        var inCore = dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4;
        setFunction(grid, r, c, (dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6) && (inBorder || inCore));
      }
    }
  }

  function placeAlignment(grid, centers) {
    for (var i = 0; i < centers.length; i++) {
      for (var j = 0; j < centers.length; j++) {
        var cr = centers[i];
        var cc = centers[j];
        // ファインダと重なる3隅にはアライメントを置かない。
        if (grid.reserved[cr][cc]) continue;
        for (var dr = -2; dr <= 2; dr++) {
          for (var dc = -2; dc <= 2; dc++) {
            var ring = Math.max(Math.abs(dr), Math.abs(dc));
            setFunction(grid, cr + dr, cc + dc, ring !== 1); // 中心と外周が黒、その内側の輪が白
          }
        }
      }
    }
  }

  function placeTimingAndDark(grid) {
    for (var i = 8; i < grid.size - 8; i++) {
      var dark = i % 2 === 0;
      if (!grid.reserved[6][i]) setFunction(grid, 6, i, dark); // 横タイミング
      if (!grid.reserved[i][6]) setFunction(grid, i, 6, dark); // 縦タイミング
    }
    setFunction(grid, grid.size - 8, 8, true); // 常時黒モジュール
  }

  function reserveFormatAreas(grid) {
    // フォーマット情報が入る領域を先に確保しておき、データ配置が侵入しないようにする。
    var size = grid.size;
    for (var i = 0; i <= 8; i++) {
      if (i !== 6) {
        grid.reserved[8][i] = true; // 上部横
        grid.reserved[i][8] = true; // 左部縦
      }
    }
    for (var k = 0; k < 8; k++) grid.reserved[8][size - 1 - k] = true; // 右上横
    for (var m = 0; m < 7; m++) grid.reserved[size - 1 - m][8] = true; // 左下縦
  }

  /** ジグザグ走査でデータ・誤り訂正ビットを配置する。 */
  function placeCodewords(grid, codewords) {
    var size = grid.size;
    var bitIndex = 0;
    var totalBits = codewords.length * 8;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5; // 縦タイミング列はまたぐ
      for (var vert = 0; vert < size; vert++) {
        for (var j = 0; j < 2; j++) {
          var col = right - j;
          var upward = ((right + 1) & 2) === 0;
          var row = upward ? size - 1 - vert : vert;
          if (grid.reserved[row][col]) continue;
          var dark = false;
          if (bitIndex < totalBits) {
            var byte = codewords[bitIndex >> 3];
            dark = ((byte >> (7 - (bitIndex & 7))) & 1) === 1;
            bitIndex++;
          }
          grid.modules[row][col] = dark;
        }
      }
    }
  }

  // --- マスク処理 -------------------------------------------------------------
  function maskCondition(mask, row, col) {
    switch (mask) {
      case 0: return (row + col) % 2 === 0;
      case 1: return row % 2 === 0;
      case 2: return col % 3 === 0;
      case 3: return (row + col) % 3 === 0;
      case 4: return (Math.floor(row / 2) + Math.floor(col / 3)) % 2 === 0;
      case 5: return ((row * col) % 2) + ((row * col) % 3) === 0;
      case 6: return (((row * col) % 2) + ((row * col) % 3)) % 2 === 0;
      case 7: return (((row + col) % 2) + ((row * col) % 3)) % 2 === 0;
      default: throw new Error('未知のマスク: ' + mask);
    }
  }

  function applyMask(grid, mask) {
    for (var r = 0; r < grid.size; r++) {
      for (var c = 0; c < grid.size; c++) {
        if (!grid.reserved[r][c] && maskCondition(mask, r, c)) grid.modules[r][c] = !grid.modules[r][c];
      }
    }
  }

  /** マスク選定のためのペナルティ評価（標準の4規則）。小さいほど良い。 */
  function penaltyScore(grid) {
    var size = grid.size;
    var m = grid.modules;
    var score = 0;

    // 規則1: 同色5連以上（横・縦）。
    for (var pass = 0; pass < 2; pass++) {
      for (var a = 0; a < size; a++) {
        var run = 1;
        for (var b = 1; b < size; b++) {
          var cur = pass === 0 ? m[a][b] : m[b][a];
          var prev = pass === 0 ? m[a][b - 1] : m[b - 1][a];
          if (cur === prev) {
            run++;
            if (run === 5) score += 3;
            else if (run > 5) score += 1;
          } else {
            run = 1;
          }
        }
      }
    }

    // 規則2: 2×2の同色ブロック。
    for (var r = 0; r < size - 1; r++) {
      for (var c = 0; c < size - 1; c++) {
        var v = m[r][c];
        if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) score += 3;
      }
    }

    // 規則3: 1:1:3:1:1 のファインダ類似パターン（前後に4連白を伴う）。
    var patternA = [true, false, true, true, true, false, true, false, false, false, false];
    var patternB = [false, false, false, false, true, false, true, true, true, false, true];
    for (var d = 0; d < 2; d++) {
      for (var i = 0; i < size; i++) {
        for (var j = 0; j <= size - 11; j++) {
          var matchA = true;
          var matchB = true;
          for (var k = 0; k < 11; k++) {
            var cell = d === 0 ? m[i][j + k] : m[j + k][i];
            if (cell !== patternA[k]) matchA = false;
            if (cell !== patternB[k]) matchB = false;
          }
          if (matchA || matchB) score += 40;
        }
      }
    }

    // 規則4: 黒モジュール比率が50%から離れるほど加点。
    var dark = 0;
    for (var y = 0; y < size; y++) for (var x = 0; x < size; x++) if (m[y][x]) dark++;
    var percent = (dark * 100) / (size * size);
    var deviation = Math.floor(Math.abs(percent - 50) / 5);
    score += deviation * 10;

    return score;
  }

  // --- フォーマット情報（ECレベルM = 0b00）------------------------------------
  function formatBits(mask) {
    var data = (0x0 << 3) | mask; // 上位2bit=ECレベルM(00), 下位3bit=マスク番号
    var rem = data;
    for (var i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
    return ((data << 10) | rem) ^ 0x5412; // 15bitのマスク済みフォーマット列
  }

  function placeFormatInfo(grid, mask) {
    var bits = formatBits(mask);
    var size = grid.size;
    function bit(i) {
      return ((bits >> i) & 1) === 1;
    }
    // 1つ目の複製（左上ファインダ周り）。
    for (var i = 0; i <= 5; i++) grid.modules[i][8] = bit(i);
    grid.modules[7][8] = bit(6);
    grid.modules[8][8] = bit(7);
    grid.modules[8][7] = bit(8);
    for (var j = 9; j < 15; j++) grid.modules[8][14 - j] = bit(j);
    // 2つ目の複製（右上・左下ファインダ周り）。
    for (var k = 0; k < 8; k++) grid.modules[8][size - 1 - k] = bit(k);
    for (var n = 8; n < 15; n++) grid.modules[size - 15 + n][8] = bit(n);
    grid.modules[size - 8][8] = true; // 常時黒
  }

  // --- 公開関数 ---------------------------------------------------------------
  /** テキストを符号化し、{version, size, modules(boolean[][])} を返す。 */
  function encode(text) {
    if (typeof text !== 'string' || text.length === 0) throw new Error('QRテキストが空です');
    var bytes = toUtf8Bytes(text);
    var version = pickVersion(bytes.length);
    var codewords = buildCodewords(bytes, version);

    var grid = createMatrix(version);
    placeFinder(grid, 0, 0);
    placeFinder(grid, 0, grid.size - 7);
    placeFinder(grid, grid.size - 7, 0);
    placeAlignment(grid, VERSIONS[version].align);
    placeTimingAndDark(grid);
    reserveFormatAreas(grid);
    placeCodewords(grid, codewords);

    // 8マスクを試し、ペナルティ最小のマスクを採用する。採用マスクの番号自体は
    // 出力（modules）に既に焼き込まれ、デコード側は番号を必要としないため保持しない。
    var bestScore = Infinity;
    var bestModules = null;
    for (var mask = 0; mask < 8; mask++) {
      applyMask(grid, mask);
      placeFormatInfo(grid, mask);
      var score = penaltyScore(grid);
      if (score < bestScore) {
        bestScore = score;
        bestModules = grid.modules.map(function (row) {
          return row.slice();
        });
      }
      applyMask(grid, mask); // マスクは対合。同じマスクを再適用して元へ戻す。
    }

    return {version: version, size: grid.size, modules: bestModules};
  }

  /**
   * QRを走査可能なSVG文字列へ描画する。PC掲示用途を想定。
   * options: {moduleSize(px, 既定4), quietZone(モジュール数, 既定4), title(aria用)}
   */
  function toSvg(text, options) {
    var opts = options || {};
    var moduleSize = opts.moduleSize || 4;
    var quiet = opts.quietZone == null ? 4 : opts.quietZone;
    var result = encode(text);
    var modules = result.modules;
    var dimension = result.size + quiet * 2;
    var pixels = dimension * moduleSize;

    var rects = [];
    for (var r = 0; r < result.size; r++) {
      for (var c = 0; c < result.size; c++) {
        if (!modules[r][c]) continue;
        var x = (c + quiet) * moduleSize;
        var y = (r + quiet) * moduleSize;
        rects.push('<rect x="' + x + '" y="' + y + '" width="' + moduleSize + '" height="' + moduleSize + '"/>');
      }
    }
    var titleAttr = opts.title ? ' role="img" aria-label="' + String(opts.title).replace(/"/g, '&quot;') + '"' : ' aria-hidden="true"';
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + pixels + '" height="' + pixels + '" ' +
      'viewBox="0 0 ' + pixels + ' ' + pixels + '" shape-rendering="crispEdges"' + titleAttr + '>' +
      '<rect width="' + pixels + '" height="' + pixels + '" fill="#ffffff"/>' +
      '<g fill="#0f172a">' + rects.join('') + '</g></svg>'
    );
  }

  global.InventoryQR = {encode: encode, toSvg: toSvg};

  if (typeof module === 'object' && module.exports) module.exports = global.InventoryQR;
})(typeof self !== 'undefined' ? self : this);
