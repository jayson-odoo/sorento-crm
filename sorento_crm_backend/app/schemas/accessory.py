"""Accessories library + product / combo lists (PRICETAG-ACCESSORIES)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AccessoryImageOut(BaseModel):
    attachment_id: str
    url: str


class AccessoryOut(BaseModel):
    """A library accessory, or (in a product / combo list only) a catalogue product entry.

    `kind = 'product'` (owner, 6 Nov ~10:45): `id` is the product's, `code` its code, `name` its
    description (else name), `list_price` its LP, `image` its lead photo, all read live."""

    kind: Literal["accessory", "product"] = "accessory"
    id: str
    name: str
    #: One short line, printed as typed. Null = none (always null on a product entry).
    spec: Optional[str] = None
    image: Optional[AccessoryImageOut] = None
    code: Optional[str] = None
    list_price: Optional[float] = None
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


class AccessoryListItemIn(BaseModel):
    """Exactly one of the two (checked in the service, a 422 otherwise)."""

    accessory_id: Optional[str] = None
    product_id: Optional[str] = None


class AccessoryItemsIn(BaseModel):
    #: The whole ordered list; replaces what was there.
    items: List[AccessoryListItemIn] = Field(default_factory=list, max_length=100)
