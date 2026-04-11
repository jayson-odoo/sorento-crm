"""External forms schemas."""

from typing import List, Optional

from pydantic import BaseModel

from app.schemas.forms import FormResponse


class FormRequest(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    attachment_id: Optional[str] = None


class FormHeaderInput(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    attachment_id: Optional[str] = None


class FormSectionInput(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    class Config:
        extra = "ignore"


class FormFieldInput(BaseModel):
    name: Optional[str] = None
    section: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = None
    options: Optional[List[str]] = None

    class Config:
        extra = "ignore"


class FormCreateRequest(BaseModel):
    form: FormHeaderInput
    form_sections: Optional[List[FormSectionInput]] = None
    form_fields: Optional[List[FormFieldInput]] = None
    attachment_id: Optional[str] = None
    notify_user_id: Optional[str] = None


class FormCreateResponse(BaseModel):
    form: FormResponse
    already_existed: bool = False
    message: Optional[str] = None

