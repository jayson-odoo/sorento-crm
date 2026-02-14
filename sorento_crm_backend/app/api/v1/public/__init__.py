"""Public (unauthenticated) API routes."""
from fastapi import APIRouter
from app.api.v1.public import approval

router = APIRouter()
router.include_router(approval.router, prefix="/approval", tags=["public-approval"])
