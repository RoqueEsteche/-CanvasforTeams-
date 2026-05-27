"""Microsoft Teams team/group management endpoints."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models.teams import (
    BulkResult,
    BulkTeamsMemberAdd,
    BulkTeamsMemberRemove,
    TeamsChannelCreate,
    TeamsMemberAdd,
    TeamsTeamCreate,
    TeamsTeamUpdate,
)
from app.services import teams_client as graph
from app.services.teams_client import post_team

router = APIRouter(prefix="/teams/teams", tags=["Teams · Teams"])

# Template OData types used by the Teams provisioning API
_TEMPLATES = {
    "standard": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
    "educationClass": "https://graph.microsoft.com/v1.0/teamsTemplates('educationClass')",
    "educationStaff": "https://graph.microsoft.com/v1.0/teamsTemplates('educationStaff')",
    "educationProfessionalLearningCommunity": "https://graph.microsoft.com/v1.0/teamsTemplates('educationProfessionalLearningCommunity')",
}


@router.get("", summary="Listar todos los Teams del tenant")
async def list_teams(
    top: Annotated[int, Query(ge=1, le=999)] = 50,
):
    params = {
        "$top": top,
        "$select": "id,displayName,description,visibility",
        "$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')",
    }
    return await graph.paginate("/groups", params)


@router.get("/{team_id}", summary="Obtener Team por ID")
async def get_team(team_id: str):
    try:
        return await graph.get(f"/teams/{team_id}")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear Team (con plantilla educativa opcional)")
async def create_team(body: TeamsTeamCreate):
    template_url = _TEMPLATES.get(body.template, _TEMPLATES["educationClass"])
    payload = {
        "template@odata.bind": template_url,
        "displayName": body.display_name,
        "description": body.description or "",
        "visibility": body.visibility,
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.owner_id}')",
            }
        ],
    }
    try:
        # Teams creation is async (202); post_team polls until provisioned
        return await post_team(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{team_id}", summary="Actualizar Team")
async def update_team(team_id: str, body: TeamsTeamUpdate):
    fields = body.model_dump(exclude_none=True)
    mapping = {"display_name": "displayName", "description": "description", "visibility": "visibility"}
    payload = {mapping[k]: v for k, v in fields.items() if k in mapping}
    try:
        return await graph.patch(f"/teams/{team_id}", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{team_id}", summary="Eliminar Team")
async def delete_team(team_id: str):
    try:
        await graph.delete(f"/groups/{team_id}")
        return {"deleted": team_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Members ───────────────────────────────────────────────────────────────────

@router.get("/{team_id}/members", summary="Listar miembros del Team")
async def list_members(team_id: str):
    return await graph.paginate(f"/teams/{team_id}/members")


@router.post("/{team_id}/members", status_code=201, summary="Añadir miembro individual")
async def add_member(team_id: str, body: TeamsMemberAdd):
    payload = {
        "@odata.type": "#microsoft.graph.aadUserConversationMember",
        "roles": [body.role] if body.role == "owner" else [],
        "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.user_id}')",
    }
    try:
        return await graph.post(f"/teams/{team_id}/members", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{team_id}/members/bulk-add", summary="Añadir miembros de forma masiva")
async def bulk_add_members(team_id: str, body: BulkTeamsMemberAdd) -> BulkResult:
    # Graph supports up to 20 members per batch via addMembers action
    result = BulkResult()
    BATCH_SIZE = 20

    members_payload = [
        {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": [m.role] if m.role == "owner" else [],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{m.user_id}')",
        }
        for m in body.members
    ]

    for i in range(0, len(members_payload), BATCH_SIZE):
        batch = members_payload[i : i + BATCH_SIZE]
        try:
            resp = await graph.post(f"/teams/{team_id}/members/add", {"values": batch})
            added = resp.get("value", [])
            errors = resp.get("error", [])
            result.succeeded.extend(added)
            result.failed.extend(errors)
        except Exception as exc:
            for m in body.members[i : i + BATCH_SIZE]:
                result.failed.append({"user_id": m.user_id, "error": str(exc)})

    return result


@router.delete("/{team_id}/members/{membership_id}", summary="Quitar miembro del Team")
async def remove_member(team_id: str, membership_id: str):
    try:
        await graph.delete(f"/teams/{team_id}/members/{membership_id}")
        return {"removed": membership_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{team_id}/members/bulk-remove", summary="Quitar miembros de forma masiva")
async def bulk_remove_members(team_id: str, body: BulkTeamsMemberRemove) -> BulkResult:
    result = BulkResult()

    # Retrieve current members to map user_id → membership_id
    try:
        members = await graph.paginate(f"/teams/{team_id}/members")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    id_to_membership = {m.get("userId"): m.get("id") for m in members}

    async def _remove(user_id: str):
        membership_id = id_to_membership.get(user_id)
        if not membership_id:
            result.failed.append({"user_id": user_id, "error": "Member not found in team"})
            return
        try:
            await graph.delete(f"/teams/{team_id}/members/{membership_id}")
            result.succeeded.append({"user_id": user_id, "removed": True})
        except Exception as exc:
            result.failed.append({"user_id": user_id, "error": str(exc)})

    await asyncio.gather(*[_remove(uid) for uid in body.user_ids])
    return result


# ── Channels ─────────────────────────────────────────────────────────────────

@router.get("/{team_id}/channels", summary="Listar canales del Team")
async def list_channels(team_id: str):
    return await graph.paginate(f"/teams/{team_id}/channels")


@router.post("/{team_id}/channels", status_code=201, summary="Crear canal en el Team")
async def create_channel(team_id: str, body: TeamsChannelCreate):
    payload = {
        "displayName": body.display_name,
        "description": body.description or "",
        "membershipType": body.membership_type,
    }
    try:
        return await graph.post(f"/teams/{team_id}/channels", payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
