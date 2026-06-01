# Guía de Despliegue en Render.com

## Prerrequisitos

1. **Cuenta en Render.com** - https://render.com
2. **Repositorio en GitHub** - Sube tu código a GitHub
3. **Credenciales de Canvas y Azure AD** - Tener los tokens y IDs listos

## Paso 1: Preparar el Repositorio

1. Asegúrate de que los siguientes archivos estén en la raíz del proyecto:
   - `requirements.txt` ✓
   - `render.yaml` ✓
   - `app/main.py` ✓
   - `.env.example` ✓

2. Sube todo a GitHub:
```bash
git add .
git commit -m "Preparar para despliegue en Render"
git push origin main
```

## Paso 2: Crear el Servicio en Render

### Opción A: Despliegue Manual (Recomendado para la primera vez)

1. Accede a https://dashboard.render.com
2. Haz clic en **"New +"** → **"Web Service"**
3. Selecciona **"Deploy an existing repository"**
4. Conecta tu cuenta de GitHub y selecciona el repositorio `claudecode-CanvasforTeams-`

### Opción B: Despliegue Automático (usa render.yaml)

1. Render detectará automáticamente `render.yaml`
2. Haz clic en **"Connect"** para autorizar GitHub
3. Selecciona el repositorio

## Paso 3: Configurar el Servicio

Si Render no detecta `render.yaml` automáticamente, configura manualmente:

| Campo | Valor |
|-------|-------|
| **Name** | `canvas-teams-api` |
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Standard (o superior si necesitas más recursos) |

## Paso 4: Configurar Variables de Entorno

En **Environment Variables**, añade:

### Canvas LMS (OBLIGATORIO)
```
CANVAS_BASE_URL = https://tuinstancia.instructure.com
CANVAS_ACCESS_TOKEN = tu_token_aqui
CANVAS_ACCOUNT_ID = 1
```

### Azure AD / Microsoft (OBLIGATORIO)
```
AZURE_TENANT_ID = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET = tu_secreto_aqui
AZURE_SKU_STUDENTS = STANDARDWOFFPACK_STUDENT
AZURE_SKU_TEACHERS = STANDARDWOFFPACK_FACULTY
```

### Configuración Institucional (OBLIGATORIO)
```
INSTITUTIONAL_DOMAIN = usil.edu.py
USAGE_LOCATION = PY
TEAMS_URL = https://teams.microsoft.com
ENVIRONMENT = production
```

### SMTP (OPCIONAL - para envío de correos)
```
SMTP_HOST = smtp.office365.com
SMTP_PORT = 587
SMTP_TLS = true
SMTP_USER = notificaciones@usil.edu.py
SMTP_PASSWORD = tu_password_smtp
SMTP_FROM = no-reply@usil.edu.py
```

## Paso 5: Desplegar

1. Haz clic en **"Create Web Service"**
2. Render comenzará a:
   - Clonar el repositorio
   - Instalar dependencias (`pip install -r requirements.txt`)
   - Iniciar el servidor

3. **Espera 5-10 minutos** mientras se despliega

## Paso 6: Verificar el Despliegue

1. Ir a https://dashboard.render.com/project/prj-d8bgl23eo5us73aonjbg
2. Ver el estado del servicio - debería mostrar **"Live"** en verde
3. Abrir la URL generada por Render (ej: `https://canvas-teams-api.onrender.com`)
4. Debería ver:
   - `http://canvas-teams-api.onrender.com/health` → estado del servidor
   - `http://canvas-teams-api.onrender.com/ui/canvas/enrollments` → aplicación web

## Paso 7: Configurar el Dominio (Opcional)

Si tienes un dominio personalizado:

1. En Render Dashboard → Settings
2. Agregar dominio personalizado
3. Apuntar DNS records a Render (Render te dará las instrucciones)

## Troubleshooting

### Error: "Build failed"
- Verifica que `requirements.txt` existe y es válido
- Revisa los logs en Render Dashboard → Logs

### Error: "Port already in use"
- Asegúrate de que el `startCommand` usa `$PORT` (variable de Render)
- No hardcodear el puerto 3000

### Error: "Module not found"
- Verifica que `requirements.txt` incluye todas las dependencias
- Revisa que `app/main.py` existe en la raíz

### Base de datos SQLite
- Render usa un sistema de archivos temporal
- Los datos se pierden al redeplegar
- **Solución:** Usar una base de datos persistente (PostgreSQL, MongoDB)

## Configurar Base de Datos Persistente - PostgreSQL (Recomendado)

La aplicación soporta **SQLite (fallback)** y **PostgreSQL (producción)**. Para migrar a PostgreSQL:

### Paso 1: Crear Base de Datos PostgreSQL en Render

1. En Render Dashboard → **New +** → **PostgreSQL**
2. Configurar:
   - **Name:** `canvas-teams-db` (o tu preferencia)
   - **Database:** `canvas_teams` (default es bueno)
   - **User:** (Render genera automáticamente)
   - **Region:** (Misma que tu web service)
3. Crear la base de datos (esperar 2-3 minutos)
4. Copiar la **Connection String** (algo como `postgresql://user:pass@host:5432/db`)

### Paso 2: Agregar DATABASE_URL al Web Service

1. En Render Dashboard, ir a tu web service
2. **Environment** → Agregar nueva variable:
   - **Key:** `DATABASE_URL`
   - **Value:** Pegar la connection string de PostgreSQL
   - **Sync:** false (no compartir entre servicios)
3. Guardar cambios

### Paso 3: Redeploy Automático

1. Render redeployará automáticamente con `DATABASE_URL` configurada
2. La aplicación detectará `DATABASE_URL` y usará PostgreSQL automáticamente
3. SQLite es fallback si `DATABASE_URL` no está definida

### Paso 4: Migrar Datos (Opcional)

Si tienes datos en SQLite que quieres migrar a PostgreSQL:

```bash
# Localmente (para desarrollo)
export DATABASE_URL="postgresql://user:pass@host:5432/db"
python scripts/migrate_sqlite_to_postgres.py
```

**Nota:** En producción (Render), esto se haría accediendo a la consola del servicio.

### Verificar Migración

```bash
curl https://canvas-teams-api.onrender.com/stats

# Debería mostrar conteos de usuarios, cursos, etc.
# Ejemplo:
# {
#   "canvas_users": 1234,
#   "canvas_courses": 45,
#   "azure_users": 2000,
#   "last_sync": 1234567890.0
# }
```

## Auto-Despliegue en cada Push

1. Render detectará automáticamente cambios en GitHub
2. Cada `git push` a la rama `main` iniciará un nuevo despliegue
3. Ver progreso en **Deployments** en Render Dashboard

## Verificación Final

```bash
# Verificar que el servidor está activo
curl https://canvas-teams-api.onrender.com/health

# Debería responder con algo como:
# {"status":"ok","version":"1.1.0","cache":{"hits":123,...}}
```

## Soporte

- Documentación de Render: https://render.com/docs
- Dashboard: https://dashboard.render.com
- Estado de servicios: https://status.render.com

---

**Nota:** El primer despliegue puede tardar 10-15 minutos. Los despliegues subsecuentes son más rápidos (3-5 minutos).
