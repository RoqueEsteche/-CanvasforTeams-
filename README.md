# 📚 USIL Gestión TI - Guía de Uso

Sistema integral de gestión para Canvas LMS y Microsoft Teams con control de asistencias, usuarios, matrículas y auditoría completa.

---

## 🚀 Inicio Rápido

### Requisitos Previos
- Python 3.10+
- Credenciales de Canvas LMS
- Credenciales de Microsoft Teams/Azure AD

### 1. Instalación

```bash
# Clonar o navegar al directorio del proyecto
cd claudecode-CanvasforTeams-

# Instalar dependencias
pip install -r requirements.txt

# Crear archivo de configuración
cp .env.example .env
```

### 2. Configuración (.env)
Edita el archivo `.env` con tus credenciales:

```env
CANVAS_BASE_URL=https://usilparaguay.instructure.com
CANVAS_ACCESS_TOKEN=tu_token_de_canvas
CANVAS_ACCOUNT_ID=1

AZURE_TENANT_ID=tu_tenant_id
AZURE_CLIENT_ID=tu_client_id
AZURE_CLIENT_SECRET=tu_client_secret
INSTITUTIONAL_DOMAIN=tu_dominio
```

### 3. Ejecutar el Servidor

**Opción A: Script PowerShell (Recomendado en Windows)**
```powershell
.\run.ps1
```

**Opción B: Comando directo**
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload
```

El sistema estará disponible en: **http://localhost:3000** o **http://127.0.0.1:3000**

### Endpoints Útiles

- **Health Check:** http://localhost:3000/health
- **Documentación API:** http://localhost:3000/docs
- **Base de Datos:** `./app.db` (SQLite local)

---

## 📖 Guía Completa de Uso

### 🏠 Página Principal (Home)

**URL**: http://localhost:3000/ui/home

Es tu portal de entrada con acceso rápido a todas las funcionalidades:
- 📊 Reportes de Asistencia
- 👥 Usuarios Canvas
- 📚 Cursos
- 📋 Matrículas
- 🔐 Auditoría
- 📋 Historial de Trabajos

---

## 📊 Reportes de Asistencia

### ¿Para qué sirve?
Descargar matrices de asistencia de todos los cursos en Excel, sin descargar archivos manualmente del email de Canvas.

### Pasos para Usar

#### Opción 1: Descargar reportes existentes (Recomendado)

1. **Accede a la página de Asistencias**
   - URL: http://localhost:3000/ui/canvas/attendance
   - O desde Home → Asistencias

2. **Busca tu curso**
   - Usa la barra de búsqueda por nombre del curso o docente
   - Haz clic en "Refrescar" para actualizar la lista

3. **Descarga el Excel**
   - Haz clic en el botón "Descargar" del curso
   - Se descargará automáticamente con el formato Canvas

4. **Ver matriz completa (Opcional)**
   - Haz clic en "Ver" para ver la matriz de asistencias en pantalla
   - Muestra estudiantes y su asistencia por fecha

#### Opción 2: Actualizar con nuevos datos (Mensualmente)

**Cada mes, cuando tengas nuevos datos de Canvas:**

1. **Descarga CSV de Canvas**
   - Entra a Canvas → Attendance Tool
   - Para cada curso, descarga el CSV de asistencia
   - Guarda en: `Carpeta de plantillas/` con nombre `{course_id}.csv`
   - Ejemplo: `1723.csv` para el curso 1723

2. **Actualiza en el sistema**
   - Entra a http://localhost:3000/ui/canvas/attendance
   - Haz clic en "Refrescar"
   - El sistema detecta automáticamente los nuevos archivos

3. **Descarga los reportes**
   - Los reportes ahora incluyen datos del mes actual
   - Distribuye a docentes o directivos

---

## 👥 Gestión de Usuarios Canvas

### ¿Para qué sirve?
Crear, editar o eliminar usuarios en Canvas de forma masiva o individual.

### Pasos para Usar

1. **Accede a Usuarios Canvas**
   - URL: http://localhost:3000/ui/canvas/users
   - O desde Home → Usuarios

2. **Crear usuarios individuales**
   - Haz clic en "Crear usuario"
   - Completa los datos (nombre, email, etc.)
   - Haz clic en "Guardar"

3. **Crear usuarios masivos (Excel)**
   - Prepara un archivo Excel con columnas:
     ```
     nombre, email, login, tipo
     Juan Pérez, juan@usil.edu.py, juan.perez, student
     María García, maria@usil.edu.py, maria.garcia, instructor
     ```
   - Haz clic en "Cargar Excel"
   - Selecciona tu archivo
   - El sistema mostrará un reporte de cuáles se crearon y cuáles fallaron

4. **Ver historial de creación**
   - Entra a http://localhost:3000/ui/jobs
   - Filtrar por "Crear Usuarios"
   - Verás qué se hizo, cuántos éxito, cuántos errores

---

## 📚 Gestión de Cursos

### ¿Para qué sirve?
Sincronizar y gestionar cursos entre Canvas y Teams.

### Pasos para Usar

1. **Accede a Cursos**
   - URL: http://localhost:3000/ui/canvas/courses
   - O desde Home → Cursos

2. **Listar cursos**
   - La página muestra automáticamente todos los cursos disponibles
   - Usa búsqueda para encontrar un curso específico

3. **Ver detalles**
   - Haz clic en un curso para ver:
     - Nombre y descripción
     - Docente asignado
     - Cantidad de estudiantes
     - Información de sincronización

4. **Actualizar información**
   - Haz clic en "Editar"
   - Modifica los campos necesarios
   - Haz clic en "Guardar"

---

## 📋 Gestión de Matrículas (Enrollments)

### ¿Para qué sirve?
Asignar estudiantes a cursos de forma masiva o individual.

### Pasos para Usar

1. **Accede a Matrículas**
   - URL: http://localhost:3000/ui/canvas/enrollments
   - O desde Home → Matrículas

2. **Matrícula individual**
   - Selecciona un curso
   - Selecciona estudiante(s)
   - Haz clic en "Matricular"
   - El sistema confirmará cuántos se matricularon

3. **Matrícula masiva (Excel)**
   - Prepara un archivo Excel:
     ```
     course_id, student_id, tipo_rol
     1723, 2294, student
     1723, 2295, student
     1724, 2296, instructor
     ```
   - Haz clic en "Cargar Matrículas"
   - Carga el archivo
   - Verifica el reporte de resultados

4. **Consultar historial**
   - Entra a http://localhost:3000/ui/jobs
   - Filtrar por "Matrículas"
   - Ver qué estudiantes se asignaron correctamente y cuáles fallaron

---

## 📋 Historial de Trabajos (Jobs) - ⭐ Funcionalidad Principal

### ¿Para qué sirve?
Ver TODAS las operaciones realizadas (crear usuarios, matrículas, etc.) con detalles completos de qué funcionó y qué no.

**Los datos PERSISTEN aunque cierres la página o reinicies el servidor.**

### Pasos para Usar

1. **Accede al Historial**
   - URL: http://localhost:3000/ui/jobs
   - O desde Home → Historial de Trabajos

2. **Ver trabajos de hoy**
   - Haz clic en "Hoy"
   - Verás todas las operaciones del día

3. **Ver trabajos por período**
   - Haz clic en "Esta semana" o "Este mes"
   - O selecciona fechas personalizadas

4. **Filtrar por usuario**
   - Completa "Usuario" con el nombre
   - Haz clic en "Buscar"
   - Ver qué hizo ese usuario específico

5. **Filtrar por tipo de trabajo**
   - Selecciona en "Tipo de trabajo"
   - Opciones: Crear usuarios, Matrículas, Cursos, etc.

6. **Interpretar los resultados**
   - **Estado Completado**: Todo fue exitoso ✓
   - **Con Errores**: Algunos éxito, algunos fallidos ⚠
   - **Fallido**: La operación completa falló ✗
   - **Pendiente**: Aún se está procesando ⏳

### Información que se Guarda por Operación
- ✓ Fecha y hora exacta de inicio y fin
- ✓ Usuario que realizó la acción
- ✓ Tipo de trabajo (qué se intentó)
- ✓ Operación específica (detalles)
- ✓ Estado: Pendiente, Procesando, Completado, Con Errores, Fallido
- ✓ Cantidad de éxitos
- ✓ Cantidad de errores
- ✓ Mensaje de error detallado (si aplica)

### Ejemplo: Verificar si 100 usuarios se crearon correctamente

1. Entra a Historial de Trabajos
2. Filtrar por "Crear Usuarios (Masivo)"
3. Ver la fecha cuando se hizo
4. Verás:
   - Cantidad de éxitos
   - Cantidad de errores
   - Mensaje de error (si aplica)
5. Si hay errores, puedes reintentar solo los que fallaron

---

## 🔒 Auditoría

### ¿Para qué sirve?
Ver TODAS las solicitudes HTTP realizadas en el sistema, con información de quién las hizo, cuándo y desde dónde.

### Pasos para Usar

1. **Accede a Auditoría**
   - URL: http://localhost:3000/ui/audit
   - O desde Home → Auditoría

2. **Ver registro completo**
   - La página muestra automáticamente las últimas solicitudes
   - Navega con "Anterior/Siguiente" para ver más

3. **Filtrar por usuario**
   - Completa "Usuario"
   - Verás todas las acciones que ese usuario realizó

4. **Ver estadísticas**
   - En la parte superior se muestran:
     - Total de solicitudes
     - Usuarios únicos
     - Endpoints accedidos
     - Solicitudes por método (GET, POST, etc.)

---

## 💾 Bases de Datos

El sistema crea automáticamente 3 bases de datos en `data/`:

1. **app.db** - Datos principales (cursos, usuarios, matrículas, etc.)
2. **audit.db** - Log de todas las solicitudes HTTP
3. **jobs.db** - Historial de operaciones (crear usuarios, matrículas, etc.)

Todos los datos se **persisten automáticamente** aunque cierres la página o reinicies el servidor.

---

## ⚠️ Solución de Problemas

### El servidor no inicia
```bash
# Verifica que las credenciales en .env sean correctas
# Verifica que Canvas y Azure estén disponibles
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

### Los reportes de asistencia están vacíos
- **Solución**: Descarga el CSV del course desde Canvas y guárdalo en `Carpeta de plantillas/`
- Los datos se actualizan automáticamente cuando detecta archivos nuevos

### No veo los usuarios creados en Canvas
- **Solución**: Ve al Historial de Trabajos para ver si hubo errores
- Verifica que el token de Canvas tenga permisos de administrador

### ¿Por qué falló una operación?
- **Solución**: Ve a http://localhost:3000/ui/jobs
- Filtra por usuario y tipo de trabajo
- Lee el mensaje de error detallado
- Soluciona el problema (ej: datos incorrectos, usuario duplicado)
- Reintenta la operación

---

## 📊 Flujo Típico de Trabajo

### Inicio de Semestre
1. **Crear cursos** → Cursos
2. **Crear usuarios** → Usuarios (cargar Excel)
3. **Asignar estudiantes** → Matrículas (cargar Excel)
4. **Verificar** → Historial de Trabajos (ver cuántos éxito/error)

### Monitoreo Semanal
1. **Descargar asistencias** → Reportes de Asistencia
2. **Verificar trabajos pendientes** → Historial de Trabajos
3. **Auditar cambios** → Auditoría (opcional)

### Fin de Mes
1. **Descargar reportes finales** → Reportes de Asistencia
2. **Ver resumen de todo lo hecho** → Historial de Trabajos (filtrar por mes)
3. **Exportar para directivos** → Descargar Excels

---

## 🆘 Contacto y Soporte

- **API Documentation**: http://localhost:3000/docs
- **Logs**: Revisa la consola donde ejecutaste el servidor
- **Historial de Trabajos**: http://localhost:3000/ui/jobs (para ver qué pasó)

---

## 📝 Notas Importantes

✅ **Qué SÍ puedes hacer**:
- Crear usuarios sin límite
- Asignar estudiantes a cursos
- Descargar reportes de asistencia
- Ver historial completo de operaciones
- Auditar quién hizo qué y cuándo
- **Cerrar la página sin perder los datos** (se guardan en BD)

❌ **Qué NO puedes hacer directamente**:
- Cambiar contraseñas (hacerlo en Canvas/Azure)
- Eliminar usuarios (solo en Canvas)
- Modificar calificaciones (solo en Canvas)

---

## 🎓 Ejemplos Prácticos

### Crear 50 estudiantes nuevos
1. Prepara Excel con 50 filas (nombre, email, login)
2. Entra a http://localhost:3000/ui/canvas/users
3. Haz clic en "Cargar Excel"
4. Carga el archivo
5. Sistema procesa automáticamente
6. Ver reporte: 45 éxito, 5 fallidos (duplicados/emails inválidos)
7. Corrige los 5 y reintentar

### Descargar asistencias de fin de mes
1. Descarga CSVs de Canvas para cada curso
2. Guarda en `Carpeta de plantillas/` (ej: 1723.csv)
3. Entra a http://localhost:3000/ui/canvas/attendance
4. Haz clic en "Refrescar"
5. Haz clic en "Descargar" de cada curso
6. Envía Excels a docentes

### Verificar qué salió mal en una matrícula masiva
1. Entra a http://localhost:3000/ui/jobs
2. Filtrar por "Matrículas (Masivo)" y fecha
3. Ver: 450 éxito, 10 errores
4. Lee el mensaje de error para cada uno
5. Corrige los datos y reintenta

---

## Stack Técnico (Para Administradores)

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.12 + FastAPI |
| Servidor | Uvicorn (ASGI) |
| APIs externas | Canvas LMS REST API v1, Microsoft Graph API |
| Base de Datos | SQLite (3 BD: app, audit, jobs) |
| Frontend | Jinja2 + Bootstrap 5.3 |
| Caché | In-memory TTL con persistencia en disco |

---

**¡Listo! Ahora puedes usar el sistema completamente.** Si tienes dudas, consulta el Historial de Trabajos (jobs) para ver exactamente qué pasó en cada operación. 🚀
