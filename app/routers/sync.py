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

