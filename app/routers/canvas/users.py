"""Canvas user management endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.models.canvas import (
    BulkCanvasUserCreate,
    BulkResult,
    CanvasUserCreate,
    CanvasUserUpdate,
)
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/users", tags=["Canvas · Users"])
_ACCOUNT = settings.canvas_account_id


@router.get("", summary="Listar usuarios de la cuenta")
async def list_users(
    search_term: Annotated[str | None, Query(description="Buscar por nombre o email")] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    params: dict = {"per_page": per_page}
    if search_term:
        params["search_term"] = search_term
    return await canvas.paginate(f"/accounts/{_ACCOUNT}/users", params)


@router.get("/{user_id}", summary="Obtener usuario por ID")
async def get_user(user_id: str):
    try:
        return await canvas.get(f"/users/{user_id}/profile")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear usuario individual")
async def create_user(body: CanvasUserCreate):
    payload = {
        "user": {
            "name": body.name,
            "short_name": body.short_name or body.name,
            "sortable_name": body.sortable_name,
            "skip_registration": True,
        },
        "pseudonym": {
            "unique_id": body.login_id,
            "password": body.password,
            "send_confirmation": body.send_confirmation,
            "sis_user_id": body.sis_user_id,
        },
        "communication_channel": {
            "type": "email",
            "address": body.email,
            "skip_confirmation": True,
        },
    }
    try:
        return await canvas.post(f"/accounts/{_ACCOUNT}/users", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bulk", summary="Crear usuarios de forma masiva")
async def create_users_bulk(body: BulkCanvasUserCreate) -> BulkResult:
    result = BulkResult()

    async def _create(user: CanvasUserCreate):
        try:
            data = await canvas.post(
                f"/accounts/{_ACCOUNT}/users",
                {
                    "user": {"name": user.name, "short_name": user.short_name or user.name, "skip_registration": True},
                    "pseudonym": {"unique_id": user.login_id, "password": user.password, "sis_user_id": user.sis_user_id},
                    "communication_channel": {"type": "email", "address": user.email, "skip_confirmation": True},
                },
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": user.model_dump(), "error": str(exc)})

    await asyncio.gather(*[_create(u) for u in body.users])
    return result


@router.put("/{user_id}", summary="Actualizar usuario")
async def update_user(user_id: str, body: CanvasUserUpdate):
    payload: dict = {"user": {}}
    if body.name:
        payload["user"]["name"] = body.name
    if body.short_name:
        payload["user"]["short_name"] = body.short_name
    if body.email:
        payload["user"]["email"] = body.email
    try:
        return await canvas.put(f"/users/{user_id}", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{user_id}", summary="Eliminar usuario de la cuenta")
async def delete_user(user_id: str):
    try:
        return await canvas.delete(f"/accounts/{_ACCOUNT}/users/{user_id}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
