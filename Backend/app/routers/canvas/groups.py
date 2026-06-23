"""Canvas group management endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.models.canvas import CanvasGroupCreate, CanvasGroupMemberAdd, CanvasGroupMemberCreate, BulkResult
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/groups", tags=["Canvas · Groups"])
_ACCOUNT = settings.canvas_account_id


@router.get("", summary="Listar grupos de la cuenta")
async def list_groups(
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return await canvas.paginate(f"/accounts/{_ACCOUNT}/groups", {"per_page": per_page})


@router.get("/course/{course_id}", summary="Listar grupos de un curso")
async def list_course_groups(course_id: str):
    return await canvas.paginate(f"/courses/{course_id}/groups")


@router.get("/{group_id}", summary="Obtener grupo por ID")
async def get_group(group_id: str):
    try:
        return await canvas.get(f"/groups/{group_id}")
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear grupo en la cuenta")
async def create_group(body: CanvasGroupCreate):
    payload = {
        "name": body.name,
        "description": body.description,
        "is_public": body.is_public,
        "join_level": body.join_level,
    }
    if body.sis_group_id is not None:
        payload["sis_group_id"] = body.sis_group_id
    try:
        return await canvas.post(f"/accounts/{_ACCOUNT}/groups", payload)
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/course/{course_id}", status_code=201, summary="Crear grupo en un curso")
async def create_course_group(course_id: str, body: CanvasGroupCreate):
    payload = {
        "name": body.name,
        "description": body.description,
        "is_public": body.is_public,
        "join_level": body.join_level,
    }
    if body.sis_group_id is not None:
        payload["sis_group_id"] = body.sis_group_id
    try:
        return await canvas.post(f"/courses/{course_id}/groups", payload)
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _build_membership_payload(user_id: str, role: str = "member") -> dict:
    payload = {"user_id": user_id}
    if role == "owner":
        payload["role"] = "owner"
    return payload


@router.post("/{group_id}/members/add", status_code=201, summary="Añadir miembro individual al grupo")
async def add_member(group_id: str, body: CanvasGroupMemberCreate):
    try:
        return await canvas.post(
            f"/groups/{group_id}/memberships",
            _build_membership_payload(body.user_id, body.role),
        )
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{group_id}/members/bulk", summary="Añadir miembros de forma conjunta al grupo")
async def add_members(group_id: str, body: CanvasGroupMemberAdd) -> BulkResult:
    result = BulkResult()

    async def _add(user_id: str):
        try:
            data = await canvas.post(
                f"/groups/{group_id}/memberships",
                _build_membership_payload(user_id, body.role),
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"user_id": user_id, "error": str(exc)})

    await asyncio.gather(*[_add(uid) for uid in body.user_ids])
    return result


@router.put("/{group_id}", summary="Actualizar grupo en la cuenta")
async def update_group(group_id: str, body: CanvasGroupCreate):
    payload = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.description is not None:
        payload["description"] = body.description
    if body.is_public is not None:
        payload["is_public"] = body.is_public
    if body.join_level is not None:
        payload["join_level"] = body.join_level
    if body.sis_group_id is not None:
        payload["sis_group_id"] = body.sis_group_id
    try:
        return await canvas.put(f"/groups/{group_id}", payload)
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{group_id}/members", summary="Listar miembros del grupo")
async def list_members(group_id: str):
    return await canvas.paginate(f"/groups/{group_id}/users")


@router.delete("/{group_id}", summary="Eliminar grupo")
async def delete_group(group_id: str):
    try:
        return await canvas.delete(f"/groups/{group_id}")
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

