import asyncio
import logging
from typing import List, Dict, Any

from app.services import canvas_client, teams_client
from app.routers.sync import _enroll_single, UnifiedEnrollment

logger = logging.getLogger(__name__)

# Control loop variable
_running = False

async def get_active_courses_from_canvas() -> List[Dict[str, Any]]:
    """Retrieve active courses from Canvas to sync."""
    try:
        # Paginamos los cursos activos en el periodo actual o global
        params = {
            "state[]": ["available"],
            "per_page": 20
        }
        courses = await canvas_client.paginate_limited("/accounts/1/courses", params, max_records=50)
        return courses
    except Exception as e:
        logger.error(f"AutoSync: Error obteniendo cursos de Canvas: {e}")
        return []

async def sync_course_to_team(canvas_course: Dict[str, Any]):
    """Sincroniza un curso específico hacia su Team correspondiente."""
    course_name = canvas_course.get("name")
    course_id = canvas_course.get("id")
    if not course_name:
        return
        
    try:
        # 1. Buscar Team por nombre (Asumimos que el Team tiene el mismo nombre que el curso)
        params = {
            "$top": 1,
            "$select": "id,displayName",
            "$filter": f"resourceProvisioningOptions/Any(x:x eq 'Team') and displayName eq '{course_name}'",
        }
        teams = await teams_client.paginate("/groups", params)
        if not teams:
            logger.info(f"AutoSync: No se encontró un Team para el curso '{course_name}'. Omitiendo...")
            return
            
        team_id = teams[0]["id"]
        
        # 2. Obtener usuarios matriculados en el curso de Canvas
        enrollments = await canvas_client.paginate_limited(f"/courses/{course_id}/enrollments", {"state[]": "active"}, max_records=100)
        
        # 3. Obtener miembros del Team
        team_members = await teams_client.get(f"/teams/{team_id}/members")
        team_users = {m.get("userId") for m in team_members.get("value", []) if m.get("userId")}
        
        # 4. Comparar y agregar faltantes
        for enr in enrollments:
            canvas_user = enr.get("user", {})
            sis_login_id = canvas_user.get("sis_login_id")
            if not sis_login_id:
                continue
                
            # Buscar en Teams
            # Para esto necesitaríamos que los miembros del Team tengan un mapeo exacto.
            # En la vida real, lo más óptimo es simplemente intentar agregarlos.
            # Teams API no duplicará miembros si ya existen.
            role = "teacher" if enr.get("type") == "TeacherEnrollment" else "student"
            item = UnifiedEnrollment(
                user_identifier=sis_login_id,
                canvas_course_id=str(course_id),
                teams_team_id=team_id,
                role=role
            )
            
            # Solo llamamos _enroll_single o directamente team.post()
            teams_role = ["owner"] if role == "teacher" else []
            teams_payload = {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": teams_role,
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{sis_login_id}')",
            }
            try:
                await teams_client.post(f"/teams/{team_id}/members", teams_payload)
            except Exception as e:
                # 400 Bad Request generalmente significa que ya está en el team. 
                pass

        logger.info(f"AutoSync: Curso '{course_name}' sincronizado con éxito.")
    except Exception as e:
        logger.error(f"AutoSync: Error sincronizando curso {course_name}: {e}")

import datetime

async def auto_sync_loop():
    """Bucle que se ejecuta una vez a la madrugada (aprox 3:00 AM)."""
    global _running
    _running = True
    
    logger.info("AutoSync: Servicio iniciado en background (Espejado nocturno).")
    
    while _running:
        try:
            now = datetime.datetime.now()
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target += datetime.timedelta(days=1)
                
            wait_seconds = (target - now).total_seconds()
            logger.info(f"AutoSync: Durmiendo {wait_seconds} segundos hasta las 3:00 AM.")
            
            # Dormir hasta las 3 AM (se divide para poder interrumpirse)
            while wait_seconds > 0 and _running:
                sleep_time = min(60, wait_seconds)
                await asyncio.sleep(sleep_time)
                wait_seconds -= sleep_time
                
            if not _running:
                break
                
            logger.info("AutoSync: Iniciando ciclo de sincronización (Madrugada).")
            courses = await get_active_courses_from_canvas()
            
            for course in courses:
                if not _running:
                    break
                await sync_course_to_team(course)
                await asyncio.sleep(2) # Pausa para no saturar Rate Limits
                
            logger.info("AutoSync: Ciclo finalizado.")
        except asyncio.CancelledError:
            logger.info("AutoSync: Ciclo cancelado.")
            break
        except Exception as e:
            logger.error(f"AutoSync: Error inesperado en el ciclo: {e}")
            await asyncio.sleep(300) # Reintentar en 5 mins si hay error crítico


def start_auto_sync():
    """Llamado en el evento startup de FastAPI."""
    asyncio.create_task(auto_sync_loop())

def stop_auto_sync():
    """Llamado en el evento shutdown."""
    global _running
    _running = False
