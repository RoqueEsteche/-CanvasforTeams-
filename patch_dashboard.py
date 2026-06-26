import re

with open('Frontend/templates/dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add HTML for the new cards in the bottom row
new_cards = """
  <!-- Licencias M365 -->
  <div class="col-md-4">
    <div class="table-card h-100">
      <div class="card-header bg-light">
        <i class="bi bi-key-fill text-warning dash-card-icon"></i>
        <strong>Licencias M365</strong>
      </div>
      <div id="licenses-container" class="panel-scroll p-3">
        <div class="text-center text-muted py-4">
          <span class="spinner-border spinner-border-sm"></span> Cursos...
        </div>
      </div>
    </div>
  </div>
  
  <!-- Cuentas Huérfanas -->
  <div class="col-md-4">
    <div class="table-card h-100">
      <div class="card-header bg-light">
        <i class="bi bi-exclamation-triangle-fill text-danger dash-card-icon"></i>
        <strong>Cuentas Huérfanas</strong>
      </div>
      <div id="orphans-container" class="panel-scroll p-3">
        <div class="text-center text-muted py-4">
          <span class="spinner-border spinner-border-sm"></span> Analizando...
        </div>
      </div>
    </div>
  </div>
"""

# Find where to inject (after the recent courses col-md-4)
target_html = """  <div class="col-md-4">
    <div class="table-card h-100">
      <div class="card-header">
        <i class="bi bi-book-fill text-canvas-blue dash-card-icon"></i>
        <strong>Cursos recientes</strong>"""

if target_html in html:
    html = html.replace(target_html, new_cards + "\n" + target_html)
else:
    print("Could not find insertion point for cards.")

# 2. Add Javascript to fetch and render the new cards
new_js = """
// --- DASHBOARD ANALYTICS ---
async function loadAnalytics() {
    try {
        const licRes = await api.get('/analytics/licenses');
        const licContainer = document.getElementById('licenses-container');
        if (licRes.licenses && licRes.licenses.length > 0) {
            licContainer.innerHTML = licRes.licenses.map(l => `
                <div class="mb-3 border-bottom pb-2">
                    <div class="fw-bold text-primary">${l.skuPartNumber}</div>
                    <div class="small d-flex justify-content-between mt-1">
                        <span class="text-success"><i class="bi bi-check-circle"></i> Disponibles: ${l.available}</span>
                        <span class="text-danger"><i class="bi bi-person-dash"></i> Usadas: ${l.consumed}</span>
                    </div>
                    <div class="progress mt-2" style="height: 6px;">
                        <div class="progress-bar bg-primary" role="progressbar" style="width: ${(l.consumed/l.prepaid)*100}%" aria-valuenow="${l.consumed}" aria-valuemin="0" aria-valuemax="${l.prepaid}"></div>
                    </div>
                </div>
            `).join('');
        } else {
            licContainer.innerHTML = '<div class="text-muted small">No hay licencias.</div>';
        }
    } catch (e) {
        document.getElementById('licenses-container').innerHTML = '<div class="text-danger small">Error cargando licencias</div>';
    }

    try {
        const orphRes = await api.get('/analytics/orphans');
        const orpContainer = document.getElementById('orphans-container');
        let orpHtml = `<div class="small mb-2"><strong>Analizados:</strong> ${orphRes.total_canvas_analyzed} (Canvas), ${orphRes.total_teams_analyzed} (Teams)</div>`;
        
        if (orphRes.orphaned_in_canvas_sample.length > 0) {
            orpHtml += `<div class="fw-bold text-danger small mt-2">Solo en Canvas (Muestra):</div><ul class="small mb-1">` + 
                       orphRes.orphaned_in_canvas_sample.map(e => `<li>${e}</li>`).join('') + `</ul>`;
        }
        if (orphRes.orphaned_in_teams_sample.length > 0) {
            orpHtml += `<div class="fw-bold text-warning small mt-2">Solo en Teams (Muestra):</div><ul class="small mb-1">` + 
                       orphRes.orphaned_in_teams_sample.map(e => `<li>${e}</li>`).join('') + `</ul>`;
        }
        if (orphRes.orphaned_in_canvas_sample.length === 0 && orphRes.orphaned_in_teams_sample.length === 0) {
            orpHtml += `<div class="text-success small mt-3"><i class="bi bi-check-circle-fill"></i> Todo sincronizado en esta muestra.</div>`;
        }
        
        orpContainer.innerHTML = orpHtml;
    } catch (e) {
        document.getElementById('orphans-container').innerHTML = '<div class="text-danger small">Error cargando huérfanos</div>';
    }
}

// Attach to refreshAll
const oldRefresh = refreshAll;
refreshAll = function() {
    oldRefresh();
    loadAnalytics();
};
// Trigger first load
setTimeout(loadAnalytics, 1000);
</script>
"""

html = html.replace("</script>", new_js)

with open('Frontend/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Dashboard patched successfully!')
