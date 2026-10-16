(function inventoryApp(global, document) {
  'use strict';

  const dataApi = global.InventoryData;
  const config = global.InventoryConfig;
  const state = {
    data: {items: [], locations: [], rules: [], balances: [], transactions: [], alerts: []},
    dashboardRows: [],
    user: {id: '', name: '利用者', isAdmin: false},
    view: 'operations',
    step: 1,
    transactionType: 'IN',
    location: null,
    item: null,
    quantity: 1,
    reason: '',
    historyMode: 'transactions',
    recordTab: 'transactions',
    historyVisibleRows: [],
    // 一覧のページ送り位置（0始まり）。履歴・マスタとも1画面に全件を出さず PAGE_SIZE 件ずつ表示する。
    // 絞り込み・種別・タブ切替では 0 に戻し、ページ操作でのみ増減する。
    historyPage: 0,
    masterPage: 0,
    masterPageInfo: null,
    // ダッシュボード各パネルのページ送り位置（0始まり）。縦に伸び続けないよう panel ごとに
    // config.ui.dashboardPanelPageSize 件ずつ表示し、ページ操作でのみ増減する。データ再取得時は 0 に戻す。
    dashboardPages: {item: 0, location: 0, shortage: 0, dormant: 0},
    recentRows: [],
    dashboardDrilldowns: {kpi: [], item: [], location: [], trend: [], shortage: [], dormant: []},
    // DataFlow の TextGeneration タイルが品目×ロケーション単位で生成した AI コメント（AI_NOTE 行）を
    // `${item_code}::${location_code}` で引ける辞書に畳んでおく。ドリルダウン明細から即座に添えられる。
    aiNotes: {},
    // 在庫ダッシュボード上部の横断検索語（正規化済み）。品目別在庫・ロケーション別在庫・在庫不足・
    // 滞留在庫の4パネルを絞り込む。空文字なら絞り込みなし（無退行）。
    dashboardQuery: '',
    selectedHistoryIndex: null,
    contextDetailFilter: null,
    contextDetailOrigin: null,
    // ドロワーを閉じるスライドアウト完了後に hidden を確定するためのタイマー。再オープン時は解除する。
    drawerCloseTimer: null,
    requestId: null,
    bootReady: false,
    viewportFrame: null,
    // ダッシュボードのカード高さ揃え(equalizeDashboardRows)を1フレームに集約するための rAF ハンドル。
    dashboardEqualizeFrame: null,
    masterTab: 'item',
    masterEditKey: null,
    masterEditLabel: null,
    // 実行対象とフォーカス返却先を保持し、close リスナが一度だけ消費する。
    pendingConfirm: null
  };

  const elements = {};
  // 履歴ビューの統合タブのうち、マスタ編集（管理者専用）に相当する種別。取引・通知は履歴パネル、
  // これらはマスタパネルへ切り替える。1画面にまとめてメニュー数を減らすための対応表。
  const MASTER_TABS = {item: true, location: true, rule: true};
  // マスタ種別の日本語ラベル（編集ペインの見出し・説明文とトースト表現をここに集約）。
  const MASTER_LABELS = {item: '品目', location: 'ロケーション', rule: '基準在庫'};
  // 一覧1ページあたりの表示件数。履歴・マスタで共通。config.ui.listPageSize を唯一の定義源にして
  // ベタ書きの重複（片方だけ直し忘れ）を避ける。件数が増えても1画面を軽く保つための上限。
  const PAGE_SIZE = config.ui.listPageSize;
  // ページ送り委譲（handlePagerClick）で、scope から再フォーカス対象のページャ要素IDを引く対応表。
  const PAGER_CONTAINER_BY_SCOPE = {
    history: 'history-pager', master: 'master-pager',
    item: 'item-pager', location: 'location-pager', shortage: 'shortage-pager', dormant: 'dormant-pager'
  };
  const byId = (id) => document.getElementById(id);
  const number = new Intl.NumberFormat('ja-JP', {maximumFractionDigits: 2});
  const dateTime = new Intl.DateTimeFormat('ja-JP', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'});
  const dateTimeFull = new Intl.DateTimeFormat('ja-JP', {year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'});

  function startApplication() {
    Promise.resolve().then(init).catch(renderFatalBoot);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startApplication, {once: true});
  } else {
    startApplication();
  }

  async function init() {
    syncRuntimeLayout();
    cacheElements();
    bindEvents();
    bindViewportEvents();
    state.scanner = new global.InventoryQrScanner({
      dialog: byId('scanner-dialog'),
      video: byId('scanner-video'),
      message: byId('camera-message'),
      manualInput: byId('manual-qr'),
      manualButton: byId('manual-qr-submit'),
      imageInput: byId('qr-image-input'),
      imageButton: byId('qr-image-button'),
      captureInput: byId('qr-capture-input'),
      captureButton: byId('qr-capture-button'),
      restartButton: byId('qr-live-restart'),
      hint: byId('scanner-hint'),
      canvas: byId('qr-canvas'),
      title: byId('scanner-title')
    });
    setQrControlsReady(false, true);  // 起動直後＝読み込み中（busy）
    renderTestQrCodes();
    await refreshAll({quiet: true});
  }

  function renderFatalBoot(error) {
    state.bootReady = false;
    try { setQrControlsReady(false); } catch (ignored) { /* DOM may not be cached yet. */ }
    const status = byId('sync-status');
    if (status) {
      status.hidden = false;
      status.classList.add('error');
      const label = byId('sync-status-label');  // INV-061: 安定ラベル要素へ書く（lastChild 頼みを排す）
      if (label) label.textContent = '起動エラー';
    }
    if (global.InventoryBoot && typeof global.InventoryBoot.fail === 'function') {
      global.InventoryBoot.fail(error);
    }
  }

  function cacheElements() {
    [
      'sync-status', 'sync-status-label', 'history-caption', 'user-initial', 'user-name', 'location-search', 'item-search', 'location-options', 'item-options',
      'selected-location', 'selected-location-code', 'selected-item', 'selected-item-code', 'current-stock', 'minimum-stock',
      'quantity', 'reason', 'stock-preview', 'review-list', 'submit-button', 'recent-operations', 'kpi-grid', 'item-chart', 'location-chart',
      'trend-chart', 'shortage-list', 'dormant-list', 'ai-note-list', 'dashboard-search', 'history-search', 'history-type', 'history-head', 'history-body',
      'history-result-count', 'history-type-filter', 'masters-empty-guide', 'goto-master-register', 'history-pager', 'master-pager', 'item-pager', 'location-pager', 'shortage-pager', 'dormant-pager', 'loading-overlay', 'toast-region', 'confirm-dialog', 'confirm-title', 'confirm-message', 'confirm-details', 'confirm-action', 'confirm-cancel',
      'detail-pane', 'detail-eyebrow', 'detail-title', 'detail-subtitle', 'detail-content', 'chart-tooltip',
      'context-detail', 'context-detail-backdrop', 'context-detail-eyebrow', 'context-detail-title', 'context-detail-subtitle', 'context-detail-content', 'context-detail-more', 'context-detail-close',
      'step-count', 'step-action', 'selected-location-card', 'selected-item-card', 'run-notification',
      'master-form', 'master-item-code', 'master-item-name', 'master-item-category', 'master-item-unit',
      'master-location-code', 'master-location-name', 'master-location-zone',
      'master-rule-location', 'master-rule-item', 'master-rule-minimum', 'master-submit', 'master-new', 'master-list',
      'master-editor-title', 'master-editor-subtitle', 'master-result-count', 'master-delete', 'master-active', 'master-active-row',
      'history-filter', 'record-panel-history', 'record-panel-master'
    ].forEach((id) => { elements[id] = byId(id); });
  }

  function bindEvents() {
    document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
    // マスタ空の空状態ガイドから登録先（履歴・管理）へ直接遷移する（INV-020）。
    if (elements['goto-master-register']) elements['goto-master-register'].addEventListener('click', () => switchView('history'));
    document.querySelectorAll('.type-button').forEach((button) => button.addEventListener('click', () => setTransactionType(button.dataset.type)));
    document.querySelectorAll('.back-button').forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.back))));
    document.querySelectorAll('[data-step-nav]').forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.stepNav))));
    document.querySelectorAll('.scan-button').forEach((button) => button.addEventListener('click', () => scan(button.dataset.scan)));
    // 履歴（取引・通知）とマスタ（品目・ロケーション・基準在庫）を単一のタブ列に統合した。
    document.querySelectorAll('.record-tab').forEach((button) => {
      button.addEventListener('click', () => setRecordTab(button.dataset.record));
      button.addEventListener('keydown', handleRecordTabKey);
    });

    elements['location-search'].addEventListener('input', renderLocationOptions);
    elements['item-search'].addEventListener('input', renderItemOptions);
    elements.quantity.addEventListener('input', () => {
      // 在庫は整数（個）。増減は −／＋ ボタンで行う前提のため標準スピナー（↑↓）は出さず（type=text）、
      // キーボードや端末IMEからの小数・記号入力に備えて表示値そのものを数字だけへ正規化する。
      // これで 0.01 のような小数が入力欄に現れる余地を無くす（実機で報告された不具合の恒久対策）。
      const digits = String(elements.quantity.value || '').replace(/[^0-9]/g, '');
      if (digits !== elements.quantity.value) elements.quantity.value = digits;
      state.quantity = Number(digits);
      invalidateReview();
      renderStockPreview();
      renderStepNavigation();
    });
    // 数量の下限・上限は config.js を唯一の設定源にし、増減（changeQuantity）と送信前検証（validateDraft）で
    // クランプ・検証する。type=text には native な min/max/step が無いため DOM 側には持たせない。
    // WKWebView が HTML の inputmode 属性を無視することがあるため、整数キーパッドは IDL 側でも明示する。
    elements.quantity.inputMode = 'numeric';
    elements.reason.addEventListener('input', () => { state.reason = elements.reason.value; invalidateReview(); renderStepNavigation(); });
    // 検索語・種別の変更は絞り込みが変わるので、必ず1ページ目へ戻してから描画する。毎キーストロークで
    // 全件を再フィルタ+再ソート+再描画しないよう input はデバウンスする（INV-042）。種別は change ＝
    // 1回だけ発火するので即時のまま。候補リスト（30件上限）も即時のまま。
    elements['history-search'].addEventListener('input', debounce(() => { state.historyPage = 0; renderHistory(); }, config.ui.searchDebounceMs));
    elements['history-type'].addEventListener('change', () => { state.historyPage = 0; renderHistory(); });
    // ダッシュボード上部の横断検索。4パネルの絞り込みが変わるため、該当ページ位置を先頭へ戻して再描画する。
    elements['dashboard-search'].addEventListener('input', debounce(() => {
      state.dashboardQuery = normalizedSearch(elements['dashboard-search'].value);
      ['item', 'location', 'shortage', 'dormant'].forEach((key) => { state.dashboardPages[key] = 0; });
      renderDashboard();
    }, config.ui.searchDebounceMs));
    byId('view-dashboard').addEventListener('click', handleDashboardDrilldown);
    byId('view-dashboard').addEventListener('pointerover', handleChartPointerOver);
    byId('view-dashboard').addEventListener('pointermove', handleChartPointerMove);
    byId('view-dashboard').addEventListener('pointerout', handleChartPointerOut);
    byId('view-dashboard').addEventListener('focusin', handleChartFocus);
    byId('view-dashboard').addEventListener('focusout', hideChartTooltip);
    elements['history-body'].addEventListener('click', handleHistoryDrilldown);
    // ページ送りは安定した外枠コンテナへ委譲する（中身は再描画で作り替えるため個別バインド不可）。
    if (elements['history-pager']) elements['history-pager'].addEventListener('click', handlePagerClick);
    if (elements['master-pager']) elements['master-pager'].addEventListener('click', handlePagerClick);
    // ダッシュボード各パネルのページャ。ナビ要素自体に委譲するので、renderPager が中身のボタンを
    // 差し替えても購読は生き続ける（履歴・マスタと同じ方式）。
    ['item-pager', 'location-pager', 'shortage-pager', 'dormant-pager'].forEach((id) => {
      if (elements[id]) elements[id].addEventListener('click', handlePagerClick);
    });
    elements['recent-operations'].addEventListener('click', handleRecentDrilldown);
    // インライン詳細（ダッシュボード・入出庫）の閉じる／任意の履歴遷移。既定は同一メニュー内で完結する。
    if (elements['context-detail-close']) elements['context-detail-close'].addEventListener('click', hideContextDetail);
    if (elements['context-detail-more']) elements['context-detail-more'].addEventListener('click', openContextDetailInHistory);
    // ドロワーは背景オーバーレイのクリックと Esc でも閉じられるようにする（モーダル面としての標準操作）。
    if (elements['context-detail-backdrop']) elements['context-detail-backdrop'].addEventListener('click', hideContextDetail);
    document.addEventListener('keydown', handleDrawerKeydown);

    byId('quantity-minus').addEventListener('click', () => changeQuantity(-1));
    byId('quantity-plus').addEventListener('click', () => changeQuantity(1));
    byId('review-button').addEventListener('click', reviewTransaction);
    elements['submit-button'].addEventListener('click', confirmTransaction);
    byId('refresh-button').addEventListener('click', () => refreshAll());
    byId('history-refresh').addEventListener('click', () => refreshAll());
    byId('history-clear').addEventListener('click', clearHistoryFilters);
    if (elements['run-notification']) elements['run-notification'].addEventListener('click', confirmShortageNotification);
    if (elements['master-form']) elements['master-form'].addEventListener('submit', submitMaster);
    // 新規登録は右ペインを空の入力状態へ戻す入口。一覧行のクリック／キー操作は委譲で受け、
    // 選択行を右ペインの編集フォームへ読み込む（履歴のドリルダウンと同じ操作感に揃える）。
    if (elements['master-new']) elements['master-new'].addEventListener('click', newMaster);
    if (elements['master-delete']) elements['master-delete'].addEventListener('click', () => confirmMasterDelete(state.masterTab, state.masterEditKey, state.masterEditLabel));
    if (elements['confirm-dialog']) {
      elements['confirm-dialog'].addEventListener('close', handleConfirmClose);
      elements['confirm-dialog'].addEventListener('keydown', handleConfirmKeydown);
      elements['confirm-dialog'].addEventListener('cancel', (event) => { event.preventDefault(); cancelConfirmation(); });
      elements['confirm-dialog'].addEventListener('click', (event) => {
        if (event.target !== elements['confirm-dialog']) return;
        const rect = elements['confirm-dialog'].getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) cancelConfirmation();
      });
    }
    global.addEventListener('pagehide', cancelConfirmation);
    if (elements['master-list']) {
      elements['master-list'].addEventListener('click', handleMasterRowActivate);
    }
    elements['selected-location-card'].addEventListener('click', () => setStep(1));
    elements['selected-item-card'].addEventListener('click', () => setStep(2));
  }

  function bindViewportEvents() {
    const schedule = () => {
      if (state.viewportFrame !== null) return;
      const requestFrame = global.requestAnimationFrame || ((callback) => global.setTimeout(callback, 0));
      state.viewportFrame = requestFrame(() => {
        state.viewportFrame = null;
        syncRuntimeLayout();
      });
    };
    global.addEventListener('resize', schedule, {passive: true});
    global.addEventListener('orientationchange', schedule, {passive: true});
    if (global.visualViewport) global.visualViewport.addEventListener('resize', schedule, {passive: true});
  }

  function syncRuntimeLayout() {
    const root = document.documentElement;
    root.dataset.domoPlatform = isDomoMobileHost() ? 'mobile' : 'desktop';
    const viewportHeight = global.visualViewport?.height || global.innerHeight;
    if (Number.isFinite(viewportHeight) && viewportHeight > 0) {
      root.style.setProperty('--app-viewport-height', `${Math.round(viewportHeight)}px`);
    }
    applyMobilePersona();
    // 幅で列数が変わる auto-fit グリッドなので、リサイズ後はカード高さの揃えを取り直す
    // （視覚行の並び替えや折り返しの発生・解消に追従する）。
    scheduleDashboardEqualize();
  }

  function isMobileHostActive() {
    return document.documentElement.dataset.domoPlatform === 'mobile';
  }

  // サイドバーの「動作確認用QR」にスキャン可能なテストQRを描画する（demo モードのみ表示）。
  // 内製生成器で自己完結させ（正しさは同梱jsQRとの往復テストで担保）、静的な内容なので
  // 起動時に一度だけ描く。サイドバーはモバイルでは非表示のため PC 専用で足りる。
  function renderTestQrCodes() {
    // 固定コード（LOC-01/ITEM-001）のサンプルQRは顧客の実マスタでは必ず失敗するため、デモモードの
    // ときだけ表示する（本番=domo/error では隠す。試用導線は開発ガイドへ集約）＝INV-068。
    const block = document.getElementById('test-qr-help');
    if (!block) return;
    if (dataApi.mode !== 'demo') { block.hidden = true; return; }
    block.hidden = false;
    if (!global.InventoryQR || typeof global.InventoryQR.toSvg !== 'function') return;
    document.querySelectorAll('.qr-sample[data-qr]').forEach((node) => {
      const payload = node.dataset.qr;
      if (!payload || node.dataset.rendered === 'true') return;
      try {
        const svg = global.InventoryQR.toSvg(payload, {moduleSize: 4, quietZone: 2, title: `${payload} のテスト用QR`});
        node.innerHTML = `<span class="qr-sample-image">${svg}</span><code>${escapeHtml(payload)}</code>`;
        node.dataset.rendered = 'true';
      } catch (error) {
        // QR生成に失敗しても致命ではない。コード文字列のテキスト表示へフォールバックする。
        node.innerHTML = `<code>${escapeHtml(payload)}</code>`;
      }
    });
  }

  // ハンディ端末を想定し、スマホアプリでは現場作業に不要な導線（マスタ編集タブ）を
  // 隠して最小構成にする。PCは全機能を維持する（PC業務とスマホ業務は別ペルソナ）。
  function applyMobilePersona() {
    const mobile = isMobileHostActive();
    if (mobile) {
      document.querySelectorAll('.admin-only').forEach((node) => { node.hidden = true; });
      // マスタ編集タブはモバイルで隠れるため、表示中なら取引履歴へ戻す。
      if (MASTER_TABS[state.recordTab]) setRecordTab('transactions');
    }
  }

  async function refreshAll(options) {
    cancelConfirmation();
    const quiet = options && options.quiet;
    if (!quiet) setLoading(true, 'データを更新しています');
    state.bootReady = false;
    setQrControlsReady(false, true);  // 読み込み中＝busy
    try {
      const loaded = await dataApi.loadInitialData();
      state.data = loaded;
      state.user = loaded.user;
      setConnectionStatus(loaded.mode === 'domo' ? 'connected' : 'demo');
      updateUser();
      renderAll();
      state.bootReady = loaded.locations.some(isActive) && loaded.items.some(isActive);
      setQrControlsReady(state.bootReady);  // 読み込み完了＝busy でない（不可用は disabled のみ）
      // マスタ空＝入出庫の行き止まり。登録先（履歴・管理）への空状態ガイドを出す（INV-020）。
      if (elements['masters-empty-guide']) elements['masters-empty-guide'].hidden = state.bootReady;
      if (global.InventoryBoot && typeof global.InventoryBoot.ready === 'function') global.InventoryBoot.ready();
      if (!state.bootReady) {
        toast('有効な品目・ロケーションのマスタがありません。「履歴・管理」で品目とロケーションを登録してください。', 'error', config.ui.toastDurationLong);
      }

      const authTask = dataApi.callFunction('get_inventory_state', {request_json: '{}'}).then((auth) => {
        if (auth && auth.ok && auth.user) {
          // Code Engine の実行情報は isAdmin を確定させる権威ソースだが、インスタンスによっては
          // メールアドレスを返さない（空文字）。People API で解決済みの state.user.email を空文字で
          // 上書きしないよう、auth 側が空のときは既存値を保持する（AI在庫通知の宛先解決に必須）。
          const authUser = auth.user;
          state.user = Object.assign({}, state.user, authUser, {
            // CE が空を返すインスタンスでは People API で解決済みの値を尊重する。
            // 氏名も同様：CE の name が空でも、既に解決した実名を保持する。
            email: authUser.email || state.user.email || '',
            name: authUser.name || state.user.name || '',
          });
          updateUser();
        }
      }).catch(() => {
        // Read-only screens remain available if Code Engine is temporarily unavailable.
      });
      // ダッシュボードの運用数値は、上で取得済みの loaded(ライブ AppDB スナップショット)を渡して
      // 算出する。集計 DataFlow は遅延するため主ソースにせず、AI 在庫コメントだけを合流させる。
      // 同一スナップショット共用で、現在庫がダッシュボードとドリルダウンで食い違わない。
      const dashboardTask = dataApi.loadDashboard(loaded).then((rows) => {
        state.dashboardRows = rows;
        // データ再取得時はページ位置を先頭へ戻す（state.dashboardPages の契約）。古いページ番号が
        // 件数の変わった新データを指し、初手で途中ページや空表示になるのを防ぐ。
        state.dashboardPages = {item: 0, location: 0, shortage: 0, dormant: 0};
        renderDashboard();
      }).catch(() => {
        state.dashboardRows = [];
        state.dashboardPages = {item: 0, location: 0, shortage: 0, dormant: 0};
        renderDashboard();
      });
      await Promise.all([authTask, dashboardTask]);
      if (!quiet) toast('最新データを読み込みました。', 'success');
      return state.bootReady;
    } catch (error) {
      state.bootReady = false;
      setQrControlsReady(false);
      setConnectionStatus('error');
      toast(errorMessage(error, 'データを読み込めませんでした。'), 'error');
      renderAll();
      if (global.InventoryBoot && typeof global.InventoryBoot.ready === 'function') global.InventoryBoot.ready();
      return false;
    } finally {
      setLoading(false);
    }
  }

  function renderAll() {
    renderLocationOptions();
    renderItemOptions();
    renderSelection();
    renderRecent();
    renderDashboard();
    renderHistory();
    renderMasters();
    setStep(state.step, false);
  }

  // 接続状態バッジは「問題があるときだけ」出す。正常時（Domo接続済み）は常時表示を避け、
  // ヘッダーの情報量を最小にする＝運用中に見るべきものだけを残す設計。
  function setConnectionStatus(mode) {
    const node = elements['sync-status'];
    if (!node) return;
    // INV-061: ラベルは安定要素 #sync-status-label に書き、末尾テキストノード頼み（lastChild）を使わない
    //（ドットを別行にする整形や末尾テキスト削除で lastChild が dot span や null になる脆さを排す）。
    const label = elements['sync-status-label'];
    node.className = 'sync-status';
    if (mode === 'connected') {
      node.hidden = true;
      return;
    }
    node.hidden = false;
    if (mode === 'demo') {
      if (label) label.textContent = 'ローカルデモ';
    } else {
      node.classList.add('error');
      if (label) label.textContent = '接続エラー';
    }
  }

  function updateUser() {
    const name = state.user.name || '利用者';
    elements['user-name'].textContent = name;
    elements['user-initial'].textContent = Array.from(name)[0] || '利';
    document.querySelectorAll('.admin-only').forEach((node) => { node.hidden = !state.user.isAdmin || isMobileHostActive(); });
    // admin-only 一括表示は record-panel-master も対象になるため、タブ状態で表示を必ず上書きする
    // （取引タブのまま履歴とマスタが両方縦に並ぶ不具合の防止）。
    syncRecordPanels();
    // 権限が外れている場合、マスタ編集タブ表示中なら取引履歴へ戻す（PC・モバイル共通の二重防御）。
    if (MASTER_TABS[state.recordTab] && !state.user.isAdmin) setRecordTab('transactions');
    applyMobilePersona();
  }

  function switchView(view) {
    cancelConfirmation();
    state.view = view;
    // メニュー切替時はインライン詳細を閉じ、前ビューのドリルダウン明細が残らないようにする。
    hideContextDetail();
    document.querySelectorAll('.view').forEach((node) => node.classList.toggle('active', node.id === `view-${view}`));
    // 現在ビューは .active の見た目に加えて aria-current='page' でも公開する。
    // これで最上位ナビが、type-button の aria-pressed・record-tab の aria-selected・
    // stepper の aria-current と同じ「現在地を必ずATへ伝える」規約に揃う。
    document.querySelectorAll('.nav-item').forEach((node) => {
      const current = node.dataset.view === view;
      node.classList.toggle('active', current);
      if (current) node.setAttribute('aria-current', 'page');
      else node.removeAttribute('aria-current');
    });
    document.querySelector(`#view-${view}`).focus({preventScroll: true});
    if (view === 'dashboard') renderDashboard();
    if (view === 'history') renderHistory();
    scrollAppToTop();
  }

  function scrollAppToTop() {
    const content = document.querySelector('main');
    const contentScrolls = content && content.scrollHeight > content.clientHeight;
    if (contentScrolls) content.scrollTo({top: 0, behavior: 'smooth'});
    else global.scrollTo({top: 0, behavior: 'smooth'});
  }

  function setTransactionType(type) {
    const changed = state.transactionType !== type;
    state.transactionType = type;
    document.querySelectorAll('.type-button').forEach((button) => {
      const selected = button.dataset.type === type;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    if (changed) invalidateReview();
    renderStockPreview();
    if (changed && state.step === 4) {
      setStep(3);
      toast('処理種別を変更しました。数量を確認し、もう一度「内容を確認」を押してください。', 'success');
    } else {
      setStep(state.step);
    }
  }

  function setStep(step, focusTitle = true) {
    cancelConfirmation();
    state.step = Math.min(4, Math.max(1, step));
    renderStepNavigation();
    document.querySelectorAll('.form-step').forEach((node) => node.classList.toggle('active', Number(node.dataset.stepPanel) === state.step));
    // 初期表示ではフォーカスを当てない。プログラム的な focus は PC で :focus-visible の
    // 枠を描き、STEP 1 が「クリック済み／選択済み」に見えてしまう。ステップ移動が
    // ユーザー操作で起きたときだけ、キーボード操作の連続性のために見出しへフォーカスする。
    if (focusTitle) byId(`step-title-${state.step}`)?.focus({preventScroll: true});
  }

  function renderStepNavigation() {
    const stepActions = {
      1: 'ロケーションを選択',
      2: '品目を選択',
      3: `${state.transactionType === 'OUT' ? '出庫' : '入庫'}数量を入力`,
      4: '登録内容を確認'
    };
    elements['step-count'].textContent = `ステップ ${state.step} / 4`;
    elements['step-action'].textContent = stepActions[state.step];
    document.querySelectorAll('.stepper li').forEach((node) => {
      const nodeStep = Number(node.dataset.step);
      const button = node.querySelector('[data-step-nav]');
      const accessible = nodeStep === 1
        || (nodeStep === 2 && Boolean(state.location))
        || (nodeStep === 3 && Boolean(state.location && state.item))
        || (nodeStep === 4 && Boolean(state.requestId));
      const complete = (nodeStep === 1 && Boolean(state.location))
        || (nodeStep === 2 && Boolean(state.item))
        || (nodeStep === 3 && Boolean(state.requestId));
      node.classList.toggle('active', nodeStep === state.step);
      node.classList.toggle('done', complete && nodeStep !== state.step);
      node.classList.toggle('available', accessible && nodeStep !== state.step);
      button.disabled = nodeStep === state.step || !accessible;
      if (nodeStep === state.step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
  }

  function normalizedSearch(value) {
    return String(value || '').trim().toLocaleLowerCase('ja-JP');
  }

  // 連続入力の最後の1回だけ fn を走らせる（INV-042）。横断検索の毎キーストローク全再描画を抑える。
  function debounce(fn, wait) {
    let timer = 0;
    return (...args) => {
      global.clearTimeout(timer);
      timer = global.setTimeout(() => fn(...args), wait);
    };
  }

  function renderLocationOptions() {
    const query = normalizedSearch(elements['location-search'].value);
    const matched = state.data.locations.filter((row) => isActive(row) && (!query || `${row.location_code} ${row.location_name} ${row.zone || ''}`.toLocaleLowerCase('ja-JP').includes(query)));
    const rows = matched.slice(0, config.ui.optionListLimit);
    elements['location-options'].innerHTML = rows.length ? rows.map((row) => optionHtml('location', row.location_code, row.location_name, row.zone ? `ゾーン ${row.zone}` : '', state.location?.location_code === row.location_code)).join('') + optionMoreNote(matched.length) : emptyHtml('該当するロケーションがありません。');
    elements['location-options'].querySelectorAll('.option-button').forEach((button) => button.addEventListener('click', () => selectLocation(button.dataset.code)));
  }

  function renderItemOptions() {
    const query = normalizedSearch(elements['item-search'].value);
    const matched = state.data.items.filter((row) => isActive(row) && (!query || `${row.item_code} ${row.item_name} ${row.category || ''}`.toLocaleLowerCase('ja-JP').includes(query)));
    const rows = matched.slice(0, config.ui.optionListLimit);
    elements['item-options'].innerHTML = rows.length ? rows.map((row) => optionHtml('item', row.item_code, row.item_name, row.category || '', state.item?.item_code === row.item_code)).join('') + optionMoreNote(matched.length) : emptyHtml('該当する品目がありません。');
    elements['item-options'].querySelectorAll('.option-button').forEach((button) => button.addEventListener('click', () => selectItem(button.dataset.code)));
  }

  // 候補ボタンは「選択して次へ進む」操作なので、素の <button>（＝暗黙 role=button）のままにする。
  // role="option" は listbox の子専用で、キーボードモデル（活性子孫・矢印移動）を伴わないと不完全な契約
  // になる。ここでは検索入力＋候補ボタン群という素直な構成にし、選択中候補は集合内カレントを表す
  // aria-current で示す（履歴・マスタ行と統一した規約）。
  function optionMoreNote(total) {
    // 候補は単一キャップ（ページングしない）規約。超過時だけ末尾へ非対話の注記を出し、超過の事実と
    // 次の行動（検索語で絞り込む）を伝える＝沈黙打ち切りで「登録されていない」と誤認させない（INV-012）。
    const hidden = total - config.ui.optionListLimit;
    return hidden > 0 ? `<p class="option-note" role="note">ほか ${number.format(hidden)} 件の候補があります。検索語を追加して絞り込んでください。</p>` : '';
  }

  function optionHtml(type, code, name, meta, selected) {
    const icon = type === 'location' ? 'LOC' : 'SKU';
    return `<button class="option-button" type="button"${selected ? ' aria-current="true"' : ''} data-code="${escapeAttribute(code)}"><span class="option-icon">${icon}</span><span><strong>${escapeHtml(name)}</strong><small>${escapeHtml(code)}</small></span><span class="option-meta">${escapeHtml(meta)}</span></button>`;
  }

  function selectLocation(code) {
    state.location = state.data.locations.find((row) => row.location_code === code) || null;
    state.item = null;
    invalidateReview();
    elements['item-search'].value = '';
    renderSelection();
    renderLocationOptions();
    renderItemOptions();
    setStep(2);
  }

  function selectItem(code) {
    state.item = state.data.items.find((row) => row.item_code === code) || null;
    invalidateReview();
    renderSelection();
    renderItemOptions();
    setStep(3);
  }

  async function scan(expectedType) {
    if (!state.bootReady) {
      toast('在庫マスタを読み込んでいます。少し待ってからQRを読み取ってください。', 'error');
      return;
    }
    try {
      const scanResult = await state.scanner.open(expectedType);
      // スキャナは expectedType 一致時のみ解決する（型不一致は届かない）ので、再パースや到達不能な
      // 型不一致 throw は持たず、解決済み code を直接使う。接頭辞パースの唯一定義源はスキャナ側の
      // parse() のままで、ここから越境して呼ばない（INV-060）。
      if (expectedType === 'location') {
        const match = state.data.locations.find((row) => row.location_code === scanResult.code && isActive(row));
        if (!match) throw new Error('有効なロケーションが見つかりません。');
        selectLocation(match.location_code);
        toast(`${match.location_name}を選択しました。続けて品目を選んでください。`, 'success');
      } else {
        const match = state.data.items.find((row) => row.item_code === scanResult.code && isActive(row));
        if (!match) throw new Error('有効な品目が見つかりません。');
        selectItem(match.item_code);
        toast(`${match.item_name}を選択しました。続けて数量を確認してください。`, 'success');
      }
    } catch (error) {
      if (error.message !== 'SCAN_CANCELLED') toast(errorMessage(error, 'QRコードを読み取れませんでした。'), 'error');
    }
  }

  function setQrControlsReady(ready, busy = false) {
    document.querySelectorAll('.scan-button').forEach((button) => {
      button.disabled = !ready;
      // aria-busy は「読み込み中」のときだけ true。マスタ空やエラーで使えない状態は disabled だけで表し、
      // 「読込中」を意味する aria-busy を居座らせない（INV-020）。
      if (busy) button.setAttribute('aria-busy', 'true');
      else button.removeAttribute('aria-busy');
    });
  }

  function currentBalance() {
    if (!state.location || !state.item) return null;
    return state.data.balances.find((row) => row.location_code === state.location.location_code && row.item_code === state.item.item_code) || null;
  }

  function currentRule() {
    if (!state.location || !state.item) return null;
    return state.data.rules.find((row) => row.location_code === state.location.location_code && row.item_code === state.item.item_code && isActive(row)) || null;
  }

  function renderSelection() {
    elements['selected-location'].textContent = state.location?.location_name || '未選択';
    elements['selected-location-code'].textContent = state.location?.location_code || 'QRまたは一覧から選択';
    elements['selected-item'].textContent = state.item?.item_name || '未選択';
    elements['selected-item-code'].textContent = state.item?.item_code || 'QRまたは一覧から選択';
    elements['selected-item-card'].disabled = !state.location;
    const balance = currentBalance();
    const rule = currentRule();
    elements['current-stock'].textContent = balance ? `${number.format(Number(balance.quantity || 0))} ${state.item?.unit || ''}` : (state.item && state.location ? `0 ${state.item.unit || ''}` : '—');
    elements['minimum-stock'].textContent = `基準在庫: ${rule ? number.format(Number(rule.minimum_quantity || 0)) : '設定なし'}`;
    renderStockPreview();
  }

  function changeQuantity(delta) {
    // 現在値を整数へ丸めてから増減する。0.01 等の残差が種になって 18.00999… のような
    // 浮動小数が積み上がるのを防ぎ、増減は常に整数（個）に収める。
    const current = Math.round(Number(elements.quantity.value || 0));
    const next = Math.max(config.quantityMinimum, Math.min(config.quantityMaximum, current + delta));
    elements.quantity.value = next;
    state.quantity = next;
    invalidateReview();
    renderStockPreview();
    renderStepNavigation();
  }

  function projectedQuantity() {
    const before = Number(currentBalance()?.quantity || 0);
    const quantity = Number(state.quantity || 0);
    if (state.transactionType === 'OUT') return before - quantity;
    return before + quantity;
  }

  function renderStockPreview() {
    const node = elements['stock-preview'];
    if (!state.location || !state.item) {
      node.className = 'stock-preview';
      node.textContent = 'ロケーションと品目を選択すると、登録後の見込み在庫を表示します。';
      return;
    }
    const before = Number(currentBalance()?.quantity || 0);
    const after = projectedQuantity();
    const minimum = Number(currentRule()?.minimum_quantity || 0);
    node.className = 'stock-preview';
    if (!Number.isFinite(after)) {
      node.textContent = '数量を入力してください。';
      return;
    }
    if (after < 0) node.classList.add('error');
    else if (minimum > 0 && after < minimum) node.classList.add('warning');
    const suffix = after < 0 ? '（在庫数を超えるため登録できません）' : minimum > 0 && after < minimum ? '（基準在庫を下回ります）' : '';
    const unit = state.item.unit || '';
    const operation = state.transactionType === 'OUT' ? '出庫' : '入庫';
    const operator = state.transactionType === 'OUT' ? '−' : '＋';
    node.innerHTML = `<span>登録後の見込み在庫</span><strong>${escapeHtml(number.format(after))} ${escapeHtml(unit)}</strong><small>現在 ${escapeHtml(number.format(before))} ${escapeHtml(unit)} ${operator} ${operation} ${escapeHtml(number.format(Number(state.quantity || 0)))} ${escapeHtml(unit)}${escapeHtml(suffix)}</small>`;
  }

  function reviewTransaction() {
    state.quantity = Number(elements.quantity.value);
    state.reason = elements.reason.value.trim();
    const validation = validateDraft();
    if (validation) {
      toast(validation, 'error');
      return;
    }
    const labels = {IN: '入庫', OUT: '出庫'};
    const rows = [
      ['処理種別', labels[state.transactionType]],
      ['ロケーション', `${state.location.location_name} (${state.location.location_code})`],
      ['品目', `${state.item.item_name} (${state.item.item_code})`],
      ['数量', `${number.format(state.quantity)} ${state.item.unit || ''}`],
      ['登録後の見込み在庫', `${number.format(projectedQuantity())} ${state.item.unit || ''}（現在 ${number.format(Number(currentBalance()?.quantity || 0))} ${state.item.unit || ''} ${state.transactionType === 'OUT' ? '−' : '＋'} ${number.format(state.quantity)} ${state.item.unit || ''}）`],
      ['理由・メモ', state.reason || '—']
    ];
    elements['review-list'].innerHTML = rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
    state.requestId = createRequestId();
    setStep(4);
  }

  function validateDraft() {
    if (!state.location || !state.item) return 'ロケーションと品目を選択してください。';
    if (!isActive(state.location) || !isActive(state.item)) return '停止中のロケーションまたは品目には登録できません。先に対象を有効化してください。';
    if (!Number.isFinite(state.quantity) || !Number.isInteger(state.quantity) || state.quantity < config.quantityMinimum || state.quantity > config.quantityMaximum) return `数量は${number.format(config.quantityMinimum)}以上${number.format(config.quantityMaximum)}以下の整数で入力してください。`;
    if (state.transactionType === 'OUT' && projectedQuantity() < 0) return '在庫数を超える出庫は登録できません。';
    return '';
  }

  function transactionRequest() {
    return {
      request_id: state.requestId,
      transaction_type: state.transactionType,
      location_code: state.location?.location_code,
      item_code: state.item?.item_code,
      quantity: state.quantity,
      reason: state.reason,
      source: isMobileHostActive() ? 'DOMO_MOBILE' : 'DOMO_WEB',
      operator_email: state.user.email || '',
      operator_display_name: state.user.name || ''
    };
  }

  function confirmTransaction() {
    const validation = validateDraft();
    if (validation) { toast(validation, 'error'); setStep(3); return; }
    if (!state.requestId) state.requestId = createRequestId();
    const payload = transactionRequest();
    const operation = state.transactionType === 'OUT' ? '出庫' : '入庫';
    const unit = state.item.unit || '';
    showActionConfirmation({
      title: `${operation}を登録しますか？`,
      message: '確定後は履歴に記録されます。登録直前にサーバーで最新の在庫を確認し、基準在庫の状態が変わった場合はAI通知も開始します。',
      details: [
        ['ロケーション', `${state.location.location_name}（${payload.location_code}）`],
        ['品目', `${state.item.item_name}（${payload.item_code}）`],
        ['数量', `${operation} ${number.format(payload.quantity)} ${unit}`],
        ['登録後の見込み在庫', `${number.format(Number(currentBalance()?.quantity || 0))} → ${number.format(projectedQuantity())} ${unit}`],
        ['理由・メモ', payload.reason || '—']
      ],
      actionLabel: 'はい、登録する',
      trigger: elements['submit-button'],
      onConfirm: () => {
        if (JSON.stringify(payload) !== JSON.stringify(transactionRequest())) {
          toast('登録内容が変わりました。もう一度内容を確認してください。', 'error');
          return;
        }
        submitTransaction(payload);
      }
    });
  }

  async function submitTransaction(payload) {
    if (!elements['loading-overlay'].hidden) return;
    const validation = validateDraft();
    if (validation) {
      toast(validation, 'error');
      setStep(3);
      return;
    }
    elements['submit-button'].disabled = true;
    setLoading(true, '在庫を登録しています');
    try {
      const result = await dataApi.callFunction('register_transaction', {request_json: JSON.stringify(payload)});
      if (!result || !result.ok) throw new Error(result?.error?.message || '登録処理に失敗しました。');
      const transaction = result.transaction || {};
      const label = {IN: '入庫', OUT: '出庫'}[transaction.transaction_type || state.transactionType] || '登録';
      const unit = state.item.unit || '';
      const locationName = transaction.location_name || state.location.location_name;
      const itemName = transaction.item_name || state.item.item_name;
      const before = Number(transaction.balance_before);
      const after = Number(transaction.balance_after ?? result.balance?.quantity);
      const balanceText = Number.isFinite(before) && Number.isFinite(after) ? `、確定在庫 ${number.format(before)} → ${number.format(after)} ${unit}` : '';
      let notificationText = '';
      let notificationError = null;
      // 通知Workflowの起動は Code Engine がサーバー側で行う（最新の有効版を実行時に解決）。
      // フロントは Workflow API を直接呼ばない＝カードの再配線・再埋め込みが不要。
      if (!result.duplicate && result.notification?.workflow_ready) {
        if (result.notification.workflow_started) {
          notificationText = '。AI在庫通知を開始しました';
        } else {
          notificationError = result.notification.workflow_error || '通知Workflowを開始できませんでした。';
        }
      }
      toast(result.duplicate
        ? `${locationName}／${itemName}の同じ登録は処理済みです${balanceText}。`
        : `${locationName}／${itemName}を${label}${number.format(Number(transaction.quantity ?? state.quantity))} ${unit}で登録しました${balanceText}${notificationText}。`, 'success', config.ui.toastDurationLong);
      if (notificationError) {
        toast('在庫登録は完了しましたが、AI在庫通知を開始できませんでした。通知履歴を確認してください。', 'error', config.ui.toastDurationLong);
      }
      resetOperation();
      await refreshAll({quiet: true});
    } catch (error) {
      toast(errorMessage(error, '在庫を登録できませんでした。通信を確認して再試行してください。'), 'error', config.ui.toastDurationLong);
    } finally {
      setLoading(false);
      elements['submit-button'].disabled = false;
    }
  }

  // 通知Workflowの起動・起動結果の監査記録（STARTED／FAILED）は Code Engine（inventory_api）が
  // サーバー側で完結させる。フロントに Workflow を起動するヘルパーは持たない——起動される版は
  // かつて App Studio カードの配線（埋め込み時点のスナップショット）が決めていたため、
  // Workflow を改版するたびにカードを再埋め込みする必要があった。CE がモデルの有効版を実行時に
  // 解決して起動するようになり、改版・release だけで最新版が使われる（画面は結果を表示するだけ）。
  /**
   * オンデマンドで在庫不足通知Workflowを起動する導線（取引に紐づかない起動例）。
   *
   * 現在もっとも深刻な在庫不足に対し、People APIで解決した宛先(operator_email)を
   * Code Engineへ渡し、CE がサーバー側で最新の有効版のAI在庫通知Workflowをその場で開始する
   * （起動結果は CE が ALERT_HISTORY へ確定し、画面は notification の結果だけを表示する）。
   * 実行コンテキストがメールを返さないインスタンスでも宛先を確定できるよう
   * operator_email を同じく同送する。
   */
  function confirmShortageNotification() {
    const recipient = {operator_email: state.user.email || '', operator_display_name: state.user.name || ''};
    showActionConfirmation({
      title: 'AI在庫通知を実行しますか？',
      message: '実行時点の在庫不足をCode Engineで確認し、AIが通知文を作成して実行ユーザー宛てにメールを送信します。不足がない場合は通知しません。',
      details: [['通知先', recipient.operator_email || '実行時にDomoユーザーのメールアドレスを確認します']],
      actionLabel: 'はい、通知を実行する',
      trigger: elements['run-notification'],
      onConfirm: () => runShortageNotification(recipient)
    });
  }

  async function runShortageNotification(recipient) {
    if (!elements['loading-overlay'].hidden) return;
    const button = elements['run-notification'];
    if (button) button.disabled = true;
    setLoading(true, 'AI在庫通知を実行しています');
    try {
      const result = await dataApi.callFunction('start_shortage_notification', {request_json: JSON.stringify(recipient)});
      if (!result || !result.ok) throw new Error(result?.error?.message || 'AI在庫通知を開始できませんでした。');
      const notification = result.notification || {};
      if (!notification.workflow_ready) {
        toast(notification.reason === 'NO_SHORTAGE'
          ? '現在、基準在庫を下回っている品目はありません。'
          : notification.reason === 'RECIPIENT_EMAIL_MISSING'
            ? '通知の宛先メールアドレスを確認できないため、AI在庫通知を開始できません。'
            : 'AI在庫通知の対象がありません。', '', 6000);
        return;
      }
      const others = Number(notification.shortage_count) > 1 ? `（ほか${Number(notification.shortage_count) - 1}件の不足あり）` : '';
      if (notification.workflow_started) {
        toast(`AI在庫通知を開始しました${others}。通知履歴で状況を確認できます。`, 'success', config.ui.toastDurationLong);
      } else {
        toast('AI在庫通知を開始できませんでした。通知履歴を確認してください。', 'error', config.ui.toastDurationLong);
      }
      await refreshAll({quiet: true});
    } catch (error) {
      toast(errorMessage(error, 'AI在庫通知を実行できませんでした。'), 'error', config.ui.toastDurationLong);
    } finally {
      setLoading(false);
      if (button) button.disabled = false;
    }
  }

  function resetOperation() {
    state.location = null;
    state.item = null;
    state.quantity = 1;
    state.reason = '';
    state.requestId = null;
    elements['location-search'].value = '';
    elements['item-search'].value = '';
    elements.quantity.value = '1';
    elements.reason.value = '';
    setStep(1);
  }

  function invalidateReview() {
    cancelConfirmation();
    state.requestId = null;
  }

  // 物理削除（ITEM/LOCATION）されたマスタの取引には Code Engine が archived 印を付ける。
  // ダッシュボードの集計（KPIカード・7日トレンド）は canonical DataFlow もフォールバック集計も
  // archived を除外するため、その内訳ドリルダウン・「直近の登録」も同じ基準で archived を落とし、
  // 同一画面でカード値と内訳・一覧が食い違わないようにする。台帳（履歴）ビューは監査証跡として
  // archived 取引も表示するので、そちらは state.data.transactions を素で使い続ける。
  function activeTransactions() {
    // archived 判定は集計（domo-access.buildDashboardRows）と同一にするため共有定義を使う（INV-041）。
    return state.data.transactions.filter((row) => !dataApi.isArchived(row));
  }

  function renderRecent() {
    const rows = [...activeTransactions()].sort(sortNewest('occurred_at')).slice(0, config.ui.recentCardLimit);
    state.recentRows = rows;
    const content = rows.length ? rows.map((row, index) => {
      const typeClass = row.transaction_type === 'OUT' ? 'out' : '';
      return `<button type="button" class="recent-row" data-recent-index="${index}" aria-label="${escapeAttribute(row.item_name || row.item_code)}の取引詳細"><span class="recent-badge ${typeClass}">${escapeHtml(transactionLabel(row.transaction_type))}</span><span><strong>${escapeHtml(row.item_name || row.item_code)}</strong><small>${escapeHtml(row.location_name || row.location_code)}</small></span><time>${formatDate(row.occurred_at)}</time><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button>`;
    }).join('') : '<div class="empty-compact">まだ取引がありません。</div>';
    elements['recent-operations'].innerHTML = `<h3>直近の登録</h3>${content}`;
  }

  /**
   * 在庫ダッシュボードの一覧行を、上部ツールバーの横断検索語で絞り込む。
   *
   * 検索対象は各行が持ちうる表示項目（品目名/コード・ロケーション名/コード・分類・ゾーン・表示ラベル）を
   * 1本の文字列へ連結したもの。品目別在庫・ロケーション別在庫・在庫不足・滞留在庫の4パネルで共用する。
   * KPI・7日間トレンド・AIコメントは集計/時系列のため呼び出し側で対象外にしている。
   * 検索語が空なら元の配列をそのまま返し、絞り込み前と完全に同じ表示にする（無退行）。
   *
   * @param {Array<object>} rows 整列済みの一覧行（呼び出し側で sort 済み）
   * @return {Array<object>} 検索語に一致する行。ページャ・ドリルダウンの index はこの配列基準で一貫する。
   */
  function filterDashboardRows(rows) {
    const query = state.dashboardQuery;
    if (!query) return rows;
    return rows.filter((row) => {
      // 状態トークン（不足/滞留）を haystack へ合成し、検索プレースホルダの約束どおり
      // 「不足」「滞留」で該当パネルを絞り込めるようにする（INV-013。record_type が状態の真実源）。
      const stateToken = row.record_type === 'SHORTAGE' ? '不足' : (row.record_type === 'DORMANT' ? '滞留' : '');
      const haystack = [row.label, row.item_code, row.item_name, row.category, row.location_code, row.location_name, row.zone, stateToken]
        .filter((value) => value != null && value !== '')
        .join(' ')
        .toLocaleLowerCase('ja-JP');
      return haystack.includes(query);
    });
  }

  /**
   * ダッシュボード一覧が空のときの表示HTMLを返す。検索中は「一致なし」を、通常時は既定メッセージを返す。
   * 検索で0件になったときに「在庫不足はありません」のような誤解を招く文言を出さないための切り替え。
   *
   * @param {string} defaultMarkup 検索していないときに表示する既定の空状態HTML
   * @return {string} 表示するHTML
   */
  function dashboardEmpty(defaultMarkup) {
    if (!state.dashboardQuery) return defaultMarkup;
    const shown = String(elements['dashboard-search'].value || '').trim();
    return `<div class="empty-state">「${escapeHtml(shown)}」に一致する記録がありません。</div>`;
  }

  function renderDashboard() {
    const rows = state.dashboardRows || [];
    const kpis = rows.filter((row) => row.record_type === 'KPI');
    const kpiOrder = ['TOTAL_QUANTITY', 'ITEM_COUNT', 'SHORTAGE_COUNT', 'TODAY_IN_COUNT', 'TODAY_OUT_COUNT'];
    const fallbackLabels = {TOTAL_QUANTITY: '総在庫数', ITEM_COUNT: '在庫品目', SHORTAGE_COUNT: '在庫不足', TODAY_IN_COUNT: '本日の入庫', TODAY_OUT_COUNT: '本日の出庫'};
    const kpiRows = kpiOrder.map((key) => {
      const row = kpis.find((item) => item.metric_key === key) || {metric_value: 0, label: fallbackLabels[key]};
      return Object.assign({}, row, {metric_key: key, label: row.label || fallbackLabels[key]});
    });
    state.dashboardDrilldowns.kpi = kpiRows;
    elements['kpi-grid'].innerHTML = kpiRows.map((row, index) => {
      const isShortage = row.metric_key === 'SHORTAGE_COUNT';
      const value = Number(row.metric_value || 0);
      const isAlert = isShortage && value > 0;
      // 状態を色だけに頼らせない: 不足>0は「要補充 N件」＋警告アイコン、0は「基準内」、他KPIは「最新集計」。
      // これでアクセシブル名が状態ごとに別語になり（例「在庫不足 3 要補充 3件」/「在庫不足 0 基準内」）、
      // 色覚・AT 利用者にも不足の有無が文言で伝わる。
      const note = isShortage ? (isAlert ? `要補充 ${number.format(value)}件` : '基準内') : '最新集計';
      const alertIcon = isAlert ? '<svg class="kpi-alert-icon" aria-hidden="true"><use href="#icon-bell"></use></svg>' : '';
      return `<button type="button" class="kpi-card ${isAlert ? 'alert' : ''}" data-drill-kind="kpi" data-drill-index="${index}" data-tooltip-title="${escapeAttribute(row.label)}" data-tooltip-detail="${escapeAttribute(`${number.format(value)} / クリックして内訳を表示`)}"><span class="kpi-label">${escapeHtml(row.label)}</span><strong>${number.format(value)}</strong><span class="kpi-footer"><small>${alertIcon}${escapeHtml(note)}</small><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></span></button>`;
    }).join('');

    const itemStocks = filterDashboardRows(rows.filter((row) => row.record_type === 'ITEM_STOCK').sort((a, b) => Number(b.metric_value) - Number(a.metric_value)));
    state.dashboardDrilldowns.item = itemStocks;
    renderDashboardPanel('item', itemStocks, 'item-chart', 'item-pager', dashboardEmpty(emptyHtml('分析データがありません。')), barRowHtml(itemStocks, 'item'));

    const locations = filterDashboardRows(rows.filter((row) => row.record_type === 'LOCATION').sort((a, b) => Number(b.metric_value) - Number(a.metric_value)));
    state.dashboardDrilldowns.location = locations;
    renderDashboardPanel('location', locations, 'location-chart', 'location-pager', dashboardEmpty(emptyHtml('分析データがありません。')), barRowHtml(locations, 'location'));

    /**
     * 横棒1本のHTMLを組み立てるクロージャを返す。棒幅もツールチップの「最大比」も「全件」の最大値を
     * 基準にする（同じ分母＝絵と数字が一致）ため、ページ送りで表示中の並びが変わっても棒の長さと％が
     * 揺れない（比較の基準が固定される）。
     * @param {Array} all 整列済み全件（この種別の drilldown 対象）
     * @param {string} kind ドリルダウン種別（'item' | 'location'）
     * @return {function(object, number): string} (行, 絶対index) → 横棒HTML
     */
    function barRowHtml(all, kind) {
      // 棒幅の基準（最大値）を線形走査で求める。品目/ロケーションが数万件規模になり得る配布先では、
      // 配列を可変長スプレッドで最大値関数へ展開する書き方だと実行系の引数上限（V8で約6.5万・iOS
      // WebView はさらに小さい）を超えて RangeError を投げ、renderDashboard 全体が例外終了して
      // ダッシュボードが空になる。走査なら件数に依らず安全。
      let maximum = 1;
      for (const row of all) {
        const value = Number(row.metric_value || 0);
        if (value > maximum) maximum = value;
      }
      return (row, index) => {
        const value = Number(row.metric_value || 0);
        // ツールチップの比率は棒の内容（value/最大値）と同じ分母にする。合計基準の「構成比」を最大値
        // 正規化の棒に添えると、ほぼ満杯の棒に小さな％が並び絵と数字が食い違う（INV-021）。棒長＝最大比％。
        const maxShare = maximum > 0 ? value / maximum * 100 : 0;
        return `<button type="button" class="bar-row chart-hit" data-drill-kind="${kind}" data-drill-index="${index}" data-tooltip-title="${escapeAttribute(row.label)}" data-tooltip-detail="${escapeAttribute(`現在庫 ${number.format(value)} / 最大比 ${number.format(maxShare)}%`)}"><span class="bar-label">${escapeHtml(row.label)}</span><span class="bar-track"><span style="width:${barPct(value, maximum)}%"></span></span><b>${number.format(value)}</b><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button>`;
      };
    }

    const trend = rows.filter((row) => row.record_type === 'TREND').sort((a, b) => String(a.date_key).localeCompare(String(b.date_key))).slice(-config.analytics.trendWindowDays);
    state.dashboardDrilldowns.trend = trend;
    // barRowHtml と同じ方針で、配列を可変長スプレッドで Math.max へ展開しない（大規模データで
    // 実行系の引数上限を超え RangeError になる反パターンを避ける）。reduce で1行ずつ畳み、各行は
    // 固定アリティの Math.max(max, 入, 出) に収める＝trend 件数に依らず安全（INV-043）。
    const trendMax = trend.reduce((max, row) => Math.max(max, Number(row.inbound_quantity || 0), Number(row.outbound_quantity || 0)), 1);
    elements['trend-chart'].innerHTML = trend.length ? trend.map((row, index) => `<button type="button" class="trend-column chart-hit" data-drill-kind="trend" data-drill-index="${index}" aria-label="${escapeAttribute(`${formatDisplayDate(row.date_key)} 入庫 ${number.format(Number(row.inbound_quantity || 0))} 出庫 ${number.format(Number(row.outbound_quantity || 0))}`)}" data-tooltip-title="${escapeAttribute(formatDisplayDate(row.date_key))}" data-tooltip-detail="${escapeAttribute(`入庫 ${number.format(Number(row.inbound_quantity || 0))} / 出庫 ${number.format(Number(row.outbound_quantity || 0))}`)}"><span class="trend-bars"><span style="height:${barPct(row.inbound_quantity, trendMax)}%"></span><span class="out" style="height:${barPct(row.outbound_quantity, trendMax)}%"></span></span><small>${escapeHtml(formatShortDate(row.date_key))}</small></button>`).join('') : emptyHtml(`直近${config.analytics.trendWindowDays}日間の取引がありません。`);

    const shortages = filterDashboardRows(rows.filter((row) => row.record_type === 'SHORTAGE').sort((a, b) => Number(b.shortage_quantity || 0) - Number(a.shortage_quantity || 0)));
    state.dashboardDrilldowns.shortage = shortages;
    renderDashboardPanel('shortage', shortages, 'shortage-list', 'shortage-pager', dashboardEmpty('<div class="empty-state">在庫不足はありません。</div>'), (row, index) =>
      `<button type="button" class="shortage-row" data-drill-kind="shortage" data-drill-index="${index}" data-tooltip-title="${escapeAttribute(row.item_name || row.item_code)}" data-tooltip-detail="${escapeAttribute(`${row.location_name || row.location_code} / 現在 ${number.format(Number(row.quantity || row.current_quantity || 0))} / 基準 ${number.format(Number(row.minimum_quantity || 0))}`)}"><span><strong>${escapeHtml(row.item_name || row.item_code)}</strong><small>${escapeHtml(row.location_name || row.location_code)} / 現在 ${number.format(Number(row.quantity || row.current_quantity || 0))}</small></span><span class="shortage-qty">-${number.format(Number(row.shortage_quantity || 0))}<small>不足</small></span><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button>`);

    const dormant = filterDashboardRows(rows.filter((row) => row.record_type === 'DORMANT').sort((a, b) => Number(b.age_days || 0) - Number(a.age_days || 0)));
    state.dashboardDrilldowns.dormant = dormant;
    renderDashboardPanel('dormant', dormant, 'dormant-list', 'dormant-pager', dashboardEmpty(`<div class="empty-state">${config.analytics.dormantThresholdDays}日超の滞留在庫はありません。</div>`), (row, index) =>
      `<button type="button" class="dormant-row" data-drill-kind="dormant" data-drill-index="${index}" data-tooltip-title="${escapeAttribute(row.item_name || row.item_code)}" data-tooltip-detail="${escapeAttribute(`${row.location_name || row.location_code} / 現在庫 ${number.format(Number(row.quantity || 0))} / ${number.format(Number(row.age_days || 0))}日取引なし`)}"><span><strong>${escapeHtml(row.item_name || row.item_code)}</strong><small>${escapeHtml(row.location_name || row.location_code)} / ${number.format(Number(row.quantity || 0))}</small></span><span><strong>${number.format(Number(row.age_days || 0))}日</strong><small>取引なし</small></span><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button>`);

    renderAiNotes(rows);
    // 描画直後にカード高さを揃える（レイアウト確定後の1フレームで計測するためスケジュールする）。
    scheduleDashboardEqualize();
  }

  /**
   * ダッシュボード各行のカード高さを「その行で最も低いカード」に揃える。
   *
   * 高いカードは中身(.dash-scroll)だけが内部縦スクロールになり、見出し・凡例・ページャは
   * スクロール枠の外に固定表示される（改ページボタンは常に見える）。低いカードを基準にするため、
   * 揃えても低いカード下に余白が残らない（高い方へ合わせる従来方式で生じた空白を解消する狙い）。
   *
   * カードが横に並びきらず折り返す狭い画面では、視覚行(offsetTop)ごとに扱い、単独のカードは
   * 揃える相手がいないので自然高のまま（無用な内部スクロールを出さない）にする。CSS の
   * `.dashboard-row > .panel { min-height }` が、空表示などで極端に低いカードによる行の潰れを防ぐ床。
   */
  function equalizeDashboardRows() {
    const container = document.getElementById('view-dashboard');
    // 非表示ビュー（display:none）では offsetHeight が 0 になり計測できないので、表示中だけ揃える。
    if (!container || !container.classList.contains('active')) return;
    container.querySelectorAll('.dashboard-row').forEach((row) => {
      const cards = Array.prototype.filter.call(row.children, (el) => el.classList && el.classList.contains('panel'));
      if (!cards.length) return;
      // まず明示高さを外して自然高へ戻す（前回の揃え結果を持ち越さず、今の中身で測り直す）。
      cards.forEach((card) => { card.style.height = ''; });
      // offsetTop が同じカードは同じ視覚行（横並び）。折り返した行は別グループになる。
      const lines = new Map();
      cards.forEach((card) => {
        const key = Math.round(card.offsetTop);
        if (!lines.has(key)) lines.set(key, []);
        lines.get(key).push(card);
      });
      lines.forEach((group) => {
        if (group.length < 2) return; // 単独カードは自然高のまま（揃える相手がいない）
        let min = Infinity;
        group.forEach((card) => { if (card.offsetHeight < min) min = card.offsetHeight; });
        if (!(min > 0) || !Number.isFinite(min)) return;
        group.forEach((card) => { card.style.height = `${min}px`; });
      });
    });
  }

  /**
   * カード高さ揃えを次の描画フレームで1回だけ実行するスケジューラ。
   * 連続呼び出し（再描画＋リサイズが重なる等）を1フレームに集約し、計測のちらつきを防ぐ。
   */
  function scheduleDashboardEqualize() {
    if (state.dashboardEqualizeFrame !== null) return;
    const requestFrame = global.requestAnimationFrame || ((callback) => global.setTimeout(callback, 0));
    state.dashboardEqualizeFrame = requestFrame(() => {
      state.dashboardEqualizeFrame = null;
      equalizeDashboardRows();
    });
  }

  /**
   * ダッシュボードの一覧パネル（横棒・不足・滞留）を1ページ分だけ描画し、対応するページャを更新する。
   * 縦に伸び続けないよう1画面の件数を config.ui.dashboardPanelPageSize で区切るのが狙い。
   *
   * ドリルダウンは全件配列（state.dashboardDrilldowns[kind]）への「絶対index」で照合するため、
   * 行HTMLには page.start + offset（ページ内位置ではなく全体位置）を渡す。これによりページを
   * 送っても、クリックした行と開く明細がずれない。
   *
   * @param {string} kind ドリルダウン種別＝ページ状態キー（'item' | 'location' | 'shortage' | 'dormant'）
   * @param {Array<object>} all 整列済みの全件（drilldown 照合の対象そのもの）
   * @param {string} chartId 行を流し込む要素ID
   * @param {string} pagerId ページャの要素ID
   * @param {string} emptyMarkup 0件時に表示するHTML
   * @param {function(object, number): string} rowHtml (行, 絶対index) を受け取り行HTMLを返す
   */
  function renderDashboardPanel(kind, all, chartId, pagerId, emptyMarkup, rowHtml) {
    if (!all.length) {
      elements[chartId].innerHTML = emptyMarkup;
      state.dashboardPages[kind] = 0; // 空になったらページ位置も先頭へ戻す（次にデータが来ても先頭表示）。
      renderPager(pagerId, kind, null);
      return;
    }
    const page = paginate(all, state.dashboardPages[kind], config.ui.dashboardPanelPageSize);
    state.dashboardPages[kind] = page.safePage; // 範囲外要求は safePage に丸められるので採用する。
    elements[chartId].innerHTML = page.slice.map((row, offset) => rowHtml(row, page.start + offset)).join('');
    renderPager(pagerId, kind, page);
  }

  /**
   * ダッシュボード右下の「AI在庫コメント」パネルを描画する。
   *
   * AI_NOTE 行は品目×ロケーション単位で1件ずつ生成されるため、同じ品目が多拠点で不足していると
   * 似た要約がパネルを埋め、「どの記録の話か」が伝わりにくい。そこでパネルでは品目ごとに1枚へ束ね、
   * 品目内で最も注意すべき拠点（不足→在庫の少ない順）を代表に選び、他拠点は件数だけ添える。
   * 全件（拠点別）は各明細のドリルダウン（aiNoteSection）で確認できる。
   *
   * @param {Array<object>} rows ダッシュボードDataSetの全行（record_type で種別を識別）
   */
  function renderAiNotes(rows) {
    if (!elements['ai-note-list']) return;
    const notes = (rows || []).filter((row) => row.record_type === 'AI_NOTE' && String(row.ai_summary || '').trim());
    // ドリルダウン明細から O(1) で引けるよう item_code×location_code をキーに畳む（明細は拠点別に出す）。
    const map = {};
    notes.forEach((row) => { map[aiNoteKey(row.item_code, row.location_code)] = row; });
    state.aiNotes = map;
    if (!notes.length) {
      elements['ai-note-list'].innerHTML = '<div class="empty-state">AIコメントは分析DataSetの更新後に表示されます。</div>';
      return;
    }
    // 品目コード（無ければ品目名）でグルーピングし、要約の重複を品目単位で解消する。
    const byItem = new Map();
    notes.forEach((row) => {
      const itemKey = String(row.item_code || row.item_name || '').trim().toUpperCase();
      const group = byItem.get(itemKey);
      if (group) group.push(row); else byItem.set(itemKey, [row]);
    });
    // 要注意度の並び：不足を上へ、その後は在庫の少ない順。代表選び・パネル整列の両方で共用する。
    const worstFirst = (a, b) => {
      const shortageDelta = Number(isShortageRow(b)) - Number(isShortageRow(a));
      if (shortageDelta !== 0) return shortageDelta;
      return Number(a.quantity || 0) - Number(b.quantity || 0);
    };
    // 品目ごとに代表ノート1件と「残り拠点数」を求め、代表同士を要注意度で並べる。
    const representatives = [...byItem.values()].map((group) => {
      const sorted = [...group].sort(worstFirst);
      return {note: sorted[0], extra: sorted.length - 1};
    }).sort((a, b) => worstFirst(a.note, b.note));
    // パネルは要点だけを見せ、残りは各明細のドリルダウンで確認できる旨を控えめに添える。
    // 表示件数は config に集約し、他パネル（3列2段）と段の高さが揃う値を1か所で管理する。
    const VISIBLE = config.ui.aiNoteCardLimit;
    const shown = representatives.slice(0, VISIBLE);
    // 代表カードに「ほかN拠点」を出すため、代表ノートのキー→残り拠点数を引く辞書を作る。
    const extraByKey = {};
    shown.forEach(({note, extra}) => { if (extra > 0) extraByKey[aiNoteKey(note.item_code, note.location_code)] = extra; });
    const moreItems = representatives.length - shown.length;
    const moreNote = moreItems > 0 ? `<p class="ai-note-more">ほか${number.format(moreItems)}品目は各明細で確認できます。</p>` : '';
    elements['ai-note-list'].innerHTML = aiNoteCards(shown.map((entry) => entry.note), extraByKey) + moreNote;
  }

  /** AI_NOTE 照合キー。前後空白と大小文字の揺れを吸収して item_code×location_code を1本の文字列にする。 */
  function aiNoteKey(itemCode, locationCode) {
    return `${String(itemCode || '').trim().toUpperCase()}::${String(locationCode || '').trim().toUpperCase()}`;
  }

  /** is_shortage を真偽へ正規化する（DataSetは boolean と 'true' 文字列が混在しうる）。集計（domo-access）
   *  と同一判定にするため共有定義へ委譲する（バイト重複＝ドリフトの罠を塞ぐ・INV-041）。 */
  function isShortageRow(row) {
    return dataApi.isShortage(row);
  }

  /**
   * AI_NOTE 行の配列を、落ち着いた青系のコメントカード群のHTMLへ整形する。
   * 各カードは「品目名＋品目コード」の見出しと、「ロケーション名（コード）」の所在行、
   * 生成AIの要約本文を持ち、どの記録（品目×ロケーション）の要約かを明確にする。
   *
   * @param {Array<object>} notes ai_summary を持つ AI_NOTE 行
   * @param {Object<string, number>} [extraByKey] 代表カードに添える「残り拠点数」。
   *   aiNoteKey(item, location) → 件数。パネルの品目集約でのみ渡し、明細では省略する。
   * @return {string} コメント一覧のHTML
   */
  function aiNoteCards(notes, extraByKey) {
    return `<ul class="ai-note-cards">${notes.map((row) => {
      const item = row.item_name || row.item_code || '品目';
      const itemCode = String(row.item_code || '').trim();
      const place = row.location_name || row.location_code || '';
      const placeCode = String(row.location_code || '').trim();
      const shortage = isShortageRow(row);
      const extra = extraByKey ? Number(extraByKey[aiNoteKey(row.item_code, row.location_code)] || 0) : 0;
      // 見出しに品目コードも併記し、似た品目名でもどの記録か取り違えないようにする。
      const codeTag = itemCode ? `<small class="ai-note-code">${escapeHtml(itemCode)}</small>` : '';
      // 所在行は「名称（コード）」で明示。コードが名称と重複する場合はコードを省いて冗長にしない。
      const placeLabel = place
        ? `${escapeHtml(place)}${placeCode && placeCode !== place ? `（${escapeHtml(placeCode)}）` : ''}`
        : '拠点未設定';
      // 同一品目が他拠点にもある場合だけ「ほかN拠点」を添える（詳細は各明細のドリルダウンで）。
      const extraTag = extra > 0 ? `<span class="ai-note-extra">ほか${number.format(extra)}拠点</span>` : '';
      return `<li class="ai-note${shortage ? ' is-shortage' : ''}"><div class="ai-note-head"><span class="ai-note-badge">AI</span><strong>${escapeHtml(item)}</strong>${codeTag}</div><p class="ai-note-loc">${placeLabel}${extraTag}</p><p class="ai-note-body">${escapeHtml(String(row.ai_summary || '').trim())}</p></li>`;
    }).join('')}</ul>`;
  }

  /**
   * 指定した在庫（品目×ロケーションの集合）に対応するAIコメントを、明細用のセクションHTMLで返す。
   * 該当コメントが1件も無ければ空文字を返し、明細に余計な見出しを出さない。
   *
   * @param {Array<{item_code?:string,location_code?:string}>} balances 明細対象の在庫行
   * @return {string} detailSection のHTML、または ''
   */
  function aiNoteSection(balances) {
    const seen = new Set();
    const notes = [];
    (balances || []).forEach((row) => {
      const key = aiNoteKey(row.item_code, row.location_code);
      if (seen.has(key)) return;
      const note = state.aiNotes[key];
      if (note) { seen.add(key); notes.push(note); }
    });
    return notes.length ? detailSection('AI在庫コメント', aiNoteCards(notes)) : '';
  }

  // タブ列でのキーボード操作。左右で隣のタブへ、Home/Endで端へ移動し、移動先を即座に表示する
  // （WAI-ARIA Tabs パターン）。hidden なタブ（非管理者に隠れる品目等）は対象から除外する。
  function handleRecordTabKey(event) {
    const key = event.key;
    if (key !== 'ArrowLeft' && key !== 'ArrowRight' && key !== 'Home' && key !== 'End') return;
    const tabs = Array.prototype.filter.call(document.querySelectorAll('.record-tab'), (t) => !t.hidden);
    const current = tabs.indexOf(document.activeElement);
    if (current === -1) return;
    event.preventDefault();
    let next = current;
    if (key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
    else if (key === 'ArrowRight') next = (current + 1) % tabs.length;
    else if (key === 'Home') next = 0;
    else if (key === 'End') next = tabs.length - 1;
    const target = tabs[next];
    setRecordTab(target.dataset.record);
    target.focus();
  }

  // 履歴／マスタの2つのタブパネルは「現在のタブ」だけが表示管理者。
  // updateUser の admin-only 一括表示は record-panel-master（admin-only 付き）も
  // 対象にしてしまい、取引タブのまま両パネルが縦に並ぶ不具合が出るため、
  // 表示切替をこの関数へ集約し、タブ状態で必ず上書きする。
  function syncRecordPanels() {
    const isMaster = MASTER_TABS[state.recordTab] === true;
    if (elements['record-panel-history']) elements['record-panel-history'].hidden = isMaster;
    if (elements['record-panel-master']) elements['record-panel-master'].hidden = !isMaster;
  }

  // 統合タブのクリック入口。取引・通知は履歴パネル、品目・ロケーション・基準在庫はマスタパネルへ
  // 切り替える。マスタ系は管理者かつPCのみ許可し、権限がなければ取引履歴へフォールバックする。
  function setRecordTab(tab) {
    cancelConfirmation();
    const isMaster = MASTER_TABS[tab] === true;
    if (isMaster && (!state.user.isAdmin || isMobileHostActive())) {
      setRecordTab('transactions'); // 'transactions' はマスタ系でないため再帰しない
      return;
    }
    state.recordTab = tab;
    document.querySelectorAll('.record-tab').forEach((button) => {
      const selected = button.dataset.record === tab;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
      // ロービングtabindex: Tabキーではアクティブなタブ1つだけを辿り、タブ間は矢印キーで移動する
      // （WAI-ARIA Tabs パターン）。非アクティブなタブは -1 でタブ順から外す。
      button.tabIndex = selected ? 0 : -1;
      // 表示中パネルを指すのはアクティブなタブだけ。多対一（5タブ→2パネル）なので他タブからは外す。
      if (!selected) button.removeAttribute('aria-controls');
    });
    // パネルの表示切替。CSSの display 指定が [hidden] を打ち消さないよう app.css 側で対を定義済み。
    syncRecordPanels();
    // タブ⇄パネルの関連付け。アクティブタブに aria-controls、表示中パネルに aria-labelledby を張り、
    // 支援技術へ「今どのタブがどのパネルを開いているか」を伝える。
    const activeTab = document.querySelector(`.record-tab[data-record="${tab}"]`);
    const activePanel = isMaster ? elements['record-panel-master'] : elements['record-panel-history'];
    if (activeTab && activePanel && activeTab.id) {
      activeTab.setAttribute('aria-controls', activePanel.id);
      activePanel.setAttribute('aria-labelledby', activeTab.id);
    }
    // 検索・種別フィルタは履歴一覧専用。マスタ表示時は隠す。
    if (elements['history-filter']) elements['history-filter'].hidden = isMaster;
    if (isMaster) {
      setMasterTab(tab);
    } else {
      state.historyMode = tab;
      state.historyPage = 0;
      renderHistory();
    }
  }

  function renderHistory() {
    // 一覧を作り直すと行インデックスと選択状態がずれるため、詳細ペインを初期状態へ戻す。
    // ドリルダウン遷移では switchView→renderHistory の後に fillDetailPane が上書きする。
    resetDetailPane();
    const query = normalizedSearch(elements['history-search'].value);
    const type = elements['history-type'].value;
    // 表のアクセシブル名（INV-034）。1画面に複数の表が並ぶため、SR の表一覧で取引/通知を区別できるよう
    // モードに応じた隠しキャプションを与える。
    if (elements['history-caption']) elements['history-caption'].textContent = state.historyMode === 'alerts' ? '通知履歴' : '取引履歴';
    let rows;
    let renderRow;
    let emptyColspan;
    let emptyMessage;
    if (state.historyMode === 'alerts') {
      elements['history-type-filter'].hidden = true;  // INV-040: 安定 id で参照（closest は不要）
      elements['history-head'].innerHTML = '<tr><th scope="col">日時</th><th scope="col">イベント</th><th scope="col">品目</th><th scope="col">ロケーション</th><th scope="col">在庫 / 基準</th><th scope="col">通知</th><th scope="col">件名</th><th scope="col" aria-label="詳細"></th></tr>';
      rows = [...state.data.alerts].filter((row) => !query || `${row.item_code || ''} ${row.item_name || ''} ${row.location_code || ''} ${row.location_name || ''} ${row.notification_subject || ''} ${row.created_at || ''} ${formatDate(row.created_at)} ${formatDisplayDate(row.created_at)} ${row.alert_id || ''}`.toLocaleLowerCase('ja-JP').includes(query)).sort(sortNewest('created_at'));
      renderRow = (row, index) => `<tr class="drilldown-row" data-history-index="${index}"><td>${formatDate(row.created_at)}</td><td><span class="status-pill ${row.event_type === 'RECOVERY' ? 'recovery' : 'shortage'}">${escapeHtml(row.event_type === 'RECOVERY' ? '回復' : '不足')}</span></td><td>${escapeHtml(row.item_name || row.item_code)}</td><td>${escapeHtml(row.location_name || row.location_code)}</td><td>${number.format(Number(row.current_quantity || 0))} / ${number.format(Number(row.minimum_quantity || 0))}</td><td><span class="status-pill ${statusClass(row.notification_status)}">${escapeHtml(statusLabel(row.notification_status))}</span></td><td>${escapeHtml(row.notification_subject || '—')}</td><td class="drill-cell"><button type="button" class="drill-btn" aria-label="${escapeAttribute(row.item_name || row.item_code)}の明細を開く"><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button></td></tr>`;
      emptyColspan = 8;
      emptyMessage = '通知履歴がありません。';
    } else {
      elements['history-type-filter'].hidden = false;
      elements['history-head'].innerHTML = '<tr><th scope="col">日時</th><th scope="col">種別</th><th scope="col">品目</th><th scope="col">ロケーション</th><th scope="col">数量</th><th scope="col">残高</th><th scope="col">担当者</th><th scope="col">理由</th><th scope="col" aria-label="詳細"></th></tr>';
      rows = [...state.data.transactions].filter((row) => (!type || row.transaction_type === type) && (!query || `${row.item_code || ''} ${row.item_name || ''} ${row.location_code || ''} ${row.location_name || ''} ${row.operator_name || ''} ${row.reason || ''} ${row.occurred_at || ''} ${formatDate(row.occurred_at)} ${formatDisplayDate(row.occurred_at)} ${row.transaction_id || ''} ${row.request_id || ''}`.toLocaleLowerCase('ja-JP').includes(query))).sort(sortNewest('occurred_at'));
      renderRow = (row, index) => {
        const cls = row.transaction_type === 'OUT' ? 'pending' : 'sent';
        return `<tr class="drilldown-row" data-history-index="${index}"><td>${formatDate(row.occurred_at)}</td><td><span class="status-pill ${cls}">${escapeHtml(transactionLabel(row.transaction_type))}</span></td><td>${escapeHtml(row.item_name || row.item_code)}</td><td>${escapeHtml(row.location_name || row.location_code)}</td><td>${number.format(Number(row.quantity || 0))}</td><td>${number.format(Number(row.balance_after || 0))}</td><td>${escapeHtml(row.operator_name || row.operator_user_id || '—')}</td><td>${escapeHtml(row.reason || '—')}</td><td class="drill-cell"><button type="button" class="drill-btn" aria-label="${escapeAttribute(row.item_name || row.item_code)}の明細を開く"><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button></td></tr>`;
      };
      emptyColspan = 9;
      emptyMessage = '取引履歴がありません。';
    }
    // 行選択（data-history-index）は絞り込み後の全件配列 historyVisibleRows を指す。ページ送りで
    // 表示スライスが変わっても index は絶対位置のままなので、明細ドリルダウンが崩れない。
    state.historyVisibleRows = rows;
    elements['history-result-count'].textContent = `${number.format(rows.length)}件`;
    const page = paginate(rows, state.historyPage);
    state.historyPage = page.safePage;
    elements['history-body'].innerHTML = rows.length
      ? page.slice.map((row, offset) => renderRow(row, page.start + offset)).join('')
      : tableEmpty(emptyColspan, emptyMessage);
    // 履歴の明細一覧は1ページに収まっても枠を残す（alwaysShow）。件数が少ないときにページャ領域が
    // 真っ白になって不具合に見えるのを防ぎ、前後ボタンは無効化して操作位置を安定させる。
    renderPager('history-pager', 'history', page, {alwaysShow: true});
  }

  /**
   * 配列を1ページ分へ切り出し、ページ送りに必要な指標をまとめて返す。
   * 要求ページが範囲外でも安全側に丸め（0〜最終ページ）、呼び出し側は戻り値の safePage を採用する。
   *
   * @param {Array} rows 全件（絞り込み・整列済み）
   * @param {number} requestedPage 表示したいページ（0始まり）
   * @param {number} [pageSize=PAGE_SIZE] 1ページ件数。履歴・マスタは既定、ダッシュボード各パネルは小さめ値を渡す。
   * @return {{slice: Array, start: number, safePage: number, pageCount: number, total: number, pageSize: number}}
   */
  function paginate(rows, requestedPage, pageSize = PAGE_SIZE) {
    const total = rows.length;
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(0, Number(requestedPage) || 0), pageCount - 1);
    const start = safePage * pageSize;
    return {slice: rows.slice(start, start + pageSize), start, safePage, pageCount, total, pageSize};
  }

  /**
   * ページ送りナビゲーションを描画する。
   *
   * 既定（ダッシュボードの小パネル）は全件が1ページに収まると枠ごと隠して段を詰める。
   * 履歴・管理の明細一覧は `options.alwaysShow` を真にして常に枠を出し、前後ボタンを無効化して
   * 「◯–◯ / 全N件（1/1ページ）」を表示する（件数が少なくても操作位置を安定させ、真っ白に見せない）。
   * レンジ表示は aria-live で読み上げる。
   *
   * @param {string} elementId 描画先コンテナの要素ID（history-pager / master-pager / item-pager など）
   * @param {string} scope ページ状態の識別子（'history' | 'master' | 'item' | 'location' | 'shortage' | 'dormant'）。クリック委譲で参照する。
   * @param {?object} page paginate() の戻り値。null のときは（データ行が無いパネルとして）非表示にする。
   * @param {{alwaysShow?: boolean}} [options] alwaysShow=true で1ページに収まっても枠を残し、前後ボタンを無効化して表示する。
   */
  function renderPager(elementId, scope, page, options) {
    const container = elements[elementId];
    if (!container) return;
    const alwaysShow = !!(options && options.alwaysShow);
    // page===null は「パネルにデータ行が無い」明示ケース（ダッシュボードの空パネル）なので必ず隠す。
    // それ以外で1ページに収まるときは、既定では隠すが alwaysShow のときは枠を残す（真っ白回避）。
    if (!page || (page.total <= page.pageSize && !alwaysShow)) {
      container.hidden = true;
      container.innerHTML = '';
      return;
    }
    const from = page.total ? page.start + 1 : 0;
    const to = page.start + page.slice.length;
    const statusText = `${number.format(from)}–${number.format(to)} / 全${number.format(page.total)}件（${page.safePage + 1}/${page.pageCount}ページ）`;
    // aria-live のステータス節点は作り直さずテキストだけ差し替える。innerHTML ごと置換すると
    // ライブリージョンが毎回 DOM から消えて再生成され、スクリーンリーダーがページ移動を読み上げない。
    // scope は要素ごとに固定なので、初回（または未構築時）だけ骨格を組み、以後はボタンの無効状態と
    // 件数テキストだけを更新する。
    if (container.dataset.pagerScope !== scope || !container.querySelector('.pager-status')) {
      container.dataset.pagerScope = scope;
      container.innerHTML = `<button type="button" class="pager-btn" data-page-scope="${scope}" data-page-dir="-1" aria-label="前のページ">前へ</button><span class="pager-status" aria-live="polite">${escapeHtml(statusText)}</span><button type="button" class="pager-btn" data-page-scope="${scope}" data-page-dir="1" aria-label="次のページ">次へ</button>`;
    } else {
      container.querySelector('.pager-status').textContent = statusText;
    }
    const buttons = container.querySelectorAll('.pager-btn');
    buttons[0].disabled = page.safePage <= 0;
    buttons[1].disabled = page.safePage >= page.pageCount - 1;
    container.hidden = false;
  }

  /**
   * ページ送りボタンのクリックを処理する（前後コンテナへ委譲）。押下方向へ状態を進めて再描画し、
   * 押したボタンが端に達して無効化された場合は反対側のボタンへフォーカスを移してキーボード操作を継続させる。
   */
  function handlePagerClick(event) {
    const button = event.target.closest('[data-page-dir]');
    if (!button || button.disabled) return;
    const scope = button.dataset.pageScope;
    const dir = Number(button.dataset.pageDir);
    if (scope === 'history') { state.historyPage += dir; renderHistory(); }
    else if (scope === 'master') { state.masterPage += dir; renderMasters(); }
    // ダッシュボードの4パネルは共通の再描画で1ページ進める（描画側が safePage で範囲を丸める）。
    else if (Object.prototype.hasOwnProperty.call(state.dashboardPages, scope)) { state.dashboardPages[scope] += dir; renderDashboard(); }
    else return;
    // 再描画後に同方向ボタンが無効なら、反対方向ボタンへフォーカスを退避してタブ位置を失わせない。
    const containerId = PAGER_CONTAINER_BY_SCOPE[scope];
    const container = elements[containerId];
    if (!container || container.hidden) return;
    const same = container.querySelector(`[data-page-dir="${dir}"]`);
    const opposite = container.querySelector(`[data-page-dir="${-dir}"]`);
    if (same && !same.disabled) same.focus();
    else if (opposite && !opposite.disabled) opposite.focus();
  }

  function handleDashboardDrilldown(event) {
    const target = event.target.closest('[data-drill-kind]');
    if (!target) return;
    const kind = target.dataset.drillKind;
    const index = Number(target.dataset.drillIndex);
    const row = state.dashboardDrilldowns[kind]?.[index];
    if (!row) return;
    hideChartTooltip();
    if (kind === 'kpi') openKpiDetail(row);
    else if (kind === 'item') openItemDetail(row);
    else if (kind === 'location') openLocationDetail(row);
    else if (kind === 'trend') openTrendDetail(row);
    else if (kind === 'shortage') openShortageDetail(row);
    else if (kind === 'dormant') openDormantDetail(row);
  }

  function handleRecentDrilldown(event) {
    const target = event.target.closest('[data-recent-index]');
    if (!target) return;
    const row = state.recentRows[Number(target.dataset.recentIndex)];
    if (row) openTransactionDetail(row);
  }

  function handleHistoryDrilldown(event) {
    const target = event.target.closest('[data-history-index]');
    if (!target) return;
    openHistoryRow(Number(target.dataset.historyIndex));
  }

  function openHistoryRow(index) {
    const row = state.historyVisibleRows[index];
    if (!row) return;
    // マスタ（一覧）で選択行を強調し、詳細（ペイン）を同一ビュー内で差し替える。
    state.selectedHistoryIndex = index;
    highlightSelectedHistoryRow();
    if (state.historyMode === 'alerts') openAlertDetail(row);
    else openTransactionDetail(row);
  }

  /** 選択中の履歴行だけに is-selected を付け、他行から外す（マスタ側のカレント表示）。 */
  function highlightSelectedHistoryRow() {
    elements['history-body'].querySelectorAll('.drilldown-row').forEach((node) => {
      const selected = Number(node.dataset.historyIndex) === state.selectedHistoryIndex;
      node.classList.toggle('is-selected', selected);
      // 行は素の <tr>（role=row）。集合内のカレント項目は aria-current で表す（aria-selected は
      // listbox/grid 専用で tr には無効）。未選択時は属性ごと外す。
      if (selected) node.setAttribute('aria-current', 'true');
      else node.removeAttribute('aria-current');
    });
  }

  function handleChartPointerOver(event) {
    if (event.pointerType === 'touch') return;
    const target = event.target.closest('[data-tooltip-title]');
    if (!target || target.contains(event.relatedTarget)) return;
    showChartTooltip(target, event);
  }

  function handleChartPointerMove(event) {
    if (elements['chart-tooltip'].hidden || event.pointerType === 'touch') return;
    const target = event.target.closest('[data-tooltip-title]');
    if (target) positionChartTooltip(target, event);
  }

  function handleChartPointerOut(event) {
    const target = event.target.closest('[data-tooltip-title]');
    if (target && !target.contains(event.relatedTarget)) hideChartTooltip();
  }

  function handleChartFocus(event) {
    const target = event.target.closest('[data-tooltip-title]');
    if (target) showChartTooltip(target);
  }

  function showChartTooltip(target, event) {
    const title = target.dataset.tooltipTitle || '';
    const detail = target.dataset.tooltipDetail || '';
    elements['chart-tooltip'].innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span><small>クリックして明細を表示</small>`;
    elements['chart-tooltip'].hidden = false;
    positionChartTooltip(target, event);
  }

  function positionChartTooltip(target, event) {
    const tooltip = elements['chart-tooltip'];
    const viewportWidth = global.visualViewport?.width || global.innerWidth;
    const viewportHeight = global.visualViewport?.height || global.innerHeight;
    const anchorRect = target.getBoundingClientRect();
    const pointerX = event && Number.isFinite(event.clientX) ? event.clientX : anchorRect.left + anchorRect.width / 2;
    const pointerY = event && Number.isFinite(event.clientY) ? event.clientY : anchorRect.top;
    const left = Math.max(8, Math.min(pointerX + 14, viewportWidth - tooltip.offsetWidth - 8));
    const preferredTop = pointerY + 16;
    const top = preferredTop + tooltip.offsetHeight < viewportHeight - 8 ? preferredTop : Math.max(8, pointerY - tooltip.offsetHeight - 14);
    tooltip.style.left = `${Math.round(left)}px`;
    tooltip.style.top = `${Math.round(top)}px`;
  }

  function hideChartTooltip() {
    elements['chart-tooltip'].hidden = true;
  }

  function openKpiDetail(row) {
    const key = row.metric_key;
    if (key === 'TODAY_IN_COUNT' || key === 'TODAY_OUT_COUNT') {
      const type = key === 'TODAY_IN_COUNT' ? 'IN' : 'OUT';
      const latestTrend = state.dashboardDrilldowns.trend[state.dashboardDrilldowns.trend.length - 1];
      const dateKey = latestTrend?.date_key || new Date().toISOString().slice(0, 10);
      const transactions = activeTransactions().filter((item) => item.transaction_type === type && String(item.occurred_at || '').slice(0, 10) === dateKey);
      openDetail({
        eyebrow: '本日の取引',
        title: row.label,
        subtitle: `${formatDisplayDate(dateKey)} / ${number.format(transactions.length)}件`,
        content: detailStats([['件数', transactions.length], ['数量合計', transactions.reduce((sum, item) => sum + Number(item.quantity || 0), 0)]]) + detailSection('取引明細', renderDetailTransactions(transactions)),
        historyFilter: {mode: 'transactions', query: dateKey, type}
      });
      return;
    }

    if (key === 'SHORTAGE_COUNT') {
      // KPI カードの数値は検索クエリの影響を受けない全体集計(metric_value)なので、その内訳も
      // 検索で絞り込まれた state.dashboardDrilldowns.shortage ではなく全 SHORTAGE 行から導出する。
      // こうしないと、カード面「在庫不足 N」を押したのに明細が検索一致分だけになり件数が食い違う。
      const shortages = (state.dashboardRows || [])
        .filter((entry) => entry.record_type === 'SHORTAGE')
        .sort((a, b) => Number(b.shortage_quantity || 0) - Number(a.shortage_quantity || 0));
      openDetail({
        eyebrow: '要対応',
        title: row.label,
        subtitle: '基準在庫を下回る品目とロケーション',
        content: detailStats([['不足箇所', shortages.length], ['不足数量', shortages.reduce((sum, item) => sum + Number(item.shortage_quantity || 0), 0)]]) + aiNoteSection(shortages) + detailSection('不足一覧', detailTable(['品目', 'ロケーション', '現在', '基準', '不足'], shortages.map((item) => [item.item_name || item.item_code, item.location_name || item.location_code, number.format(Number(item.quantity || item.current_quantity || 0)), number.format(Number(item.minimum_quantity || 0)), number.format(Number(item.shortage_quantity || 0))]), '不足一覧')),
        historyFilter: {mode: 'alerts', query: '', type: ''}
      });
      return;
    }

    const balances = [...state.data.balances].sort((a, b) => Number(b.quantity || 0) - Number(a.quantity || 0));
    openDetail({
      eyebrow: '在庫サマリー',
      title: row.label,
      subtitle: key === 'ITEM_COUNT' ? '在庫がある品目の一覧' : '全ロケーションの現在庫',
      content: detailStats([['集計値', Number(row.metric_value || 0)], ['在庫明細', balances.length]]) + detailSection('現在庫上位', renderBalanceDetails(balances.slice(0, config.ui.topStockLimit))),
      historyFilter: {mode: 'transactions', query: '', type: ''}
    });
  }

  function openItemDetail(row) {
    const label = String(row.label || '');
    const balances = state.data.balances.filter((item) => item.item_name === label || item.item_code === label);
    const itemCode = balances[0]?.item_code || state.data.items.find((item) => item.item_name === label || item.item_code === label)?.item_code || '';
    // 同名で別コードの品目が複数あると、balances は名称一致で全件拾うのに取引を先頭コードだけで
    // 絞ると取引件数が過少になる。名称一致した全 balances のコード集合（＋マスタ解決コード）で拾う。
    const itemCodes = new Set(balances.map((item) => item.item_code).filter(Boolean));
    if (itemCode) itemCodes.add(itemCode);
    const transactions = activeTransactions().filter((item) => itemCodes.size ? itemCodes.has(item.item_code) : item.item_name === label).sort(sortNewest('occurred_at'));
    const total = balances.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    openDetail({
      eyebrow: '品目ドリルダウン',
      title: label || itemCode || '品目明細',
      subtitle: itemCode || '分析DataSetの集計名で照合',
      content: detailStats([['現在庫', total], ['ロケーション数', balances.length], ['取引件数', transactions.length]]) + aiNoteSection(balances) + detailSection('ロケーション別現在庫', renderBalanceDetails(balances)) + detailSection('直近の取引', renderDetailTransactions(transactions.slice(0, config.ui.detailTransactionLimit))),
      historyFilter: {mode: 'transactions', query: itemCode || label, type: ''}
    });
  }

  function openLocationDetail(row) {
    const label = String(row.label || '');
    const balances = state.data.balances.filter((item) => item.location_name === label || item.location_code === label);
    const locationCode = balances[0]?.location_code || state.data.locations.find((item) => item.location_name === label || item.location_code === label)?.location_code || '';
    // 同名で別コードのロケーションが複数あるケースに備え、名称一致した全 balances のコード集合
    // （＋マスタ解決コード）で取引を拾う（先頭コードだけで絞ると取引件数が過少になる）。
    const locationCodes = new Set(balances.map((item) => item.location_code).filter(Boolean));
    if (locationCode) locationCodes.add(locationCode);
    const transactions = activeTransactions().filter((item) => locationCodes.size ? locationCodes.has(item.location_code) : item.location_name === label).sort(sortNewest('occurred_at'));
    const total = balances.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    openDetail({
      eyebrow: 'ロケーションドリルダウン',
      title: label || locationCode || 'ロケーション明細',
      subtitle: locationCode || '分析DataSetの集計名で照合',
      content: detailStats([['現在庫', total], ['品目数', balances.length], ['取引件数', transactions.length]]) + aiNoteSection(balances) + detailSection('品目別現在庫', renderBalanceDetails(balances)) + detailSection('直近の取引', renderDetailTransactions(transactions.slice(0, config.ui.detailTransactionLimit))),
      historyFilter: {mode: 'transactions', query: locationCode || label, type: ''}
    });
  }

  function openTrendDetail(row) {
    const dateKey = String(row.date_key || '');
    const transactions = activeTransactions().filter((item) => String(item.occurred_at || '').slice(0, 10) === dateKey).sort(sortNewest('occurred_at'));
    openDetail({
      eyebrow: '日別ドリルダウン',
      title: formatDisplayDate(dateKey),
      subtitle: `${number.format(transactions.length)}件の取引`,
      content: detailStats([['入庫数量', Number(row.inbound_quantity || 0)], ['出庫数量', Number(row.outbound_quantity || 0)], ['取引件数', transactions.length]]) + detailSection('取引明細', renderDetailTransactions(transactions)),
      historyFilter: {mode: 'transactions', query: dateKey, type: ''}
    });
  }

  function openShortageDetail(row) {
    const transactions = relatedTransactions(row).sort(sortNewest('occurred_at'));
    openDetail({
      eyebrow: '不足明細',
      title: row.item_name || row.item_code || '在庫不足',
      subtitle: `${row.location_name || row.location_code || 'ロケーション未設定'} / 補充確認が必要`,
      content: detailStats([['現在庫', Number(row.quantity || row.current_quantity || 0)], ['基準在庫', Number(row.minimum_quantity || 0)], ['不足数量', Number(row.shortage_quantity || 0)]]) + aiNoteSection([row]) + detailSection('直近の取引', renderDetailTransactions(transactions.slice(0, config.ui.detailTransactionLimit))),
      historyFilter: {mode: 'transactions', query: row.item_code || row.item_name || '', type: ''}
    });
  }

  function openDormantDetail(row) {
    const transactions = relatedTransactions(row).sort(sortNewest('occurred_at'));
    openDetail({
      eyebrow: '滞留明細',
      title: row.item_name || row.item_code || '滞留在庫',
      subtitle: `${row.location_name || row.location_code || 'ロケーション未設定'} / ${number.format(Number(row.age_days || 0))}日取引なし`,
      content: detailStats([['現在庫', Number(row.quantity || 0)], ['経過日数', Number(row.age_days || 0)], ['取引件数', transactions.length]]) + aiNoteSection([row]) + detailSection('過去の取引', renderDetailTransactions(transactions.slice(0, config.ui.detailTransactionLimit))),
      historyFilter: {mode: 'transactions', query: row.item_code || row.item_name || '', type: ''}
    });
  }

  function openTransactionDetail(row) {
    const before = Number(row.balance_before || 0);
    const after = Number(row.balance_after || 0);
    const signed = Number(row.signed_quantity ?? (row.transaction_type === 'OUT' ? -Number(row.quantity || 0) : Number(row.quantity || 0)));
    openDetail({
      eyebrow: '取引明細',
      title: `${transactionLabel(row.transaction_type)} / ${row.item_name || row.item_code || '品目未設定'}`,
      subtitle: formatFullDate(row.occurred_at),
      // 取引明細の主役は「在庫がいくつからいくつへ動いたか」。KPI箱を並べず、登録前→登録後の
      // 流れと増減量を1本の帯（balanceFlow）で見せ、登録情報は細罫線だけの静かな並びにする。
      content: balanceFlow(before, after, signed, row.transaction_type)
        + detailSection('登録情報', detailDefinition([
          ['ロケーション', `${row.location_name || '—'} (${row.location_code || '—'})`],
          ['品目', `${row.item_name || '—'} (${row.item_code || '—'})`],
          ['担当者', row.operator_name || row.operator_user_id || '—'],
          ['理由・メモ', row.reason || '—'],
          ['登録元', sourceLabel(row.source)]
        ]))
        // 取引ID・リクエストIDは監査・照合用の参照値。本文に混ぜず、末尾へ控えめな等幅表記で添える。
        + detailMeta([
          ['取引ID', row.transaction_id || '—'],
          ['リクエストID', row.request_id || '—']
        ]),
      historyFilter: {mode: 'transactions', query: row.item_code || row.item_name || '', type: ''}
    });
  }

  function openAlertDetail(row) {
    openDetail({
      eyebrow: '通知明細',
      title: row.notification_subject || `${row.item_name || row.item_code || '品目'}の通知`,
      subtitle: formatFullDate(row.created_at),
      content: detailStats([['現在庫', Number(row.current_quantity || 0)], ['基準在庫', Number(row.minimum_quantity || 0)], ['不足数量', Number(row.shortage_quantity || 0)]])
        + detailSection('通知情報', detailDefinition([
          ['イベント', row.event_type === 'RECOVERY' ? '在庫回復' : '在庫不足'],
          ['品目', `${row.item_name || '—'} (${row.item_code || '—'})`],
          ['ロケーション', `${row.location_name || '—'} (${row.location_code || '—'})`],
          ['通知状態', statusLabel(row.notification_status)],
          ['本文', row.notification_body || '—'],
          ['エラー', row.error_message || '—']
        ]))
        // 通知IDも照合用の参照値。取引明細と同じく末尾へ控えめに添える。
        + detailMeta([['通知ID', row.alert_id || '—']]),
      historyFilter: {mode: 'alerts', query: row.item_code || row.item_name || '', type: ''}
    });
  }

  /**
   * ドリルダウン明細を表示する。表示先は現在ビューで分岐する。
   *
   * 履歴ビューでは一覧の右側の詳細ペイン（#detail-pane）を差し替えるだけで、検索条件やタブは動かさない。
   * ダッシュボード・入出庫では、右から滑り込むスライドイン・ドロワー（#context-detail）へ描き、履歴タブへは
   * 遷移しない。履歴条件があるときだけ「履歴で詳しく見る」導線を添えるが、遷移はユーザー操作に委ね強制しない。
   *
   * @param {{eyebrow?:string,title?:string,subtitle?:string,content?:string,historyFilter?:object}} options
   */
  function openDetail(options) {
    if (state.view === 'history') {
      // 履歴ビュー：選択行の明細だけを差し替える（一覧・検索条件・タブはそのまま保持）。
      fillDetailPane(options);
      return;
    }
    // 履歴以外（ダッシュボード／入出庫）：現在のメニュー内でインライン詳細を表示し、タブ遷移しない。
    fillContextDetail(options);
  }

  /** 詳細ペインの見出しと本文を差し替える。一覧の再描画は行わない。 */
  function fillDetailPane(options) {
    elements['detail-eyebrow'].textContent = options.eyebrow || 'DETAIL';
    elements['detail-title'].textContent = options.title || '明細';
    elements['detail-subtitle'].textContent = options.subtitle || '';
    elements['detail-content'].innerHTML = options.content || emptyHtml('表示できる明細がありません。');
    elements['detail-pane'].classList.add('has-detail');
    elements['detail-title'].focus({preventScroll: true});
    // 縦積みレイアウト（狭幅・スマホ）では詳細が一覧の下に来るため、そこまでスクロールする。
    if (global.matchMedia && global.matchMedia('(max-width: 980px)').matches) {
      elements['detail-pane'].scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }

  /** 一覧の選択解除に合わせ、詳細ペインを未選択のプレースホルダーへ戻す。 */
  function resetDetailPane() {
    state.selectedHistoryIndex = null;
    elements['detail-eyebrow'].textContent = 'DETAIL';
    elements['detail-title'].textContent = '明細';
    elements['detail-subtitle'].textContent = '一覧から選択';
    elements['detail-content'].innerHTML = '<div class="detail-placeholder">左の一覧から行を選ぶと、ここに明細が表示されます。</div>';
    elements['detail-pane'].classList.remove('has-detail');
  }

  /**
   * ダッシュボード・入出庫のドリルダウン明細を、右から滑り込むドロワーへ描く。
   * 履歴タブへは遷移しない。履歴条件があるときだけ「履歴で詳しく見る」導線を添える（任意遷移）。
   */
  function fillContextDetail(options) {
    if (!elements['context-detail']) return;
    elements['context-detail-eyebrow'].textContent = options.eyebrow || 'DETAIL';
    elements['context-detail-title'].textContent = options.title || '明細';
    elements['context-detail-subtitle'].textContent = options.subtitle || '';
    elements['context-detail-content'].innerHTML = options.content || emptyHtml('表示できる明細がありません。');
    // 任意の履歴遷移用に条件を保持。強制はせず、ユーザーがボタンを押したときだけ使う。
    state.contextDetailFilter = options.historyFilter || null;
    elements['context-detail-more'].hidden = !options.historyFilter;
    // 閉じたときにフォーカスを戻せるよう、開くきっかけになった要素（行・グラフ等）を控えておく。
    // ドロワーを開く前に取得する必要がある。非フォーカス要素なら復帰は自然に no-op になる。
    state.contextDetailOrigin = document.activeElement;
    openContextDrawer();
    // 面の内容は先頭から読ませたいので、ドロワー内スクロールを戻してから見出しへフォーカスする。
    elements['context-detail-content'].scrollTop = 0;
    elements['context-detail-title'].focus({preventScroll: true});
  }

  // .context-detail.drawer / .drawer-backdrop の transition と一致させる（閉じ切ってから hidden 化）。
  const DRAWER_ANIM_MS = 240;

  /**
   * 背景（.app-shell 配下の主要 UI）の inert を切り替える。
   *
   * ドロワーはモーダルなので、開いている間は背後を Tab フォーカス・支援技術の読み上げ双方から
   * 隔離したい。inert プロパティ1つで両方を満たせる。ドロワーと同 backdrop は .app-shell の外に
   * あるため巻き込まれない。inert 非対応の古いエンジンでは no-op になり、aria-modal と背景
   * オーバーレイで最低限のモーダル性を保つ（グレースフルデグレード）。
   *
   * @param {boolean} inert 背景を不活性にするなら true、解除するなら false。
   */
  function setBackgroundInert(inert) {
    const shell = document.querySelector('.app-shell');
    if (shell) shell.inert = inert;
  }

  /** インライン詳細を右からのドロワーとして開く。背景オーバーレイを出し、スライドインさせる。 */
  function openContextDrawer() {
    const drawer = elements['context-detail'];
    const backdrop = elements['context-detail-backdrop'];
    if (!drawer) return;
    // 閉じ途中の後始末タイマーが残っていれば解除し、開いた面を誤って hidden 化しないようにする。
    if (state.drawerCloseTimer) { clearTimeout(state.drawerCloseTimer); state.drawerCloseTimer = null; }
    if (backdrop) backdrop.hidden = false;
    drawer.hidden = false;
    // 閉状態の transform を一度レイアウトへ反映してから .is-open を付け、display:none からでも確実に滑らせる。
    void drawer.offsetWidth;
    drawer.classList.add('is-open');
    if (backdrop) backdrop.classList.add('is-open');
    document.body.classList.add('drawer-open');
    // ドロワーは .app-shell の外（body直下）にあるため、背景の .app-shell を inert 化しても
    // 面自体は生きたまま、背後の Tab フォーカスと読み上げだけを止められる（真のモーダル化）。
    setBackgroundInert(true);
  }

  /** ドロワーを閉じる。スライドアウト後に hidden を確定し、支援技術のツリーからも外す。 */
  function closeContextDrawer() {
    const drawer = elements['context-detail'];
    const backdrop = elements['context-detail-backdrop'];
    if (!drawer || drawer.hidden) return;
    // inert は即時に解除する。hideContextDetail は closeContextDrawer の直後に呼び出し元へ
    // フォーカスを戻すが、その要素は .app-shell 内にあり、inert のままだと focus() が無効化されるため。
    setBackgroundInert(false);
    drawer.classList.remove('is-open');
    if (backdrop) backdrop.classList.remove('is-open');
    document.body.classList.remove('drawer-open');
    // reduce-motion 等で transitionend が来ない端末でも確実に閉じるよう、時間で hidden を確定する。
    if (state.drawerCloseTimer) clearTimeout(state.drawerCloseTimer);
    state.drawerCloseTimer = setTimeout(() => {
      state.drawerCloseTimer = null;
      // 後始末の直前に再オープンされていないことを確認してから hidden 化する。
      if (!drawer.classList.contains('is-open')) {
        drawer.hidden = true;
        if (backdrop) backdrop.hidden = true;
      }
    }, DRAWER_ANIM_MS);
  }

  /** ドロワー表示中の Esc で閉じる。QRスキャナ等の <dialog> は各自 Esc を処理するため干渉しない。 */
  function handleDrawerKeydown(event) {
    if (elements['confirm-dialog']?.open) return;
    if (event.key !== 'Escape') return;
    if (elements['context-detail'] && !elements['context-detail'].hidden) hideContextDetail();
  }

  /** インライン詳細（ドロワー）を閉じ、保持していた履歴条件も破棄して元のビュー表示へ戻す。 */
  function hideContextDetail() {
    if (!elements['context-detail']) return;
    closeContextDrawer();
    elements['context-detail-more'].hidden = true;
    state.contextDetailFilter = null;
    // 明細を閉じたら、開くきっかけになった要素へフォーカスを戻す（body へ落とさない）。
    // DOMに残っていて focus 可能なときだけ復帰させ、そうでなければ何もしない。
    const origin = state.contextDetailOrigin;
    state.contextDetailOrigin = null;
    if (origin && origin.isConnected && typeof origin.focus === 'function') {
      origin.focus({preventScroll: true});
    }
  }

  /** 任意導線：保持中の条件で履歴ビューを開き、該当タブと絞り込みを適用する（ユーザー操作時のみ）。 */
  function openContextDetailInHistory() {
    const filter = state.contextDetailFilter;
    hideContextDetail();
    if (filter) {
      elements['history-search'].value = filter.query || '';
      elements['history-type'].value = filter.type || '';
      state.historyMode = filter.mode || 'transactions';
    }
    switchView('history');
    setRecordTab(state.historyMode);
  }

  function clearHistoryFilters() {
    elements['history-search'].value = '';
    elements['history-type'].value = '';
    state.historyPage = 0;
    renderHistory();
    elements['history-search'].focus();
  }

  function relatedTransactions(row) {
    // 不足/滞留ドリルダウンは生存中の残高（BALANCE）に紐づく行なので、物理削除マスタの
    // archived 取引は「直近の取引」から除外し、残高と取引明細の基準を揃える。
    return activeTransactions().filter((item) => {
      const itemMatches = !row.item_code || item.item_code === row.item_code;
      const locationMatches = !row.location_code || item.location_code === row.location_code;
      return itemMatches && locationMatches;
    });
  }

  function minimumForBalance(row) {
    if (row.minimum_quantity !== undefined && row.minimum_quantity !== null) return Number(row.minimum_quantity || 0);
    const rule = state.data.rules.find((item) => item.item_code === row.item_code && item.location_code === row.location_code && isActive(item));
    return Number(rule?.minimum_quantity || 0);
  }

  function renderBalanceDetails(rows) {
    if (!rows.length) return '<div class="empty-state">現在庫明細がありません。</div>';
    return detailTable(['品目', 'ロケーション', '現在庫', '基準', '状態'], rows.map((row) => {
      const quantity = Number(row.quantity || 0);
      const minimum = minimumForBalance(row);
      return [row.item_name || row.item_code || '—', row.location_name || row.location_code || '—', number.format(quantity), number.format(minimum), minimum > 0 && quantity < minimum ? '不足' : '正常'];
    }), '在庫明細');
  }

  function renderDetailTransactions(rows) {
    if (!rows.length) return '<div class="empty-state">該当する取引はありません。</div>';
    return detailTable(['日時', '種別', '品目・ロケーション', '数量', '残高'], rows.map((row) => [formatDate(row.occurred_at), transactionLabel(row.transaction_type), `${row.item_name || row.item_code || '—'} / ${row.location_name || row.location_code || '—'}`, number.format(Number(row.quantity || 0)), number.format(Number(row.balance_after || 0))]), '取引明細');
  }

  function detailStats(rows) {
    return `<div class="detail-stat-grid">${rows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(number.format(Number(value || 0)))}</strong></div>`).join('')}</div>`;
  }

  function detailSection(title, content) {
    return `<section class="detail-section"><h3>${escapeHtml(title)}</h3>${content}</section>`;
  }

  function detailDefinition(rows) {
    return `<dl class="detail-definition">${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>`;
  }

  function detailTable(headers, rows, caption) {
    // 表のアクセシブル名（INV-034）。ドリルダウン明細も SR の表一覧で種別が分かるよう隠しキャプションを添える。
    const cap = caption ? `<caption class="sr-only">${escapeHtml(caption)}</caption>` : '';
    if (!rows.length) return '<div class="empty-state">明細がありません。</div>';
    return `<div class="detail-table-wrap"><table class="detail-table">${cap}<thead><tr>${headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${escapeHtml(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  /**
   * 取引明細の主役ビュー。在庫が登録前→登録後でどう動いたかを、KPI箱の羅列ではなく
   * 1本の静かな帯として示す。種別（入庫/出庫）で意味色を分け、増減量を右端に添える。
   *
   * @param {number} before 登録前の在庫数
   * @param {number} after 登録後の在庫数
   * @param {number} signed 符号付き増減量（入庫=正・出庫=負）
   * @param {string} type 取引種別コード（IN / OUT）
   * @return {string} balance-flow のHTML
   */
  function balanceFlow(before, after, signed, type) {
    // 直近取引バッジ（recent-badge）と同じ意味色に揃える：入庫=緑・出庫=橙。
    const dir = type === 'OUT' ? 'out' : 'in';
    // 符号は全角（＋／−）で、既存の見込み在庫表示と表記を統一する。
    const sign = signed > 0 ? '＋' : signed < 0 ? '−' : '±';
    const delta = `${sign}${number.format(Math.abs(signed))}`;
    return `<div class="balance-flow">`
      + `<span class="balance-flow-badge ${dir}">${escapeHtml(transactionLabel(type))}</span>`
      + `<div class="balance-flow-track">`
      + `<span class="balance-flow-node"><small>登録前</small><strong>${escapeHtml(number.format(before))}</strong></span>`
      + `<svg class="balance-flow-arrow" aria-hidden="true"><use href="#icon-chevron-right"></use></svg>`
      + `<span class="balance-flow-node is-after"><small>登録後</small><strong>${escapeHtml(number.format(after))}</strong></span>`
      + `</div>`
      + `<span class="balance-flow-delta ${dir}">${escapeHtml(delta)}</span>`
      + `</div>`;
  }

  /**
   * 監査・照合用の参照値（取引ID・リクエストID・通知IDなど）を、本文から浮かせて
   * 末尾に控えめな等幅表記で添えるための定義リスト。主役情報の可読性を邪魔しない。
   *
   * @param {Array<Array<string>>} rows [ラベル, 値] の組の配列
   * @return {string} detail-meta のHTML
   */
  function detailMeta(rows) {
    return `<dl class="detail-meta">${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>`;
  }

  /**
   * 登録元コードを利用者向けの短い日本語ラベルへ変換する。DOMO_MOBILE のような内部enumを
   * そのまま見せると事務的で分かりにくいため、意味を保ったまま読みやすい表記に置き換える。
   * 未知のコードはそのまま返し、情報を失わない。
   *
   * @param {string} source 登録元コード
   * @return {string} 表示用ラベル
   */
  function sourceLabel(source) {
    if (!source) return '—';
    return {DOMO_MOBILE: 'モバイルアプリ', DOMO_WEB: 'PC Web', DEMO_SEED: '初期デモデータ', DOMO: 'Domo'}[source] || source;
  }

  // 管理者専用のマスタCRUD。すべてCode Engineの単一入口 manage_master(MANAGE_MASTER) を通す。
  // 「削除」はAppDBから項目自体を消す物理削除（不可逆・関連データも連鎖削除、ただし台帳は保持）。
  // 一時停止は active=false での更新（可逆）で、物理削除とは別操作として提示する。
  function setMasterTab(tab) {
    if (!state.user.isAdmin) return;
    if (tab !== 'item' && tab !== 'location' && tab !== 'rule') return;
    state.masterTab = tab;
    // 種別を切り替えたら別の一覧になるため、ページ送りは先頭へ戻す。
    state.masterPage = 0;
    // 種別に応じて入力フィールド群を切り替える（統合タブ列の選択状態は setRecordTab が管理する）。
    document.querySelectorAll('[data-master-fields]').forEach((node) => { node.hidden = node.dataset.masterFields !== tab; });
    resetMasterForm();
    renderMasters();
  }

  // 右ペインを「新規登録」の空状態へ戻す。入力値・見出し・操作ボタンをすべて初期化し、
  // 編集途中のキー選択も解除する（callMaster 成功後や種別タブ切替から呼ばれる）。
  function resetMasterForm() {
    cancelConfirmation();
    state.masterEditKey = null;
    state.masterEditLabel = null;
    ['master-item-code', 'master-item-name', 'master-item-category', 'master-item-unit', 'master-location-code', 'master-location-name', 'master-location-zone', 'master-rule-minimum'].forEach((id) => { if (elements[id]) elements[id].value = ''; });
    ['master-item-code', 'master-location-code'].forEach((id) => { if (elements[id]) elements[id].readOnly = false; });
    if (elements['master-rule-location']) { elements['master-rule-location'].disabled = false; elements['master-rule-location'].selectedIndex = 0; }
    if (elements['master-rule-item']) { elements['master-rule-item'].disabled = false; elements['master-rule-item'].selectedIndex = 0; }
    if (elements['master-submit']) { elements['master-submit'].textContent = '登録する'; elements['master-submit'].hidden = false; }
    if (elements['master-delete']) elements['master-delete'].hidden = true;
    // 状態トグルは既存レコードの編集時のみ表示（新規は常に有効で登録する）。
    if (elements['master-active-row']) elements['master-active-row'].hidden = true;
    if (elements['master-active']) elements['master-active'].checked = true;
    setMasterEditorChrome('新規登録', `新しい${MASTER_LABELS[state.masterTab] || 'マスタ'}を入力して保存します。`);
  }

  // 「新規登録」ボタンの入口。空状態へ戻したうえで一覧の選択強調を外し、最初の入力へフォーカスする。
  function newMaster() {
    if (!state.user.isAdmin) return;
    resetMasterForm();
    updateMasterSelection();
    const firstField = {item: 'master-item-code', location: 'master-location-code', rule: 'master-rule-location'}[state.masterTab];
    if (elements[firstField] && typeof elements[firstField].focus === 'function') elements[firstField].focus();
  }

  /** 右ペインの見出し（対象名）と説明文を差し替える。 */
  function setMasterEditorChrome(title, subtitle) {
    if (elements['master-editor-title']) elements['master-editor-title'].textContent = title;
    if (elements['master-editor-subtitle']) elements['master-editor-subtitle'].textContent = subtitle;
  }

  function renderMasterRuleOptions() {
    const locationSelect = elements['master-rule-location'];
    const itemSelect = elements['master-rule-item'];
    if (!locationSelect || !itemSelect) return;
    const previousLocation = locationSelect.value;
    const previousItem = itemSelect.value;
    const activeLocations = state.data.locations.filter(isActive);
    const activeItems = state.data.items.filter(isActive);
    locationSelect.innerHTML = activeLocations.length ? activeLocations.map((row) => `<option value="${escapeAttribute(row.location_code)}">${escapeHtml(row.location_name || row.location_code)}（${escapeHtml(row.location_code)}）</option>`).join('') : '<option value="">ロケーション未登録</option>';
    itemSelect.innerHTML = activeItems.length ? activeItems.map((row) => `<option value="${escapeAttribute(row.item_code)}">${escapeHtml(row.item_name || row.item_code)}（${escapeHtml(row.item_code)}）</option>`).join('') : '<option value="">品目未登録</option>';
    if (previousLocation) locationSelect.value = previousLocation;
    if (previousItem) itemSelect.value = previousItem;
  }

  /**
   * 停止中(active=false)のマスタを参照する基準在庫を編集するための補助。基準在庫のセレクトは
   * 有効なマスタだけで組み立てられる（renderMasterRuleOptions）ため、停止済みのコードは選択肢に
   * 無く、select.value 代入が空振りして selectedIndex=-1（＝value=''）になる。その状態で保存すると
   * 空コードが送られ、最小基準の変更や再有効化ができない。編集対象の実コードを選択肢として補い、
   * 表示と保存値を正しく往復させる（編集中はセレクト自体を disabled にして誤変更を防ぐ）。
   *
   * @param {HTMLSelectElement} select 対象セレクト（品目またはロケーション）
   * @param {string} value 補いたいコード
   * @param {string} label 選択肢に表示する名称
   */
  function ensureSelectOption(select, value, label) {
    if (!select || !value) return;
    if (Array.from(select.options).some((option) => option.value === value)) return;
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label ? `${label}（${value}）` : value;
    select.appendChild(option);
  }

  function renderMasters() {
    if (!elements['master-list']) return;
    renderMasterRuleOptions();
    const tab = state.masterTab;
    elements['master-list'].innerHTML = masterListHtml(tab);
    // 件数は「表示中の行数」ではなく絞り込み後の全件（masterListHtml が算出した total）を出す。
    // ページ送り情報が無い（空一覧）ときは 0 件表示にフォールバックする。
    if (elements['master-result-count']) elements['master-result-count'].textContent = `${number.format(state.masterPageInfo ? state.masterPageInfo.total : 0)}件`;
    // 管理（マスタ）の明細一覧も履歴と同じく1ページでも枠を残す（真っ白回避・操作位置の安定）。
    renderPager('master-pager', 'master', state.masterPageInfo, {alwaysShow: true});
    updateMasterSelection();
  }

  function masterListHtml(tab) {
    if (tab === 'item') {
      const all = [...state.data.items].sort((a, b) => String(a.item_code).localeCompare(String(b.item_code)));
      if (!all.length) { state.masterPageInfo = null; return emptyHtml('登録済みの品目がありません。'); }
      const page = paginate(all, state.masterPage);
      state.masterPage = page.safePage;
      state.masterPageInfo = page;
      const body = page.slice.map((row) => masterRowHtml(tab, row.item_code, row.item_name || row.item_code, [row.item_code, row.item_name || '—', row.category || '—', row.unit || '—'], isActive(row))).join('');
      return masterTableHtml(['コード', '品目名', 'カテゴリー', '単位'], body);
    }
    if (tab === 'location') {
      const all = [...state.data.locations].sort((a, b) => String(a.location_code).localeCompare(String(b.location_code)));
      if (!all.length) { state.masterPageInfo = null; return emptyHtml('登録済みのロケーションがありません。'); }
      const page = paginate(all, state.masterPage);
      state.masterPage = page.safePage;
      state.masterPageInfo = page;
      const body = page.slice.map((row) => masterRowHtml(tab, row.location_code, row.location_name || row.location_code, [row.location_code, row.location_name || '—', row.zone || '—'], isActive(row))).join('');
      return masterTableHtml(['コード', '名称', 'ゾーン'], body);
    }
    const itemNames = new Map(state.data.items.map((row) => [row.item_code, row.item_name || row.item_code]));
    const locationNames = new Map(state.data.locations.map((row) => [row.location_code, row.location_name || row.location_code]));
    const all = [...state.data.rules].sort((a, b) => String(a.rule_key).localeCompare(String(b.rule_key)));
    if (!all.length) { state.masterPageInfo = null; return emptyHtml('登録済みの基準在庫がありません。'); }
    const page = paginate(all, state.masterPage);
    state.masterPage = page.safePage;
    state.masterPageInfo = page;
    const body = page.slice.map((row) => {
      const label = `${locationNames.get(row.location_code) || row.location_code} / ${itemNames.get(row.item_code) || row.item_code}`;
      return masterRowHtml(tab, row.rule_key, label, [locationNames.get(row.location_code) || row.location_code, itemNames.get(row.item_code) || row.item_code, number.format(Number(row.minimum_quantity || 0))], isActive(row));
    }).join('');
    return masterTableHtml(['ロケーション', '品目', '基準在庫'], body);
  }

  function masterTableHtml(headers, body) {
    // 末尾は状態バッジ列とドリルダウン矢印列（見出しは空）。本文の列数と揃える。
    const head = headers.concat(['状態', '']).map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join('');
    // マスタ一覧は取引・通知の履歴表と同じ「素の table」で描く。ドリルダウン詳細ペイン用の
    // .detail-table-wrap（枠線＋角丸の入れ子カード）を流用すると、列見出しの下の縁だけが丸く
    // 見えて履歴表と不揃いになる。スクロール枠は親の #master-list（.master-list）が担い、
    // 見出しは共通の sticky th（#f3f6fc・角丸なしでフラット）に揃える。
    // 表のアクセシブル名（INV-034）。履歴表と並ぶ画面で品目/ロケーション/基準在庫のどのマスタ一覧かを
    // SR が区別できるよう、現在のマスタ種別から隠しキャプションを与える。
    const caption = `${MASTER_LABELS[state.masterTab] || 'マスタ'}の一覧`;
    return `<table class="master-table"><caption class="sr-only">${escapeHtml(caption)}</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function masterRowHtml(tab, code, label, cells, active) {
    const dataCells = cells.map((value) => `<td>${escapeHtml(value)}</td>`).join('');
    const status = active ? '<span class="master-status active">有効</span>' : '<span class="master-status inactive">停止中</span>';
    const selected = code === state.masterEditKey;
    // 行全体をクリック／キー操作の対象にし、右ペインの編集フォームへ読み込む（履歴の明細ドリルダウンと同じ操作感）。
    return `<tr class="drilldown-row${active ? '' : ' master-row-inactive'}${selected ? ' is-selected' : ''}" data-master-edit="${escapeAttribute(code)}"${selected ? ' aria-current="true"' : ''}>${dataCells}<td>${status}</td><td class="drill-cell"><button type="button" class="drill-btn" aria-label="${escapeAttribute(label)}を編集"><svg class="drill-icon" aria-hidden="true"><use href="#icon-chevron-right"></use></svg></button></td></tr>`;
  }

  function submitMaster(event) {
    if (event) event.preventDefault();
    if (!state.user.isAdmin) return;
    const tab = state.masterTab;
    let action, fields, successMessage, details;
    // 編集時のみ状態トグルの値を UPSERT に含める（可逆な有効/停止の切替＝更新Dの実演）。
    // 新規時はトグル非表示のため active を送らず、CE 既定の有効(true)で登録する。
    const activeField = (state.masterEditKey && elements['master-active']) ? {active: elements['master-active'].checked} : {};
    if (tab === 'item') {
      const code = (elements['master-item-code'].value || '').trim();
      const name = (elements['master-item-name'].value || '').trim();
      if (!code || !name) { toast('品目コードと品目名を入力してください。', 'error'); return; }
      action = 'UPSERT_ITEM';
      fields = Object.assign({item_code: code, item_name: name, category: (elements['master-item-category'].value || '').trim(), unit: (elements['master-item-unit'].value || '').trim()}, activeField);
      successMessage = `品目「${name}」を保存しました。`;
      details = [['品目', `${name}（${code}）`], ['カテゴリー', fields.category || '—'], ['単位', fields.unit || '—']];
    } else if (tab === 'location') {
      const code = (elements['master-location-code'].value || '').trim();
      const name = (elements['master-location-name'].value || '').trim();
      if (!code || !name) { toast('ロケーションコードとロケーション名を入力してください。', 'error'); return; }
      action = 'UPSERT_LOCATION';
      fields = Object.assign({location_code: code, location_name: name, zone: (elements['master-location-zone'].value || '').trim()}, activeField);
      successMessage = `ロケーション「${name}」を保存しました。`;
      details = [['ロケーション', `${name}（${code}）`], ['ゾーン', fields.zone || '—']];
    } else {
      const locationCode = elements['master-rule-location'].value;
      const itemCode = elements['master-rule-item'].value;
      const minimumRaw = elements['master-rule-minimum'].value;
      if (!locationCode || !itemCode) { toast('ロケーションと品目を選択してください。', 'error'); return; }
      const minimum = Number(minimumRaw);
      if (minimumRaw === '' || !Number.isFinite(minimum) || minimum < 0) { toast('基準在庫は0以上の数値で入力してください。', 'error'); return; }
      action = 'UPSERT_RULE';
      fields = Object.assign({location_code: locationCode, item_code: itemCode, minimum_quantity: minimum}, activeField);
      successMessage = '基準在庫を保存しました。';
      const locationName = state.data.locations.find((row) => row.location_code === locationCode)?.location_name || locationCode;
      const itemName = state.data.items.find((row) => row.item_code === itemCode)?.item_name || itemCode;
      details = [['ロケーション', `${locationName}（${locationCode}）`], ['品目', `${itemName}（${itemCode}）`], ['基準在庫', number.format(minimum)]];
    }
    const editing = Boolean(state.masterEditKey);
    const editKey = state.masterEditKey;
    details.push(['状態', fields.active === false ? '停止中（元に戻せます）' : '有効']);
    showActionConfirmation({
      title: `${MASTER_LABELS[tab]}を${editing ? '更新' : '登録'}しますか？`,
      message: '以下の内容を保存します。有効・停止中の変更は、入出庫の選択肢と基準在庫の判定に反映されます。',
      details,
      actionLabel: 'はい、保存する',
      trigger: event?.submitter || elements['master-submit'],
      onConfirm: () => {
        if (!state.user.isAdmin || state.masterTab !== tab || state.masterEditKey !== editKey) {
          toast('権限または編集対象が変わりました。もう一度確認してください。', 'error');
          return;
        }
        callMaster(action, fields, successMessage);
      }
    });
  }

  // 一覧行の選択で右ペインへ読み込む。値を流し込んだあと、状態(有効/停止)を状態トグルへ反映し、
  // 操作ボタンを applyMasterEditorMode で編集モードに整える（更新・削除・可逆な停止切替を提示）。
  function editMaster(tab, code) {
    if (!state.user.isAdmin) return;
    cancelConfirmation();
    let active = true;
    let label = code;
    if (tab === 'item') {
      const row = state.data.items.find((item) => item.item_code === code);
      if (!row) return;
      active = isActive(row);
      label = row.item_name || row.item_code;
      elements['master-item-code'].value = row.item_code || '';
      elements['master-item-code'].readOnly = true;
      elements['master-item-name'].value = row.item_name || '';
      elements['master-item-category'].value = row.category || '';
      elements['master-item-unit'].value = row.unit || '';
    } else if (tab === 'location') {
      const row = state.data.locations.find((location) => location.location_code === code);
      if (!row) return;
      active = isActive(row);
      label = row.location_name || row.location_code;
      elements['master-location-code'].value = row.location_code || '';
      elements['master-location-code'].readOnly = true;
      elements['master-location-name'].value = row.location_name || '';
      elements['master-location-zone'].value = row.zone || '';
    } else {
      const row = state.data.rules.find((rule) => rule.rule_key === code);
      if (!row) return;
      active = isActive(row);
      renderMasterRuleOptions();
      const itemName = (state.data.items.find((item) => item.item_code === row.item_code) || {}).item_name || row.item_code;
      const locationName = (state.data.locations.find((location) => location.location_code === row.location_code) || {}).location_name || row.location_code;
      // 停止中マスタを参照する基準在庫でも、実コードを選択肢へ補って表示・保存値を正しく往復させる。
      ensureSelectOption(elements['master-rule-location'], row.location_code, locationName);
      ensureSelectOption(elements['master-rule-item'], row.item_code, itemName);
      label = `${locationName} / ${itemName}`;
      elements['master-rule-location'].value = row.location_code || '';
      elements['master-rule-item'].value = row.item_code || '';
      elements['master-rule-location'].disabled = true;
      elements['master-rule-item'].disabled = true;
      elements['master-rule-minimum'].value = Number(row.minimum_quantity || 0);
    }
    state.masterEditKey = code;
    state.masterEditLabel = label;
    applyMasterEditorMode(tab, label, active);
    updateMasterSelection();
  }

  /** 選択レコードを右ペインへ読み込んだ後、見出し・状態トグル・操作ボタンを編集モードに整える。 */
  function applyMasterEditorMode(tab, label, active) {
    const typeLabel = MASTER_LABELS[tab] || 'マスタ';
    setMasterEditorChrome(label || '編集', `${typeLabel}の内容を編集して更新するか、削除できます。`);
    // 状態トグルを表示し現在の有効/停止を反映する。更新保存で可逆に切り替えられる（不可逆な削除とは別操作）。
    if (elements['master-active-row']) elements['master-active-row'].hidden = false;
    if (elements['master-active']) elements['master-active'].checked = active;
    if (elements['master-submit']) { elements['master-submit'].textContent = '更新を保存'; elements['master-submit'].hidden = false; }
    if (elements['master-delete']) elements['master-delete'].hidden = false;
    const focusTarget = {item: 'master-item-name', location: 'master-location-name', rule: 'master-rule-minimum'}[tab];
    if (elements[focusTarget] && typeof elements[focusTarget].focus === 'function') elements[focusTarget].focus();
  }

  /** 選択中のマスタ行だけに is-selected を付ける（右ペイン編集対象のカレント表示）。 */
  function updateMasterSelection() {
    if (!elements['master-list']) return;
    elements['master-list'].querySelectorAll('[data-master-edit]').forEach((node) => {
      const selected = node.dataset.masterEdit === state.masterEditKey;
      node.classList.toggle('is-selected', selected);
      // 行は素の <tr>（role=row）。選択は集合内カレントなので aria-current で表す（aria-selected は無効）。
      if (selected) node.setAttribute('aria-current', 'true');
      else node.removeAttribute('aria-current');
    });
  }

  function handleMasterRowActivate(event) {
    const row = event.target.closest('[data-master-edit]');
    if (!row) return;
    editMaster(state.masterTab, row.dataset.masterEdit);
  }

  // 物理削除の確認ダイアログ。不可逆であること・関連データも連鎖削除されること・
  // ただし台帳(履歴)は残ることを明示し、一時停止したいだけなら状態トグルへ誘導する。
  function masterDeleteImpact(tab, code) {
    // 品目/ロケーションの物理削除で道連れになる現在庫・相手側の拠点/品目数・基準在庫件数を、メモリ上の
    // state.data から定量化する（INV-017。基準在庫〔rule〕単体の削除は在庫を道連れにしないため対象外）。
    if (tab !== 'item' && tab !== 'location') return '';
    const field = tab === 'item' ? 'item_code' : 'location_code';
    const otherField = tab === 'item' ? 'location_code' : 'item_code';
    const otherLabel = tab === 'item' ? '拠点' : '品目';
    const balances = state.data.balances.filter((row) => row[field] === code);
    const rules = state.data.rules.filter((row) => row[field] === code);
    const totalQty = balances.reduce((sum, row) => sum + Number(row.quantity || 0), 0);
    const otherCount = new Set(balances.map((row) => row[otherField])).size;
    return `${otherCount}${otherLabel}に現在庫 計${number.format(totalQty)} / 基準在庫${rules.length}件を同時削除`;
  }

  function confirmMasterDelete(tab, code, label) {
    if (!state.user.isAdmin) return;
    const typeLabel = tab === 'item' ? '品目' : tab === 'location' ? 'ロケーション' : '基準在庫';
    const details = [['削除対象', `${label || code}（${code}）`]];
    const impact = masterDeleteImpact(tab, code);
    if (impact) details.push(['影響範囲', impact]);  // 不可逆操作の影響範囲を定量で見せる
    showActionConfirmation({
      title: `${typeLabel}を完全に削除しますか？`,
      message: 'この項目をAppDBから完全に削除します。この操作は取り消せません。関連する基準在庫や現在庫も一緒に削除されますが、入出庫・通知の履歴は監査証跡として残ります。一時的に止めたいだけなら、削除せずチェックボックス「入出庫で選択できるようにする」をオフにしてください（停止中・元に戻せます）。',
      details,
      actionLabel: 'はい、完全に削除する',
      danger: true,
      trigger: elements['master-delete'],
      onConfirm: () => runMasterDelete(tab, code)
    });
  }

  function showActionConfirmation({title, message, details, actionLabel, danger = false, trigger, onConfirm}) {
    if (state.pendingConfirm) { elements['confirm-cancel']?.focus({preventScroll: true}); return; }
    if (!elements['loading-overlay'].hidden) return;
    const dialog = elements['confirm-dialog'];
    if (!dialog || typeof dialog.showModal !== 'function' ||
        !['confirm-title', 'confirm-message', 'confirm-details', 'confirm-action', 'confirm-cancel'].every((id) => elements[id])) {
      toast('確認画面を表示できません。画面を再読み込みしてください。', 'error');
      return;
    }
    elements['confirm-title'].textContent = title;
    elements['confirm-message'].textContent = message;
    elements['confirm-details'].innerHTML = details.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
    elements['confirm-action'].textContent = actionLabel;
    elements['confirm-action'].classList.toggle('danger', danger);
    state.pendingConfirm = {action: onConfirm, trigger: trigger || document.activeElement, previousOverflow: document.body.style.overflow};
    dialog.returnValue = '';
    try {
      dialog.showModal();
      document.body.style.overflow = 'hidden';
      elements['confirm-cancel'].focus({preventScroll: true});
    } catch (error) {
      cancelConfirmation();
      toast(errorMessage(error, '確認画面を表示できません。画面を再読み込みしてください。'), 'error');
    }
  }

  function cancelConfirmation() {
    if (state.pendingConfirm) state.pendingConfirm.action = null;
    if (elements['confirm-dialog']?.open) elements['confirm-dialog'].close('cancel');
    handleConfirmClose();
  }

  function handleConfirmKeydown(event) {
    if (event.key !== 'Tab') return;
    const buttons = Array.from(elements['confirm-dialog'].querySelectorAll('button:not([disabled])'));
    const first = buttons[0], last = buttons[buttons.length - 1];
    if ((!event.shiftKey && document.activeElement === last) || (event.shiftKey && document.activeElement === first)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus({preventScroll: true});
    }
  }

  // 確認ダイアログの単一実行点。確定ボタン(value="default")で閉じたときだけ保留中の操作を1回実行する。
  // キャンセル/×(value="cancel")・ESC(returnValue="")では保留を捨てるだけで何もしない。
  function handleConfirmClose() {
    if (elements['confirm-dialog']?.open) return;
    const pending = state.pendingConfirm;
    state.pendingConfirm = null;
    if (!pending) return;
    document.body.style.overflow = pending.previousOverflow;
    if (pending.trigger?.isConnected) pending.trigger.focus({preventScroll: true});
    if (pending.action && elements['confirm-dialog'].returnValue === 'default') pending.action();
  }

  // AppDBからの物理削除(D)を実行する。CE側でマスタ本体＋依存ルール＋派生状態を連鎖削除し、
  // 追記専用の台帳は保持する（削除の連鎖範囲はサーバ側の管理者用ハンドラ _admin が一元管理）。
  function runMasterDelete(tab, code) {
    if (tab === 'rule') {
      const parts = String(code).split('|');
      return callMaster('DELETE_RULE', {location_code: parts[0], item_code: parts[1]}, '基準在庫を削除しました。');
    }
    if (tab === 'item') return callMaster('DELETE_ITEM', {item_code: code}, '品目を削除しました。');
    return callMaster('DELETE_LOCATION', {location_code: code}, 'ロケーションを削除しました。');
  }

  async function callMaster(action, fields, successMessage) {
    if (!state.user.isAdmin) return;
    if (!elements['loading-overlay'].hidden) return;
    setLoading(true, 'マスタを更新しています');
    try {
      const request = Object.assign({action, request_id: createRequestId(), source: 'ADMIN_UI'}, fields);
      const result = await dataApi.callFunction('manage_master', {request_json: JSON.stringify(request)});
      if (!result || !result.ok) throw new Error(result?.error?.message || 'マスタ操作に失敗しました。');
      toast(successMessage || 'マスタを更新しました。', 'success');
      resetMasterForm();
      await refreshAll({quiet: true});
    } catch (error) {
      toast(errorMessage(error, 'マスタ操作を実行できませんでした。'), 'error', config.ui.toastDurationLong);
    } finally {
      setLoading(false);
    }
  }

  function setLoading(active, message) {
    // ローディングオーバーレイの表示だけを状態源にする（別途フラグを持たず二重管理を避ける）。
    elements['loading-overlay'].hidden = !active;
    const text = elements['loading-overlay'].querySelector('p');
    if (message && text) text.textContent = message;
  }

  function toast(message, type, duration) {
    const node = document.createElement('div');
    node.className = `toast ${type || ''}`;
    node.setAttribute('role', type === 'error' ? 'alert' : 'status');
    // 先頭の状態グリフ（!/✓）は装飾。role=alert/status で全文が読まれるため、SR には
    // 「感嘆符」「チェックマーク」を前置しないよう aria-hidden にして本文だけを通知する。
    node.innerHTML = `<span aria-hidden="true">${type === 'error' ? '!' : '✓'}</span><span>${escapeHtml(message)}</span><button type="button" aria-label="閉じる">×</button>`;
    node.querySelector('button').addEventListener('click', () => node.remove());
    elements['toast-region'].appendChild(node);
    global.setTimeout(() => node.remove(), duration || config.ui.toastDurationDefault);
  }

  function createRequestId() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') return global.crypto.randomUUID();
    return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function isActive(row) {
    return row && (row.active === true || String(row.active).toLowerCase() === 'true' || row.active === 1 || row.active === undefined);
  }

  function isDomoMobileHost() {
    // モバイル専用ペルソナ（.admin-only を全消しし、マスタCRUDタブをメニューから外す）へ落とす判定。
    // 影響が大きい（PCの管理者がマスタ編集面を無言で失う）ため、まず Domo SDK の明示シグナルを正とする。
    const domoEnvironment = global.domo && global.domo.env ? global.domo.env : {};
    const platform = String(domoEnvironment.platform || '').trim().toLowerCase();
    if (platform === 'mobile') return true;
    if (platform === 'desktop' || platform === 'web') return false;
    if (domoEnvironment.isMobile === true || domoEnvironment.mobile === true) return true;
    // 明示シグナルが埋まらないホスト向けの UA フォールバック。素の 'Domo' 部分一致にはしない——UA に
    // 'Domo' を含むだけのデスクトップ/埋め込みラッパまでモバイル扱いし、管理者から編集面を奪うため
    // （INV-039）。「Domo マーカー」かつ「標準モバイルOSトークン」が揃うときだけモバイルと見なす。
    const userAgent = String(global.navigator?.userAgent || '');
    return /Domo/i.test(userAgent) && /Mobi|Android|iPhone|iPad|iPod/i.test(userAgent);
  }


  function sortNewest(field) {
    return (a, b) => new Date(b[field] || 0).getTime() - new Date(a[field] || 0).getTime();
  }

  function barPct(raw, denom) {
    // 棒のサイズ(%)。真のゼロ（在庫0・入出庫0の静かな日）は 0 幅/0 高で描き、最小クランプ(2%)の
    // 「わずかに有り」の瘤を出さない＝ゼロと少量を見分けられる（INV-023）。値>0 のときだけ最小 2% を
    // 下限にし、負値・分母0（全ゼロ）は 0 にする（0/0 の NaN 棒も防ぐ）。
    const value = Number(raw) || 0;
    return value > 0 && denom > 0 ? Math.max(2, value / denom * 100) : 0;
  }

  function formatDate(value) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '—' : dateTime.format(parsed);
  }

  function formatFullDate(value) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '—' : dateTimeFull.format(parsed);
  }

  function formatDisplayDate(value) {
    const parts = String(value || '').slice(0, 10).split('-');
    return parts.length === 3 ? `${Number(parts[0])}年${Number(parts[1])}月${Number(parts[2])}日` : String(value || '—');
  }

  function formatShortDate(value) {
    const parts = String(value || '').slice(5).split('-');
    return parts.length === 2 ? `${Number(parts[0])}/${Number(parts[1])}` : value;
  }

  function statusClass(status) {
    const value = String(status || '').toUpperCase();
    if (value === 'SENT' || value === 'SUCCESS') return 'sent';
    if (value === 'FAILED' || value === 'FALLBACK') return 'failed';
    return 'pending';
  }

  // バックエンドの通知ステータス enum を表示専用の日本語へ（取引種別の transactionLabel と同じ方針）。
  // 色は statusClass、文字は statusLabel で「色＋文字」を満たす。未知値はそのまま出す（黙って隠さない）。
  function statusLabel(status) {
    const value = String(status || '').toUpperCase();
    return {
      PENDING: '送信待ち', STARTED: '送信中', SENT: '送信済み', SUCCESS: '送信済み',
      FAILED: '送信失敗', FALLBACK: '代替送信', SKIPPED: '送信省略'
    }[value] || (status ? String(status) : '送信待ち');
  }

  function transactionLabel(type) {
    return {IN: '入庫', OUT: '出庫'}[type] || type || '取引';
  }

  function errorMessage(error, fallback) {
    if (!error) return fallback;
    if (typeof error === 'string') return error;
    if (error.message && !/^HTTP \d+$/.test(error.message)) return error.message;
    if (error.response && error.response.message) return error.response.message;
    return fallback;
  }

  function emptyHtml(message) {
    return `<div class="empty-state">${escapeHtml(message)}</div>`;
  }

  function tableEmpty(columns, message) {
    return `<tr><td colspan="${columns}"><div class="empty-state">${escapeHtml(message)}</div></td></tr>`;
  }

  function escapeHtml(value) {
    const node = document.createElement('span');
    node.textContent = String(value ?? '');
    return node.innerHTML;
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
})(window, document);
