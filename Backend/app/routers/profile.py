import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services import auth as auth_service
from app.services import canvas_client as canvas
from app.services import teams_client as graph

router = APIRouter(prefix="/profile", tags=["Profile"])
_ACCOUNT = settings.canvas_account_id


def get_current_user(request: Request) -> dict:
    user = auth_service.get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="No estás autenticado")
    return user


async def _find_canvas_user(identifier: str) -> dict | None:
    if not identifier:
        return None
    
    identifier = identifier.strip()
    
    # Si es numérico (C.I.), busca al usuario usando sis_user_id:{cedula}
    if identifier.replace("-", "").replace(".", "").isdigit():
        try:
            return await canvas.get(f"/users/sis_user_id:{identifier}")
        except Exception:
            pass

    # Si contiene @ o es texto, intentamos buscar por sis_user_id:{email} primero
    if "@" in identifier:
        try:
            return await canvas.get(f"/users/sis_user_id:{identifier}")
        except Exception:
            pass

    try:
        users = await canvas.paginate(f"/accounts/{_ACCOUNT}/users", {"search_term": identifier, "per_page": 100})
    except Exception:
        return None
        
    local = identifier.split("@")[0] if "@" in identifier else identifier
    # Priority: exact match on login_id or email fields first
    for user in users:
        if (user.get("login_id") == identifier
                or user.get("email") == identifier
                or user.get("sis_user_id") == identifier
                or user.get("login_id") == local):
            return user
    return users[0] if users else None


async def _canvas_enrollments(uid: str) -> tuple[list, list]:
    """Return (enriched_enrollments, groups). Groups may be empty if Canvas blocks the endpoint."""
    # All enrollment types — students, teachers, TAs, observers
    try:
        raw = await canvas.paginate(
            f"/users/{uid}/enrollments", {"per_page": 100}
        )
    except Exception:
        return [], []

    # Fetch course details in parallel
    course_ids = list({str(e.get("course_id")) for e in raw if e.get("course_id")})

    async def _get_course(cid: str) -> tuple[str, dict]:
        try:
            return cid, await canvas.get(f"/courses/{cid}")
        except Exception:
            return cid, {}

    course_results = await asyncio.gather(*[_get_course(cid) for cid in course_ids])
    courses = dict(course_results)

    enriched = []
    for e in raw:
        course = courses.get(str(e.get("course_id")), {})
        enriched.append({
            "id":              e.get("id"),
            "course_id":       e.get("course_id"),
            "course_name":     course.get("name") or e.get("course_name") or "Sin nombre",
            "course_code":     course.get("course_code") or e.get("course_code"),
            "role":            e.get("type"),
            "enrollment_state": e.get("enrollment_state"),
            "program":         _extract_program(course),
            "year":            _extract_year(course),
            "start_at":        course.get("start_at"),
            "end_at":          course.get("end_at"),
        })

    # Groups: Canvas requires user impersonation for /users/{id}/groups with admin token.
    # Try the endpoint; return empty list if it fails.
    groups: list = []
    try:
        groups = await canvas.paginate(f"/users/{uid}/groups", {"per_page": 100})
    except Exception:
        pass

    return enriched, groups


def _extract_program(course: dict) -> str:
    code = course.get("course_code") or ""
    if "-" in code:
        return code.split("-")[0]
    name = course.get("name", "")
    return name.split()[0] if name else "Sin programa"


def _extract_year(course: dict) -> str:
    start_at = course.get("start_at")
    if start_at and len(start_at) >= 4:
        return start_at[:4]
    return "Sin año"


@router.get("/me", summary="Obtener datos del usuario autenticado")
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.get("/canvas", summary="Obtener perfil Canvas del usuario")
async def canvas_profile(
    program: Annotated[str | None, Query()] = None,
    year: Annotated[str | None, Query()] = None,
    current_user: dict = Depends(get_current_user),
):
    email = current_user["email"]
    canvas_user = await _find_canvas_user(email)
    if not canvas_user:
        raise HTTPException(status_code=404, detail="Usuario Canvas no encontrado")

    user_id = str(canvas_user.get("id"))
    enrollments, groups = await _canvas_enrollments(user_id)

    if program or year:
        enrollments = [
            e for e in enrollments
            if (not program or program.lower() in str(e["program"]).lower())
            and (not year or year == e["year"])
        ]

    return {
        "canvas_user": {"id": user_id, "name": canvas_user.get("name"), "email": canvas_user.get("email")},
        "enrollments": enrollments,
        "groups": groups,
    }


_GRAPH_USER_SELECT = (
    "id,displayName,mail,userPrincipalName,department,jobTitle,"
    "accountEnabled,officeLocation,mobilePhone,businessPhones,usageLocation"
)


async def _find_graph_user(email: str) -> dict | None:
    """Try multiple identifier formats to find a user in Azure AD."""
    for identifier in [email, email.split("@")[0]]:
        try:
            return await graph.get(f"/users/{identifier}", {"$select": _GRAPH_USER_SELECT})
        except Exception:
            pass
    try:
        result = await graph.get("/users", {
            "$filter": f"mail eq '{email}' or userPrincipalName eq '{email}'",
            "$select": _GRAPH_USER_SELECT,
            "$top": 1,
        })
        users = result.get("value", []) if isinstance(result, dict) else []
        return users[0] if users else None
    except Exception:
        return None


async def _graph_user_to_dict(az_user: dict) -> dict:
    phones = az_user.get("businessPhones") or []
    return {
        "id":                 az_user.get("id"),
        "displayName":        az_user.get("displayName"),
        "mail":               az_user.get("mail"),
        "userPrincipalName":  az_user.get("userPrincipalName"),
        "department":         az_user.get("department"),
        "jobTitle":           az_user.get("jobTitle"),
        "officeLocation":     az_user.get("officeLocation"),
        "mobilePhone":        az_user.get("mobilePhone"),
        "phone":              phones[0] if phones else None,
        "usageLocation":      az_user.get("usageLocation"),
        "accountEnabled":     az_user.get("accountEnabled"),
    }


async def _teams_with_channels(user_id: str) -> list[dict]:
    """Return joined teams, each with a (possibly empty) channels list."""
    try:
        raw_teams = await graph.paginate(f"/users/{user_id}/joinedTeams")
    except Exception:
        return []

    async def _get_channels(team: dict) -> dict:
        try:
            channels = await graph.paginate(f"/teams/{team['id']}/channels")
            ch = [{"id": c.get("id"), "displayName": c.get("displayName"),
                   "membershipType": c.get("membershipType", "standard")} for c in channels]
        except Exception:
            ch = []
        return {
            "id":          team.get("id"),
            "displayName": team.get("displayName"),
            "description": team.get("description"),
            "visibility":  team.get("visibility"),
            "channels":    ch,
        }

    return list(await asyncio.gather(*[_get_channels(t) for t in raw_teams]))


@router.get("/teams", summary="Obtener perfil Teams del usuario")
async def teams_profile(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    az_user = await _find_graph_user(email)
    if not az_user:
        raise HTTPException(status_code=404, detail=f"Usuario '{email}' no encontrado en Azure AD")

    teams = await _teams_with_channels(az_user["id"])

    return {
        "teams_user": await _graph_user_to_dict(az_user),
        "teams":      teams,
    }


@router.get("/lookup", summary="Ver perfil completo de cualquier usuario")
async def lookup_user_profile(
    email: Annotated[str | None, Query(description="Email, login o C.I. del usuario")] = None,
    canvas_id: Annotated[str | None, Query(description="ID Canvas del usuario")] = None,
):
    if not email and not canvas_id:
        raise HTTPException(status_code=400, detail="Especificá email (o C.I.) o canvas_id")

    result: dict[str, Any] = {}
    identifier = email

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas_user = None
    if canvas_id:
        try:
            canvas_user = await canvas.get(f"/users/{canvas_id}/profile")
        except Exception:
            pass
    if canvas_user is None and identifier:
        canvas_user = await _find_canvas_user(identifier)

    if canvas_user:
        uid = str(canvas_user.get("id"))
        enrollments, groups = await _canvas_enrollments(uid)
        # Derive email for Teams lookup — prefer any field that looks like an email
        if not identifier or "@" not in identifier:
            for _field in ("primary_email", "email", "login_id", "sis_user_id"):
                _val = canvas_user.get(_field) or ""
                if "@" in _val:
                    identifier = _val
                    break
        result["canvas"] = {
            "user": {
                "id": uid,
                "name": canvas_user.get("name"),
                "email": canvas_user.get("primary_email") or canvas_user.get("email"),
                "login_id": canvas_user.get("login_id"),
                "sis_user_id": canvas_user.get("sis_user_id"),
                "avatar_url": canvas_user.get("avatar_url"),
            },
            "enrollments": enrollments,
            "groups": [{"id": g.get("id"), "name": g.get("name"),
                        "course_id": g.get("course_id")} for g in groups],
        }
    else:
        result["canvas"] = None

    # ── Teams ─────────────────────────────────────────────────────────────────
    teams_email = identifier if identifier and "@" in identifier else None
    if teams_email:
        az_user = await _find_graph_user(teams_email)
        if az_user:
            teams_list = await _teams_with_channels(az_user["id"])
            result["teams"] = {
                "user": await _graph_user_to_dict(az_user),
                "teams": teams_list,
            }
        else:
            result["teams"] = None
    else:
        result["teams"] = None

    if not result.get("canvas") and not result.get("teams"):
        raise HTTPException(status_code=404, detail=f"No se encontraron registros para '{identifier}' ni en Canvas ni en Teams.")

    return result


class ResetPasswordPayload(BaseModel):
    password: str


@router.post("/teams/reset-password", summary="Restablecer contraseña de Teams")
async def reset_password(body: ResetPasswordPayload, current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    user = await graph.get(f"/users/{email}")
    payload = {
        "passwordProfile": {
            "forceChangePasswordNextSignIn": True,
            "password": body.password,
        }
    }
    return await graph.patch(f"/users/{user['id']}", payload)
