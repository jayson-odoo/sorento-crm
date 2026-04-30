"""Resource management schemas."""
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import Optional, List, Literal
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
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class AttachmentDirectoryTreeNode(AttachmentDirectoryResponse):
    """Directory with nested children for tree API."""
    children: List["AttachmentDirectoryTreeNode"] = []


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
    model_config = ConfigDict(from_attributes=True)

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
    description: Optional[str] = None
    access_levels: Optional[list[str]] = None  # e.g. ["dealer", "end_user"]
    sort_order: Optional[int] = None


class AttachmentCreate(AttachmentBase):
    pass


class AttachmentUpdate(BaseModel):
    attachment_type_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    directory_id: Optional[str] = None
    description: Optional[str] = None
    access_levels: Optional[list[str]] = None
    sort_order: Optional[int] = None
    # Display name shown in the UI and used as Content-Disposition filename on download.
    # Updating this does NOT touch S3 — the underlying object key (stored_filename / file_path)
    # is immutable so existing CDN URLs keep resolving.
    original_filename: Optional[str] = None

    @field_validator("original_filename", mode="before")
    @classmethod
    def sanitize_original_filename(cls, v):
        """Trim, reject path separators / control chars, cap at 255 chars. None means 'no change'."""
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        s = v.strip()
        if not s:
            raise ValueError("original_filename cannot be empty.")
        if any(ch in s for ch in ("/", "\\", "\x00")) or any(ord(ch) < 32 for ch in s):
            raise ValueError("original_filename cannot contain path separators or control characters.")
        if len(s) > 255:
            raise ValueError("original_filename must not exceed 255 characters.")
        return s


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
    model_config = ConfigDict(from_attributes=True)

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
    
class LinkedEntityRef(BaseModel):
    """Reference to a linked entity (product, promotion, or form) resolved from junction/parent tables."""
    id: str
    name: str
    description: Optional[str] = None
    link_id: Optional[str] = None  # ProductAttachment/PromotionAttachment id for unlink; forms use id as form_id


class AttachmentResponse(AttachmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uploaded_by: Optional[str] = None
    uploaded_by_user: Optional[UploadedByUser] = None
    uploaded_at: datetime
    created_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    attachment_type: Optional[AttachmentTypeSimple] = None
    entity_display_name: Optional[str] = None
    linked_products: list[LinkedEntityRef] = []
    linked_promotions: list[LinkedEntityRef] = []
    linked_form: Optional[LinkedEntityRef] = None
    linked_packing_lists: list[LinkedEntityRef] = []

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


class AccessPropagationTarget(BaseModel):
    """Linked entity that can receive propagated access_levels (with human-facing code)."""
    kind: Literal["product", "promotion", "form", "packing_list"]
    entity_id: str
    code: str
    name: Optional[str] = None


class BulkAccessLevelsPreviewRequest(BaseModel):
    """Preview propagation targets: pass either directory_id (folder subtree) or attachment_ids (bulk selection)."""
    attachment_ids: Optional[list[str]] = None
    directory_id: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_scope(self):
        has_attachments = bool(self.attachment_ids and len(self.attachment_ids) > 0)
        has_dir = bool(self.directory_id and str(self.directory_id).strip())
        if has_attachments == has_dir:
            raise ValueError("Provide exactly one of: non-empty attachment_ids or directory_id")
        return self


class BulkAccessLevelsPreviewResponse(BaseModel):
    attachment_count: int
    targets: list[AccessPropagationTarget]


class BulkAccessLevelsApplyRequest(BaseModel):
    attachment_ids: Optional[list[str]] = None
    directory_id: Optional[str] = None
    access_levels: list[str]
    propagate_to_linked: bool = False

    @model_validator(mode="after")
    def exactly_one_scope(self):
        has_attachments = bool(self.attachment_ids and len(self.attachment_ids) > 0)
        has_dir = bool(self.directory_id and str(self.directory_id).strip())
        if has_attachments == has_dir:
            raise ValueError("Provide exactly one of: non-empty attachment_ids or directory_id")
        return self


class BulkAccessLevelsApplyResponse(BaseModel):
    updated_attachments: int
    propagated: Optional[dict] = None
