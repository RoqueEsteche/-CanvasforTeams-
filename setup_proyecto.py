"""
Setup script — crea el proyecto completo en tu PC.
Uso: python setup_proyecto.py
"""
import os, sys, subprocess, textwrap

BASE = os.path.join(os.path.expanduser("~"), "CanvasTeamsAPI")

FILES = {}

FILES["requirements.txt"] = """\
fastapi==0.115.5
uvicorn[standard]==0.32.1
httpx==0.27.2
pydantic[email]==2.9.2
pydantic-settings==2.6.1
python-dotenv==1.0.1
msal==1.31.0
tenacity==9.0.0
python-multipart==0.0.12
"""

FILES[".env.example"] = """\
# Canvas LMS
CANVAS_BASE_URL=https://tuinstancia.instructure.com
CANVAS_ACCESS_TOKEN=tu_token_canvas_aqui
CANVAS_ACCOUNT_ID=1

# Microsoft Entra / Azure AD
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=tu_secreto_azure_aqui

PORT=3000
ENVIRONMENT=development
"""

FILES[".gitignore"] = """\
.env
__pycache__/
*.pyc
.venv/
venv/
"""

FILES["app/__init__.py"] = ""

FILES["app/core/__init__.py"] = ""

FILES["app/core/config.py"] = """\
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    canvas_base_url: str = "https://canvas.instructure.com"
    canvas_access_token: str = ""
    canvas_account_id: str = "1"
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    port: int = 3000
    environment: str = "development"

settings = Settings()
"""

FILES["app/models/__init__.py"] = ""

FILES["app/models/canvas.py"] = """\
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field

class CanvasUserCreate(BaseModel):
    name: str = Field(..., examples=["Juan García"])
    short_name: Optional[str] = None
    sortable_name: Optional[str] = None
    email: EmailStr
    login_id: str = Field(..., examples=["jgarcia"])
    password: Optional[str] = None
    sis_user_id: Optional[str] = None
    send_confirmation: bool = False

class CanvasUserUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    email: Optional[EmailStr] = None
    login_id: Optional[str] = None
    sis_user_id: Optional[str] = None

class CanvasCourseCreate(BaseModel):
    name: str = Field(..., examples=["Matemáticas I"])
    course_code: Optional[str] = Field(None, examples=["MAT-001"])
    sis_course_id: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    license: Optional[str] = "public_domain"
    is_public: bool = False
    enroll_me: bool = False

class CanvasCourseUpdate(BaseModel):
    name: Optional[str] = None
    course_code: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    workflow_state: Optional[Literal["unpublished","available","completed","deleted"]] = None

EnrollmentType = Literal[
    "StudentEnrollment","TeacherEnrollment","TaEnrollment",
    "DesignerEnrollment","ObserverEnrollment"
]

class CanvasEnrollmentCreate(BaseModel):
    user_id: str = Field(..., examples=["123"])
    type: EnrollmentType = "StudentEnrollment"
    enrollment_state: Literal["active","invited","inactive"] = "active"
    notify: bool = False
    role_id: Optional[str] = None
    course_section_id: Optional[str] = None

class CanvasGroupCreate(BaseModel):
    name: str = Field(..., examples=["Grupo A"])
    description: Optional[str] = None
    is_public: bool = False
    join_level: Literal["parent_context_auto_join","parent_context_request","invitation_only"] = "invitation_only"
    sis_group_id: Optional[str] = None

class CanvasGroupMemberAdd(BaseModel):
    user_ids: list[str] = Field(..., examples=[["1","2","3"]])

class BulkCanvasUserCreate(BaseModel):
    users: list[CanvasUserCreate]

class BulkCanvasCourseCreate(BaseModel):
    courses: list[CanvasCourseCreate]

class BulkCanvasEnrollmentCreate(BaseModel):
    course_id: str
    enrollments: list[CanvasEnrollmentCreate]

class BulkCanvasEnrollmentDelete(BaseModel):
    course_id: str
    enrollment_ids: list[str]
    task: Literal["delete","conclude","deactivate","inactivate"] = "conclude"

class BulkResult(BaseModel):
    succeeded: list[dict] = []
    failed: list[dict] = []
"""

FILES["app/models/teams.py"] = """\
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

class TeamsUserCreate(BaseModel):
    display_name: str = Field(..., examples=["Juan García"])
    given_name: Optional[str] = None
    surname: Optional[str] = None
    user_principal_name: str = Field(..., examples=["jgarcia@usil.edu.py"])
    mail_nickname: str = Field(..., examples=["jgarcia"])
    password: str = Field(..., min_length=8)
    department: Optional[str] = None
    job_title: Optional[str] = None
    usage_location: str = Field("PY", description="ISO 3166-1 alpha-2")
    account_enabled: bool = True

class TeamsUserUpdate(BaseModel):
    display_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    account_enabled: Optional[bool] = None

class TeamsTeamCreate(BaseModel):
    display_name: str = Field(..., examples=["Matemáticas I - 2025"])
    description: Optional[str] = None
    mail_nickname: str = Field(..., examples=["mat-i-2025"])
    visibility: Literal["Public","Private","HiddenMembership"] = "Private"
    template: Literal["standard","educationClass","educationStaff","educationProfessionalLearningCommunity"] = "educationClass"
    owner_id: str = Field(..., description="Azure AD object ID del propietario")

class TeamsTeamUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[Literal["Public","Private"]] = None

MemberRole = Literal["member","owner"]

class TeamsMemberAdd(BaseModel):
    user_id: str = Field(..., description="Azure AD object ID del usuario")
    role: MemberRole = "member"

class TeamsChannelCreate(BaseModel):
    display_name: str = Field(..., examples=["Anuncios del curso"])
    description: Optional[str] = None
    membership_type: Literal["standard","private","shared"] = "standard"

class BulkTeamsUserCreate(BaseModel):
    users: list[TeamsUserCreate]

class BulkTeamsMemberAdd(BaseModel):
    team_id: str
    members: list[TeamsMemberAdd]

class BulkTeamsMemberRemove(BaseModel):
    team_id: str
    user_ids: list[str]

class BulkResult(BaseModel):
    succeeded: list[dict] = []
    failed: list[dict] = []
"""

FILES["app/services/__init__.py"] = ""

FILES["app/services/canvas_client.py"] = """\
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings

_BASE = f"{settings.canvas_base_url.rstrip('/')}/api/v1"
_HEADERS = {"Authorization": f"Bearer {settings.canvas_access_token}"}
_TIMEOUT = httpx.Timeout(30.0)

def _client():
    return httpx.AsyncClient(base_url=_BASE, headers=_HEADERS, timeout=_TIMEOUT)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def get(path: str, params: dict | None = None) -> Any:
    async with _client() as c:
        r = await c.get(path, params=params); r.raise_for_status(); return r.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def post(path: str, payload: dict) -> Any:
    async with _client() as c:
        r = await c.post(path, json=payload); r.raise_for_status(); return r.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def put(path: str, payload: dict) -> Any:
    async with _client() as c:
        r = await c.put(path, json=payload); r.raise_for_status(); return r.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def delete(path: str, params: dict | None = None) -> Any:
    async with _client() as c:
        r = await c.delete(path, params=params); r.raise_for_status()
        return r.json() if r.content else {}

async def paginate(path: str, params: dict | None = None) -> list[Any]:
    results: list[Any] = []
    params = dict(params or {}); params.setdefault("per_page", 100)
    next_url: str | None = path
    async with _client() as c:
        while next_url:
            kw = {"params": params} if next_url == path else {}
            r = await c.get(next_url, **kw); r.raise_for_status()
            data = r.json()
            results.extend(data if isinstance(data, list) else [data])
            link = r.headers.get("Link", "")
            next_url = next(
                (s.strip().strip("<>") for s in (p.split(";")[0] for p in link.split(","))
                 if 'rel="next"' in p), None)
    return results
"""

FILES["app/services/teams_client.py"] = """\
import asyncio, re, time
from typing import Any
import httpx, msal
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings

_GRAPH   = "https://graph.microsoft.com/v1.0"
_SCOPE   = ["https://graph.microsoft.com/.default"]
_TIMEOUT = httpx.Timeout(30.0)
_cache: dict = {"access_token": None, "expires_at": 0}

def _get_access_token() -> str:
    if _cache["access_token"] and time.time() < _cache["expires_at"] - 60:
        return _cache["access_token"]
    app = msal.ConfidentialClientApplication(
        client_id=settings.azure_client_id,
        client_credential=settings.azure_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}")
    result = app.acquire_token_for_client(scopes=_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"MSAL: {result.get('error_description', result)}")
    _cache["access_token"] = result["access_token"]
    _cache["expires_at"] = time.time() + result.get("expires_in", 3600)
    return result["access_token"]

def _h() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/json"}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_GRAPH}{path}", headers=_h(), params=params)
        r.raise_for_status(); return r.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def post(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}{path}", headers=_h(), json=payload)
        r.raise_for_status(); return r.json() if r.content else {}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def patch(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.patch(f"{_GRAPH}{path}", headers=_h(), json=payload)
        r.raise_for_status(); return r.json() if r.content else {}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def delete(path: str) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.delete(f"{_GRAPH}{path}", headers=_h()); r.raise_for_status()

async def paginate(path: str, params: dict | None = None) -> list[Any]:
    results: list[Any] = []
    next_url: str | None = f"{_GRAPH}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        while next_url:
            kw = {"params": params} if next_url == f"{_GRAPH}{path}" else {}
            r = await c.get(next_url, headers=_h(), **kw); r.raise_for_status()
            data = r.json(); results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
    return results

async def post_team(payload: dict, poll_timeout: int = 60) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}/teams", headers=_h(), json=payload)
        if r.status_code in (200, 201) and r.content:
            return r.json()
        if r.status_code != 202:
            r.raise_for_status()
        location = r.headers.get("Location") or r.headers.get("Content-Location", "")
        m = re.search(r"teams\\('([^']+)'\\)", location) or re.search(r"teams/([0-9a-f-]{36})", location)
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            await asyncio.sleep(3)
            if m:
                try:
                    rp = await c.get(f"{_GRAPH}/teams/{m.group(1)}", headers=_h())
                    if rp.status_code == 200:
                        return rp.json()
                except Exception:
                    pass
        raise TimeoutError(f"Team provisioning timeout. Location: {location}")
"""

FILES["app/routers/__init__.py"] = ""
FILES["app/routers/canvas/__init__.py"] = ""
FILES["app/routers/teams/__init__.py"] = ""

FILES["app/routers/canvas/users.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.models.canvas import BulkCanvasUserCreate, BulkResult, CanvasUserCreate, CanvasUserUpdate
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/users", tags=["Canvas · Users"])
_ACC = settings.canvas_account_id

@router.get("", summary="Listar usuarios")
async def list_users(search_term: Annotated[str|None,Query()]=None, per_page: Annotated[int,Query(ge=1,le=100)]=50):
    p: dict = {"per_page": per_page}
    if search_term: p["search_term"] = search_term
    return await canvas.paginate(f"/accounts/{_ACC}/users", p)

@router.get("/{user_id}", summary="Obtener usuario")
async def get_user(user_id: str):
    try: return await canvas.get(f"/users/{user_id}/profile")
    except Exception as e: raise HTTPException(404, str(e))

@router.post("", status_code=201, summary="Crear usuario")
async def create_user(body: CanvasUserCreate):
    try:
        return await canvas.post(f"/accounts/{_ACC}/users", {
            "user": {"name": body.name, "short_name": body.short_name or body.name, "skip_registration": True},
            "pseudonym": {"unique_id": body.login_id, "password": body.password, "sis_user_id": body.sis_user_id,
                          "send_confirmation": body.send_confirmation},
            "communication_channel": {"type": "email", "address": body.email, "skip_confirmation": True}})
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/bulk", summary="Crear usuarios masivo")
async def create_users_bulk(body: BulkCanvasUserCreate) -> BulkResult:
    result = BulkResult()
    async def _c(u: CanvasUserCreate):
        try:
            data = await canvas.post(f"/accounts/{_ACC}/users", {
                "user": {"name": u.name, "skip_registration": True},
                "pseudonym": {"unique_id": u.login_id, "password": u.password, "sis_user_id": u.sis_user_id},
                "communication_channel": {"type": "email", "address": u.email, "skip_confirmation": True}})
            result.succeeded.append(data)
        except Exception as e: result.failed.append({"input": u.model_dump(), "error": str(e)})
    await asyncio.gather(*[_c(u) for u in body.users])
    return result

@router.put("/{user_id}", summary="Actualizar usuario")
async def update_user(user_id: str, body: CanvasUserUpdate):
    p: dict = {}
    if body.name: p["name"] = body.name
    if body.short_name: p["short_name"] = body.short_name
    if body.email: p["email"] = body.email
    try: return await canvas.put(f"/users/{user_id}", {"user": p})
    except Exception as e: raise HTTPException(400, str(e))

@router.delete("/{user_id}", summary="Eliminar usuario")
async def delete_user(user_id: str):
    try: return await canvas.delete(f"/accounts/{_ACC}/users/{user_id}")
    except Exception as e: raise HTTPException(400, str(e))
"""

FILES["app/routers/canvas/courses.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.models.canvas import BulkCanvasCourseCreate, BulkResult, CanvasCourseCreate, CanvasCourseUpdate
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/courses", tags=["Canvas · Courses"])
_ACC = settings.canvas_account_id

@router.get("", summary="Listar cursos")
async def list_courses(search_term: Annotated[str|None,Query()]=None, per_page: Annotated[int,Query(ge=1,le=100)]=50):
    p: dict = {"per_page": per_page}
    if search_term: p["search_term"] = search_term
    return await canvas.paginate(f"/accounts/{_ACC}/courses", p)

@router.get("/{course_id}", summary="Obtener curso")
async def get_course(course_id: str):
    try: return await canvas.get(f"/courses/{course_id}")
    except Exception as e: raise HTTPException(404, str(e))

@router.post("", status_code=201, summary="Crear curso")
async def create_course(body: CanvasCourseCreate):
    payload = {"course": {"name": body.name, "course_code": body.course_code,
               "sis_course_id": body.sis_course_id, "start_at": body.start_at,
               "end_at": body.end_at, "license": body.license, "is_public": body.is_public}}
    if body.enroll_me: payload["enroll_me"] = True
    try: return await canvas.post(f"/accounts/{_ACC}/courses", payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/bulk", summary="Crear cursos masivo")
async def create_courses_bulk(body: BulkCanvasCourseCreate) -> BulkResult:
    result = BulkResult()
    async def _c(co: CanvasCourseCreate):
        try:
            data = await canvas.post(f"/accounts/{_ACC}/courses",
                {"course": {"name": co.name, "course_code": co.course_code,
                 "sis_course_id": co.sis_course_id, "start_at": co.start_at, "end_at": co.end_at}})
            result.succeeded.append(data)
        except Exception as e: result.failed.append({"input": co.model_dump(), "error": str(e)})
    await asyncio.gather(*[_c(c) for c in body.courses])
    return result

@router.put("/{course_id}", summary="Actualizar curso")
async def update_course(course_id: str, body: CanvasCourseUpdate):
    try: return await canvas.put(f"/courses/{course_id}", {"course": body.model_dump(exclude_none=True)})
    except Exception as e: raise HTTPException(400, str(e))

@router.delete("/{course_id}", summary="Eliminar/concluir curso")
async def delete_course(course_id: str, event: Annotated[str,Query(description="delete|conclude")]="conclude"):
    try: return await canvas.delete(f"/courses/{course_id}", {"event": event})
    except Exception as e: raise HTTPException(400, str(e))
"""

FILES["app/routers/canvas/enrollments.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.models.canvas import BulkCanvasEnrollmentCreate, BulkCanvasEnrollmentDelete, BulkResult, CanvasEnrollmentCreate
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/courses/{course_id}/enrollments", tags=["Canvas · Enrollments"])

@router.get("", summary="Listar matrículas")
async def list_enrollments(course_id: str, per_page: Annotated[int,Query(ge=1,le=100)]=50):
    return await canvas.paginate(f"/courses/{course_id}/enrollments", {"per_page": per_page})

@router.post("", status_code=201, summary="Matricular usuario")
async def enroll_user(course_id: str, body: CanvasEnrollmentCreate):
    p = {"enrollment": {"user_id": body.user_id, "type": body.type,
          "enrollment_state": body.enrollment_state, "notify": body.notify}}
    if body.role_id: p["enrollment"]["role_id"] = body.role_id
    if body.course_section_id: p["enrollment"]["course_section_id"] = body.course_section_id
    try: return await canvas.post(f"/courses/{course_id}/enrollments", p)
    except Exception as e: raise HTTPException(400, str(e))

@router.delete("/{enrollment_id}", summary="Desmatricular usuario")
async def unenroll_user(course_id: str, enrollment_id: str,
                        task: Annotated[str,Query(description="delete|conclude|deactivate|inactivate")]="conclude"):
    try: return await canvas.delete(f"/courses/{course_id}/enrollments/{enrollment_id}", {"task": task})
    except Exception as e: raise HTTPException(400, str(e))

bulk_router = APIRouter(prefix="/canvas/enrollments/bulk", tags=["Canvas · Enrollments"])

@bulk_router.post("/enroll", summary="Matricular masivo")
async def bulk_enroll(body: BulkCanvasEnrollmentCreate) -> BulkResult:
    result = BulkResult()
    async def _e(e: CanvasEnrollmentCreate):
        try:
            data = await canvas.post(f"/courses/{body.course_id}/enrollments",
                {"enrollment": {"user_id": e.user_id, "type": e.type,
                 "enrollment_state": e.enrollment_state, "notify": e.notify}})
            result.succeeded.append(data)
        except Exception as ex: result.failed.append({"input": e.model_dump(), "error": str(ex)})
    await asyncio.gather(*[_e(e) for e in body.enrollments])
    return result

@bulk_router.post("/unenroll", summary="Desmatricular masivo")
async def bulk_unenroll(body: BulkCanvasEnrollmentDelete) -> BulkResult:
    result = BulkResult()
    async def _u(eid: str):
        try:
            data = await canvas.delete(f"/courses/{body.course_id}/enrollments/{eid}", {"task": body.task})
            result.succeeded.append({"enrollment_id": eid, **data})
        except Exception as e: result.failed.append({"enrollment_id": eid, "error": str(e)})
    await asyncio.gather(*[_u(eid) for eid in body.enrollment_ids])
    return result
"""

FILES["app/routers/canvas/groups.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.models.canvas import CanvasGroupCreate, CanvasGroupMemberAdd, BulkResult
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/groups", tags=["Canvas · Groups"])
_ACC = settings.canvas_account_id

@router.get("", summary="Listar grupos")
async def list_groups(per_page: Annotated[int,Query(ge=1,le=100)]=50):
    return await canvas.paginate(f"/accounts/{_ACC}/groups", {"per_page": per_page})

@router.get("/course/{course_id}", summary="Grupos de un curso")
async def list_course_groups(course_id: str):
    return await canvas.paginate(f"/courses/{course_id}/groups")

@router.get("/{group_id}", summary="Obtener grupo")
async def get_group(group_id: str):
    try: return await canvas.get(f"/groups/{group_id}")
    except Exception as e: raise HTTPException(404, str(e))

@router.post("", status_code=201, summary="Crear grupo en cuenta")
async def create_group(body: CanvasGroupCreate):
    try: return await canvas.post(f"/accounts/{_ACC}/groups",
        {"name": body.name, "description": body.description, "is_public": body.is_public,
         "join_level": body.join_level, "sis_group_id": body.sis_group_id})
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/course/{course_id}", status_code=201, summary="Crear grupo en curso")
async def create_course_group(course_id: str, body: CanvasGroupCreate):
    try: return await canvas.post(f"/courses/{course_id}/groups",
        {"name": body.name, "description": body.description,
         "is_public": body.is_public, "join_level": body.join_level})
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/{group_id}/members", summary="Añadir miembros al grupo")
async def add_members(group_id: str, body: CanvasGroupMemberAdd) -> BulkResult:
    result = BulkResult()
    async def _a(uid: str):
        try: result.succeeded.append(await canvas.post(f"/groups/{group_id}/memberships", {"user_id": uid}))
        except Exception as e: result.failed.append({"user_id": uid, "error": str(e)})
    await asyncio.gather(*[_a(uid) for uid in body.user_ids])
    return result

@router.get("/{group_id}/members", summary="Listar miembros")
async def list_members(group_id: str):
    return await canvas.paginate(f"/groups/{group_id}/users")

@router.delete("/{group_id}", summary="Eliminar grupo")
async def delete_group(group_id: str):
    try: return await canvas.delete(f"/groups/{group_id}")
    except Exception as e: raise HTTPException(400, str(e))
"""

FILES["app/routers/teams/users.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.models.teams import BulkResult, BulkTeamsUserCreate, TeamsUserCreate, TeamsUserUpdate
from app.services import teams_client as graph

router = APIRouter(prefix="/teams/users", tags=["Teams · Users"])

@router.get("", summary="Listar usuarios Azure AD")
async def list_users(search: Annotated[str|None,Query()]=None, top: Annotated[int,Query(ge=1,le=999)]=50):
    p: dict = {"$top": top, "$select": "id,displayName,userPrincipalName,mail,department,jobTitle,accountEnabled"}
    if search: p["$search"] = f'"displayName:{search}" OR "userPrincipalName:{search}"'
    return await graph.paginate("/users", p)

@router.get("/{user_id}", summary="Obtener usuario")
async def get_user(user_id: str):
    try: return await graph.get(f"/users/{user_id}")
    except Exception as e: raise HTTPException(404, str(e))

@router.post("", status_code=201, summary="Crear usuario en Azure AD")
async def create_user(body: TeamsUserCreate):
    payload = {"displayName": body.display_name, "userPrincipalName": body.user_principal_name,
               "mailNickname": body.mail_nickname, "usageLocation": body.usage_location,
               "accountEnabled": body.account_enabled,
               "passwordProfile": {"forceChangePasswordNextSignIn": True, "password": body.password}}
    for k, v in [("givenName", body.given_name), ("surname", body.surname),
                 ("department", body.department), ("jobTitle", body.job_title)]:
        if v: payload[k] = v
    try: return await graph.post("/users", payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/bulk", summary="Crear usuarios masivo en Azure AD")
async def create_users_bulk(body: BulkTeamsUserCreate) -> BulkResult:
    result = BulkResult()
    async def _c(u: TeamsUserCreate):
        try:
            p = {"displayName": u.display_name, "userPrincipalName": u.user_principal_name,
                 "mailNickname": u.mail_nickname, "usageLocation": u.usage_location,
                 "accountEnabled": u.account_enabled,
                 "passwordProfile": {"forceChangePasswordNextSignIn": True, "password": u.password}}
            for k, v in [("givenName", u.given_name), ("surname", u.surname),
                         ("department", u.department), ("jobTitle", u.job_title)]:
                if v: p[k] = v
            result.succeeded.append(await graph.post("/users", p))
        except Exception as e: result.failed.append({"input": u.model_dump(exclude={"password"}), "error": str(e)})
    await asyncio.gather(*[_c(u) for u in body.users])
    return result

@router.patch("/{user_id}", summary="Actualizar usuario")
async def update_user(user_id: str, body: TeamsUserUpdate):
    m = {"display_name":"displayName","given_name":"givenName","surname":"surname",
         "department":"department","job_title":"jobTitle","account_enabled":"accountEnabled"}
    payload = {m[k]: v for k, v in body.model_dump(exclude_none=True).items() if k in m}
    try: return await graph.patch(f"/users/{user_id}", payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.delete("/{user_id}", summary="Eliminar usuario de Azure AD")
async def delete_user(user_id: str):
    try: await graph.delete(f"/users/{user_id}"); return {"deleted": user_id}
    except Exception as e: raise HTTPException(400, str(e))
"""

FILES["app/routers/teams/teams_mgmt.py"] = """\
import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from app.models.teams import BulkResult, BulkTeamsMemberAdd, BulkTeamsMemberRemove, TeamsChannelCreate, TeamsMemberAdd, TeamsTeamCreate, TeamsTeamUpdate
from app.services import teams_client as graph
from app.services.teams_client import post_team

router = APIRouter(prefix="/teams/teams", tags=["Teams · Teams"])
_T = {
    "standard": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
    "educationClass": "https://graph.microsoft.com/v1.0/teamsTemplates('educationClass')",
    "educationStaff": "https://graph.microsoft.com/v1.0/teamsTemplates('educationStaff')",
    "educationProfessionalLearningCommunity": "https://graph.microsoft.com/v1.0/teamsTemplates('educationProfessionalLearningCommunity')",
}

@router.get("", summary="Listar Teams del tenant")
async def list_teams(top: Annotated[int,Query(ge=1,le=999)]=50):
    return await graph.paginate("/groups", {"$top": top,
        "$select": "id,displayName,description,visibility",
        "$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')"})

@router.get("/{team_id}", summary="Obtener Team")
async def get_team(team_id: str):
    try: return await graph.get(f"/teams/{team_id}")
    except Exception as e: raise HTTPException(404, str(e))

@router.post("", status_code=201, summary="Crear Team (plantilla educativa)")
async def create_team(body: TeamsTeamCreate):
    payload = {"template@odata.bind": _T.get(body.template, _T["educationClass"]),
               "displayName": body.display_name, "description": body.description or "",
               "visibility": body.visibility,
               "members": [{"@odata.type": "#microsoft.graph.aadUserConversationMember",
                             "roles": ["owner"],
                             "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.owner_id}')"}]}
    try: return await post_team(payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.patch("/{team_id}", summary="Actualizar Team")
async def update_team(team_id: str, body: TeamsTeamUpdate):
    m = {"display_name":"displayName","description":"description","visibility":"visibility"}
    payload = {m[k]: v for k, v in body.model_dump(exclude_none=True).items() if k in m}
    try: return await graph.patch(f"/teams/{team_id}", payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.delete("/{team_id}", summary="Eliminar Team")
async def delete_team(team_id: str):
    try: await graph.delete(f"/groups/{team_id}"); return {"deleted": team_id}
    except Exception as e: raise HTTPException(400, str(e))

@router.get("/{team_id}/members", summary="Listar miembros")
async def list_members(team_id: str):
    return await graph.paginate(f"/teams/{team_id}/members")

@router.post("/{team_id}/members", status_code=201, summary="Añadir miembro")
async def add_member(team_id: str, body: TeamsMemberAdd):
    payload = {"@odata.type": "#microsoft.graph.aadUserConversationMember",
               "roles": ["owner"] if body.role == "owner" else [],
               "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.user_id}')"}
    try: return await graph.post(f"/teams/{team_id}/members", payload)
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/{team_id}/members/bulk-add", summary="Añadir miembros masivo")
async def bulk_add_members(team_id: str, body: BulkTeamsMemberAdd) -> BulkResult:
    result = BulkResult()
    BATCH = 20
    members = [{"@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"] if m.role == "owner" else [],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{m.user_id}')"} for m in body.members]
    for i in range(0, len(members), BATCH):
        try:
            resp = await graph.post(f"/teams/{team_id}/members/add", {"values": members[i:i+BATCH]})
            result.succeeded.extend(resp.get("value", []))
            result.failed.extend(resp.get("error", []))
        except Exception as e:
            for m in body.members[i:i+BATCH]: result.failed.append({"user_id": m.user_id, "error": str(e)})
    return result

@router.delete("/{team_id}/members/{membership_id}", summary="Quitar miembro")
async def remove_member(team_id: str, membership_id: str):
    try: await graph.delete(f"/teams/{team_id}/members/{membership_id}"); return {"removed": membership_id}
    except Exception as e: raise HTTPException(400, str(e))

@router.post("/{team_id}/members/bulk-remove", summary="Quitar miembros masivo")
async def bulk_remove_members(team_id: str, body: BulkTeamsMemberRemove) -> BulkResult:
    result = BulkResult()
    try: members = await graph.paginate(f"/teams/{team_id}/members")
    except Exception as e: raise HTTPException(400, str(e))
    id_map = {m.get("userId"): m.get("id") for m in members}
    async def _r(uid: str):
        mid = id_map.get(uid)
        if not mid: result.failed.append({"user_id": uid, "error": "Not found"}); return
        try: await graph.delete(f"/teams/{team_id}/members/{mid}"); result.succeeded.append({"user_id": uid})
        except Exception as e: result.failed.append({"user_id": uid, "error": str(e)})
    await asyncio.gather(*[_r(uid) for uid in body.user_ids])
    return result

@router.get("/{team_id}/channels", summary="Listar canales")
async def list_channels(team_id: str):
    return await graph.paginate(f"/teams/{team_id}/channels")

@router.post("/{team_id}/channels", status_code=201, summary="Crear canal")
async def create_channel(team_id: str, body: TeamsChannelCreate):
    payload = {"displayName": body.display_name, "description": body.description or "",
               "membershipType": body.membership_type}
    try: return await graph.post(f"/teams/{team_id}/channels", payload)
    except Exception as e: raise HTTPException(400, str(e))
"""

FILES["app/routers/sync.py"] = """\
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings
from app.services import canvas_client as canvas
from app.services import teams_client as graph
from app.services.teams_client import post_team

router = APIRouter(prefix="/sync", tags=["Sync · Canvas ↔ Teams"])
_ACC = settings.canvas_account_id

class SyncCourseRequest(BaseModel):
    canvas_course_id: str
    owner_id: str
    template: str = "educationClass"

class SyncCourseResponse(BaseModel):
    canvas_course_id: str
    team_id: str
    synced_members: int
    failed_members: int

@router.post("/course-to-team", summary="Crear Team desde Curso Canvas + sincronizar miembros")
async def sync_course_to_team(body: SyncCourseRequest) -> SyncCourseResponse:
    try: course = await canvas.get(f"/courses/{body.canvas_course_id}")
    except Exception as e: raise HTTPException(404, f"Canvas course not found: {e}")
    payload = {"template@odata.bind": f"https://graph.microsoft.com/v1.0/teamsTemplates('{body.template}')",
               "displayName": course.get("name", f"Course {body.canvas_course_id}"),
               "description": course.get("public_description") or course.get("name", ""),
               "visibility": "Private",
               "members": [{"@odata.type": "#microsoft.graph.aadUserConversationMember",
                             "roles": ["owner"],
                             "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{body.owner_id}')"}]}
    try: team = await post_team(payload)
    except Exception as e: raise HTTPException(400, f"Could not create Teams team: {e}")
    team_id = team.get("id", "")
    enrollments = await canvas.paginate(f"/courses/{body.canvas_course_id}/enrollments",
                                        {"state[]": ["active"], "per_page": 100})
    synced = 0; failed = 0
    async def _add(e: dict):
        nonlocal synced, failed
        email = e.get("user", {}).get("email") or e.get("user", {}).get("login_id")
        if not email: failed += 1; return
        try:
            await graph.post(f"/teams/{team_id}/members",
                {"@odata.type": "#microsoft.graph.aadUserConversationMember",
                 "roles": [],
                 "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{email}')"})
            synced += 1
        except Exception: failed += 1
    await asyncio.gather(*[_add(e) for e in enrollments])
    return SyncCourseResponse(canvas_course_id=body.canvas_course_id, team_id=team_id,
                               synced_members=synced, failed_members=failed)
"""

FILES["app/main.py"] = """\
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.canvas.users import router as canvas_users
from app.routers.canvas.courses import router as canvas_courses
from app.routers.canvas.enrollments import router as canvas_enrollments, bulk_router as canvas_enrollments_bulk
from app.routers.canvas.groups import router as canvas_groups
from app.routers.teams.users import router as teams_users
from app.routers.teams.teams_mgmt import router as teams_teams
from app.routers.sync import router as sync_router

@asynccontextmanager
async def lifespan(app): yield

app = FastAPI(
    title="Canvas LMS & Microsoft Teams — API de Gestión",
    description="Gestión masiva e individual de usuarios, cursos, matrículas y grupos "
                "en Canvas LMS y Microsoft Teams / Azure AD.\\n\\n"
                "Universidad San Ignacio de Loyola — Paraguay",
    version="1.0.0", lifespan=lifespan, docs_url="/docs", redoc_url="/redoc")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(canvas_users)
app.include_router(canvas_courses)
app.include_router(canvas_enrollments)
app.include_router(canvas_enrollments_bulk)
app.include_router(canvas_groups)
app.include_router(teams_users)
app.include_router(teams_teams)
app.include_router(sync_router)

@app.get("/health", tags=["Health"])
async def health(): return {"status": "ok", "canvas": "usilparaguay.instructure.com", "tenant": "San Ignacio de Loyola"}
"""

# ─── Write all files ──────────────────────────────────────────────────────────

def write(path, content):
    full = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))

print(f"Creando proyecto en: {BASE}")
for path, content in FILES.items():
    write(path, content)
    print(f"  OK  {path}")

# ─── Install dependencies ─────────────────────────────────────────────────────
print("\nInstalando dependencias...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
    "fastapi", "uvicorn[standard]", "httpx", "pydantic[email]",
    "pydantic-settings", "python-dotenv", "msal", "tenacity"])
print("Dependencias instaladas.")

print(f"""
{'='*60}
PROYECTO LISTO

Para arrancar el servidor:
  cd "{BASE}"
  uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload

Swagger UI: http://localhost:3000/docs
{'='*60}
""")
