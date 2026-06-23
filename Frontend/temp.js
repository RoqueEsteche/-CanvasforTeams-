
  // ==========================================
  // ESTADO GLOBAL
  // ==========================================
  let lastQuery = '';
  let currentData = null;

  const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // ==========================================
  // CONTROLADOR PRINCIPAL: BÚSQUEDA
  // ==========================================
  async function searchUnified() {
    const query = document.getElementById('unifiedSearchInput').value.trim();
    if (!query) { toast('Ingrese un identificador para buscar', 'warning'); return; }

    lastQuery = query;

    setLoadingState();

    try {
      currentData = await api.get('/profile/lookup?email=' + encodeURIComponent(query));
      renderList(currentData, query);
      renderDetail(currentData, query);
    } catch (e) {
      showErrorState(e.message);
    }
  }

  // ==========================================
  // RENDERIZADO DE COMPONENTES
  // ==========================================

  // 1. Maestro: Lista de resultados (Panel Izquierdo)
  function renderList(data, query) {
    const resArea = document.getElementById('unifiedResultsArea');

    const cName = data.canvas?.user?.name;
    const tName = data.teams?.user?.displayName;
    const displayName = cName || tName || 'Usuario Desconocido';
    const email = data.canvas?.user?.login_id || data.teams?.user?.mail || query;

    resArea.innerHTML = `
    <button class="list-group-item list-group-item-action p-4 border-0 border-bottom active" onclick="renderDetail(currentData, lastQuery)">
      <div class="d-flex align-items-center gap-3">
        <div class="bg-white text-primary rounded-circle d-flex align-items-center justify-content-center shadow-sm" style="width: 48px; height: 48px;">
          <i class="bi bi-person-fill fs-4"></i>
        </div>
        <div>
          <div class="fw-bold fs-6 mb-1">${displayName}</div>
          <div class="small opacity-75">${email}</div>
        </div>
      </div>
      <div class="mt-3 d-flex gap-2">
        ${data.canvas ? '<span class="badge bg-danger bg-opacity-25 text-white border border-danger">Canvas OK</span>' : '<span class="badge bg-secondary bg-opacity-25 text-white">Sin Canvas</span>'}
        ${data.teams ? '<span class="badge bg-primary bg-opacity-25 text-white border border-primary">Teams OK</span>' : '<span class="badge bg-secondary bg-opacity-25 text-white">Sin Teams</span>'}
      </div>
    </button>
  `;
  }

  // 2. Detalle: Panel Completo (Panel Derecho)
  function renderDetail(data, query) {
    const detailPane = document.getElementById('unifiedDetailPane');
    if (!data) return;

    const headerHtml = buildUnifiedHeader(data.canvas?.user, data.teams?.user, query, data.canvas?.enrollments?.length || 0, data.teams?.teams?.length || 0);
    const canvasHtml = buildCanvasSection(data.canvas);
    const teamsHtml = buildTeamsSection(data.teams);

    detailPane.innerHTML = `
      <div class="p-4 overflow-auto" style="height: 100%;">
        ${headerHtml}
        ${canvasHtml}
        ${teamsHtml}
      </div>
    `;
  }

  // ==========================================
  // CONSTRUCTORES DE VISTA (TEMPLATES)
  // ==========================================

  function buildUnifiedHeader(canvasUser, teamsUser, fallbackQuery, cursosCount, teamsCount) {
    const displayName = canvasUser?.name || teamsUser?.displayName || 'Usuario Desconocido';
    const email = teamsUser?.mail || teamsUser?.userPrincipalName || canvasUser?.login_id || fallbackQuery;
    const sis = canvasUser?.sis_user_id || '—';

    const tStatus = teamsUser
      ? (teamsUser.accountEnabled
        ? '<span class="badge bg-success">Activo en Teams</span>'
        : '<span class="badge bg-danger">Bloqueado en Teams</span>')
      : '';
      
    const initials = displayName.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();

    return `
    <!-- Top Unified Header -->
    <div class="table-card p-4 mb-4">
      <div class="d-flex align-items-center gap-4 flex-wrap">
        <div class="rounded-circle d-flex align-items-center justify-content-center fw-bold text-white fs-2 flex-shrink-0"
             style="width:72px;height:72px;background:var(--sidebar-accent)">${esc(initials)}</div>
        <div class="flex-grow-1">
          <h4 class="mb-0 fw-bold">${esc(displayName)}</h4>
          <div class="text-muted small mb-2">${esc(email)}</div>
          <div class="d-flex flex-wrap gap-2">
            ${canvasUser ? `<span class="badge bg-light text-dark border"><i class="bi bi-mortarboard-fill text-warning me-1"></i>Canvas SIS: ${esc(sis)}</span>` : ''}
            ${teamsUser ? `<span class="badge bg-light text-dark border"><i class="bi bi-person-badge-fill me-1" style="color:#6264a7"></i>${esc(teamsUser.jobTitle || teamsUser.department || 'Azure AD')}</span>` : ''}
            ${tStatus}
          </div>
        </div>
      </div>
    </div>
    
    <!-- Stats -->
    <div class="row g-3 mb-4">
      <div class="col-6 col-md-6">
        <div class="table-card p-3 text-center">
          <div class="fs-3 fw-bold text-primary">${cursosCount}</div>
          <div class="small text-muted">Matrículas Canvas</div>
        </div>
      </div>
      <div class="col-6 col-md-6">
        <div class="table-card p-3 text-center">
          <div class="fs-3 fw-bold" style="color:#6264a7">${teamsCount}</div>
          <div class="small text-muted">Equipos Teams</div>
        </div>
      </div>
    </div>
    `;
  }

  const ROLE_MAP = {
    TeacherEnrollment:  { label: 'Docente',       cls: 'bg-warning text-dark' },
    StudentEnrollment:  { label: 'Alumno',         cls: 'bg-primary'          },
    TaEnrollment:       { label: 'Asistente TA',   cls: 'bg-info text-dark'   },
    ObserverEnrollment: { label: 'Observador',     cls: 'bg-secondary'        },
  };
  const STATE_MAP = {
    active:    { label: 'Activo',     cls: 'bg-success' },
    invited:   { label: 'Invitado',   cls: 'bg-warning text-dark' },
    completed: { label: 'Completado', cls: 'bg-secondary' },
    inactive:  { label: 'Inactivo',   cls: 'bg-danger'  },
  };

  function roleBadge(role) {
    const r = ROLE_MAP[role] || { label: role || '—', cls: 'bg-secondary' };
    return `<span class="badge ${r.cls}">${r.label}</span>`;
  }
  function stateBadge(state) {
    const s = STATE_MAP[state] || { label: state || '—', cls: 'bg-secondary' };
    return `<span class="badge ${s.cls}">${s.label}</span>`;
  }

  function buildCanvasSection(canvasData) {
    let listHtml = '';

    if (canvasData && canvasData.enrollments.length > 0) {
      listHtml = `
      <div class="table-responsive mb-0" style="max-height:340px;overflow-y:auto">
        <table class="table table-sm table-hover mb-0">
          <thead>
            <tr>
              <th>Código</th><th>Nombre del curso</th><th>Programa</th>
              <th>Año</th><th>Rol</th><th>Estado</th><th class="text-end">Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${canvasData.enrollments.map(e => `
            <tr>
              <td class="small text-muted align-middle">${esc(e.course_code || '—')}</td>
              <td class="small fw-semibold align-middle">${esc(e.course_name)}</td>
              <td class="small align-middle">${esc(e.program || '—')}</td>
              <td class="small align-middle">${esc(e.year || '—')}</td>
              <td class="align-middle">${roleBadge(e.role)}</td>
              <td class="align-middle">${stateBadge(e.enrollment_state)}</td>
              <td class="text-end">
                <button class="btn btn-sm btn-light text-danger btn-icon" title="Desmatricular" onclick="unenrollCanvas('${e.course_id}', '${e.id}', this)">
                  <i class="bi bi-trash3-fill"></i>
                </button>
              </td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } else if (canvasData) {
      listHtml = '<div class="text-center text-muted py-4">Sin matrículas activas</div>';
    } else {
      listHtml = `
        <div class="text-center py-4">
          <i class="bi bi-person-x fs-1 text-muted opacity-50 d-block"></i>
          <div class="small text-muted mt-2 mb-3">No existe en Canvas</div>
          <button class="btn btn-sm btn-danger" onclick="openCanvasCreate()"><i class="bi bi-person-plus me-1"></i>Crear perfil</button>
        </div>`;
    }

    return `
      <!-- Canvas section -->
      <div class="table-card mb-4">
        <div class="card-header border-bottom-0 pb-0">
          <i class="bi bi-mortarboard-fill text-warning me-2"></i><strong>Canvas LMS</strong>
        </div>
        <div class="p-3">
          ${listHtml}
        </div>
      </div>
    `;
  }

  function buildTeamsSection(teamsData) {
    let listHtml = '';
    const tId = teamsData?.user?.id;

    if (teamsData && teamsData.teams.length > 0) {
      const VISIB = { Public: 'Público', Private: 'Privado', HiddenMembership: 'Organización' };
      const VISIB_CLS = { Public: 'bg-success', Private: 'bg-warning text-dark', HiddenMembership: 'bg-info text-dark' };

      listHtml = `
      <div id="teamsListContainer" class="row g-3">
        ${teamsData.teams.map(t => {
          const vis = VISIB[t.visibility] || t.visibility || '—';
          const visCls = VISIB_CLS[t.visibility] || 'bg-secondary';
          return `
            <div class="col-md-6 col-lg-6 teams-row">
              <div class="border rounded p-3 h-100 position-relative">
                <div class="d-flex justify-content-between align-items-start mb-2">
                  <div class="fw-semibold small pe-4">${esc(t.displayName)}</div>
                  <span class="badge ${visCls} flex-shrink-0 ms-1">${vis}</span>
                </div>
                ${t.description ? `<div class="text-muted" style="font-size:.72rem;margin-bottom:.5rem">${esc(t.description.slice(0,80))}${t.description.length>80?'…':''}</div>` : ''}
                <div class="position-absolute top-0 end-0 p-2">
                  <button class="btn btn-sm btn-light text-danger btn-icon" title="Quitar de equipo" onclick="removeTeamsMember('${t.id}', '${tId}', this)">
                    <i class="bi bi-trash3-fill"></i>
                  </button>
                </div>
              </div>
            </div>`;
        }).join('')}
      </div>`;
    } else if (teamsData) {
      listHtml = '<div class="text-center text-muted py-4 empty-teams-msg">No pertenece a ningún equipo</div>';
    } else {
      listHtml = `
        <div class="text-center py-4">
          <i class="bi bi-person-x fs-1 text-muted opacity-50 d-block"></i>
          <div class="small text-muted mt-2 mb-3">No existe en Teams</div>
          <button class="btn btn-sm btn-primary" onclick="openTeamsCreate()"><i class="bi bi-person-plus me-1"></i>Crear perfil</button>
        </div>`;
    }

    return `
      <!-- Teams section -->
      <div class="table-card mb-4">
        <div class="card-header border-bottom-0 pb-0">
          <i class="bi bi-microsoft-teams me-2" style="color:#6264a7"></i><strong>Microsoft Teams / Azure AD</strong>
          <span id="teamsCountLabel" class="d-none"></span>
        </div>
        <div class="p-3">
          ${listHtml}
        </div>
      </div>
    `;
  }

  // ==========================================
  // UTILIDADES UI (Loaders y Errores)
  // ==========================================

  function setLoadingState() {
    document.getElementById('unifiedResultsArea').innerHTML = `
    <div class="p-4">
      <div class="d-flex gap-3 align-items-center mb-4">
        <div class="skeleton rounded-circle" style="width: 48px; height: 48px;"></div>
        <div class="flex-grow-1">
          <div class="skeleton mb-2 w-75" style="height: 16px;"></div>
          <div class="skeleton w-50" style="height: 12px;"></div>
        </div>
      </div>
    </div>`;

    document.getElementById('unifiedDetailPane').innerHTML = `
    <div class="d-flex align-items-center justify-content-center h-100 w-100 text-muted flex-column opacity-50 py-5">
      <div class="spinner-border text-primary mb-3" style="width: 3rem; height: 3rem;" role="status"></div>
      <p>Cargando perfiles...</p>
    </div>`;
  }

  function showErrorState(message) {
    document.getElementById('unifiedResultsArea').innerHTML = `
    <div class="p-4 text-danger"><i class="bi bi-exclamation-triangle-fill me-2"></i>Error: ${message}</div>
  `;
    document.getElementById('unifiedDetailPane').innerHTML = '';
  }

  // ==========================================
  // CRUD Y ACCIONES API
  // ==========================================

  function openCanvasCreate() {
    const query = document.getElementById('unifiedSearchInput').value.trim();
    const isEmail = query.includes('@');

    showModal('Crear Usuario en Canvas', `
    <form id="canvasCreateForm">
      <div class="row g-3">
        <div class="col-md-12"><label class="form-label">Nombre Completo *</label><input type="text" id="c_name" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">Email *</label><input type="email" id="c_email" class="form-control" value="${isEmail ? query : ''}" required></div>
        <div class="col-md-6"><label class="form-label">Login ID *</label><input type="text" id="c_login" class="form-control" value="${isEmail ? query : ''}" required></div>
        <div class="col-md-6"><label class="form-label">Contraseña (opcional)</label><input type="password" id="c_pass" class="form-control"></div>
        <div class="col-md-6"><label class="form-label">SIS ID</label><input type="text" id="c_sis" class="form-control" value="${!isEmail ? query : ''}"></div>
      </div>
    </form>`,
      `<button class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
     <button class="btn btn-success" id="c_saveBtn" onclick="saveCanvasUser()"><i class="bi bi-check-lg me-1"></i>Crear</button>`);
  }

  async function saveCanvasUser() {
    const btn = document.getElementById('c_saveBtn');
    const data = {
      name: document.getElementById('c_name').value,
      email: document.getElementById('c_email').value,
      login_id: document.getElementById('c_login').value,
      password: document.getElementById('c_pass').value || null,
      sis_user_id: document.getElementById('c_sis').value || null
    };

    if (!data.name || !data.email || !data.login_id) return toast('Completa los campos obligatorios (*)', 'warning');

    setLoading(btn, true);
    try {
      await api.post('/canvas/users', data);
      toast('Usuario creado en Canvas correctamente', 'success');
      closeModal();
      searchUnified();
    } catch (e) { toast('Error: ' + e.message, 'danger'); }
    finally { setLoading(btn, false); }
  }

  async function unenrollCanvas(course_id, enrollment_id, btn) {
    if (!confirm('¿Desmatricular usuario de este curso?')) return;
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
    btn.disabled = true;

    try {
      await api.del('/canvas/enrollments/' + enrollment_id + '?course_id=' + course_id + '&task=conclude');
      toast('Usuario desmatriculado de Canvas', 'success');

      const row = btn.closest('.list-group-item');
      row.style.transition = 'all 0.3s ease';
      row.style.opacity = '0';
      row.style.transform = 'translateX(20px)';
      setTimeout(() => row.remove(), 300);
    } catch (e) {
      toast('Error: ' + e.message, 'danger');
      btn.innerHTML = originalHtml;
      btn.disabled = false;
    }
  }

  async function removeTeamsMember(team_id, user_id, btn) {
    if (!confirm('¿Quitar usuario de este equipo?')) return;
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
    btn.disabled = true;

    try {
      await api.post('/teams/teams/' + team_id + '/members/bulk-remove', { team_id: team_id, user_ids: [user_id] });
      toast('Usuario removido del equipo en Teams', 'success');

      const row = btn.closest('.list-group-item');
      row.style.transition = 'all 0.3s ease';
      row.style.opacity = '0';
      row.style.transform = 'translateX(20px)';

      setTimeout(() => {
        row.remove();
        const countLabel = document.getElementById('teamsCountLabel');
        if (countLabel) {
          const rows = document.querySelectorAll('.teams-row').length;
          countLabel.innerHTML = `<i class="bi bi-microsoft-teams me-2"></i>Equipos (${rows})`;
          if (rows === 0) {
            const container = document.getElementById('teamsListContainer');
            if (container) container.innerHTML = '<div class="list-group-item text-muted p-3 empty-teams-msg">No pertenece a ningún equipo</div>';
          }
        }
      }, 300);

    } catch (e) {
      toast('Error: ' + e.message, 'danger');
      btn.innerHTML = originalHtml;
      btn.disabled = false;
    }
  }

  // ==========================================
  // CRUD: TEAMS
  // ==========================================

  function openTeamsCreate() {
    const query = document.getElementById('unifiedSearchInput').value.trim();
    const isEmail = query.includes('@');
    const alias = isEmail ? query.split('@')[0] : '';

    showModal('Crear Usuario en Teams / Azure AD', `
    <form id="teamsCreateForm">
      <div class="row g-3">
        <div class="col-md-12"><label class="form-label">Nombre Completo *</label><input type="text" id="t_display_name" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">UPN (Correo) *</label><input type="email" id="t_upn" class="form-control" value="${isEmail ? query : ''}" required></div>
        <div class="col-md-6"><label class="form-label">Alias de correo *</label><input type="text" id="t_alias" class="form-control" value="${alias}" required></div>
        <div class="col-md-6"><label class="form-label">Contraseña *</label><input type="password" id="t_pass" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">País (Ubicación)</label><input type="text" id="t_loc" class="form-control" value="PE" required></div>
        <div class="col-12">
          <div class="form-check"><input class="form-check-input" type="checkbox" id="t_enabled" checked><label class="form-check-label" for="t_enabled">Cuenta habilitada</label></div>
        </div>
      </div>
    </form>`,
      `<button class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
     <button class="btn btn-primary" id="t_saveBtn" onclick="saveTeamsUser()"><i class="bi bi-check-lg me-1"></i>Crear en Teams</button>`);
  }

  async function saveTeamsUser() {
    const btn = document.getElementById('t_saveBtn');
    const form = document.getElementById('teamsCreateForm');
    if (!form.checkValidity()) { form.reportValidity(); return; }

    const data = {
      display_name: document.getElementById('t_display_name').value,
      user_principal_name: document.getElementById('t_upn').value,
      mail_nickname: document.getElementById('t_alias').value,
      password: document.getElementById('t_pass').value,
      usage_location: document.getElementById('t_loc').value,
      account_enabled: document.getElementById('t_enabled').checked
    };

    setLoading(btn, true);
    try {
      await api.post('/teams/users', data);
      toast('Usuario creado en Teams/Azure AD correctamente', 'success');
      closeModal();
      searchUnified();
    } catch (e) { toast('Error: ' + e.message, 'danger'); }
    finally { setLoading(btn, false); }
  }
