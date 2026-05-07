"""Complaint management API routes."""
from fastapi import APIRouter
from app.api.v1.complaints import complaints, complaint_root_causes, complaint_resolutions

router = APIRouter()

router.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
router.include_router(
    complaint_root_causes.router,
    prefix="/complaint-root-causes",
    tags=["complaint-root-causes"],
)
router.include_router(
    complaint_resolutions.router,
    prefix="/complaint-resolutions",
    tags=["complaint-resolutions"],
)
