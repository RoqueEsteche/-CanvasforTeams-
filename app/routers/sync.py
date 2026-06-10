"""
Sync operations: create a Teams Team from a Canvas Course and keep members in sync.
"""
import asyncio

from fastapi import APIRouter, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services import canvas_client as canvas
from app.services import teams_client as graph
from app.services.teams_client import post_team

router = APIRouter(prefix="/sync", tags=["Sync · Canvas ↔ Teams"])
_ACCOUNT = settings.canvas_account_id


class SyncCourseRequest(BaseModel):
    canvas_course_id: str
    owner_id: str  # Azure AD object ID of the Teams owner
    template: str = "educationClass"


class SyncCourseResponse(BaseModel):
    canvas_course_id: str
    team_id: str
    synced_members: int
    failed_members: int


@router.post("/course-to-team", summary="Crear Team desde un Curso de Canvas y sincronizar miembros")
async def sync_course_to_team(body: SyncCourseRequest) -> SyncCourseResponse:
    # 1. Fetch Canvas course info
    try:
        course = await canvas.get(f"/courses/{body.canvas_course_id}")
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Canvas course not found: {exc}")

    # 2. Create Teams team
    team_payload = {
        "template@odata.bind": f"https://graph.microsoft.com/v1.0/teamsTemplates('{body.template}')",
        "displayName": course.get("name", f"Course {body.canvas_course_id}"),
        "description": course.get("public_description") or course.get("name", ""),
        "visibility": "Private",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.owner_id}')",
            }
        ],
    }
    try:
        team = await post_team(team_payload)
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not create Teams team: {exc}")

    team_id = team.get("id", "")

    # 3. Fetch Canvas enrollments
    enrollments = await canvas.paginate(
        f"/courses/{body.canvas_course_id}/enrollments",
        {"state[]": ["active"], "per_page": 100},
    )

    # 4. Map Canvas SIS login → Azure UPN (assumes same email domain)
    synced = 0
    failed = 0

    async def _add_member(enrollment: dict):
        nonlocal synced, failed
        email = enrollment.get("user", {}).get("email") or enrollment.get("user", {}).get("login_id")
        if not email:
            failed += 1
            return
        try:
            await graph.post(
                f"/teams/{team_id}/members",
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": [],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{email}')",
                },
            )
            synced += 1
        except Exception:
            failed += 1

    await asyncio.gather(*[_add_member(e) for e in enrollments])

    return SyncCourseResponse(
        canvas_course_id=body.canvas_course_id,
        team_id=team_id,
        synced_members=synced,
        failed_members=failed,
    )


class UnifiedCreateRequest(BaseModel):
    course_name: str
    course_code: str
    owner_identifier: str  # SIS ID or Email
    template: str = "educationClass"

class UnifiedEnrollRequest(BaseModel):
    user_identifier: str # SIS ID o Email
    canvas_course_id: str
    teams_team_id: str
    role: str = "student"

class BulkUnifiedCreateRequest(BaseModel):
    items: list[UnifiedCreateRequest]

class BulkUnifiedEnrollRequest(BaseModel):
    items: list[UnifiedEnrollRequest]

@router.post("/create-course-and-team", summary="Crear curso en Canvas y equipo en Teams simultáneamente")
async def create_course_and_team(body: UnifiedCreateRequest) -> dict:
    # 1. Resolve owner in Canvas and Teams
    from app.routers.profile import _find_canvas_user, _find_graph_user
    
    canvas_owner = await _find_canvas_user(body.owner_identifier)
    teams_owner = await _find_graph_user(body.owner_identifier)
    
    if not canvas_owner:
        raise HTTPException(status_code=404, detail=f"Owner not found in Canvas using identifier {body.owner_identifier}")
    if not teams_owner:
        raise HTTPException(status_code=404, detail=f"Owner not found in Teams using identifier {body.owner_identifier}")
        
    canvas_owner_id = canvas_owner.get("id")
    teams_owner_id = teams_owner.get("id")
    
    # 2. Create Canvas Course
    canvas_course = await canvas.post(
        f"/accounts/{_ACCOUNT}/courses",
        {
            "course": {
                "name": body.course_name,
                "course_code": body.course_code,
                "is_public": False,
            }
        }
    )
    course_id = canvas_course.get("id")
    
    # Enroll owner in Canvas course as teacher
    await canvas.post(
        f"/courses/{course_id}/enrollments",
        {
            "enrollment": {
                "user_id": canvas_owner_id,
                "type": "TeacherEnrollment",
                "enrollment_state": "active",
            }
        }
    )

    # 3. Create Teams Team
    team_payload = {
        "template@odata.bind": f"https://graph.microsoft.com/v1.0/teamsTemplates('{body.template}')",
        "displayName": body.course_name,
        "description": body.course_code,
        "visibility": "Private",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{teams_owner_id}')",
            }
        ],
    }
    
    team = await post_team(team_payload)
    team_id = team.get("id", "")
    
    return {
        "status": "success",
        "canvas_course_id": course_id,
        "teams_team_id": team_id,
    }

@router.post("/bulk-create-courses-and-teams", summary="Creación masiva de cursos y equipos")
async def bulk_create_courses_and_teams(body: BulkUnifiedCreateRequest) -> dict:
    from app.models.canvas import BulkResult
    result = BulkResult()
    
    async def _run(item: UnifiedCreateRequest):
        try:
            res = await create_course_and_team(item)
            result.succeeded.append({"item": item.course_code, "result": res})
        except Exception as exc:
            result.failed.append({"item": item.course_code, "error": str(exc)})
            
    await asyncio.gather(*[_run(i) for i in body.items])
    return result

@router.post("/enroll-both", summary="Matricular usuario en Canvas y Teams simultáneamente")
async def enroll_both(body: UnifiedEnrollRequest) -> dict:
    from app.routers.profile import _find_canvas_user, _find_graph_user
    
    canvas_user = await _find_canvas_user(body.user_identifier)
    teams_user = await _find_graph_user(body.user_identifier)
    
    if not canvas_user:
        raise HTTPException(status_code=404, detail=f"User not found in Canvas using identifier {body.user_identifier}")
    if not teams_user:
        raise HTTPException(status_code=404, detail=f"User not found in Teams using identifier {body.user_identifier}")
        
    canvas_user_id = canvas_user.get("id")
    teams_user_id = teams_user.get("id")
    
    canvas_role = "StudentEnrollment" if body.role.lower() == "student" else "TeacherEnrollment"
    
    # 1. Enroll in Canvas
    try:
        await canvas.post(
            f"/courses/{body.canvas_course_id}/enrollments",
            {
                "enrollment": {
                    "user_id": canvas_user_id,
                    "type": canvas_role,
                    "enrollment_state": "active",
                }
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to enroll in Canvas: {exc}")
        
    # 2. Enroll in Teams
    teams_roles = [] if body.role.lower() == "student" else ["owner"]
    try:
        await graph.post(
            f"/teams/{body.teams_team_id}/members",
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": teams_roles,
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{teams_user_id}')",
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to enroll in Teams: {exc}")
        
    return {
        "status": "success",
        "canvas_enrolled": True,
        "teams_enrolled": True
    }

@router.post("/bulk-enroll-both", summary="Matriculación masiva en Canvas y Teams")
async def bulk_enroll_both(body: BulkUnifiedEnrollRequest) -> dict:
    from app.models.canvas import BulkResult
    result = BulkResult()
    
    async def _run(item: UnifiedEnrollRequest):
        try:
            res = await enroll_both(item)
            result.succeeded.append({"item": item.user_identifier, "result": res})
        except Exception as exc:
            result.failed.append({"item": item.user_identifier, "error": str(exc)})
            
    await asyncio.gather(*[_run(i) for i in body.items])
    return result
