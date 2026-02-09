"""Resource management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import uuid


class AttachmentTypeBase(BaseModel):
    type_name: str
    description: Optional[str] = None
    allowed_extensions: str
    max_file_size_mb: int = 10


class AttachmentTypeCreate(AttachmentTypeBase):
    pass


class AttachmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    allowed_extensions: Optional[str] = None
    max_file_size_mb: Optional[int] = None


class AttachmentTypeResponse(AttachmentTypeBase):
    id: str
    created_at: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)
    
    class Config:
        from_attributes = True


class AttachmentBase(BaseModel):
    attachment_type_id: Optional[str] = None
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    file_hash: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class AttachmentCreate(AttachmentBase):
    pass


class AttachmentUpdate(BaseModel):
    attachment_type_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class AttachmentBulkDeleteRequest(BaseModel):
    """Request body for mass-deleting attachments."""
    attachment_ids: list[str]

    @field_validator("attachment_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("At least one attachment ID is required")
        return v


class AttachmentTypeSimple(BaseModel):
    id: str
    type_name: str
    description: Optional[str] = None
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)
    
    class Config:
        from_attributes = True


class AttachmentResponse(AttachmentBase):
    id: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    attachment_type: Optional[AttachmentTypeSimple] = None
    
    @field_validator('id', 'uploaded_by', 'deleted_by', 'attachment_type_id', 'entity_id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        if isinstance(v, str):
            return v
        return str(v)
    
    class Config:
        from_attributes = True
