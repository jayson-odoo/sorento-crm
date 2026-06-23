"""Notifications API."""
from fastapi import APIRouter
from app.api.v1.notifications import notifications as notifications_routes
from app.api.v1.notifications import coverage as coverage_routes

router = APIRouter()
router.include_router(notifications_routes.router, tags=["notifications"])
router.include_router(
    coverage_routes.router, prefix="/coverage", tags=["notifications"]
)
