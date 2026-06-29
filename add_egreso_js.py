import sys

with open('Frontend/static/js/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

new_code = '''
async function fetchSheetsEgreso() {
    const urlInput = document.getElementById('urlEgresoOneDrive').value.trim();
    if (!urlInput) {
        toast("Por favor ingresa la URL de OneDrive primero.", "warning");
        return;
    }
    
    const btn = document.getElementById('btnLoadSheetsEgreso');
    const select = document.getElementById('sheetEgresoOneDrive');
    const oldText = btn.innerHTML;
    
    try {
        setLoading(btn, true);
        const sheets = await api.post('/excel/egreso/sheets', { url: urlInput });
        if (sheets && sheets.length > 0) {
            select.innerHTML = '<option value="">Selecciona una pestaña...</option>';
            sheets.forEach(sheet => {
                const option = document.createElement('option');
                option.value = sheet;
                option.textContent = sheet;
                select.appendChild(option);
            });
            toast("Pestañas cargadas correctamente.", "success");
        } else {
            select.innerHTML = '<option value="">No se encontraron pestañas.</option>';
            toast("No se encontraron pestañas en este archivo.", "warning");
        }
    } catch (e) {
        toast('Error al cargar pestañas: ' + (e.detail || e.message || e), 'danger');
        select.innerHTML = '<option value="">Error al cargar pestañas</option>';
    } finally {
        setLoading(btn, false);
        btn.innerHTML = oldText;
    }
}
'''

content += "\n" + new_code

with open('Frontend/static/js/main.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("JS appended for egreso sheets")
