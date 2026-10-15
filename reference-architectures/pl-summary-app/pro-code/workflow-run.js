(function () {
  "use strict";
  var state = {requesting: false, running: false, unknown: false, instanceId: "", beganAt: "", progressPath: "", timer: null, pending: null};
  var els = {}, storageKey = "pl-workflow-run";

  function call(operation, request) {
    var timer;
    var timeout = new Promise(function (_, reject) {
      timer = setTimeout(function () { reject(new Error("通信がタイムアウトしました。実行状況を確認してください。")); }, 20000);
    });
    var posted = Promise.resolve().then(function () { return domo.post("/domo/codeengine/v2/packages/plReportApi", {operation: operation, request: request || {}}); });
    return Promise.race([posted, timeout])
      .then(function (response) {
        var result = response && response.result !== undefined ? response.result : response;
        if (typeof result === "string") result = JSON.parse(result);
        if (!result || result.ok !== true) {
          var error = new Error(result && result.error && result.error.message || "Workflowの処理に失敗しました。");
          error.code = result && result.error && result.error.code;
          throw error;
        }
        return result;
      }).finally(function () { clearTimeout(timer); });
  }

  function saveState() {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({instanceId: state.instanceId, unknown: state.unknown, beganAt: state.beganAt}));
    } catch (error) {
      renderStatus(els.status.textContent + " 実行状態を端末に保持できません。再読込後は実行状況を確認してください。", true);
    }
  }

  function renderStatus(message, error) {
    els.status.textContent = message;
    els.status.classList.toggle("workflow-error", error === true);
    els.run.disabled = state.requesting || state.running || state.unknown;
    els.run.textContent = state.running ? "更新中…" : state.unknown ? "開始結果を確認中" : "AIレポートを更新";
    els.run.setAttribute("aria-busy", String(state.requesting || state.running));
    els.check.disabled = !state.progressPath;
  }

  function stopPoll() { clearTimeout(state.timer); state.timer = null; }

  function schedulePoll() {
    stopPoll();
    if ((state.running || state.unknown) && !document.hidden) state.timer = setTimeout(checkStatus, 30000);
  }

  function acceptStatus(result) {
    var wasRunning = state.running;
    state.instanceId = result.instance_id || state.instanceId;
    state.running = result.running === true;
    if (/^\/workflows\/instances\/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\/$/i.test(result.progress_path || "")) state.progressPath = result.progress_path;
    if (state.running || (result.created_on && result.created_on >= state.beganAt)) state.unknown = false;
    if (state.unknown) {
      renderStatus("開始結果はまだ未確認です。再実行せず、実行状況を別タブで確認してください。", true);
    } else if (state.running) {
      renderStatus("全店舗・全社のAIレポートを更新中です。現在のレポートは引き続き閲覧できます。");
    } else if (result.status === "COMPLETED") {
      renderStatus("メインWorkflowは完了しました。個別のAIレポートは順次反映されます。");
      if (wasRunning) window.dispatchEvent(new Event("pl-workflow-completed"));
    } else if (result.status === "IDLE") {
      renderStatus("全店舗・全社の長文AIレポートを手動で更新します。");
    } else {
      renderStatus("前回の実行状態: " + result.status + "。詳細は実行状況を別タブで確認してください。", true);
    }
    saveState();
    schedulePoll();
  }

  function checkStatus() {
    if (state.requesting) return Promise.resolve();
    state.requesting = true;
    return call("status", state.instanceId ? {instance_id: state.instanceId} : {})
      .then(function (result) {
        state.requesting = false;
        acceptStatus(result);
      }).catch(function (error) {
        state.requesting = false;
        renderStatus("実行状況を取得できませんでした: " + error.message, true);
        els.run.disabled = true;
        schedulePoll();
      });
  }

  function startWorkflow() {
    if (state.requesting || state.running || state.unknown) return;
    state.requesting = true;
    state.beganAt = new Date().toISOString();
    state.instanceId = "";
    renderStatus("メインWorkflowを開始しています…");
    return call("start", {}).then(function (result) {
      state.requesting = false;
      state.unknown = false;
      acceptStatus(result);
    }).catch(function (error) {
      state.requesting = false;
      state.unknown = error.code === "START_UNCONFIRMED" || !error.code;
      renderStatus(error.message, true);
      saveState();
      schedulePoll();
    });
  }

  function closeConfirmation() {
    if (state.pending) state.pending.action = null;
    if (els.dialog && els.dialog.open) els.dialog.close("cancel");
    finishConfirmation();
  }

  function finishConfirmation() {
    if (!state.pending || els.dialog.open) return;
    var pending = state.pending;
    state.pending = null;
    document.body.style.overflow = pending.overflow;
    if (pending.origin && pending.origin.isConnected) pending.origin.focus({preventScroll: true});
    if (pending.action && els.dialog.returnValue === "default") pending.action();
  }

  function confirmRun() {
    if (state.requesting || state.running || state.unknown) return;
    if (state.pending) { els.cancel.focus(); return; }
    if (!els.dialog || !els.cancel || !els.yes || typeof els.dialog.showModal !== "function") {
      renderStatus("確認画面を表示できません。画面を再読み込みしてください。", true);
      return;
    }
    state.pending = {action: startWorkflow, origin: els.run, overflow: document.body.style.overflow};
    els.dialog.returnValue = "";
    try {
      els.dialog.showModal();
      document.body.style.overflow = "hidden";
      els.cancel.focus({preventScroll: true});
    } catch (error) {
      closeConfirmation();
      renderStatus("確認画面を表示できません: " + error.message, true);
    }
  }

  function init() {
    els.run = document.getElementById("workflow-run");
    els.check = document.getElementById("workflow-check");
    els.status = document.getElementById("workflow-status");
    els.dialog = document.getElementById("workflow-confirm");
    els.cancel = document.getElementById("workflow-cancel");
    els.yes = document.getElementById("workflow-confirm-yes");
    try {
      var saved = JSON.parse(sessionStorage.getItem(storageKey) || "{}");
      state.instanceId = saved.instanceId || "";
      state.unknown = saved.unknown === true;
      state.beganAt = saved.beganAt || "";
    } catch (error) {
      renderStatus("端末の実行状態を読み込めません。実行状況を確認してください。", true);
    }
    els.run.addEventListener("click", confirmRun);
    els.check.addEventListener("click", function () {
      if (!state.progressPath || typeof domo.navigate !== "function") {
        renderStatus("実行状況の画面を開けません。Domo SDKとWorkflowの配線を確認してください。", true);
        return;
      }
      domo.navigate(state.progressPath, true);
    });
    if (els.dialog) {
      els.dialog.addEventListener("close", finishConfirmation);
      els.dialog.addEventListener("cancel", function (event) { event.preventDefault(); closeConfirmation(); });
      els.dialog.addEventListener("click", function (event) {
        if (event.target !== els.dialog) return;
        var rect = els.dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeConfirmation();
      });
      els.dialog.addEventListener("keydown", function (event) {
        if (event.key !== "Tab") return;
        var buttons = Array.from(els.dialog.querySelectorAll("button"));
        var first = buttons[0], last = buttons[buttons.length - 1];
        if ((!event.shiftKey && document.activeElement === last) || (event.shiftKey && document.activeElement === first)) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        }
      });
    }
    window.addEventListener("pagehide", function () { closeConfirmation(); stopPoll(); });
    document.addEventListener("visibilitychange", function () {
      stopPoll();
      if (!document.hidden && !state.requesting) {
        if (state.unknown) state.instanceId = "";
        checkStatus();
      }
    });
    checkStatus();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
