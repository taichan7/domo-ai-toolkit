(function qrScannerModule(global) {
  'use strict';

  // QR デバイス層のチューニング値をここへ集約する（唯一の定義源）。解像度が高いほど小さな/遠い
  // QRを拾えるが負荷が増える、間隔が短いほど反応は速いが CPU が上がる、というトレードオフで決める。
  const CAMERA_IDEAL_WIDTH = 1280;   // ライブ映像の理想幅（px）。環境により実際の解像度は前後する。
  const CAMERA_IDEAL_HEIGHT = 720;   // ライブ映像の理想高（px）。
  const SCAN_THROTTLE_MS = 180;      // ライブ走査の最小間隔（ミリ秒）。CPU 負荷と反応速度の折衷。
  const LIVE_DECODE_MAX_DIMENSION = 720;   // ライブ映像をデコードする際の縮小上限（px）。
  const IMAGE_DECODE_MAX_DIMENSION = 1600; // 静止画（写真選択）をデコードする際の縮小上限（px）。

  class InventoryQrScanner {
    constructor(options) {
      this.dialog = options.dialog;
      this.video = options.video;
      this.message = options.message;
      this.manualInput = options.manualInput;
      this.manualButton = options.manualButton;
      this.imageInput = options.imageInput;
      this.imageButton = options.imageButton;
      this.captureInput = options.captureInput || null;
      this.captureButton = options.captureButton || null;
      this.restartButton = options.restartButton || null;
      this.hint = options.hint || null;
      // ライブスキャンを全端末の既定にする。iPhoneのDomo Mobile（WKWebView）はホストの
      // allowsInlineMediaPlaybackが無効でライブ映像を全画面化するが、全画面のまま読み取りを
      // 続け、成功時に全画面を抜けてこの画面へ自動で戻す。端末カメラ撮影（capture）・写真選択・
      // 手入力は、ライブで読み取れない場合の控えとして残す（captureMode=false が既定＝ライブ）。
      this.captureMode = false;
      this.inFullscreen = false;
      this.canvas = options.canvas;
      this.context = this.canvas.getContext('2d', {willReadFrequently: true});
      this.title = options.title;
      this.stream = null;
      this.detector = null;
      this.decoderMode = '';
      this.nativeDecoderEnabled = false;
      this.softwareDecoderEnabled = false;
      this.frameHandle = null;
      this.expectedType = null;
      this.resolve = null;
      this.reject = null;
      this.lastScanAt = 0;
      this.sessionId = 0;

      this.dialog.addEventListener('close', () => {
        this.sessionId += 1;
        this.stopCamera();
        if (this.dialog.returnValue !== 'success' && this.reject) this.reject(new Error('SCAN_CANCELLED'));
        this.clearPromise();
      });
      if (global.document && typeof global.document.addEventListener === 'function') {
        global.document.addEventListener('visibilitychange', () => {
          if (global.document.hidden) this.suspendForBackground();
        });
      }
      if (typeof global.addEventListener === 'function') {
        global.addEventListener('pagehide', () => this.suspendForBackground());
      }
      this.manualButton.addEventListener('click', () => this.acceptManual());
      this.manualInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          this.acceptManual();
        }
      });
      this.imageButton.addEventListener('click', () => this.imageInput.click());
      this.imageInput.addEventListener('change', () => this.readImage(this.imageInput));
      if (this.captureButton && this.captureInput) {
        this.captureButton.addEventListener('click', () => this.captureInput.click());
        this.captureInput.addEventListener('change', () => this.readImage(this.captureInput));
      }
      if (this.restartButton) {
        this.restartButton.addEventListener('click', () => this.restartLive());
      }
      // ホストWebView（iPhoneのDomo Mobile等）がライブ映像を全画面化しても読み取りは継続する。
      // 成功時はcomplete()で全画面を抜けてこの画面へ自動的に戻る。利用者が読み取り前に全画面を
      // 自分で閉じた場合はhandleFullscreenDismissed()でライブ再開の導線を出す。
      this.video.addEventListener('webkitbeginfullscreen', () => this.handleEnterFullscreen());
      this.video.addEventListener('webkitendfullscreen', () => this.handleFullscreenDismissed());
    }

    async open(expectedType) {
      if (this.resolve) {
        this.reject(new Error('SCAN_REPLACED'));
        this.clearPromise();
      }
      const sessionId = ++this.sessionId;
      this.stopCamera();
      this.expectedType = expectedType;
      this.title.textContent = expectedType === 'location' ? 'ロケーションQRを読み取る' : '品目QRを読み取る';
      this.manualInput.value = '';
      this.manualInput.placeholder = expectedType === 'location' ? 'LOC:LOC-01' : 'ITEM:ITEM-001';
      this.imageInput.value = '';
      if (this.captureInput) this.captureInput.value = '';
      this.imageButton.disabled = false;
      const promise = new Promise((resolve, reject) => {
        this.resolve = resolve;
        this.reject = reject;
      });
      this.dialog.returnValue = '';
      this.dialog.showModal();
      // 端末に依らずライブスキャンを既定にする。全画面化する端末でもそのまま読み取り、
      // 成功時に自動でこの画面へ戻る。
      this.inFullscreen = false;
      this.showRestart(false);
      this.setCaptureMode(false);
      this.message.textContent = 'カメラを起動しています';
      this.startCamera(sessionId);
      return promise;
    }

    setCaptureMode(on) {
      this.captureMode = Boolean(on);
      if (this.dialog.classList) this.dialog.classList.toggle('capture-mode', this.captureMode);
      if (this.captureButton) this.captureButton.hidden = !this.captureMode;
      if (this.hint) {
        this.hint.textContent = this.captureMode
          ? 'この端末ではライブ映像が全画面になるため、端末カメラで1枚撮影して読み取ります。うまくいかない場合は「写真から選ぶ」または下のコード入力をご利用ください。画像は端末内だけで解析します。'
          : 'ライブ映像にQRを合わせると自動で読み取り、この画面へ戻ります。スマホでは映像が全画面になる場合がありますが、そのまま読み取れます。読み取れないときは「写真から選ぶ」または下のコード入力をご利用ください。画像は端末内だけで解析します。';
      }
    }

    handleEnterFullscreen() {
      // 全画面化してもライブ読み取りを継続する（映像フレームは全画面でも取得できる）。
      // カメラを止めず走査ループをそのまま回し、成功時はcomplete()で全画面を抜ける。
      this.inFullscreen = true;
    }

    handleFullscreenDismissed() {
      // 全画面を抜けた。インライン再生を継続できる端末では映像も走査も続くのでフォールバック不要
      // （ライブ再開ボタンは出さない）。iOS が映像を一時停止した端末でだけカメラを止めて
      // ［ライブ映像を再開］の導線を出す。成功時・ダイアログ閉時（this.resolve が null）は何もしない。
      this.inFullscreen = false;
      if (!this.resolve || this.dialog.open === false) return;
      if (this.isLivePlayingInline()) {
        this.resumeInlineScan();
        return;
      }
      this.stopCamera();
      this.showRestart(true);
      this.showFallbackMessage('ライブ映像を閉じました。［ライブ映像を再開］でもう一度読み取るか、［写真から選ぶ］または下のコード入力をご利用ください。');
    }

    isLivePlayingInline() {
      // ホスト全画面を表示している最中に発火する端末があるため、その場合はインライン継続扱いにする。
      if (this.video && this.video.webkitDisplayingFullscreen) return true;
      const stream = this.stream;
      const trackLive = Boolean(stream && typeof stream.getVideoTracks === 'function'
        && stream.getVideoTracks().some((track) => track && track.readyState === 'live'));
      // カメラトラックが生きていて映像も再生中（一時停止していない）＝インライン再生が継続している。
      return Boolean(trackLive && this.video && this.video.paused === false && this.decoderMode);
    }

    resumeInlineScan() {
      // インライン再生が続いているので、ライブ再開ボタンを隠して走査メッセージへ戻す。走査ループが
      // 何らかの理由で止まっていた場合だけ再開する（動作中は二重ループを避けるため呼ばない）。
      this.showRestart(false);
      if (this.message && !this.captureMode) this.message.textContent = '枠内にQRコードを合わせてください';
      if (!this.frameHandle) this.scanFrame(this.sessionId);
    }

    showRestart(on) {
      if (this.restartButton) this.restartButton.hidden = !on;
    }

    restartLive() {
      const sessionId = ++this.sessionId;
      this.stopCamera();
      this.showRestart(false);
      this.setCaptureMode(false);
      this.message.textContent = 'カメラを起動しています';
      this.startCamera(sessionId);
    }

    exitFullscreen() {
      if (typeof this.video.webkitExitFullscreen === 'function') {
        try { this.video.webkitExitFullscreen(); } catch (error) { /* best effort */ }
      }
      this.inFullscreen = false;
    }

    isSessionActive(sessionId) {
      return sessionId === this.sessionId && this.dialog.open !== false && Boolean(this.resolve);
    }

    async startCamera(sessionId = this.sessionId) {
      if (!global.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (this.isSessionActive(sessionId)) {
          // ライブ映像を開始できない端末でだけ、控えの端末カメラ撮影ボタンを露出させる。
          if (this.captureButton) this.setCaptureMode(true);
          this.showFallbackMessage('この画面ではライブカメラを開始できません。［カメラで撮影］［写真から選ぶ］または下のコード入力をご利用ください。');
        }
        return;
      }

      let stream = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {facingMode: {ideal: 'environment'}, width: {ideal: CAMERA_IDEAL_WIDTH}, height: {ideal: CAMERA_IDEAL_HEIGHT}}
        });
        if (!this.isSessionActive(sessionId)) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        this.stream = stream;
        // iOSのWebView（Domo Mobile）でライブ映像がネイティブ全画面へ飛ばされるのを避けるため、
        // 属性だけでなくIDLプロパティ（playsInline / muted）も、srcObject代入の前に確定させる。
        // 一部のWKWebViewビルドは属性版のplaysinlineを無視し、プロパティ版のみを尊重する。
        this.video.setAttribute('playsinline', '');
        this.video.setAttribute('webkit-playsinline', '');
        this.video.playsInline = true;
        this.video.muted = true;
        this.video.defaultMuted = true;
        this.video.controls = false;
        this.video.srcObject = stream;
        await this.video.play();
        if (!this.isSessionActive(sessionId)) {
          this.stopCamera();
          return;
        }
        await this.configureDecoder(sessionId);
        if (!this.isSessionActive(sessionId)) {
          this.stopCamera();
          return;
        }
        if (!this.decoderMode) {
          this.stopCamera();
          this.showFallbackMessage('ライブ映像のQR解析を利用できません。［写真から選ぶ］または下のコード入力をご利用ください。');
          return;
        }
        this.showRestart(false);
        this.message.textContent = '枠内にQRコードを合わせてください';
        this.scanFrame(sessionId);
      } catch (error) {
        if (!this.isSessionActive(sessionId)) {
          if (stream) stream.getTracks().forEach((track) => track.stop());
          return;
        }
        this.stopCamera();
        // カメラ起動に失敗した端末でだけ、控えの端末カメラ撮影ボタンを露出させる。
        if (this.captureButton) this.setCaptureMode(true);
        const denied = error && (error.name === 'NotAllowedError' || error.name === 'SecurityError');
        this.showFallbackMessage(denied
          ? 'カメラが許可されていません。Domo／端末設定で許可するか、［カメラで撮影］［写真から選ぶ］を使用してください。'
          : 'ライブカメラを起動できません。［カメラで撮影］［写真から選ぶ］または下のコード入力で続行できます。');
      }
    }

    async configureDecoder(sessionId = null) {
      this.detector = null;
      this.decoderMode = '';
      this.nativeDecoderEnabled = false;
      this.softwareDecoderEnabled = typeof global.jsQR === 'function';
      if ('BarcodeDetector' in global) {
        try {
          const formats = typeof global.BarcodeDetector.getSupportedFormats === 'function'
            ? await global.BarcodeDetector.getSupportedFormats()
            : ['qr_code'];
          if (sessionId !== null && !this.isSessionActive(sessionId)) return;
          if (formats.includes('qr_code')) {
            this.detector = new global.BarcodeDetector({formats: ['qr_code']});
            this.nativeDecoderEnabled = true;
          }
        } catch (error) {
          this.detector = null;
        }
      }
      this.updateDecoderMode();
    }

    updateDecoderMode() {
      this.decoderMode = [
        this.nativeDecoderEnabled ? 'native' : '',
        this.softwareDecoderEnabled ? 'software' : ''
      ].filter(Boolean).join('+');
    }

    async scanFrame(sessionId = this.sessionId) {
      // セッションが差し替わった／カメラが止められた通常の後始末は黙って抜ける。
      if (!this.isSessionActive(sessionId) || !this.stream) return;
      // 走査の途中でネイティブ BarcodeDetector が例外により無効化され（decodeSource 参照）、
      // ソフトウェア(jsQR)も無い端末では decoderMode が空になる。ここで黙ってループを止めると
      // 利用者は固まった映像の前に取り残されるため、撮影／写真／コード入力の代替導線へ切り替える。
      if (!this.decoderMode) {
        this.stopCamera();
        this.setCaptureMode(true);
        this.showRestart(true);
        this.showFallbackMessage('この端末ではライブ読み取りを続けられませんでした。［カメラで撮影］［写真から選ぶ］または下のコード入力をご利用ください。');
        return;
      }
      const now = performance.now();
      if (now - this.lastScanAt > SCAN_THROTTLE_MS && this.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        this.lastScanAt = now;
        try {
          const rawValue = await this.decodeSource(this.video, LIVE_DECODE_MAX_DIMENSION);
          if (!this.isSessionActive(sessionId)) return;
          if (rawValue) {
            if (this.acceptDetectedValue(rawValue, sessionId)) return;
          }
        } catch (error) {
          this.message.textContent = '読み取りを再試行しています。動かさずに合わせてください。';
        }
      }
      if (this.isSessionActive(sessionId)) this.frameHandle = global.requestAnimationFrame(() => this.scanFrame(sessionId));
    }

    async readImage(input = this.imageInput) {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!String(file.type || '').startsWith('image/')) {
        this.showFallbackMessage('画像ファイルを選択してください。');
        input.value = '';
        return;
      }

      const sessionId = ++this.sessionId;
      this.stopCamera();
      this.imageButton.disabled = true;
      this.message.textContent = '画像からQRコードを解析しています';
      let loaded = null;
      try {
        await this.configureDecoder(sessionId);
        if (!this.isSessionActive(sessionId)) return;
        if (!this.decoderMode) throw new Error('QR_DECODER_UNAVAILABLE');
        loaded = await this.loadImage(file);
        if (!this.isSessionActive(sessionId)) return;
        const rawValue = await this.decodeSource(loaded.source, IMAGE_DECODE_MAX_DIMENSION);
        if (!this.isSessionActive(sessionId)) return;
        if (!rawValue) throw new Error('QR_NOT_FOUND');
        this.acceptDetectedValue(rawValue, sessionId);
      } catch (error) {
        if (!this.isSessionActive(sessionId)) return;
        this.showFallbackMessage(error.message === 'QR_DECODER_UNAVAILABLE'
          ? 'この端末では画像のQR解析を利用できません。下のコード入力を使用してください。'
          : '画像内にQRコードを見つけられませんでした。正面から大きく写して再度お試しください。');
      } finally {
        if (loaded && loaded.dispose) loaded.dispose();
        this.imageButton.disabled = false;
        input.value = '';
        // 画像デコードが不成立だと readImage は既に stopCamera() 済みなのにライブ再開導線が
        // 隠れたままで手詰まりになる（visibilitychange の無い PC Web のファイル選択で顕著）。ここで
        // 必ず再開導線を出す。成功時は complete() が resolve を null 化するので出さない（ちらつき回避）。
        if (this.isSessionActive(sessionId)) this.showRestart(true);
      }
    }

    async loadImage(file) {
      if (typeof global.createImageBitmap === 'function') {
        try {
          const bitmap = await global.createImageBitmap(file, {imageOrientation: 'from-image'});
          return {source: bitmap, dispose: () => bitmap.close()};
        } catch (error) {
          // Fall through to an HTMLImageElement for WebViews without createImageBitmap support.
        }
      }
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.decoding = 'async';
      image.src = url;
      try {
        if (typeof image.decode === 'function') await image.decode();
        else await new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = reject;
        });
        return {source: image, dispose: () => URL.revokeObjectURL(url)};
      } catch (error) {
        URL.revokeObjectURL(url);
        throw error;
      }
    }

    async decodeSource(source, maximumDimension) {
      if (this.nativeDecoderEnabled && this.detector) {
        try {
          const codes = await this.detector.detect(source);
          if (codes.length && codes[0].rawValue) return codes[0].rawValue;
        } catch (error) {
          // Some embedded browsers expose BarcodeDetector but cannot decode a live
          // HTMLVideoElement. Disable it for this session and continue with jsQR.
          this.nativeDecoderEnabled = false;
          this.detector = null;
          this.updateDecoderMode();
        }
      }
      if (!this.softwareDecoderEnabled || typeof global.jsQR !== 'function') return '';

      const sourceWidth = Number(source.videoWidth || source.naturalWidth || source.width || 0);
      const sourceHeight = Number(source.videoHeight || source.naturalHeight || source.height || 0);
      if (!sourceWidth || !sourceHeight) return '';
      const scale = Math.min(1, maximumDimension / Math.max(sourceWidth, sourceHeight));
      this.canvas.width = Math.max(1, Math.round(sourceWidth * scale));
      this.canvas.height = Math.max(1, Math.round(sourceHeight * scale));
      this.context.drawImage(source, 0, 0, this.canvas.width, this.canvas.height);
      const imageData = this.context.getImageData(0, 0, this.canvas.width, this.canvas.height);
      const result = global.jsQR(imageData.data, imageData.width, imageData.height, {inversionAttempts: 'attemptBoth'});
      return result && result.data ? result.data : '';
    }

    parse(rawValue) {
      const normalized = String(rawValue || '').normalize('NFKC').trim().toUpperCase();
      // このアプリが受け付けるQRの接頭辞（LOC:／ITEM:）とコード形式の唯一の定義源。
      // 設定ファイル等へ二重に持たず、判定・型変換はここに集約する。
      const match = /^(LOC|ITEM):([A-Z0-9_-]{1,64})$/.exec(normalized);
      if (match) {
        return {
          ok: true,
          qr_type: match[1] === 'LOC' ? 'location' : 'item',
          code: match[2],
          normalized
        };
      }

      const preview = normalized.replace(/[\r\n\t]+/g, ' ').slice(0, 80) || '空の値';
      throw new Error(`QRコードは読み取れましたが、このアプリ用ではありません（読取値: ${preview}）。LOC:<コード> または ITEM:<コード> を使用してください。`);
    }

    acceptDetectedValue(rawValue, sessionId = this.sessionId) {
      if (!this.isSessionActive(sessionId)) return false;
      let parsed;
      try {
        parsed = this.parse(rawValue);
      } catch (error) {
        this.showFallbackMessage(error.message);
        return false;
      }
      if (parsed.qr_type !== this.expectedType) {
        this.showFallbackMessage(this.expectedType === 'location'
          ? '品目QRを読み取りました。現在はロケーション選択です。ロケーションQRを枠内へ合わせてください。'
          : 'ロケーションQRを読み取りました。現在は品目選択です。品目QRを枠内へ合わせてください。');
        return false;
      }
      this.complete(rawValue, sessionId);
      return true;
    }

    acceptManual() {
      const value = this.manualInput.value.trim();
      if (!value) {
        this.manualInput.setCustomValidity('コードを入力してください。');
        this.manualInput.reportValidity();
        this.manualInput.setCustomValidity('');
        return;
      }
      this.acceptDetectedValue(value, this.sessionId);
    }

    complete(rawValue, sessionId = this.sessionId) {
      if (!this.isSessionActive(sessionId)) return;
      const resolver = this.resolve;
      this.resolve = null;
      this.reject = null;
      this.stopCamera();
      this.exitFullscreen();
      this.dialog.close('success');
      if (resolver) resolver({rawValue: String(rawValue).trim(), expectedType: this.expectedType});
    }

    showFallbackMessage(text) {
      this.message.textContent = text;
    }

    suspendForBackground() {
      if (this.dialog.open === false || !this.resolve) return;
      // 端末カメラ撮影中・ライブ全画面中はWebViewがバックグラウンド扱いになることがあるため
      // ここでは中断しない（撮影は戻り時のchangeで解析、全画面は読み取りを継続する）。
      if (this.captureMode || this.inFullscreen) return;
      this.sessionId += 1;
      this.stopCamera();
      // 復帰時に自動でカメラは戻らないため、［ライブ映像を再開］導線を必ず出す。
      // これが無いと、写真・コード入力しか手が無いように見えてライブ読み取りへ戻れない。
      this.showRestart(true);
      this.showFallbackMessage('アプリが一時停止されたためカメラを終了しました。［ライブ映像を再開］でもう一度読み取るか、［写真から選ぶ］または下のコード入力で続行してください。');
    }

    stopCamera() {
      if (this.frameHandle) global.cancelAnimationFrame(this.frameHandle);
      this.frameHandle = null;
      if (this.stream) this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
      this.detector = null;
      this.decoderMode = '';
      this.nativeDecoderEnabled = false;
      this.softwareDecoderEnabled = false;
      this.video.pause();
      this.video.srcObject = null;
    }

    clearPromise() {
      this.resolve = null;
      this.reject = null;
    }
  }

  global.InventoryQrScanner = InventoryQrScanner;
})(window);
