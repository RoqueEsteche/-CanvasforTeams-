# API Reference – Gestión de Credenciales

Base URL: `http://localhost:3000`
Documentación interactiva: `http://localhost:3000/docs`

---

## Módulo: Nuevo Ingreso (`/ingreso`)

### POST `/ingreso/create`

Crea un usuario en Canvas y/o Teams y envía el correo de bienvenida.

**Request body:**
```json
{
  "full_name":      "Karen Gonzalez",
  "cedula":         "6868066",
  "personal_email": "karen@gmail.com",
  "role":           "student",
  "platform":       "both",
  "program_type":   "grado",
  "program_name":   "",
  "send_email":     true,
  "cc":             []
}
```

| Campo | Tipo | Requerido | Valores válidos |
|---|---|---|---|
| `full_name` | string | ✓ | ≥ 3 caracteres |
| `cedula` | string | ✓ | Solo números (con o sin guión) |
| `personal_email` | string | ✓ | Email válido |
| `role` | string | — | `student` \| `teacher` |
| `platform` | string | — | `canvas` \| `teams` \| `both` |
| `program_type` | string | — | `grado` \| `mba` \| `diplomado` |
| `program_name` | string | — | Nombre del programa (solo diplomados) |
| `send_email` | bool | — | `true` \| `false` |
| `cc` | array | — | Lista de emails adicionales en CC |

**Response:**
```json
{
  "student": "Karen Gonzalez",
  "role": "student",
  "credentials": {
    "email": "karen.gonzalez@usil.edu.py",
    "password": "6868066-Kg",
    "login_id": "karen.gonzalez@usil.edu.py"
  },
  "canvas": { "status": "ok", "id": 1234 },
  "teams":  { "status": "ok", "id": "uuid...", "license": "STANDARDWOFFPACK_STUDENT" },
  "email":  "sent"
}
```

Posibles valores de `status`: `ok` | `exists` | `error`

---

### POST `/ingreso/bulk`

Crea múltiples usuarios en paralelo.

**Request body:**
```json
{
  "students": [ { ... }, { ... } ]
}
```

**Response:**
```json
{
  "succeeded": [ { ... }, { ... } ],
  "failed":    [ { "student": "Nombre", "error": "..." } ]
}
```

---

### POST `/ingreso/resend-credentials`

Reenvía el correo de bienvenida con las credenciales calculadas. No modifica la cuenta en Canvas ni Teams.

**Request body:**
```json
{
  "full_name":      "Karen Gonzalez",
  "cedula":         "6868066",
  "personal_email": "karen@gmail.com",
  "platform":       "both",
  "program_type":   "grado",
  "program_name":   "",
  "cc":             []
}
```

**Response:**
```json
{
  "student":     "Karen Gonzalez",
  "cedula":      "6868066",
  "credentials": { "email": "karen.gonzalez@usil.edu.py", "password": "6868066-Kg" },
  "action":      "resend",
  "email":       "sent"
}
```

---

### POST `/ingreso/bulk-resend`

Reenvío masivo de credenciales.

**Request body:** igual que `/ingreso/bulk` pero con `ResendCredentialsIn`.

---

### POST `/ingreso/check-account`

Verifica si un usuario existe en Canvas y/o Teams antes de crearlo.

**Request body:**
```json
{
  "cedula":    "6868066",
  "full_name": "Karen Gonzalez",
  "platform":  "both"
}
```

> `full_name` es requerido si `platform` incluye Teams (se usa para generar el UPN).

**Response:**
```json
{
  "cedula":          "6868066",
  "full_name":       "Karen Gonzalez",
  "generated_email": "karen.gonzalez@usil.edu.py",
  "canvas": {
    "exists":   true,
    "found_by": "cedula",
    "canvas_id": 2384,
    "name":      "Karen Gonzalez",
    "login_id":  "karen.gonzalez@usil.edu.py"
  },
  "teams": {
    "exists": false
  }
}
```

---

### POST `/ingreso/bulk-check`

Verificación masiva con estadísticas.

**Response:**
```json
{
  "total":        5,
  "found_canvas": 3,
  "found_teams":  2,
  "results":      [ { ... } ]
}
```

---

### POST `/ingreso/preview`

Genera y muestra las credenciales que se asignarían, **sin crear nada**.

**Response:**
```json
{
  "full_name":          "Karen Gonzalez",
  "cedula":             "6868066",
  "personal_email":     "karen@gmail.com",
  "role":               "student",
  "login_id":           "karen.gonzalez@usil.edu.py",
  "institutional_email":"karen.gonzalez@usil.edu.py",
  "password":           "6868066-Kg"
}
```

---

### GET `/ingreso/template/crear`

Descarga una plantilla Excel (.xlsx) con el formato esperado para carga masiva.

**Columnas de la plantilla:**
| Col | Campo | Ejemplo |
|---|---|---|
| A | Nombre Completo | `Karen Gonzalez` |
| B | Cédula | `6868066` |
| C | Email Personal | `karen@gmail.com` |
| D | Rol | `student` \| `teacher` |
| E | Plataforma | `both` \| `canvas` \| `teams` |
| F | Programa | `grado` \| `mba` \| `diplomado` |
| G | Nombre del Programa | `Diplomado en SQL...` |

---

### POST `/ingreso/bulk-file`

Crea usuarios leyendo un archivo Excel subido mediante `multipart/form-data`.

```bash
curl -X POST http://localhost:3000/ingreso/bulk-file \
  -F "file=@usuarios.xlsx"
```

---

### POST `/ingreso/test-email`

Envía un correo de prueba para verificar la configuración.

**Query params:**
- `to_email` (requerido)
- `program_type` (opcional, default `grado`)
- `program_name` (opcional)

---

## Lógica de Generación de Credenciales

Dada una entrada `full_name + cedula + domain`:

| Input | Output |
|---|---|
| `Karen Gonzalez` + `6868066` | email: `karen.gonzalez@usil.edu.py` |
| | password: `6868066-Kg` |
| | login_id: `karen.gonzalez@usil.edu.py` |

**Fórmula:**
- `login_id = normalize(first).normalize(last)` (sin tildes, sin espacios, minúsculas)
- `password = cedula + "-" + initial_first.upper() + initial_last.lower()`

Caracteres especiales se normalizan: `Björn → bjorn`, `García → garcia`.

---

## Lógica de Verificación de Cuentas

### Canvas
1. Busca por `SIS user ID = cedula` (método primario — funciona aunque el nombre haya cambiado)
2. Fallback: busca por `login_id = email institucional generado`

### Teams / Azure AD
1. Busca por `userPrincipalName = email institucional generado`
2. Trata HTTP 404 como "no existe" (no como error)
3. Cualquier otro error (403, conexión) se propaga como error real

---

## Tipos de Programas y Correos

| `program_type` | Plantilla de correo | Asunto |
|---|---|---|
| `grado` | Plantilla GA Grado (Canvas + Teams) | `Credenciales de acceso – Grado` |
| `mba` | Plantilla MBA (USIL Business School) | `Credenciales de acceso – MBA – TI UBS` |
| `diplomado` | Plantilla UBS Diplomado (Teams) | `Credenciales de acceso – {nombre} – TI UBS` |

Los diplomados adjuntan automáticamente:
- `2° Acceso a la Plataforma Teams- Instructivo.pdf`
- `3° Descargar grabacion en TEAMS - Instructivo.pdf`

---

## Códigos de Error

| HTTP | Significado |
|---|---|
| 400 | Datos de entrada inválidos (validación Pydantic) |
| 401 | Token de Canvas o Azure expirado |
| 403 | Sin permisos suficientes en Canvas o Azure |
| 404 | Recurso no encontrado |
| 422 | Error de validación de campos (falta campo requerido o formato inválido) |
| 500 | Error interno del servidor |
