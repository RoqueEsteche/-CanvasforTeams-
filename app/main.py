"""Canvas for Teams - Main FastAPI Application"""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log"),
    ]
)
logger = logging.getLogger(__name__)

from app.core import database
from app.core.config import settings
from app.routers import (
    audit,
    auth,
    canvas,
    excel,
    ingreso,
    jobs,
    profile,
    sync,
    web,
)

# Setup paths
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# Create FastAPI app
app = FastAPI(
    title="Canvas for Teams API",
    description="Integration between Canvas LMS and Microsoft Teams",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Setup templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Health check endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check."""
    try:
        stats = await get_stats()
        return {
            "status": "ok",
            "environment": settings.environment,
            **stats
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "degraded",
            "error": str(e)
        }


@app.get("/stats", tags=["Health"])
async def get_stats():
    """Get application statistics."""
    try:
        return {
            "courses": await database.count_courses(),
            "canvas_users": await database.count_canvas_users(),
            "azure_users": await database.count_azure_users(),
        }
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return {
            "courses": 0,
            "canvas_users": 0,
            "azure_users": 0,
            "error": str(e)
        }


@app.get("/ping", tags=["Health"])
async def ping():
    """Simple ping endpoint."""
    return {"pong": True}


# Include routers with error handling
routers_to_load = [
    ("Auth", auth.router),
    ("Canvas", canvas.router),
    ("Excel", excel.router),
    ("Ingreso", ingreso.router),
    ("Jobs", jobs.router),
    ("Profile", profile.router),
    ("Sync", sync.router),
    ("Audit", audit.router),
    ("Web", web.router),
]

for router_name, router_obj in routers_to_load:
    try:
        app.include_router(router_obj)
        logger.info(f"[OK] {router_name} router loaded")
    except Exception as e:
        logger.error(f"[ERROR] {router_name} router failed: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.environment == "development",
    )
