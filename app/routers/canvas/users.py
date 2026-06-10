"""Canvas user management endpoints."""
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.background import BackgroundTasks

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core import cache, audit, database
from app.models.canvas import (
    BulkCanvasUserCreate,
    BulkResult,
    CanvasUserCreate,
    CanvasUserUpdate,
)
from app.services import canvas_client as canvas
from app.services import auth as auth_service

router = APIRouter(prefix="/canvas/users", tags=["Canvas · Users"])
_ACCOUNT = settings.canvas_account_id
_BULK_SEM = asyncio.Semaphore(8)


class BulkDeleteRequest(BaseModel):
    ids: list[str]


_USERS_TTL = 3600  # 1h en caché, refresca en background


async def _fetch_and_cache_users(cache_key: str, params: dict, max_records: int) -> list:
    """Fetches users from Canvas API and stores in cache + DB."""
    try:
        result = await canvas.paginate_limited(
            f"/accounts/{_ACCOUNT}/users", params, max_records
        )
        await database.upsert_canvas_users(result)
        await database.mark_synced("canvas_users")
        cache.set(cache_key, result, ttl=_USERS_TTL)
        return result
    except Exception as exc:
        logger.error(f"Error refrescando caché de usuarios: {exc}")
        return []


@router.get("", summary="Listar usuarios de la cuenta")
async def list_users(
    background_tasks: BackgroundTasks,
    search_term: Annotated[str | None, Query(description="Buscar por nombre o email")] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 100,
    max_records: Annotated[int, Query(ge=1, le=10000)] = 5000,
):
    cache_key = f"canvas:users:{search_term or ''}:{per_page}:{max_records}"
    cached = cache.get(cache_key)

    params: dict = {"per_page": per_page}
    if search_term:
        params["search_term"] = search_term
        max_records = min(max_records, 100)

    if cached is not None:
        # Stale-while-revalidate: respuesta inmediata + refresco en background
        background_tasks.add_task(_fetch_and_cache_users, cache_key, params, max_records)
        return cached

    # Primera carga: esperar la API
    return await _fetch_and_cache_users(cache_key, params, max_records)


@router.get("/{user_id}", summary="Obtener usuario por ID")
async def get_user(user_id: str):
    try:
        return await canvas.get(f"/users/{user_id}/profile")
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear usuario individual")
async def create_user(body: CanvasUserCreate, request: Request):
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
        data = await canvas.post(f"/accounts/{_ACCOUNT}/users", payload)
        cache.patch_list("canvas:users:", data.get("id"), data, id_field="id", action="create")
        await database.upsert_canvas_users([data])
        user = auth_service.get_user_from_request(request)
        audit.log("create", "canvas_user", user=user.get("email","?") if user else "api",
                  detail=f"{body.name} ({body.login_id})")
        return data
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bulk", summary="Crear usuarios de forma masiva")
async def create_users_bulk(body: BulkCanvasUserCreate, request: Request) -> BulkResult:
    result = BulkResult()

    async def _create(user: CanvasUserCreate):
        async with _BULK_SEM:
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
    cache.invalidate("canvas:users:")
    req_user = auth_service.get_user_from_request(request)
    audit.log("import", "canvas_users_bulk",
              user=req_user.get("email","?") if req_user else "api",
              detail=f"{len(result.succeeded)} ok / {len(result.failed)} errores de {len(body.users)}")
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
        data = await canvas.put(f"/users/{user_id}", payload)
        cache.patch_list("canvas:users:", user_id, data, id_field="id", action="update")
        await database.upsert_canvas_users([data])
        return data
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/bulk", summary="Eliminar usuarios en masa")
async def delete_users_bulk(body: BulkDeleteRequest, request: Request) -> BulkResult:
    result = BulkResult()

    async def _del(uid: str):
        async with _BULK_SEM:
            try:
                await canvas.delete(f"/accounts/{_ACCOUNT}/users/{uid}")
                await database.delete_canvas_user(uid)
                result.succeeded.append({"id": uid})
            except Exception as exc:
                result.failed.append({"id": uid, "error": str(exc)})

    await asyncio.gather(*[_del(uid) for uid in body.ids])
    cache.invalidate("canvas:users:")
    req_user = auth_service.get_user_from_request(request)
    audit.log("delete", "canvas_users_bulk",
              user=req_user.get("email", "?") if req_user else "api",
              detail=f"{len(result.succeeded)} eliminados / {len(result.failed)} errores")
    return result


@router.delete("/{user_id}", summary="Eliminar usuario de la cuenta")
async def delete_user(user_id: str, request: Request):
    try:
        data = await canvas.delete(f"/accounts/{_ACCOUNT}/users/{user_id}")
        await database.delete_canvas_user(user_id)
        cache.patch_list("canvas:users:", user_id, None, id_field="id", action="delete")
        return data
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

