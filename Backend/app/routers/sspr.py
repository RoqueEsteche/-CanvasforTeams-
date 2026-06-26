import logging
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.services import canvas_client, teams_client, email_service
from app.services.credential_generator import generate_password

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SSPR"])
_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "Frontend" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

@router.get("/sspr", response_class=HTMLResponse)
async def sspr_page(request: Request):
    """Página pública de autogestión de contraseñas (Self-Service Password Reset)."""
    return templates.TemplateResponse(
        "sspr.html",
        {"request": request, "page_title": "Restablecer Contraseña"}
    )

@router.post("/api/sspr/reset")
async def process_sspr(
    cedula: str = Form(...),
    email: str = Form(...)
):
    """Procesa la solicitud de reseteo de contraseña."""
    try:
        # 1. Buscar en Canvas por sis_login_id (Cédula)
        canvas_users = await canvas_client.get("/accounts/1/users", params={"search_term": f"sis_login_id:{cedula}"})
        if not canvas_users:
            raise ValueError("No se encontró ningún estudiante con esa cédula.")
            
        canvas_user = canvas_users[0]
        
        # Validar el email personal en Canvas (si se guardó ahí) o permitir que busque en Azure
        canvas_email = canvas_user.get("email", "").lower()
        
        # 2. Buscar en Teams por UPN o extensión
        teams_users = await teams_client.paginate("/users", {"$filter": f"employeeId eq '{cedula}' or mailNickname eq '{cedula}' or startswith(userPrincipalName, '{cedula}')"})
        
        if not teams_users:
            # Fallback si no tiene employeeId, intentamos match por displayname o upn
            raise ValueError("Usuario encontrado en Canvas, pero no en Microsoft Teams. Contacte a TI.")
            
        teams_user = teams_users[0]
        upn = teams_user["userPrincipalName"]
        display_name = teams_user["displayName"]
        
        # Opcional: Obtener detalles del usuario de Teams para leer otherMails (si se cargaron)
        # Por simplicidad, aquí validamos que el email provisto coincida con el email registrado en Canvas.
        if email.lower() != canvas_email and email.lower() != upn.lower():
            # Intentar verificar otherMails en Azure
            teams_user_details = await teams_client.get(f"/users/{teams_user['id']}?$select=otherMails")
            other_mails = [m.lower() for m in teams_user_details.get("otherMails", [])]
            if email.lower() not in other_mails:
                raise ValueError("El correo electrónico proporcionado no coincide con el registrado en nuestro sistema (Canvas o Azure AD).")

        # 3. Generar nueva contraseña y actualizar
        new_password = generate_password()
        await teams_client.update_user_password(teams_user["id"], new_password)
        
        # 4. Enviar el correo electrónico
        await email_service.send_welcome_email(
            to_email=email,
            full_name=display_name,
            institutional_email=upn,
            login_id=cedula,
            password=new_password,
            platform="teams", # Solo reseteamos Teams (usualmente Canvas usa SSO de Teams)
            program_type="SSPR",
            program_name="Restablecimiento de Contraseña"
        )
        
        return JSONResponse({"status": "success", "message": "Se ha enviado su nueva contraseña a su correo personal."})
        
    except ValueError as e:
        logger.warning(f"SSPR Error para {cedula}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error procesando SSPR: {e}")
        raise HTTPException(status_code=500, detail="Ocurrió un error interno al restablecer la contraseña.")
