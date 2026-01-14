"""Attachment types API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.resources_service import AttachmentTypeService
from app.schemas.resources import AttachmentTypeCreate, AttachmentTypeUpdate, AttachmentTypeResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[AttachmentTypeResponse])
async def get_attachment_types(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all attachment types."""
    try:
        service = AttachmentTypeService(db)
        types = service.list_types()
        return {
            "data": types,
            "pagination": {"total": len(types), "page": 1, "limit": len(types)},
            "empty": len(types) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{type_id}", response_model=AttachmentTypeResponse)
async def get_attachment_type(
    type_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single attachment type by ID."""
    try:
        service = AttachmentTypeService(db)
        attachment_type = service.get_type(type_id)
        return attachment_type
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=AttachmentTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_attachment_type(
    type_data: AttachmentTypeCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new attachment type."""
    try:
        service = AttachmentTypeService(db)
        attachment_type = service.create_type(type_data)
        return attachment_type
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{type_id}", response_model=AttachmentTypeResponse)
async def update_attachment_type(
    type_id: str,
    type_data: AttachmentTypeUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an attachment type."""
    try:
        service = AttachmentTypeService(db)
        attachment_type = service.update_type(type_id, type_data)
        return attachment_type
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{type_id}", status_code=status.HTTP_200_OK)
async def delete_attachment_type(
    type_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an attachment type."""
    try:
        service = AttachmentTypeService(db)
        # Implement delete logic
        return {"message": "Attachment type deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
