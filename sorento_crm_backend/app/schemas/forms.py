"""Forms management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime
import uuid
from app.schemas.resources import AttachmentTypeSimple


class FormBase(BaseModel):
    code: str
    name: str
    form_type: str = "marketing"
    purpose: Optional[str] = None
    language: str = "en"
    version: int = 1
    is_active: bool = False
    attachment_id: Optional[str] = None


class FormCreate(FormBase):
    pass


class FormUpdate(BaseModel):
    name: Optional[str] = None
    form_type: Optional[str] = None
    purpose: Optional[str] = None
    language: Optional[str] = None
    version: Optional[int] = None
    is_active: Optional[bool] = None
    attachment_id: Optional[str] = None


class AttachmentSimple(BaseModel):
    """Simple attachment reference for Form."""
    id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    attachment_type: Optional[AttachmentTypeSimple] = None
    
    class Config:
        from_attributes = True


class FormResponse(FormBase):
    id: str
    # created_by column doesn't exist in database, removed from response
    # created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    attachment: Optional[AttachmentSimple] = None
    
    @field_validator('attachment_id', 'id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class FormSectionBase(BaseModel):
    form_id: str
    section_name: str
    section_order: int = 0


class FormSectionCreate(FormSectionBase):
    pass


class FormSectionUpdate(BaseModel):
    section_name: Optional[str] = None
    section_order: Optional[int] = None


class FormSectionResponse(FormSectionBase):
    id: str
    created_at: datetime
    
    @field_validator('form_id', 'id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class FormFieldBase(BaseModel):
    section_id: str
    field_name: str
    field_label: str
    field_type: str
    is_required: bool = False
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    validation_rule: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    default_value: Optional[str] = None
    conditional_logic: Optional[Any] = None
    field_order: int = 0


class FormFieldCreate(FormFieldBase):
    pass


class FormFieldUpdate(BaseModel):
    field_name: Optional[str] = None
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    validation_rule: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    default_value: Optional[str] = None
    conditional_logic: Optional[Any] = None
    field_order: Optional[int] = None


class FormFieldResponse(FormFieldBase):
    id: str
    created_at: datetime
    
    @field_validator('section_id', 'id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class FormSubmissionBase(BaseModel):
    form_id: str
    status: str = "draft"
    submission_data: dict


class FormSubmissionCreate(FormSubmissionBase):
    pass


class FormSubmissionUpdate(BaseModel):
    status: Optional[str] = None
    submission_data: Optional[dict] = None


class FormSubmissionResponse(FormSubmissionBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormVersionBase(BaseModel):
    form_id: str
    version_number: int
    structure: Any
    change_summary: Optional[str] = None
    is_active: bool = False


class FormVersionCreate(FormVersionBase):
    pass


class FormVersionResponse(FormVersionBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    
    @field_validator('form_id', 'id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True
