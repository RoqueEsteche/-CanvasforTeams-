"""Audit middleware to log all HTTP requests."""
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core import audit_log
from app.services import auth

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that logs all HTTP requests to audit database."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and log to audit database."""

        # Get user information
        try:
            user = auth.get_user_from_request(request)
            username = user.email if user else "Anonymous"
        except Exception:
            username = "Anonymous"

        # Get client IP
        ip_address = request.client.host if request.client else "Unknown"

        # Get user agent
        user_agent = request.headers.get("user-agent", "Unknown")

        # Skip logging for static files and health checks
        skip_paths = ["/static/", "/health"]
        skip = any(request.url.path.startswith(p) for p in skip_paths)

        # Process request
        response = await call_next(request)

        # Log to audit database (skip if flagged)
        if not skip:
            try:
                await audit_log.log_activity(
                    username=username,
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    ip_address=ip_address,
                    user_agent=user_agent[:255],  # Truncate to 255 chars
                    details=None
                )
            except Exception as e:
                logger.error(f"Failed to log audit activity: {e}")

        return response
