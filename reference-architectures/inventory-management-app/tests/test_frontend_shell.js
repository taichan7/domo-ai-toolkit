const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../pro-code/index.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '../pro-code/app.css'), 'utf8');
const app = fs.readFileSync(path.join(__dirname, '../pro-code/app.js'), 'utf8');
const qr = fs.readFileSync(path.join(__dirname, '../pro-code/qr-scanner.js'), 'utf8');
const access = fs.readFileSync(path.join(__dirname, '../pro-code/domo-access.js'), 'utf8');
const boot = fs.readFileSync(path.join(__dirname, '../pro-code/boot-diagnostics.js'), 'utf8');
const configSource = fs.readFileSync(path.join(__dirname, '../pro-code/config.js'), 'utf8');
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../pro-code/manifest.json'), 'utf8'));
const codeEngineAsset = JSON.parse(fs.readFileSync(path.join(__dirname, '../code-engine/asset.json'), 'utf8'));

test('UIで参照する線画アイコンがすべて定義されている', () => {
  const symbolIds = new Set([...html.matchAll(/<symbol\s+id="([^"]+)"/g)].map((match) => match[1]));
  const iconRefs = [...html.matchAll(/<use\s+href="#([^"]+)"/g)].map((match) => match[1]);

  assert.ok(iconRefs.length > 0);
  iconRefs.forEach((iconRef) => assert.ok(symbolIds.has(iconRef), `Missing SVG symbol: ${iconRef}`));
});

test('業務UIテーマに旧デモ向け装飾を戻さない', () => {
  assert.doesNotMatch(css, /linear-gradient/);
  assert.doesNotMatch(css, /#(?:0145f1|0ca9ff|1fa9ff|59d0ff|9ef0eb)/i);
  assert.doesNotMatch(html, /<span>[⇄▥◷⚙▣⌕]</);
  assert.match(css, /\.operation-grid\s*\{[^}]*align-items:\s*start/s);
  assert.match(css, /\.context-panel\s*\{[^}]*position:\s*sticky/s);
});

test('参照する全CSSカスタムプロパティが定義済み（別パレット由来の未定義トークン混入を防ぐ）', () => {
  // 過去に別アプリのパレット名（--primary/--text）を参照し、accent-color等が端末既定色へ
  // 落ちる「詰めの甘さ」が混入した。定義漏れのトークン参照を検出して恒久的に防ぐ。
  const defined = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
  const referenced = new Set([...css.matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((m) => m[1]));
  const undefinedRefs = [...referenced].filter((name) => !defined.has(name));
  assert.deepEqual(undefinedRefs, [], `未定義のCSSカスタムプロパティ参照: ${undefinedRefs.join(', ')}`);
});

test('トークン化した低コントラスト/非トークンのベタ色を能動値へ戻さない', () => {
  // 可読性（コントラスト）とパレット一貫性のため、旧ベタ色を var(--muted)/var(--orange-600)/
  // var(--line-soft) 等へ寄せた。コメント（/* ... */）は「旧 #xxxxxx は…」と由来を残すため、
  // 能動値の検査からは除外して比較する（コメント内の言及で誤検知しない）。
  const activeCss = css.replace(/\/\*[\s\S]*?\*\//g, '');
  // #eef3fc/#eaf2fb/#f6f9fe は選択・強調面色として散っていた近似青→var(--surface-selected)/
  // var(--surface-muted) へ集約。#6f2f2f/#fff5f5/#7f4b4b は起動エラー枠を赤トークン
  // var(--red-600)/var(--red-100) へ寄せた。#eef2fb は --surface-selected のトークン値
  // 本体なので退役対象に含めない（含めると :root の定義行で誤検知する）。
  ['#79838f', '#7f8a97', '#97a6b8', '#8f3d12', '#9a4a16', '#e6eaf3', '#5f596d',
   '#eef3fc', '#eaf2fb', '#f6f9fe', '#6f2f2f', '#fff5f5', '#7f4b4b'].forEach((hex) =>
    assert.doesNotMatch(activeCss, new RegExp(hex, 'i'), `トークン化前のベタ色 ${hex} が能動値に復活している`));
});

test('調整(ADJUST)は概念ごと廃止し、UIから完全に取り除く', () => {
  // リファレンスアーキテクチャは入庫/出庫の2種別だけで在庫の増減を説明する。
  // 種別トグルにも履歴フィルタにも ADJUST/調整 を復活させない（退行ガード）。
  assert.doesNotMatch(html, /data-type="ADJUST"/, '種別トグルに ADJUST ボタンが残っている');
  assert.doesNotMatch(html, /<option value="ADJUST"/, '履歴フィルタに 調整 の選択肢が残っている');
  assert.doesNotMatch(app, /'ADJUST'/, "app.js に 'ADJUST' 分岐が残っている");
});

test('トースト領域は aria-live=polite のみとし、aria-atomic で古いトーストを読み直させない', () => {
  // 各トーストは role=alert / role=status を自前で持つため、領域側の aria-atomic=true は
  // 新規トースト追加時に既存トーストまで読み直させてしまう。領域は polite のみに保つ。
  const region = html.match(/<div id="toast-region"[^>]*>/);
  assert.ok(region, 'toast-region が見つからない');
  assert.match(region[0], /aria-live="polite"/, 'toast-region に aria-live=polite が無い');
  assert.doesNotMatch(region[0], /aria-atomic/, 'toast-region に aria-atomic を残さない');
});

test('チューニング値は config.js に集約され、消費側はベタ書きせず参照する', () => {
  // config.js が唯一の設定源であることを構造で保証する（キーの取りこぼしを検出）。
  const configKeys = [
    'quantityMinimum:', 'quantityMaximum:',
    'network:', 'requestTimeoutMs:', 'dashboardRowLimit:', 'queryPageSize:',
    'ui:', 'toastDurationDefault:', 'toastDurationLong:', 'optionListLimit:',
    'detailTransactionLimit:', 'topStockLimit:', 'recentCardLimit:', 'aiNoteCardLimit:',
    'dashboardPanelPageSize:', 'listPageSize:',
    'analytics:', 'trendWindowDays:', 'dormantThresholdDays:', 'alertHistoryLimit:'
  ];
  configKeys.forEach((key) => assert.match(configSource, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `config.js に ${key} がありません`));

  // データアクセス層は通信・集計のチューニングを config から取る（マジックナンバーを持たない）。
  assert.match(access, /config\.network\.requestTimeoutMs/);
  assert.match(access, /config\.network\.dashboardRowLimit/);
  assert.match(access, /config\.network\.queryPageSize/);
  assert.match(access, /config\.analytics\.dormantThresholdDays/);
  assert.match(access, /config\.analytics\.trendWindowDays/);
  assert.match(access, /config\.analytics\.alertHistoryLimit/);
  assert.doesNotMatch(access, /\?limit=50000/);

  // UI層はトースト時間・件数上限・数量範囲を config から取る。
  assert.match(app, /config\.ui\.toastDurationDefault/);
  assert.match(app, /config\.ui\.toastDurationLong/);
  assert.match(app, /config\.ui\.optionListLimit/);
  assert.match(app, /config\.ui\.detailTransactionLimit/);
  assert.match(app, /config\.ui\.topStockLimit/);
  assert.match(app, /config\.ui\.recentCardLimit/);
  assert.match(app, /config\.ui\.aiNoteCardLimit/);
  // 明細一覧の1ページ件数も config を唯一の設定源にし、app.js にベタ書きしない（既定10件ごと）。
  assert.match(app, /const PAGE_SIZE = config\.ui\.listPageSize;/);
  assert.match(configSource, /listPageSize:\s*10/);
  assert.match(app, /config\.quantityMinimum/);
  assert.doesNotMatch(app, /duration \|\| 4500/);
  assert.doesNotMatch(app, /'error', 7000\)/);
});

test('数量入力は整数（個）に固定し、標準スピナー(↑↓)を出さず・小数を入力できない', () => {
  // 在庫は個単位の整数で扱う。config の下限は 1（0.01 ではない）。下限が 0.01 だと
  // changeQuantity の Math.max(下限, 1-1=0) が 0.01 を返し、そこから ＋ を押すと
  // 0.01+1+1+… が 18.00999… のような浮動小数残差になる（実機で報告された不具合）。
  assert.match(configSource, /quantityMinimum:\s*1\b/);
  assert.doesNotMatch(configSource, /quantityMinimum:\s*0\./);
  // 数量入力は type=text（標準スピナー ↑↓ を出さない。増減は −／＋ ボタンで行う）＋
  // inputmode=numeric（整数キーパッド）。小数を誘発する type=number / decimal を残さない。
  const quantityInput = html.match(/<input id="quantity"[^>]*>/);
  assert.ok(quantityInput, '数量入力が見つからない');
  assert.match(quantityInput[0], /type="text"/);
  assert.doesNotMatch(quantityInput[0], /type="number"/);
  assert.match(quantityInput[0], /inputmode="numeric"/);
  assert.doesNotMatch(quantityInput[0], /inputmode="decimal"/);
  // 標準スピナーを外しても数量を変更できるよう、−／＋ ボタンの導線が残っていること。
  assert.match(html, /id="quantity-minus"/);
  assert.match(html, /id="quantity-plus"/);
  // app.js は IDL でも整数キーパッドを明示（端末差の吸収）、入力は数字だけへ正規化し、
  // 増減は現在値を Math.round で整数へ丸めてから行い、検証は整数のみ通す。
  assert.match(app, /elements\.quantity\.inputMode = 'numeric'/);
  assert.match(app, /replace\(\/\[\^0-9\]\/g,\s*''\)/);
  assert.match(app, /const current = Math\.round\(Number\(elements\.quantity\.value \|\| 0\)\)/);
  assert.match(app, /!Number\.isInteger\(state\.quantity\)/);
});

test('配布物に内製コードネームや社内アプリへの言及を含めない', () => {
  // 他のお客様にも配布する汎用リファレンスのため、成果物（コード・コメント）に内製の
  // コードネームや社内アプリ名を残さない。過去に app.css コメントへ紛れ込んだため恒久ガード化する。
  const distributed = [html, css, app, qr, access, boot, configSource].join('\n');
  assert.doesNotMatch(distributed, /ask-domo-kb/i, '内製コードネームが混入しています');
  assert.doesNotMatch(distributed, /colleague/i, '社内アプリへの言及が混入しています');
});

test('PCとDomo Mobileが単一のレスポンシブ画面契約を共有する', () => {
  const viewports = [...html.matchAll(/<meta\s+name="viewport"\s+content="([^"]+)"/g)];
  assert.equal(viewports.length, 1);
  assert.match(viewports[0][1], /width=device-width/);
  assert.match(viewports[0][1], /initial-scale=1/);
  assert.match(viewports[0][1], /viewport-fit=cover/);
  assert.equal(manifest.size.width, 1);
  assert.equal(manifest.size.height, 1);
  assert.equal(Object.hasOwn(manifest, 'fullpage'), false);
  assert.equal(Object.hasOwn(manifest, 'allowFullPage'), false);
  assert.deepEqual(manifest.ignore, ['vendor/*.LICENSE', 'vendor/README.md']);
  assert.doesNotMatch(css, /transform:\s*scale\(/);
});

test('ダッシュボードの横棒集計は可変長スプレッドを使わず線形走査で最大値を求める', () => {
  // barRowHtml の Math.max(...all.map(...)) は、品目/ロケーションが数万件規模の配布先で
  // 実行系の引数上限(V8約6.5万・iOS WebViewはさらに小さい)を超えて RangeError を投げ、
  // renderDashboard 全体が例外終了してダッシュボードが空になる。件数非依存の走査へ戻さない。
  assert.doesNotMatch(app, /Math\.max\(\s*\.\.\.\s*all\.map/);
  // 走査版が存在すること（棒幅の基準最大値を for ループで求めている）を確かめる。
  assert.match(app, /if \(value > maximum\) maximum = value/);
});

test('集計ドリルダウン・直近一覧は archived 取引を除外し、台帳（履歴）は監査証跡として残す', () => {
  // 物理削除マスタの取引には CE が archived 印を付け、canonical DataFlow / フォールバック集計は
  // 本日KPI・トレンドから除外する。カード値と食い違わないよう、その内訳ドリルダウン・「直近の登録」も
  // 同じ基準で archived を落とす。一方で台帳（履歴）ビューは監査証跡として archived 取引も表示する。
  // ヘルパが定義され、archived を真偽値・文字列 'true' の両方で弾くこと。
  assert.match(app, /function activeTransactions\(\)\s*\{/);
  assert.match(app, /row\.archived === true \|\| String\(row\.archived\)\.toLowerCase\(\) === 'true'/);
  // 集計/内訳の消費側（renderRecent・KPI/品目/棚/トレンドの各ドリルダウン・不足/滞留明細）が
  // 生の state.data.transactions ではなく activeTransactions() を使う（呼び出しが6か所以上）。
  const activeCalls = (app.match(/activeTransactions\(\)/g) || []).length;
  assert.ok(activeCalls >= 6, `activeTransactions() の利用が想定より少ない: ${activeCalls}`);
  // 台帳（履歴）ビューは全取引（archived を含む）を素の state.data.transactions から読む。
  assert.match(app, /rows = \[\.\.\.state\.data\.transactions\]\.filter/);
});

test('display:flexで表示するバッジ類はhidden属性を尊重する', () => {
  // display:flex は作者スタイルとしてUAの [hidden]{display:none} を打ち消すため、
  // 明示的な打ち消しがないと「接続済みで隠す」経路が効かず初期文言が残り続ける退行を防ぐ。
  assert.match(css, /\.sync-status\s*\{[^}]*display:\s*flex/s);
  assert.match(css, /\.sync-status\[hidden\][^{]*\{[^}]*display:\s*none/s);
  assert.match(css, /\.user-chip\[hidden\][^{]*\{[^}]*display:\s*none/s);
});

test('PCでは画面幅いっぱいに広げず中央寄せの列に収める', () => {
  // 上限幅と、上限未満で0に潰れるガター変数（タブレット・スマホ無影響）を定義する。
  assert.match(css, /--app-max:\s*\d+px/);
  assert.match(css, /--app-gutter:\s*max\(\s*0px\s*,\s*calc\(\(100vw\s*-\s*var\(--app-max\)\)\s*\/\s*2\)\s*\)/);
  // トップバーとメイン余白がガターを取り込み、左右対称に中央寄せされる。
  assert.match(css, /\.topbar\s*\{[^}]*inset:\s*0\s+var\(--app-gutter\)\s+auto\s+var\(--app-gutter\)/s);
  assert.match(css, /main\s*\{[^}]*var\(--app-gutter\)/s);
  // サイドバーは全高レールをやめ内容分だけのカード（bottom:0で全高に伸ばさない）。
  assert.match(css, /\.sidebar\s*\{[^}]*border-radius:/s);
  assert.doesNotMatch(css, /\.sidebar\s*\{[^}]*inset:\s*var\(--header\)\s+auto\s+0\s+0/s);
});

test('ManifestはCode EngineとWorkflowの実在バージョンを明示マッピングする', () => {
  // 版番号は manifest.json / asset.json が一次情報。テストに固定値を焼き込むと版上げの
  // たびに書き換えが必要になり（Cycle 16 で解消したはずの陳腐化源）、実害を捕まえないまま
  // 保守負債だけが残る。ここでは「形式が妥当か」「配線が実在リリースへ整合しているか」の
  // 不変条件だけを検証する。
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
  assert.equal(manifest.packagesMapping.length, 1);
  assert.equal(manifest.packagesMapping[0].name, 'inventoryService');
  assert.equal(manifest.packagesMapping[0].alias, 'inventoryApi');
  assert.equal(manifest.packagesMapping[0].parameters[1].name, 'request_json');
  assert.equal(manifest.packagesMapping[0].parameters[1].alias, 'requestJson');
  // Manifest が配線する CE パッケージ版は、実際にリリースした版（asset.json）と一致する。
  assert.match(manifest.packagesMapping[0].version, /^\d+\.\d+\.\d+$/);
  assert.equal(manifest.packagesMapping[0].version, codeEngineAsset.version);
  assert.equal(manifest.workflowsMapping.length, 1);
  assert.equal(manifest.workflowsMapping[0].alias, 'lowStockNotification');
  assert.equal(manifest.workflowsMapping[0].modelId, '0c61146c-9e04-4a9b-bc5e-7c43384d06d6');
  assert.match(manifest.workflowsMapping[0].version, /^\d+\.\d+\.\d+$/);
  // 通知Workflowの起動は Code Engine がサーバー側で行う（フロントに起動経路を持たない）。
  // これにより Workflow を改版してもカードの再配線・再埋め込みが不要になる。
  assert.doesNotMatch(access, /startWorkflow/);
  assert.doesNotMatch(access, /\/domo\/workflow\/v1\/models\//);
  assert.match(app, /AI在庫通知を開始しました/);
  assert.match(app, /在庫登録は完了しましたが、AI在庫通知を開始できませんでした/);
  assert.match(app, /notification\.workflow_started/);
  assert.match(app, /notification\.workflow_error/);
});

test('リファレンス実装として、取引に依らずWorkflowを起動できる導線を画面に持つ', () => {
  // 在庫不足パネルに「AI在庫通知を実行」ボタンを置き、その場で通知を開始できる。
  // 参照アーキテクチャとして、取引登録の副作用（自動）と手動ボタンは同じ Code Engine
  // （inventory_api→NOTIFY_NOW／REGISTER）を通り、Workflow の起動は CE がサーバー側で行う。
  assert.match(html, /<symbol\s+id="icon-bell"/);
  assert.match(html, /id="run-notification"[^>]*class="secondary-button"[^>]*type="button"/s);
  assert.match(html, /<use href="#icon-bell">/);
  assert.match(html, /AI在庫通知を実行/);
  // 参照アーキテクチャの要：Workflow をボタンでキックできる導線を明確にするため、起動ボタンは
  // 在庫不足カード内ではなくダッシュボード上部の独立ツールバー（.toolbar-workflow）へ常設する。
  assert.match(html, /class="toolbar-workflow"[\s\S]*id="run-notification"/);
  assert.match(css, /\.toolbar-workflow\s*\{[^}]*margin-left:\s*auto/s);
  // 旧レイアウト（在庫不足カード内のボタン枠 .shortage-actions）は撤去済みで痕跡を残さない。
  assert.doesNotMatch(html, /class="shortage-actions"/);
  assert.doesNotMatch(css, /\.shortage-actions\b/);
  // フロント→CE：新導線 start_shortage_notification が NOTIFY_NOW にマッピングされている。
  assert.match(access, /start_shortage_notification:\s*'NOTIFY_NOW'/);
  // ローカルプレビューでも導線を確認できるデモ分岐（宛先なしのため実行手前まで再現）。
  assert.match(access, /functionName === 'start_shortage_notification'/);
  assert.match(access, /RECIPIENT_EMAIL_MISSING/);
  // 手動ボタンのハンドラが配線され、起動結果（CE が返す workflow_started/workflow_error）を表示する。
  assert.match(app, /async function runShortageNotification/);
  assert.match(app, /callFunction\('start_shortage_notification'/);
  assert.match(app, /elements\['run-notification'\]\.addEventListener\('click', runShortageNotification\)/);
  // 自動経路（登録の副作用）も CE が返す結果だけを見る（フロントに Workflow 起動ヘルパーは持たない）。
  assert.match(app, /result\.notification\?\.workflow_ready/);
  assert.doesNotMatch(app, /launchNotificationWorkflow|recordNotificationFailure/);
});

test('狭いiframeでもページ全体を横スクロールさせない', () => {
  assert.match(css, /html\s*\{[^}]*min-width:\s*0[^}]*overflow-x:\s*clip/s);
  assert.match(css, /body\s*\{[^}]*min-width:\s*0[^}]*overflow-x:\s*hidden/s);
  assert.match(css, /\.table-scroll\s*\{[^}]*overflow-x:\s*auto[^}]*overscroll-behavior-x:\s*contain/s);
  assert.match(css, /@media\s*\(max-width:\s*767px\)/);
  assert.match(css, /\.bar-row\s*\{[^}]*minmax\(0,\s*1fr\)/s);
});

test('Domo Mobileホストと回転・キーボード表示をレイアウトへ反映する', () => {
  assert.match(app, /domoEnvironment\.platform/);
  assert.match(app, /platform === 'mobile'/);
  assert.match(app, /visualViewport\?\.height/);
  assert.match(app, /visualViewport\.addEventListener\('resize'/);
  assert.match(app, /addEventListener\('orientationchange'/);
  // App StudioはPro Code iframeを文書高へ拡張しない。正常表示する同僚アプリと同じく、
  // シェルを実ビューポート(100dvh)へ固定し、mainを唯一の縦スクロール領域にする。
  // height:100% はiframe内で包含ブロックが内容高へ潰れると崩れる（＝縦長描画・末尾到達不可・
  // 余白がApp Studioのカード選択層へ抜けて青枠化）ため、実高に追従するdvhで固定する。
  assert.match(css, /html\[data-domo-platform="mobile"\][^{]*,[^{]*body\s*\{[^}]*height:\s*100dvh[^}]*min-height:\s*0[^}]*overflow:\s*hidden/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.app-shell\s*\{[^}]*display:\s*flex[^}]*height:\s*100dvh[^}]*min-height:\s*0[^}]*overflow:\s*hidden/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+main\s*\{[^}]*flex:\s*1\s+1\s+auto[^}]*min-height:\s*0[^}]*overflow-y:\s*auto/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.topbar\s*\{[^}]*position:\s*static/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.mobile-nav\s*\{[^}]*position:\s*static[^}]*display:\s*flex/s);
  // カード内タップで出る青い外枠＋スクロール固定は WebKit の tap ハイライト／長押し
  // コールアウトが主因。Web側で無効化できるこの2点を base の html で切る。
  assert.match(css, /html\s*\{[^}]*-webkit-tap-highlight-color:\s*transparent[^}]*-webkit-touch-callout:\s*none/s);
  // 手順書準拠の幅ドリブン経路（max-width:767px）でも同じdvhビューポート固定を保証する。
  assert.match(css, /@media\s*\(max-width:\s*767px\)[\s\S]*\.app-shell\s*\{[^}]*height:\s*100dvh[^}]*overflow:\s*hidden/s);
  assert.ok(html.indexOf('class="mobile-nav"') < html.indexOf('<main id="main-content"'), 'mobile nav must precede main content');
  assert.match(app, /function scrollAppToTop/);
  assert.match(app, /content\.scrollTo\(\{top:\s*0/);
});

test('Mobile WebViewの起動停止を検出し、静的画面から再試行できる', () => {
  assert.match(html, /id="boot-message"[^>]*role="alert"[^>]*hidden/);
  assert.match(html, /id="boot-retry"/);
  assert.match(html, /src="boot-diagnostics\.js"/);
  assert.match(boot, /function markReady/);
  assert.match(boot, /unhandledrejection/);
  assert.match(boot, /12000/);
  // 起動失敗を確定表示したら遅延ウォッチドッグを解除し、具体的な失敗理由が汎用メッセージで
  // 上書きされないようにする。加えてコールバック側も data-app-boot=error なら再表示しない二重の保険。
  assert.match(boot, /function markFailed[\s\S]*?if \(watchdog\) \{ global\.clearTimeout\(watchdog\); watchdog = null; \}/);
  assert.match(boot, /getAttribute\('data-app-boot'\) !== 'error'/);
  assert.match(app, /document\.readyState === 'loading'/);
  assert.match(app, /Promise\.resolve\(\)\.then\(init\)\.catch\(renderFatalBoot\)/);
  assert.match(app, /function renderFatalBoot/);
  assert.match(access, /requestTimeoutMs = config\.network\.requestTimeoutMs/);
  assert.match(access, /function withTimeout/);
  assert.match(css, /dialog:not\(\[open\]\)\s*\{\s*display:\s*none/);
  assert.match(css, /\.boot-message\s*\{/);
});

test('登録ステップは現在の作業を説明し、完了済み画面へ戻れる', () => {
  assert.match(html, /id="step-count">ステップ 1 \/ 4/);
  assert.match(html, /id="step-action">ロケーションを選択/);
  assert.equal((html.match(/data-step-nav=/g) || []).length, 4);
  assert.equal((html.match(/aria-controls="step-panel-/g) || []).length, 4);
  assert.match(app, /ステップ \$\{state\.step\} \/ 4/);
  assert.match(app, /ロケーションを選択/);
  assert.match(app, /品目を選択/);
  assert.match(app, /登録内容を確認/);
  assert.match(app, /button\.disabled = nodeStep === state\.step \|\| !accessible/);
  assert.match(app, /setAttribute\('aria-current', 'step'\)/);
  // 初期表示ではステップ見出しへプログラム的フォーカスを当てない（PCで:focus-visibleの枠が
  // 出て「STEP 1が選択済み」に見えるため）。ユーザー操作の移動時のみフォーカスする。
  assert.match(app, /function setStep\(step, focusTitle = true\)/);
  assert.match(app, /if \(focusTitle\) byId\(`step-title-\$\{state\.step\}`\)\?\.focus/);
  assert.match(app, /setStep\(state\.step, false\)/);
  assert.match(app, /const complete = \(nodeStep === 1/);
  assert.match(app, /byId\(`step-title-\$\{state\.step\}`\)\?\.focus/);
  assert.match(css, /\.stepper\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.stepper button\s*\{[^}]*min-height:\s*44px/s);
  assert.match(css, /\.stepper b::after\s*\{[^}]*content:\s*attr\(data-short\)/s);
});

test('確認内容の陳腐化を防ぎ、モバイルでも選択内容を確認できる', () => {
  assert.match(html, /id="selected-location-card"[^>]*aria-label="ロケーション選択へ戻る"/);
  assert.match(html, /id="selected-item-card"[^>]*aria-label="品目選択へ戻る"[^>]*disabled/);
  assert.match(app, /function invalidateReview/);
  assert.match(app, /changed && state\.step === 4/);
  assert.match(app, /もう一度「内容を確認」を押してください/);
  assert.match(app, /button\.setAttribute\('aria-pressed', String\(selected\)\)/);
  assert.match(app, /elements\['selected-item-card'\]\.disabled = !state\.location/);
  assert.match(css, /\.context-panel\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s);
  assert.match(css, /\.context-panel \.selection-card\s*\{[^}]*min-height:\s*64px/s);
});

test('QR選択と在庫変化を業務文脈で案内する', () => {
  assert.doesNotMatch(app, /QRコードを読み取りました。/);
  assert.match(app, /を選択しました。続けて品目を選んでください。/);
  assert.match(app, /を選択しました。続けて数量を確認してください。/);
  assert.match(app, /登録後の見込み在庫/);
  assert.match(app, /現在 .* \$\{operator\} \$\{operation\}/);
  assert.match(app, /\['登録後見込み在庫'/);
  assert.match(app, /確定在庫 \$\{number\.format\(before\)\} → \$\{number\.format\(after\)\}/);
  assert.doesNotMatch(html, /同じリクエストは二重登録されません/);
  assert.match(html, /内容に問題がなければ「登録を確定」を押してください/);
});

test('QRはライブ映像を全端末の既定にし、全画面化しても継続・自動復帰する。撮影／保存画像／手入力の控えも維持する', () => {
  // ライブスキャンを全端末（PC/Android/iPhone）の既定にする。iPhoneのDomo Mobile（WKWebView）は
  // ホストのallowsInlineMediaPlaybackが無効でライブ映像を全画面化するが、全画面のまま読み取りを
  // 続け、成功時は全画面を抜けてこの画面へ自動で戻る（webkitExitFullscreen＋dialog.close）。
  // 利用者が読み取り前に全画面を閉じたらライブ再開の導線を出す。端末カメラ撮影（capture）・
  // 保存画像・手入力は、ライブで読み取れない場合の控えとして維持する。
  assert.match(html, /id="qr-capture-input"[^>]*accept="image\/\*"[^>]*capture="environment"[^>]*hidden/);
  assert.match(html, /id="qr-capture-button"[^>]*class="camera-capture-cta"/);
  assert.match(html, /カメラで撮影/);
  assert.match(html, /id="qr-image-input"[^>]*accept="image\/\*"[^>]*hidden/);
  assert.doesNotMatch(html.match(/<input id="qr-image-input"[^>]*>/)?.[0] || '', /capture=/);
  assert.match(html, /id="qr-image-button"/);
  assert.match(html, /写真から選ぶ/);
  assert.match(html, /id="scanner-video"[^>]*autoplay[^>]*playsinline[^>]*webkit-playsinline/);
  assert.match(html, /src="vendor\/domo\.js"/);
  assert.match(html, /src="vendor\/jsQR\.js"/);
  assert.doesNotMatch(html, /<script[^>]+src="https?:\/\//);
  assert.ok(fs.existsSync(path.join(__dirname, '../pro-code/vendor/domo.js')));
  assert.ok(fs.existsSync(path.join(__dirname, '../pro-code/vendor/jsQR.js')));
  assert.ok(fs.existsSync(path.join(__dirname, '../pro-code/vendor/ryuu.js-4.6.0.LICENSE')));
  assert.ok(fs.existsSync(path.join(__dirname, '../pro-code/vendor/jsQR-1.4.0.LICENSE')));
  assert.match(qr, /navigator\.mediaDevices\.getUserMedia/);
  assert.match(qr, /facingMode:\s*\{ideal:\s*'environment'\}/);
  assert.match(qr, /typeof global\.jsQR === 'function'/);
  assert.match(qr, /global\.jsQR\(imageData\.data/);
  assert.match(qr, /function'\) await image\.decode/);
  assert.match(qr, /parse\(rawValue\)/);
  assert.match(qr, /\^\(LOC\|ITEM\):/);
  assert.match(qr, /nativeDecoderEnabled/);
  assert.match(qr, /softwareDecoderEnabled/);
  assert.match(qr, /isSessionActive\(sessionId\)/);
  assert.match(qr, /stream\.getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/);
  assert.match(qr, /suspendForBackground\(\)/);
  // ライブ全画面の継続と自動復帰、再開導線、控えの撮影・写真・手入力を配線する。
  assert.match(html, /id="qr-live-restart"[^>]*class="camera-capture-cta"/);
  assert.match(html, /ライブ映像を再開/);
  assert.match(qr, /webkitbeginfullscreen/);
  assert.match(qr, /webkitendfullscreen/);
  assert.match(qr, /handleEnterFullscreen/);
  assert.match(qr, /handleFullscreenDismissed/);
  assert.match(qr, /webkitExitFullscreen/);
  assert.match(qr, /restartLive/);
  assert.match(qr, /setCaptureMode/);
  assert.match(qr, /this\.captureInput/);
  assert.match(qr, /this\.captureButton/);
  assert.match(qr, /showFallbackMessage/);
  assert.match(qr, /写真から選ぶ/);
  assert.match(qr, /acceptDetectedValue\(rawValue, sessionId\)/);
  assert.match(qr, /returnValue !== 'success'/);
  assert.match(app, /bootReady:\s*false/);
  assert.match(app, /setQrControlsReady\(false\)/);
  assert.match(css, /\.scanner-modal \.modal-heading\s*\{[^}]*position:\s*sticky/s);
  assert.match(css, /min-height:\s*clamp\(160px,\s*32vh,\s*240px\)/);
  assert.match(qr, /\.filter\(Boolean\)\.join\('\+'\)/);
  assert.match(app, /state\.scanner\.parse\(scanResult\.rawValue\)/);
  assert.doesNotMatch(app, /callFunction\('parse_qr'/);
  assert.match(app, /品目QRを読み取りました。現在はロケーション選択です/);
  assert.match(app, /ロケーションQRを読み取りました。現在は品目選択です/);
  assert.match(qr, /ロケーションQRを読み取る/);
  assert.match(qr, /品目QRを読み取る/);
  assert.match(qr, /下のコード入力/);
  assert.match(qr, /acceptManual\(\)[\s\S]*acceptDetectedValue\(value, this\.sessionId\)/);
  assert.match(css, /\.scanner-actions\s*\{/);
  assert.match(css, /touch-action:\s*pan-y pinch-zoom/);
  assert.match(css, /\.camera-frame video\s*\{[^}]*pointer-events:\s*none/s);
});

test('スマホアプリはハンディ端末を想定して不要導線を隠し、タイル状の大きめUIにする', () => {
  // PC業務とスマホ業務は別ペルソナ。Domo Mobileホスト（data-domo-platform="mobile"）では
  // 現場作業に不要な導線（マスタ編集タブ）を隠し、コアの入出庫だけに絞る。
  // PCは全機能を維持する。判定はホスト属性のみに依存させ、幅ドリブンとは独立させる。
  assert.match(app, /function isMobileHostActive\(\)\s*\{[^}]*dataset\.domoPlatform === 'mobile'/s);
  assert.match(app, /function applyMobilePersona\(\)/);
  // syncRuntimeLayout はホスト属性を確定した直後にペルソナを適用する。
  assert.match(app, /root\.dataset\.domoPlatform = isDomoMobileHost\(\)[\s\S]*applyMobilePersona\(\);/);
  // 管理系（admin-only）はモバイルでは権限に関わらず隠す。
  assert.match(app, /querySelectorAll\('\.admin-only'\)\.forEach\(\(node\) => \{ node\.hidden = true; \}\)/);
  assert.match(app, /node\.hidden = !state\.user\.isAdmin \|\| isMobileHostActive\(\)/);
  // マスタ編集タブ表示中はモバイルで取引履歴へ戻す（4→3メニュー統合後の防御）。
  assert.match(app, /if \(MASTER_TABS\[state\.recordTab\]\) setRecordTab\('transactions'\)/);
  // マスタ編集タブ（管理者専用）は管理者かつPCのみ許可し、権限がなければ取引履歴へフォールバックする。
  assert.match(app, /if \(isMaster && \(!state\.user\.isAdmin \|\| isMobileHostActive\(\)\)\)/);
  assert.match(app, /if \(MASTER_TABS\[state\.recordTab\] && !state\.user\.isAdmin\) setRecordTab\('transactions'\)/);
  // タイル状ナビ：均等幅・縦積み・角丸カード。
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.mobile-nav \.nav-item\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*flex-direction:\s*column[^}]*border-radius:\s*14px/s);
  // 大きめボタン・数量コントロール・選択カード（片手操作しやすいタッチ領域）。
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.scan-button,[\s\S]*\.primary-button\s*\{[^}]*min-height:\s*54px/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.quantity-control button\s*\{[^}]*height:\s*64px/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.type-button\s*\{[^}]*min-height:\s*50px/s);
  assert.match(css, /html\[data-domo-platform="mobile"\]\s+\.selection-card\s*\{[^}]*min-height:\s*74px/s);
});

test('PC表示は業務画面向けの高密度レイアウトを使う', () => {
  assert.match(css, /@media\s*\(min-width:\s*981px\)/);
  assert.match(css, /\.view\s*\{\s*max-width:\s*1680px/);
  assert.match(css, /\.workflow-panel\s*\{\s*padding:\s*14px 18px 16px/);
  assert.match(css, /@media\s*\(min-width:\s*1200px\)[\s\S]*\.option-list\s*\{\s*grid-template-columns:\s*repeat\(2,/);
  // ダッシュボードは幅で列が畳まれる auto-fit グリッド（.dashboard-row、最小260px）で組む。
  assert.match(css, /\.dashboard-row\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(260px,\s*1fr\)\)/s);
  // 旧・固定比率の2列グリッドと .dashboard-column ラッパは廃止（痕跡を残さない）。
  assert.doesNotMatch(css, /\.dashboard-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.24fr\)/s);
  assert.doesNotMatch(css, /\.dashboard-column\b/);
  assert.doesNotMatch(css, /\.chart-panel,[^}]*min-height:\s*(?:260|300)px/s);
});

test('ダッシュボードは各行を最も低いカードへ高さ揃え＋高いカードは内部スクロール（NEW-O）', () => {
  // 上段(row-primary=3枚)・下段(row-secondary=2枚)を、幅に応じて列が畳まれる auto-fit グリッドで組む。
  assert.match(html, /<div class="dashboard-row row-primary">/);
  assert.match(html, /<div class="dashboard-row row-secondary">/);
  // 折り返し時・単独カードの既定は自然高（align-items:start）。横並び時のみ JS が最短カード高へ揃える。
  assert.match(css, /\.dashboard-row\s*\{[^}]*align-items:\s*start/s);
  // カードは縦フレックス＋overflow:hidden。中身(.dash-scroll)だけが内部縦スクロールを担い、
  // 見出し・凡例・ページャはスクロール枠の外に固定表示（改ページボタンは常に見える）。
  assert.match(css, /\.dashboard-row\s*>\s*\.panel\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.dashboard-row\s*>\s*\.panel\s*>\s*\*\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.match(css, /\.dashboard-row\s*>\s*\.panel\s*>\s*\.dash-scroll\s*\{[^}]*flex:\s*1 1 auto[^}]*min-height:\s*0[^}]*overflow-y:\s*auto/s);
  // 5つの中身領域にスクロール枠(.dash-scroll)を付ける（傾向グラフは min-height を保つため専用ラッパで包む）。
  assert.match(html, /id="item-chart" class="bar-chart dash-scroll"/);
  assert.match(html, /id="location-chart" class="bar-chart dash-scroll"/);
  assert.match(html, /<div id="shortage-list" class="dash-scroll">/);
  assert.match(html, /<div id="dormant-list" class="dash-scroll">/);
  assert.match(html, /<div class="dash-scroll"><div id="trend-chart" class="trend-chart">/);
  // ページャはスクロール枠の外の兄弟要素として、中身(.dash-scroll)の直後に置く（枠内スクロール対象にしない）。
  assert.match(html, /<div id="shortage-list" class="dash-scroll"><\/div><nav id="shortage-pager"/);
  assert.match(html, /<div id="dormant-list" class="dash-scroll"><\/div><nav id="dormant-pager"/);
  // 高さ揃えは JS。最短カード高を視覚行ごとに計測し、描画直後とリサイズ後に取り直す。
  assert.match(app, /function equalizeDashboardRows\(\)/);
  assert.match(app, /function scheduleDashboardEqualize\(\)/);
  assert.match(app, /renderAiNotes\(rows\);\s*\n\s*\/\/[^\n]*\n\s*scheduleDashboardEqualize\(\);/s);
  assert.match(app, /applyMobilePersona\(\);[\s\S]{0,160}scheduleDashboardEqualize\(\);/);
  // 高さ均等化を CSS の height:100% ハックや display:contents で再導入しない（JS 計測に一本化）。
  assert.doesNotMatch(css, /\.dashboard-grid\s*>\s*\.panel\s*\{[^}]*height:\s*100%/s);
  assert.doesNotMatch(css, /display:\s*contents/s);
  // 1パネルの表示件数を絞り、各パネルを短く保つ。
  assert.match(configSource, /dashboardPanelPageSize:\s*6/);
});

test('ダッシュボード上部のツールバーに横断検索とWorkflow起動を常設する（NEW-P）', () => {
  // 取引入力・履歴に続き、ダッシュボードにも小綺麗な検索ボックスを常設する（calm-blue 準拠）。
  assert.match(html, /<div class="search-wrap dashboard-search-wrap">[\s\S]*id="dashboard-search"/);
  assert.match(html, /id="dashboard-search"[^>]*type="search"/);
  assert.match(css, /\.dashboard-search-wrap\s*\{[^}]*flex:\s*1 1 260px/s);
  // 検索語は正規化して state に持ち、入力のたびに4パネルを先頭ページから再描画する（空クエリは無退行で素通し）。
  assert.match(app, /dashboardQuery:\s*''/);
  assert.match(app, /state\.dashboardQuery = normalizedSearch\(elements\['dashboard-search'\]\.value\)/);
  assert.match(app, /function filterDashboardRows\(rows\)/);
  assert.match(app, /if \(!query\) return rows;/);
  // 一致なしの時だけ専用の空表示に切り替え、既存の空文言（在庫不足はありません等）を誤表示しない。
  assert.match(app, /function dashboardEmpty\(defaultMarkup\)/);
  assert.match(app, /に一致する記録がありません。/);
  // 生成AIの要約は参照アーキテクチャの見せ場。右下に埋めず KPI 直下の全幅バンドへ置き、
  // バンド内カードは横並び(grid auto-fit)。ただしドリルダウン明細の .ai-note-cards は縦積みのまま。
  assert.match(html, /<div id="kpi-grid" class="kpi-grid"><\/div>\s*<article class="panel ai-note-panel">/);
  assert.match(css, /#ai-note-list \.ai-note-cards\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(260px,\s*1fr\)\)/s);
});

test('ダッシュボードの密度・トーン仕上げが後退していない（NEW-N cycle3）', () => {
  // auto-fit の最小列幅(260px)でも傾向バーが列幅を超えて重ならないよう、基底のバー幅上限を控えめに保つ。
  assert.match(css, /\.trend-bars span\s*\{[^}]*width:\s*clamp\(7px,\s*1\.8vw,\s*15px\)/s);
  // 淡い仕切り線トークンを定義し、散っていた #e9edf5 直書きを1本へ集約する。
  assert.match(css, /--line-soft:\s*#e9edf5/);
  assert.match(css, /\.recent-row\s*\{[^}]*border-top:\s*1px solid var\(--line-soft\)/s);
  assert.match(css, /\.shortage-row,\s*\.dormant-row\s*\{[^}]*border-top:\s*1px solid var\(--line-soft\)/s);
  // カード角丸は共通トークン（--radius）に揃える（7px 直書きを残さない）。
  assert.match(css, /\.table-panel\s*\{[^}]*border-radius:\s*var\(--radius\)/s);
  assert.match(css, /\.kpi-card\s*\{[^}]*border-radius:\s*var\(--radius\)/s);
  assert.doesNotMatch(css, /\.kpi-card\s*\{[^}]*border-radius:\s*7px/s);
  // KPIカードのホバーは控えめに：浮き上がり（translateY）と強い影を使わない。
  assert.match(css, /\.kpi-card:hover,\s*\.kpi-card:focus-visible\s*\{[^}]*box-shadow:\s*var\(--shadow\)[^}]*\}/s);
  assert.doesNotMatch(css, /\.kpi-card:hover,\s*\.kpi-card:focus-visible\s*\{[^}]*translateY/s);
  // 不足数量の太さを 700 に落として過度な強調を避ける。
  assert.match(css, /\.shortage-qty\s*\{[^}]*font-weight:\s*700/s);
  // 保留ピルの配色をトークン化（生の16進を残さない）。
  assert.match(css, /\.status-pill\.pending\s*\{[^}]*color:\s*var\(--orange-600\)[^}]*background:\s*var\(--orange-100\)/s);
  // 広い画面では横棒グラフの行間を詰めて縦伸びを抑える。
  assert.match(css, /@media\s*\(min-width:\s*981px\)[\s\S]*\.bar-chart\s*\{[^}]*gap:\s*6px/s);
});

test('集計グラフとKPIがホバー情報とドリルダウンを提供する', () => {
  assert.match(html, /id="chart-tooltip"[^>]*role="tooltip"/);
  // モーダル（スライダー）は廃止。明細は履歴ビュー内のマスター詳細ペインへ描画する。
  assert.match(html, /class="master-detail"/);
  assert.match(html, /class="panel md-detail" id="detail-pane"/);
  assert.doesNotMatch(html, /id="detail-dialog"/);
  assert.match(app, /data-tooltip-title/);
  assert.match(app, /data-drill-kind="(?:kpi|item|location|trend|shortage|dormant)"/);
  assert.match(app, /function handleDashboardDrilldown/);
  assert.match(app, /function openItemDetail/);
  assert.match(app, /function openLocationDetail/);
  assert.match(app, /function openTrendDetail/);
  assert.match(css, /\.chart-tooltip\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /\.master-detail\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.4fr\)/s);
  assert.doesNotMatch(css, /\.detail-drawer/);
});

test('在庫不足KPIのドリルダウンは検索で絞らない全SHORTAGE行から件数を出す（カード面と一致）', () => {
  // KPIカードの数値は横断検索の影響を受けない全体集計(metric_value)。その内訳ドリルダウンも
  // 検索で絞り込まれた state.dashboardDrilldowns.shortage ではなく、全 SHORTAGE 行から導出する。
  // こうしないと「在庫不足 N」を押したのに明細が検索一致分だけになり、面の数値と食い違う。
  assert.match(
    app,
    /key === 'SHORTAGE_COUNT'[\s\S]{0,400}?\(state\.dashboardRows \|\| \[\]\)\s*[\s\S]{0,120}?record_type === 'SHORTAGE'/,
    'SHORTAGE_COUNTドリルダウンが全dashboardRowsから導出されていない'
  );
  // 旧実装（検索フィルタ済み配列の流用）を再導入しない番人。
  assert.doesNotMatch(
    app,
    /key === 'SHORTAGE_COUNT'[\s\S]{0,200}?const shortages = state\.dashboardDrilldowns\.shortage;/,
    'SHORTAGE_COUNTドリルダウンが検索フィルタ済み配列を流用している（面と不一致になる）'
  );
});

test('履歴・マスタの2ペインは同じ高さ枠で丈を揃える（NEW-J）', () => {
  // 左の一覧ペイン(.md-list)を右の明細ペイン(.md-detail)と同じ高さ枠に収め、
  // 縦の間延びと左右の不均衡を解消する。見出し・ページャは固定、一覧のみ内部スクロール。
  assert.match(css, /\.md-detail\s*\{[^}]*max-height:\s*calc\(var\(--app-viewport-height\) - 88px\)/s);
  assert.match(css, /\.md-list\s*\{[^}]*max-height:\s*calc\(var\(--app-viewport-height\) - 88px\)[^}]*flex-direction:\s*column/s);
  assert.match(css, /\.md-list \.table-scroll,\s*\.md-list \.master-list\s*\{[^}]*flex:\s*1 1 auto[^}]*overflow-y:\s*auto/s);
  // 表ヘッダは内部スクロール中も追従する（列名を見失わない）。
  assert.match(css, /(^|\})\s*th\s*\{[^}]*position:\s*sticky[^}]*top:\s*0/s);
  // スマホ（1カラム）では高さ枠を外し、入れ子スクロールを避けてページ全体の縦スクロールに委ねる。
  assert.match(css, /@media \(max-width: 980px\)[\s\S]*\.md-list\s*\{\s*min-height:\s*0;\s*max-height:\s*none/);
});

test('取引・通知履歴は行クリックとキーボードで明細を開く', () => {
  assert.match(html, /id="history-result-count"/);
  assert.match(html, /id="history-clear"/);
  assert.match(app, /class="drilldown-row" tabindex="0" role="button" data-history-index/);
  assert.match(app, /function handleHistoryDrilldownKey/);
  assert.match(app, /event\.key !== 'Enter' && event\.key !== ' '/);
  assert.match(app, /function openTransactionDetail/);
  assert.match(app, /function openAlertDetail/);
  // 行選択でマスター側を強調し、詳細を同一ビューのペインへ差し替える（モーダルなし）。
  assert.match(app, /function openHistoryRow/);
  assert.match(app, /function highlightSelectedHistoryRow/);
  assert.match(app, /function fillDetailPane/);
  assert.match(css, /\.drilldown-row\.is-selected/);
  assert.doesNotMatch(app, /detail-dialog|function closeDetail|function showRelatedHistory/);
});

test('各メニューは自メニュー内で明細まで完結し、履歴タブへ強制遷移しない', () => {
  // ダッシュボード・入出庫のドリルダウンは、履歴タブへ飛ばさず右からのスライドイン・ドロワーへ描く。
  assert.match(html, /id="context-detail"[^>]*class="[^"]*context-detail[^"]*drawer/);
  // ドロワーはモーダル面として role="dialog" / aria-modal を持ち、背景オーバーレイを伴う。
  assert.match(html, /id="context-detail"[^>]*role="dialog"[^>]*aria-modal="true"/);
  assert.match(html, /id="context-detail-backdrop"[^>]*class="drawer-backdrop"[^>]*hidden/);
  assert.match(html, /id="context-detail-content"/);
  // 履歴遷移は任意導線（ボタン）で、既定は同一メニュー内で完結する。
  assert.match(html, /id="context-detail-more"[^>]*hidden/);
  // 右から滑り込む面のスタイル（閉状態は translateX(100%)、開くと 0 へ）。
  assert.match(css, /\.context-detail\.drawer\s*\{/);
  assert.match(css, /\.context-detail\.drawer\.is-open\s*\{[^}]*translateX\(0\)/);
  assert.match(css, /\.drawer-backdrop\s*\{[^}]*position:\s*fixed/s);
  assert.match(app, /function fillContextDetail/);
  assert.match(app, /function hideContextDetail/);
  assert.match(app, /function openContextDrawer/);
  assert.match(app, /function closeContextDrawer/);
  assert.match(app, /function openContextDetailInHistory/);
  // 背景クリックと Esc でも閉じられる（モーダル面としての標準操作）。
  assert.match(app, /elements\['context-detail-backdrop'\]\.addEventListener\('click', hideContextDetail\)/);
  assert.match(app, /function handleDrawerKeydown/);
  assert.match(app, /event\.key !== 'Escape'/);
  // openDetail は現在ビューで分岐する。履歴は既存ペイン、それ以外はドロワー。
  assert.match(app, /function openDetail\(options\)\s*\{[\s\S]*?state\.view === 'history'[\s\S]*?fillDetailPane\(options\);[\s\S]*?fillContextDetail\(options\);/);
  // 旧実装の「履歴ビューへの強制遷移」は撤去済み（メニューをまたがない）。
  assert.doesNotMatch(app, /if \(state\.view !== 'history'\) switchView\('history'\)/);
  // メニュー切替時はインライン詳細を閉じ、前ビューの明細を残さない。
  assert.match(app, /function switchView\(view\)\s*\{[\s\S]*?hideContextDetail\(\);/);
  // 旧 detail-dialog / detail-drawer 実装は再導入しない（新ドロワーは context-detail 系で実装）。
  assert.doesNotMatch(css, /\.detail-drawer/);
  assert.doesNotMatch(html, /id="detail-dialog"/);
});

test('アクセシビリティ: 可視フォーカス・補足メタのコントラスト、モーダルの背景inert、ローディングのライブ通知', () => {
  // フォーカスリングは淡い半透明ではなく不透明のアクセント青 2px にし、WCAG 2.4.7 の視認性を担保する。
  assert.match(css, /\[tabindex\]:focus-visible\s*\{[\s\S]*?outline:\s*2px solid var\(--teal-700\)/);
  assert.doesNotMatch(css, /outline:\s*3px solid rgba\(47, 107, 176/);
  // 補足メタ（.option-meta）は本文 AA を満たす共通トークン --muted に寄せ、旧 #737f92 は使わない。
  assert.match(css, /\.option-meta\s*\{[^}]*color:\s*var\(--muted\)/);
  assert.doesNotMatch(css, /\.option-meta\s*\{[^}]*#737f92/);
  // モーダルのドロワーを開く間は背景 .app-shell を inert にし、Tab フォーカスと読み上げを面内へ閉じ込める。
  assert.match(app, /function setBackgroundInert\(inert\)\s*\{[\s\S]*?shell\.inert = inert/);
  assert.match(app, /function openContextDrawer[\s\S]*?setBackgroundInert\(true\)/);
  assert.match(app, /function closeContextDrawer[\s\S]*?setBackgroundInert\(false\)/);
  // inert は hidden 化を待つ setTimeout より前（同期）で解除する。閉じた直後に呼び出し元
  // （.app-shell 内の行・グラフ）へフォーカスを戻すため、inert 状態のままだと focus() が無効化される。
  assert.match(app, /function closeContextDrawer[\s\S]*?setBackgroundInert\(false\)[\s\S]*?setTimeout/);
  // ローディング面は role="status" の live region にし、処理中メッセージを支援技術へ読み上げる。
  assert.match(html, /id="loading-overlay"[^>]*role="status"/);
});

test('ミニマリズム: 未使用のフラグ・キャッシュ参照を復活させない', () => {
  // ライブスキャンが全端末既定。未使用の preferNativeCapture フラグは撤去済みで、再導入しない。
  assert.doesNotMatch(qr, /preferNativeCapture/);
  // 確認ダイアログは <form method="dialog"> の returnValue で完結し、confirm-action ボタンは
  // JS から参照しない（要素キャッシュにも積まない）。
  assert.doesNotMatch(app, /'confirm-action'/);
  // master-editor / master-note は静的な見出し・注記で、要素キャッシュへ積む必要がない。
  assert.doesNotMatch(app, /'master-editor'(?!-)/);
  assert.doesNotMatch(app, /'master-note'/);
});

test('管理者はマスタCRUDを単一のCode Engine入口で操作し、削除は物理削除にする', () => {
  // 履歴ビューのマスタ管理は左=一覧・右=編集フォームの2ペイン（.master-detail）に統合済み。
  assert.match(html, /<div class="master-detail admin-only" id="record-panel-master" role="tabpanel" aria-labelledby="record-tab-item" hidden>/);
  // マスタ種別は統合タブ（.record-tab）の data-record で切り替える。管理系タブは admin-only + hidden。
  assert.match(html, /class="record-tab admin-only" data-record="item"[^>]*hidden/);
  assert.match(html, /class="record-tab admin-only" data-record="location"[^>]*hidden/);
  assert.match(html, /class="record-tab admin-only" data-record="rule"[^>]*hidden/);
  assert.match(html, /id="master-form"/);
  assert.match(html, /id="master-item-code"/);
  assert.match(html, /id="master-location-code"/);
  assert.match(html, /id="master-rule-minimum"/);
  assert.match(html, /id="master-list"/);
  // 右ペインの編集フォーム構成要素（見出し・新規登録・件数・削除・可逆な状態トグル）を持つ。
  assert.match(html, /id="master-editor"/);
  assert.match(html, /id="master-editor-title"/);
  assert.match(html, /id="master-new"/);
  assert.match(html, /id="master-result-count"/);
  assert.match(html, /id="master-delete"[^>]*hidden/);
  // 削除ボタンは物理削除（不可逆）を表す「削除」ラベル、復元ボタンは廃止済み。
  assert.match(html, /id="master-delete"[^>]*>削除</);
  assert.doesNotMatch(html, /id="master-restore"/);
  // 有効/停止の状態トグル（可逆なUPDATE）は編集時のみ表示。既定は hidden。
  assert.match(html, /id="master-active-row"[^>]*hidden/);
  assert.match(html, /id="master-active"[^>]*type="checkbox"/);
  // フロント→CE：唯一の入口 manage_master が MANAGE_MASTER にマッピングされている。
  assert.match(access, /manage_master:\s*'MANAGE_MASTER'/);
  assert.match(access, /functionName === 'manage_master'/);
  // ローカルプレビューでも物理削除の意味論（マスタ本体＋依存を連鎖削除）を再現する。
  assert.match(access, /deleted: removed/);
  assert.doesNotMatch(access, /row\.active = false;/);
  // すべての書き込みは共通ヘルパー callMaster('...', ...) → manage_master を通る。
  assert.match(app, /async function callMaster/);
  assert.match(app, /callFunction\('manage_master'/);
  assert.match(app, /'UPSERT_ITEM'/);
  assert.match(app, /'UPSERT_LOCATION'/);
  assert.match(app, /'UPSERT_RULE'/);
  assert.match(app, /'DELETE_ITEM'/);
  assert.match(app, /'DELETE_LOCATION'/);
  assert.match(app, /'DELETE_RULE'/);
  // 削除は確認ダイアログ経由の物理削除で、不可逆かつ台帳(履歴)は残す旨を明示する。
  assert.match(app, /function confirmMasterDelete/);
  assert.match(app, /AppDBから完全に削除します/);
  assert.match(app, /この操作は取り消せません/);
  // 復元(論理削除の巻き戻し)は廃止。停止は状態トグルによる可逆なUPDATEで代替する。
  assert.doesNotMatch(app, /function restoreMaster/);
  // 2ペイン：行クリック/キー操作で右ペインへ読み込み（委譲）、選択行を強調する。
  assert.match(app, /function editMaster/);
  assert.match(app, /function newMaster/);
  assert.match(app, /function updateMasterSelection/);
  assert.match(app, /function handleMasterRowActivate/);
  assert.match(app, /function handleMasterRowKey/);
  // 行はドリルダウン行として data-master-edit を持ち、行内アクションボタン（.master-link）は廃止済み。
  assert.match(app, /class="drilldown-row[^"]*"[^>]*data-master-edit=/);
  // マスタ一覧は取引・通知の履歴表と同じ「素の table.master-table」で描く。詳細ペイン用の
  // .detail-table-wrap（枠線＋角丸カード）を流用すると列見出しの下の縁だけ丸く見えて不揃いになるため、
  // masterTableHtml は wrapper 無しの table を返し、見出しは共通の sticky th に揃える（回帰防止）。
  assert.match(app, /function masterTableHtml[\s\S]*?return `<table class="master-table"><thead>/);
  assert.doesNotMatch(app, /<div class="detail-table-wrap"><table class="detail-table master-table"/);
  // ドリルダウン詳細ペインの表は従来どおり .detail-table-wrap/.detail-table を維持する（別用途）。
  assert.match(app, /<div class="detail-table-wrap"><table class="detail-table">/);
  // マスタ一覧要素自身が横スクロール枠になる（min-width:480px の表が狭幅ではみ出すため）。
  assert.match(css, /\.master-list\s*\{[^}]*overflow-x:\s*auto/s);
  assert.doesNotMatch(app, /data-master-delete=/);
  assert.doesNotMatch(app, /class="master-link/);
  // 編集時は状態トグルの値を UPSERT の active に載せて可逆に有効/停止を切り替える（入力ロックは廃止）。
  assert.doesNotMatch(app, /function lockMasterInputs/);
  assert.match(app, /master-active'\]\) \? \{active: elements\['master-active'\]\.checked\}/);
  // 管理者以外は各ハンドラの先頭で弾く（ビュー・ボタン露出とは独立した二重防御）。
  assert.match(app, /function submitMaster[\s\S]*?if \(!state\.user\.isAdmin\) return;/);
  assert.match(app, /renderMasters\(\);/);
  // マスタ管理は履歴ビュー内の admin-only パネルに置き、現場（スマホ）ペルソナには出さない。
  assert.ok(html.indexOf('id="view-history"') < html.indexOf('id="record-panel-master"'));
  assert.doesNotMatch(html, /id="view-admin"/);
  // 狭い画面ではフィールドを1カラムに折り返す。
  assert.match(css, /\.master-fields\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s);
  assert.match(css, /@media\s*\(max-width:\s*767px\)[\s\S]*\.master-fields\s*\{\s*grid-template-columns:\s*1fr/s);
});

test('物理削除の確認は close 単一実行点で、確定時だけ1回実行する（ハンドラ蓄積による誤削除を防ぐ）', () => {
  // 不可逆な物理削除の確認は、確定ボタンへ都度 click ハンドラを足すと
  // キャンセル/ESC で {once} が解除されず残り、次の別レコード削除時に過去対象まで巻き込む危険がある。
  // そのため確定/取消の判定を confirm-dialog の close に一元化し、保留操作を state で1つだけ持つ。
  // 都度の click ハンドラ登録・解除は行わない（蓄積の芽を断つ）。
  assert.doesNotMatch(app, /confirm-action'\]\.addEventListener\('click', handler/);
  assert.doesNotMatch(app, /confirm-action'\]\.removeEventListener/);
  // close リスナは1本だけ束ねる。確定(returnValue==="default")のときのみ保留操作を実行する。
  assert.match(app, /confirm-dialog'\]\.addEventListener\('close', handleConfirmClose\)/);
  assert.match(app, /function handleConfirmClose/);
  assert.match(app, /returnValue === 'default'/);
  // 保留操作は state.pendingConfirm に1つだけ載せ、実行後は必ず null に戻して二重実行を防ぐ。
  assert.match(app, /state\.pendingConfirm = \(\) => runMasterDelete\(tab, code\)/);
  assert.match(app, /state\.pendingConfirm = null/);
  // 直前の確定結果が残って ESC 誤発火しないよう、表示前に returnValue を初期化する。
  assert.match(app, /confirm-dialog'\]\.returnValue = ''/);
});

test('選択状態は role=button 行では aria-current で表し、ビュー枠はプログラム的フォーカスを受けられる', () => {
  // 行(drilldown-row)は role="button"。aria-selected は listbox/grid 専用で role=button/素の tr では
  // 無効なため、集合内カレントを表す aria-current へ統一する。視覚選択は is-selected クラスが担う。
  assert.match(app, /class="drilldown-row" tabindex="0" role="button" data-history-index/);
  assert.match(app, /role="button" data-master-edit=/);
  assert.match(app, /node\.setAttribute\('aria-current', 'true'\)/);
  assert.match(app, /node\.removeAttribute\('aria-current'\)/);
  // 行に対して無効な aria-selected を残さない。候補ピッカーも role=option を廃し、選択は aria-current に統一。
  assert.doesNotMatch(app, /data-history-index="\$\{index\}"[^>]*aria-selected/);
  assert.doesNotMatch(app, /data-master-edit="[^"]*"[^>]*aria-selected/);
  // ビュー切替は #view-* へ focus() する。section に tabindex=-1 が無いと no-op になり、
  // キーボード/支援技術にビュー変更のフォーカス手掛かりが渡らない。3ビューすべてに付与する。
  assert.match(html, /id="view-operations"[^>]*tabindex="-1"/);
  assert.match(html, /id="view-dashboard"[^>]*tabindex="-1"/);
  assert.match(html, /id="view-history"[^>]*tabindex="-1"/);
  // 受け皿はあるが操作起点は各ボタン側なので、:focus-visible の枠は抑えたままにする。
  assert.match(css, /\.view:focus-visible[^{]*\{\s*outline:\s*none/);
});

test('最上位ナビは現在地を aria-current=page で公開し、切替時も付け替える', () => {
  // .active の見た目だけでなく aria-current='page' でも現在ビューを AT に伝える
  // （type-button の aria-pressed・record-tab の aria-selected・stepper の aria-current と同じ規約）。
  // 初期表示（入出庫）で active な nav-item は、静的HTMLの時点で aria-current=page を持つ。
  const activeNav = html.match(/<button class="nav-item active"[^>]*>/g) || [];
  assert.ok(activeNav.length > 0, 'active な nav-item が見つからない');
  activeNav.forEach((tag) => assert.match(tag, /aria-current="page"/, `active な nav-item に aria-current=page が無い: ${tag}`));
  // 非activeな nav-item には aria-current を付けない（現在地は常に1ビューぶんだけ示す）。
  const inactiveNav = html.match(/<button class="nav-item"[^>]*>/g) || [];
  inactiveNav.forEach((tag) => assert.doesNotMatch(tag, /aria-current/, `非active な nav-item に aria-current が残っている: ${tag}`));
  // switchView がビュー切替時に全 nav-item の aria-current を付け替える（据え置きの嘘を残さない）。
  assert.match(app, /node\.setAttribute\('aria-current', 'page'\)/);
  assert.match(app, /node\.removeAttribute\('aria-current'\)/);
});

test('利用者チップは操作を持たない静的表示にする（死んだコントロールを置かない）', () => {
  // 利用者名は表示専用。クリック不能な要素を button にすると、支援技術にフォーカス可能な操作を
  // 誤って約束してしまう。ハンドラの無い装飾は非対話要素（div）で表す。
  assert.match(html, /<div class="user-chip">/);
  assert.doesNotMatch(html, /<button[^>]*class="user-chip"/, 'user-chip を button に戻さない');
});

test('マスタ一覧の表は aria-live で丸ごと読み上げない（件数行が通知を担う）', () => {
  // 再描画のたびに一覧全体を読み上げると冗長。件数の更新は #master-result-count（aria-live）が担い、
  // #master-list 自体は live region にしない。
  const masterList = html.match(/<div id="master-list"[^>]*>/);
  assert.ok(masterList, '#master-list が見つからない');
  assert.doesNotMatch(masterList[0], /aria-live/, '#master-list に aria-live を戻さない');
});

test('インライン詳細を閉じたら、開くきっかけの要素へフォーカスを戻す（body へ落とさない）', () => {
  // 開いた時点の活性要素（行・グラフ等）を控え、× で閉じたときにそこへフォーカスを返す。
  // 見出しへフォーカスを移す前に取得する必要がある。DOMに残り focus 可能なときだけ復帰させる。
  assert.match(app, /state\.contextDetailOrigin = document\.activeElement/);
  assert.match(app, /const origin = state\.contextDetailOrigin/);
  assert.match(app, /origin\.isConnected && typeof origin\.focus === 'function'/);
  assert.match(app, /origin\.focus\(\{preventScroll: true\}\)/);
  // 取得は必ず見出しフォーカスより前（順序が逆だと見出し自身を控えてしまう）。
  const open = app.slice(app.indexOf('function fillContextDetail'), app.indexOf('function hideContextDetail'));
  assert.ok(
    open.indexOf('state.contextDetailOrigin = document.activeElement') <
      open.indexOf("elements['context-detail-title'].focus"),
    'origin の取得は見出しフォーカスより前で行う'
  );
});

test('display:flexのトグルはhidden属性を尊重する（作者displayがUAの[hidden]を打ち消さない）', () => {
  // 既知の落とし穴：作者側 display:flex/grid は UA の [hidden]{display:none} を上書きするため、
  // hidden で隠す要素にはセレクタと対で display:none を明示する。状態トグルの出っぱなしを防ぐ。
  assert.match(css, /\.master-active-toggle\[hidden\]\s*\{\s*display:\s*none/);
});

test('横向き(低い高さ)でも本文がスクロールで到達できる（app-shellが縦フレックス列）', () => {
  // @media (max-width:900px) and (max-height:520px) の app-shell に display:flex/flex-direction:column が
  // 無いと、固定高＋overflow:hidden で main がスクロール担当にならず本文下部が切れて到達不能になる。
  assert.match(css, /@media\s*\(max-width:\s*900px\)\s*and\s*\(max-height:\s*520px\)[\s\S]*?\.app-shell\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column/s);
});

test('履歴と管理を1画面に統合し、ナビは3項目・切替は単一の.record-tabsに集約する', () => {
  // 導線を絞る意図：4メニュー（入出庫/ダッシュボード/履歴/管理）→3メニューへ統合。
  // 管理は履歴ビュー内の admin-only タブに畳み込み、独立した管理ビューは持たない。
  const navItems = html.match(/data-view="(operations|dashboard|history|admin)"/g) || [];
  // サイドバー＋モバイルナビで各3項目ずつ＝合計6。admin は残っていてはならない。
  assert.equal(navItems.length, 6, 'ナビ項目はPC/モバイル合わせて6（各3）である');
  assert.doesNotMatch(html, /data-view="admin"/);
  assert.doesNotMatch(html, /id="view-admin"/);
  assert.doesNotMatch(html, /id="icon-settings"/);
  // 履歴ナビの文言は統合を反映する（サイドバーは「履歴・管理」）。
  assert.match(html, /data-view="history"[^>]*>[\s\S]*?<em>履歴・管理<\/em>/);
  // 取引/通知/品目/ロケーション/基準在庫を単一のタブ列で切り替える。
  assert.match(html, /class="record-tabs" role="tablist"/);
  ['transactions', 'alerts', 'item', 'location', 'rule'].forEach((record) => {
    assert.match(html, new RegExp(`data-record="${record}"`));
  });
  // 旧タブ実装（.history-tabs / .master-tabs / data-history / data-master-tab）は残さない。
  assert.doesNotMatch(html, /history-tabs|master-tabs|data-history=|data-master-tab=/);
  assert.doesNotMatch(css, /\.history-tab\b|\.master-tab\b|\.admin-grid\b|\.admin-card\b/);
  // タブのディスパッチャは setRecordTab に一本化し、旧 setHistoryMode は残さない。
  assert.match(app, /function setRecordTab\(tab\)/);
  assert.doesNotMatch(app, /function setHistoryMode/);
  // マスタ種別テーブル（item/location/rule）で履歴タブとマスタタブを判別する。
  assert.match(app, /const MASTER_TABS = \{item: true, location: true, rule: true\}/);
  // トグルで表示切替するグリッド系パネルは著者側 display を [hidden] より優先させない。
  assert.match(css, /\.filter-panel\[hidden\],\s*\.master-detail\[hidden\]\s*\{\s*display:\s*none/s);
});

test('タブ列はWAI-ARIA Tabsパターンを満たす（id/aria-controls/tabpanel/ロービングtabindex/矢印キー）', () => {
  // role="tablist" を宣言する以上、タブ⇄パネルの関連付けとキーボード操作まで完成させる。
  // 各タブに安定 id を付け、パネルは role="tabpanel" で active タブに aria-labelledby で結ぶ。
  ['transactions', 'alerts', 'item', 'location', 'rule'].forEach((record) => {
    assert.match(html, new RegExp(`id="record-tab-${record}"[^>]*data-record="${record}"`));
  });
  // 2枚のパネルは tabpanel。初期は既定タブ（取引／品目）で名前付けし、以降は setRecordTab が張り替える。
  assert.match(html, /id="record-panel-history" role="tabpanel" aria-labelledby="record-tab-transactions"/);
  assert.match(html, /id="record-panel-master" role="tabpanel" aria-labelledby="record-tab-item"/);
  // ロービングtabindex: 非アクティブなタブは初期状態で tabindex="-1"（Tabキーはアクティブ1つだけ辿る）。
  assert.match(html, /data-record="alerts"[^>]*tabindex="-1"/);
  // setRecordTab が tabindex と aria-controls/aria-labelledby を動的に張り替える。
  assert.match(app, /button\.tabIndex = selected \? 0 : -1/);
  assert.match(app, /activeTab\.setAttribute\('aria-controls', activePanel\.id\)/);
  assert.match(app, /activePanel\.setAttribute\('aria-labelledby', activeTab\.id\)/);
  assert.match(app, /if \(!selected\) button\.removeAttribute\('aria-controls'\)/);
  // 矢印キー／Home／End でタブを移動し、hidden なタブ（非管理者に隠れる管理系）は対象外にする。
  assert.match(app, /function handleRecordTabKey\(event\)/);
  assert.match(app, /button\.addEventListener\('keydown', handleRecordTabKey\)/);
  assert.match(app, /'ArrowLeft'[\s\S]*?'ArrowRight'[\s\S]*?'Home'[\s\S]*?'End'/);
  assert.match(app, /\.filter\.call\(document\.querySelectorAll\('\.record-tab'\), \(t\) => !t\.hidden\)/);
});

test('履歴／マスタのパネル表示はタブ状態が唯一の管理者（NEW-M）', () => {
  // admin-only 一括表示（updateUser）は record-panel-master も対象にするため、
  // それだけでは取引タブのまま履歴とマスタが両方縦に並んでしまう。
  // 表示切替を syncRecordPanels に集約し、現在のタブで必ず上書きする。
  assert.match(app, /function syncRecordPanels\(\)/);
  assert.match(app, /const isMaster = MASTER_TABS\[state\.recordTab\] === true;[\s\S]*?record-panel-history'\]\.hidden = isMaster;[\s\S]*?record-panel-master'\]\.hidden = !isMaster;/);
  // admin-only の一括表示直後に syncRecordPanels で表示を確定する。
  assert.match(app, /querySelectorAll\('\.admin-only'\)\.forEach\(\(node\) => \{ node\.hidden = !state\.user\.isAdmin \|\| isMobileHostActive\(\); \}\);[\s\S]*?syncRecordPanels\(\);/);
  // タブ切替も同じ関数を使う（表示ロジックを二重化しない）。
  assert.match(app, /\/\/ パネルの表示切替。[\s\S]*?syncRecordPanels\(\);/);
});

test('候補ピッカーは不完全な listbox を宣言せず、素直なボタン群にする（選択は aria-current）', () => {
  // role="listbox"/role="option" は活性子孫や矢印キーのキーボードモデルを伴わないと不完全な契約になる。
  // 検索入力＋候補ボタン群という素直な構成にし、選択中は集合内カレントを表す aria-current で示す。
  assert.doesNotMatch(html, /id="location-options"[^>]*role="listbox"/);
  assert.doesNotMatch(html, /id="item-options"[^>]*role="listbox"/);
  assert.match(html, /id="location-options" class="option-list" role="group" aria-label="ロケーション候補"/);
  assert.match(html, /id="item-options" class="option-list" role="group" aria-label="品目候補"/);
  // 候補ボタンは role="option"/aria-selected を持たず、選択中だけ aria-current="true" を付ける。
  assert.doesNotMatch(app, /class="option-button"[^`]*role="option"/);
  assert.doesNotMatch(app, /class="option-button"[^`]*aria-selected/);
  assert.match(app, /class="option-button" type="button"\$\{selected \? ' aria-current="true"' : ''\}/);
  // 視覚強調のCSSも aria-current に合わせる（aria-selected セレクタは残さない）。
  assert.match(css, /\.option-button\[aria-current="true"\]/);
  assert.doesNotMatch(css, /\.option-button\[aria-selected="true"\]/);
});

test('サイドバーのQR形式にスキャン可能なテスト用QRを内製生成器で描画する', () => {
  // ユーザー要望：QR形式（LOC:LOC-01 / ITEM:ITEM-001）にテスト用QRの表示を復活させる。
  // 生成器は自前JSで、外部ライブラリやOS依存ツール・画像バイナリに依存しない配布形態にする。
  assert.ok(fs.existsSync(path.join(__dirname, '../pro-code/qr-generator.js')), 'qr-generator.js が同梱されている');
  // スクリプトは app.js より前・vendor(jsQR) と同居して読み込む。
  assert.match(html, /<script src="qr-generator\.js"><\/script>/);
  assert.ok(html.indexOf('qr-generator.js') < html.indexOf('app.js'), 'qr-generator.js は app.js より前に読み込む');
  // サイドバーのテストQR領域は data-qr を単一の情報源にして LOC/ITEM を描く。
  assert.match(html, /class="sidebar-help"[\s\S]*?data-qr="LOC:LOC-01"[\s\S]*?data-qr="ITEM:ITEM-001"/);
  assert.match(html, /QR形式（テスト用）/);
  // 起動時に一度だけ描画し、生成には内製の InventoryQR.toSvg を使う。
  assert.match(app, /function renderTestQrCodes\(\)/);
  assert.match(app, /global\.InventoryQR\.toSvg/);
  assert.match(app, /renderTestQrCodes\(\);/);
  // モバイルではサイドバー自体を隠すため、テストQRは自然とPC専用になる。
  assert.match(css, /html\[data-domo-platform="mobile"\]\s*\.sidebar\s*\{\s*display:\s*none/);
});

test('本文テキストの最小フォントは11px以上（可読性フロア）', () => {
  // 落ち着いた業務向けデザイン言語に合わせ、8〜10px の極小テキストを廃し 11px を下限にする。
  // スクロール可能な iframe 内描画のため、ラベル・見出しの +1〜3px は密度を保ったまま可読性を上げる。
  const tinyFonts = css.match(/font-size:\s*(?:[0-9]|10)px\b/g) || [];
  assert.deepEqual(tinyFonts, [], `11px 未満の font-size が残っている: ${tinyFonts.join(', ')}`);
  // ベースは据え置き（過度な拡大で App Studio カード内の密度を崩さない）。
  assert.match(css, /body\s*\{[^}]*font-size:\s*13px/s);
});

test('動的生成する表の見出しセルはすべて scope="col" を持つ（スクリーンリーダー対応）', () => {
  // 履歴・詳細・マスタの表は app.js で組み立てるため、<th> に scope が無いと
  // 支援技術が列見出しと本文セルの対応を読み上げられない。バレ <th>（scope 無し）を残さない。
  assert.doesNotMatch(app, /<th>/, 'scope の無い素の <th> が残っている');
  assert.match(app, /<th scope="col">\$\{escapeHtml\(header\)\}<\/th>/);
  // 履歴ヘッダ（取引/通知の両モード）も列見出しに scope を付ける。
  assert.match(app, /<tr><th scope="col">日時<\/th>/);
});

test('件数表示は aria-live で通知する（スクリーンリーダー対応）', () => {
  // 設計原則どおり「件数の更新は aria-live で通知」する。検索やフィルタで結果件数が
  // 変わったとき、支援技術が新しい件数を読み上げられるよう live region にしておく。
  assert.match(html, /<strong id="history-result-count" aria-live="polite">/);
  assert.match(html, /<strong id="master-result-count" aria-live="polite">/);
});

test('モーダルダイアログは見出しをaria-labelledbyで名前付けする', () => {
  // 設計原則「アクセシビリティを基本装備とする」に従い、他の領域（#context-detail・
  // #detail-pane・#master-editor）と同じく、ダイアログにも見出しを結び付けて
  // 支援技術が適切なアクセシブルネームを読み上げられるようにする。
  assert.match(html, /<dialog id="scanner-dialog"[^>]*aria-labelledby="scanner-title"/);
  assert.match(html, /<dialog id="confirm-dialog"[^>]*aria-labelledby="confirm-title"/);
  assert.match(html, /<h2 id="scanner-title"/);
  assert.match(html, /<h2 id="confirm-title"/);
});

test('取引明細は在庫の流れを balance-flow 帯で示し、IDは detail-meta へ控えめに置く', () => {
  // 「数量／登録前／登録後」を3つのKPI箱で並べる帳票的な見せ方はやめ、
  // 登録前→登録後の流れと増減量を1本の静かな帯（balanceFlow）で見せる。
  assert.match(app, /function balanceFlow\(/);
  assert.match(app, /balance-flow-track/);
  assert.match(app, /balance-flow-delta/);
  assert.match(app, /balanceFlow\(before, after, signed, row\.transaction_type\)/);
  assert.match(css, /\.balance-flow\s*\{/);
  assert.match(css, /\.balance-flow-badge\.out\s*\{/);
  // 取引ID・リクエストIDは監査用の参照値。detail-meta（等幅・控えめ）へ回す。
  assert.match(app, /function detailMeta\(/);
  assert.match(app, /detailMeta\(\[[\s\S]*?'取引ID'/);
  assert.match(css, /\.detail-meta dd\s*\{[^}]*monospace/s);
  // 定義リストはグレーのラベル列（背景）をやめ、静かな細罫線だけの並びにした。
  assert.doesNotMatch(css, /\.detail-definition dt\s*\{[^}]*background/);
  // 登録元の内部コードは読みやすい日本語ラベルへ変換して表示する。
  assert.match(app, /function sourceLabel\(/);
  assert.match(app, /DOMO_MOBILE: 'モバイルアプリ'/);
});

test('AI在庫コメント（AI_NOTE）をダッシュボードと明細に表示する', () => {
  // DataFlow の TextGeneration タイルが生成した ai_summary を埋もれさせず、
  // ダッシュボードのパネルと各ドリルダウン明細で活用する（NEW-B）。
  assert.match(html, /<div id="ai-note-list"><\/div>/);
  assert.match(html, /class="panel ai-note-panel"/);
  assert.match(app, /function renderAiNotes\(rows\)/);
  assert.match(app, /function aiNoteSection\(balances\)/);
  assert.match(app, /function aiNoteKey\(itemCode, locationCode\)/);
  // 明細ドリルダウンに aiNoteSection を差し込む（品目・ロケーション・不足・滞留・不足KPI）。
  assert.match(app, /\+ aiNoteSection\(balances\) \+/);
  assert.match(app, /\+ aiNoteSection\(\[row\]\) \+/);
  // ai_summary が空の行は除外し、創作しない。
  assert.match(app, /record_type === 'AI_NOTE' && String\(row\.ai_summary \|\| ''\)\.trim\(\)/);
  // 落ち着いた青系トークンのカードスタイルが定義されている。
  assert.match(css, /\.ai-note-cards\s*\{/);
  assert.match(css, /\.ai-note\.is-shortage\s*\{/);
});

test('AI在庫コメントは品目ごとに束ね、品目コードと所在を明示する（NEW-K）', () => {
  // 同じ品目が多拠点で不足すると似た要約がパネルを埋めるため、品目単位で1枚へ集約し、
  // 品目内で最も注意すべき拠点を代表に選び、残りは「ほかN拠点」として件数だけ添える。
  assert.match(app, /const byItem = new Map\(\);/);
  assert.match(app, /const worstFirst = \(a, b\) =>/);
  // 代表選び＝不足優先→在庫の少ない順、パネル整列も同じ基準を共用する。
  assert.match(app, /Number\(isShortageRow\(b\)\) - Number\(isShortageRow\(a\)\)/);
  // 代表ノートのキー→残り拠点数を引く辞書を作り、カードに渡す。
  assert.match(app, /const extraByKey = \{\};/);
  assert.match(app, /aiNoteCards\(shown\.map\(\(entry\) => entry\.note\), extraByKey\)/);
  assert.match(app, /function aiNoteCards\(notes, extraByKey\)/);
  // カードは品目コードチップ・所在行・他拠点チップを持つ。
  assert.match(app, /class="ai-note-code"/);
  assert.match(app, /class="ai-note-loc"/);
  assert.match(app, /class="ai-note-extra">ほか\$\{number\.format\(extra\)\}拠点/);
  // 明細ドリルダウンは拠点別に出すため extraByKey を渡さない（引数省略で従来どおり）。
  assert.match(app, /aiNoteCards\(notes\)\s*\)\s*:\s*''/);
  // ラベル用スタイルは calm-blue トークンで定義（フォントは 11px 下限を満たす）。
  assert.match(css, /\.ai-note-code\s*\{/);
  assert.match(css, /\.ai-note-loc\s*\{/);
  assert.match(css, /\.ai-note-extra\s*\{/);
});

test('AI在庫コメントのパネルは余白を持ち、カードの色帯は持たない（NEW-L）', () => {
  // 他のダッシュボードパネルと同じ内側余白を与え、見出し・カードが枠にくっつかないようにする。
  assert.match(css, /\.chart-panel, \.shortage-panel, \.dormant-panel, \.ai-note-panel \{[^}]*padding:/);
  // 左の色帯（inset シャドウ / border-left）はユーザー要望により全廃した。
  assert.doesNotMatch(css, /\.ai-note \{[^}]*box-shadow:/);
  assert.doesNotMatch(css, /\.ai-note \{[^}]*border-left:/);
  // 不足の強調は面塗りとバッジの色で示す（左の色帯に依存しない）。
  assert.match(css, /\.ai-note\.is-shortage \{[^}]*background: var\(--orange-100\)/);
  assert.match(css, /\.ai-note\.is-shortage \.ai-note-badge \{[^}]*background: var\(--orange-600\)/);
});

test('選択・装飾を問わず左の色帯（アクセント線）は使わない', () => {
  // ユーザー要望：選択状態や見出し・カードの左端に出ていた紺色の縦線（inset バー・太い border-left）を
  // 全廃し、強調は面塗り（--surface-selected / --teal-100）と文字色だけで示す。
  assert.doesNotMatch(css, /box-shadow:\s*inset/);
  assert.doesNotMatch(css, /border-left:\s*[2-9]px/);
});

test('一覧のページ送り: 履歴・マスタに pager を持ち、絞り込み変更で先頭へ戻す', () => {
  // データ全件を一度に描かず PAGE_SIZE 件ずつ表示する（NEW-C）。
  assert.match(html, /<nav id="history-pager" class="pager"[^>]*hidden><\/nav>/);
  assert.match(html, /<nav id="master-pager" class="pager"[^>]*hidden><\/nav>/);
  assert.match(app, /const PAGE_SIZE = config\.ui\.listPageSize;/);
  assert.match(app, /function paginate\(rows, requestedPage, pageSize = PAGE_SIZE\)/);
  assert.match(app, /function renderPager\(elementId, scope, page, options\)/);
  assert.match(app, /function handlePagerClick\(event\)/);
  // 検索・種別変更、条件クリア、履歴タブ切替、マスタ種別切替で必ずページを0へ戻す。
  assert.match(app, /state\.historyPage = 0; renderHistory\(\);/);
  assert.match(app, /state\.masterPage = 0;/);
  // display:flex は UA の [hidden] を打ち消すため、非表示用の対を必ず持つ。
  assert.match(css, /\.pager\[hidden\]\s*\{\s*display:\s*none/);
  // 明細一覧（履歴・管理）は1ページに収まっても枠を残す（真っ白回避）。renderPager は alwaysShow を
  // 尊重し、前後ボタンを無効化して表示する。ダッシュボードの小パネルは既定どおり1ページなら隠す。
  assert.match(app, /renderPager\('history-pager', 'history', page, \{alwaysShow: true\}\)/);
  assert.match(app, /renderPager\('master-pager', 'master', state\.masterPageInfo, \{alwaysShow: true\}\)/);
  assert.match(app, /page\.total <= page\.pageSize && !alwaysShow/);
});

test('paginate は範囲外ページを安全側へ丸める純関数である', () => {
  // クロージャ内の paginate をソースから取り出し、PAGE_SIZE=20 を与えて実挙動を検証する。
  const PAGE_SIZE = 20;
  const source = app.match(/function paginate\(rows, requestedPage, pageSize = PAGE_SIZE\) \{[\s\S]*?\n  \}/);
  assert.ok(source, 'paginate 関数のソースを抽出できること');
  // eslint-disable-next-line no-new-func
  const paginate = new Function('PAGE_SIZE', `${source[0]}; return paginate;`)(PAGE_SIZE);
  const rows = Array.from({length: 45}, (_, i) => i);
  const first = paginate(rows, 0);
  assert.equal(first.slice.length, 20);
  assert.equal(first.start, 0);
  assert.equal(first.safePage, 0);
  assert.equal(first.pageCount, 3);
  assert.equal(first.total, 45);
  assert.equal(first.pageSize, 20);
  const last = paginate(rows, 2);
  assert.equal(last.slice.length, 5);
  assert.equal(last.start, 40);
  // 範囲外（過大）は最終ページへ丸める。
  assert.equal(paginate(rows, 99).safePage, 2);
  // 負値は先頭へ丸める。
  assert.equal(paginate(rows, -5).safePage, 0);
  // 空配列でも pageCount は最低1、total 0。
  const empty = paginate([], 0);
  assert.equal(empty.pageCount, 1);
  assert.equal(empty.total, 0);
  assert.deepEqual(empty.slice, []);
  // 明示 pageSize（ダッシュボードのパネル用）ではその件数で区切り、start も pageSize に追従する。
  const small = paginate(rows, 0, 8);
  assert.equal(small.slice.length, 8);
  assert.equal(small.pageCount, 6);
  assert.equal(small.pageSize, 8);
  assert.equal(paginate(rows, 1, 8).start, 8);
  // 範囲外要求は明示 pageSize 基準で最終ページへ丸める（45件÷8=6ページ→index5）。
  assert.equal(paginate(rows, 99, 8).safePage, 5);
});

test('ダッシュボード各パネルもページ送りで縦の伸びを抑える（NEW-I）', () => {
  // 品目別・ロケーション別・在庫不足・滞留の4パネルにパネル内ページャを持たせ、
  // 1ページ件数は config.ui.dashboardPanelPageSize で共通管理する。
  ['item', 'location', 'shortage', 'dormant'].forEach((kind) => {
    assert.match(html, new RegExp(`<nav id="${kind}-pager" class="pager pager-compact"[^>]*hidden></nav>`),
      `${kind}-pager のパネル内ページャが存在すること`);
  });
  // ページ状態は4パネル分を1オブジェクトで保持し、データ再取得時に先頭へ戻せる。
  assert.match(app, /dashboardPages: \{item: 0, location: 0, shortage: 0, dormant: 0\}/);
  // 共通の描画ヘルパで「全件を絶対indexで」ページングし、drilldown 照合がずれないこと。
  assert.match(app, /function renderDashboardPanel\(kind, all, chartId, pagerId, emptyMarkup, rowHtml\)/);
  assert.match(app, /page\.slice\.map\(\(row, offset\) => rowHtml\(row, page\.start \+ offset\)\)/);
  // handlePagerClick はダッシュボードの scope も受け付け、再描画で範囲を丸める。
  assert.match(app, /hasOwnProperty\.call\(state\.dashboardPages, scope\)/);
  // 1ページ件数は config を唯一の設定源にする（ベタ書きしない）。
  assert.match(app, /config\.ui\.dashboardPanelPageSize/);
  // 軽量ページャのスタイルが定義され、[hidden] の対も継承している（.pager[hidden]）。
  assert.match(css, /\.pager-compact\s*\{/);
  // AI在庫コメントは全幅バンドとして .dashboard-grid の前（上）に置くため、order ハックに頼らない。
  assert.match(html, /class="panel ai-note-panel"[\s\S]*<div class="dashboard-grid">/);
  assert.doesNotMatch(css, /\.ai-note-panel\s*\{\s*order:/);
});
