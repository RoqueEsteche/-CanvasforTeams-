"""Excel import endpoints + template downloads.

All templates use Spanish headers; upload endpoints accept both Spanish
and English column names via the _get() helper that tries multiple keys.
"""
import asyncio
import io
import logging
import re
import unicodedata
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.models.canvas import BulkResult
from app.services import canvas_client as canvas
from app.services import teams_client as graph
from app.services.credential_generator import generate_credentials
from app.services.email_service import send_welcome_email, get_program_attachments
from app.services.teams_client import create_team_via_group

def _err(exc: Exception) -> str:
    return getattr(exc, "detail", str(exc))

router = APIRouter(tags=["Excel Import/Export"])
_ACCOUNT = settings.canvas_account_id
logger = logging.getLogger(__name__)

# Límites de seguridad
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 10000
ALLOWED_EXCEL_TYPES = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/x-xlsx"
}


# ── Excel read/normalize helpers ─────────────────────────────────────────────

def _norm(s: str) -> str:
    """Normalize a header string: lowercase, strip accents, spaces→underscore."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _validate_file(file: UploadFile) -> None:
    """Validar tipo y tamaño del archivo."""
    # Validar tipo MIME
    if file.content_type not in ALLOWED_EXCEL_TYPES:
        logger.warning(f"Tipo MIME no permitido: {file.content_type}")
        raise HTTPException(
            status_code=400,
            detail=f"Solo archivos Excel permitidos. Recibido: {file.content_type}"
        )

    # Validar extensión
    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        logger.warning(f"Extensión no permitida: {filename}")
        raise HTTPException(
            status_code=400,
            detail="Solo archivos .xlsx o .xls permitidos"
        )


def _read_excel(file: UploadFile) -> list[dict]:
    """Leer y normalizar archivo Excel con validaciones de seguridad."""
    _validate_file(file)

    contents = file.file.read()

    # Validar tamaño
    if len(contents) > MAX_FILE_SIZE:
        logger.warning(f"Archivo excede límite de {MAX_FILE_SIZE} bytes")
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande. Máximo: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    try:
        df = pd.read_excel(io.BytesIO(contents), dtype=str)
    except Exception as e:
        logger.error(f"Error leyendo Excel: {e}")
        raise HTTPException(status_code=400, detail="Archivo Excel inválido")

    # Validar número de filas
    if len(df) > MAX_ROWS:
        logger.warning(f"Archivo excede {MAX_ROWS} filas")
        raise HTTPException(
            status_code=413,
            detail=f"Máximo {MAX_ROWS} filas permitidas"
        )

    df = df.where(pd.notnull(df), None)
    # Normalize column headers
    df.columns = [_norm(str(c)) for c in df.columns]
    return df.to_dict(orient="records")


def _get(row: dict, *keys) -> Any:
    """Try multiple key variants (Spanish + English) and return the first non-empty value."""
    for k in keys:
        v = row.get(k) or row.get(_norm(k))
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


# ── Template generation ───────────────────────────────────────────────────────

_HEADER_FILL  = PatternFill("solid", fgColor="1A2035")
_EXAMPLE_FILL = PatternFill("solid", fgColor="EEF2FF")
_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=10)
_EXAMPLE_FONT = Font(italic=True, color="555555", size=9)
_BORDER_SIDE  = Side(style="thin", color="C5C5C5")
_CELL_BORDER  = Border(left=_BORDER_SIDE, right=_BORDER_SIDE,
                       bottom=_BORDER_SIDE, top=_BORDER_SIDE)


def _build_template(
    headers: list[str],
    examples: list[list],
    col_widths: list[int] | None = None,
) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active

    # Header row
    ws.append(headers)
    for i, cell in enumerate(ws[1], 1):
        cell.fill   = _HEADER_FILL
        cell.font   = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = _CELL_BORDER
        ws.column_dimensions[get_column_letter(i)].width = (
            col_widths[i - 1] if col_widths and i <= len(col_widths) else 22
        )
    ws.row_dimensions[1].height = 30

    # Example rows
    for row in examples:
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.fill   = _EXAMPLE_FILL
            cell.font   = _EXAMPLE_FONT
            cell.border = _CELL_BORDER

    ws.freeze_panes = "A2"
    return wb


def _wb_response(wb: openpyxl.Workbook, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _excel_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Simple response for exported data (no special formatting)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for r in rows:
            ws.append(list(r.values()))
    return _wb_response(wb, filename)


# ═══════════════════════════════════════════════════════════════════════════════
# Canvas – Usuarios
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/canvas-users", summary="Descargar plantilla usuarios Canvas")
async def template_canvas_users():
    wb = _build_template(
        headers=["Nombre Completo *", "Email *", "Login / Usuario *", "Contraseña",
                 "ID SIS (cédula)"],
        examples=[
            ["Karen Gonzalez", "karen.gonzalez@usil.edu.py", "karen.gonzalez",
             "6868066-Kg", "6868066"],
            ["Juan Perez", "juan.perez@usil.edu.py", "juan.perez",
             "1234567-Jp", "1234567"],
        ],
        col_widths=[28, 32, 22, 18, 18],
    )
    return _wb_response(wb, "plantilla_canvas_usuarios.xlsx")


@router.post("/excel/canvas/users", summary="Importar usuarios Canvas desde Excel")
async def import_canvas_users(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _create(row: dict):
        try:
            name     = _get(row, "nombre_completo", "nombre", "name")
            email    = _get(row, "email", "correo", "email_institucional")
            login_id = _get(row, "login_usuario", "login", "login_id")
            password = _get(row, "contrasena", "password")
            sis_id   = _get(row, "id_sis_cedula", "id_sis", "sis_user_id")

            if not name or not email or not login_id:
                raise ValueError("Nombre Completo, Email y Login son obligatorios")

            payload = {
                "user": {"name": name, "short_name": name},
                "pseudonym": {"unique_id": login_id, "send_confirmation": False},
                "communication_channel": {
                    "type": "email", "address": email, "skip_confirmation": True
                },
            }
            if password:
                payload["pseudonym"]["password"] = password
            if sis_id:
                payload["pseudonym"]["sis_user_id"] = sis_id

            data = await canvas.post(f"/accounts/{_ACCOUNT}/users", payload)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    await asyncio.gather(*[_create(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Canvas – Cursos
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/canvas-courses", summary="Descargar plantilla cursos Canvas")
async def template_canvas_courses():
    wb = _build_template(
        headers=["Nombre del Curso *", "Código del Curso *", "ID SIS Curso",
                 "Fecha Inicio (YYYY-MM-DD)", "Fecha Fin (YYYY-MM-DD)"],
        examples=[
            ["Matemáticas I – 2025", "MAT-I-2025", "MAT-I-2025",
             "2025-03-01", "2025-07-31"],
            ["Comunicación Oral – 2025", "COM-ORAL-2025", "COM-ORAL-2025",
             "2025-03-01", "2025-07-31"],
        ],
        col_widths=[32, 22, 18, 26, 26],
    )
    return _wb_response(wb, "plantilla_canvas_cursos.xlsx")


@router.post("/excel/canvas/courses", summary="Importar cursos Canvas desde Excel")
async def import_canvas_courses(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _create(row: dict):
        try:
            name    = _get(row, "nombre_del_curso", "nombre", "name")
            code    = _get(row, "codigo_del_curso", "codigo", "course_code")
            sis_id  = _get(row, "id_sis_curso", "sis_course_id")
            start   = _get(row, "fecha_inicio_yyyy_mm_dd", "fecha_inicio", "start_at")
            end     = _get(row, "fecha_fin_yyyy_mm_dd", "fecha_fin", "end_at")

            if not name or not code:
                raise ValueError("Nombre del Curso y Código son obligatorios")

            payload = {"course": {
                "name": name, "course_code": code,
                "sis_course_id": sis_id or None,
                "start_at": start or None,
                "end_at": end or None,
            }}
            data = await canvas.post(f"/accounts/{_ACCOUNT}/courses", payload)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    await asyncio.gather(*[_create(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Canvas – Matrículas
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/canvas-enrollments",
            summary="Descargar plantilla matrículas Canvas")
async def template_canvas_enrollments():
    wb = _build_template(
        headers=["ID Curso *", "ID Usuario *",
                 "Rol * (StudentEnrollment / TeacherEnrollment / TaEnrollment)",
                 "Estado (active / invited)", "Notificar (true / false)"],
        examples=[
            ["103", "958", "StudentEnrollment", "active", "false"],
            ["103", "1355", "TeacherEnrollment", "active", "false"],
        ],
        col_widths=[14, 14, 44, 24, 24],
    )
    return _wb_response(wb, "plantilla_canvas_matriculas.xlsx")


@router.post("/excel/canvas/enrollments",
             summary="Matricular usuarios Canvas desde Excel")
async def import_canvas_enrollments(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _enroll(row: dict):
        try:
            course_id = _get(row, "id_curso", "course_id")
            user_id   = _get(row, "id_usuario", "user_id")
            rol       = _get(row, "rol", "type") or "StudentEnrollment"
            estado    = _get(row, "estado", "enrollment_state") or "invited"
            notif_raw = _get(row, "notificar", "notify") or ""

            if not course_id or not user_id:
                raise ValueError("ID Curso e ID Usuario son obligatorios")

            payload = {"enrollment": {
                "user_id": str(user_id),
                "type": rol,
                "enrollment_state": estado,
                "notify": notif_raw.lower() in ("1", "true", "si", "yes"),
            }}
            data = await canvas.post(f"/courses/{course_id}/enrollments", payload)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    await asyncio.gather(*[_enroll(r) for r in rows])
    return result


@router.post("/excel/canvas/unenrollments",
             summary="Desmatricular usuarios Canvas desde Excel")
async def import_canvas_unenrollments(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _unenroll(row: dict):
        try:
            course_id     = _get(row, "id_curso", "course_id")
            enrollment_id = _get(row, "id_matricula", "enrollment_id")
            task          = _get(row, "accion", "task") or "conclude"

            if not course_id or not enrollment_id:
                raise ValueError("ID Curso e ID Matrícula son obligatorios")

            data = await canvas.delete(
                f"/courses/{course_id}/enrollments/{enrollment_id}",
                {"task": task},
            )
            result.succeeded.append({"enrollment_id": enrollment_id, **data})
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    await asyncio.gather(*[_unenroll(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Teams – Usuarios Azure AD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/teams-users",
            summary="Descargar plantilla usuarios Azure AD")
async def template_teams_users():
    wb = _build_template(
        headers=["Nombre Completo *", "Usuario Principal (UPN) *",
                 "Alias de Correo *", "Contraseña *",
                 "País * (PY / PE / US)", "Rol * (student / teacher)",
                 "Nombre", "Apellido", "Departamento", "Cargo"],
        examples=[
            ["Karen Gonzalez", "karen.gonzalez@usil.edu.py",
             "karen_gonzalez", "6868066-Kg", "PY", "student",
             "Karen", "Gonzalez", "Sistemas", "Alumno"],
            ["Prof. Juan Perez", "juan.perez@usil.edu.py",
             "juan_perez", "1234567-Jp", "PY", "teacher",
             "Juan", "Perez", "Docentes", "Profesor"],
        ],
        col_widths=[28, 32, 22, 18, 16, 24, 18, 18, 20, 20],
    )
    return _wb_response(wb, "plantilla_teams_usuarios.xlsx")


@router.post("/excel/teams/users",
             summary="Importar usuarios Azure AD desde Excel")
async def import_teams_users(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _create(row: dict):
        try:
            display = _get(row, "nombre_completo", "nombre", "display_name")
            upn     = _get(row, "usuario_principal_upn", "usuario_principal",
                           "user_principal_name")
            alias   = _get(row, "alias_de_correo", "alias", "mail_nickname")
            pwd     = _get(row, "contrasena", "password")
            country = _get(row, "pais_py_pe_us", "pais", "usage_location") or settings.usage_location
            role    = (_get(row, "rol_student_teacher", "rol", "role") or "student").lower()
            fname   = _get(row, "nombre", "given_name")
            lname   = _get(row, "apellido", "surname")
            dept    = _get(row, "departamento", "department")
            title   = _get(row, "cargo", "job_title")

            missing = [f for f, v in [("Nombre Completo", display),
                                       ("Usuario Principal", upn),
                                       ("Alias de Correo", alias),
                                       ("Contraseña", pwd)] if not v]
            if missing:
                raise ValueError(f"Campos obligatorios faltantes: {', '.join(missing)}")

            if role not in ("student", "teacher"):
                role = "student"

            payload: dict[str, Any] = {
                "displayName": display,
                "userPrincipalName": upn,
                "mailNickname": alias,
                "usageLocation": country,
                "accountEnabled": True,
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": True,
                    "password": pwd,
                },
            }
            for src, dst in [(fname, "givenName"), (lname, "surname"),
                             (dept, "department"), (title, "jobTitle")]:
                if src:
                    payload[dst] = src

            data = await graph.post("/users", payload)
            sku = settings.azure_sku_teachers if role == "teacher" else settings.azure_sku_students
            await graph.assign_license(data["id"], sku)
            result.succeeded.append({**data, "role": role})
        except Exception as exc:
            result.failed.append({
                "input": {k: v for k, v in row.items() if "contrasena" not in k and "password" not in k},
                "error": str(exc),
            })

    await asyncio.gather(*[_create(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Teams – Miembros
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/teams-members",
            summary="Descargar plantilla miembros Teams")
async def template_teams_members():
    wb = _build_template(
        headers=["ID Equipo *", "ID Usuario (Azure AD) *",
                 "Rol * (member / owner)"],
        examples=[
            ["d5e9a352-4d7e-4e61-b965-2637856568e0",
             "46ad7584-b4f4-44ea-aa8e-2a77127fdb82", "member"],
            ["d5e9a352-4d7e-4e61-b965-2637856568e0",
             "7f3c9b21-a1d2-4e33-b421-998765432100", "owner"],
        ],
        col_widths=[40, 40, 20],
    )
    return _wb_response(wb, "plantilla_teams_miembros.xlsx")


@router.post("/excel/teams/members",
             summary="Añadir miembros a Teams desde Excel")
async def import_teams_members(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    async def _add(row: dict):
        try:
            team_id = _get(row, "id_equipo", "team_id")
            user_id = _get(row, "id_usuario_azure_ad", "id_usuario", "user_id")
            role    = _get(row, "rol_member_owner", "rol", "role") or "member"

            if not team_id or not user_id:
                raise ValueError("ID Equipo e ID Usuario son obligatorios")

            payload = {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"] if role.lower() == "owner" else [],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
            }
            data = await graph.post(f"/teams/{team_id}/members", payload)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    await asyncio.gather(*[_add(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Nuevo Ingreso
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/ingreso",
            summary="Descargar plantilla Nuevo Ingreso")
async def template_ingreso():
    wb = _build_template(
        headers=["Nombre Completo *", "Cédula *", "Correo Personal *",
                 "Rol * (student / teacher)",
                 "Tipo Programa * (grado / mba / diplomado)",
                 "Nombre del Programa",
                 "Plataforma (both / canvas / teams)",
                 "Enviar Correo (true / false)",
                 "CC (correos separados por coma)"],
        examples=[
            ["Karen Gonzalez", "6868066", "karen@gmail.com",
             "student", "grado", "", "both", "true", ""],
            ["Juan Perez", "1234567", "juan@gmail.com",
             "student", "mba", "Master in Business Administration", "both", "true",
             "director@usil.edu.py"],
            ["Prof. Maria Lopez", "9999999", "maria@gmail.com",
             "teacher", "diplomado", "Diplomado en Gestión Empresarial",
             "teams", "true", ""],
        ],
        col_widths=[28, 14, 28, 26, 36, 36, 30, 26, 36],
    )
    return _wb_response(wb, "plantilla_nuevo_ingreso.xlsx")


@router.post("/excel/ingreso",
             summary="Crear cuentas conjuntas desde lista de alumnos")
async def import_ingreso(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()
    _ACCOUNT_LOCAL = settings.canvas_account_id

    async def _process(row: dict):
        try:
            full_name = _get(row, "nombre_completo", "nombre", "full_name")
            cedula    = _get(row, "cedula", "ci")
            p_email   = _get(row, "correo_personal", "personal_email")

            if not full_name or not cedula:
                raise ValueError("Nombre Completo y Cédula son obligatorios")

            creds        = generate_credentials(full_name, cedula, settings.institutional_domain)
            role         = (_get(row, "rol_student_teacher", "rol", "role") or "student").lower()
            platform     = (_get(row, "plataforma_both_canvas_teams", "plataforma", "platform") or "both").lower()
            program_type = (_get(row, "tipo_programa_grado_mba_diplomado", "tipo_programa", "program_type") or "grado").lower()
            program_name = _get(row, "nombre_del_programa", "nombre_programa", "program_name") or ""
            do_email     = (_get(row, "enviar_correo_true_false", "enviar_correo", "send_email") or "true").lower() not in ("false", "0", "no")
            cc_raw       = _get(row, "cc_correos_separados_por_coma", "cc") or ""
            extra_cc     = [e.strip() for e in cc_raw.split(",") if e.strip()]
            # login = email institucional para ambas plataformas (alumnos y docentes)
            # SIS   = cédula siempre (identificador institucional)
            login_id = creds["email"]

            entry: dict[str, Any] = {
                "student": full_name, "role": role,
                "credentials": {**creds, "login_id": login_id},
            }

            if platform in ("canvas", "both"):
                try:
                    cu = await canvas.post(f"/accounts/{_ACCOUNT_LOCAL}/users", {
                        "user": {"name": creds["full_name"]},
                        "pseudonym": {
                            "unique_id": login_id, "sis_user_id": cedula,
                            "password": creds["password"], "send_confirmation": False,
                        },
                        "communication_channel": {
                            "type": "email", "address": creds["email"],
                            "skip_confirmation": True,
                        },
                    })
                    entry["canvas"] = {"status": "ok", "id": cu.get("id")}
                except Exception as exc:
                    entry["canvas"] = {"status": "error", "error": exc.detail if isinstance(exc, HTTPException) else str(exc)}

            if platform in ("teams", "both"):
                parts = full_name.strip().split()
                sku = settings.azure_sku_teachers if role == "teacher" else settings.azure_sku_students
                try:
                    au = await graph.post("/users", {
                        "displayName": creds["full_name"],
                        "givenName": parts[0],
                        "surname": " ".join(parts[1:]) if len(parts) > 1 else "",
                        "userPrincipalName": creds["email"],
                        "mailNickname": creds["login_id"].replace(".", "_"),
                        "usageLocation": settings.usage_location,
                        "accountEnabled": True,
                        "passwordProfile": {
                            "forceChangePasswordNextSignIn": True,
                            "password": creds["password"],
                        },
                    })
                    await graph.assign_license(au["id"], sku)
                    entry["teams"] = {"status": "ok", "id": au.get("id")}
                except Exception as exc:
                    entry["teams"] = {"status": "error", "error": exc.detail if isinstance(exc, HTTPException) else str(exc)}

            if do_email and p_email:
                try:
                    await send_welcome_email(
                        to_email=p_email, 
                        full_name=creds["full_name"], 
                        institutional_email=creds["email"],
                        login_id=login_id, 
                        password=creds["password"], 
                        platform=platform,
                        program_type=program_type, 
                        program_name=program_name,
                        extra_cc=extra_cc or None,
                        attachments=get_program_attachments(program_type)
                    )
                    entry["email"] = "sent"
                except Exception as exc:
                    entry["email"] = f"error: {exc}"

            result.succeeded.append(entry)
        except Exception as exc:
            result.failed.append({
                "input": {k: v for k, v in row.items() if "cedula" not in k},
                "error": str(exc),
            })

    await asyncio.gather(*[_process(r) for r in rows])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Sync Canvas → Teams
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/excel/template/sync",
            summary="Descargar plantilla sincronización Canvas→Teams")
async def template_sync():
    wb = _build_template(
        headers=["ID Curso Canvas *", "ID Owner (Azure AD) *",
                 "Visibilidad (Private / Public)",
                 "Alias de Correo del Equipo *"],
        examples=[
            ["103", "46ad7584-b4f4-44ea-aa8e-2a77127fdb82",
             "Private", "comunicacion-oral-2025"],
            ["104", "46ad7584-b4f4-44ea-aa8e-2a77127fdb82",
             "Private", "matematicas-i-2025"],
        ],
        col_widths=[22, 40, 28, 32],
    )
    return _wb_response(wb, "plantilla_sync_canvas_teams.xlsx")


@router.post("/excel/sync/canvas-teams",
             summary="Sincronización conjunta Canvas→Teams desde Excel")
async def bulk_sync_canvas_teams(file: UploadFile = File(...)) -> BulkResult:
    rows = _read_excel(file)
    result = BulkResult()

    for row in rows:
        try:
            course_id   = _get(row, "id_curso_canvas", "canvas_course_id")
            owner_id    = _get(row, "id_owner_azure_ad", "owner_id")
            visibility  = _get(row, "visibilidad_private_public", "visibilidad", "visibility") or "Private"
            mail_nick   = _get(row, "alias_de_correo_del_equipo", "alias", "mail_nickname")

            if not course_id or not owner_id:
                raise ValueError("ID Curso Canvas e ID Owner son obligatorios")
            if not mail_nick:
                raise ValueError("Alias de Correo del Equipo es obligatorio")

            course = await canvas.get(f"/courses/{course_id}")
            team = await create_team_via_group(
                display_name=course.get("name", f"Curso {course_id}"),
                mail_nickname=mail_nick,
                description=course.get("public_description") or course.get("name", ""),
                visibility=visibility,
                owner_ids=[owner_id],
            )
            result.succeeded.append({
                "canvas_course_id": course_id,
                "team_id": team.get("id", ""),
                "team_name": team.get("displayName", ""),
            })
        except Exception as exc:
            result.failed.append({"input": row, "error": _err(exc)})

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Sync – members endpoint (used by sync.html)
# ═══════════════════════════════════════════════════════════════════════════════

class SyncMembersRequest(BaseModel):
    canvas_course_id: str
    teams_team_id: str


@router.post("/sync/canvas-to-teams",
             summary="Añadir miembros del curso Canvas al Team")
async def sync_canvas_to_teams(body: SyncMembersRequest) -> BulkResult:
    result = BulkResult()
    try:
        enrollments = await canvas.paginate(
            f"/courses/{body.canvas_course_id}/enrollments",
            {"state[]": ["active"], "per_page": 100},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async def _add(enrollment: dict):
        email = (enrollment.get("user") or {}).get("email") or \
                enrollment.get("user", {}).get("login_id")
        if not email:
            result.failed.append({
                "enrollment_id": enrollment.get("id"), "error": "Sin email"
            })
            return
        try:
            data = await graph.post(
                f"/teams/{body.teams_team_id}/members",
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": [],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{email}')",
                },
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"enrollment_id": enrollment.get("id"), "error": _err(exc)})

    await asyncio.gather(*[_add(e) for e in enrollments])
    return result
@router.get("/template/unified-creation", summary="Descargar plantilla Excel para creación conjunta")
async def template_unified_creation():
    import io
    import openpyxl
    from fastapi.responses import StreamingResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cursos y Equipos"

    headers = [
        "Nombre del Curso", "Código del Curso", "Identificador del Propietario"
    ]
    ws.append(headers)
    for col in ws.iter_cols(min_row=1, max_row=1):
        for cell in col:
            cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            cell.fill = openpyxl.styles.PatternFill(start_color="5A67D8", end_color="5A67D8", fill_type="solid")
            cell.alignment = openpyxl.styles.Alignment(horizontal="center")

    ws.append(["Curso de Prueba", "PRB-101", "profesor@usil.edu.py"])
    for col_letter in ["A", "B", "C"]:
        ws.column_dimensions[col_letter].width = 25

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_creacion_unificada.xlsx"},
    )

@router.get("/template/unified-enrollment", summary="Descargar plantilla Excel para matriculación conjunta")
async def template_unified_enrollment():
    import io
    import openpyxl
    from fastapi.responses import StreamingResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Matriculaciones"

    headers = [
        "Identificador de Usuario", "ID Curso Canvas", "ID Equipo Teams", "Rol"
    ]
    ws.append(headers)
    for col in ws.iter_cols(min_row=1, max_row=1):
        for cell in col:
            cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            cell.fill = openpyxl.styles.PatternFill(start_color="5A67D8", end_color="5A67D8", fill_type="solid")
            cell.alignment = openpyxl.styles.Alignment(horizontal="center")

    ws.append(["1234567", "10203", "1a2b3c-4d5e", "student"])
    for col_letter in ["A", "B", "C", "D"]:
        ws.column_dimensions[col_letter].width = 25

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_matriculacion_unificada.xlsx"},
    )

# ═══════════════════════════════════════════════════════════════════════════════
# Diplomados (Lectura y Escritura de Planilla Original)
# ═══════════════════════════════════════════════════════════════════════════════

class DiplomadosUrlRequest(BaseModel):
    url: str
    sheet_name: str


class UrlOnlyRequest(BaseModel):
    url: str
class PreviewResponse(BaseModel):
    sheet_name: str
    students_to_process: int
    students_already_processed: int
    student_details: list[dict]

def _encode_share_url(url: str) -> str:
    import base64
    b64 = base64.b64encode(url.encode()).decode()
    b64 = b64.replace("/", "_").replace("+", "-").rstrip("=")
    return f"u!{b64}"


@router.post("/excel/diplomados/sheets", response_model=list[str])
async def get_diplomados_sheets(req: UrlOnlyRequest) -> list[str]:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL invalida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        sheets_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudieron cargar las pestanas. {e}")

    values = sheets_data.get("value", [])
    return [s.get("name") for s in values if s.get("name")]

@router.post("/excel/egreso/sheets", response_model=list[str])
async def get_egreso_sheets(req: UrlOnlyRequest) -> list[str]:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL invalida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        sheets_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets")
    exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudieron cargar las pestanas. {e}")

    values = sheets_data.get("value", [])
    return [s.get("name") for s in values if s.get("name")]
@router.post("/excel/diplomados/preview", response_model=PreviewResponse)
async def preview_diplomados_onedrive(req: DiplomadosUrlRequest) -> PreviewResponse:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL inválida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        range_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/usedRange")
    except Exception as e:
        if "ItemNotFound" in str(e):
            raise HTTPException(status_code=400, detail=f"La pestaña '{req.sheet_name}' no existe o el archivo no es un Excel válido.")
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo de Excel. {e}")

    values = range_data.get("values", [])
    if not values:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    header_r_idx = None
    headers = {}
    
    # We only look at the first 6 rows to find the headers
    for r_idx, row in enumerate(values[:6]):
        row_vals = [str(v or "").strip().lower() for v in row]
        if any("nombre" in v for v in row_vals) and any("cedula" in v or "cédula" in v or "ci" in v for v in row_vals):
            header_r_idx = r_idx
            for c_idx, val in enumerate(row_vals):
                if val:
                    headers[_norm(val)] = c_idx
            break
            
    if header_r_idx is None:
        raise HTTPException(status_code=400, detail="No se encontraron las columnas 'Nombre' y 'Cédula'.")

    def get_col_idx(*keys):
        for k in keys:
            for h, idx in headers.items():
                if _norm(k) in h:
                    return idx
        return None

    col_nombre = get_col_idx("nombre")
    col_cedula = get_col_idx("cedula", "cédula", "ci")
    col_enviado = get_col_idx("enviado", "estado")

    if col_nombre is None or col_cedula is None:
        raise HTTPException(status_code=400, detail="Columnas requeridas no encontradas.")

    to_process = 0
    already_processed = 0
    details = []
    
    empty_count = 0
    for r_idx in range(header_r_idx + 1, len(values)):
        row = values[r_idx]
        
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        nombre_val = get_val(col_nombre)
        cedula_val = get_val(col_cedula)
        enviado_val = get_val(col_enviado)
        
        if not nombre_val and not cedula_val:
            empty_count += 1
            if empty_count > 10:
                break
            continue
            
        empty_count = 0
        if "✅" in enviado_val or "si" in enviado_val.lower() or "enviado" in enviado_val.lower():
            already_processed += 1
        else:
            to_process += 1
            if len(details) < 50:
                details.append({"nombre": nombre_val, "cedula": cedula_val})

    return PreviewResponse(
        sheet_name=req.sheet_name,
        students_to_process=to_process,
        students_already_processed=already_processed,
        student_details=details
    )

@router.post("/excel/diplomados", response_model=BulkResult)
async def import_diplomados_onedrive(req: DiplomadosUrlRequest) -> BulkResult:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL inválida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        range_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/usedRange")
    except Exception as e:
        if "ItemNotFound" in str(e):
            raise HTTPException(status_code=400, detail=f"La pestaña '{req.sheet_name}' no existe o el archivo no es un Excel válido.")
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo de Excel. {e}")

    values = range_data.get("values", [])
    if not values:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    # The starting row/col index of this used range relative to the worksheet (0-based)
    start_row = range_data.get("rowIndex", 0)
    start_col = range_data.get("columnIndex", 0)

    header_r_idx = None
    headers = {}
    
    for r_idx, row in enumerate(values[:6]):
        row_vals = [str(v or "").strip().lower() for v in row]
        if any("nombre" in v for v in row_vals) and any("cedula" in v or "cédula" in v or "ci" in v for v in row_vals):
            header_r_idx = r_idx
            for c_idx, val in enumerate(row_vals):
                if val:
                    headers[_norm(val)] = c_idx
            break
            
    if header_r_idx is None:
        raise HTTPException(status_code=400, detail="No se encontraron las columnas 'Nombre' y 'Cédula'.")

    def get_col_idx(*keys):
        for k in keys:
            for h, idx in headers.items():
                if _norm(k) in h:
                    return idx
        return None

    col_nombre = get_col_idx("nombre")
    col_cedula = get_col_idx("cedula", "cédula", "ci")
    col_correo = get_col_idx("correo", "email")
    
    col_usuario = get_col_idx("usuario", "user")
    col_contra = get_col_idx("contrasena", "contraseña", "clave", "pass")
    col_enviado = get_col_idx("enviado", "estado")

    if col_nombre is None or col_cedula is None:
        raise HTTPException(status_code=400, detail="Columnas requeridas no encontradas.")

    max_col = len(values[header_r_idx])
    
    # We patch missing headers if necessary
    async def patch_header(c_idx, val):
        abs_r = start_row + header_r_idx
        abs_c = start_col + c_idx
        try:
            await graph.patch(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/cell(row={abs_r},column={abs_c})", {"values": [[val]]})
        except:
            pass

    if col_usuario is None:
        col_usuario = max_col
        max_col += 1
        await patch_header(col_usuario, "Usuario")
    if col_contra is None:
        col_contra = max_col
        max_col += 1
        await patch_header(col_contra, "Contraseña")
    if col_enviado is None:
        col_enviado = max_col
        max_col += 1
        await patch_header(col_enviado, "Enviado")

    result = BulkResult(succeeded=[], failed=[])
    
    async def process_row(r_idx, row):
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        nombre = get_val(col_nombre)
        cedula = get_val(col_cedula)
        correo = get_val(col_correo) if col_correo is not None else ""
        enviado = get_val(col_enviado)
        
        if not nombre or not cedula or cedula == "None":
            return
        if "✅" in enviado or enviado.lower() in ["si", "yes", "true", "enviado"]:
            return

        creds = generate_credentials(nombre, cedula, settings.institutional_domain)
        login_id = creds["email"]
        pwd = creds["password"]
        error = None
        
        try:
            await canvas.post(f"/accounts/{_ACCOUNT}/users", {
                "user": {"name": creds["full_name"]},
                "pseudonym": {
                    "unique_id": login_id, "sis_user_id": cedula,
                    "password": pwd, "send_confirmation": False,
                },
                "communication_channel": {
                    "type": "email", "address": login_id,
                    "skip_confirmation": True,
                },
            })
        except Exception as e:
            error = str(e)
        
        if not error:
            parts = creds["full_name"].strip().split()
            try:
                au = await graph.post("/users", {
                    "displayName": creds["full_name"],
                    "givenName": parts[0],
                    "surname": " ".join(parts[1:]) if len(parts) > 1 else "",
                    "userPrincipalName": login_id,
                    "mailNickname": login_id.replace(".", "_").replace("@", "_"),
                    "usageLocation": settings.usage_location,
                    "accountEnabled": True,
                    "passwordProfile": {
                        "forceChangePasswordNextSignIn": True,
                        "password": pwd,
                    },
                })
                await graph.assign_license(au["id"], settings.azure_sku_students)
            except Exception as e:
                if "already exists" not in str(e).lower() and "Request_BadRequest" not in str(e):
                    error = str(e)
        
        email_sent = False
        if not error and correo and correo != "None":
            try:
                await send_welcome_email(
                    to_email=correo, 
                    full_name=creds["full_name"], 
                    institutional_email=login_id,
                    login_id=login_id, 
                    password=pwd, 
                    platform="both",
                    program_type="diplomado", 
                    program_name=req.sheet_name,
                    extra_cc=None,
                    attachments=get_program_attachments("diplomado")
                )
                email_sent = True
            except Exception as e:
                error = f"Creado OK, pero falló el correo: {e}"
        elif not error and (not correo or correo == "None"):
            error = "Creado OK, pero no hay correo asignado"
        
        # calculate absolute row and column addresses
        abs_r = start_row + r_idx
        abs_col_enviado = start_col + col_enviado
        abs_col_user = start_col + col_usuario
        abs_col_pwd = start_col + col_contra

        async def patch_cell(c, val):
            try:
                await graph.patch(
                    f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/cell(row={abs_r},column={c})",
                    {"values": [[val]]}
                )
            except Exception as e:
                pass # ignore cell update errors if any (or log them)

        if not error or "Creado OK" in str(error):
            result.succeeded.append({"cedula": cedula, "nombre": creds["full_name"]})
            
            if email_sent:
                # Patch cells individually
                await patch_cell(abs_col_user, login_id)
                await patch_cell(abs_col_pwd, pwd)
                await patch_cell(abs_col_enviado, "✅")
            else:
                await patch_cell(abs_col_user, login_id)
                await patch_cell(abs_col_pwd, pwd)
                await patch_cell(abs_col_enviado, f"✅? {error}")
        else:
            result.failed.append({"input": {"cedula": cedula}, "error": error})
            await patch_cell(abs_col_enviado, f"❌ Error: {error}")

    tasks = []
    empty_count = 0
    for r_idx in range(header_r_idx + 1, len(values)):
        row = values[r_idx]
        
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        nombre_val = get_val(col_nombre)
        cedula_val = get_val(col_cedula)
        
        if not nombre_val and not cedula_val:
            empty_count += 1
            if empty_count > 10:
                break
            continue
            
        empty_count = 0
        tasks.append(process_row(r_idx, row))
        
    if len(tasks) > 50:
        raise HTTPException(status_code=400, detail=f"Límite de seguridad excedido: Intentas procesar {len(tasks)} alumnos a la vez (Máximo 50 permitidos). Revisa el archivo para evitar accidentes.")

    batch_size = 5
    for i in range(0, len(tasks), batch_size):
        await asyncio.gather(*tasks[i:i+batch_size])

    return result


# ------------------------------------------------------------------
# Egreso Masivo (Offboarding) con OneDrive y Graph API
# ------------------------------------------------------------------

@router.post("/excel/egreso/preview", response_model=PreviewResponse)
async def preview_egreso_onedrive(req: DiplomadosUrlRequest) -> PreviewResponse:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL inválida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        range_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/usedRange")
    except Exception as e:
        if "ItemNotFound" in str(e):
            raise HTTPException(status_code=400, detail=f"La pestaña '{req.sheet_name}' no existe o el archivo no es un Excel válido.")
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo de Excel. {e}")

    values = range_data.get("values", [])
    if not values:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    header_r_idx = None
    headers = {}
    
    # Buscamos en las primeras 6 filas
    for r_idx, row in enumerate(values[:6]):
        row_vals = [str(v or "").strip().lower() for v in row]
        if any("cedula" in v or "cédula" in v or "ci" in v for v in row_vals):
            header_r_idx = r_idx
            for c_idx, val in enumerate(row_vals):
                if val:
                    headers[_norm(val)] = c_idx
            break
            
    if header_r_idx is None:
        raise HTTPException(status_code=400, detail="No se encontró la columna 'Cédula' o equivalente.")

    def get_col_idx(*keys):
        for k in keys:
            for h, idx in headers.items():
                if _norm(k) in h:
                    return idx
        return None

    col_nombre = get_col_idx("nombre")
    col_cedula = get_col_idx("cedula", "cédula", "ci")
    col_desvinculado = get_col_idx("desvinculado", "estado", "enviado")

    if col_cedula is None:
        raise HTTPException(status_code=400, detail="Columna Cédula requerida no encontrada.")

    to_process = 0
    already_processed = 0
    details = []
    
    empty_count = 0
    for r_idx in range(header_r_idx + 1, len(values)):
        row = values[r_idx]
        
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        nombre_val = get_val(col_nombre) if col_nombre is not None else ""
        cedula_val = get_val(col_cedula)
        desv_val = get_val(col_desvinculado)
        
        if not cedula_val:
            empty_count += 1
            if empty_count > 10:
                break
            continue
            
        empty_count = 0
        if "✅" in desv_val or "si" in desv_val.lower() or "desvinculado" in desv_val.lower():
            already_processed += 1
        else:
            to_process += 1
            if len(details) < 50:
                details.append({"nombre": nombre_val or "Sin Nombre", "cedula": cedula_val})

    return PreviewResponse(
        sheet_name=req.sheet_name,
        students_to_process=to_process,
        students_already_processed=already_processed,
        student_details=details
    )

@router.post("/excel/egreso", response_model=BulkResult)
async def import_egreso_onedrive(req: DiplomadosUrlRequest) -> BulkResult:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL inválida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        range_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/usedRange")
    except Exception as e:
        if "ItemNotFound" in str(e):
            raise HTTPException(status_code=400, detail=f"La pestaña '{req.sheet_name}' no existe o el archivo no es un Excel válido.")
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo de Excel. {e}")

    values = range_data.get("values", [])
    if not values:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    start_row = range_data.get("rowIndex", 0)
    start_col = range_data.get("columnIndex", 0)

    header_r_idx = None
    headers = {}
    
    for r_idx, row in enumerate(values[:6]):
        row_vals = [str(v or "").strip().lower() for v in row]
        if any("cedula" in v or "cédula" in v or "ci" in v for v in row_vals):
            header_r_idx = r_idx
            for c_idx, val in enumerate(row_vals):
                if val:
                    headers[_norm(val)] = c_idx
            break
            
    if header_r_idx is None:
        raise HTTPException(status_code=400, detail="No se encontró la columna 'Cédula'.")

    def get_col_idx(*keys):
        for k in keys:
            for h, idx in headers.items():
                if _norm(k) in h:
                    return idx
        return None

    col_cedula = get_col_idx("cedula", "cédula", "ci")
    col_desvinculado = get_col_idx("desvinculado", "estado", "enviado")

    if col_cedula is None:
        raise HTTPException(status_code=400, detail="Columna Cédula requerida no encontrada.")

    max_col = len(values[header_r_idx])
    
    async def patch_header(c_idx, val):
        abs_r = start_row + header_r_idx
        abs_c = start_col + c_idx
        try:
            await graph.patch(f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/cell(row={abs_r},column={abs_c})", {"values": [[val]]})
        except:
            pass

    if col_desvinculado is None:
        col_desvinculado = max_col
        max_col += 1
        await patch_header(col_desvinculado, "Desvinculado")

    result = BulkResult(succeeded=[], failed=[])
    
    async def process_row(r_idx, row):
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        cedula = get_val(col_cedula)
        desvinculado = get_val(col_desvinculado)
        
        if not cedula or cedula == "None":
            return
        if "✅" in desvinculado or "si" in desvinculado.lower() or "desvinculado" in desvinculado.lower():
            return

        error = None
        
        # 1. Canvas suspend
        canvas_email = None
        try:
            c_user = await canvas.get(f"/accounts/{_ACCOUNT}/users/sis_user_id:{cedula}")
            user_id = c_user.get("id")
            if user_id:
                await canvas.delete(f"/accounts/{_ACCOUNT}/users/{user_id}")
                canvas_email = c_user.get("email")
            else:
                error = "Usuario no encontrado en Canvas"
        except Exception as e:
            if "404" in str(e):
                error = "Usuario no encontrado en Canvas"
            else:
                error = f"Error Canvas: {e}"
        
        # 2. Teams disable
        teams_suspended = False
        if not error and canvas_email:
            try:
                teams_users = await graph.get("/users", params={"$filter": f"userPrincipalName eq '{canvas_email}'"})
                if teams_users and isinstance(teams_users.get("value"), list) and len(teams_users["value"]) > 0:
                    t_user_id = teams_users["value"][0]["id"]
                    await graph.patch(f"/users/{t_user_id}", {"accountEnabled": False})
                    teams_suspended = True
                else:
                    error = "Creado OK en Canvas, pero no encontrado en Teams"
            except Exception as te:
                error = f"Creado OK en Canvas, Error Teams: {te}"

        # calculate absolute row and column addresses
        abs_r = start_row + r_idx
        abs_col_desv = start_col + col_desvinculado

        async def patch_cell(c, val):
            try:
                await graph.patch(
                    f"/shares/{encoded_url}/driveItem/workbook/worksheets('{req.sheet_name}')/cell(row={abs_r},column={c})",
                    {"values": [[val]]}
                )
            except Exception as e:
                pass 

        if not error or "Creado OK" in str(error):
            result.succeeded.append({"cedula": cedula, "nombre": canvas_email})
            await patch_cell(abs_col_desv, "✅")
        else:
            result.failed.append({"input": {"cedula": cedula}, "error": error})
            await patch_cell(abs_col_desv, f"❌ Error: {error}")

    tasks = []
    empty_count = 0
    for r_idx in range(header_r_idx + 1, len(values)):
        row = values[r_idx]
        
        def get_val(c_idx):
            if c_idx is not None and c_idx < len(row):
                return str(row[c_idx] or "").strip()
            return ""

        cedula_val = get_val(col_cedula)
        
        if not cedula_val:
            empty_count += 1
            if empty_count > 10:
                break
            continue
            
        empty_count = 0
        tasks.append(process_row(r_idx, row))
        
    if len(tasks) > 50:
        raise HTTPException(status_code=400, detail=f"Límite de seguridad excedido: Intentas procesar {len(tasks)} alumnos a la vez (Máximo 50 permitidos). Revisa el archivo para evitar accidentes.")

    batch_size = 5
    for i in range(0, len(tasks), batch_size):
        await asyncio.gather(*tasks[i:i+batch_size])

    return result
