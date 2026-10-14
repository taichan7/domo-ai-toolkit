const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../pro-code/qr-scanner.js'), 'utf8');

function element(overrides = {}) {
  const listeners = {};
  return {
    addEventListener(type, listener) { listeners[type] = listener; },
    dispatch(type) { if (listeners[type]) listeners[type](); },
    click() {},
    setAttribute(name, value) { this[name] = value; },
    pause() {},
    ...overrides
  };
}

function scannerEnvironment({nativeDetect, softwareResult, getUserMedia, createImageBitmap} = {}) {
  const context2d = {
    drawImage() {},
    getImageData() {
      return {data: new Uint8ClampedArray(16), width: 2, height: 2};
    }
  };
  const window = {
    isSecureContext: true,
    requestAnimationFrame() { return 1; },
    cancelAnimationFrame() {},
    jsQR: softwareResult === undefined ? undefined : () => softwareResult,
  };
  // 静止画（写真選択）デコード経路のテスト用に、任意で createImageBitmap を注入できるようにする。
  if (createImageBitmap) window.createImageBitmap = createImageBitmap;
  if (nativeDetect) {
    window.BarcodeDetector = class BarcodeDetector {
      static async getSupportedFormats() { return ['qr_code']; }
      async detect(value) { return nativeDetect(value); }
    };
  }
  const navigator = {mediaDevices: getUserMedia ? {getUserMedia} : undefined};
  vm.runInNewContext(source, {
    window, navigator, console, Uint8ClampedArray,
    performance: {now: () => 0},
    HTMLMediaElement: {HAVE_CURRENT_DATA: 2},
    URL, Image: class Image {}
  });
  const scanner = new window.InventoryQrScanner({
    dialog: element({
      open: true,
      returnValue: '',
      classList: {toggle() {}},
      showModal() { this.open = true; },
      close(value) { this.returnValue = value; this.open = false; }
    }),
    video: element({webkitExitFullscreen() { this.exitCalls = (this.exitCalls || 0) + 1; }}),
    message: element({textContent: ''}),
    manualInput: element({value: ''}),
    manualButton: element(),
    imageInput: element({value: '', files: []}),
    imageButton: element({disabled: false}),
    captureInput: element({value: '', files: []}),
    captureButton: element({hidden: true}),
    restartButton: element({hidden: true}),
    hint: element({textContent: ''}),
    canvas: element({width: 0, height: 0, getContext: () => context2d}),
    title: element({textContent: ''})
  });
  return scanner;
}

const videoFrame = {videoWidth: 640, videoHeight: 480};

test('標準検出器が未検出でも同じフレームをjsQRへフォールバックする', async () => {
  const scanner = scannerEnvironment({nativeDetect: async () => [], softwareResult: {data: 'LOC:LOC-01'}});
  await scanner.configureDecoder();

  assert.equal(scanner.decoderMode, 'native+software');
  assert.equal(await scanner.decodeSource(videoFrame, 720), 'LOC:LOC-01');
});

test('標準検出器が例外を返す埋込みブラウザでもjsQRを継続利用する', async () => {
  const scanner = scannerEnvironment({nativeDetect: async () => { throw new Error('unsupported source'); }, softwareResult: {data: 'ITEM:ITEM-001'}});
  await scanner.configureDecoder();

  assert.equal(await scanner.decodeSource(videoFrame, 720), 'ITEM:ITEM-001');
  assert.equal(scanner.decoderMode, 'software');
});

test('アプリ用の種別付きQRだけを解釈し、無関係なQRは読取済みとして拒否する', () => {
  const scanner = scannerEnvironment();

  assert.equal(scanner.parse('loc:loc-01').code, 'LOC-01');
  assert.equal(scanner.parse(' item:item-001 ').qr_type, 'item');
  assert.throws(() => scanner.parse('https://postcard.example/'), /QRコードは読み取れました/);
  assert.throws(() => scanner.parse('LOC-01'), /このアプリ用ではありません/);
});

test('閉じた後に完了した古いカメラ要求はストリームを即時停止する', async () => {
  let releaseCamera;
  let stopped = 0;
  const camera = new Promise((resolve) => { releaseCamera = resolve; });
  const scanner = scannerEnvironment({getUserMedia: () => camera});
  scanner.sessionId = 1;
  scanner.resolve = () => {};

  const starting = scanner.startCamera(1);
  scanner.sessionId = 2;
  scanner.dialog.open = false;
  releaseCamera({getTracks: () => [{stop: () => { stopped += 1; }}]});
  await starting;

  assert.equal(stopped, 1);
  assert.equal(scanner.stream, null);
});

test('STEPと異なるQRはモーダルを閉じずに読み直しを案内する', () => {
  const scanner = scannerEnvironment();
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.expectedType = 'location';

  assert.equal(scanner.acceptDetectedValue('ITEM:ITEM-001', 1), false);
  assert.match(scanner.message.textContent, /現在はロケーション選択/);
  assert.equal(scanner.dialog.open, true);
});

test('success以外のdialog closeはスキャン待機を必ずキャンセルする', () => {
  const scanner = scannerEnvironment();
  let rejected = null;
  scanner.resolve = () => {};
  scanner.reject = (error) => { rejected = error; };
  scanner.dialog.returnValue = '';

  scanner.dialog.dispatch('close');

  assert.equal(rejected.message, 'SCAN_CANCELLED');
  assert.equal(scanner.resolve, null);
});

test('ライブスキャンを全端末で既定にし、開くとライブ映像を起動する', () => {
  let getUserMediaCalls = 0;
  const scanner = scannerEnvironment({
    // 起動の有無だけ確認し、await先は未解決のまま保持する（play()まで進めない）。
    getUserMedia: () => { getUserMediaCalls += 1; return new Promise(() => {}); }
  });

  const pending = scanner.open('location');
  pending.catch(() => {}); // 読み取り完了まで未解決のまま保持されるためハンドラだけ付ける

  // iPhone判定に依らずライブ映像を既定にする（撮影モードは控えとして隠したまま）。
  assert.equal(getUserMediaCalls, 1);
  assert.equal(scanner.captureMode, false);
  assert.equal(scanner.captureButton.hidden, true);
  assert.equal(scanner.restartButton.hidden, true);
  assert.equal(scanner.inFullscreen, false);
  assert.match(scanner.message.textContent, /カメラを起動しています/);
});

test('ライブ起動時はiOSインライン再生のためplaysInline/mutedをプロパティで確定する', async () => {
  // 属性版playsinlineを無視するWKWebViewビルドがあるため、srcObject代入前にIDLプロパティで確定する。
  const scanner = scannerEnvironment({
    nativeDetect: async () => [],                 // BarcodeDetectorを定義しdecoderModeを確定させる
    softwareResult: {data: 'LOC:LOC-01'},
    getUserMedia: async () => ({getTracks: () => [{stop() {}}]})
  });
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.video.play = async () => {};

  await scanner.startCamera(1);

  assert.equal(scanner.video.playsInline, true);
  assert.equal(scanner.video.muted, true);
  assert.equal(scanner.video.defaultMuted, true);
  assert.equal(scanner.video.srcObject !== undefined, true);
});

test('ライブ映像が全画面化しても撮影へ切り替えず読み取りを継続する', () => {
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};

  scanner.handleEnterFullscreen();

  // 全画面でも映像フレームは取得できるため、カメラを止めず撮影導線にも切り替えない。
  assert.equal(scanner.inFullscreen, true);
  assert.equal(scanner.captureMode, false);
  assert.equal(scanner.captureButton.hidden, true);
});

test('利用者が読み取り前に全画面を閉じたらライブ再開の導線を出す', () => {
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};
  scanner.dialog.open = true;
  scanner.inFullscreen = true;

  scanner.handleFullscreenDismissed();

  assert.equal(scanner.inFullscreen, false);
  assert.equal(scanner.restartButton.hidden, false);
  assert.equal(scanner.captureMode, false);
  assert.match(scanner.message.textContent, /ライブ映像を閉じました/);
});

test('インライン再生が続く端末では全画面end後もフォールバックを出さず走査を続ける', () => {
  // v2.4.29でインライン再生に対応後、全画面/インラインの遷移でwebkitendfullscreenが発火しても、
  // ライブ映像が生きている端末では［ライブ映像を再開］ボタンを動作中の映像に重ねてはならない。
  const scanner = scannerEnvironment({nativeDetect: async () => [], softwareResult: {data: 'LOC:LOC-01'}});
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.dialog.open = true;
  scanner.decoderMode = 'software';
  scanner.stream = {getVideoTracks: () => [{readyState: 'live'}]};
  scanner.video.paused = false;
  scanner.restartButton.hidden = true;
  scanner.inFullscreen = true;

  scanner.handleFullscreenDismissed();

  assert.equal(scanner.inFullscreen, false);
  assert.equal(scanner.restartButton.hidden, true);              // ライブ再開ボタンは出さない
  assert.match(scanner.message.textContent, /枠内にQRコードを合わせて/); // 走査メッセージへ戻す
  assert.notEqual(scanner.stream, null);                          // 生きているカメラは止めない
});

test('全画面表示が続く最中のendイベントでもライブ読み取りを継続する', () => {
  // 一部の端末は全画面表示のまま webkitendfullscreen を発火させる。webkitDisplayingFullscreen が真なら
  // まだ全画面中とみなし、カメラを止めず走査を続ける。
  const scanner = scannerEnvironment();
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.dialog.open = true;
  scanner.decoderMode = 'software';
  scanner.stream = {getVideoTracks: () => [{readyState: 'live'}]};
  scanner.video.webkitDisplayingFullscreen = true;
  scanner.restartButton.hidden = true;

  scanner.handleFullscreenDismissed();

  assert.equal(scanner.restartButton.hidden, true);
  assert.notEqual(scanner.stream, null);
});

test('読み取り成功時は全画面を抜けてこの画面へ自動で戻る', () => {
  const scanner = scannerEnvironment();
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.expectedType = 'location';
  scanner.dialog.open = true;

  scanner.complete('LOC:LOC-01', 1);

  assert.equal(scanner.video.exitCalls, 1);
  assert.equal(scanner.dialog.returnValue, 'success');
  assert.equal(scanner.dialog.open, false);
});

test('ライブ全画面中はバックグラウンド化で中断しない', () => {
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};
  scanner.inFullscreen = true;
  const before = scanner.sessionId;

  scanner.suspendForBackground();

  // 全画面はホスト側の一時的なバックグラウンド扱いになり得るが、読み取りは継続させる。
  assert.equal(scanner.sessionId, before);
});

test('ライブを開始できない端末でだけ控えの端末カメラ撮影ボタンを露出する', async () => {
  // getUserMediaを持たない端末ではライブを開始できないため、controlの撮影ボタンを表に出す。
  const scanner = scannerEnvironment();
  scanner.sessionId = 1;
  scanner.resolve = () => {};

  await scanner.startCamera(1);

  assert.equal(scanner.captureMode, true);
  assert.equal(scanner.captureButton.hidden, false);
  assert.match(scanner.message.textContent, /カメラで撮影/);
});

test('端末カメラ撮影中はバックグラウンド化で中断しない', () => {
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};
  scanner.captureMode = true;
  const before = scanner.sessionId;

  scanner.suspendForBackground();

  // 撮影のために必ずバックグラウンド化するため、ここでセッションを進めない
  // （進めると撮影から戻ったときに解析結果が捨てられる）。
  assert.equal(scanner.sessionId, before);
});

test('通常のライブ中にバックグラウンド化したらカメラを止めてライブ再開の導線を出す', () => {
  // 撮影中でも全画面中でもない素のライブ走査中に一時停止された場合は、復帰時に自動で
  // カメラが戻らないため［ライブ映像を再開］を必ず出す。これが無いと写真・コード入力しか
  // 手が無いように見えてライブ読み取りへ戻れない退行になる。
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};
  scanner.stream = {getTracks: () => []};
  scanner.captureMode = false;
  scanner.inFullscreen = false;
  const before = scanner.sessionId;

  scanner.suspendForBackground();

  assert.equal(scanner.sessionId, before + 1);        // 古い走査を無効化するためセッションを進める
  assert.equal(scanner.stream, null);                 // カメラは停止する
  assert.equal(scanner.restartButton.hidden, false);  // ［ライブ映像を再開］を露出する
  assert.match(scanner.message.textContent, /ライブ映像を再開/);
});

test('走査中にデコーダを失ったら黙って止めず撮影・写真・コード入力の導線へ切り替える', async () => {
  // ネイティブBarcodeDetectorが例外で無効化され、jsQRも無い端末では走査の途中でdecoderModeが
  // 空になる。ここで黙ってループを止めると利用者は固まった映像の前に取り残されるため、
  // カメラを止めて撮影ボタン・ライブ再開・フォールバック文言を明示的に出す。
  const scanner = scannerEnvironment();
  scanner.resolve = () => {};
  scanner.sessionId = 1;
  scanner.stream = {getTracks: () => []};
  scanner.decoderMode = '';  // 走査中にデコーダを喪失した状態を再現

  await scanner.scanFrame(1);

  assert.equal(scanner.stream, null);                 // カメラを停止
  assert.equal(scanner.captureMode, true);            // 端末カメラ撮影を露出
  assert.equal(scanner.captureButton.hidden, false);
  assert.equal(scanner.restartButton.hidden, false);  // ライブ再開も出す
  assert.match(scanner.message.textContent, /写真から選ぶ/);
});

test('画像デコードが不成立でもライブ再開の導線を必ず出す（PC Webのデッドエンド防止）', async () => {
  // 写真選択でカメラを止めた後、解析不可（デコーダ無し）でも［ライブ映像を再開］を出さないと、
  // visibilitychange の発火しない PC Web のファイル選択ではライブ読み取りへ戻れない手詰まりになる。
  const scanner = scannerEnvironment();  // デコーダ無し→QR_DECODER_UNAVAILABLE
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.expectedType = 'location';
  scanner.dialog.open = true;
  scanner.imageInput.files = [{type: 'image/png'}];
  scanner.restartButton.hidden = true;

  await scanner.readImage(scanner.imageInput);

  assert.equal(scanner.restartButton.hidden, false);  // ［ライブ映像を再開］を露出
  assert.equal(scanner.stream, null);                 // カメラは停止済み
  assert.match(scanner.message.textContent, /QR解析を利用できません|コード入力/);
});

test('画像から種別違いのQRを読んでもライブ再開の導線を出しモーダルは閉じない', async () => {
  // 品目QR画像をロケーション選択中に選ぶと acceptDetectedValue は false（throw しない）で
  // finally を通る。ここでも再開導線を出さないとライブへ戻れないため、確実に露出する。
  const scanner = scannerEnvironment({
    nativeDetect: async () => [{rawValue: 'ITEM:ITEM-001'}],       // 画像から品目QRを検出
    createImageBitmap: async () => ({width: 10, height: 10, close() {}})
  });
  scanner.sessionId = 1;
  scanner.resolve = () => {};
  scanner.expectedType = 'location';
  scanner.dialog.open = true;
  scanner.imageInput.files = [{type: 'image/png'}];
  scanner.restartButton.hidden = true;

  await scanner.readImage(scanner.imageInput);

  assert.equal(scanner.dialog.open, true);            // 種別違いはモーダルを閉じない
  assert.equal(scanner.restartButton.hidden, false);  // ライブ再開の導線を露出
  assert.match(scanner.message.textContent, /品目QRを読み取りました/);
});

test('フォールバックは共通メッセージの文言を更新する', () => {
  const scanner = scannerEnvironment();

  scanner.showFallbackMessage('fallback');
  assert.equal(scanner.message.textContent, 'fallback');
});
