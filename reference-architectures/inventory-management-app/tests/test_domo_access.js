const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../pro-code/domo-access.js'), 'utf8');

function loadDataModule({protocol = 'https:', hostname = 'maintenance-instance.domo.com', domo, clock = Date, network} = {}) {
  const window = {
    location: {protocol, hostname},
    InventoryConfig: {
      collections: {records: 'inventory_management_records'},
      packageAlias: 'inventoryApi',
      dashboardAlias: 'inventoryDashboard',
      // config.js（本番）と同じ設定源をミラーする。domo-access.js は読み込み時に
      // network.requestTimeoutMs を、buildDashboardRows で analytics.* を参照するため必須。
      // network はページングの pageSize を差し替えたいテスト向けに上書き可能にする。
      network: network || {requestTimeoutMs: 12000, dashboardRowLimit: 50000, queryPageSize: 10000},
      analytics: {trendWindowDays: 7, dormantThresholdDays: 30, alertHistoryLimit: 30}
    }
  };
  if (domo) window.domo = domo;
  // clock は「現在時刻」を固定したいテスト用の Date 差し替え口。日境界の挙動を
  // 実行環境のタイムゾーンに依存せず検証するために使う（既定は本物の Date）。
  vm.runInNewContext(source, {window, console, Date: clock, Promise, Set});
  return window.InventoryData;
}

/** 現在時刻を固定した Date 実装を作る（引数なし new Date() だけ固定、他は本物に委譲）。 */
function fixedClock(nowIso) {
  return class FixedDate extends Date {
    constructor(...args) {
      if (args.length === 0) super(nowIso);
      else super(...args);
    }
    static now() {
      return new Date(nowIso).getTime();
    }
  };
}

test('Domo上ではSDKを使い、demoへ切り替えない', async () => {
  const calls = [];
  const data = loadDataModule({
    domo: {
      get: async () => [],
      post: async (url) => {
        calls.push(url);
        return [];
      },
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });

  assert.equal(data.mode, 'domo');
  await data.getCollection('inventory_management_records', 'items');
  // 空の1ページ（上限未満）なので1往復で終わる。ページングの limit/offset を query string に付ける。
  assert.deepEqual(calls, ['/domo/datastores/v2/collections/inventory_management_records/documents/query?limit=10000&offset=0']);
});

test('AppDBの取得は limit/offset のクエリ文字列で全ページを走査する', async () => {
  // ページ上限ちょうど(pageSize)を返すページが続く限り offset を進め、上限未満のページで止める。
  // これがないと台帳が1万件を超えたとき初期ロード・フォールバック集計が先頭ページで静かに欠ける。
  const pageSize = 2;
  const calls = [];
  const wrap = (id, itemCode) => ({id, content: {record_type: 'ITEM', item_code: itemCode}});
  const pages = [
    [wrap('d1', 'ITEM-001'), wrap('d2', 'ITEM-002')], // 満杯 → 次ページへ
    [wrap('d3', 'ITEM-003'), wrap('d4', 'ITEM-004')], // 満杯 → 次ページへ
    [wrap('d5', 'ITEM-005')]                           // 上限未満 → ここで停止
  ];
  const data = loadDataModule({
    domo: {
      get: async () => [],
      post: async (url) => {
        calls.push(url);
        return pages.shift() || [];
      },
      env: {userId: '123'}
    },
    network: {requestTimeoutMs: 12000, dashboardRowLimit: 50000, queryPageSize: pageSize}
  });

  const rows = await data.getCollection('inventory_management_records', 'items');
  assert.equal(rows.length, 5, '全ページ分の行を連結して返す');
  assert.equal(rows.map((row) => row.item_code).join(','), 'ITEM-001,ITEM-002,ITEM-003,ITEM-004,ITEM-005');
  assert.equal(rows[0]._documentId, 'd1', 'content ラッパーを外し _documentId を保持する');
  assert.deepEqual(calls, [
    '/domo/datastores/v2/collections/inventory_management_records/documents/query?limit=2&offset=0',
    '/domo/datastores/v2/collections/inventory_management_records/documents/query?limit=2&offset=2',
    '/domo/datastores/v2/collections/inventory_management_records/documents/query?limit=2&offset=4'
  ]);
});

test('v2 queryが失敗したらv1 GETフォールバックも limit/offset でページ送りする', async () => {
  const pageSize = 2;
  const getCalls = [];
  const wrap = (id, itemCode) => ({id, content: {record_type: 'ITEM', item_code: itemCode}});
  const pages = [
    [wrap('g1', 'ITEM-001'), wrap('g2', 'ITEM-002')],
    [wrap('g3', 'ITEM-003')]
  ];
  const data = loadDataModule({
    domo: {
      get: async (url) => {
        getCalls.push(url);
        return pages.shift() || [];
      },
      post: async () => { throw new Error('v2 query 不可'); },
      env: {userId: '123'}
    },
    network: {requestTimeoutMs: 12000, dashboardRowLimit: 50000, queryPageSize: pageSize}
  });

  const rows = await data.getCollection('inventory_management_records', 'items');
  assert.equal(rows.map((row) => row.item_code).join(','), 'ITEM-001,ITEM-002,ITEM-003');
  assert.deepEqual(getCalls, [
    '/domo/datastores/v1/collections/inventory_management_records/documents/?limit=2&offset=0',
    '/domo/datastores/v1/collections/inventory_management_records/documents/?limit=2&offset=2'
  ]);
});

test('DomoドメインでSDKがない場合はerrorとし、demoデータを返さない', async () => {
  const data = loadDataModule();

  assert.equal(data.mode, 'error');
  await assert.rejects(data.loadInitialData(), /Domo SDK/);
});

test('localhostではSDKなしでもローカルdemoを利用できる', async () => {
  const data = loadDataModule({protocol: 'http:', hostname: 'localhost'});
  const loaded = await data.loadInitialData();

  assert.equal(data.mode, 'demo');
  assert.equal(loaded.mode, 'demo');
  assert.equal(loaded.user.name, 'ローカル利用者');
  assert.equal(loaded.items.length, 5);
});

test('Code Engineの実行ラッパーを外して業務結果を返す', async () => {
  const calls = [];
  const data = loadDataModule({
    domo: {
      get: async () => [],
      post: async (url, body) => {
        calls.push({url, body});
        return {
          executionId: 'execution-1',
          functionName: 'inventory_api',
          status: 'SUCCESS',
          result: {ok: true, user: {id: '123', name: 'Domo利用者'}}
        };
      },
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });

  const result = await data.callFunction('get_inventory_state', {request_json: '{}'});

  assert.equal(result.ok, true);
  assert.equal(result.user.id, '123');
  assert.equal(calls[0].url, '/domo/codeengine/v2/packages/inventoryApi');
  assert.equal(calls[0].body.operation, 'GET_STATE');
  assert.deepEqual(JSON.parse(calls[0].body.request_json), {});
});

test('Code Engineの失敗ステータスはエラー本文を投げて握り潰さない（stderr.logは非配列でも安全）', async () => {
  // status が SUCCESS 以外なら unwrap は throw して呼び出し側にエラーを伝える。
  // 詳細は errorInformation.message → errorInformation.log → stderr.log(join) → 既定文言 の優先順。
  const withMessage = loadDataModule({
    domo: {
      get: async () => [],
      post: async () => ({status: 'ERROR', errorInformation: {message: '在庫の更新権限がありません。'}}),
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });
  await assert.rejects(
    withMessage.callFunction('get_inventory_state', {request_json: '{}'}),
    /在庫の更新権限がありません。/
  );

  // stderr.log は配列とは限らない。文字列で来ても Array.isArray ガードにより .filter が例外にならず、
  // CE エラーを TypeError で握り潰さず既定文言へフォールバックする（ガードを外すと回帰でこのテストが落ちる）。
  const stringStderr = loadDataModule({
    domo: {
      get: async () => [],
      post: async () => ({status: 'FAILED', stderr: {log: 'これは配列ではない'}}),
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });
  await assert.rejects(
    stringStderr.callFunction('get_inventory_state', {request_json: '{}'}),
    /Code Engineの処理に失敗しました。/
  );

  // stderr.log が配列なら Boolean で間引いて join し、詳細として伝える。
  const arrayStderr = loadDataModule({
    domo: {
      get: async () => [],
      post: async () => ({status: 'FAILED', stderr: {log: ['接続に失敗', '', 'リトライ上限']}}),
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });
  await assert.rejects(
    arrayStderr.callFunction('get_inventory_state', {request_json: '{}'}),
    /接続に失敗 リトライ上限/
  );
});

test('ログイン利用者の表示名はPeople APIの実名を最優先し、無ければ環境値・メールへ落とす', async () => {
  // People API が実名(displayName)を返すときは、それを表示名にする。
  const withDisplayName = loadDataModule({
    domo: {
      get: async (url) => (url.startsWith('/domo/users/v1/')
        ? {id: '123', displayName: '在庫 太郎', emailAddress: 'taro@example.invalid'}
        : []),
      post: async () => [],
      env: {userId: '123', userName: 'env-fallback', userEmail: 'env@example.invalid'}
    }
  });
  const resolved = await withDisplayName.loadInitialData();
  assert.equal(resolved.user.name, '在庫 太郎');
  assert.equal(resolved.user.email, 'taro@example.invalid');

  // People API が実名を返さないときは環境変数の userName をログイン名に使う。
  const withEnvName = loadDataModule({
    domo: {
      get: async (url) => (url.startsWith('/domo/users/v1/') ? {id: '123'} : []),
      post: async () => [],
      env: {userId: '123', userName: 'env-login-name'}
    }
  });
  const envResolved = await withEnvName.loadInitialData();
  assert.equal(envResolved.user.name, 'env-login-name');

  // 実名が全く取れないときはメールをログイン名に使い、仮名は捏造しない。
  const withEmailOnly = loadDataModule({
    domo: {
      get: async (url) => (url.startsWith('/domo/users/v1/') ? {id: '123', emailAddress: 'only-mail@example.invalid'} : []),
      post: async () => [],
      env: {userId: '123'}
    }
  });
  const mailResolved = await withEmailOnly.loadInitialData();
  assert.equal(mailResolved.user.name, 'only-mail@example.invalid');

  // 実装に固定プレースホルダ（Domo利用者）を残さない。
  assert.doesNotMatch(source, /Domo利用者/);
});

test('通知Workflowの起動はフロントに持たない（CEがサーバー側で最新版を起動する）', async () => {
  // 起動される版がカード配線のスナップショットに固定され、Workflow改版のたびに再埋め込みが
  // 必要だった旧経路（/domo/workflow/v1/models/{alias}/start）を廃止する。起動は Code Engine
  // （inventory_api の REGISTER／NOTIFY_NOW）が実行時に最新の有効版を解決して行う。
  const calls = [];
  const data = loadDataModule({
    domo: {
      get: async () => [],
      post: async (url, body) => {
        calls.push({url, body});
        return [];
      },
      env: {userId: '123', userName: 'Domo利用者'}
    }
  });

  assert.equal(typeof data.startWorkflow, 'undefined');
  // 旧・監査更新の縦型関数も公開しない（起動結果の記録は CE が同一操作内で行う）。
  await assert.rejects(
    data.callFunction('update_notification_status', {request_json: '{}'}),
    /Unsupported inventory operation/
  );
  assert.equal(calls.length, 0);
});

test('フォールバックのトレンドは想定外の種別を入庫・出庫のどちらにも数えない', () => {
  // 正準の集計DataFlow（dashboard_transform.py）と同じく、入出庫の「流量」は IN/OUT だけ。
  // 想定外の種別が混ざっても入庫・出庫の両方から除外する（データ不整合で数字が歪まない）。
  // フォールバック集計だけが想定外種別を入庫へ混ぜて数字が食い違う退行を、件数で捕捉する。
  const data = loadDataModule({clock: fixedClock('2026-08-08T12:00:00.000Z')});
  const transactions = [
    {transaction_type: 'IN', quantity: 10, occurred_at: '2026-08-08T03:00:00.000Z'},
    {transaction_type: 'OUT', quantity: 3, occurred_at: '2026-08-08T04:00:00.000Z'},
    {transaction_type: 'UNKNOWN', quantity: 5, occurred_at: '2026-08-08T05:00:00.000Z'}
  ];
  const rows = data.buildDashboardRows({balances: [], transactions, alerts: []});
  const today = rows.filter((row) => row.record_type === 'TREND').find((row) => row.date_key === '2026-08-08');
  // 想定外種別の5が入庫へ混ざれば15になる。混ざっていないことを確認する。
  assert.equal(today.inbound_quantity, 10);
  assert.equal(today.outbound_quantity, 3);
});

test('フォールバックの本日KPIはUTC暦日で数え、内訳ドロワー・トレンドと一致する', () => {
  // 実行タイムゾーンをUTC+9へ固定する。こうするとローカル暦日判定とUTC暦日判定で
  // 分類が割れる取引を用意でき、CIがUTCでもローカル暦日への退行を「件数」で確実に捕捉できる
  // （UTC実行のままだと両判定の件数が偶然一致し、退行がすり抜ける）。
  const savedTz = process.env.TZ;
  process.env.TZ = 'Asia/Tokyo';
  try {
    // 現在時刻もUTCで固定する（UTC暦日=2026-08-08／JSTでは2026-08-09 07:00）。
    const data = loadDataModule({clock: fixedClock('2026-08-08T22:00:00.000Z')});
    const transactions = [
      {transaction_type: 'IN', quantity: 1, occurred_at: '2026-08-08T14:00:00.000Z'},  // UTC=08-08(当日) / JST=08-08→判定が割れる
      {transaction_type: 'IN', quantity: 1, occurred_at: '2026-08-08T20:00:00.000Z'},  // UTC=08-08(当日) / JST=08-09
      {transaction_type: 'IN', quantity: 1, occurred_at: '2026-08-08T23:30:00.000Z'},  // UTC=08-08(当日) / JST=08-09
      {transaction_type: 'OUT', quantity: 2, occurred_at: '2026-08-08T10:00:00.000Z'}, // UTC=08-08(当日) / JST=08-08→判定が割れる
      {transaction_type: 'IN', quantity: 1, occurred_at: '2026-08-07T23:59:00.000Z'}   // UTC=08-07(前日)
    ];
    const rows = data.buildDashboardRows({balances: [], transactions, alerts: []});
    const kpi = (key) => rows.find((row) => row.record_type === 'KPI' && row.metric_key === key).metric_value;

    // UTC当日はIN 3件・OUT 1件。ローカル暦日(JST)判定へ退行すると14:00Z INと10:00Z OUTが
    // 前日扱いで除外され IN=2・OUT=0 になるため、この件数アサーションが退行を確実に捕捉する。
    assert.equal(kpi('TODAY_IN_COUNT'), 3);
    assert.equal(kpi('TODAY_OUT_COUNT'), 1);

    // 最新トレンドバケットのdate_key（app.jsのドリルダウンが基準にする値）が当日UTCと一致し、
    // その日のIN件数がKPIと一致する＝カード・内訳・トレンドが同じ暦日で揃う。
    const trendRows = rows.filter((row) => row.record_type === 'TREND');
    const latestKey = trendRows[trendRows.length - 1].date_key;
    assert.equal(latestKey, '2026-08-08');
    const drilldownInCount = transactions.filter(
      (row) => row.transaction_type === 'IN' && String(row.occurred_at).slice(0, 10) === latestKey
    ).length;
    assert.equal(drilldownInCount, kpi('TODAY_IN_COUNT'));

    // ローカル暦日で判定していた旧sameDayが復活していないこと（名称ベースの退行ガード）。
    assert.doesNotMatch(source, /\bsameDay\b/);
  } finally {
    // タイムゾーン差し替えを後続テストへ漏らさない。
    if (savedTz === undefined) delete process.env.TZ;
    else process.env.TZ = savedTz;
  }
});

test('7日トレンド窓のキーはUTC暦日で採番し、DST切替日でも欠け・重複が出ない', () => {
  // トレンド窓のキーは todayKey（new Date().toISOString() 由来＝UTC暦日）や取引の
  // occurred_at.slice(0,10)（同じくUTC暦日）と揃える必要がある。ローカル暦での日付減算
  // （setDate/getDate）だと、DSTを持つタイムゾーンの切替日に壁時計時刻を保ったまま日をまたぎ、
  // UTC暦日として読むと1日ぶん欠け・重複する。実際 America/New_York・2026-03-08T23:00Z（春の
  // 切替直後）では旧ロジックが 03-02 を落として 03-08 を重複させ、窓が6日ぶんに縮む。
  const savedTz = process.env.TZ;
  process.env.TZ = 'America/New_York';
  try {
    const data = loadDataModule({clock: fixedClock('2026-03-08T23:00:00.000Z')});
    const rows = data.buildDashboardRows({balances: [], transactions: [], alerts: []});
    const trendKeys = rows.filter((row) => row.record_type === 'TREND').map((row) => row.date_key);

    // 7日ぶんのバケットが「欠け・重複なく」連続し、末尾は当日UTC(todayKey)に一致する。
    assert.equal(trendKeys.length, 7, 'トレンドは常に trendWindowDays 件');
    assert.equal(new Set(trendKeys).size, 7, 'DST切替日でもキーが重複しない');
    assert.equal(
      trendKeys.join(','),
      '2026-03-02,2026-03-03,2026-03-04,2026-03-05,2026-03-06,2026-03-07,2026-03-08',
      'UTC暦日で連続する7日（旧ローカル暦だと 03-02 が落ち 03-08 が重複する）'
    );
    assert.equal(trendKeys[trendKeys.length - 1], '2026-03-08', '末尾は当日UTC(todayKey)');

    // ローカル暦での日付減算（setDate/getDate）がトレンド窓に復活していないこと。
    // ※ daysAgo（demo用の日付生成ヘルパ）は setDate を使うため、窓生成の UTC 版採用を正の
    //   アサーションで固定する（blanket な doesNotMatch(/setDate/) は daysAgo に誤爆する）。
    assert.match(source, /setUTCDate\(\s*[A-Za-z_$][\w$]*\.getUTCDate\(\)\s*-\s*offset\s*\)/);
  } finally {
    if (savedTz === undefined) delete process.env.TZ;
    else process.env.TZ = savedTz;
  }
});

test('フォールバック集計は不足(SHORTAGE)と滞留(DORMANT)を正準DataFlowと同じ規則で行に起こす', () => {
  // is_shortage は真偽値と文字列 'true' の両方（AppDBの返却型ゆらぎ）で不足と見なす。
  // 滞留は最終取引からの経過日数 > dormantThresholdDays(=30) のみが対象。閾値付近を境界で確かめる。
  const data = loadDataModule({clock: fixedClock('2026-08-08T12:00:00.000Z')});
  const balances = [
    {balance_key: 'LOC-01|ITEM-001', item_code: 'ITEM-001', item_name: '安全手袋', location_code: 'LOC-01', location_name: '中央倉庫', quantity: 4, minimum_quantity: 10, shortage_quantity: 6, is_shortage: true, last_transaction_at: '2026-08-07T00:00:00.000Z'},
    {balance_key: 'LOC-02|ITEM-002', item_code: 'ITEM-002', item_name: '保護メガネ', location_code: 'LOC-02', location_name: '組立エリア', quantity: 2, minimum_quantity: 5, shortage_quantity: 3, is_shortage: 'true', last_transaction_at: '2026-08-08T00:00:00.000Z'},
    {balance_key: 'LOC-03|ITEM-003', item_code: 'ITEM-003', item_name: '作業帽', location_code: 'LOC-03', location_name: '倉庫奥', quantity: 50, minimum_quantity: 5, shortage_quantity: 0, is_shortage: false, last_transaction_at: '2026-06-01T00:00:00.000Z'}
  ];
  const rows = data.buildDashboardRows({balances, transactions: [], alerts: []});

  // 不足は is_shortage が true / 'true' の2件のみ。false や欠落を巻き込まない。
  // （buildDashboardRows の戻り配列は vm 実行コンテキスト側の Array なので、prototype 同一性を問う
  //  deepStrictEqual は使えない。ここは件数・並びが本質なので join した文字列で値比較する。）
  const shortage = rows.filter((row) => row.record_type === 'SHORTAGE');
  assert.equal(shortage.map((row) => row.item_code).sort().join(','), 'ITEM-001,ITEM-002');
  const shortageKpi = rows.find((row) => row.record_type === 'KPI' && row.metric_key === 'SHORTAGE_COUNT');
  assert.equal(shortageKpi.metric_value, 2);

  // 滞留は 30日超のITEM-003だけ。直近取引(1日前・当日)は滞留に含めない。
  const dormant = rows.filter((row) => row.record_type === 'DORMANT');
  assert.equal(dormant.map((row) => row.item_code).join(','), 'ITEM-003');
  assert.ok(dormant[0].age_days > 30, '滞留の経過日数は閾値を超えていること');
});

test('フォールバック集計は在庫のある品目・ロケーションにコードと名称を載せ、コード検索でヒットさせる', () => {
  // ITEM_STOCK / LOCATION は表示ラベル(名称)で集約するが、コードでも検索できるよう item_code /
  // location_code を併せて載せる。これが無いと在庫のある品目をコード(例: ITEM-11)で検索しても
  // ダッシュボードでヒットしない（実運用で報告された不具合の回帰ガード）。表示は label のみ使う。
  const data = loadDataModule();
  const balances = [
    {balance_key: 'LOC-02|ITEM-11', item_code: 'ITEM-11', item_name: 'オリーブオイル', location_code: 'LOC-02', location_name: '組立エリア', quantity: 5, is_shortage: false, last_transaction_at: '2026-08-11T00:00:00.000Z'}
  ];
  const rows = data.buildDashboardRows({balances, transactions: [], alerts: []});
  const item = rows.find((row) => row.record_type === 'ITEM_STOCK');
  // 表示ラベルは名称のまま。コード・名称は検索ハンドルとして併記する。
  assert.equal(item.label, 'オリーブオイル');
  assert.equal(item.item_code, 'ITEM-11');
  assert.equal(item.item_name, 'オリーブオイル');
  const location = rows.find((row) => row.record_type === 'LOCATION');
  assert.equal(location.label, '組立エリア');
  assert.equal(location.location_code, 'LOC-02');
  assert.equal(location.location_name, '組立エリア');
});

test('フォールバック集計は archived（物理削除マスタ）取引を本日KPI・トレンドから除外する', () => {
  // 物理削除された ITEM/LOCATION の取引には CE が archived 印を付け、canonical な RECALCULATE と
  // 集計DataFlow は本日入出庫KPI・7日トレンドから除外する（残高は既に BALANCE から消えている）。
  // フォールバック集計も同じ基準で archived を落とし、DataFlow到達時とフロー集計を一致させる。
  const data = loadDataModule({clock: fixedClock('2026-08-08T12:00:00.000Z')});
  const transactions = [
    // archived 済み（削除マスタの当日フロー）は数えない。真偽値と文字列 'true' の両方を弾く。
    {transaction_type: 'IN', quantity: 50, occurred_at: '2026-08-08T03:00:00.000Z', archived: true},
    {transaction_type: 'OUT', quantity: 20, occurred_at: '2026-08-08T04:00:00.000Z', archived: 'true'},
    // 生存取引（archived なし/ 'false'）だけが計上される。
    {transaction_type: 'IN', quantity: 8, occurred_at: '2026-08-08T05:00:00.000Z'},
    {transaction_type: 'OUT', quantity: 2, occurred_at: '2026-08-08T06:00:00.000Z', archived: 'false'}
  ];
  const rows = data.buildDashboardRows({balances: [], transactions, alerts: []});
  const kpi = (key) => rows.find((row) => row.record_type === 'KPI' && row.metric_key === key).metric_value;
  // archived を数えれば本日入庫=2/出庫=2。生存分だけの 1/1 であること。
  assert.equal(kpi('TODAY_IN_COUNT'), 1);
  assert.equal(kpi('TODAY_OUT_COUNT'), 1);
  const today = rows.filter((row) => row.record_type === 'TREND').find((row) => row.date_key === '2026-08-08');
  // archived の 50/20 が混ざれば 58/22。生存分だけの 8/2 であること。
  assert.equal(today.inbound_quantity, 8);
  assert.equal(today.outbound_quantity, 2);
});

test('フォールバックの通知履歴はcreated_at降順で最新alertHistoryLimit件だけを載せる', () => {
  // 正準の集計DataFlow（dashboard_transform.py）は ALERT_HISTORY を created_at 降順でキャップする。
  // 入力を「古い→新しい」の昇順で渡し、素の slice(0,N) なら最古のN件が残る配置にしておく。
  // 修正後は降順ソートしてからキャップするため最新N件が残る＝この件数・並びが退行を捕捉する。
  const data = loadDataModule({clock: fixedClock('2026-08-08T12:00:00.000Z')});
  const base = new Date('2026-01-01T00:00:00.000Z').getTime();
  const alerts = [];
  for (let index = 0; index < 35; index += 1) {
    alerts.push({
      alert_id: `ALERT-${String(index).padStart(3, '0')}`,
      event_type: 'SHORTAGE',
      notification_status: 'PENDING',
      created_at: new Date(base + index * 60000).toISOString()
    });
  }
  const rows = data.buildDashboardRows({balances: [], transactions: [], alerts});
  const alertRows = rows.filter((row) => row.record_type === 'ALERT');

  // 上限30件（テスト設定 alertHistoryLimit）でキャップされること。
  assert.equal(alertRows.length, 30);
  // 先頭は最新(created_at 最大)。素の slice なら最古の ALERT-000 が先頭に来て落第する。
  assert.equal(alertRows[0].alert_id, 'ALERT-034');
  assert.equal(alertRows[alertRows.length - 1].alert_id, 'ALERT-005');
  // 最古5件(000〜004)は最新30件に入らないため落ちる。
  assert.equal(alertRows.some((row) => row.alert_id === 'ALERT-000'), false);
});
