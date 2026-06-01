"""New-student/teacher onboarding: credential generation + Canvas/Teams creation + welcome email."""
import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


def _err(exc: Exception) -> str:
    """Extract the most useful error message from any exception type."""
    return exc.detail if isinstance(exc, HTTPException) else str(exc)

from app.core.config import settings
from app.models.canvas import BulkResult
from app.services import canvas_client as canvas
from app.services import teams_client as graph
from app.services.credential_generator import generate_credentials
from app.services.email_service import send_welcome_email

router = APIRouter(prefix="/ingreso", tags=["Nuevo Ingreso"])
_ACCOUNT = settings.canvas_account_id


class StudentIn(BaseModel):
    full_name: str
    cedula: str
    personal_email: str
    role: str = "student"            # "student" | "teacher"
    platform: str = "both"           # "canvas" | "teams" | "both"
    program_type: str = "grado"      # "grado" | "mba" | "diplomado"
    program_name: str = ""           # nombre específico del diplomado/programa
    send_email: bool = True
    cc: list[str] = []               # extra CC recipients for this send


class BulkStudentsIn(BaseModel):
    students: list[StudentIn]


class CredentialPreview(BaseModel):
    full_name: str
    cedula: str
    personal_email: str
    role: str
    login_id: str
    institutional_email: str
    password: str


def _resolve_login(creds: dict, role: str) -> tuple[str, str]:
    """Return (canvas_login_id, canvas_sis_user_id).

    Both students and teachers use the institutional email as login (unique_id)
    so they can authenticate with their email and password on both Canvas and Teams.
    The SIS user ID is always the cédula for institutional tracking.
    """
    return creds["email"], creds["cedula"]


@router.post("/preview", response_model=CredentialPreview, summary="Previsualizar credenciales")
async def preview_credentials(body: StudentIn):
    creds = generate_credentials(body.full_name, body.cedula, settings.institutional_domain)
    login_id, _ = _resolve_login(creds, body.role)
    return CredentialPreview(
        full_name=body.full_name,
        cedula=body.cedula,
        personal_email=body.personal_email,
        role=body.role,
        login_id=login_id,
        institutional_email=creds["email"],
        password=creds["password"],
    )


async def _create_student(student: StudentIn) -> dict[str, Any]:
    creds = generate_credentials(student.full_name, student.cedula, settings.institutional_domain)
    login_id, sis_user_id = _resolve_login(creds, student.role)
    results: dict[str, Any] = {
        "student": student.full_name,
        "role": student.role,
        "credentials": {**creds, "login_id": login_id},
    }

    if student.platform in ("canvas", "both"):
        try:
            canvas_user = await canvas.post(
                f"/accounts/{_ACCOUNT}/users",
                {
                    "user": {"name": creds["full_name"], "short_name": creds["full_name"]},
                    "pseudonym": {
                        "unique_id": login_id,
                        "sis_user_id": sis_user_id,
                        "password": creds["password"],
                        "send_confirmation": False,
                    },
                    "communication_channel": {
                        "type": "email",
                        "address": creds["email"],
                        "skip_confirmation": True,
                    },
                },
            )
            results["canvas"] = {"status": "ok", "id": canvas_user.get("id")}
        except Exception as exc:
            results["canvas"] = {"status": "error", "error": _err(exc)}

    if student.platform in ("teams", "both"):
        parts = student.full_name.strip().split()
        sku = settings.azure_sku_teachers if student.role == "teacher" else settings.azure_sku_students
        try:
            az_user = await graph.post(
                "/users",
                {
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
                },
            )
            await graph.assign_license(az_user["id"], sku)
            results["teams"] = {"status": "ok", "id": az_user.get("id"), "license": sku}
        except Exception as exc:
            results["teams"] = {"status": "error", "error": _err(exc)}

    if student.send_email:
        try:
            await send_welcome_email(
                to_email=student.personal_email,
                full_name=creds["full_name"],
                institutional_email=creds["email"],
                login_id=login_id,
                password=creds["password"],
                platform=student.platform,
                program_type=student.program_type,
                program_name=student.program_name,
                extra_cc=student.cc or None,
            )
            results["email"] = "sent"
        except Exception as exc:
            results["email"] = f"error: {exc}"

    return results


@router.post("/test-email", summary="Probar envío de correo")
async def test_email(
    to_email: str,
    program_type: str = "grado",
    program_name: str = "",
):
    """Envía un correo de prueba para verificar la configuración y la plantilla."""
    try:
        await send_welcome_email(
            to_email=to_email,
            full_name="Usuario de Prueba",
            institutional_email=f"prueba@{settings.institutional_domain}",
            login_id=f"prueba@{settings.institutional_domain}",
            password="Test-Pw123",
            platform="both",
            program_type=program_type,
            program_name=program_name,
        )
        return {"status": "ok", "to": to_email, "from": settings.smtp_from, "program_type": program_type}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.post("/create", summary="Crear credenciales para un alumno o docente")
async def create_student(body: StudentIn):
    return await _create_student(body)


@router.post("/bulk", summary="Crear credenciales masivas")
async def create_students_bulk(body: BulkStudentsIn) -> BulkResult:
    result = BulkResult()

    async def _run(student: StudentIn):
        try:
            data = await _create_student(student)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"student": student.full_name, "error": str(exc)})

    await asyncio.gather(*[_run(s) for s in body.students])
    return result
