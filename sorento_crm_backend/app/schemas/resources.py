"""Resource management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
import uuid


class AttachmentDirectoryBase(BaseModel):
    name: str
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None


class AttachmentDirectoryCreate(AttachmentDirectoryBase):
    pass


class AttachmentDirectoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None


class AttachmentDirectoryResponse(AttachmentDirectoryBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class AttachmentDirectoryTreeNode(AttachmentDirectoryResponse):
    """Directory with nested children for tree API."""
    children: List["AttachmentDirectoryTreeNode"] = []

    class Config:
        from_attributes = True


# Allow self-reference for tree
AttachmentDirectoryTreeNode.model_rebuild()


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
    directory_id: Optional[str] = None
    full_directory_path: Optional[str] = None  # e.g. "SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve"
    sort_order: Optional[int] = None


class AttachmentCreate(AttachmentBase):
    pass


class AttachmentUpdate(BaseModel):
    attachment_type_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    directory_id: Optional[str] = None
    sort_order: Optional[int] = None


class AttachmentBulkDeleteRequest(BaseModel):
    """Request body for mass-deleting attachments."""
    attachment_ids: list[str]

    @field_validator("attachment_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("At least one attachment ID is required")
        return v


class AttachmentReorderRequest(BaseModel):
    """Request body for reordering attachments within a folder."""
    directory_id: Optional[str] = None
    attachment_ids: list[str]

    @field_validator("attachment_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("At least one attachment ID is required")
        return v


class UploadedByUser(BaseModel):
    """User who uploaded the attachment (for display)."""
    id: str
    name: Optional[str] = None
    email: Optional[str] = None

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)


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


class LinkedEntityRef(BaseModel):
    """Reference to a linked entity (product, promotion, or form) resolved from junction/parent tables."""
    id: str
    name: str
    description: Optional[str] = None
    link_id: Optional[str] = None  # ProductAttachment/PromotionAttachment id for unlink; forms use id as form_id


class AttachmentResponse(AttachmentBase):
    id: str
    uploaded_by: Optional[str] = None
    uploaded_by_user: Optional[UploadedByUser] = None
    uploaded_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    attachment_type: Optional[AttachmentTypeSimple] = None
    entity_display_name: Optional[str] = None
    linked_products: list[LinkedEntityRef] = []
    linked_promotions: list[LinkedEntityRef] = []
    linked_form: Optional[LinkedEntityRef] = None

    @field_validator('id', 'uploaded_by', 'deleted_by', 'attachment_type_id', 'entity_id', 'directory_id', mode='before')
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
