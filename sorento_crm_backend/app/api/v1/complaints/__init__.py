"""Complaint management API routes."""
from fastapi import APIRouter
from app.api.v1.complaints import complaints

router = APIRouter()

router.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
