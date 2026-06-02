"""Resource management API routes."""
from fastapi import APIRouter
from app.api.v1.resources import (
    attachment_types,
    attachments,
    directories,
    upload_activity,
)

router = APIRouter()

router.include_router(attachments.router, prefix="/attachments", tags=["attachments"])
router.include_router(attachment_types.router, prefix="/attachment-types", tags=["attachment-types"])
router.include_router(directories.router, prefix="/directories", tags=["directories"])
router.include_router(upload_activity.router, prefix="/upload-activity", tags=["upload-activity"])
