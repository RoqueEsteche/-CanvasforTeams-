"""Canvas course management endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.models.canvas import (
    BulkCanvasCourseCreate,
    BulkResult,
    CanvasCourseCreate,
    CanvasCourseUpdate,
)
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/courses", tags=["Canvas · Courses"])
_ACCOUNT = settings.canvas_account_id


@router.get("", summary="Listar cursos de la cuenta")
async def list_courses(
    search_term: Annotated[str | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    params: dict = {"per_page": per_page}
    if search_term:
        params["search_term"] = search_term
    if state:
        params["state[]"] = state
    return await canvas.paginate(f"/accounts/{_ACCOUNT}/courses", params)


@router.get("/{course_id}", summary="Obtener curso por ID")
async def get_course(course_id: str):
    try:
        return await canvas.get(f"/courses/{course_id}")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear curso individual")
async def create_course(body: CanvasCourseCreate):
    payload: dict = {
        "course": {
            "name": body.name,
            "course_code": body.course_code,
            "sis_course_id": body.sis_course_id,
            "start_at": body.start_at,
            "end_at": body.end_at,
            "license": body.license,
            "is_public": body.is_public,
        }
    }
    if body.enroll_me:
        payload["enroll_me"] = True
    try:
        return await canvas.post(f"/accounts/{_ACCOUNT}/courses", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bulk", summary="Crear cursos de forma masiva")
async def create_courses_bulk(body: BulkCanvasCourseCreate) -> BulkResult:
    result = BulkResult()

    async def _create(course: CanvasCourseCreate):
        try:
            data = await canvas.post(
                f"/accounts/{_ACCOUNT}/courses",
                {"course": {
                    "name": course.name,
                    "course_code": course.course_code,
                    "sis_course_id": course.sis_course_id,
                    "start_at": course.start_at,
                    "end_at": course.end_at,
                }},
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": course.model_dump(), "error": str(exc)})

    await asyncio.gather(*[_create(c) for c in body.courses])
    return result


@router.put("/{course_id}", summary="Actualizar curso")
async def update_course(course_id: str, body: CanvasCourseUpdate):
    fields = body.model_dump(exclude_none=True)
    try:
        return await canvas.put(f"/courses/{course_id}", {"course": fields})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{course_id}", summary="Eliminar / concluir curso")
async def delete_course(
    course_id: str,
    event: Annotated[str, Query(description="delete | conclude")] = "conclude",
):
    try:
        return await canvas.delete(f"/courses/{course_id}", {"event": event})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
