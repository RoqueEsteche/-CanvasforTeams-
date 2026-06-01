"""Job/Task history endpoints."""
import logging
from fastapi import APIRouter, Query
from typing import Annotated, Optional

from app.core import jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Job History"])


@router.get("/list", summary="Obtener historial de trabajos")
async def get_jobs_list(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    job_type: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get job history with filters.

    Available job types: bulk_user_create, user_create, enrollment_bulk, etc.
    Available statuses: pending, processing, completed, completed_with_errors, failed
    Date format: YYYY-MM-DD
    """
    try:
        result = await jobs.get_jobs(
            limit=limit,
            offset=offset,
            job_type=job_type,
            username=username,
            status=status,
            date_from=date_from,
            date_to=date_to
        )
        return result
    except Exception as exc:
        logger.error(f"Error retrieving jobs: {exc}")
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/stats", summary="Estadísticas de trabajos")
async def get_jobs_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get job statistics by type and user.

    Date format: YYYY-MM-DD
    """
    try:
        result = await jobs.get_jobs_stats(date_from=date_from, date_to=date_to)
        return result
    except Exception as exc:
        logger.error(f"Error getting job stats: {exc}")
        return {}


@router.get("/today", summary="Trabajos de hoy")
async def get_todays_jobs():
    """Get all jobs from today."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await jobs.get_jobs(
            limit=500,
            offset=0,
            date_from=today,
            date_to=today
        )
        return result
    except Exception as exc:
        logger.error(f"Error retrieving today's jobs: {exc}")
        return {"jobs": [], "total": 0}


@router.get("/by-date/{date_str}", summary="Trabajos por fecha específica")
async def get_jobs_by_date(date_str: str):
    """Get all jobs from a specific date (YYYY-MM-DD)."""
    try:
        result = await jobs.get_jobs(
            limit=500,
            offset=0,
            date_from=date_str,
            date_to=date_str
        )
        return result
    except Exception as exc:
        logger.error(f"Error retrieving jobs for date: {exc}")
        return {"jobs": [], "total": 0}


@router.get("/by-user/{username}", summary="Trabajos de un usuario")
async def get_jobs_by_user(
    username: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Get all jobs created by a specific user."""
    try:
        result = await jobs.get_jobs(
            limit=limit,
            offset=offset,
            username=username
        )
        return result
    except Exception as exc:
        logger.error(f"Error retrieving user jobs: {exc}")
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/by-type/{job_type}", summary="Trabajos por tipo")
async def get_jobs_by_type(
    job_type: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Get all jobs of a specific type."""
    try:
        result = await jobs.get_jobs(
            limit=limit,
            offset=offset,
            job_type=job_type
        )
        return result
    except Exception as exc:
        logger.error(f"Error retrieving jobs by type: {exc}")
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset}
