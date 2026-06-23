"""Canvas routers - combine all Canvas-related endpoints."""
from fastapi import APIRouter

from . import attendance, courses, enrollments, groups, terms, users

# Create main canvas router - sub-routers already have /canvas prefix
router = APIRouter(tags=["Canvas"])

# Include all sub-routers (they have their own /canvas/... prefixes)
router.include_router(courses.router)
router.include_router(users.router)
router.include_router(enrollments.router)
router.include_router(enrollments.bulk_router)
router.include_router(groups.router)
router.include_router(attendance.router)
router.include_router(terms.router)
