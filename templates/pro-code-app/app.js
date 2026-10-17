// app.js — Pro Code Starter
//
// Reads from the dataset bound as alias "mainDs" in manifest.json.
// Replace the dataSetId in manifest.json, then have your AI agent
// build the actual workflow on top of this skeleton.

const ALIAS = 'mainDs';
const PREVIEW_SQL = 'SELECT * FROM table LIMIT 50';

// 実際の Domo ランタイム上か判定する。ryuu.js は CDN から読めると domo / domo.env 自体は
// 定義される（env は中身が空のオブジェクト）ため、`typeof domo` や `!domo.env` だけでは
// ローカル（file:// / ブラウザ直開き）と区別できない。実アプリでは domo.env.customer
// （インスタンス名）が入るので、それを「本物のランタイムか」の信号に使う。
function inDomoRuntime() {
  return typeof domo !== 'undefined' && !!domo.env && !!domo.env.customer;
}

document.addEventListener('DOMContentLoaded', () => {
  initEnvDisplay();
  wireButtons();
  loadPreview();
});

// ============================================================
// 1. Show who's signed in (domo.env) — works on every Custom App
// ============================================================

function initEnvDisplay() {
  if (!inDomoRuntime()) {
    // Running outside a real Domo runtime (file:// / browser preview) — label it clearly.
    document.getElementById('userName').textContent = 'Local';
    document.getElementById('instanceName').textContent = 'preview';
    return;
  }
  document.getElementById('userName').textContent = domo.env.userName || '—';
  document.getElementById('instanceName').textContent = domo.env.customer || '—';
}

// ============================================================
// 2. Load a preview of the bound dataset
// ============================================================

async function loadPreview() {
  setEmptyState('Loading dataset preview...');

  // ローカル（file:// やブラウザ直開き）では Domo セッションが無く SQL を取得できない。赤いエラー
  // ではなく「未接続」状態を見せ、レイアウト／デザインシステムが正しく描画されることを示す。
  if (!inDomoRuntime()) {
    setEmptyState(
      `<strong>ローカルプレビュー（未接続）</strong>
       レイアウトとデザインシステムはこのとおり描画されます。実データは Domo に公開して
       データセットを割り当てると表示されます。`
    );
    return;
  }

  try {
    // Try mapped-alias SQL first (preferred — uses manifest binding).
    const result = await domo.post(`/sql/v1/${ALIAS}`, PREVIEW_SQL, { contentType: 'text/plain' });
    renderTable(result);
    updateStats(result);
  } catch (err) {
    console.error('Failed to load preview:', err);
    setEmptyState(
      `<strong>Could not load dataset</strong>
       Check that <code>manifest.json</code> has a real <code>dataSetId</code>
       under <code>datasetsMapping[0]</code>, and that the app has been published
       and assigned that dataset.`
    );
  }
}

// ============================================================
// 3. Render rows into the table
// ============================================================

function renderTable(result) {
  const { columns = [], rows = [] } = result || {};
  const thead = document.querySelector('#dataTable thead');
  const tbody = document.querySelector('#dataTable tbody');

  if (!columns.length) {
    setEmptyState('Dataset returned no columns.');
    return;
  }

  // Reset
  thead.innerHTML = '';
  tbody.innerHTML = '';

  // Header
  const headerRow = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  // Body
  rows.forEach(row => {
    const tr = document.createElement('tr');
    row.forEach(cell => {
      const td = document.createElement('td');
      td.textContent = cell == null ? '' : String(cell);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ============================================================
// 4. Update stats bar from result metadata
// ============================================================

function updateStats(result) {
  const { columns = [], rows = [] } = result || {};
  document.getElementById('rowCount').textContent = rows.length.toLocaleString();
  document.getElementById('columnCount').textContent = columns.length.toLocaleString();
}

// ============================================================
// 5. Buttons
// ============================================================

function wireButtons() {
  document.getElementById('refreshBtn').addEventListener('click', loadPreview);

  document.getElementById('runSqlBtn').addEventListener('click', async () => {
    // SQL は card 内のインライン <textarea> から読む（window.prompt は iframe サンドボックスで
    // 無反応になりうるうえ、キーボード/スクリーンリーダー非対応でデザインシステムから外れる）。
    const input = document.getElementById('sqlInput');
    const errBox = document.getElementById('sqlError');
    const sql = (input.value || '').trim();
    errBox.hidden = true;
    errBox.textContent = '';
    if (!sql) {
      errBox.textContent = 'SQL を入力してください。';
      errBox.hidden = false;
      input.focus();
      return;
    }
    if (!inDomoRuntime()) {
      errBox.textContent = 'ローカルでは実行できません。Domo に公開してから実行してください。';
      errBox.hidden = false;
      return;
    }
    setEmptyState('Running query...');
    try {
      const result = await domo.post(`/sql/v1/${ALIAS}`, sql, { contentType: 'text/plain' });
      renderTable(result);
      updateStats(result);
    } catch (err) {
      console.error('Query failed:', err);
      // err.message は失敗した SQL（textarea のユーザー入力）やサーバのエラー文を反映しうる
      // 動的値。innerHTML へ入れる前に必ず escapeHtml() を通す（上の invariant）。
      setEmptyState(`<strong>Query failed</strong>${escapeHtml(err.message || String(err))}`);
    }
  });
}

// ============================================================
// 6. Empty-state helper
// ============================================================

// Escape the 5 HTML-significant characters before putting any *dynamic* value
// (dataset content, server/error text, user input) into innerHTML. Mirrors the
// untrusted-DOM-XSS rule in skills/domo-procode-app.md — keep this when you
// build on the skeleton so apps scaffolded from it inherit the safe pattern.
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// setEmptyState writes to innerHTML, so it takes STATIC/trusted markup (e.g. the
// <strong>/<code> hints in loadPreview). Any dynamic value must go through
// escapeHtml() first — see the "Query failed" call site in wireButtons().
function setEmptyState(html) {
  const tbody = document.querySelector('#dataTable tbody');
  const thead = document.querySelector('#dataTable thead');
  thead.innerHTML = '';
  tbody.innerHTML = `<tr><td><div class="empty-state">${html}</div></td></tr>`;
}
