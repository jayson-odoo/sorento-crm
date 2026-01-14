"""Forms management schemas."""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class FormBase(BaseModel):
    code: str
    name: str
    purpose: Optional[str] = None
    language: str = "en"
    version: int = 1
    is_active: bool = False
    attachment_id: Optional[str] = None


class FormCreate(FormBase):
    pass


class FormUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    language: Optional[str] = None
    version: Optional[int] = None
    is_active: Optional[bool] = None
    attachment_id: Optional[str] = None


class FormResponse(FormBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
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
    
    class Config:
        from_attributes = True
