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
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Canvas LMS & Microsoft Teams Management API",
    description=(
        "Web service para gestión masiva e individual de usuarios, cursos, matrículas, "
        "grupos en Canvas LMS y usuarios, Teams y miembros en Microsoft Teams / Azure AD. "
        "\n\n**Nota:** Configura las variables de entorno antes de usar (ver `.env.example`)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Canvas
app.include_router(canvas_users)
app.include_router(canvas_courses)
app.include_router(canvas_enrollments)
app.include_router(canvas_enrollments_bulk)
app.include_router(canvas_groups)

# Teams / Azure AD
app.include_router(teams_users)
app.include_router(teams_teams)

# Sync
app.include_router(sync_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
