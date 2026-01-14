"""Resource management schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


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


class AttachmentTypeSimple(BaseModel):
    id: str
    type_name: str
    description: Optional[str] = None
    
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
    
    class Config:
        from_attributes = True
