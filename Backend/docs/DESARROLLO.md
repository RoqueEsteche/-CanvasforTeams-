# Guía de Desarrollo

## Requisitos

- Python 3.11+
- pip
- Acceso a Canvas LMS (token de administrador)
- App Registration en Azure AD con los permisos requeridos

## Instalación

```bash
git clone https://github.com/RoqueEsteche/claudecode-CanvasforTeams-.git
cd claudecode-CanvasforTeams-

pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus credenciales
```

## Estructura de un Endpoint

Todos los routers siguen el mismo patrón:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/modulo", tags=["Nombre del Módulo"])

class InputModel(BaseModel):
    campo: str

    @field_validator("campo")
    @classmethod
    def v_campo(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El campo es requerido")
        return v.strip()

@router.post("/accion", summary="Descripción corta")
async def accion(body: InputModel):
    """Docstring detallado del endpoint."""
    ...
```

## Agregar un Nuevo Tipo de Correo

1. Agregar función `_html_nuevo_tipo()` en `app/services/email_service.py`
2. Agregar el tipo al diccionario `program_labels` en `send_welcome_email()`
3. Agregar la rama `elif program_type == "nuevo_tipo"` para seleccionar el HTML
4. Agregar el valor a `_VALID_PROGRAMS` en `app/routers/ingreso.py`
5. Actualizar el dropdown en `app/templates/ingreso.html`

## Agregar una Nueva Página UI

1. Crear plantilla `app/templates/nueva_pagina.html`
2. Agregar ruta en `app/routers/web.py`:
   ```python
   @router.get("/ui/nueva-pagina", response_class=HTMLResponse)
   async def nueva_pagina(request: Request):
       user = _current_user(request)
       if not user:
           return RedirectResponse(url="/ui/login", status_code=302)
       return _r(request, "nueva_pagina.html")
   ```
3. Agregar enlace en `app/templates/base.html` si aplica al sidebar

## Convenciones de Código

### Nombres de Variables
- Modelos Pydantic: PascalCase con sufijo `In` para inputs, `Out` para outputs
- Funciones privadas: `_snake_case`
- Endpoints: `snake_case` sin prefijo

### Validaciones
- Siempre validar campos requeridos con `field_validator`
- Las validaciones de formato (email, cédula) van en el modelo
- Los errores de negocio van en el cuerpo de la función del endpoint

### Manejo de Errores
- Usar `HTTPException(status_code=..., detail=...)` para errores de cliente
- Usar `_err(exc)` para extraer el mensaje de cualquier excepción
- Nunca silenciar errores críticos (solo los 404 en verificación de cuentas)

### Respuestas
Los endpoints de creación devuelven siempre:
```python
{
    "student": "Nombre del usuario",
    "credentials": { ... },
    "canvas": { "status": "ok|exists|error", ... },
    "teams":  { "status": "ok|exists|error", ... },
    "email":  "sent|error: ..."
}
```

## Variables de Entorno Importantes

| Variable | Descripción | Requerida |
|---|---|---|
| `CANVAS_ACCESS_TOKEN` | Token de admin de Canvas | ✓ |
| `AZURE_TENANT_ID` | ID del tenant de Azure | ✓ |
| `AZURE_CLIENT_ID` | Client ID de la app registration | ✓ |
| `AZURE_CLIENT_SECRET` | Secret de la app registration | ✓ |
| `SMTP_FROM` | Buzón desde el que se envían correos | ✓ |
| `SMTP_FROM_NAME` | Nombre del remitente | — |
| `INSTITUTIONAL_DOMAIN` | Dominio institucional (ej: usil.edu.py) | ✓ |
| `SECRET_KEY` | Clave para firmar cookies de sesión | ✓ |
| `EMAIL_CC` | CC fijo para todos los correos (separado por coma) | — |

## Diagnóstico de Problemas Frecuentes

### Canvas devuelve 401
- El token de Canvas expiró. Generar nuevo en Canvas → Configuración → Tokens de acceso.

### Azure devuelve 403
- La app registration no tiene admin consent para los permisos `User.ReadWrite.All` o `Mail.Send`.
- Ir a Azure Portal → App Registrations → API Permissions → Grant admin consent.

### Correo no se envía
- Verificar que `SMTP_FROM` sea un buzón válido del tenant de Azure.
- El buzón debe tener habilitado el permiso `Mail.Send` en la app registration.
- Probar con `POST /ingreso/test-email?to_email=test@example.com`.

### Usuario creado en Canvas pero no en Teams
- Revisar la licencia disponible con `GET /diagnostics`.
- El SKU configurado (`AZURE_SKU_STUDENTS` / `AZURE_SKU_TEACHERS`) debe estar disponible en el tenant.

### PDFs no se adjuntan en diplomados
- Verificar que los archivos existan en `app/static/templates/`.
- Los nombres exactos esperados son:
  - `2° Acceso a la Plataforma Teams- Instructivo.pdf`
  - `3° Descargar grabacion en TEAMS - Instructivo.pdf`

## Tests Manuales Rápidos

```bash
# Verificar servidor activo
curl http://localhost:3000/ping

# Diagnóstico de conexiones
curl http://localhost:3000/diagnostics

# Previsualizar credenciales
curl -X POST http://localhost:3000/ingreso/preview \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Karen Gonzalez","cedula":"6868066","personal_email":"k@g.com","role":"student"}'

# Verificar cuenta existente
curl -X POST http://localhost:3000/ingreso/check-account \
  -H "Content-Type: application/json" \
  -d '{"cedula":"6868066","full_name":"Karen Gonzalez","platform":"both"}'

# Probar envío de correo
curl -X POST "http://localhost:3000/ingreso/test-email?to_email=tu@email.com&program_type=grado"
```
