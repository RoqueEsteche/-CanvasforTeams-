"""Audit log endpoints."""
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated

from app.core import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs", summary="Obtener logs de auditoría")
async def get_audit_logs(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Get audit logs with pagination."""
    try:
        result = await audit_log.get_audit_logs(limit=limit, offset=offset)
        return result
    except Exception as exc:
        logger.error(f"Error retrieving audit logs: {exc}")
        raise HTTPException(status_code=500, detail="Error retrieving audit logs")


@router.get("/logs/user/{username}", summary="Obtener logs de un usuario específico")
async def get_user_audit_logs(
    username: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Get audit logs for a specific user."""
    try:
        # Get all logs and filter by username
        result = await audit_log.get_audit_logs(limit=limit + offset, offset=0)

        user_logs = [log for log in result["logs"] if log["username"] == username]

        return {
            "logs": user_logs[offset:offset + limit],
            "total": len(user_logs),
            "limit": limit,
            "offset": offset,
            "username": username
        }
    except Exception as exc:
        logger.error(f"Error retrieving user audit logs: {exc}")
        raise HTTPException(status_code=500, detail="Error retrieving audit logs")


@router.delete("/logs/cleanup", summary="Limpiar logs antiguos (admin)")
async def cleanup_old_logs(days: Annotated[int, Query(ge=1)] = 90):
    """Delete audit logs older than N days."""
    try:
        deleted = await audit_log.clear_old_logs(days=days)
        return {
            "deleted": deleted,
            "days": days,
            "message": f"Deleted {deleted} audit logs older than {days} days"
        }
    except Exception as exc:
        logger.error(f"Error cleaning up audit logs: {exc}")
        raise HTTPException(status_code=500, detail="Error cleaning up audit logs")


@router.get("/stats", summary="Estadísticas de actividad")
async def get_audit_stats():
    """Get activity statistics."""
    try:
        result = await audit_log.get_audit_logs(limit=10000, offset=0)
        logs = result["logs"]

        # Count by method
        method_counts = {}
        user_counts = {}
        endpoint_counts = {}

        for log in logs:
            method = log.get("method", "Unknown")
            username = log.get("username", "Unknown")
            endpoint = log.get("endpoint", "Unknown")

            method_counts[method] = method_counts.get(method, 0) + 1
            user_counts[username] = user_counts.get(username, 0) + 1
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

        return {
            "total_requests": result["total"],
            "by_method": method_counts,
            "by_user": user_counts,
            "by_endpoint": endpoint_counts,
            "unique_users": len(user_counts),
            "unique_endpoints": len(endpoint_counts)
        }
    except Exception as exc:
        logger.error(f"Error getting audit stats: {exc}")
        raise HTTPException(status_code=500, detail="Error getting audit statistics")
