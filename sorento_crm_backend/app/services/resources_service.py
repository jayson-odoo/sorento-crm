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
        from sqlalchemy.orm import joinedload
        q = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.is_deleted == False)
        
        if entity_type:
            q = q.filter(Attachment.entity_type == entity_type)
        if entity_id:
            q = q.filter(Attachment.entity_id == entity_id)
        
        q = q.order_by(Attachment.uploaded_at.desc())
        
        total = q.count()
        offset = (page - 1) * limit
        attachments = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": attachments,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_attachment(self, attachment_id: str):
        """Get an attachment by ID."""
        from sqlalchemy.orm import joinedload
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise handle_not_found("Attachment", attachment_id)
        return attachment
    
    def create_attachment(self, attachment_data: AttachmentCreate, uploaded_by: str):
        """Create a new attachment."""
        from sqlalchemy.orm import joinedload
        import uuid as uuid_module
        
        attachment_dict = attachment_data.model_dump()
        # Ensure uploaded_by is a string (convert UUID if needed)
        if isinstance(uploaded_by, uuid_module.UUID):
            attachment_dict["uploaded_by"] = str(uploaded_by)
        else:
            attachment_dict["uploaded_by"] = str(uploaded_by) if uploaded_by else None
        
        attachment = Attachment(**attachment_dict)
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        
        # Reload with relationship
        attachment = self.db.query(Attachment).options(
            joinedload(Attachment.attachment_type)
        ).filter(Attachment.id == attachment.id).first()
        
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
    
    def get_file_content(self, attachment_id: str) -> bytes:
        """
        Retrieve file content from S3 for an attachment.
        
        Args:
            attachment_id: ID of the attachment
        
        Returns:
            File content as bytes
        
        Raises:
            Exception: If attachment not found or file retrieval fails
        """
        attachment = self.get_attachment(attachment_id)
        
        if not attachment.file_path:
            raise Exception("Attachment has no file path")
        
        from app.services.s3_service import S3Service
        from urllib.parse import urlparse
        
        s3_service = S3Service()
        
        try:
            # Extract S3 key from URL if it's a full URL
            # Format: https://bucket.s3.region.amazonaws.com/key
            # Or: https://bucket.s3.amazonaws.com/key
            file_path = attachment.file_path
            if file_path.startswith("https://"):
                # Parse URL to extract key
                parsed = urlparse(file_path)
                # Path will be like /key, so remove leading /
                s3_key = parsed.path.lstrip("/")
            else:
                # Already a key
                s3_key = file_path
            
            file_content = s3_service.download_file(s3_key)
            return file_content
        except Exception as e:
            raise Exception(f"Failed to retrieve file from S3: {str(e)}")
