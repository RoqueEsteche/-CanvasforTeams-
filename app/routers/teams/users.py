"""Microsoft Teams / Azure AD user management endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models.teams import BulkResult, BulkTeamsUserCreate, TeamsUserCreate, TeamsUserUpdate
from app.services import teams_client as graph

router = APIRouter(prefix="/teams/users", tags=["Teams · Users"])


@router.get("", summary="Listar usuarios del directorio")
async def list_users(
    search: Annotated[str | None, Query(description="Buscar por displayName o userPrincipalName")] = None,
    top: Annotated[int, Query(ge=1, le=999)] = 50,
):
    params: dict = {"$top": top, "$select": "id,displayName,userPrincipalName,mail,department,jobTitle,accountEnabled"}
    if search:
        params["$search"] = f'"displayName:{search}" OR "userPrincipalName:{search}"'
    return await graph.paginate("/users", params)


@router.get("/{user_id}", summary="Obtener usuario por ID o UPN")
async def get_user(user_id: str):
    try:
        return await graph.get(f"/users/{user_id}")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear usuario individual en Azure AD")
async def create_user(body: TeamsUserCreate):
    payload = {
        "displayName": body.display_name,
        "givenName": body.given_name,
        "surname": body.surname,
        "userPrincipalName": body.user_principal_name,
        "mailNickname": body.mail_nickname,
        "department": body.department,
        "jobTitle": body.job_title,
        "usageLocation": body.usage_location,
        "accountEnabled": body.account_enabled,
        "passwordProfile": {
            "forceChangePasswordNextSignIn": True,
            "password": body.password,
        },
    }
    try:
        return await graph.post("/users", {k: v for k, v in payload.items() if v is not None})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bulk", summary="Crear usuarios de forma masiva en Azure AD")
async def create_users_bulk(body: BulkTeamsUserCreate) -> BulkResult:
    result = BulkResult()

    async def _create(user: TeamsUserCreate):
        try:
            payload = {
                "displayName": user.display_name,
                "userPrincipalName": user.user_principal_name,
                "mailNickname": user.mail_nickname,
                "usageLocation": user.usage_location,
                "accountEnabled": user.account_enabled,
                "passwordProfile": {"forceChangePasswordNextSignIn": True, "password": user.password},
            }
            if user.given_name:
                payload["givenName"] = user.given_name
            if user.surname:
                payload["surname"] = user.surname
            if user.department:
                payload["department"] = user.department
            if user.job_title:
                payload["jobTitle"] = user.job_title
            data = await graph.post("/users", payload)
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": user.model_dump(exclude={"password"}), "error": str(exc)})

    await asyncio.gather(*[_create(u) for u in body.users])
    return result


@router.patch("/{user_id}", summary="Actualizar usuario")
async def update_user(user_id: str, body: TeamsUserUpdate):
    fields = body.model_dump(exclude_none=True)
    # Convert snake_case → camelCase
    mapping = {
        "display_name": "displayName",
        "given_name": "givenName",
        "surname": "surname",
        "department": "department",
        "job_title": "jobTitle",
        "account_enabled": "accountEnabled",
    }
    payload = {mapping[k]: v for k, v in fields.items() if k in mapping}
    try:
        return await graph.patch(f"/users/{user_id}", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{user_id}", summary="Eliminar usuario de Azure AD")
async def delete_user(user_id: str):
    try:
        await graph.delete(f"/users/{user_id}")
        return {"deleted": user_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
