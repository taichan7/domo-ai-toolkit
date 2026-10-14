/*
 * 在庫入出庫管理｜開発ガイド — クライアントロジック（縦スクロール1ページの技術文書）
 *
 * この資料は「上から下へ読み進める」静的なスクロール文書。データ取得も集計も行わないので
 * Domo API には依存しない（＝ Domo 上でもローカルプレビュー file:// でも同じく動く）。
 * 役割は次に限定する:
 *   1) セクションの出現アニメと、上部バーのランニングヘッダ（現在の §N）
 *   2) コマンド/コード片のクリップボードコピー（[data-copy]）
 *   3) アクセシビリティの一括補正（装飾アイコンを隠す・リストへ role 付与・はみ出し枠を
 *      キーボードで辿れるよう昇格・コピーボタンへ文脈付き aria-label を与える）
 *
 * 目次アンカーは素の href="#id"（JS 無しでも遷移する）。スクロールの平滑化は CSS
 * （html{ scroll-behavior: smooth }）が担い、JS では行わない。
 * 進行の操作系（前へ/次へ/ドット送り/拡大縮小）は持たない。ブラウザ本来の縦スクロールに委ねる。
 * 番号（§N・§N.M・図N・表N）の正準は CSS カウンタ。JS が扱うのは上部バー（ランニングヘッダ）の
 * 見かけの通し番号のみで、本文の番号は一切振らない。
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // コピー失敗時の文言（複数箇所から参照する単一情報源）。
  var COPY_FAIL = "コピーできませんでした。手動で選択してください";

  /* ── トースト（コピー等の成功フィードバックを短時間表示） ───────────────── */
  var toastTimer = null;
  function toast(message) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("is-visible");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("is-visible"); }, 1800);
  }

  /*
   * 文字列をクリップボードへコピーする。
   * なぜ2段構えか: Domo の iframe や古い環境では navigator.clipboard が使えないことがあるため、
   *   execCommand('copy') にフォールバックして確実にコピーさせる。
   */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; })
        .catch(function () { return fallbackCopy(text); });
    }
    return Promise.resolve(fallbackCopy(text));
  }
  function fallbackCopy(text) {
    // 全体を try/catch で包み、DOM 操作（appendChild/select/removeChild）が失敗しても false を返す
    // ＝ copyText は常に真偽値へ解決し、reject 経路を持たない（呼び出し側の .catch 不要）。
    var ta = null;
    try {
      ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      if (ta && ta.parentNode) { try { ta.parentNode.removeChild(ta); } catch (e2) {} }
      return false;
    }
  }

  /* ── セクション出現アニメ・ランニングヘッダ ─────────────────
   * 出現アニメ（.is-in）と現在地判定を IntersectionObserver で一括処理する。
   * 現在地が変わったら、上部バーのランニングヘッダへ「§N タイトル」を書き込む
   * （論文の柱記号のように、長い文書のどこを読んでいるかを常に示す）。 */
  var sections = Array.prototype.slice.call(document.querySelectorAll(".sec"));
  var runningHead = document.getElementById("runningHead");

  // 出現アニメを有効化（JS がある時だけ。無ければ CSS 側で常に表示）。
  if (!reduceMotion) document.documentElement.classList.add("reveal");

  /** ランニングヘッダへ「§N タイトル」を反映する。 */
  function setActive(index) {
    if (runningHead && index >= 0 && sections[index]) {
      var title = sections[index].getAttribute("data-title") || "";
      // §番号は CSS カウンタが正なので、ここでは 1 始まりの見かけの通し番号を添えるに留める。
      runningHead.textContent = title ? ("§" + (index + 1) + "　" + title) : "";
    }
  }

  if ("IntersectionObserver" in window) {
    // 出現：一度画面に入ったら .is-in を付けて留める（戻しては明滅するので付けっぱなし）。
    var revealObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-in"); revealObs.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -12% 0px", threshold: 0.08 });
    sections.forEach(function (s) { revealObs.observe(s); });

    // 現在地：ビューポート中央に最も近いセクションを active にする。
    // 1 回のコールバックで複数の節が中央帯に入ることがある（短い節・高速スクロールで
    // エントリがまとまる）。forEach で最後が勝つと中央から遠い節を選びうるため、
    // 交差中エントリのうち矩形中心がビューポート中央に最も近いものを採る。
    var activeObs = new IntersectionObserver(function (entries) {
      var mid = window.innerHeight / 2;
      var best = null, bestDist = Infinity;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var r = e.boundingClientRect;
        var dist = Math.abs((r.top + r.bottom) / 2 - mid);
        if (dist < bestDist) { bestDist = dist; best = e.target; }
      });
      if (best) setActive(sections.indexOf(best));
    }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });
    sections.forEach(function (s) { activeObs.observe(s); });
  } else {
    // 非対応環境では全セクションを可視にしておく（内容が消えない安全側）。
    sections.forEach(function (s) { s.classList.add("is-in"); });
  }

  /* ── a11y の一括補正 ───────────────────────────────────── */
  // 装飾アイコン（本文と意味が重複する線画）は支援技術から隠す。
  Array.prototype.slice.call(document.querySelectorAll(".ic")).forEach(function (icon) {
    icon.setAttribute("aria-hidden", "true");
    icon.setAttribute("focusable", "false");
  });
  // list-style:none を当てたリストは、Safari+VoiceOver で意味論が消えるため role を明示する。
  Array.prototype.slice.call(document.querySelectorAll(".toc__list, .readme__list, ol.proc, .vs__list, .steps"))
    .forEach(function (list) { if (list.tagName === "OL" || list.tagName === "UL") list.setAttribute("role", "list"); });
  // 横スクロールが実際に必要なときだけ、キーボードで辿れるようにフォーカス可能にする
  // （全部に付けると見分けのつかないフォーカス停止点が大量発生する）。名前は近くの見出しから。
  function makeScrollable(el, fallbackLabel) {
    if (el.scrollWidth <= el.clientWidth + 2) {
      // フォーカス中の要素から tabindex を抜くと、操作中にタブ順から外れてフォーカスを失う。
      // フォーカスを保持している間は掃除を見送る（次の再評価で外れていれば片付く）。
      if (el !== document.activeElement) {
        el.removeAttribute("tabindex"); el.removeAttribute("role"); el.removeAttribute("aria-label");
      }
      return;
    }
    var bar = el.closest(".cmd") ? el.closest(".cmd").querySelector(".cmd__bar span") : null;
    var cap = el.closest("figure") ? el.closest("figure").querySelector("figcaption") : null;
    var label = (bar || cap) ? (bar || cap).textContent.replace(/\s+/g, " ").trim().slice(0, 40) : fallbackLabel;
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "region");
    el.setAttribute("aria-label", label + "（左右キーでスクロール）");
  }
  function applyScrollable() {
    Array.prototype.slice.call(document.querySelectorAll(".cmd__body")).forEach(function (pre) {
      makeScrollable(pre, "コマンド");
    });
    Array.prototype.slice.call(document.querySelectorAll(".tablewrap")).forEach(function (wrap) {
      makeScrollable(wrap, "表");
    });
  }
  applyScrollable();
  // フォント読込（display=swap）や幅変更で折返しが変わると要否も変わるため再評価する。
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(applyScrollable);
  var scrollableTimer = 0;
  window.addEventListener("resize", function () {
    clearTimeout(scrollableTimer);
    scrollableTimer = setTimeout(applyScrollable, 150);
  });
  // 15 の面カードはリストとして読み上げ可能にする。
  // 直接の子を無条件に listitem にすると、将来 .surface 以外の子が入ったとき誤ラベルになるので、
  // :scope 直下の .surface だけを対象にする。
  Array.prototype.slice.call(document.querySelectorAll(".surfaces")).forEach(function (grid) {
    grid.setAttribute("role", "list");
    Array.prototype.slice.call(grid.querySelectorAll(":scope > .surface")).forEach(function (card) { card.setAttribute("role", "listitem"); });
  });

  // 入場アニメが内容を隠したままにしない安全網：一定時間後は必ず終端（表示）へ寄せる。
  // スクロールが起きない・IO が発火しない・描画キャプチャ等でも、本文が消えたままにならない。
  window.setTimeout(function () {
    sections.forEach(function (s) { s.classList.add("is-in"); });
  }, 2000);

  /** 近接の見出し（小見出し §N.M → 無ければ節見出し）のテキスト。重複しがちな要素名を一意化する文脈に使う。 */
  function nearestHeading(el) {
    var block = el.closest(".cmd, figure, .try, section") || el;
    var p = block.previousElementSibling;
    while (p) {
      if (p.matches && p.matches("h3.sub, h2.sec__title")) return p.textContent.replace(/\s+/g, " ").trim();
      p = p.previousElementSibling;
    }
    var sec = el.closest(".sec");
    var title = sec && sec.querySelector(".sec__title");
    return title ? title.textContent.replace(/\s+/g, " ").trim() : "";
  }

  /* ── コピーボタン（[data-copy="対象要素のid"]）─────────────────────────
   * 参照先要素（コマンド/コード片）の textContent をそのままコピーする。
   * 単一情報源: 画面に見えているテキストがコピー内容と必ず一致する（別途文字列を持たない）。 */
  var copyButtons = Array.prototype.slice.call(document.querySelectorAll("[data-copy]"));
  // バー文言（例「ターミナル」）は複数バーで重複しうる。SR のボタン一覧で区別できるよう、
  // 重複する文言には近接の見出しを添えて一意化する（WCAG 2.4.6 / 4.1.2）。
  var barCount = Object.create(null);  // prototype キー（toString 等）とバー文言の衝突を避ける
  copyButtons.forEach(function (btn) {
    var bar0 = btn.closest(".cmd__bar");
    var t0 = bar0 && bar0.querySelector("span") ? bar0.querySelector("span").textContent.replace(/\s+/g, " ").trim() : "";
    if (t0) barCount[t0] = (barCount[t0] || 0) + 1;
  });
  copyButtons.forEach(function (btn) {
    var bar = btn.closest(".cmd__bar");
    var text = bar && bar.querySelector("span") ? bar.querySelector("span").textContent.replace(/\s+/g, " ").trim() : "";
    var name = text;
    if (text && barCount[text] > 1) {
      var ctx = nearestHeading(btn);
      if (ctx) name = text + "（" + ctx + "）";
    }
    var baseLabel = name ? name + " をコピー" : "コピー";
    btn.setAttribute("aria-label", baseLabel);
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target) { toast("コピー対象が見つかりません"); return; }
      // copyText は常に真偽値へ解決する（writeText 失敗時も fallbackCopy へ落ちる）ので reject 経路は無い。
      copyText(target.textContent).then(function (ok) {
        if (ok) { flash(btn, baseLabel); toast("コピーしました"); }
        else { toast(COPY_FAIL); }
      });
    });
  });

  /** ボタンを一瞬ハイライトして「押した」を伝える。
   *  初回に表示ラベルを dataset.origLabel へ退避し、復帰時はそれを戻す（固定リテラルに依存せず、
   *  index.html 側の文言変更にも追従する／再クリックでも元の文言を失わない）。
   *  タイマー id は使い終えたら dataset から消す（期限切れの id を残さない）。 */
  function flash(btn, baseLabel) {
    if (btn.dataset.flashTimer) clearTimeout(Number(btn.dataset.flashTimer));
    if (btn.dataset.origLabel == null) btn.dataset.origLabel = btn.textContent;
    btn.classList.add("is-copied");
    btn.textContent = "✓ コピー済み";
    btn.setAttribute("aria-label", "コピー済み");
    btn.dataset.flashTimer = String(setTimeout(function () {
      btn.classList.remove("is-copied");
      btn.textContent = btn.dataset.origLabel;
      btn.setAttribute("aria-label", baseLabel || "コピー");
      delete btn.dataset.flashTimer;
    }, 1400));
  }

  /* ── 初期化 ────────────────────────────────────────────── */
  // 初期はランニングヘッダを空のまま（最初の .sec が交差した時点で埋まる）。
  // 読み込み直後に §1 を表示すると「まだ本文に居ないのに現在地が出る」ため。
})();
