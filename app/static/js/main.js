/* ── Theme toggle (Light/Dark mode) ── */
function initThemeToggle() {
  const toggle = document.getElementById('themeToggle');
  const html = document.documentElement;
  // Por defecto: light mode (claro). Se puede cambiar a dark con el botón
  const savedTheme = localStorage.getItem('theme') || 'light';

  function applyTheme(theme) {
    if (theme === 'dark') {
      html.classList.add('dark-mode');
      html.classList.remove('light-mode');
      toggle.innerHTML = '<i class="bi bi-sun-fill"></i>';
      toggle.title = 'Cambiar a modo claro';
    } else if (theme === 'light') {
      html.classList.remove('dark-mode');
      html.classList.add('light-mode');
      toggle.innerHTML = '<i class="bi bi-moon-fill"></i>';
      toggle.title = 'Cambiar a modo oscuro';
    } else {
      // Auto: detect from system preference
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(isDark ? 'dark' : 'light');
      toggle.innerHTML = isDark ? '<i class="bi bi-sun-fill"></i>' : '<i class="bi bi-moon-fill"></i>';
      toggle.title = isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
    }
  }

  // Asegurar que el tema se aplica inmediatamente
  applyTheme(savedTheme);

  if (toggle) {
    toggle.addEventListener('click', () => {
      const isDark = html.classList.contains('dark-mode');
      const newTheme = isDark ? 'light' : 'dark';
      applyTheme(newTheme);
      localStorage.setItem('theme', newTheme);
    });
  }

  // Listen to system preference changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (localStorage.getItem('theme') === 'auto' || !localStorage.getItem('theme')) {
      applyTheme(e.matches ? 'dark' : 'light');
    }
  });
}

/* ── Sidebar toggle ── */
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const mc = document.getElementById('main-content');
  sb.classList.toggle('collapsed');
  mc.classList.toggle('expanded');
}

// Initialize theme toggle on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
  initThemeToggle();
}

/* ── Copy to clipboard function ── */
function copyToClipboard(text, label = 'ID') {
  navigator.clipboard.writeText(text).then(() => {
    toast(`${label} copiado: ${text}`, 'success');
  }).catch(() => {
    toast(`Error al copiar ${label.toLowerCase()}`, 'danger');
  });
}

/* ── Global search with optimized debounce ── */
let _gsearchTimeout;
async function onGlobalSearch(q) {
  clearTimeout(_gsearchTimeout);
  const resultsEl = document.getElementById('gsearch-results');
  // Min 3 chars para reducir carga de servidor
  if (!q || q.length < 3) { resultsEl.style.display = 'none'; return; }

  _gsearchTimeout = setTimeout(async () => {
    try {
      const [users, courses] = await Promise.all([
        api.get(`/canvas/users?search=${encodeURIComponent(q)}&per_page=5`).catch(() => []),
        api.get(`/canvas/courses?search=${encodeURIComponent(q)}&per_page=5`).catch(() => []),
      ]);

      const html = [
        ...users.map(u => `
          <a href="javascript:void(0)" onclick="window.location='/ui/canvas/users'; openUserProfile('${u.id}','${(u.email||u.login_id||'').replace(/'/g,"\\'")}','${u.name.replace(/'/g,"\\'")}'); return false" class="gs-item">
            <i class="bi bi-person text-muted"></i>
            <div>
              <div class="gs-label">${u.name}</div>
              <div class="gs-sub">${u.login_id || u.email || '—'}</div>
            </div>
            <span class="gs-type bg-primary">Usuario</span>
          </a>`),
        ...courses.map(c => `
          <a href="/ui/canvas/courses" class="gs-item">
            <i class="bi bi-book text-muted"></i>
            <div>
              <div class="gs-label">${c.name}</div>
              <div class="gs-sub">${c.course_code || ''}</div>
            </div>
            <span class="gs-type bg-success">Curso</span>
          </a>`),
      ].join('');

      resultsEl.innerHTML = html || '<div class="gs-item text-muted">Sin resultados</div>';
      resultsEl.style.display = 'block';
    } catch(e) {
      logger.error('Error en búsqueda global:', e);
      resultsEl.innerHTML = `<div class="gs-item text-danger small">Error en búsqueda</div>`;
      resultsEl.style.display = 'block';
    }
  }, 700); // Debounce aumentado a 700ms (era 300ms)
}

/* ── API helpers ── */
async function apiCall(method, url, data = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (data) opts.body = JSON.stringify(data);

  let r;
  try {
    r = await fetch(url, opts);
  } catch (netErr) {
    throw new Error('Error de conexión: no se pudo contactar al servidor. Verificá que el servicio está activo.');
  }

  if (!r.ok) {
    let detail;
    try {
      const err = await r.json();
      detail = err.detail;
      if (Array.isArray(detail)) {
        // Pydantic validation errors: [{loc, msg, type}, ...]
        detail = detail.map(e => {
          const field = (e.loc || []).slice(1).join('.');
          return field ? `${field}: ${e.msg}` : e.msg;
        }).join(' | ');
      } else if (detail && typeof detail === 'object') {
        detail = JSON.stringify(detail);
      }
    } catch (_) {
      detail = null;
    }
    const httpMsg = {
      400: 'Solicitud inválida',
      401: 'No autenticado',
      403: 'Acceso denegado',
      404: 'Recurso no encontrado',
      409: 'Conflicto: el recurso ya existe',
      422: 'Datos de entrada inválidos',
      429: 'Demasiadas solicitudes — esperá un momento',
      500: 'Error interno del servidor',
      502: 'Servidor no disponible',
      503: 'Servicio temporalmente no disponible',
    };
    throw new Error(detail || httpMsg[r.status] || `Error ${r.status}: ${r.statusText}`);
  }

  return r.status === 204 ? {} : r.json();
}
const api = {
  get:      (u)    => apiCall('GET',    u),
  post:     (u, d) => apiCall('POST',   u, d),
  put:      (u, d) => apiCall('PUT',    u, d),
  patch:    (u, d) => apiCall('PATCH',  u, d),
  del:      (u)    => apiCall('DELETE', u),
  del_body: (u, d) => apiCall('DELETE', u, d),  // DELETE with JSON body (bulk ops)
};

/* ── Toast notifications ── */
function toast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const id = 'toast-' + Date.now();
  const icons = { success: 'check-circle-fill', danger: 'x-circle-fill', warning: 'exclamation-triangle-fill', info: 'info-circle-fill' };
  c.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
      <div class="d-flex">
        <div class="toast-body"><i class="bi bi-${icons[type]||'info-circle-fill'} me-2"></i>${msg}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`);
  const el = document.getElementById(id);
  new bootstrap.Toast(el, { delay: 4500 }).show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

/* ── Button loading ── */
function setLoading(btn, on) {
  if (on) { btn._orig = btn.innerHTML; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Procesando...'; btn.disabled = true; }
  else    { btn.innerHTML = btn._orig;  btn.disabled = false; }
}

/* ── Global modal ── */
const gModal = () => bootstrap.Modal.getOrCreateInstance(document.getElementById('globalModal'));
function showModal(title, bodyHtml, footerHtml = '') {
  document.getElementById('globalModalTitle').textContent = title;
  document.getElementById('globalModalBody').innerHTML = bodyHtml;
  document.getElementById('globalModalFooter').innerHTML = footerHtml;
  gModal().show();
}
function closeModal() { gModal().hide(); }

/* ── Export table to Excel ── */
function exportTableToExcel(containerId, filename) {
  const d = _tableData[containerId];
  if (!d || !d.rows || d.rows.length === 0) {
    toast('No hay datos para exportar', 'warning');
    return;
  }
  const rows = d.rows.map(row => {
    const obj = {};
    d.cols.forEach(c => { obj[c.label] = row[c.key] ?? ''; });
    return obj;
  });
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Datos');
  XLSX.writeFile(wb, filename || 'export.xlsx');
  toast(`${rows.length} registros exportados`, 'success');
}

/* ── Build table (sortable + optional row selection) ── */
const _tableData = {};

/**
 * @param {string}   containerId
 * @param {Array}    rows
 * @param {Array}    cols        [{key, label}]
 * @param {Function|string} actions  row → HTML string, or ''
 * @param {boolean}  selectable  enable checkbox column (default false)
 * @param {string}   idKey       field used as row id for selection (default 'id')
 */
function buildTable(containerId, rows, cols, actions = '', selectable = false, idKey = 'id') {
  _tableData[containerId] = { rows: [...rows], cols, actions, sortKey: null, sortAsc: true, selectable, idKey };
  _updateBulkBar(containerId, 0);  // reset bar count when table reloads
  _renderTable(containerId);
}

function _renderTable(containerId) {
  const { rows, cols, actions, sortKey, sortAsc, selectable, idKey } = _tableData[containerId];
  const sorted = sortKey
    ? [...rows].sort((a, b) => {
        const av = String(a[sortKey] ?? '').toLowerCase();
        const bv = String(b[sortKey] ?? '').toLowerCase();
        return sortAsc ? av.localeCompare(bv, 'es') : bv.localeCompare(av, 'es');
      })
    : rows;

  const arrow = key => key !== sortKey
    ? '<i class="bi bi-arrow-down-up ms-1 text-muted" style="font-size:.65rem;opacity:.5"></i>'
    : (sortAsc ? '<i class="bi bi-sort-alpha-down ms-1" style="font-size:.7rem"></i>'
               : '<i class="bi bi-sort-alpha-up ms-1" style="font-size:.7rem"></i>');

  const chkHead = selectable
    ? `<th style="width:36px"><input type="checkbox" id="selAll_${containerId}" title="Seleccionar todo" onchange="toggleSelectAll('${containerId}',this.checked)"></th>`
    : '';

  const thead = chkHead + cols.map(c =>
    `<th style="cursor:pointer;user-select:none;white-space:nowrap" onclick="sortTable('${containerId}','${c.key}')">${c.label}${arrow(c.key)}</th>`
  ).join('') + (actions ? '<th>Acciones</th>' : '');

  const colSpan = cols.length + (actions ? 1 : 0) + (selectable ? 1 : 0);
  const tbody = sorted.length === 0
    ? `<tr><td colspan="${colSpan}" class="text-center text-muted py-4">Sin datos</td></tr>`
    : sorted.map(row => {
        const rowId = row[idKey] ?? '';
        const chkCell = selectable
          ? `<td><input type="checkbox" class="row-sel" data-cid="${containerId}" data-rid="${rowId}" onchange="_onRowSelect('${containerId}')"></td>`
          : '';
        const cells = cols.map(c => `<td>${row[c.key] ?? '—'}</td>`).join('');
        return `<tr>${chkCell}${cells}${actions ? `<td>${actions(row)}</td>` : ''}</tr>`;
      }).join('');

  document.getElementById(containerId).innerHTML = `
    <table class="table table-hover mb-0">
      <thead><tr>${thead}</tr></thead>
      <tbody>${tbody}</tbody>
    </table>`;
}

function sortTable(containerId, key) {
  const s = _tableData[containerId];
  s.sortAsc = s.sortKey === key ? !s.sortAsc : true;
  s.sortKey = key;
  _renderTable(containerId);
}

/* ── Row selection helpers ── */

function toggleAllRows(event, containerId) {
  const checkboxes = document.querySelectorAll(`#${containerId} .row-checkbox`);
  checkboxes.forEach(cb => { cb.checked = event.target.checked; });
  updateSelectionBadge(containerId);
}

function updateSelectionBadge(containerId) {
  const ids = getSelectedIds(containerId);
  const badge = document.getElementById(`selBadge_${containerId}`);
  const bar = document.getElementById('bulk-bar');
  if (ids.length > 0) {
    if (badge) badge.textContent = ids.length + ' seleccionado(s)';
    if (bar) {
      bar.dataset.container = containerId;
      document.getElementById('bulk-count').textContent = ids.length + ' fila(s) seleccionada(s)';
      bar.style.display = 'flex';
    }
  } else {
    if (badge) badge.textContent = '';
    if (bar) bar.style.display = 'none';
  }
}

function getSelectedIds(containerId) {
  return [...document.querySelectorAll(`.row-sel[data-cid="${containerId}"]:checked`)]
    .map(cb => String(cb.dataset.rid));
}

function toggleSelectAll(containerId, checked) {
  document.querySelectorAll(`.row-sel[data-cid="${containerId}"]`)
    .forEach(cb => { cb.checked = checked; });
  _onRowSelect(containerId);
}

function clearSelection(containerId) {
  if (!containerId) return;
  document.querySelectorAll(`.row-sel[data-cid="${containerId}"]`)
    .forEach(cb => { cb.checked = false; });
  const allCb = document.getElementById(`selAll_${containerId}`);
  if (allCb) allCb.checked = false;
  _updateBulkBar(containerId, 0);
}

function _onRowSelect(containerId) {
  const count = getSelectedIds(containerId).length;
  // Update inline counter badge if page provided one (id="selBadge_<containerId>")
  const badge = document.getElementById(`selBadge_${containerId}`);
  if (badge) {
    badge.textContent = count > 0 ? `${count} seleccionado${count !== 1 ? 's' : ''}` : '';
    badge.style.display = count > 0 ? '' : 'none';
  }
  _updateBulkBar(containerId, count);
}

/* ── Floating bulk-action bar ── */

function _updateBulkBar(containerId, count) {
  const bar = document.getElementById('bulk-bar');
  if (!bar) return;
  if (count > 0) {
    bar.style.display = 'flex';
    bar.dataset.container = containerId;
    document.getElementById('bulk-count').textContent =
      count + ' seleccionado' + (count !== 1 ? 's' : '');
  } else {
    bar.style.display = 'none';
    // Keep container so clearSelection button still works during animation
  }
}

/* ── Local search filter (instant, client-side) ── */
function filterTable(inputId, tableContainer) {
  const q = document.getElementById(inputId).value.toLowerCase();
  let shown = 0, hidden = 0;
  document.querySelectorAll(`#${tableContainer} tbody tr`).forEach(tr => {
    if (tr.textContent.toLowerCase().includes(q)) {
      tr.style.display = '';
      shown++;
    } else {
      tr.style.display = 'none';
      hidden++;
    }
  });
  // Show empty state if all rows hidden
  const noData = document.querySelector(`#${tableContainer} .no-data-row`);
  if (shown === 0 && hidden > 0 && !noData) {
    const tbody = document.querySelector(`#${tableContainer} tbody`);
    const cols = tbody.querySelector('tr')?.cells.length || 1;
    tbody.insertAdjacentHTML('beforeend',
      `<tr class="no-data-row"><td colspan="${cols}" class="text-center text-muted py-3">Sin resultados para la búsqueda</td></tr>`);
  } else if (noData && shown > 0) {
    noData.remove();
  }
}

/* ── Smart local search with fuzzy matching ── */
function smartFilter(inputId, tableContainer, columns = null) {
  const q = document.getElementById(inputId).value.toLowerCase().trim();
  if (!q) { filterTable(inputId, tableContainer); return; }

  const tbody = document.querySelector(`#${tableContainer} tbody`);
  const rows = Array.from(tbody.querySelectorAll('tr:not(.no-data-row)'));

  const scored = rows.map(tr => {
    let score = 0;
    const cells = Array.from(tr.cells);
    cells.forEach((cell, idx) => {
      const text = cell.textContent.toLowerCase();
      if (text.includes(q)) score += 100;
      if (text.startsWith(q)) score += 50;
      if (text.match(new RegExp(`\\b${q}`, 'i'))) score += 25;
    });
    return { tr, score };
  }).filter(s => s.score > 0).sort((a, b) => b.score - a.score);

  rows.forEach(tr => tr.style.display = 'none');
  scored.forEach(s => s.tr.style.display = '');

  if (scored.length === 0) {
    const cols = rows[0]?.cells.length || 1;
    tbody.innerHTML = `<tr class="no-data-row"><td colspan="${cols}" class="text-center text-muted py-3">Sin resultados</td></tr>`;
  }
}

/* ── Excel drop zone ── */
function initDropZone(zoneId, fileInputId, previewCb) {
  const zone = document.getElementById(zoneId);
  const inp  = document.getElementById(fileInputId);
  if (!zone || !inp) return;
  zone.addEventListener('click', () => inp.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) { inp.files = e.dataTransfer.files; previewCb(e.dataTransfer.files[0]); }
  });
  inp.addEventListener('change', () => { if (inp.files[0]) previewCb(inp.files[0]); });
}

/* ── Read Excel client-side (preview) ── */
function readExcel(file, cb) {
  const reader = new FileReader();
  reader.onload = e => {
    const wb = XLSX.read(e.target.result, { type: 'binary' });
    const ws = wb.Sheets[wb.SheetNames[0]];
    cb(XLSX.utils.sheet_to_json(ws, { defval: '' }));
  };
  reader.readAsBinaryString(file);
}

/* ── Upload Excel to server ── */
async function uploadExcel(url, fileInputId) {
  const inp = document.getElementById(fileInputId);
  if (!inp.files[0]) throw new Error('Selecciona un archivo Excel primero');
  const fd = new FormData();
  fd.append('file', inp.files[0]);
  const r = await fetch(url, { method: 'POST', body: fd });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText); }
  return r.json();
}

/* ── Render bulk result ── */
function renderBulkResult(result, containerId) {
  const ok  = result.succeeded || [];
  const err = result.failed    || [];
  const html = `
    <div class="d-flex gap-3 mb-3">
      <span class="badge bg-success fs-6">${ok.length} exitosos</span>
      <span class="badge bg-danger  fs-6">${err.length} fallidos</span>
    </div>
    ${err.length ? `<div class="alert alert-warning p-2" style="max-height:200px;overflow:auto">
      ${err.map(e => `<div class="small">${JSON.stringify(e.input||e)} — <span class="text-danger">${e.error}</span></div>`).join('')}
    </div>` : ''}`;
  if (containerId) document.getElementById(containerId).innerHTML = html;
  return html;
}

/* ── Confirm dialog ── */
function confirmAction(msg, cb) {
  showModal('Confirmar acción', `<p>${msg}</p>`,
    `<button class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
     <button class="btn btn-danger" id="confirmBtn">Confirmar</button>`);
  document.getElementById('confirmBtn').onclick = () => { closeModal(); cb(); };
}
