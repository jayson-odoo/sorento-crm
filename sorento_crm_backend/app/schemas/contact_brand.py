from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints


class ContactBrandRef(BaseModel):
    id: str
    brand_name: str


class ContactItemClassOption(BaseModel):
    code: str
    name: str


class ContactBrandsUpdate(BaseModel):
    """Replace a contact's accessible brands with this exact set (empty = every brand) and, when
    given, its allowed item class codes (empty = every class; absent = unchanged)."""
    brand_ids: List[str] = []
    allowed_item_class_codes: Optional[List[Annotated[str, StringConstraints(max_length=50)]]] = Field(
        None, max_length=500
    )


class ContactBrandsResponse(BaseModel):
    brand_ids: List[str] = []
    brands: List[ContactBrandRef] = []
    allowed_item_class_codes: List[str] = []
    item_class_options: List[ContactItemClassOption] = []
