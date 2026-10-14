(function inventoryDataModule(global) {
  'use strict';

  const config = global.InventoryConfig;
  const localHosts = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);
  const isLocalPreview = global.location.protocol === 'file:' || localHosts.has(global.location.hostname);
  const hasDomo = !isLocalPreview && Boolean(global.domo && typeof global.domo.get === 'function');
  const runtimeMode = hasDomo ? 'domo' : (isLocalPreview ? 'demo' : 'error');
  // 通信タイムアウトは config.js（InventoryConfig.network）を唯一の設定源とし、
  // マジックナンバーをここへベタ書きしない。
  const requestTimeoutMs = config.network.requestTimeoutMs;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const isoNow = () => new Date().toISOString();
  const daysAgo = (days, hour) => {
    const date = new Date();
    date.setDate(date.getDate() - days);
    date.setHours(hour || 9, 0, 0, 0);
    return date.toISOString();
  };

  const demo = {
    items: [
      {item_code: 'ITEM-001', item_name: '安全手袋', category: '安全用品', unit: '双', qr_value: 'ITEM:ITEM-001', active: true},
      {item_code: 'ITEM-002', item_name: '保護メガネ', category: '安全用品', unit: '個', qr_value: 'ITEM:ITEM-002', active: true},
      {item_code: 'ITEM-003', item_name: '六角ボルト M8', category: '締結部品', unit: '本', qr_value: 'ITEM:ITEM-003', active: true},
      {item_code: 'ITEM-004', item_name: '潤滑オイル', category: '消耗品', unit: '缶', qr_value: 'ITEM:ITEM-004', active: true},
      {item_code: 'ITEM-005', item_name: '梱包テープ', category: '梱包資材', unit: '巻', qr_value: 'ITEM:ITEM-005', active: true}
    ],
    locations: [
      {location_code: 'LOC-01', location_name: '中央倉庫', zone: 'A', qr_value: 'LOC:LOC-01', active: true},
      {location_code: 'LOC-02', location_name: '組立エリア', zone: 'B', qr_value: 'LOC:LOC-02', active: true},
      {location_code: 'LOC-03', location_name: '保守部品庫', zone: 'C', qr_value: 'LOC:LOC-03', active: true}
    ],
    rules: [
      {rule_key: 'LOC-01|ITEM-001', location_code: 'LOC-01', item_code: 'ITEM-001', minimum_quantity: 20, active: true},
      {rule_key: 'LOC-01|ITEM-002', location_code: 'LOC-01', item_code: 'ITEM-002', minimum_quantity: 10, active: true},
      {rule_key: 'LOC-02|ITEM-001', location_code: 'LOC-02', item_code: 'ITEM-001', minimum_quantity: 12, active: true},
      {rule_key: 'LOC-02|ITEM-003', location_code: 'LOC-02', item_code: 'ITEM-003', minimum_quantity: 50, active: true},
      {rule_key: 'LOC-03|ITEM-004', location_code: 'LOC-03', item_code: 'ITEM-004', minimum_quantity: 8, active: true}
    ],
    balances: [
      {balance_key: 'LOC-01|ITEM-001', location_code: 'LOC-01', location_name: '中央倉庫', item_code: 'ITEM-001', item_name: '安全手袋', quantity: 38, minimum_quantity: 20, shortage_quantity: 0, is_shortage: false, last_transaction_at: daysAgo(0, 10)},
      {balance_key: 'LOC-01|ITEM-002', location_code: 'LOC-01', location_name: '中央倉庫', item_code: 'ITEM-002', item_name: '保護メガネ', quantity: 7, minimum_quantity: 10, shortage_quantity: 3, is_shortage: true, last_transaction_at: daysAgo(1, 14)},
      {balance_key: 'LOC-02|ITEM-001', location_code: 'LOC-02', location_name: '組立エリア', item_code: 'ITEM-001', item_name: '安全手袋', quantity: 11, minimum_quantity: 12, shortage_quantity: 1, is_shortage: true, last_transaction_at: daysAgo(0, 9)},
      {balance_key: 'LOC-02|ITEM-003', location_code: 'LOC-02', location_name: '組立エリア', item_code: 'ITEM-003', item_name: '六角ボルト M8', quantity: 145, minimum_quantity: 50, shortage_quantity: 0, is_shortage: false, last_transaction_at: daysAgo(4, 11)},
      {balance_key: 'LOC-03|ITEM-004', location_code: 'LOC-03', location_name: '保守部品庫', item_code: 'ITEM-004', item_name: '潤滑オイル', quantity: 19, minimum_quantity: 8, shortage_quantity: 0, is_shortage: false, last_transaction_at: daysAgo(42, 9)},
      {balance_key: 'LOC-01|ITEM-005', location_code: 'LOC-01', location_name: '中央倉庫', item_code: 'ITEM-005', item_name: '梱包テープ', quantity: 32, minimum_quantity: 0, shortage_quantity: 0, is_shortage: false, last_transaction_at: daysAgo(35, 13)}
    ],
    transactions: [
      {transaction_id: 'TRX-DEMO-001', request_id: 'SEED-001', transaction_type: 'IN', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 50, signed_quantity: 50, balance_before: 0, balance_after: 50, reason: '初期受入', operator_name: 'デモ担当者', occurred_at: daysAgo(6, 9)},
      {transaction_id: 'TRX-DEMO-002', request_id: 'SEED-002', transaction_type: 'OUT', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 12, signed_quantity: -12, balance_before: 50, balance_after: 38, reason: '作業用払出', operator_name: 'デモ担当者', occurred_at: daysAgo(0, 10)},
      {transaction_id: 'TRX-DEMO-003', request_id: 'SEED-003', transaction_type: 'IN', item_code: 'ITEM-002', item_name: '保護メガネ', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 15, signed_quantity: 15, balance_before: 0, balance_after: 15, reason: '初期受入', operator_name: 'デモ担当者', occurred_at: daysAgo(5, 10)},
      {transaction_id: 'TRX-DEMO-004', request_id: 'SEED-004', transaction_type: 'OUT', item_code: 'ITEM-002', item_name: '保護メガネ', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 8, signed_quantity: -8, balance_before: 15, balance_after: 7, reason: '現場払出', operator_name: 'デモ担当者', occurred_at: daysAgo(1, 14)},
      {transaction_id: 'TRX-DEMO-005', request_id: 'SEED-005', transaction_type: 'IN', item_code: 'ITEM-003', item_name: '六角ボルト M8', location_code: 'LOC-02', location_name: '組立エリア', quantity: 150, signed_quantity: 150, balance_before: 0, balance_after: 150, reason: '初期受入', operator_name: '管理担当者', occurred_at: daysAgo(8, 9)},
      {transaction_id: 'TRX-DEMO-006', request_id: 'SEED-006', transaction_type: 'OUT', item_code: 'ITEM-003', item_name: '六角ボルト M8', location_code: 'LOC-02', location_name: '組立エリア', quantity: 10, signed_quantity: -10, balance_before: 150, balance_after: 140, reason: '組立払出', operator_name: 'デモ担当者', occurred_at: daysAgo(4, 11)},
      {transaction_id: 'TRX-DEMO-008', request_id: 'SEED-008', transaction_type: 'IN', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-02', location_name: '組立エリア', quantity: 20, signed_quantity: 20, balance_before: 0, balance_after: 20, reason: '初期配置', operator_name: '管理担当者', occurred_at: daysAgo(2, 9)},
      {transaction_id: 'TRX-DEMO-009', request_id: 'SEED-009', transaction_type: 'OUT', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-02', location_name: '組立エリア', quantity: 9, signed_quantity: -9, balance_before: 20, balance_after: 11, reason: '作業用払出', operator_name: 'デモ担当者', occurred_at: daysAgo(0, 9)},
      {transaction_id: 'TRX-DEMO-010', request_id: 'SEED-010', transaction_type: 'IN', item_code: 'ITEM-004', item_name: '潤滑オイル', location_code: 'LOC-03', location_name: '保守部品庫', quantity: 19, signed_quantity: 19, balance_before: 0, balance_after: 19, reason: '保守在庫', operator_name: '管理担当者', occurred_at: daysAgo(42, 9)},
      {transaction_id: 'TRX-DEMO-011', request_id: 'SEED-011', transaction_type: 'IN', item_code: 'ITEM-005', item_name: '梱包テープ', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 32, signed_quantity: 32, balance_before: 0, balance_after: 32, reason: '梱包資材受入', operator_name: '管理担当者', occurred_at: daysAgo(35, 13)}
    ],
    alerts: [
      {alert_id: 'ALERT-DEMO-001', event_type: 'SHORTAGE', balance_key: 'LOC-01|ITEM-002', item_code: 'ITEM-002', item_name: '保護メガネ', location_code: 'LOC-01', location_name: '中央倉庫', current_quantity: 7, minimum_quantity: 10, shortage_quantity: 3, notification_status: 'SENT', notification_subject: '在庫不足: 保護メガネ', created_at: daysAgo(1, 14)},
      {alert_id: 'ALERT-DEMO-002', event_type: 'SHORTAGE', balance_key: 'LOC-02|ITEM-001', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-02', location_name: '組立エリア', current_quantity: 11, minimum_quantity: 12, shortage_quantity: 1, notification_status: 'PENDING', notification_subject: '在庫不足: 安全手袋', created_at: daysAgo(0, 9)}
    ]
  };

  function normalizeDocuments(rows) {
    if (!Array.isArray(rows)) return [];
    return rows.map((row) => {
      if (row && typeof row === 'object' && row.content && typeof row.content === 'object') {
        return Object.assign({_documentId: row.id}, row.content);
      }
      return row;
    });
  }

  function withTimeout(promise, label) {
    if (typeof global.setTimeout !== 'function' || typeof global.clearTimeout !== 'function') {
      return Promise.resolve(promise);
    }
    return new Promise((resolve, reject) => {
      const timer = global.setTimeout(() => reject(new Error(`${label}がタイムアウトしました。`)), requestTimeoutMs);
      Promise.resolve(promise).then(
        (value) => { global.clearTimeout(timer); resolve(value); },
        (error) => { global.clearTimeout(timer); reject(error); }
      );
    });
  }

  async function request(method, url, body) {
    if (!hasDomo) throw new Error('Domo SDK is not available');
    const operation = method === 'GET'
      ? global.domo.get(url)
      : global.domo[method.toLowerCase()](url, body);
    return withTimeout(operation, 'Domo通信');
  }

  async function queryCollection(alias, query) {
    const criteria = query || {};
    const base = `/domo/datastores/v2/collections/${encodeURIComponent(alias)}/documents/query`;
    const payload = Object.keys(criteria).length ? criteria : {};
    // AppDB の documents/query は1応答を最大 queryPageSize 件（上限 10,000 件）で打ち切る。
    // limit/offset をクエリ文字列で送り、1ページ未満になるまで繰り返して全件を集める（body は
    // 絞り込み条件、ページングは query string が契約）。台帳が1万件を超えても取りこぼさない。
    const pageSize = Math.max(Number(config.network.queryPageSize) || 0, 1);
    const documents = [];
    for (let offset = 0; ; offset += pageSize) {
      const page = normalizeDocuments(await request('POST', `${base}?limit=${pageSize}&offset=${offset}`, payload));
      documents.push(...page);
      if (page.length < pageSize) break;
    }
    return documents;
  }

  async function getCollection(alias, demoKey) {
    if (isLocalPreview) return clone(demo[demoKey] || []);
    try {
      return await queryCollection(alias, {});
    } catch (queryError) {
      // v2 query が使えない環境向けのフォールバック。v1 の一覧取得も1応答が上限件数で打ち切られる
      // ため、query 経路と同じく limit/offset のクエリ文字列で全ページを走査し、取りこぼさない。
      const base = `/domo/datastores/v1/collections/${encodeURIComponent(alias)}/documents/`;
      const pageSize = Math.max(Number(config.network.queryPageSize) || 0, 1);
      const documents = [];
      for (let offset = 0; ; offset += pageSize) {
        const page = normalizeDocuments(await request('GET', `${base}?limit=${pageSize}&offset=${offset}`));
        documents.push(...page);
        if (page.length < pageSize) break;
      }
      return documents;
    }
  }

  async function callFunction(functionName, parameters) {
    if (isLocalPreview) return demoFunction(functionName, parameters);
    const operationByFunction = {
      get_inventory_state: 'GET_STATE',
      register_transaction: 'REGISTER',
      start_shortage_notification: 'NOTIFY_NOW',
      manage_master: 'MANAGE_MASTER'
    };
    const operation = operationByFunction[functionName];
    if (!operation) throw new Error(`Unsupported inventory operation: ${functionName}`);
    const input = parameters || {};
    const requestJson = input.request_json;
    const url = `/domo/codeengine/v2/packages/${encodeURIComponent(config.packageAlias)}`;
    const response = await request('POST', url, {operation, request_json: requestJson || '{}'});
    return unwrapCodeEngineResponse(response);
  }

  function unwrapCodeEngineResponse(response) {
    let value = response;
    if (typeof value === 'string') {
      try {
        value = JSON.parse(value);
      } catch (error) {
        return value;
      }
    }
    if (!value || typeof value !== 'object') return value;
    if (value.status && String(value.status).toUpperCase() !== 'SUCCESS') {
      // stderr.log は配列とは限らない（文字列や欠落もあり得る）。Array.isArray で守らないと
      // .filter が例外になり、本来伝えたい Code Engine のエラー本文が握り潰されてしまう。
      const stderrLog = Array.isArray(value.stderr?.log) ? value.stderr.log.filter(Boolean).join(' ') : '';
      const detail = value.errorInformation?.message || value.errorInformation?.log || stderrLog || 'Code Engineの処理に失敗しました。';
      throw new Error(String(detail));
    }
    if (Object.prototype.hasOwnProperty.call(value, 'result') && (value.status || value.executionId || value.functionName || value.result?.ok !== undefined)) {
      return value.result;
    }
    return value;
  }

  function demoFunction(functionName, parameters) {
    if (functionName === 'register_transaction') {
      const payload = JSON.parse((parameters || {}).request_json || '{}');
      const location = demo.locations.find((row) => row.location_code === payload.location_code);
      const item = demo.items.find((row) => row.item_code === payload.item_code);
      const balance = demo.balances.find((row) => row.balance_key === `${payload.location_code}|${payload.item_code}`);
      const before = balance ? Number(balance.quantity) : 0;
      const quantity = Number(payload.quantity);
      const signed = payload.transaction_type === 'OUT' ? -quantity : quantity;
      if (!item || !location || !quantity || quantity <= 0) return Promise.resolve({ok: false, error: {code: 'VALIDATION_ERROR', message: '入力内容を確認してください。'}});
      if (before + signed < 0) return Promise.resolve({ok: false, error: {code: 'NEGATIVE_INVENTORY', message: '在庫数を超える出庫は登録できません。'}});
      const row = {transaction_id: `TRX-LOCAL-${Date.now()}`, request_id: payload.request_id, transaction_type: payload.transaction_type, item_code: item.item_code, item_name: item.item_name, location_code: location.location_code, location_name: location.location_name, quantity, signed_quantity: signed, balance_before: before, balance_after: before + signed, reason: payload.reason || '', operator_name: 'ローカルデモ', occurred_at: isoNow()};
      demo.transactions.unshift(row);
      if (balance) balance.quantity = row.balance_after;
      else demo.balances.push({balance_key: `${location.location_code}|${item.item_code}`, location_code: location.location_code, location_name: location.location_name, item_code: item.item_code, item_name: item.item_name, quantity: row.balance_after, minimum_quantity: 0, shortage_quantity: 0, is_shortage: false, last_transaction_at: row.occurred_at});
      return Promise.resolve({ok: true, transaction: clone(row), balance: {quantity: row.balance_after}, notification: {triggered: false}, demo: true});
    }
    if (functionName === 'get_inventory_state') return Promise.resolve({ok: true, user: {id: 'local-demo-user', name: 'ローカル利用者', email: '', isAdmin: true}, demo: true});
    if (functionName === 'start_shortage_notification') {
      const shortages = demo.balances.filter((row) => row.is_shortage && Number(row.shortage_quantity) > 0);
      if (!shortages.length) return Promise.resolve({ok: true, notification: {triggered: false, workflow_ready: false, reason: 'NO_SHORTAGE', shortage_count: 0}, demo: true});
      // ローカルデモは宛先メールを持たないため、実行導線の確認までを再現する。
      return Promise.resolve({ok: true, notification: {triggered: false, workflow_ready: false, reason: 'RECIPIENT_EMAIL_MISSING', shortage_count: shortages.length}, demo: true});
    }
    if (functionName === 'manage_master') {
      // ローカルプレビューでも管理者マスタCRUDを体験できるよう、共有demo配列を直接更新する。
      // 削除はライブと同じく物理削除で、依存ルール・派生残高も連鎖削除する（台帳=取引は残す）。
      const payload = JSON.parse((parameters || {}).request_json || '{}');
      const action = String(payload.action || '').toUpperCase();
      const codeOf = (raw) => String(raw || '').trim().toUpperCase();
      const named = (raw) => String(raw || '').trim();
      const flag = (raw) => (raw === undefined || raw === null ? true : Boolean(raw));
      if (action === 'LIST_MASTERS') return Promise.resolve({ok: true, items: clone(demo.items), locations: clone(demo.locations), rules: clone(demo.rules), demo: true});
      if (action === 'UPSERT_ITEM') {
        const item_code = codeOf(payload.item_code);
        if (!item_code || !named(payload.item_name)) return Promise.resolve({ok: false, error: {code: 'VALIDATION_ERROR', message: '品目コードと品目名を入力してください。'}});
        let row = demo.items.find((r) => r.item_code === item_code);
        const status = row ? 'updated' : 'created';
        if (!row) { row = {item_code}; demo.items.push(row); }
        Object.assign(row, {item_name: named(payload.item_name), category: named(payload.category), unit: named(payload.unit), qr_value: named(payload.qr_value) || `ITEM:${item_code}`, active: flag(payload.active)});
        return Promise.resolve({ok: true, status, record_type: 'ITEM', record: clone(row), demo: true});
      }
      if (action === 'UPSERT_LOCATION') {
        const location_code = codeOf(payload.location_code);
        if (!location_code || !named(payload.location_name)) return Promise.resolve({ok: false, error: {code: 'VALIDATION_ERROR', message: 'ロケーションコードとロケーション名を入力してください。'}});
        let row = demo.locations.find((r) => r.location_code === location_code);
        const status = row ? 'updated' : 'created';
        if (!row) { row = {location_code}; demo.locations.push(row); }
        Object.assign(row, {location_name: named(payload.location_name), zone: named(payload.zone), qr_value: named(payload.qr_value) || `LOC:${location_code}`, active: flag(payload.active)});
        return Promise.resolve({ok: true, status, record_type: 'LOCATION', record: clone(row), demo: true});
      }
      if (action === 'UPSERT_RULE') {
        const location_code = codeOf(payload.location_code);
        const item_code = codeOf(payload.item_code);
        if (!demo.items.some((r) => r.item_code === item_code)) return Promise.resolve({ok: false, error: {code: 'INVALID_ITEM', message: '有効な品目が見つかりません。'}});
        if (!demo.locations.some((r) => r.location_code === location_code)) return Promise.resolve({ok: false, error: {code: 'INVALID_LOCATION', message: '有効なロケーションが見つかりません。'}});
        const minimum = Number(payload.minimum_quantity);
        if (!Number.isFinite(minimum) || minimum < 0) return Promise.resolve({ok: false, error: {code: 'INVALID_MINIMUM_QUANTITY', message: '基準在庫は0以上の数値で指定してください。'}});
        const rule_key = `${location_code}|${item_code}`;
        let row = demo.rules.find((r) => r.rule_key === rule_key);
        const status = row ? 'updated' : 'created';
        if (!row) { row = {rule_key, location_code, item_code}; demo.rules.push(row); }
        Object.assign(row, {minimum_quantity: minimum, notification_enabled: flag(payload.notification_enabled), active: flag(payload.active)});
        return Promise.resolve({ok: true, status, record_type: 'RULE', record: clone(row), demo: true});
      }
      if (action === 'DELETE_ITEM' || action === 'DELETE_LOCATION' || action === 'DELETE_RULE') {
        const type = action.split('_')[1];
        const removeFrom = (arr, keep) => { const before = arr.length; const kept = arr.filter(keep); arr.length = 0; arr.push(...kept); return before - arr.length; };
        if (type === 'RULE') {
          const rule_key = `${codeOf(payload.location_code)}|${codeOf(payload.item_code)}`;
          if (!demo.rules.some((r) => r.rule_key === rule_key)) return Promise.resolve({ok: false, error: {code: 'MASTER_NOT_FOUND', message: '対象のマスタが見つかりません。'}});
          // ルール削除でしきい値は消えるが現在庫(残高)は残す。ライブの連鎖範囲に合わせる。
          const removed = {RULE: removeFrom(demo.rules, (r) => r.rule_key !== rule_key), ALERT_STATE: 0};
          return Promise.resolve({ok: true, status: 'deleted', record_type: 'RULE', deleted: removed, demo: true});
        }
        const field = type === 'ITEM' ? 'item_code' : 'location_code';
        const value = codeOf(type === 'ITEM' ? payload.item_code : payload.location_code);
        const masters = type === 'ITEM' ? demo.items : demo.locations;
        if (!masters.some((r) => r[field] === value)) return Promise.resolve({ok: false, error: {code: 'MASTER_NOT_FOUND', message: '対象のマスタが見つかりません。'}});
        // マスタ本体・依存ルール・派生残高を物理削除。取引(台帳)は監査証跡として保持する。
        const removed = {[type]: removeFrom(masters, (r) => r[field] !== value), RULE: removeFrom(demo.rules, (r) => r[field] !== value), BALANCE: removeFrom(demo.balances, (r) => r[field] !== value), ALERT_STATE: 0};
        return Promise.resolve({ok: true, status: 'deleted', record_type: type, deleted: removed, demo: true});
      }
      return Promise.resolve({ok: false, error: {code: 'UNSUPPORTED_MASTER_ACTION', message: '対応していないマスタ操作です。'}});
    }
    return Promise.reject(new Error(`Unsupported demo function: ${functionName}`));
  }

  async function getUser() {
    const env = global.domo && global.domo.env ? global.domo.env : {};
    if (isLocalPreview) return {id: 'local-demo-user', name: 'ローカル利用者', email: '', isAdmin: true, mode: 'demo'};
    if (!hasDomo) throw new Error('Domo SDKを読み込めませんでした。アプリを再読み込みしてください。');
    let details = {};
    try {
      if (env.userId) details = await request('GET', `/domo/users/v1/${encodeURIComponent(env.userId)}?includeDetails=true`);
    } catch (error) {
      details = {};
    }
    const email = String(details.emailAddress || env.userEmail || '').trim();
    // People API と domo.env でフィールド名が揺れる（displayName / name / userName…）。実名を
    // 最優先で拾い、無ければメール→空文字の順。仮名を返すと CE 由来の空値マージで良い名前を潰すため。
    const name = String(
      details.displayName || details.name || details.userName || details.fullName
      || env.userName || env.displayName || email
      || ''
    ).trim();
    return {
      id: String(env.userId || details.id || ''),
      name,
      email,
      isAdmin: Boolean(env.isAdmin || details.role === 'Admin'),
      mode: 'domo'
    };
  }

  async function loadInitialData() {
    const [records, user] = await Promise.all([
      getCollection(config.collections.records, 'records'),
      getUser()
    ]);
    const source = hasDomo ? records : null;
    const byType = (type, fallbackKey) => source
      ? source.filter((row) => String(row.record_type || '').toUpperCase() === type)
      : clone(demo[fallbackKey] || []);
    const items = byType('ITEM', 'items');
    const locations = byType('LOCATION', 'locations');
    const rules = byType('RULE', 'rules');
    const balances = byType('BALANCE', 'balances');
    const transactions = byType('TRANSACTION', 'transactions');
    const alerts = byType('ALERT_HISTORY', 'alerts');
    return {items, locations, rules, balances, transactions, alerts, user, mode: runtimeMode};
  }

  // ダッシュボードは「運用数値はライブ AppDB、AI 助言だけ遅延 DataFlow」で構成する。
  // 集計 DataFlow(dashboard_transform.py) は数分〜1日の遅延があり、それを主ソースにすると
  // 登録直後の現在庫がダッシュボードとドリルダウン(ライブ AppDB)で食い違う。そこで在庫・不足・
  // KPI・トレンドは常にライブ AppDB から算出し、TextGen がバッチ生成する AI_NOTE(在庫コメント)
  // だけを遅延 DataSet からベストエフォートで合流させる。prefetched を渡すと loadInitialData と
  // 同一スナップショットを共用し、二重取得と取得タイミング差(表示のちらつき)を無くす。
  async function loadDashboard(prefetched) {
    if (isLocalPreview) return buildDashboardRows(demo);
    let liveRows = null;
    try {
      let balances;
      let transactions;
      let alerts;
      if (prefetched && Array.isArray(prefetched.balances)) {
        ({balances, transactions, alerts} = prefetched);
      } else {
        const records = await getCollection(config.collections.records, 'records');
        const ofType = (type) => records.filter((row) => String(row.record_type || '').toUpperCase() === type);
        balances = ofType('BALANCE');
        transactions = ofType('TRANSACTION');
        alerts = ofType('ALERT_HISTORY');
      }
      liveRows = buildDashboardRows({balances, transactions, alerts});
    } catch (error) {
      // ライブ AppDB が読めないときだけ、遅延はあるが集計 DataFlow の全行を最後の拠り所にする。
      liveRows = null;
    }
    let datasetRows = null;
    try {
      const fetched = await request('GET', `/data/v1/${encodeURIComponent(config.dashboardAlias)}?limit=${config.network.dashboardRowLimit}`);
      if (Array.isArray(fetched)) datasetRows = fetched;
    } catch (error) {
      // 集計 DataFlow 未到達時は AI コメント無しで運用数値のみ表示する(機能低下は許容)。
    }
    if (!liveRows) return datasetRows || [];
    if (datasetRows) {
      datasetRows
        .filter((row) => String(row.record_type || '').toUpperCase() === 'AI_NOTE' && String(row.ai_summary || '').trim())
        .forEach((row) => liveRows.push(row));
    }
    return liveRows;
  }

  /** 検索ハンドル(コード・名称)を挿入順を保ったまま重複なく積む小さなヘルパ。 */
  function pushDistinct(list, value) {
    if (value && list.indexOf(value) === -1) list.push(value);
  }

  function buildDashboardRows(source) {
    const rows = [];
    const balances = source.balances || [];
    const transactions = source.transactions || [];
    const alerts = source.alerts || [];
    const total = balances.reduce((sum, row) => sum + Number(row.quantity || 0), 0);
    const shortage = balances.filter((row) => row.is_shortage === true || String(row.is_shortage).toLowerCase() === 'true');
    // 物理削除されたマスタの取引には CE が archived 印を付け、canonical な集計はそれを本日入出庫
    // KPI・7日トレンドから除外する。台帳ビューは監査証跡として残すので、集計用の作業配列だけ絞り込む。
    const activeTransactions = transactions.filter((row) => !(row.archived === true || String(row.archived).toLowerCase() === 'true'));
    rows.push({record_type: 'KPI', metric_key: 'TOTAL_QUANTITY', metric_value: total, label: '総在庫数'});
    rows.push({record_type: 'KPI', metric_key: 'ITEM_COUNT', metric_value: new Set(balances.map((row) => row.item_code)).size, label: '在庫品目'});
    rows.push({record_type: 'KPI', metric_key: 'SHORTAGE_COUNT', metric_value: shortage.length, label: '在庫不足'});
    // 「本日」はUTC暦日で数える。7日トレンド・KPIドリルダウン・集計DataFlow（dashboard_transform.py
    // は utc=True）が全てUTC日基準なので、ここだけローカル暦にすると件数が食い違う。occurred_atはUTC保存。
    const todayKey = new Date().toISOString().slice(0, 10);
    const todayTransactions = activeTransactions.filter((row) => String(row.occurred_at || '').slice(0, 10) === todayKey);
    rows.push({record_type: 'KPI', metric_key: 'TODAY_IN_COUNT', metric_value: todayTransactions.filter((row) => row.transaction_type === 'IN').length, label: '本日の入庫'});
    rows.push({record_type: 'KPI', metric_key: 'TODAY_OUT_COUNT', metric_value: todayTransactions.filter((row) => row.transaction_type === 'OUT').length, label: '本日の出庫'});

    // ITEM_STOCK / LOCATION は表示ラベル(名称)で集約するが、検索ヒット用にコードと名称も併せて載せる。
    // これが無いと在庫のある品目をコード(例: ITEM-11)で検索してもダッシュボードでヒットしない。
    // 表示は label のみを使うので、コード・名称の付与は検索の網羅性だけを広げ、見た目は変えない。
    const items = {};
    balances.forEach((row) => {
      const label = row.item_name || row.item_code || '未設定';
      const bucket = items[label] || (items[label] = {value: 0, codes: [], names: []});
      bucket.value += Number(row.quantity || 0);
      pushDistinct(bucket.codes, row.item_code && String(row.item_code));
      pushDistinct(bucket.names, row.item_name && String(row.item_name));
    });
    Object.entries(items).forEach(([label, bucket]) => rows.push({
      record_type: 'ITEM_STOCK', label, metric_value: bucket.value,
      item_code: bucket.codes.join(' ') || undefined,
      item_name: bucket.names.join(' ') || undefined
    }));
    const locations = {};
    balances.forEach((row) => {
      const label = row.location_name || row.location_code || '未設定';
      const bucket = locations[label] || (locations[label] = {value: 0, codes: [], names: []});
      bucket.value += Number(row.quantity || 0);
      pushDistinct(bucket.codes, row.location_code && String(row.location_code));
      pushDistinct(bucket.names, row.location_name && String(row.location_name));
    });
    Object.entries(locations).forEach(([label, bucket]) => rows.push({
      record_type: 'LOCATION', label, metric_value: bucket.value,
      location_code: bucket.codes.join(' ') || undefined,
      location_name: bucket.names.join(' ') || undefined
    }));

    shortage.forEach((row) => rows.push(Object.assign({}, row, {record_type: 'SHORTAGE'})));
    // 「滞留在庫」のしきい値は config.analytics.dormantThresholdDays。正準の定義はダッシュボード
    // DataFlow 側にあり、ここは DataFlow 未到達時のフォールバック集計なので同じ日数へ揃える。
    const dormantThresholdDays = config.analytics.dormantThresholdDays;
    balances.filter((row) => daysBetween(row.last_transaction_at, new Date()) > dormantThresholdDays).forEach((row) => rows.push(Object.assign({}, row, {record_type: 'DORMANT', age_days: daysBetween(row.last_transaction_at, new Date())})));

    const trend = {};
    // トレンドの表示日数は config.analytics.trendWindowDays（直近N日）。窓のキーを todayKey や
    // occurred_at.slice(0,10) と揃えるため UTC で日を減算する（ローカル暦だと DST 切替日にずれる）。
    for (let offset = config.analytics.trendWindowDays - 1; offset >= 0; offset -= 1) {
      const date = new Date();
      date.setUTCDate(date.getUTCDate() - offset);
      const key = date.toISOString().slice(0, 10);
      trend[key] = {in: 0, out: 0};
    }
    activeTransactions.forEach((row) => {
      const key = String(row.occurred_at || '').slice(0, 10);
      if (!trend[key]) return;
      // 集計DataFlow と同じく IN/OUT だけを流量として数える。
      if (row.transaction_type === 'OUT') trend[key].out += Number(row.quantity || 0);
      else if (row.transaction_type === 'IN') trend[key].in += Number(row.quantity || 0);
    });
    Object.entries(trend).forEach(([date_key, values]) => rows.push({record_type: 'TREND', date_key, inbound_quantity: values.in, outbound_quantity: values.out}));
    // 通知履歴は created_at 降順で最新 alertHistoryLimit 件だけを載せる（集計DataFlow と並び・件数を
    // 揃える）。文字列比較でよいのは created_at が UTC ISO 8601（辞書順＝時系列順）で保存されるため。
    alerts
      .slice()
      .sort((left, right) => {
        const byDate = String(right.created_at || '').localeCompare(String(left.created_at || ''));
        if (byDate !== 0) return byDate;
        // created_at 同値時は alert_id 昇順で確定（集計DataFlow のタイブレークに揃え、境界での揺れを防ぐ）。
        return String(left.alert_id || '').localeCompare(String(right.alert_id || ''));
      })
      .slice(0, config.analytics.alertHistoryLimit)
      .forEach((row) => rows.push(Object.assign({}, row, {record_type: 'ALERT'})));
    return rows;
  }

  function daysBetween(value, date) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return 0;
    return Math.floor((date.getTime() - parsed.getTime()) / 86400000);
  }

  // 公開面は app.js の実行時入口（loadInitialData / loadDashboard / callFunction）と、
  // 単体テストが直接叩く継ぎ目（mode / getCollection / buildDashboardRows＝削除するとテストが壊れる）に限る。
  // 通知Workflowの起動はフロントでは行わない（Code Engine がサーバー側で最新版を解決して開始する）。
  global.InventoryData = Object.freeze({
    mode: runtimeMode,
    loadInitialData,
    loadDashboard,
    getCollection,
    callFunction,
    buildDashboardRows
  });
})(window);
