"""Canvas for Teams - Main FastAPI Application"""
import logging
import sys
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan events."""
    try:
        logger.info("Starting Canvas for Teams API...")
        await database.init_db()
        logger.info("Database initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down Canvas for Teams API...")


# Create FastAPI app
app = FastAPI(
    title="Canvas for Teams API",
    description="Integration between Canvas LMS and Microsoft Teams",
    version="1.0.0",
    lifespan=lifespan,
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


# Include routers
try:
    app.include_router(auth.router)
    logger.info("✓ Auth router loaded")
except Exception as e:
    logger.warning(f"⚠ Auth router failed: {e}")

try:
    app.include_router(canvas.router)
    logger.info("✓ Canvas router loaded")
except Exception as e:
    logger.warning(f"⚠ Canvas router failed: {e}")

try:
    app.include_router(excel.router)
    logger.info("✓ Excel router loaded")
except Exception as e:
    logger.warning(f"⚠ Excel router failed: {e}")

try:
    app.include_router(ingreso.router)
    logger.info("✓ Ingreso router loaded")
except Exception as e:
    logger.warning(f"⚠ Ingreso router failed: {e}")

try:
    app.include_router(jobs.router)
    logger.info("✓ Jobs router loaded")
except Exception as e:
    logger.warning(f"⚠ Jobs router failed: {e}")

try:
    app.include_router(profile.router)
    logger.info("✓ Profile router loaded")
except Exception as e:
    logger.warning(f"⚠ Profile router failed: {e}")

try:
    app.include_router(sync.router)
    logger.info("✓ Sync router loaded")
except Exception as e:
    logger.warning(f"⚠ Sync router failed: {e}")

try:
    app.include_router(audit.router)
    logger.info("✓ Audit router loaded")
except Exception as e:
    logger.warning(f"⚠ Audit router failed: {e}")

try:
    app.include_router(web.router)
    logger.info("✓ Web router loaded")
except Exception as e:
    logger.warning(f"⚠ Web router failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.environment == "development",
    )
