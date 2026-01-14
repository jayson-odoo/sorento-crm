"""Resources service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional
from app.models.resources import Attachment, AttachmentType
from app.schemas.resources import (
    AttachmentCreate, AttachmentUpdate, AttachmentTypeCreate, AttachmentTypeUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


class AttachmentTypeService:
    """Service for attachment type operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_types(self):
        """List all attachment types."""
        types = self.db.query(AttachmentType).all()
        return types
    
    def get_type(self, type_id: str):
        """Get an attachment type by ID."""
        attachment_type = self.db.query(AttachmentType).filter(AttachmentType.id == type_id).first()
        if not attachment_type:
            raise handle_not_found("Attachment Type", type_id)
        return attachment_type
    
    def create_type(self, type_data: AttachmentTypeCreate):
        """Create a new attachment type."""
        existing = self.db.query(AttachmentType).filter(
            AttachmentType.type_name == type_data.type_name
        ).first()
        if existing:
            raise handle_conflict("Attachment type name already exists.")
        
        attachment_type = AttachmentType(**type_data.model_dump())
        self.db.add(attachment_type)
        self.db.commit()
        self.db.refresh(attachment_type)
        return attachment_type
    
    def update_type(self, type_id: str, type_data: AttachmentTypeUpdate):
        """Update an attachment type."""
        attachment_type = self.get_type(type_id)
        
        update_data = type_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(attachment_type, key, value)
        
        self.db.commit()
        self.db.refresh(attachment_type)
        return attachment_type


class AttachmentService:
    """Service for attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None
    ):
        """List attachments."""
        q = self.db.query(Attachment).filter(Attachment.is_deleted == False)
        
        if entity_type:
            q = q.filter(Attachment.entity_type == entity_type)
        if entity_id:
            q = q.filter(Attachment.entity_id == entity_id)
        
        q = q.order_by(Attachment.uploaded_at.desc())
        
        total = q.count()
        offset = (page - 1) * limit
        attachments = q.offset(offset).limit(limit).all()
        
        return {
            "data": attachments,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_attachment(self, attachment_id: str):
        """Get an attachment by ID."""
        attachment = self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise handle_not_found("Attachment", attachment_id)
        return attachment
    
    def create_attachment(self, attachment_data: AttachmentCreate, uploaded_by: str):
        """Create a new attachment."""
        attachment_dict = attachment_data.model_dump()
        attachment_dict["uploaded_by"] = uploaded_by
        attachment = Attachment(**attachment_dict)
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        return attachment
    
    def update_attachment(self, attachment_id: str, attachment_data: AttachmentUpdate):
        """Update an attachment."""
        attachment = self.get_attachment(attachment_id)
        
        update_data = attachment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(attachment, key, value)
        
        self.db.commit()
        self.db.refresh(attachment)
        return attachment
    
    def delete_attachment(self, attachment_id: str, deleted_by: str):
        """Soft delete an attachment."""
        attachment = self.get_attachment(attachment_id)
        from datetime import datetime
        attachment.is_deleted = True
        attachment.deleted_at = datetime.utcnow()
        attachment.deleted_by = deleted_by
        self.db.commit()
        return {"message": "Attachment deleted successfully"}
