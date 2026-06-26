"""Sync router for Unified Enrollments in Canvas and Teams."""

import asyncio
import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services import canvas_client as canvas
from app.services import teams_client as graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Sync"])

class UnifiedEnrollment(BaseModel):
    user_identifier: str
    canvas_course_id: str
    teams_team_id: str
    role: str = "student"

class BulkUnifiedEnrollment(BaseModel):
    items: List[UnifiedEnrollment]

async def resolve_canvas_course(course_ref: str) -> str:
    """Returns the course ID, searching by name if course_ref is not purely numeric."""
    if course_ref.isdigit():
        return course_ref

    params = {
        "search_term": course_ref,
        "per_page": 5,
        "state[]": ["available", "completed", "created", "claimed"]
    }
    account_id = settings.canvas_account_id
    try:
        courses = await canvas.paginate_limited(f"/accounts/{account_id}/courses", params, max_records=10)
        # Buscar coincidencia exacta por nombre o código
        for c in courses:
            if c.get("name") == course_ref or c.get("course_code") == course_ref:
                return str(c["id"])
        # Si no hay exacta, usar el primero
        if courses:
            return str(courses[0]["id"])
    except Exception as e:
        logger.error(f"Error resolving Canvas course {course_ref}: {e}")
    
    raise ValueError(f"No se encontró el curso en Canvas: {course_ref}")

async def resolve_teams_group(team_ref: str) -> str:
    """Returns the team ID, searching by displayName if team_ref is not a UUID."""
    try:
        uuid_obj = uuid.UUID(team_ref)
        return str(uuid_obj)
    except ValueError:
        pass # Not a UUID, proceed to search by name
    
    params = {
        "$top": 5,
        "$select": "id,displayName",
        "$filter": f"resourceProvisioningOptions/Any(x:x eq 'Team') and displayName eq '{team_ref}'",
    }
    try:
        teams = await graph.paginate("/groups", params)
        if teams:
            return teams[0]["id"]
    except Exception as e:
        logger.error(f"Error resolving Teams group {team_ref}: {e}")

    raise ValueError(f"No se encontró el equipo en Teams: {team_ref}")

async def resolve_canvas_user(user_ref: str) -> str:
    """Returns the internal Canvas user ID."""
    if user_ref.isdigit():
        return user_ref

    account_id = settings.canvas_account_id
    try:
        users = await canvas.paginate_limited(f"/accounts/{account_id}/users", {"search_term": user_ref, "per_page": 5}, max_records=5)
        if users:
            return str(users[0]["id"])
    except Exception as e:
        logger.error(f"Error resolving Canvas user {user_ref}: {e}")
    
    if "@" in user_ref:
        return f"sis_login_id:{user_ref}"
        
    raise ValueError(f"No se encontró el usuario en Canvas: {user_ref}")

async def _enroll_single(item: UnifiedEnrollment):
    errors = []
    
    # 1. Resolve IDs
    try:
        canvas_user_id = await resolve_canvas_user(item.user_identifier)
    except Exception as e:
        return {"status": "error", "message": str(e), "item": item.dict()}

    try:
        course_id = await resolve_canvas_course(item.canvas_course_id)
    except Exception as e:
        return {"status": "error", "message": str(e), "item": item.dict()}

    try:
        team_id = await resolve_teams_group(item.teams_team_id)
    except Exception as e:
        return {"status": "error", "message": str(e), "item": item.dict()}

    # 2. Canvas Enrollment
    canvas_role = "TeacherEnrollment" if item.role == "teacher" else "StudentEnrollment"
    canvas_payload = {
        "enrollment": {
            "user_id": canvas_user_id,
            "type": canvas_role,
            "enrollment_state": "invited",
            "notify": True
        }
    }
    
    try:
        await canvas.post(f"/courses/{course_id}/enrollments", canvas_payload)
    except Exception as e:
        errors.append(f"Canvas Error: {e}")

    # 3. Teams Enrollment
    teams_role = ["owner"] if item.role == "teacher" else []
    teams_payload = {
        "@odata.type": "#microsoft.graph.aadUserConversationMember",
        "roles": teams_role,
        "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{item.user_identifier}')",
    }
    
    try:
        await graph.post(f"/teams/{team_id}/members", teams_payload)
    except Exception as e:
        errors.append(f"Teams Error: {e}")

    if errors:
        return {"status": "error", "message": " | ".join(errors), "item": item.dict()}
    
    return {"status": "success", "item": item.dict()}


@router.post("/enroll-both")
async def enroll_both(body: UnifiedEnrollment):
    result = await _enroll_single(body)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return {"message": "Matriculado correctamente en ambas plataformas"}

@router.post("/bulk-enroll-both")
async def bulk_enroll_both(body: BulkUnifiedEnrollment):
    results = await asyncio.gather(*[_enroll_single(item) for item in body.items])
    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]
    
    return {
        "succeeded": succeeded,
        "failed": failed,
        "total_succeeded": len(succeeded),
        "total_failed": len(failed)
    }
