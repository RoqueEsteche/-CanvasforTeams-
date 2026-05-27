"""Canvas enrollment/unenrollment endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models.canvas import (
    BulkCanvasEnrollmentCreate,
    BulkCanvasEnrollmentDelete,
    BulkResult,
    CanvasEnrollmentCreate,
    CanvasEnrollmentDelete,
)
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/courses/{course_id}/enrollments", tags=["Canvas · Enrollments"])


@router.get("", summary="Listar matrículas de un curso")
async def list_enrollments(
    course_id: str,
    type: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    params: dict = {"per_page": per_page}
    if type:
        params["type[]"] = type
    if state:
        params["state[]"] = state
    return await canvas.paginate(f"/courses/{course_id}/enrollments", params)


@router.post("", status_code=201, summary="Matricular usuario individual")
async def enroll_user(course_id: str, body: CanvasEnrollmentCreate):
    payload = {
        "enrollment": {
            "user_id": body.user_id,
            "type": body.type,
            "enrollment_state": body.enrollment_state,
            "notify": body.notify,
        }
    }
    if body.role_id:
        payload["enrollment"]["role_id"] = body.role_id
    if body.course_section_id:
        payload["enrollment"]["course_section_id"] = body.course_section_id
    try:
        return await canvas.post(f"/courses/{course_id}/enrollments", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{enrollment_id}", summary="Desmatricular usuario individual")
async def unenroll_user(
    course_id: str,
    enrollment_id: str,
    task: Annotated[str, Query(description="delete | conclude | deactivate | inactivate")] = "conclude",
):
    try:
        return await canvas.delete(
            f"/courses/{course_id}/enrollments/{enrollment_id}",
            {"task": task},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Bulk ─────────────────────────────────────────────────────────────────────

bulk_router = APIRouter(prefix="/canvas/enrollments/bulk", tags=["Canvas · Enrollments"])


@bulk_router.post("/enroll", summary="Matricular usuarios de forma masiva en un curso")
async def bulk_enroll(body: BulkCanvasEnrollmentCreate) -> BulkResult:
    result = BulkResult()

    async def _enroll(enrollment: CanvasEnrollmentCreate):
        try:
            data = await canvas.post(
                f"/courses/{body.course_id}/enrollments",
                {"enrollment": {
                    "user_id": enrollment.user_id,
                    "type": enrollment.type,
                    "enrollment_state": enrollment.enrollment_state,
                    "notify": enrollment.notify,
                }},
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": enrollment.model_dump(), "error": str(exc)})

    await asyncio.gather(*[_enroll(e) for e in body.enrollments])
    return result


@bulk_router.post("/unenroll", summary="Desmatricular usuarios de forma masiva de un curso")
async def bulk_unenroll(body: BulkCanvasEnrollmentDelete) -> BulkResult:
    result = BulkResult()

    async def _unenroll(enrollment_id: str):
        try:
            data = await canvas.delete(
                f"/courses/{body.course_id}/enrollments/{enrollment_id}",
                {"task": body.task},
            )
            result.succeeded.append({"enrollment_id": enrollment_id, **data})
        except Exception as exc:
            result.failed.append({"enrollment_id": enrollment_id, "error": str(exc)})

    await asyncio.gather(*[_unenroll(eid) for eid in body.enrollment_ids])
    return result
