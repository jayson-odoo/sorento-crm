from typing import Dict, List

from pydantic import BaseModel


class ContactBrandRef(BaseModel):
    id: str
    brand_name: str


class ContactItemClassRef(BaseModel):
    id: str
    item_class_name: str


class ContactBrandsUpdate(BaseModel):
    """Replace a contact's accessible brands with this exact set (empty = every brand), and per
    brand the item classes it is narrowed to (a brand absent or mapped to [] = every class)."""
    brand_ids: List[str] = []
    brand_class_ids: Dict[str, List[str]] = {}


class ContactBrandsResponse(BaseModel):
    brand_ids: List[str] = []
    brands: List[ContactBrandRef] = []
    brand_class_ids: Dict[str, List[str]] = {}
    item_classes: List[ContactItemClassRef] = []
