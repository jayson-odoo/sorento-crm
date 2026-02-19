"""Notifications API."""
from fastapi import APIRouter
from app.api.v1.notifications import notifications as notifications_routes

router = APIRouter()
router.include_router(notifications_routes.router, tags=["notifications"])
