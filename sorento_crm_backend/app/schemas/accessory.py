"""Accessories library + product / combo lists (PRICETAG-ACCESSORIES)."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AccessoryImageOut(BaseModel):
    attachment_id: str
    url: str


class AccessoryOut(BaseModel):
    id: str
    name: str
    #: One short line, printed as typed. Null = none.
    spec: Optional[str] = None
    image: Optional[AccessoryImageOut] = None
    #: How many products / combos list it (the library grid, and why a delete is refused).
    product_count: int = 0
    combo_count: int = 0


class AccessoryCreate(BaseModel):
    name: str = Field(max_length=500)
    spec: Optional[str] = Field(default=None, max_length=1000)


class AccessoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=500)
    #: Omitted = left alone; null or blank = cleared.
    spec: Optional[str] = Field(default=None, max_length=1000)


class AccessoryListOut(BaseModel):
    data: List[AccessoryOut] = []


class AccessoryIdsIn(BaseModel):
    #: The whole ordered list; replaces what was there.
    accessory_ids: List[str] = Field(default_factory=list, max_length=100)
