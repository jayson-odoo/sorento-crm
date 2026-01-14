"""Resource management API routes."""
from fastapi import APIRouter
from app.api.v1.resources import attachments, attachment_types

router = APIRouter()

router.include_router(attachments.router, prefix="/attachments", tags=["attachments"])
router.include_router(attachment_types.router, prefix="/attachment-types", tags=["attachment-types"])
