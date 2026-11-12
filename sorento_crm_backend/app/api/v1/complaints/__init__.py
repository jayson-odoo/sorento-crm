"""Complaint management API routes."""
from fastapi import APIRouter, Depends
from app.api.v1._request_own_scope import complaint_own_scope
from app.api.v1.complaints import complaints, complaint_root_causes, complaint_resolutions

router = APIRouter()

# "Only theirs" for a user holding complaints view_own alone (PORTAL-P4-REQUESTS).
router.include_router(
    complaints.router,
    prefix="/complaints",
    tags=["complaints"],
    dependencies=[Depends(complaint_own_scope)],
)
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
