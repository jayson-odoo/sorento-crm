"""Activities & Notes API routes."""
from fastapi import APIRouter

from app.api.v1.activities import activities

router = APIRouter()

router.include_router(activities.router)
