// app.js — Pro Code Starter
//
// Reads from the dataset bound as alias "mainDs" in manifest.json.
// Replace the dataSetId in manifest.json, then have your AI agent
// build the actual workflow on top of this skeleton.

const ALIAS = 'mainDs';
const PREVIEW_SQL = 'SELECT * FROM table LIMIT 50';

document.addEventListener('DOMContentLoaded', () => {
  initEnvDisplay();
  wireButtons();
  loadPreview();
});

// ============================================================
// 1. Show who's signed in (domo.env) — works on every Custom App
// ============================================================

function initEnvDisplay() {
  if (typeof domo === 'undefined' || !domo.env) {
    // Running outside Domo (e.g., file://) — show placeholder text.
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
    const sql = window.prompt(
      'Enter SQL to run against this dataset (table name is always "table"):',
      PREVIEW_SQL
    );
    if (!sql) return;
    setEmptyState('Running query...');
    try {
      const result = await domo.post(`/sql/v1/${ALIAS}`, sql, { contentType: 'text/plain' });
      renderTable(result);
      updateStats(result);
    } catch (err) {
      console.error('Query failed:', err);
      // err.message は失敗した SQL（window.prompt のユーザー入力）やサーバのエラー文を
      // 反映しうる動的値。innerHTML へ入れる前に必ず escapeHtml() を通す（上の invariant）。
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
