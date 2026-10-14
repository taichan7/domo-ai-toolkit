(function inventoryBootDiagnostics(global, document) {
  'use strict';

  var complete = false;
  var watchdog = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function messageOf(value) {
    if (!value) return '';
    if (typeof value === 'string') return value;
    if (value.message) return String(value.message);
    return String(value);
  }

  function show(title, detail) {
    var node = byId('boot-message');
    var titleNode = byId('boot-message-title');
    var detailNode = byId('boot-message-detail');
    if (!node) return;
    if (titleNode) titleNode.textContent = title || 'アプリを起動できません';
    if (detailNode) detailNode.textContent = detail || 'Domoとの接続を確認し、再読み込みしてください。';
    node.hidden = false;
    document.documentElement.setAttribute('data-app-boot', 'error');
  }

  function markReady() {
    complete = true;
    if (watchdog) global.clearTimeout(watchdog);
    var node = byId('boot-message');
    if (node) node.hidden = true;
    document.documentElement.setAttribute('data-app-boot', 'ready');
  }

  function markFailed(error, title) {
    if (complete) return;
    // 失敗を確定表示したら遅延ウォッチドッグを解除する。放置すると具体的な失敗理由が汎用の待機案内で上書きされる。
    if (watchdog) { global.clearTimeout(watchdog); watchdog = null; }
    var detail = messageOf(error) || 'Domoとの接続を確認し、再読み込みしてください。';
    show(title || 'アプリを起動できません', detail);
    if (global.console && typeof global.console.error === 'function') {
      global.console.error('[inventory-boot]', error);
    }
  }

  global.InventoryBoot = { ready: markReady, fail: markFailed };

  global.addEventListener('error', function (event) {
    var target = event && event.target;
    if (target && target !== global && (target.src || target.href)) {
      markFailed('必要なファイルを読み込めませんでした: ' + (target.src || target.href));
      return;
    }
    markFailed(event && (event.error || event.message));
  }, true);

  global.addEventListener('unhandledrejection', function (event) {
    markFailed(event && event.reason);
  });

  var retry = byId('boot-retry');
  if (retry) retry.addEventListener('click', function () { global.location.reload(); });

  watchdog = global.setTimeout(function () {
    // 二重の保険: 既に失敗表示（data-app-boot=error）なら汎用の待機案内で上書きしない。
    if (!complete && document.documentElement.getAttribute('data-app-boot') !== 'error') {
      show('起動に時間がかかっています', '通信を確認して「再読み込み」を押してください。問題が続く場合は、この表示を管理者へ共有してください。');
    }
  }, 12000);
})(window, document);
