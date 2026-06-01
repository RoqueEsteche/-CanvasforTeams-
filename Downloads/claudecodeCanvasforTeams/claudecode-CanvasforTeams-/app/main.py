import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Configure logging FIRST, before importing any modules that use logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core import cache, audit, database, audit_log, jobs
from app.middleware.audit import AuditMiddleware
from app.routers.canvas.users import router as canvas_users
from app.routers.canvas.courses import router as canvas_courses
from app.routers.canvas.enrollments import router as canvas_enrollments, bulk_router as canvas_enrollments_bulk
from app.routers.canvas.terms import router as canvas_terms
from app.routers.canvas.attendance import router as canvas_attendance
from app.routers.teams.users import router as teams_users
from app.routers.teams.teams_mgmt import router as teams_teams
from app.routers.sync import router as sync_router
from app.routers.web import router as web_router
from app.routers.excel import router as excel_router
from app.routers.ingreso import router as ingreso_router
from app.routers.auth import router as auth_router
from app.routers.profile import router as profile_router
from app.routers.audit import router as audit_router
from app.routers.jobs import router as jobs_router
from app.services import auth as auth_service


async def _full_db_sync() -> None:
    """Background sync: Canvas courses → Canvas users → Azure users into SQLite."""
    await asyncio.sleep(3)  # allow the app to finish starting before hammering the APIs

    from app.services import canvas_client as _canvas
    from app.services import teams_client as _graph

    # ── Canvas courses ─────────────────────────────────────────────────────────
    try:
        courses = await _canvas.paginate_limited(
            f"/accounts/{settings.canvas_account_id}/courses",
            {"per_page": 100}, max_records=2000,
        )
        await database.upsert_courses(courses)
        await database.mark_synced("canvas_courses")
        cache.set("canvas:courses:::50", courses, ttl=300)
        logger.info("DB sync: %d cursos Canvas", len(courses))
    except Exception as exc:
        logger.warning("DB sync cursos falló: %s", exc)

    # ── Canvas users ───────────────────────────────────────────────────────────
    try:
        users = await _canvas.paginate_limited(
            f"/accounts/{settings.canvas_account_id}/users",
            {"per_page": 100}, max_records=5000,
        )
        await database.upsert_canvas_users(users)
        await database.mark_synced("canvas_users")
        logger.info("DB sync: %d usuarios Canvas", len(users))
    except Exception as exc:
        logger.warning("DB sync usuarios Canvas falló: %s", exc)

    # ── Azure AD users ─────────────────────────────────────────────────────────
    try:
        azure_users = await _graph.paginate_limited(
            "/users",
            {
                "$top": 999,
                "$select": "id,displayName,userPrincipalName,mail,department,jobTitle,accountEnabled",
                "$orderby": "displayName",
            },
            max_records=5000,
        )
        await database.upsert_azure_users(azure_users)
        await database.mark_synced("azure_users")
        logger.info("DB sync: %d usuarios Azure AD", len(azure_users))
    except Exception as exc:
        logger.warning("DB sync usuarios Azure falló: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 USIL Canvas+Teams API starting — environment: %s", settings.environment)

    if settings.is_insecure_secret and settings.environment != "development":
        logger.error("SEGURIDAD: SECRET_KEY usa el valor por defecto. Detén el servicio y configura una clave segura.")

    try:
        # Restore cache from disk (previous session)
        restored = cache.load_from_disk()
        logger.info("Cache restaurada: %d entradas desde disco", restored)

        # Initialize database
        logger.info("🔧 Initializing database...")
        await database.init_db()
        logger.info("✅ Database initialized successfully")

        # Initialize audit database
        audit_log.init_audit_db()

        # Initialize jobs database
        jobs.init_jobs_db()

        # Background sync to populate/refresh local DB mirror
        asyncio.create_task(_full_db_sync())
        logger.info("✅ Background sync started")

    except Exception as e:
        logger.error(f"❌ Error during startup: {e}", exc_info=True)
        raise

    yield

    cache.save_to_disk()
    logger.info("USIL Canvas+Teams API shutdown — cache guardada en disco")


app = FastAPI(
    title="Canvas LMS & Microsoft Teams Management API",
    description=(
        "Web service para gestión masiva e individual de usuarios, cursos, matrículas, "
        "grupos en Canvas LMS y usuarios, Teams y miembros en Microsoft Teams / Azure AD."
    ),
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Audit logging — log all HTTP requests with user information
app.add_middleware(AuditMiddleware)

# Compression — reduce response size by ~70% for JSON/HTML
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — restrict to configured site_url in production
_allowed_origins = (
    ["*"]
    if settings.environment == "development"
    else [settings.site_url.rstrip("/")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

# Static files
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(web_router)
app.include_router(excel_router)
app.include_router(ingreso_router)
app.include_router(canvas_users)
app.include_router(canvas_courses)
app.include_router(canvas_enrollments)
app.include_router(canvas_enrollments_bulk)
app.include_router(canvas_terms)
app.include_router(canvas_attendance)
app.include_router(teams_users)
app.include_router(teams_teams)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(audit_router)
app.include_router(jobs_router)
app.include_router(sync_router)


# ── Health & diagnostics ──────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "cache": cache.stats(),
    }


@app.get("/stats", tags=["Health"])
async def stats():
    """Conteos instantáneos desde la DB local — sin llamadas a APIs externas."""
    from app.core.database import count_canvas_users, count_courses, count_azure_users
    canvas_u, canvas_c, azure_u = await asyncio.gather(
        count_canvas_users(),
        count_courses(),
        count_azure_users(),
    )
    last_sync = await database.get_last_sync("canvas_courses")
    return {
        "canvas_users":  canvas_u,
        "canvas_courses": canvas_c,
        "azure_users":   azure_u,
        "last_sync":     last_sync,
    }


@app.get("/diagnostics", tags=["Health"])
async def diagnostics(request: Request):
    """Test Canvas and Azure credentials. Requires authenticated session."""
    user = auth_service.get_user_from_request(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Autenticación requerida")

    import httpx
    result: dict = {"canvas": {}, "azure": {}}

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
            else:
                result["canvas"] = {"status": "error", "code": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        result["canvas"] = {"status": "error", "detail": str(e)}

    try:
        import msal
        app_msal = msal.ConfidentialClientApplication(
            client_id=settings.azure_client_id,
            client_credential=settings.azure_client_secret,
            authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        )
        token_result = app_msal.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in token_result:
            result["azure"] = {"status": "error",
                               "detail": token_result.get("error_description", "unknown")}
        else:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://graph.microsoft.com/v1.0/users",
                    headers={"Authorization": f"Bearer {token_result['access_token']}"},
                    params={"$top": 1, "$select": "id,displayName"},
                )
                if r.status_code == 200:
                    result["azure"] = {"status": "ok", "token": "válido",
                                       "sample_count": len(r.json().get("value", []))}
                else:
                    result["azure"] = {"status": "error", "code": r.status_code,
                                       "detail": r.text[:200]}
    except Exception as e:
        result["azure"] = {"status": "error", "detail": str(e)}

    return result


# ── Audit log ─────────────────────────────────────────────────────────────────

@app.get("/audit/recent", tags=["Audit"])
async def audit_recent(request: Request, limit: int = 50):
    """Últimas operaciones registradas. Requiere sesión autenticada."""
    user = auth_service.get_user_from_request(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    return {
        "entries": audit.recent(min(limit, 200)),
        "summary": audit.summary(),
    }


# ── Cache management ──────────────────────────────────────────────────────────

@app.post("/cache/clear", tags=["Health"])
async def clear_cache(request: Request, prefix: str = ""):
    """Limpia la caché de respuestas API. Requiere sesión autenticada."""
    user = auth_service.get_user_from_request(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    n = cache.clear_all() if not prefix else (cache.invalidate(prefix) or 0)
    audit.log("cache_clear", prefix or "all", user=user.get("email", "?"))
    return {"cleared": n if isinstance(n, int) else "ok", "prefix": prefix or "all"}
