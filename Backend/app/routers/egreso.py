from fastapi import APIRouter, HTTPException
import logging
from app.services import canvas_client as canvas
from app.services import teams_client as graph
from app.core.config import settings

router = APIRouter(prefix="/egreso", tags=["Desvinculación"])
logger = logging.getLogger(__name__)
_ACCOUNT = settings.canvas_account_id

@router.post("/suspend", summary="Suspender cuenta de Canvas y MS Teams")
async def suspend_user(sys_user_id: str):
    """
    Suspende a un usuario en Canvas y MS Teams.
    """
    sys_user_id = sys_user_id.strip()
    if not sys_user_id:
        raise HTTPException(status_code=400, detail="Se requiere el ID del usuario")
    
    res = {"sys_user_id": sys_user_id, "canvas": "skipped", "teams": "skipped"}
    
    # 1. Canvas: Buscar y Suspender o Eliminar (Soft Delete)
    try:
        # En Canvas, usamos el endpoint de borrar que marca al usuario como "deleted" 
        # (Esto deshabilita login pero retiene info en base de datos)
        # O podemos buscarlo primero.
        c_user = await canvas.get(f"/accounts/{_ACCOUNT}/users/sis_user_id:{sys_user_id}")
        user_id = c_user.get("id")
        if user_id:
            await canvas.delete(f"/accounts/{_ACCOUNT}/users/{user_id}")
            res["canvas"] = "suspended"
            canvas_email = c_user.get("email")
            
            # 2. Teams: Buscar por el email de Canvas o UPN y Suspender
            if canvas_email:
                try:
                    # En Teams (Graph), buscamos por UPN
                    teams_users = await graph.get("/users", params={"$filter": f"userPrincipalName eq '{canvas_email}'"})
                    if teams_users and isinstance(teams_users.get("value"), list) and len(teams_users["value"]) > 0:
                        t_user_id = teams_users["value"][0]["id"]
                        # Deshabilitar cuenta en Azure AD
                        await graph.patch(f"/users/{t_user_id}", {"accountEnabled": False})
                        res["teams"] = "suspended"
                    else:
                        res["teams"] = "not_found"
                except Exception as te:
                    logger.error(f"Error suspendiendo en Teams: {te}")
                    res["teams"] = f"error: {te}"
    except Exception as e:
        if "404" in str(e):
            res["canvas"] = "not_found"
        else:
            logger.error(f"Error suspendiendo en Canvas: {e}")
            res["canvas"] = f"error: {e}"
            
    return res
