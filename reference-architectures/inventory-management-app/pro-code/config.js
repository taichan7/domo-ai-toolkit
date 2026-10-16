/**
 * アプリ全体で共有する不変設定。
 *
 * 物理ID（DataSet・Code Engine・Workflow の UUID）は持たず、Manifest で配線したエイリアスと、
 * 散在しがちなチューニング値（表示件数・タイムアウト・集計ウィンドウ）だけを1か所へ集約する。
 * フロントエンドは実行時に manifest.json を読めないため、同じエイリアス名をここへミラーする
 * （物理IDは Manifest 配線が解決するので持たない）。
 */
window.InventoryConfig = Object.freeze({
  // AppDB統合コレクション名（標準同期の対象）。
  collections: Object.freeze({
    records: 'inventory_management_records'
  }),
  // Manifestで配線したエイリアス。物理IDの代わりに使い、層をまたいでIDを持ち回らない。
  // 通知Workflowは Code Engine がサーバー側で起動する（最新の有効版を実行時に解決するため
  // FE に workflow の alias は持たない＝Workflow改版時にカード再埋め込みが不要）。
  packageAlias: 'inventoryApi',
  dashboardAlias: 'inventoryDashboard',

  // 数量入力の下限・上限。桁あふれや誤操作を早期に弾くためのUIガード（app.jsで使用）。
  // 在庫は「個」単位の整数で扱うため下限は 1。下限を 0.01 にすると −ボタンで 1→0 が下限へ
  // 丸められ、入力欄に 0.01 が現れてしまう（小数在庫を扱う配布先はこの値と整数検証を緩める）。
  // Code Engine 側にも同じ上限（MAX_QUANTITY）があり、こちらは入力UXを整える先回りの検証。
  quantityMinimum: 1,
  quantityMaximum: 1000000,

  // 通信とデータ量のチューニング。配布先が回線・データ規模に応じて調整し得る値。
  network: Object.freeze({
    // Domo SDK 呼び出しが無応答のまま固まらないよう、自前で打ち切るまでの時間（ミリ秒）。
    requestTimeoutMs: 12000,
    // ダッシュボードDataSetを一度に取得する行数の上限。過大取得を防ぐデータ量ガード。
    dashboardRowLimit: 50000,
    // AppDB の documents/query は1応答を最大この件数（上限 10,000 件）で打ち切る。domo-access.js は
    // この値で limit/offset のページ送りを行い、台帳が1万件を超えても全件を取りこぼさないようにする。
    queryPageSize: 10000
  }),

  // 画面表示のチューニング（件数上限・トースト表示時間）。同じ意味の値を複数箇所へ
  // 書かず、ここを唯一の定義源にして食い違い（片方だけ直し忘れ）を防ぐ。
  ui: Object.freeze({
    // 横断検索（履歴・ダッシュボード）の入力デバウンス（ミリ秒）。数万件規模で毎キーストローク
    // 再フィルタ+再ソート+再描画しないための待機。候補リスト（30件上限）は即時のまま。
    searchDebounceMs: 160,
    // 通常トーストの表示時間（ミリ秒）。
    toastDurationDefault: 4500,
    // 重要な結果（成功・エラー）を読み切れるよう長めに出すトーストの表示時間（ミリ秒）。
    toastDurationLong: 7000,
    // ロケーション／品目候補リストの描画上限。多すぎる候補で画面を埋めないための上限。
    optionListLimit: 30,
    // ドリルダウン「直近の取引」の表示件数。
    detailTransactionLimit: 8,
    // KPIドリルダウン「現在庫上位」の表示件数。
    topStockLimit: 12,
    // 「直近の登録」カードの表示件数。
    recentCardLimit: 4,
    // ダッシュボードのAI在庫コメントに並べる品目数（代表1枚／品目）。残りは「ほかN品目」に集約。
    // 全幅の auto-fit グリッド（2〜3列）で末尾に空セルを残さない件数にする（3列で割り切れる6）。
    aiNoteCardLimit: 6,
    // ダッシュボード各パネル（品目別・ロケーション別・在庫不足・滞留）の1ページ表示件数。
    // 縦に伸び続けないよう区切り、1画面（広い画面では3列2段）に収める上限。
    dashboardPanelPageSize: 6,
    // 履歴・管理（マスタ）の明細一覧の1ページ表示件数（履歴と管理で共通）。app.js の PAGE_SIZE は
    // この値を唯一の定義源にする。配布先が調整し得るチューニング値（既定は10件ごとのページ送り）。
    listPageSize: 10
  }),

  // 集計ウィンドウ。正となる定義はダッシュボードDataFlow（dashboard_transform.py）にあり、
  // ここは AppDB フォールバック集計（DataFlow未到達時）を DataFlow と揃えるためのミラー。
  // DataFlow側を変えるときは必ずこの値も合わせること（片方だけ変えると表示が食い違う）。
  analytics: Object.freeze({
    // 入出庫トレンドの表示日数（直近N日）。
    trendWindowDays: 7,
    // 「滞留在庫」と判定する最終取引からの経過日数のしきい値。
    dormantThresholdDays: 30,
    // ダッシュボード行に載せる通知履歴(ALERT)の最新件数上限。フォールバック集計(domo-access.js)が
    // この値でキャップし、集計DataFlow(dashboard_transform.py の ALERT_HISTORY_LIMIT)と同値に保つ。
    // 画面のアラート履歴一覧は別途 ALERT_HISTORY を直接読むため、この上限は集計行にのみ効く。
    alertHistoryLimit: 100
  })

  // QRのデバイス層（接頭辞 LOC:／ITEM: のパース、カメラ解像度・スキャン間隔・縮小サイズ）は
  // qr-scanner.js を唯一の定義源とし、ここには重複して持たない（層の責務分離）。
});
