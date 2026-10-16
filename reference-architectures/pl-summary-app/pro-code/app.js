/* ============================================================
   Store P/L AI Insights — self-contained single-card dashboard
   - live datasets (すべて実データ・凍結スナップショット無し):
       summary : 100 stores × 当月（KPI/ランキング/費用/カテゴリ/前月比/前年比/AI要約）
       trend   : 店舗×月×{rev,profit}（24ヶ月トレンド・店舗別/全社/月次ランキング）
       dept    : 部門×月×{rev,cogs,variance}（事業部別タブ）→ FE で DEPT オブジェクトへ再構成
     ＋ AppDB（店舗別/全社の analysis_html）
   - trend/dept は DataFlow の集計出力データセット（App Framework proxy は groupby/sum を 400 で
     拒否するため、集計は ETL 側で materialize し FE は fields+limit で live 取得する）。
     旧 window.__TREND__ / window.__DEPT__ の静的同梱は廃止（実データ差し替え時の凍結ドリフト防止）。
   - charts: hand-drawn SVG (no external deps)
   ============================================================ */



(function () {
  "use strict";

  var COLLECTION_NAME = "店舗別損益AI要約";
  var ALL_LABEL = "全社";
  var ALL_STORE_ID = "ALL";   // AppDB analysis lookup key for the company-wide doc

  var SUMMARY_FIELDS = [
    "店舗ID", "店舗名", "地域", "期間",
    "総売上", "総費用", "純利益", "利益率",
    "前年同月比売上変化率",
    "商品原価", "総人件費", "施設費", "マケ費用", "管理費用",
    "人件費比率", "管理費用比率",
    "収益性ステータス", "予算達成度", "リスクレベル",
    "店舗別AIサマリー"
  ];

  var COST_KEYS = [
    { key: "商品原価", label: "商品原価", color: "#7F1D2D" },
    { key: "総人件費", label: "総人件費", color: "#B23A48" },
    { key: "施設費",   label: "施設費",   color: "#C97B84" },
    { key: "マケ費用", label: "マケ費用", color: "#D8A7AC" },
    { key: "管理費用", label: "管理費用", color: "#E4C9CC" }
  ];

  var COMPANY_AI_FIELD = "全社AIサマリー";  // DataFlow TextGeneration 列。行ごと実行のため僅かに異なる複数バリアントが混在しうる（全て全社視点で等価）→ 表示側で最頻値を決定的に選択

  // trend / dept データセットの取得列（DataFlow 集計出力）。summary と同じ App Framework proxy 経由。
  var TREND_FIELDS = ["period", "store_id", "store", "region", "rev", "profit"];
  var DEPT_FIELDS = ["period", "code", "name", "rev", "cogs", "variance"];
  // 事業部の配色（コード→色）。旧 window.__DEPT__ に焼き込まれていた色を FE 定数へ移設。
  var DEPT_COLORS = { APPA: "#7F1D2D", LIFE: "#B23A48", FOOD: "#5F7A64", NEW: "#B8863B" };

  // 24ヶ月トレンド（店舗×月×{rev,profit}）と事業部別損益。いずれも DataFlow の集計出力データセットから
  // live 取得する（旧 window.__TREND__ / window.__DEPT__ の静的同梱は廃止）。ブートストラップで代入。
  // 収益4事業部のみが対象（間接部門は売上0のため集計時点で除外）。粗利益＝売上−売上原価（間接費は事業部非配賦）。
  // ※ モジュール変数として保持（drillFrom/描画関数が enclosing scope から参照。テストも DEPT を差し替える）。
  var TREND = [];
  var DEPT = null;

  // アクセント配色（単一の真実の源）。同じ意味の色はここを参照し、インラインで hex を書かない。
  // ※ トレンド線/棒の実体は app.css の .line-rev / .line-profit 等。ツールチップ・ランキングの
  //    swatch 色は下記で CSS と一致させること（片方だけ変えると凡例と本体がズレる）。
  var PALETTE = {
    rev: "#7F1D2D",     // 売上・プライマリ臙脂
    profit: "#5F7A64",  // 純利益・グリーン
    rankSel: "#5A0F1C"  // 選択店ハイライト
  };
  var BAR_COGS = "#C97B84", BAR_GROSS = PALETTE.profit; // 事業部積み上げ棒: 売上原価ローズ / 粗利益グリーン

  var els = {};
  var state = { stores: [], byId: {}, period: "", companyAi: "", reqSeq: 0, sel: ALL_LABEL, isAll: true, view: null };
  var activateTab = null;  // initViewTabs() が代入。render() から事業部別タブの表示/非表示制御に使う

  // ドリルダウン（カード内でビューが切り替わる Domo 標準カード相当のドリルパス）。
  // チャートごとに独立したフレームスタックを持ち、末尾が現在のビュー。空 = トップレベル。
  // フレーム例: {type:"storesForPeriod",period} / {type:"storeTrend",storeId,storeName} /
  //   {type:"monthDetail",...} / {type:"storesForCategory",catKey,catLabel} / {type:"storeCosts",...} /
  //   {type:"storeCostTable",...} / {type:"deptMonthly",code,name} / {type:"deptMonthBreakdown",period} /
  //   {type:"deptMonthDetail",code,name,period}
  var DRILL = { trend: [], donut: [], rank: [], deptBar: [], deptDonut: [], deptTrend: [] };
  var DRILL_KEYS = ["trend", "donut", "rank", "deptBar", "deptDonut", "deptTrend"];
  var deptLineSeries = [];  // 事業部トレンド系の現在の系列（ツールチップ・フォーカス点が参照）

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    els.loading = document.getElementById("loading");
    els.dashboard = document.getElementById("dashboard");
    els.message = document.getElementById("message-container");
    els.select = document.getElementById("store-select");
    els.eyebrow = document.getElementById("view-eyebrow");
    els.title = document.getElementById("view-title");
    els.badges = document.getElementById("badges");
    els.kpis = document.getElementById("kpis");
    els.aiQuick = document.getElementById("ai-quick");
    els.trend = document.getElementById("chart-trend");
    els.legendTrend = document.getElementById("legend-trend");
    els.donut = document.getElementById("chart-donut");
    els.rank = document.getElementById("chart-rank");
    els.rankTitle = document.getElementById("rank-title");
    els.analysis = document.getElementById("analysis-container");
    els.insightNote = document.getElementById("insight-note");
    els.titleTrend = document.getElementById("title-trend");
    els.titleDonut = document.getElementById("title-donut");
    els.legendRank = document.getElementById("legend-rank");
    window.addEventListener("pl-workflow-completed", function () { if (state.view) render(state.sel); });

    // 事業部別損益セクション（全社ビューのみ表示）
    els.deptSection = document.getElementById("dept-section");
    els.deptPeriodNote = document.getElementById("dept-period-note");
    els.deptBar = document.getElementById("chart-dept-bar");
    els.legendDeptBar = document.getElementById("legend-dept-bar");
    els.deptDonut = document.getElementById("chart-dept-donut");
    els.deptTrend = document.getElementById("chart-dept-trend");
    els.legendDeptTrend = document.getElementById("legend-dept-trend");
    els.deptTable = document.getElementById("dept-budget-table");
    els.titleDeptBar = document.getElementById("title-dept-bar");
    els.titleDeptDonut = document.getElementById("title-dept-donut");
    els.titleDeptTrend = document.getElementById("title-dept-trend");

    initViewTabs();
    // Chart hover tooltips (bound once; delegated listeners survive innerHTML redraws)
    els.tipTrend = makeTip(els.trend);
    els.tipDonut = makeTip(els.donut);
    els.tipRank = makeTip(els.rank);
    bindChartHover(els.trend, els.tipTrend, [trendLineSpec, storeBarSpec]);
    bindChartHover(els.donut, els.tipDonut, [sliceSpec]);
    bindChartHover(els.rank, els.tipRank, [rankSpec, trendLineSpec]);
    // Department chart tooltips（全社ビューのみ意味を持つが、要素は常設なのでここで一度だけ配線する）。
    // ※ DEPT は非同期ロードで後から代入されるため、init 時点の DEPT 有無で分岐しない（分岐すると
    //    事業部チャートのツールチップが二度と配線されない）。事業部セクション非表示時は無害。
    els.tipDeptBar = makeTip(els.deptBar);
    els.tipDeptDonut = makeTip(els.deptDonut);
    els.tipDeptTrend = makeTip(els.deptTrend);
    bindChartHover(els.deptBar, els.tipDeptBar, [deptBarSpec, deptLineSpec]);
    bindChartHover(els.deptDonut, els.tipDeptDonut, [sliceSpec]);
    bindChartHover(els.deptTrend, els.tipDeptTrend, [deptLineSpec, deptMonthSpec]);
    // Drill-down bars + delegated click/keyboard wiring (survives innerHTML redraws)
    els.drillBars = {};
    [
      ["trend", els.trend], ["donut", els.donut], ["rank", els.rank],
      ["deptBar", els.deptBar], ["deptDonut", els.deptDonut], ["deptTrend", els.deptTrend]
    ].forEach(function (pair) {
      els.drillBars[pair[0]] = makeDrillBar(pair[1]);
      bindDrillBar(els.drillBars[pair[0]], pair[0]);
      bindDrill(pair[1], pair[0]);
    });

    // カード幅が変わったら現在のドリルフレームのまま再描画（SVG を実寸で描き直す）。ドリル状態は保持。
    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (!state.view) return;
        ["trend", "donut", "rank"].forEach(renderCard);
        if (DEPT && els.deptSection && !els.deptSection.classList.contains("hidden")) {
          ["deptBar", "deptDonut", "deptTrend"].forEach(renderCard);
        }
      }, 150);
    });

    Promise.all([loadSummary(), loadCompanyAi(), loadTrend(), loadDept()])
      .then(function (res) {
        var rows = res[0];
        if (!rows || !rows.length) throw new Error("損益データが空です");
        state.stores = rows.map(normalizeStore);
        state.stores.forEach(function (s) { state.byId[s.id] = s; });
        state.period = rows[0]["期間"] || rows[0].period || "";
        state.companyAi = res[1] || "";
        TREND = res[2] || [];    // 24ヶ月トレンド（live・空なら折れ線は空表示）
        DEPT = res[3] || null;   // 事業部別（live・未取得なら updateDeptTab が事業部タブを自動非表示）
        buildSelector();
        els.loading.classList.add("hidden");
        els.dashboard.classList.remove("hidden");
        render(ALL_LABEL);
      })
      .catch(function (err) {
        els.loading.classList.add("hidden");
        console.error("[pl] データ取得に失敗:", err);
        showMessage("データを取得できませんでした。少し時間をおいてから再読み込みしてください。", true);
      });
  }

  /* ---------------- data ---------------- */

  function loadSummary() {
    var qs = "/data/v1/summary?fields=" + encodeURIComponent(SUMMARY_FIELDS.join(",")) + "&limit=1000";
    return domo.get(qs);
  }

  // 全社短文サマリー。DataFlow の TextGeneration は行ごとに実行されるため、同一入力でも
  // 僅かに異なる複数バリアントが生成されうる（内容はいずれも全社視点で等価）。全行を取得して
  // 最頻値（canonical）を決定的に選ぶことで、リロードごとに表示が揺れないようにする。
  // 列が未生成でも本体を壊さないよう、独立クエリ＋失敗時は空文字で握りつぶす。
  function loadCompanyAi() {
    var qs = "/data/v1/summary?fields=" + encodeURIComponent(COMPANY_AI_FIELD) + "&limit=1000";
    return domo.get(qs)
      .then(function (rows) { return pickMode(rows, COMPANY_AI_FIELD); })
      .catch(function () { return ""; });
  }

  // 非空値の最頻値を返す（行順は安定なので決定的：同数なら先に最大カウントへ到達した値）。
  function pickMode(rows, field) {
    if (!rows || !rows.length) return "";
    var counts = {}, best = "", bestN = 0;
    for (var i = 0; i < rows.length; i++) {
      var v = rows[i] && rows[i][field];
      if (!v) continue;
      counts[v] = (counts[v] || 0) + 1;
      if (counts[v] > bestN) { bestN = counts[v]; best = v; }
    }
    return best;
  }

  function normalizeStore(r) {
    return {
      id: r["店舗ID"], name: r["店舗名"], region: r["地域"],
      sales: num(r["総売上"]), cost: num(r["総費用"]), profit: num(r["純利益"]),
      margin: num(r["利益率"]),
      yoyRev: num(r["前年同月比売上変化率"]),
      cogs: num(r["商品原価"]), labor: num(r["総人件費"]), facility: num(r["施設費"]),
      marketing: num(r["マケ費用"]), admin: num(r["管理費用"]),
      laborRatio: num(r["人件費比率"]), adminRatio: num(r["管理費用比率"]),
      status: r["収益性ステータス"] || "", budget: num(r["予算達成度"]),
      risk: r["リスクレベル"] || "", aiSummary: r["店舗別AIサマリー"] || ""
    };
  }

  function queryAppDb(storeId) {
    var url = "/domo/datastores/v1/collections/" + encodeURIComponent(COLLECTION_NAME) +
      "/documents/query?sort=content.generated_at&descending=true&limit=1";
    var body = { "content.store_id": { "$eq": storeId } };
    return domo.post(url, body)
      .then(function (res) {
        var docs = Array.isArray(res) ? res : (res && res.documents) || [];
        return docs.length ? docs[0].content : null;
      })
      .catch(function () { return null; });
  }

  // 24ヶ月トレンド（店舗×月×{rev,profit}）を trend 集計データセットから live 取得する。
  // proxy は集計不可（groupby/sum 400）なので ETL 側で店舗×月に集計済み。100店×24ヶ月≒2,400行のため
  // limit を余裕を持って確保する。列は period/store_id/store/region/rev/profit（旧 __TREND__ と同形）。
  // 失敗・未マッピング時は空配列で握りつぶす（トレンド折れ線は空表示になるが本体は壊さない）。
  function loadTrend() {
    var qs = "/data/v1/trend?fields=" + encodeURIComponent(TREND_FIELDS.join(",")) + "&limit=5000";
    return domo.get(qs)
      .then(function (rows) {
        return (rows || []).map(function (r) {
          return {
            period: r.period || r["期間"] || "",
            store_id: r.store_id || r["店舗ID"] || "",
            store: r.store || r["店舗名"] || "",
            region: r.region || r["地域"] || "",
            rev: num(r.rev), profit: num(r.profit)
          };
        });
      })
      .catch(function () { return []; });
  }

  // 事業部別損益（部門×月×{rev,cogs,variance}）を dept 集計データセットから live 取得し、
  // 描画関数が期待する DEPT オブジェクト（divisions=FY合計 / monthly=月次系列）へ再構成する。
  // 収益4事業部のみ（間接部門は集計時点で除外）。粗利益=売上-売上原価、予算=粗利-予算差異、達成率=粗利/予算。
  // 失敗・未マッピング時は null（updateDeptTab が事業部タブを自動的に隠す）。
  function loadDept() {
    var qs = "/data/v1/dept?fields=" + encodeURIComponent(DEPT_FIELDS.join(",")) + "&limit=1000";
    return domo.get(qs)
      .then(function (rows) { return buildDept(rows || []); })
      .catch(function () { return null; });
  }

  // 部門×月の行配列 → DEPT オブジェクトへ再構成（旧 window.__DEPT__ と同形）。行が無ければ null。
  function buildDept(rows) {
    if (!rows || !rows.length) return null;
    var periods = {}, byCode = {}, order = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var code = r.code || r["部門コード"] || "";
      var period = r.period || r["期間"] || "";
      if (!code || !period) continue;
      periods[period] = true;
      var d = byCode[code];
      if (!d) {
        d = byCode[code] = {
          code: code, name: r.name || r["部門"] || code,
          color: DEPT_COLORS[code] || "#8896A6",
          rev: 0, cogs: 0, variance: 0, monthly: {}
        };
        order.push(code);
      }
      var rev = num(r.rev), cogs = num(r.cogs);
      d.rev += rev; d.cogs += cogs; d.variance += num(r.variance);
      d.monthly[period] = (d.monthly[period] || 0) + rev;   // 月次系列は売上（旧 __DEPT__ の series.rev と同義）
    }
    var periodList = Object.keys(periods).sort();
    if (!periodList.length) return null;
    var divisions = order.map(function (code) {
      var d = byCode[code];
      var gross = d.rev - d.cogs;
      var budget = gross - d.variance;   // 予算 = 粗利 - 予算差異（実績-予算=差異）
      return {
        code: d.code, name: d.name, color: d.color,
        rev: d.rev, cogs: d.cogs, gross: gross, variance: d.variance,
        budget: budget, achieve: budget ? Math.round((gross / budget) * 1000) / 10 : 0
      };
    });
    var series = order.map(function (code) {
      var d = byCode[code];
      return {
        code: d.code, name: d.name, color: d.color,
        rev: periodList.map(function (p) { return d.monthly[p] || 0; })
      };
    });
    return {
      fy: parseInt((periodList[0] || "").slice(0, 4), 10) || null,
      from: periodList[0], to: periodList[periodList.length - 1],
      divisions: divisions,
      monthly: { periods: periodList, series: series }
    };
  }

  /* ---------------- selector ---------------- */

  function buildSelector() {
    var html = ['<option value="__ALL__">' + esc(ALL_LABEL + "（全店舗合算）") + "</option>"];
    var regions = {};
    state.stores.forEach(function (s) { (regions[s.region] = regions[s.region] || []).push(s); });
    Object.keys(regions).sort().forEach(function (region) {
      html.push('<optgroup label="' + esc(region) + '">');
      regions[region].sort(byProfitDesc).forEach(function (s) {
        html.push('<option value="' + esc(s.id) + '">' + esc(s.name) + "</option>");
      });
      html.push("</optgroup>");
    });
    els.select.innerHTML = html.join("");
    els.select.addEventListener("change", function () {
      render(this.value === "__ALL__" ? ALL_LABEL : this.value);
    });
  }

  /* ---------------- render ---------------- */

  function render(sel) {
    var isAll = (sel === ALL_LABEL);
    var view = isAll ? companyView() : storeView(state.byId[sel]);
    if (!view) { showMessage("選択した店舗のデータが見つかりません"); return; }
    hideMessage();

    state.sel = sel;
    state.isAll = isAll;
    state.view = view;
    DRILL_KEYS.forEach(function (k) { DRILL[k].length = 0; }); // 店舗/全社の切替でドリル状態をリセット

    els.eyebrow.textContent = (state.period ? state.period + " 時点" : "") + (isAll ? " ・ " + state.stores.length + "店舗" : " ・ " + view.region);
    els.title.textContent = view.title;
    renderBadges(view);
    renderKpis(view, isAll);
    renderQuickAi(view);
    renderTrendCard();
    renderDonutCard();
    renderRankCard();
    updateDeptTab(isAll);
    renderDeptSection(isAll);

    // AI insight HTML (AppDB) — async, graceful fallback.
    // reqSeq guards against out-of-order resolution when the store is switched rapidly:
    // a stale response must not overwrite the current store's report.
    var myReq = ++state.reqSeq;
    els.analysis.classList.remove("ready");
    els.analysis.innerHTML = '<div class="ai-pending"><div class="spinner sm"></div><p>AI インサイトを読み込み中…</p></div>';
    var lookup = isAll ? ALL_STORE_ID : view.id;
    queryAppDb(lookup).then(function (content) {
      if (myReq !== state.reqSeq) return; // a newer selection superseded this request
      if (content && content.analysis_html) {
        try {
          els.analysis.innerHTML = sanitizeReportHtml(content.analysis_html);
        } catch (error) {
          console.error("[pl] AIレポート表示に失敗:", error);
          els.analysis.innerHTML = '<div class="ai-pending" role="alert"><p>AIレポートを表示できませんでした。時間をおいて再度お試しください。</p></div>';
          els.insightNote.textContent = "";
          return;
        }
        stripReportTitle(els.analysis);
        markReportMeta(els.analysis);
        els.analysis.classList.add("ready");
        els.insightNote.textContent = content.generated_at ? "生成: " + String(content.generated_at).slice(0, 10) : "";
      } else {
        els.analysis.innerHTML = '<div class="ai-pending"><p><b>AI 詳細インサイトは準備中です。</b></p>' +
          '<p>この店舗の詳細分析は次回の AI 分析更新後に表示されます。上部の AI サマリーで最新の要点をご確認ください。</p></div>';
        els.insightNote.textContent = "";
      }
    });
  }

  function companyView() {
    var s = state.stores;
    var sales = sum(s, "sales"), cost = sum(s, "cost"), profit = sum(s, "profit");
    var profitable = s.filter(function (x) { return x.profit > 0; }).length;
    var v = {
      isAll: true, title: ALL_LABEL + "サマリー", region: "全社",
      sales: sales, cost: cost, profit: profit,
      margin: sales ? (profit / sales) * 100 : 0,
      profitable: profitable, total: s.length,
      status: profit >= 0 ? "黒字" : "赤字",
      risk: "", budget: null,
      costs: COST_KEYS.map(function (c) {
        return { label: c.label, color: c.color, value: sum(s, costField(c.key)) };
      }),
      trend: trendFor(null)
    };
    // 全社短文サマリー: DataFlow の TextGeneration 由来（全行共通）を優先、
    // 未生成時は集計値からクライアント側で簡易生成してフォールバック。
    v.aiIsSynth = !state.companyAi;   // 実AI未生成時は集計フォールバック＝「AI」と偽らず区別する
    v.aiSummary = state.companyAi || synthCompanySummary(v);
    return v;
  }

  // 全社サマリー列が未生成のときのフォールバック（3段落・\n\n 区切り）
  function synthCompanySummary(v) {
    var pct = Math.round(v.margin * 10) / 10;
    var judge = v.margin >= 8 ? "好調" : v.margin >= 4 ? "堅調" : v.margin >= 0 ? "要注意" : "不振";
    var top = (v.costs || []).slice().sort(function (a, b) { return b.value - a.value; })[0];
    var costLine = (top && v.cost) ? top.label + "が総費用の約" + Math.round(top.value / v.cost * 100) + "%を占め" : "";
    var p1 = "全社は" + (v.profit >= 0 ? "黒字" : "赤字") + "基調。利益率" + pct + "%で" + judge + "、" +
      v.profitable + "/" + v.total + "店が黒字です。";
    var p2 = "純利益は" + jpMoney(v.profit) + "、総売上は" + jpMoney(v.sales) + "。" +
      (costLine ? costLine + "、コスト構造の管理が業績の要点です。" : "");
    var p3 = "次月は下位店舗の予算差異是正と固定費比率の抑制を優先し、全社利益率の底上げを図ります。";
    return [p1, p2, p3].join("\n\n");
  }

  function storeView(s) {
    if (!s) return null;
    return {
      isAll: false, id: s.id, name: s.name, title: s.name, region: s.region,
      sales: s.sales, cost: s.cost, profit: s.profit, margin: s.margin,
      yoyRev: s.yoyRev,
      status: s.status, risk: s.risk, budget: s.budget,
      laborRatio: s.laborRatio,
      costs: COST_KEYS.map(function (c) {
        return { label: c.label, color: c.color, value: s[costField(c.key)] };
      }),
      trend: trendFor(s.id),
      aiSummary: s.aiSummary
    };
  }

  function costField(k) {
    return { "商品原価": "cogs", "総人件費": "labor", "施設費": "facility", "マケ費用": "marketing", "管理費用": "admin" }[k];
  }

  function renderBadges(v) {
    var b = [];
    var st = v.status || "";
    var cls = /黒字|好調|堅調/.test(st) ? "pos" : (/赤字|不振|要注意/.test(st) ? "neg" : "mid");
    if (st) b.push('<span class="badge ' + cls + '">' + esc(st) + "</span>");
    if (v.risk) {
      var rc = /High|高/.test(v.risk) ? "neg" : (/Low|低/.test(v.risk) ? "pos" : "mid");
      b.push('<span class="badge ' + rc + '">リスク: ' + esc(v.risk) + "</span>");
    }
    if (v.isAll) b.push('<span class="badge pos">黒字 ' + v.profitable + " / " + v.total + "店</span>");
    els.badges.innerHTML = b.join("");
  }

  function renderKpis(v, isAll) {
    var cards;
    if (isAll) {
      cards = [
        kpi("総売上", jpMoney(v.sales)),
        kpi("純利益", jpMoney(v.profit), v.profit >= 0 ? "pos" : "neg"),
        kpi("利益率", fmtPct(v.margin), v.margin >= 0 ? "pos" : "neg"),
        kpi("黒字店舗", v.profitable + " / " + v.total + " 店")
      ];
    } else {
      cards = [
        kpi("総売上", jpMoney(v.sales)),
        kpi("純利益", jpMoney(v.profit), v.profit >= 0 ? "pos" : "neg"),
        kpi("利益率", fmtPct(v.margin), v.margin >= 0 ? "pos" : "neg"),
        kpi("前年同月比 売上", fmtSignedPct(v.yoyRev), v.yoyRev >= 0 ? "pos" : "neg")
      ];
    }
    els.kpis.innerHTML = cards.join("");
  }

  function kpi(label, value, tone) {
    return '<div class="kpi">' +
      '<div class="kpi-label">' + esc(label) + "</div>" +
      '<div class="kpi-value ' + (tone || "") + '">' + esc(value) + "</div></div>";
  }

  function renderQuickAi(v) {
    if (v.aiSummary) {
      var paras = String(v.aiSummary).split(/\n+/).filter(Boolean)
        .map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("");
      // 実AI出力か、未生成時の集計フォールバックかを明示的に区別する（合成文を「AI」と偽らない）。
      var mark = v.aiIsSynth
        ? '<div class="ai-quick-mark ai-quick-mark--synth">集計</div>'
        : '<div class="ai-quick-mark">AI</div>';
      var note = v.aiIsSynth
        ? '<p class="ai-quick-note">AI要約は未生成のため、集計値から自動作成した概要を表示しています。</p>'
        : '<p class="ai-quick-note">AIが生成した要約です。重要な判断の前に数値をご確認ください。</p>';
      els.aiQuick.innerHTML = mark + '<div class="ai-quick-body">' + paras + note + "</div>";
      els.aiQuick.classList.remove("hidden");
    } else {
      els.aiQuick.classList.add("hidden");
      els.aiQuick.innerHTML = "";
    }
  }

  /* ---------------- view tabs (概要 / 事業部別 / サマリー) ---------------- */

  // 概要（KPI・チャート・短文AI）／事業部別（全社ビュー限定の事業部別損益）／サマリー（AppDB analysis_html 全文）を切り替える。
  // ダッシュボードは静的HTMLなので初期化時に一度だけ配線する（描画のたびに再配線しない）。
  // 事業部別タブは店舗ビューでは updateDeptTab() が .hidden で隠すため、キーボードナビは「表示中タブのみ」で回す。
  function initViewTabs() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".view-tab"));
    var panels = {
      overview: document.getElementById("panel-overview"),
      department: document.getElementById("panel-department"),
      summary: document.getElementById("panel-summary")
    };
    function visibleTabs() {
      return tabs.filter(function (t) { return !t.classList.contains("hidden"); });
    }
    function activate(name) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("data-tab") === name;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1; // 隠しタブは active になり得ない（updateDeptTab が保証）ため常に -1
      });
      Object.keys(panels).forEach(function (k) {
        if (panels[k]) panels[k].classList.toggle("active", k === name);
      });
      clearChartTips(); // hiding a panel doesn't fire mouseleave — drop any lingering tooltip/guide
    }
    activateTab = activate; // モジュールスコープへ公開（updateDeptTab から呼ぶ）
    tabs.forEach(function (t) {
      t.addEventListener("click", function () { activate(t.getAttribute("data-tab")); });
      t.addEventListener("keydown", function (e) {
        var vis = visibleTabs(), idx = vis.indexOf(t), ni = idx;
        if (idx < 0) return; // 隠しタブ上のキー入力は無視
        if (e.key === "ArrowRight" || e.key === "ArrowDown") ni = (idx + 1) % vis.length;
        else if (e.key === "ArrowLeft" || e.key === "ArrowUp") ni = (idx - 1 + vis.length) % vis.length;
        else if (e.key === "Home") ni = 0;
        else if (e.key === "End") ni = vis.length - 1;
        else return;
        e.preventDefault();
        vis[ni].focus();
        activate(vis[ni].getAttribute("data-tab"));
      });
    });
    activate("overview");
  }

  // 事業部別データは全社ビュー限定。店舗選択時（または万一 DEPT 未ロード時）はタブごと隠し、
  // そのタブ表示中だった場合は概要へ戻す。表示条件は renderDeptSection のガードと一致させる。
  function updateDeptTab(isAll) {
    var tab = document.getElementById("tab-department");
    if (!tab) return;
    var show = isAll && DEPT && DEPT.divisions && DEPT.divisions.length;
    if (show) {
      tab.classList.remove("hidden");
      tab.removeAttribute("aria-hidden");
    } else {
      var wasActive = tab.classList.contains("active");
      tab.classList.add("hidden");
      tab.setAttribute("aria-hidden", "true");
      tab.tabIndex = -1;
      if (wasActive && activateTab) activateTab("overview"); // 隠すタブが表示中なら概要へフォールバック
    }
  }

  // パネルを隠しても mouseleave は発火しないため、タブ切替時に残存するツールチップ状態を明示的に消す。
  // init() では tip 要素の代入前に activate("overview") が走るので、未代入でも安全なようガードする。
  function clearChartTips() {
    [els.tipTrend, els.tipDonut, els.tipRank, els.tipDeptBar, els.tipDeptDonut, els.tipDeptTrend]
      .forEach(function (t) { if (t) hideTip(t); });
    [els.trend, els.deptTrend].forEach(function (host) {
      if (!host) return;
      var fade = host.querySelectorAll(".trend-guide, .trend-focus, .dfocus");
      Array.prototype.forEach.call(fade, function (n) { n.style.opacity = 0; });
    });
  }

  // レポート先頭の h1（表題）はカード見出し・ビュー表題と重複するため取り除く。
  function stripReportTitle(container) {
    var first = container.firstElementChild;
    while (first && first.tagName === "H1") {
      var next = first.nextElementSibling;
      container.removeChild(first);
      first = next;
    }
  }

  // AI レポート先頭のメタ行（店舗/期間/リスク等の「ラベル: 値 | …」）を識別する純粋判定。
  // 本文段落を誤ってメタ帯にしないよう、先頭が <p>・短い・「|」区切り・<b> ラベル付き、を条件にする。
  function isReportMeta(text, hasBold) {
    var t = String(text == null ? "" : text);
    return !!hasBold && t.length > 0 && t.length <= 300 && t.indexOf("|") >= 0;
  }

  // メタ行に .report-meta を付与（CSS が帯状に整形する）。構造が違うレポートは何もしない。
  function markReportMeta(container) {
    var first = container.firstElementChild;
    if (!first || first.tagName !== "P") return;
    if (!isReportMeta(first.textContent, !!first.querySelector("b"))) return;
    first.classList.add("report-meta");
  }

  /* ---------------- chart tooltips ---------------- */

  // ツールチップ要素は chart-body の親（.chart-card, position:relative）に置く。
  // chart-body の innerHTML は再描画で総入れ替えされるため、子に置くと消えてしまう。
  function makeTip(bodyEl) {
    var card = bodyEl.parentNode;
    var tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.setAttribute("aria-hidden", "true");
    card.appendChild(tip);
    return tip;
  }
  function moveTip(tip, bodyEl, clientX, clientY) {
    var r = bodyEl.parentNode.getBoundingClientRect();
    var x = clientX - r.left, y = clientY - r.top;
    var half = tip.offsetWidth / 2 + 6;
    if (x < half) x = half;
    if (x > r.width - half) x = r.width - half;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function showTip(tip, html) { tip.innerHTML = html; tip.classList.add("show"); }
  function hideTip(tip) { tip.classList.remove("show"); }

  // 祖先方向に指定属性を持つ要素を探す（SVG 要素にも対応）
  function closestAttr(node, attr, root) {
    while (node && node !== root) {
      if (node.getAttribute && node.getAttribute(attr) !== null) return node;
      node = node.parentNode;
    }
    return null;
  }

  function tipRow(color, label, val) {
    return '<div class="tip-row">' +
      (color ? '<span class="tip-sw" style="background:' + color + '"></span>' : '') +
      '<span>' + esc(label) + '</span>' +
      '<span class="tip-val">' + esc(val) + '</span></div>';
  }

  // ホバー仕様（marker → ツールチップ html + フォーカス操作）。1ホストに複数仕様を順に照合し、
  // その描画フレームに存在するマーカーだけがヒットする（redraw 後も delegated listener が生きる）。
  function bindChartHover(host, tip, specs) {
    function clearAll() { specs.forEach(function (s) { if (s.clear) s.clear(host); }); }
    // target から該当 spec を引き、ツールチップを client 座標 (cx, cy) に出す。見つかれば true。
    function showFor(target, cx, cy) {
      for (var i = 0; i < specs.length; i++) {
        var el = closestAttr(target, specs[i].marker, host);
        if (!el) continue;
        clearAll();
        if (specs[i].prepare) specs[i].prepare(host, el);
        showTip(tip, specs[i].html(el));
        moveTip(tip, host, cx, cy);
        return true;
      }
      return false;
    }
    host.addEventListener("mousemove", function (e) {
      if (!showFor(e.target, e.clientX, e.clientY)) { hideTip(tip); clearAll(); }
    });
    host.addEventListener("mouseleave", function () { hideTip(tip); clearAll(); });
    // キーボード操作: ドリル帯（tabindex=0）へフォーカスが入ったら、ホバーと同じツールチップを
    // 帯の bbox 中央上に出す。focusin/focusout は bubble するため、再描画後も host 委譲で生き続ける。
    host.addEventListener("focusin", function (e) {
      var r = e.target && e.target.getBoundingClientRect && e.target.getBoundingClientRect();
      if (r) showFor(e.target, (r.left + r.right) / 2, r.top + 24);
    });
    host.addEventListener("focusout", function () { hideTip(tip); clearAll(); });
  }

  // 2系列トレンド（売上/純利益）の縦ガイド線＋フォーカス点
  function setTrendFocus(host, hit, on) {
    var guide = host.querySelector(".trend-guide");
    var fRev = host.querySelector(".focus-rev");
    var fPro = host.querySelector(".focus-profit");
    if (!on || !hit) {
      if (guide) guide.style.opacity = 0;
      if (fRev) fRev.style.opacity = 0;
      if (fPro) fPro.style.opacity = 0;
      return;
    }
    var xx = hit.getAttribute("data-x");
    if (guide) { guide.setAttribute("x1", xx); guide.setAttribute("x2", xx); guide.style.opacity = 1; }
    if (fRev) { fRev.setAttribute("cx", xx); fRev.setAttribute("cy", hit.getAttribute("data-yrev")); fRev.style.opacity = 1; }
    if (fPro) { fPro.setAttribute("cx", xx); fPro.setAttribute("cy", hit.getAttribute("data-yprofit")); fPro.style.opacity = 1; }
  }
  function trendLineTipHtml(el) {
    return '<div class="tip-head">' + esc(longPeriod(el.getAttribute("data-period"))) + '</div>' +
      tipRow(PALETTE.rev, "売上", jpMoney(+el.getAttribute("data-rev"))) +
      tipRow(PALETTE.profit, "純利益", jpMoney(+el.getAttribute("data-profit")));
  }
  var trendLineSpec = {
    marker: "data-i", html: trendLineTipHtml,
    prepare: function (host, el) { setTrendFocus(host, el, true); },
    clear: function (host) { setTrendFocus(host, null, false); }
  };

  // 店舗の横棒（ランキング root は data-rank、ドリル後の店舗別横棒は data-store-bar）
  function storeBarTipHtml(el) {
    var html = '<div class="tip-head">' + esc(el.getAttribute("data-name")) + '</div>' +
      tipRow(PALETTE.rev, "売上", jpMoney(+el.getAttribute("data-rev"))) +
      tipRow(+el.getAttribute("data-profit") >= 0 ? PALETTE.profit : PALETTE.rev, "純利益", jpMoney(+el.getAttribute("data-profit")));
    var m = el.getAttribute("data-margin");
    if (m !== "" && m !== null) html += tipRow("", "利益率", fmtPct(+m));
    return html;
  }
  var storeBarSpec = { marker: "data-store-bar", html: storeBarTipHtml };

  function rankTipHtml(el) {
    var html = '<div class="tip-head">' + esc("#" + el.getAttribute("data-rank") + "  " + el.getAttribute("data-name")) + '</div>' +
      tipRow(+el.getAttribute("data-profit") >= 0 ? PALETTE.profit : PALETTE.rev, "純利益", jpMoney(+el.getAttribute("data-profit")));
    var m = el.getAttribute("data-margin");
    if (m !== "" && m !== null) html += tipRow("", "利益率", fmtPct(+m));
    return html;
  }
  var rankSpec = { marker: "data-rank", html: rankTipHtml };

  // ドーナツ / カテゴリ別店舗横棒（同一の data-slice 契約で共通ツールチップ）
  function donutTipHtml(el) {
    return '<div class="tip-head">' + esc(el.getAttribute("data-label")) + '</div>' +
      tipRow(el.getAttribute("data-color") || PALETTE.rev, "構成比", el.getAttribute("data-pct") + "%") +
      tipRow("", "金額", jpMoney(+el.getAttribute("data-value")));
  }
  var sliceSpec = { marker: "data-slice", html: donutTipHtml };

  // 事業部（積み上げ棒 root / 月次内訳横棒）
  function deptBarTipHtml(el) {
    var rev = +el.getAttribute("data-rev"), cogs = +el.getAttribute("data-cogs"), gross = +el.getAttribute("data-gross");
    return '<div class="tip-head">' + esc(el.getAttribute("data-name")) + '</div>' +
      tipRow("", "売上", jpMoney(rev)) +
      tipRow(BAR_COGS, "売上原価", jpMoney(cogs)) +
      tipRow(BAR_GROSS, "粗利益", jpMoney(gross)) +
      tipRow("", "粗利率", fmtPct(rev ? gross / rev * 100 : 0));
  }
  var deptBarSpec = { marker: "data-dept", html: deptBarTipHtml };

  function deptMonthBarTipHtml(el) {
    var html = '<div class="tip-head">' + esc(el.getAttribute("data-name")) + '</div>' +
      tipRow(el.getAttribute("data-color") || PALETTE.rev, "売上", jpMoney(+el.getAttribute("data-rev")));
    var s = el.getAttribute("data-share");
    if (s !== "" && s !== null) html += tipRow("", "構成比", s + "%");
    return html;
  }
  var deptMonthSpec = { marker: "data-dept-month", html: deptMonthBarTipHtml };

  // 事業部の複数系列トレンド（縦ガイド線＋系列ごとのフォーカス点。系列は deptLineSeries が正本）
  function setDeptLineFocus(host, hit, on) {
    var guide = host.querySelector(".trend-guide");
    if (!on || !hit) {
      if (guide) guide.style.opacity = 0;
      Array.prototype.forEach.call(host.querySelectorAll(".dfocus"), function (n) { n.style.opacity = 0; });
      return;
    }
    var xx = hit.getAttribute("data-x");
    if (guide) { guide.setAttribute("x1", xx); guide.setAttribute("x2", xx); guide.style.opacity = 1; }
    deptLineSeries.forEach(function (s, si) {
      var f = host.querySelector(".dfocus-" + si);
      if (f) { f.setAttribute("cx", xx); f.setAttribute("cy", hit.getAttribute("data-y" + si)); f.style.opacity = 1; }
    });
  }
  function deptLineTipHtml(el) {
    var html = '<div class="tip-head">' + esc(longPeriod(el.getAttribute("data-period"))) + '</div>';
    deptLineSeries.forEach(function (s, si) {
      html += tipRow(s.color, shortDept(s.name), jpMoney(+el.getAttribute("data-v" + si)));
    });
    return html;
  }
  var deptLineSpec = {
    marker: "data-i", html: deptLineTipHtml,
    prepare: function (host, el) { setDeptLineFocus(host, el, true); },
    clear: function (host) { setDeptLineFocus(host, null, false); }
  };

  /* ---------------- drill-down engine (カード内でビューが切り替わるドリルパス) ---------------- */

  // チャートカードごとの描画ターゲット（本体・凡例・タイトル）。rank カードは trend と
  // 同じ折れ線/詳細表を再利用するため、描画関数はターゲットを受け取る形に統一する。
  function cardTarget(key) {
    var map = {
      trend: { host: els.trend, legend: els.legendTrend, titleEl: els.titleTrend },
      donut: { host: els.donut, legend: null, titleEl: els.titleDonut },
      rank: { host: els.rank, legend: els.legendRank, titleEl: els.rankTitle },
      deptBar: { host: els.deptBar, legend: els.legendDeptBar, titleEl: els.titleDeptBar },
      deptDonut: { host: els.deptDonut, legend: null, titleEl: els.titleDeptDonut },
      deptTrend: { host: els.deptTrend, legend: els.legendDeptTrend, titleEl: els.titleDeptTrend }
    };
    return map[key];
  }

  // チャート本体の直前（タイトル直下）にドリルパス用のバーを挿入する。
  function makeDrillBar(host) {
    var bar = document.createElement("div");
    bar.className = "drill-bar idle";
    host.parentNode.insertBefore(bar, host);
    return bar;
  }

  function rootLabel() {
    if (state.isAll) return ALL_LABEL;
    var s = state.byId[state.sel];
    return (s && s.name) || ALL_LABEL;
  }

  function deptByCode(code) {
    var divs = (DEPT && DEPT.divisions) || [];
    for (var i = 0; i < divs.length; i++) if (divs[i].code === code) return divs[i];
    return { code: code, name: code, color: PALETTE.rev };
  }

  // パンくず1区画の表示名（適用フィルターの要約）
  function frameCrumb(f) {
    if (f.type === "storesForPeriod" || f.type === "deptMonthBreakdown" || f.type === "monthDetail" || f.type === "deptMonthDetail") return longPeriod(f.period);
    if (f.type === "storeTrend" || f.type === "storeCosts") return f.storeName;
    if (f.type === "storesForCategory") return f.catLabel;
    if (f.type === "storeCostTable") return "費用内訳";
    if (f.type === "deptMonthly") return f.name;
    return "";
  }

  function renderDrillBar(key, label) {
    var bar = els.drillBars[key];
    if (!bar) return;
    var stack = DRILL[key];
    if (!stack.length) {
      bar.className = "drill-bar idle";
      bar.innerHTML = '<span class="drill-hint">グラフ要素をクリックすると掘り下げられます</span>';
      return;
    }
    bar.className = "drill-bar";
    var parts = ['<button type="button" class="drill-btn drill-back" data-drill-act="pop">← 戻る</button>',
      '<span class="drill-path">',
      '<button type="button" class="drill-crumb" data-drill-act="to" data-drill-depth="0">' + esc(label) + "</button>"];
    stack.forEach(function (f, i) {
      var last = (i === stack.length - 1);
      parts.push('<span class="drill-sep" aria-hidden="true">›</span>');
      parts.push('<button type="button" class="drill-crumb' + (last ? " current" : "") +
        '" data-drill-act="to" data-drill-depth="' + (i + 1) + '"' + (last ? ' aria-current="true"' : "") + ">" +
        esc(frameCrumb(f)) + "</button>");
    });
    parts.push("</span>");
    parts.push('<button type="button" class="drill-btn drill-reset" data-drill-act="reset" aria-label="ドリルを解除してトップへ戻る">✕ 解除</button>');
    bar.innerHTML = parts.join("");
  }

  function bindDrillBar(bar, key) {
    bar.addEventListener("click", function (e) {
      var b = closestAttr(e.target, "data-drill-act", bar);
      if (!b) return;
      var act = b.getAttribute("data-drill-act");
      if (act === "pop") drillPop(key);
      else if (act === "reset") drillReset(key);
      else if (act === "to") drillToDepth(key, +b.getAttribute("data-drill-depth"));
    });
  }

  // チャート本体のクリック/キーボード（Enter/Space）を1回だけ配線。innerHTML 再描画後も
  // 委譲リスナーが生きるため、マーカー属性 data-drill を持つ要素なら何でも掘り下げられる。
  function bindDrill(host, key) {
    host.addEventListener("click", function (e) {
      var el = closestAttr(e.target, "data-drill", host);
      if (el) drillFrom(key, el);
    });
    host.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
      var el = closestAttr(e.target, "data-drill", host);
      if (!el) return;
      e.preventDefault();
      drillFrom(key, el);
    });
  }

  function topFrame(key) { var s = DRILL[key]; return s.length ? s[s.length - 1] : null; }
  function drillPush(key, frame) { DRILL[key].push(frame); renderCard(key); }
  function drillPop(key) { if (DRILL[key].length) { DRILL[key].pop(); renderCard(key); } }
  function drillReset(key) { DRILL[key].length = 0; renderCard(key); }
  function drillToDepth(key, depth) {
    var d = Math.max(0, Math.min(depth, DRILL[key].length));
    DRILL[key].length = d;
    renderCard(key);
  }

  function renderCard(key) {
    if (key === "trend") renderTrendCard();
    else if (key === "donut") renderDonutCard();
    else if (key === "rank") renderRankCard();
    else if (key === "deptBar") renderDeptBarCard();
    else if (key === "deptDonut") renderDeptDonutCard();
    else if (key === "deptTrend") renderDeptTrendCard();
  }

  function monthDetailFrame(storeId, storeName, period) {
    return { type: "monthDetail", storeId: storeId, storeName: storeName, period: period };
  }

  // data-drill の種類と現在フレームから次のフレームを決める（チャート別のドリルパス定義）。
  function drillFrom(key, el) {
    var kind = el.getAttribute("data-drill");
    var top = topFrame(key);

    if (key === "trend") {
      if (kind === "month" && !top) {
        if (state.isAll) drillPush(key, { type: "storesForPeriod", period: el.getAttribute("data-period") });
        else drillPush(key, monthDetailFrame(state.sel, state.view.name, el.getAttribute("data-period")));
      } else if (kind === "month" && top && top.type === "storeTrend") {
        drillPush(key, monthDetailFrame(top.storeId, top.storeName, el.getAttribute("data-period")));
      } else if (kind === "store" && top && top.type === "storesForPeriod") {
        drillPush(key, { type: "storeTrend", storeId: el.getAttribute("data-store-id"), storeName: el.getAttribute("data-name") });
      }
      return;
    }

    if (key === "donut") {
      if (kind === "slice" && !top) {
        if (state.isAll) drillPush(key, { type: "storesForCategory", catKey: el.getAttribute("data-key"), catLabel: el.getAttribute("data-label") });
        else drillPush(key, { type: "storeCostTable", storeId: state.sel, storeName: state.view.name, catKey: el.getAttribute("data-key"), catLabel: el.getAttribute("data-label") });
      } else if (kind === "cat-store" && top && top.type === "storesForCategory") {
        drillPush(key, { type: "storeCosts", storeId: el.getAttribute("data-store-id"), storeName: el.getAttribute("data-name"), catKey: top.catKey, catLabel: top.catLabel });
      } else if (kind === "slice" && top && top.type === "storeCosts") {
        drillPush(key, { type: "storeCostTable", storeId: top.storeId, storeName: top.storeName, catKey: el.getAttribute("data-key"), catLabel: el.getAttribute("data-label") });
      }
      return;
    }

    if (key === "rank") {
      if (kind === "rank" && !top) {
        drillPush(key, { type: "storeTrend", storeId: el.getAttribute("data-store-id"), storeName: el.getAttribute("data-name") });
      } else if (kind === "month" && top && top.type === "storeTrend") {
        drillPush(key, monthDetailFrame(top.storeId, top.storeName, el.getAttribute("data-period")));
      }
      return;
    }

    if (key === "deptBar" || key === "deptDonut") {
      if ((kind === "dept" || kind === "slice") && !top) {
        var d = deptByCode(el.getAttribute("data-key"));
        drillPush(key, { type: "deptMonthly", code: d.code, name: d.name });
      } else if (kind === "month" && top && top.type === "deptMonthly") {
        drillPush(key, { type: "deptMonthDetail", code: top.code, name: top.name, period: el.getAttribute("data-period") });
      }
      return;
    }

    if (key === "deptTrend") {
      if (kind === "month" && !top) {
        drillPush(key, { type: "deptMonthBreakdown", period: el.getAttribute("data-period") });
      } else if (kind === "dept" && top && top.type === "deptMonthBreakdown") {
        var d2 = deptByCode(el.getAttribute("data-key"));
        drillPush(key, { type: "deptMonthly", code: d2.code, name: d2.name });
      } else if (kind === "month" && top && top.type === "deptMonthly") {
        drillPush(key, { type: "deptMonthDetail", code: top.code, name: top.name, period: el.getAttribute("data-period") });
      }
      return;
    }
  }

  /* ---------------- drill frame rendering (チャートごとの現在ビュー) ---------------- */

  function renderTrendCard() {
    var top = topFrame("trend");
    if (!top) {
      drawTrend(state.view.trend, { drill: true, title: "売上・利益トレンド", note: "直近24ヶ月" });
    } else if (top.type === "storesForPeriod") {
      drawDivergingBars(els.trend, pickTopBottom(storeRowsForPeriod(top.period), 8, 5), { drillKind: "store" });
      setChartTitle(els.titleTrend, "店舗別 純利益", longPeriod(top.period) + "・上位8 / 下位5");
      els.legendTrend.innerHTML =
        '<span class="lg"><i class="sw sw-dot" style="background:' + PALETTE.profit + '"></i>黒字</span>' +
        '<span class="lg"><i class="sw sw-dot" style="background:' + PALETTE.rev + '"></i>赤字</span>';
    } else if (top.type === "storeTrend") {
      drawTrend(trendFor(top.storeId), { drill: true, title: top.storeName + " 売上・利益トレンド", note: "直近24ヶ月" });
    } else if (top.type === "monthDetail") {
      drawMonthDetail(top, cardTarget("trend"));
    }
    renderDrillBar("trend", rootLabel());
  }

  function renderDonutCard() {
    var top = topFrame("donut");
    if (!top) {
      var costs = state.view.costs.map(function (c, i) {
        return { label: c.label, color: c.color, value: c.value, key: COST_KEYS[i].key };
      });
      var total = costs.reduce(function (a, c) { return a + c.value; }, 0);
      donutInto(els.donut, costs, "総費用", { drill: true });
      setChartTitle(els.titleDonut, "費用構成", (state.isAll ? "" : state.view.name + "・") + jpMoney(total));
    } else if (top.type === "storesForCategory") {
      var cat = categoryStoreRows(top.catKey);
      drawHBars(els.donut, cat.rows, {
        tip: "slice", total: cat.total, valueFmt: jpMoney, drillKind: "cat-store",
        aria: function (r) { return r.name + " の費用構成を表示"; }
      });
      setChartTitle(els.titleDonut, top.catLabel + " の店舗別金額", "上位10店舗・全社");
    } else if (top.type === "storeCosts") {
      var store = state.byId[top.storeId];
      if (!store) { els.donut.innerHTML = emptyChart(); }
      else {
        var items = costsOfStore(store);
        var sumv = items.reduce(function (a, c) { return a + c.value; }, 0);
        donutInto(els.donut, items, "総費用", { drill: true, highlight: top.catKey });
        setChartTitle(els.titleDonut, top.storeName + " の費用構成", "総費用 " + jpMoney(sumv));
      }
    } else if (top.type === "storeCostTable") {
      drawStoreCostTable(top);
    }
    renderDrillBar("donut", rootLabel());
  }

  function renderRankCard() {
    var top = topFrame("rank");
    if (!top) {
      drawRanking(state.isAll ? null : state.view.id);
    } else if (top.type === "storeTrend") {
      drawTrend(trendFor(top.storeId), { target: cardTarget("rank"), drill: true, title: top.storeName + " 売上・利益トレンド", note: "直近24ヶ月" });
    } else if (top.type === "monthDetail") {
      drawMonthDetail(top, cardTarget("rank"));
    }
    renderDrillBar("rank", rootLabel());
  }

  function renderDeptBarCard() {
    var top = topFrame("deptBar");
    if (!top) drawDeptBar(DEPT.divisions);
    else if (top.type === "deptMonthly") drawDeptMonthly(top, cardTarget("deptBar"));
    else if (top.type === "deptMonthDetail") drawDeptMonthDetail(top, cardTarget("deptBar"));
    renderDrillBar("deptBar", ALL_LABEL);
  }

  function renderDeptDonutCard() {
    var top = topFrame("deptDonut");
    if (!top) drawDeptDonut();
    else if (top.type === "deptMonthly") drawDeptMonthly(top, cardTarget("deptDonut"));
    else if (top.type === "deptMonthDetail") drawDeptMonthDetail(top, cardTarget("deptDonut"));
    renderDrillBar("deptDonut", ALL_LABEL);
  }

  function renderDeptTrendCard() {
    var top = topFrame("deptTrend");
    if (!top) {
      drawDeptTrend(DEPT.monthly, { drill: true, title: "事業部別 月次売上トレンド", note: DEPT.fy + "年度・月次の季節変動を確認" });
    } else if (top.type === "deptMonthBreakdown") {
      drawDeptMonthBreakdown(top);
    } else if (top.type === "deptMonthly") {
      drawDeptMonthly(top, cardTarget("deptTrend"));
    } else if (top.type === "deptMonthDetail") {
      drawDeptMonthDetail(top, cardTarget("deptTrend"));
    }
    renderDrillBar("deptTrend", ALL_LABEL);
  }

  /* ---------------- trend aggregation ---------------- */

  function trendFor(storeId) {
    var rows = TREND;
    var byPeriod = {};
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (storeId && r.store_id !== storeId) continue;
      var p = byPeriod[r.period] || (byPeriod[r.period] = { period: r.period, rev: 0, profit: 0 });
      p.rev += r.rev; p.profit += r.profit;
    }
    return Object.keys(byPeriod).sort().map(function (k) { return byPeriod[k]; });
  }

  /* ---------------- SVG: trend line ---------------- */

  // 2系列（売上/純利益）折れ線。opts.target で描画先カード（trend / rank）を差し替え、
  // opts.drill で各月のヒットバンドをクリック/キーボードで掘り下げ可能にする。
  function drawTrend(data, opts) {
    opts = opts || {};
    var target = opts.target || cardTarget("trend");
    var host = target.host, legend = target.legend;
    if (!data || !data.length) { host.innerHTML = emptyChart(); if (legend) legend.innerHTML = ""; setChartTitle(target.titleEl, opts.title || "売上・利益トレンド", opts.note || ""); return; }
    // カード幅に合わせて実寸描画（viewBox 幅＝CSS px）。文字は縮小されない。
    var W = chartWidth(host);
    var H = Math.max(300, Math.min(420, Math.round(W * 0.45)));
    var ml = W < 480 ? 52 : 64, mr = 16, mt = 16, mb = 40;
    var iw = W - ml - mr, ih = H - mt - mb;
    var vals = [];
    data.forEach(function (d) { vals.push(d.rev, d.profit); });
    var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals.concat([0]));
    if (min > 0) min = 0;
    var pad = (max - min) * 0.08 || 1;
    max += pad; min -= pad;
    var n = data.length;
    var x = function (i) { return ml + (n === 1 ? iw / 2 : iw * i / (n - 1)); };
    var y = function (val) { return mt + ih * (1 - (val - min) / (max - min)); };

    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var gv = min + (max - min) * t / ticks;
      var gy = y(gv);
      svg.push(line(ml, gy, W - mr, gy, "grid"));
      svg.push(text(ml - 8, gy + 4, jpCompact(gv), "axis-y"));
    }
    if (min < 0 && max > 0) svg.push(line(ml, y(0), W - mr, y(0), "zero"));
    var xStep = W < 480 ? 6 : 3; // 狭いカードでは月ラベルを間引く
    for (var i = 0; i < n; i++) {
      if (i % xStep === 0 || i === n - 1) svg.push(text(x(i), H - 14, shortPeriod(data[i].period), "axis-x"));
    }
    var revPts = data.map(function (d, i) { return x(i) + "," + y(d.rev); }).join(" ");
    var proPts = data.map(function (d, i) { return x(i) + "," + y(d.profit); }).join(" ");
    svg.push('<polyline points="' + revPts + '" class="line-rev"/>');
    svg.push('<polyline points="' + proPts + '" class="line-profit"/>');
    svg.push(dot(x(n - 1), y(data[n - 1].rev), "dot-rev"));
    svg.push(dot(x(n - 1), y(data[n - 1].profit), "dot-profit"));
    // hover guide + focus points (positioned by JS on hover)
    svg.push('<line class="trend-guide" x1="0" y1="' + mt + '" x2="0" y2="' + (mt + ih) + '"/>');
    svg.push('<circle class="trend-focus focus-rev" cx="0" cy="0" r="4.5"/>');
    svg.push('<circle class="trend-focus focus-profit" cx="0" cy="0" r="4.5"/>');
    // transparent hit bands (one per period) carry the tooltip data
    for (var h = 0; h < n; h++) {
      var cxp = x(h);
      var x0 = h === 0 ? ml : (x(h - 1) + cxp) / 2;
      var x1b = h === n - 1 ? (W - mr) : (cxp + x(h + 1)) / 2;
      var drill = opts.drill ? ' data-drill="month" tabindex="0" role="button" aria-label="' +
        esc(longPeriod(data[h].period) + "、売上 " + jpMoney(data[h].rev) +
          "、純利益 " + jpMoney(data[h].profit) + "。内訳を表示") + '"' : "";
      svg.push('<rect class="trend-hit"' + drill + ' data-i="' + h + '"' +
        ' data-x="' + cxp.toFixed(1) + '" data-yrev="' + y(data[h].rev).toFixed(1) +
        '" data-yprofit="' + y(data[h].profit).toFixed(1) + '"' +
        ' data-period="' + esc(data[h].period) + '" data-rev="' + data[h].rev +
        '" data-profit="' + data[h].profit + '"' +
        ' x="' + x0.toFixed(1) + '" y="' + mt + '" width="' + (x1b - x0).toFixed(1) + '" height="' + ih + '"/>');
    }
    svg.push("</svg>");
    host.innerHTML = svg.join("");
    if (legend) {
      legend.innerHTML =
        '<span class="lg"><i class="sw sw-rev"></i>売上</span>' +
        '<span class="lg"><i class="sw sw-profit"></i>純利益</span>';
    }
    setChartTitle(target.titleEl, opts.title || "売上・利益トレンド", opts.note || "");
  }

  /* ---------------- SVG: donut ---------------- */

  // 汎用ドーナツ描画。items = [{label,color,value,key?}]。中央ラベルは centerLabel、中央値は合計。
  // opts.drill でスライスをクリック可能にし、opts.highlight（key）で他スライスを減光する。
  function donutInto(host, costs, centerLabel, opts) {
    opts = opts || {};
    var items = (costs || []).filter(function (c) { return c.value > 0; });
    var sumv = items.reduce(function (a, c) { return a + c.value; }, 0);
    if (!sumv) { host.innerHTML = emptyChart(); return; }
    var W = 300, H = 300, cx = 150, cy = 140, r = 104, rin = 64;
    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    var ang = -Math.PI / 2;
    items.forEach(function (c) {
      var frac = c.value / sumv;
      var a2 = ang + frac * Math.PI * 2;
      var attrs = 'data-slice="1" data-label="' + esc(c.label) + '" data-value="' + c.value +
        '" data-pct="' + Math.round(frac * 100) + '" data-color="' + c.color + '"';
      if (opts.drill) {
        attrs += ' data-drill="slice" data-key="' + esc(c.key || "") +
          '" tabindex="0" role="button" aria-label="' +
          esc(c.label + "、" + jpMoney(c.value) + "、構成比 " + Math.round(frac * 100) + "%。内訳を表示") + '"';
      }
      if (opts.highlight && c.key && c.key !== opts.highlight) attrs += ' style="opacity:.35"';
      svg.push(donutArc(cx, cy, r, rin, ang, a2, c.color, attrs));
      ang = a2;
    });
    svg.push('<text x="' + cx + '" y="' + (cy - 4) + '" class="donut-center-label">' + esc(centerLabel) + '</text>');
    svg.push('<text x="' + cx + '" y="' + (cy + 20) + '" class="donut-center-value">' + esc(jpCompact(sumv)) + "</text>");
    var ly = 250;
    items.forEach(function (c, i) {
      var col = i % 2, row = Math.floor(i / 2);
      var lx = 18 + col * 150, yy = ly + row * 20;
      svg.push('<rect x="' + lx + '" y="' + (yy - 9) + '" width="10" height="10" rx="2" fill="' + c.color + '"/>');
      svg.push('<text x="' + (lx + 16) + '" y="' + yy + '" class="donut-legend">' + esc(c.label) + " " + Math.round(c.value / sumv * 100) + "%</text>");
    });
    svg.push("</svg>");
    host.innerHTML = svg.join("");
  }

  /* ---------------- SVG: diverging ranking bars ---------------- */

  // チャートカードのタイトルを「見出し＋補足」で組み立て直す（ドリルで見出しが変わるため）。
  function setChartTitle(titleEl, main, note) {
    if (!titleEl) return;
    titleEl.innerHTML = esc(main) + (note ? '<span class="chart-note">' + esc(note) + "</span>" : "");
  }

  // 純利益の正負で左右に伸びる横棒（店舗別ランキング / 月次店舗別）。
  // rows = [{id,name,profit,margin,rev?}]。opts.rankOf で順位番号、opts.selectedId でハイライト、
  // opts.drillKind でクリック時の data-drill 種別を付与（クリック配線は各カードの bindDrill が拾う）。
  function drawDivergingBars(host, rows, opts) {
    opts = opts || {};
    var maxAbs = Math.max.apply(null, rows.map(function (s) { return Math.abs(s.profit); }).concat([1]));
    var W = chartWidth(host);
    var rowH = 34, gap = 10, mt = 8;
    // 店舗名カラムと金額カラムは幅に応じて比例配分（狭幅で棒が潰れないように）
    var labelW = Math.round(Math.min(230, Math.max(108, W * 0.30)));
    var valW = Math.round(Math.min(112, Math.max(72, W * 0.17)));
    var barArea = Math.max(60, W - labelW - valW - 16);
    var nameChars = Math.max(6, Math.floor((labelW - 12) / 13));
    var cx = labelW + barArea / 2;
    var H = mt * 2 + rows.length * (rowH + gap);
    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    svg.push(line(cx, mt, cx, H - mt, "zero"));
    var hits = [];
    rows.forEach(function (s, i) {
      var yy = mt + i * (rowH + gap);
      var isSel = opts.selectedId && s.id === opts.selectedId;
      var half = (Math.abs(s.profit) / maxAbs) * (barArea / 2);
      var pos = s.profit >= 0;
      var bx = pos ? cx : cx - half;
      var bw = Math.max(half, 1);
      var fill = isSel ? PALETTE.rankSel : (pos ? PALETTE.profit : PALETTE.rev);
      svg.push('<rect x="' + (labelW - 8) + '" y="' + yy + '" width="' + (W - labelW + 8) + '" height="' + rowH + '" class="rank-row' + (isSel ? " sel" : "") + '"/>');
      svg.push('<text x="8" y="' + (yy + rowH / 2 + 4) + '" class="rank-name' + (isSel ? " sel" : "") + '">' +
        (opts.rankOf ? '<tspan class="rank-num">' + opts.rankOf[s.id] + ".</tspan> " : "") + esc(trunc(s.name, nameChars)) + "</text>");
      svg.push('<rect x="' + bx + '" y="' + (yy + 6) + '" width="' + bw + '" height="' + (rowH - 12) + '" rx="3" fill="' + fill + '"/>');
      svg.push('<text x="' + (W - 8) + '" y="' + (yy + rowH / 2 + 4) + '" class="rank-val ' + (pos ? "pos" : "neg") + '">' + esc(jpMoney(s.profit)) + "</text>");
      hits.push('<rect class="rank-hit drill-hit"' +
        ' data-rank="' + (opts.rankOf ? opts.rankOf[s.id] : "") + '" data-store-bar="1"' +
        ' data-store-id="' + esc(s.id) + '" data-name="' + esc(s.name) + '"' +
        ' data-profit="' + s.profit + '" data-margin="' + (s.margin != null ? s.margin : "") + '"' +
        (s.rev != null ? ' data-rev="' + s.rev + '"' : "") +
        (opts.drillKind ? ' data-drill="' + opts.drillKind + '" tabindex="0" role="button" aria-label="' +
          esc(s.name + "、純利益 " + jpMoney(s.profit) +
            (s.rev != null ? "、売上 " + jpMoney(s.rev) : "") +
            (s.margin != null ? "、利益率 " + fmtPct(s.margin) : "") + "。推移を表示") + '"' : "") +
        ' x="' + (labelW - 8) + '" y="' + yy + '" width="' + (W - labelW + 8) + '" height="' + rowH + '"/>');
    });
    svg.push(hits.join(""));
    svg.push("</svg>");
    host.innerHTML = svg.join("");
  }

  function drawRanking(selectedId) {
    var all = state.stores.slice().sort(byProfitDesc);
    var rankOf = {};
    all.forEach(function (s, i) { rankOf[s.id] = i + 1; });
    var chosen = all.slice(0, 8).concat(all.slice(-5));
    if (selectedId) {
      var already = chosen.some(function (s) { return s.id === selectedId; });
      if (!already && state.byId[selectedId]) chosen.push(state.byId[selectedId]);
    }
    var seen = {}, rows = [];
    chosen.forEach(function (s) { if (!seen[s.id]) { seen[s.id] = 1; rows.push(s); } });
    rows.sort(byProfitDesc);

    drawDivergingBars(els.rank, rows, { rankOf: rankOf, selectedId: selectedId, drillKind: "rank" });
    setChartTitle(els.rankTitle, "店舗別 純利益ランキング", selectedId ? "選択店をハイライト" : "上位8 / 下位5");
    if (els.legendRank) {
      els.legendRank.innerHTML =
        '<span class="lg"><i class="sw sw-dot" style="background:' + PALETTE.profit + '"></i>黒字</span>' +
        '<span class="lg"><i class="sw sw-dot" style="background:' + PALETTE.rev + '"></i>赤字</span>';
    }
  }

  /* ---------------- 横棒（カテゴリ別店舗金額 / 事業部別月次売上） ---------------- */

  // 単方向の横棒。opts.tip = "slice"（カテゴリ別店舗金額）| "dept"（事業部別月次売上）。
  // opts.total があれば構成比(%)を計算してツールチップへ載せる。
  function drawHBars(host, rows, opts) {
    opts = opts || {};
    if (!rows.length) { host.innerHTML = emptyChart(); return; }
    var W = chartWidth(host);
    var mt = 8, rowH = 34, gap = 10;
    var labelW = Math.round(Math.min(230, Math.max(108, W * 0.30)));
    var valW = Math.round(Math.min(140, Math.max(80, W * 0.19)));
    var barArea = Math.max(60, W - labelW - valW - 16);
    var nameChars = Math.max(6, Math.floor((labelW - 12) / 13));
    var max = Math.max.apply(null, rows.map(function (r) { return Math.abs(r.value); }).concat([1]));
    var H = mt * 2 + rows.length * (rowH + gap);
    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    var hits = [];
    rows.forEach(function (r, i) {
      var yy = mt + i * (rowH + gap);
      var bw = Math.max((Math.abs(r.value) / max) * barArea, 1);
      var color = r.color || PALETTE.rev;
      var share = opts.total ? Math.round((r.value / opts.total) * 1000) / 10 : null;
      svg.push('<rect x="' + (labelW - 8) + '" y="' + yy + '" width="' + (W - labelW + 8) + '" height="' + rowH + '" class="rank-row"/>');
      svg.push('<text x="8" y="' + (yy + rowH / 2 + 4) + '" class="rank-name">' + esc(trunc(r.name, nameChars)) + "</text>");
      svg.push('<rect x="' + labelW + '" y="' + (yy + 6) + '" width="' + bw.toFixed(1) + '" height="' + (rowH - 12) + '" rx="3" fill="' + color + '"/>');
      svg.push('<text x="' + (W - 8) + '" y="' + (yy + rowH / 2 + 4) + '" class="rank-val">' + esc(opts.valueFmt(r.value)) + "</text>");
      var attrs = ' data-name="' + esc(r.name) + '"';
      if (opts.tip === "dept") {
        attrs += ' data-dept-month="1" data-rev="' + r.value +
          '" data-share="' + (share == null ? "" : share) + '" data-color="' + color + '"';
      } else {
        attrs += ' data-slice="1" data-label="' + esc(r.name) + '" data-value="' + r.value +
          '" data-pct="' + (share == null ? 0 : share) + '" data-color="' + color + '"';
      }
      hits.push('<rect class="drill-hit"' + attrs +
        ' data-drill="' + opts.drillKind + '"' +
        (r.storeId ? ' data-store-id="' + esc(r.storeId) + '"' : "") +
        (r.key ? ' data-key="' + esc(r.key) + '"' : "") +
        ' tabindex="0" role="button" aria-label="' + esc(opts.aria(r)) + '"' +
        ' x="' + (labelW - 8) + '" y="' + yy + '" width="' + (W - labelW + 8) + '" height="' + rowH + '"/>');
    });
    svg.push(hits.join(""));
    svg.push("</svg>");
    host.innerHTML = svg.join("");
  }

  /* ---------------- department P/L (事業部別損益 — 全社ビューのみ) ---------------- */

  // 全社ビューでのみ表示。店舗選択時は非表示（事業部は全社横断の切り口のため）。
  function renderDeptSection(isAll) {
    if (!els.deptSection) return;
    if (!isAll || !DEPT || !DEPT.divisions || !DEPT.divisions.length) {
      els.deptSection.classList.add("hidden");
      return;
    }
    els.deptSection.classList.remove("hidden");
    var divs = DEPT.divisions;
    els.deptPeriodNote.textContent = DEPT.fy + "年度（" + DEPT.from + "〜" + DEPT.to + "）・収益" + divs.length + "事業部";
    drawDeptBar(divs);
    drawDeptDonut();
    drawDeptTrend(DEPT.monthly, {
      drill: true,
      title: "事業部別 月次売上トレンド",
      note: DEPT.fy + "年度・月次の季節変動を確認"
    });
    renderBudgetTable(divs);
    renderDrillBar("deptBar", ALL_LABEL);
    renderDrillBar("deptDonut", ALL_LABEL);
    renderDrillBar("deptTrend", ALL_LABEL);
  }

  // 事業部の売上構成ドーナツ（全社ビューのみ）。スライスはクリックで事業部ドリルへ。
  function drawDeptDonut() {
    var divs = DEPT.divisions;
    var total = sum(divs, "rev");
    donutInto(els.deptDonut, divs.map(function (d) {
      return { label: shortDept(d.name), color: d.color, value: d.rev, key: d.code };
    }), "総売上", { drill: true });
    setChartTitle(els.titleDeptDonut, "売上構成比", jpMoney(total));
  }

  // 積み上げ縦棒: 各事業部の売上を 売上原価（下）＋ 粗利益（上）に分解して表示。
  // 各事業部の帯はクリックでその事業部の月次ドリルへ。
  function drawDeptBar(divs) {
    if (!divs.length) { els.deptBar.innerHTML = emptyChart(); els.legendDeptBar.innerHTML = ""; setChartTitle(els.titleDeptBar, "事業部別 売上・粗利", "積み上げ＝売上原価＋粗利益"); return; }
    var W = chartWidth(els.deptBar);
    var H = Math.max(320, Math.min(430, Math.round(W * 0.5)));
    var ml = W < 480 ? 52 : 64, mr = 16, mt = 26, mb = 44;
    var iw = W - ml - mr, ih = H - mt - mb;
    var yMax = Math.max.apply(null, divs.map(function (d) { return d.rev; })) * 1.12 || 1;
    var band = iw / divs.length, bw = Math.min(96, band * 0.5);
    var y = function (v) { return mt + ih * (1 - v / yMax); };
    var y0 = y(0);

    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var gv = yMax * t / ticks, gy = y(gv);
      svg.push(line(ml, gy, W - mr, gy, "grid"));
      svg.push(text(ml - 8, gy + 4, jpCompact(gv), "axis-y"));
    }
    var hits = [];
    divs.forEach(function (d, i) {
      var cx = ml + band * i + band / 2, bx = cx - bw / 2;
      var yCogs = y(d.cogs), yRev = y(d.rev);
      // 売上原価（下段）
      if (d.cogs > 0) svg.push('<rect x="' + bx + '" y="' + yCogs.toFixed(1) + '" width="' + bw + '" height="' + (y0 - yCogs).toFixed(1) + '" class="bar-cogs"/>');
      // 粗利益（上段）
      svg.push('<rect x="' + bx + '" y="' + yRev.toFixed(1) + '" width="' + bw + '" height="' + (yCogs - yRev).toFixed(1) + '" class="bar-gross"/>');
      // 粗利率（上段が十分高いときのみ内側に表示）
      if (yCogs - yRev > 22) svg.push('<text x="' + cx + '" y="' + ((yRev + yCogs) / 2 + 4).toFixed(1) + '" class="bar-inpct">' + Math.round(d.gross / d.rev * 100) + "%</text>");
      // 売上合計（棒上）
      svg.push('<text x="' + cx + '" y="' + (yRev - 8).toFixed(1) + '" class="bar-total">' + esc(jpCompact(d.rev)) + "</text>");
      // 事業部名（x軸）
      svg.push('<text x="' + cx + '" y="' + (H - 14) + '" class="bar-xlabel">' + esc(shortDept(d.name)) + "</text>");
      hits.push('<rect class="bar-hit drill-hit" data-dept="' + i + '" data-key="' + esc(d.code) + '" data-name="' + esc(d.name) +
        '" data-rev="' + d.rev + '" data-cogs="' + d.cogs + '" data-gross="' + d.gross +
        '" data-drill="dept" tabindex="0" role="button" aria-label="' +
        esc(d.name + "、売上 " + jpMoney(d.rev) + "、粗利益 " + jpMoney(d.gross) + "。月次推移を表示") + '"' +
        ' x="' + (ml + band * i) + '" y="' + mt + '" width="' + band + '" height="' + ih + '"/>');
    });
    svg.push(hits.join(""));
    svg.push("</svg>");
    els.deptBar.innerHTML = svg.join("");
    els.legendDeptBar.innerHTML =
      '<span class="lg"><i class="sw sw-dot sw-cogs"></i>売上原価</span>' +
      '<span class="lg"><i class="sw sw-dot sw-gross"></i>粗利益</span>';
    setChartTitle(els.titleDeptBar, "事業部別 売上・粗利", "積み上げ＝売上原価＋粗利益");
  }

  // 事業部別 月次売上トレンド（複数折れ線）。月次の季節変動を可視化。
  // opts.target で描画先カード（deptTrend / deptBar / deptDonut）を差し替え、opts.series で
  // 系列を絞り込む（事業部ドリル）。opts.drill で各月をクリック可能にする。
  function drawDeptTrend(monthly, opts) {
    opts = opts || {};
    var target = opts.target || cardTarget("deptTrend");
    var periods = (monthly && monthly.periods) || [];
    var series = opts.series || (monthly && monthly.series) || [];
    deptLineSeries = series; // ツールチップ/フォーカスは現在の系列を参照する
    if (!periods.length || !series.length) {
      target.host.innerHTML = emptyChart();
      if (target.legend) target.legend.innerHTML = "";
      setChartTitle(target.titleEl, opts.title || "事業部別 月次売上トレンド", opts.note || "");
      return;
    }
    var W = chartWidth(target.host);
    var H = Math.max(280, Math.min(400, Math.round(W * 0.35)));
    var ml = W < 480 ? 48 : 60, mr = 16, mt = 16, mb = 38;
    var iw = W - ml - mr, ih = H - mt - mb;
    var max = 0;
    series.forEach(function (s) { s.rev.forEach(function (v) { if (v > max) max = v; }); });
    max = max * 1.08 || 1;
    var n = periods.length;
    var x = function (i) { return ml + (n === 1 ? iw / 2 : iw * i / (n - 1)); };
    var y = function (v) { return mt + ih * (1 - v / max); };

    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" class="svg">'];
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var gv = max * t / ticks, gy = y(gv);
      svg.push(line(ml, gy, W - mr, gy, "grid"));
      svg.push(text(ml - 8, gy + 4, jpCompact(gv), "axis-y"));
    }
    var xStep = W < 480 ? 3 : 2; // 狭いカードでは月ラベルを間引く
    for (var i = 0; i < n; i++) {
      if (i % xStep === 0 || i === n - 1) svg.push(text(x(i), H - 12, shortPeriod(periods[i]), "axis-x"));
    }
    series.forEach(function (s) {
      var pts = s.rev.map(function (v, i) { return x(i) + "," + y(v); }).join(" ");
      svg.push('<polyline points="' + pts + '" class="dline" style="stroke:' + s.color + '"/>');
    });
    // hover guide + one focus dot per series (positioned by JS)
    svg.push('<line class="trend-guide" x1="0" y1="' + mt + '" x2="0" y2="' + (mt + ih) + '"/>');
    series.forEach(function (s, si) {
      svg.push('<circle class="dfocus dfocus-' + si + '" cx="0" cy="0" r="4" style="fill:' + s.color + '"/>');
    });
    // transparent hit bands carry every series' value + y at each period
    for (var h = 0; h < n; h++) {
      var cxp = x(h);
      var xa = h === 0 ? ml : (x(h - 1) + cxp) / 2;
      var xb = h === n - 1 ? (W - mr) : (cxp + x(h + 1)) / 2;
      var monthTotal = 0;
      for (var si0 = 0; si0 < series.length; si0++) monthTotal += series[si0].rev[h] || 0;
      var drill = opts.drill ? ' data-drill="month" tabindex="0" role="button" aria-label="' +
        esc(longPeriod(periods[h]) + "、売上合計 " + jpMoney(monthTotal) + "。事業部内訳を表示") + '"' : "";
      var attr = drill + ' data-i="' + h + '" data-x="' + cxp.toFixed(1) + '" data-period="' + esc(periods[h]) + '"';
      series.forEach(function (s, si) {
        attr += ' data-v' + si + '="' + s.rev[h] + '" data-y' + si + '="' + y(s.rev[h]).toFixed(1) + '"';
      });
      svg.push('<rect class="trend-hit" ' + attr + ' x="' + xa.toFixed(1) + '" y="' + mt + '" width="' + (xb - xa).toFixed(1) + '" height="' + ih + '"/>');
    }
    svg.push("</svg>");
    target.host.innerHTML = svg.join("");
    if (target.legend) {
      target.legend.innerHTML = series.map(function (s) {
        return '<span class="lg"><i class="sw" style="background:' + s.color + '"></i>' + esc(shortDept(s.name)) + "</span>";
      }).join("");
    }
    setChartTitle(target.titleEl, opts.title || "事業部別 月次売上トレンド", opts.note || "");
  }

  /* ---------------- drill frame draws (店舗側 / 事業部側) ---------------- */

  // 事業部ドリル: その事業部だけの月次売上トレンド（単一系列）。
  function drawDeptMonthly(f, target) {
    if (!DEPT || !DEPT.monthly) { target.host.innerHTML = emptyChart(); return; }
    var series = (DEPT.monthly.series || []).filter(function (s) { return s.code === f.code; });
    drawDeptTrend(DEPT.monthly, {
      target: target, series: series, drill: true,
      title: f.name + " 月次売上", note: DEPT.fy + "年度・" + DEPT.monthly.periods.length + "ヶ月"
    });
  }

  // 事業部トレンドの月クリック: その月の事業部別内訳（横棒）。
  function drawDeptMonthBreakdown(f) {
    var idx = (DEPT.monthly.periods || []).indexOf(f.period);
    var rows = (DEPT.divisions || []).map(function (d) {
      var s = (DEPT.monthly.series || []).filter(function (x) { return x.code === d.code; })[0];
      return { key: d.code, name: d.name, color: d.color, value: (s && idx >= 0) ? num(s.rev[idx]) : 0 };
    }).filter(function (r) { return r.value > 0; });
    var total = rows.reduce(function (a, r) { return a + r.value; }, 0);
    deptLineSeries = [];
    drawHBars(els.deptTrend, rows, {
      tip: "dept", total: total, valueFmt: jpMoney, drillKind: "dept",
      aria: function (r) { return r.name + " の月次推移を表示"; }
    });
    els.legendDeptTrend.innerHTML = "";
    setChartTitle(els.titleDeptTrend, "事業部別売上", longPeriod(f.period) + "・収益" + rows.length + "事業部");
  }

  // 事業部ドリルの最終表（当月 / 前月 / FY合計）。
  function drawDeptMonthDetail(f, target) {
    var m = buildDeptMonthDetail(DEPT, f.code, f.period);
    setChartTitle(target.titleEl, f.name + " 月次詳細", longPeriod(f.period));
    if (target.legend) target.legend.innerHTML = "";
    if (!m) { target.host.innerHTML = emptyChart(); return; }
    function row(label, period, rev, mom, share, hl) {
      var momTxt = mom == null ? "-" : '<span class="delta ' + (mom >= 0 ? "pos" : "neg") + '">' + esc(fmtSignedPct(mom)) + "</span>";
      return "<tr" + (hl ? ' class="hl"' : "") + ">" +
        '<th scope="row">' + esc(label) + "</th>" +
        '<td class="num">' + esc(period || "") + "</td>" +
        '<td class="num">' + (rev == null ? "-" : esc(jpMoney(rev))) + "</td>" +
        '<td class="num">' + momTxt + "</td>" +
        '<td class="num">' + (share == null ? "-" : fmtPct(share)) + "</td></tr>";
    }
    target.host.innerHTML = '<div class="table-scroll"><table class="dept-table"><thead><tr>' +
      '<th scope="col">区分</th><th scope="col">期間</th><th scope="col">売上</th><th scope="col">前月比</th><th scope="col">年度構成比</th>' +
      "</tr></thead><tbody>" +
      row("当月", longPeriod(m.period), m.rev, m.mom, m.share, true) +
      row("前月", m.prevPeriod ? longPeriod(m.prevPeriod) : "-", m.prevRev, null, m.prevShare, false) +
      row("年度合計", m.fy + "年度", m.fyTotal, null, 100, false) +
      "</tbody></table></div>" +
      '<p class="drill-foot">※ ' + esc(m.fy + "年度") + 'の月次売上です。前月比は前月分が年度内のときのみ表示します。</p>';
  }

  // 店舗ドリルの最終表（当月 / 前月 / 前年同月）。月次の内訳はトレンド用スナップショットを使う。
  function drawMonthDetail(f, target) {
    target = target || cardTarget("trend");
    var m = buildMonthDetail(TREND, f.storeId, f.period);
    setChartTitle(target.titleEl, f.storeName + " 月次詳細", longPeriod(f.period));
    if (target.legend) target.legend.innerHTML = "";
    if (!m) { target.host.innerHTML = emptyChart(); return; }
    function metricRow(label, cur, prev, yoy, momPct, yoyPct, isPct) {
      function cell(v, pct) {
        if (v == null) return '<td class="num">-</td>';
        var txt = esc(isPct ? fmtPct(v) : jpMoney(v));
        if (pct != null) txt += ' <span class="delta ' + (pct >= 0 ? "pos" : "neg") + '">(' + esc(fmtSignedPct(pct)) + ")</span>";
        return '<td class="num">' + txt + "</td>";
      }
      return '<tr><th scope="row">' + esc(label) + "</th>" + cell(cur) + cell(prev, momPct) + cell(yoy, yoyPct) + "</tr>";
    }
    var range = trendRange(f.storeId);
    target.host.innerHTML = '<div class="table-scroll"><table class="dept-table"><thead><tr>' +
      '<th scope="col">指標</th>' +
      '<th scope="col">' + esc(longPeriod(m.period)) + "</th>" +
      '<th scope="col">' + (m.prevPeriod ? "前月 " + esc(longPeriod(m.prevPeriod)) : "前月") + "</th>" +
      '<th scope="col">' + (m.yoyPeriod ? "前年同月 " + esc(longPeriod(m.yoyPeriod)) : "前年同月") + "</th>" +
      "</tr></thead><tbody>" +
      metricRow("売上", m.sales.cur, m.sales.prev, m.sales.yoy, m.sales.momPct, m.sales.yoyPct, false) +
      metricRow("純利益", m.profit.cur, m.profit.prev, m.profit.yoy, m.profit.momPct, m.profit.yoyPct, false) +
      metricRow("利益率", m.margin.cur, m.margin.prev, m.margin.yoy, null, null, true) +
      "</tbody></table></div>" +
      '<p class="drill-foot">※ ' +
      (range.from ? esc(longPeriod(range.from) + "〜" + longPeriod(range.to)) + " の月次データより。" : "") +
      "前月比・前年同月比は比較対象月がデータ範囲内のときのみ表示します。</p>";
  }

  // その店舗の月次データが存在する期間レンジ（footnote 用）
  function trendRange(storeId) {
    var rows = TREND, from = "", to = "";
    rows.forEach(function (r) {
      if (r.store_id !== storeId) return;
      if (!from || r.period < from) from = r.period;
      if (!to || r.period > to) to = r.period;
    });
    return { from: from, to: to };
  }

  // 店舗ドリルの最終表: 費用区分ごとの金額・構成比・対売上比。
  function drawStoreCostTable(f) {
    var store = state.byId[f.storeId];
    var model = buildStoreCostTable(store, COST_KEYS);
    setChartTitle(els.titleDonut, f.storeName + " の費用内訳", model ? "総費用 " + jpMoney(model.total) : "");
    if (!model) { els.donut.innerHTML = emptyChart(); return; }
    var rows = model.rows.map(function (r) {
      return "<tr" + (r.key === f.catKey ? ' class="hl"' : "") + ">" +
        '<th scope="row"><span class="dept-swatch" style="background:' + r.color + '"></span>' + esc(r.label) + "</th>" +
        '<td class="num">' + esc(jpMoney(r.amount)) + "</td>" +
        '<td class="num">' + fmtPct(r.share) + "</td>" +
        '<td class="num">' + fmtPct(r.toSales) + "</td></tr>";
    }).join("");
    rows += '<tr class="total"><th scope="row">合計</th><td class="num">' + esc(jpMoney(model.total)) +
      '</td><td class="num">100%</td><td class="num">' + fmtPct(model.sales ? (model.total / model.sales) * 100 : 0) + "</td></tr>";
    els.donut.innerHTML = '<div class="table-scroll"><table class="dept-table"><thead><tr>' +
      '<th scope="col">費用区分</th><th scope="col">金額</th><th scope="col">構成比</th><th scope="col">対売上比</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      '<p class="drill-foot">※ 構成比＝総費用に対する割合、対売上比＝総売上に対する割合。</p>';
  }

  /* ---------------- drill data helpers / models (tests/test_drill_helpers.js が固定) ---------------- */

  function storeRowsForPeriod(period) {
    return buildStorePeriodRows(TREND, period);
  }

  // カテゴリ別 店舗金額ランキング（上位10店舗）。total は全店舗の当該カテゴリ合計（構成比の分母）。
  function categoryStoreRows(catKey) {
    var field = costField(catKey);
    var color = (COST_KEYS.filter(function (c) { return c.key === catKey; })[0] || {}).color || PALETTE.rev;
    var total = 0;
    var rows = state.stores.map(function (s) {
      var v = num(s[field]);
      total += v;
      return { storeId: s.id, name: s.name, value: v, color: color };
    }).filter(function (r) { return r.value > 0; }).sort(function (a, b) { return b.value - a.value; }).slice(0, 10);
    return { rows: rows, total: total };
  }

  function costsOfStore(store) {
    return COST_KEYS.map(function (c) {
      return { label: c.label, color: c.color, value: num(store[costField(c.key)]), key: c.key };
    });
  }

  // "YYYY-MM" の月シフト（純粋関数）
  function shiftPeriod(period, delta) {
    var m = /^(\d{4})-(\d{2})$/.exec(period || "");
    if (!m) return "";
    var total = (+m[1]) * 12 + (+m[2] - 1) + delta;
    var y = Math.floor(total / 12), mo = total % 12;
    return y + "-" + (mo < 10 ? "0" : "") + (mo + 1);
  }

  // 指定月の店舗別 売上/純利益（__TREND__ 行から集計、純利益降順）
  function buildStorePeriodRows(trendRows, period) {
    var by = {};
    (trendRows || []).forEach(function (r) {
      if (!r || r.period !== period) return;
      var s = by[r.store_id] || (by[r.store_id] = { id: r.store_id, name: r.store, rev: 0, profit: 0 });
      s.rev += num(r.rev);
      s.profit += num(r.profit);
    });
    return Object.keys(by).map(function (k) {
      var s = by[k];
      s.margin = s.rev ? (s.profit / s.rev) * 100 : 0;
      return s;
    }).sort(byProfitDesc);
  }

  // 上位 nTop + 下位 nBottom（重複除去して純利益降順）
  function pickTopBottom(rows, nTop, nBottom) {
    var out = rows.slice(0, nTop).concat(rows.slice(-nBottom));
    var seen = {}, res = [];
    out.forEach(function (s) { if (!seen[s.id]) { seen[s.id] = 1; res.push(s); } });
    return res.sort(byProfitDesc);
  }

  function pctChange(cur, base) {
    if (base == null || base === 0) return null;
    return ((cur - base) / Math.abs(base)) * 100;
  }

  // 店舗×月の詳細モデル（当月・前月・前年同月 + 変化率）
  function buildMonthDetail(trendRows, storeId, period) {
    var by = {};
    (trendRows || []).forEach(function (r) { if (r && r.store_id === storeId) by[r.period] = r; });
    var cur = by[period];
    if (!cur) return null;
    var prev = by[shiftPeriod(period, -1)] || null;
    var yoy = by[shiftPeriod(period, -12)] || null;
    function series(key) {
      var c = num(cur[key]);
      var p = prev ? num(prev[key]) : null;
      var y = yoy ? num(yoy[key]) : null;
      return { cur: c, prev: p, yoy: y, momPct: p == null ? null : pctChange(c, p), yoyPct: y == null ? null : pctChange(c, y) };
    }
    var sales = series("rev"), profit = series("profit");
    return {
      period: period,
      prevPeriod: prev ? prev.period : null,
      yoyPeriod: yoy ? yoy.period : null,
      sales: sales, profit: profit,
      margin: {
        cur: sales.cur ? (profit.cur / sales.cur) * 100 : 0,
        prev: sales.prev ? (profit.prev / sales.prev) * 100 : null,
        yoy: sales.yoy ? (profit.yoy / sales.yoy) * 100 : null
      }
    };
  }

  // 店舗の費用内訳モデル（金額・構成比・対売上比）
  function buildStoreCostTable(store, costKeys) {
    if (!store) return null;
    var total = 0;
    var rows = (costKeys || []).map(function (c) {
      var amount = num(store[costField(c.key)]);
      total += amount;
      return { key: c.key, label: c.label, color: c.color, amount: amount };
    });
    rows.forEach(function (r) {
      r.share = total ? (r.amount / total) * 100 : 0;
      r.toSales = store.sales ? (r.amount / store.sales) * 100 : 0;
    });
    return { rows: rows, total: total, sales: num(store.sales) };
  }

  // 事業部×月の詳細モデル（当月・前月・FY合計 + 前月比・FY構成比）
  function buildDeptMonthDetail(dept, code, period) {
    if (!dept || !dept.monthly) return null;
    var periods = dept.monthly.periods || [];
    var idx = periods.indexOf(period);
    if (idx < 0) return null;
    var series = (dept.monthly.series || []).filter(function (s) { return s.code === code; })[0];
    if (!series) return null;
    var div = (dept.divisions || []).filter(function (d) { return d.code === code; })[0] || { name: code, color: "" };
    var rev = num(series.rev[idx]);
    var prevRev = idx > 0 ? num(series.rev[idx - 1]) : null;
    var fyTotal = (series.rev || []).reduce(function (a, v) { return a + num(v); }, 0);
    return {
      code: code, name: div.name, color: div.color, period: period,
      prevPeriod: idx > 0 ? periods[idx - 1] : null,
      rev: rev, prevRev: prevRev,
      mom: prevRev == null ? null : pctChange(rev, prevRev),
      share: fyTotal ? (rev / fyTotal) * 100 : 0,
      prevShare: (fyTotal && prevRev != null) ? (prevRev / fyTotal) * 100 : null,
      fyTotal: fyTotal, fy: dept.fy
    };
  }

  // 予算達成状況テーブル（粗利ベース）。予算差異＝実績−予算、達成率＝実績粗利/予算粗利。
  function renderBudgetTable(divs) {
    var tr = sum(divs, "rev"), tc = sum(divs, "cogs"), tg = sum(divs, "gross"), tv = sum(divs, "variance");
    var tb = tg - tv, tach = tb ? tg / tb * 100 : 100;
    var rows = divs.map(function (d) {
      var gm = d.rev ? d.gross / d.rev * 100 : 0;
      return budgetRow(false, d.name, d.color, d.rev, d.cogs, d.gross, gm, d.variance, d.achieve);
    }).join("");
    rows += budgetRow(true, "合計", null, tr, tc, tg, (tr ? tg / tr * 100 : 0), tv, Math.round(tach * 10) / 10);
    els.deptTable.innerHTML =
      '<table class="dept-table"><thead><tr>' +
      '<th scope="col">事業部</th><th scope="col">売上</th><th scope="col">売上原価</th><th scope="col">粗利益</th><th scope="col">粗利率</th><th scope="col">予算差異</th><th scope="col">達成率</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table>";
  }

  function budgetRow(isTotal, name, color, rev, cogs, gross, gm, variance, achieve) {
    var sw = color ? '<span class="dept-swatch" style="background:' + color + '"></span>' : "";
    var vCls = variance >= 0 ? "pos" : "neg";
    var vTxt = (variance >= 0 ? "+" : "-") + jpMoney(Math.abs(variance));
    var aCls = achieve >= 100 ? "pos" : "neg";
    return '<tr' + (isTotal ? ' class="total"' : "") + ">" +
      '<th scope="row">' + sw + esc(name) + "</th>" +
      '<td class="num">' + esc(jpMoney(rev)) + "</td>" +
      '<td class="num">' + esc(jpMoney(cogs)) + "</td>" +
      '<td class="num">' + esc(jpMoney(gross)) + "</td>" +
      '<td class="num">' + fmtPct(gm) + "</td>" +
      '<td class="num ' + vCls + '">' + esc(vTxt) + "</td>" +
      '<td class="num ' + aCls + '">' + fmtPct(achieve) + "</td></tr>";
  }

  /* ---------------- svg helpers ---------------- */

  // SVG をコンテナ実寸で描くための幅（viewBox 幅＝CSS px なので文字・線が縮小されない）。
  // clientWidth が取れない環境（DOM スタブ等）は 760 にフォールバックする。
  function chartWidth(host, fallback) {
    var w = (host && host.clientWidth) || 0;
    return w > 0 ? w : (fallback || 760);
  }

  function line(x1, y1, x2, y2, cls) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" class="' + cls + '"/>';
  }
  function text(x, y, s, cls) { return '<text x="' + x + '" y="' + y + '" class="' + cls + '">' + esc(s) + "</text>"; }
  function dot(x, y, cls) { return '<circle cx="' + x + '" cy="' + y + '" r="3.5" class="' + cls + '"/>'; }
  function emptyChart() { return '<div class="chart-empty">データがありません</div>'; }

  function donutArc(cx, cy, r, rin, a1, a2, color, attrs) {
    var large = (a2 - a1) > Math.PI ? 1 : 0;
    var x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    var x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    var xi2 = cx + rin * Math.cos(a2), yi2 = cy + rin * Math.sin(a2);
    var xi1 = cx + rin * Math.cos(a1), yi1 = cy + rin * Math.sin(a1);
    return '<path d="M' + x1 + " " + y1 +
      " A" + r + " " + r + " 0 " + large + " 1 " + x2 + " " + y2 +
      " L" + xi2 + " " + yi2 +
      " A" + rin + " " + rin + " 0 " + large + " 0 " + xi1 + " " + yi1 +
      ' Z" fill="' + color + '" class="donut-slice" ' + (attrs || "") + '/>';
  }

  /* ---------------- formatting ---------------- */

  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function sum(arr, k) { return arr.reduce(function (a, x) { return a + (x[k] || 0); }, 0); }
  function byProfitDesc(a, b) { return b.profit - a.profit; }

  function jpMoney(n) {
    var a = Math.abs(n), sign = n < 0 ? "-" : "";
    if (a >= 1e8) return sign + trimZero((a / 1e8).toFixed(2)) + "億円";
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString() + "万円";
    return sign + Math.round(a).toLocaleString() + "円";
  }
  function jpCompact(n) {
    var a = Math.abs(n), sign = n < 0 ? "-" : "";
    if (a >= 1e8) return sign + trimZero((a / 1e8).toFixed(1)) + "億";
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString() + "万";
    return sign + Math.round(a).toLocaleString();
  }
  function trimZero(s) { return s.replace(/\.?0+$/, ""); }
  function fmtPct(n) { return (Math.round(n * 10) / 10) + "%"; }
  function fmtSignedPct(n) { return (n >= 0 ? "+" : "") + (Math.round(n * 10) / 10) + "%"; }
  function shortPeriod(p) { var m = /^(\d{4})-(\d{2})$/.exec(p || ""); return m ? m[1].slice(2) + "/" + m[2] : (p || ""); }
  function longPeriod(p) { var m = /^(\d{4})-(\d{2})$/.exec(p || ""); return m ? m[1] + "年" + (+m[2]) + "月" : (p || ""); }
  function trunc(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function shortDept(name) { return String(name || "").replace(/事業部$/, ""); }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function sanitizeReportHtml(s) {
    if (typeof s !== "string" || s.length > 200000) throw new Error("レポート本文の形式またはサイズが不正です。");
    var template = document.createElement("template");
    template.innerHTML = s;
    if (!template.content.children.length && /<[a-z][\s\S]*>/i.test(template.content.textContent)) {
      template.innerHTML = template.content.textContent;
    }
    var allowed = new Set("h1 h2 h3 h4 h5 h6 p div span section article header footer table thead tbody tfoot tr th td caption colgroup col ul ol li b strong em i u s small blockquote pre code hr br a details summary".split(" "));
    var blocked = new Set("script style iframe object embed link meta base svg math template img video audio form input button textarea select option noscript".split(" "));
    var attributes = new Set(["class", "title", "colspan", "rowspan", "scope", "aria-label"]);
    var removed = 0;
    Array.from(template.content.querySelectorAll("*")).forEach(function (element) {
      var tag = element.localName;
      if (blocked.has(tag)) { element.remove(); removed++; return; }
      if (!allowed.has(tag)) {
        element.replaceWith.apply(element, Array.from(element.childNodes));
        removed++;
        return;
      }
      Array.from(element.attributes).forEach(function (attribute) {
        if (!attributes.has(attribute.name) || ((attribute.name === "colspan" || attribute.name === "rowspan") && !/^\d{1,3}$/.test(attribute.value))) {
          element.removeAttribute(attribute.name); removed++;
        }
      });
    });
    if (!template.content.textContent.trim()) throw new Error("安全に表示できるレポート本文がありません。");
    if (removed) console.warn("Unsafe report markup removed", {count: removed});
    return template.innerHTML;
  }

  function showMessage(m, retry) {
    els.message.textContent = "";
    var p = document.createElement("p");
    p.className = "message-text";
    p.textContent = m;
    els.message.appendChild(p);
    if (retry) {   // 行き止まりにしない: 取得失敗には再読み込み導線を添える（PL-010）
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "retry-button";
      btn.textContent = "再読み込み";
      btn.addEventListener("click", function () { window.location.reload(); });
      els.message.appendChild(btn);
    }
    els.message.style.display = "block";
  }
  function hideMessage() { els.message.style.display = "none"; els.message.textContent = ""; }
})();
