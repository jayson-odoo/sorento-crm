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
    storage_provider: Optional[str] = None  # 's3' or 'r2'; controls URL signing dispatch
    # Field-linkage template applied when the attachment is later linked to a
    # specific row via any link API. See app.services.field_linkage.registry.
    target_entity_type: Optional[str] = None
    target_field_keys: Optional[list[str]] = None


def _validate_field_linkage_template(target_entity_type, target_field_keys):
    """Shared validator used on both AttachmentCreate and AttachmentUpdate.

    Empty inputs are tolerated: the template is opt-in. When a target_entity_type
    is given without keys (or vice versa) we leave the row in a partial state —
    it just won't fan out anything until a future PUT completes the pair.
    """
    from app.services.field_linkage import (
        SUPPORTED_ENTITY_TYPES,
        validate_field_keys,
    )

    et = (target_entity_type or "").strip() or None
    if et and et not in SUPPORTED_ENTITY_TYPES:
        raise ValueError(
            f"Unsupported target_entity_type '{et}'. "
            f"Expected one of: {', '.join(SUPPORTED_ENTITY_TYPES)}."
        )
    if target_field_keys and et:
        ok, unknown = validate_field_keys(et, list(target_field_keys))
        if unknown:
            raise ValueError(
                f"Unknown target_field_keys for {et}: {', '.join(unknown)}"
            )
        return et, ok
    if target_field_keys and not et:
        raise ValueError(
            "target_entity_type is required when target_field_keys are provided."
        )
    return et, list(target_field_keys or [])


class AttachmentCreate(AttachmentBase):
    @model_validator(mode="after")
    def _check_field_linkage_template(self):
        et, keys = _validate_field_linkage_template(
            self.target_entity_type, self.target_field_keys
        )
        object.__setattr__(self, "target_entity_type", et)
        object.__setattr__(self, "target_field_keys", keys or None)
        return self


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
    target_entity_type: Optional[str] = None
    target_field_keys: Optional[list[str]] = None

    @model_validator(mode="after")
    def _check_field_linkage_template(self):
        # Only validate when one of the two is explicitly provided. PATCH-style:
        # both None means "don't touch the template".
        if self.target_entity_type is None and self.target_field_keys is None:
            return self
        et, keys = _validate_field_linkage_template(
            self.target_entity_type, self.target_field_keys
        )
        self.target_entity_type = et
        self.target_field_keys = keys or None
        return self

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


class AttachmentsBulkMoveRequest(BaseModel):
    """Move many attachments into the same target folder in one transaction."""
    attachment_ids: list[str]
    directory_id: Optional[str] = None

    @field_validator("attachment_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one attachment ID is required")
        return v


class AttachmentsBulkMoveResponse(BaseModel):
    updated: int


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


class BulkAttachmentTypeRequest(BaseModel):
    """Bulk-edit (or single-edit) attachment_type_id on N attachments.
    Does NOT trigger any webhook resubmission — purely a metadata change."""

    attachment_ids: list[str]
    attachment_type_id: str

    @field_validator("attachment_ids")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("At least one attachment ID is required.")
        return v


class BulkAttachmentTypeResponse(BaseModel):
    updated_attachments: int
    attachment_type_id: str
