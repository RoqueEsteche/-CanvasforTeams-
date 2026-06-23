"""Web UI routes – serve Jinja2 templates."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import auth as auth_service

router = APIRouter(tags=["Web UI"])
_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "Frontend" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _current_user(request: Request):
    return auth_service.get_user_from_request(request)


def _r(request: Request, template: str, **ctx):
    ctx.setdefault("user", _current_user(request))
    ctx.setdefault("request", request)
    return templates.TemplateResponse(template, ctx)


@router.get("/", response_class=HTMLResponse)
@router.get("/ui", response_class=HTMLResponse)
async def root(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse(url="/ui/login", status_code=302)
    return RedirectResponse(url="/ui/home", status_code=302)


@router.get("/ui/canvas/users", response_class=HTMLResponse)
async def canvas_users(request: Request):
    return _r(request, "canvas/users.html")


@router.get("/ui/canvas/courses", response_class=HTMLResponse)
async def canvas_courses(request: Request):
    return _r(request, "canvas/courses.html")


@router.get("/ui/canvas/attendance", response_class=HTMLResponse)
async def canvas_attendance(request: Request):
    return _r(request, "attendance_reports.html")


@router.get("/ui/canvas/enrollments", response_class=HTMLResponse)
async def canvas_enrollments(request: Request):
    return _r(request, "canvas/enrollments.html")


@router.get("/ui/canvas/groups", response_class=HTMLResponse)
async def canvas_groups(request: Request):
    return _r(request, "canvas/groups.html")


@router.get("/ui/diagnostico", response_class=HTMLResponse)
async def diagnostico(request: Request):
    return _r(request, "diagnostico_matriculas.html")



@router.get("/ui/teams", response_class=HTMLResponse)
async def teams_root(request: Request):
    return RedirectResponse(url="/ui/teams/teams", status_code=302)


@router.get("/ui/teams/users", response_class=HTMLResponse)
async def teams_users(request: Request):
    return _r(request, "teams/users.html")


@router.get("/ui/teams/teams", response_class=HTMLResponse)
async def teams_teams(request: Request):
    return _r(request, "teams/teams.html")


@router.get("/ui/ingreso", response_class=HTMLResponse)
async def ingreso_page(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse(url="/ui/login", status_code=302)
    from app.core.config import settings
    return _r(request, "ingreso.html", domain=settings.institutional_domain)


@router.get("/ui/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = _current_user(request)
    if user:
        return RedirectResponse(url="/ui/home", status_code=302)
    return _r(request, "login.html")


@router.get("/ui/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse(url="/ui/login")
    return _r(request, "profile.html")


@router.get("/ui/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    return _r(request, "sync.html")


@router.get("/ui/home", response_class=HTMLResponse)
async def home_page(request: Request):
    return _r(request, "dashboard.html")


@router.get("/ui/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    return _r(request, "audit_logs.html")


@router.get("/ui/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    return _r(request, "job_history.html")


@router.get("/ui/unified-users", response_class=HTMLResponse)
async def unified_users_page(request: Request):
    return _r(request, "unified_users.html")


@router.get("/ui/unified-creation", response_class=HTMLResponse)
async def unified_creation_page(request: Request):
    return _r(request, "unified_creation.html")


@router.get("/ui/unified-enrollments", response_class=HTMLResponse)
async def unified_enrollments_page(request: Request):
    return _r(request, "unified_enrollments.html")


@router.get("/diagnostics", tags=["Health"])
async def diagnostics():
    """Test Canvas and Azure credentials and return status for each."""
    import httpx
    from app.core.config import settings

    result = {"canvas": {}, "azure": {}}

    # ── Canvas ────────────────────────────────────────────────
    canvas_base = f"{settings.canvas_base_url.rstrip('/')}/api/v1"
    headers_canvas = {"Authorization": f"Bearer {settings.canvas_access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{canvas_base}/users/self", headers=headers_canvas)
            if r.status_code == 200:
                me = r.json()
                result["canvas"] = {"status": "ok", "user": me.get("name"), "id": me.get("id")}
            elif r.status_code == 401:
                result["canvas"] = {"status": "error", "code": 401, "detail": "Token inválido o expirado"}
            elif r.status_code == 403:
                result["canvas"] = {"status": "error", "code": 403, "detail": "Token válido pero sin permisos admin"}
            else:
                result["canvas"] = {"status": "error", "code": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        result["canvas"] = {"status": "error", "detail": str(e)}

    # ── Azure / Graph ─────────────────────────────────────────
    try:
        import msal, time
        app_msal = msal.ConfidentialClientApplication(
            client_id=settings.azure_client_id,
            client_credential=settings.azure_client_secret,
            authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        )
        token_result = app_msal.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in token_result:
            result["azure"] = {
                "status": "error",
                "detail": f"MSAL falló: {token_result.get('error_description', token_result.get('error', 'unknown'))}",
            }
        else:
            # Token OK — test Graph /users
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://graph.microsoft.com/v1.0/users",
                    headers={"Authorization": f"Bearer {token_result['access_token']}"},
                    params={"$top": 1, "$select": "id,displayName"},
                )
                if r.status_code == 200:
                    data = r.json()
                    result["azure"] = {
                        "status": "ok",
                        "token": "válido",
                        "users_count_sample": len(data.get("value", [])),
                    }
                else:
                    try:
                        err_body = r.json()
                    except Exception:
                        err_body = r.text[:300]
                    result["azure"] = {
                        "status": "error",
                        "code": r.status_code,
                        "token": "válido",
                        "graph_error": err_body,
                    }
    except Exception as e:
        result["azure"] = {"status": "error", "detail": str(e)}

    return result
