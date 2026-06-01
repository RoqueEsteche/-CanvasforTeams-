# Script para ejecutar Canvas for Teams localmente
# Uso: .\run.ps1

Write-Host "=== Canvas for Teams - Local Development ===" -ForegroundColor Cyan
Write-Host ""

# Verificar si pip está instalado
try {
    pip --version | Out-Null
} catch {
    Write-Host "ERROR: Python/pip no está instalado" -ForegroundColor Red
    exit 1
}

# Instalar/actualizar dependencias si es necesario
Write-Host "Verificando dependencias..." -ForegroundColor Yellow
pip install -q -r requirements.txt

Write-Host ""
Write-Host "Iniciando servidor en http://127.0.0.1:3000..." -ForegroundColor Green
Write-Host "Presiona CTRL+C para detener" -ForegroundColor Gray
Write-Host ""

# Configurar encoding UTF-8 y ejecutar uvicorn
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload --log-level info
