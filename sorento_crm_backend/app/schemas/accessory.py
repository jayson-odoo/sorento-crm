"""Accessories library + product / combo lists (PRICETAG-ACCESSORIES)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


HEX_PATTERN = r"^#[0-9a-fA-F]{6}$"


class AccessoryPictureOut(BaseModel):
    """A picture as the old single-image callers read it."""

    attachment_id: str
    url: str


class AccessoryImageOut(BaseModel):
    """One of an accessory's ordered pictures, with its optional colour."""

    id: str
    attachment_id: str
    url: str
    colour_name: Optional[str] = None
    colour_hex: Optional[str] = None


class AccessoryImagePatch(BaseModel):
    #: Omitted = left alone; null clears.
    colour_name: Optional[str] = Field(default=None, max_length=40)
    colour_hex: Optional[str] = Field(default=None, pattern=HEX_PATTERN)


class AccessoryImageOrderIn(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=100)


class AccessoryEntryOut(BaseModel):
    """The stored per-row overrides of a list entry (nulls when none)."""

    image_id: Optional[str] = None
    name: Optional[str] = None
    spec: Optional[str] = None
    remark: Optional[str] = None


class AccessoryOut(BaseModel):
    """A library accessory, or (in a product / combo list only) a catalogue product entry.

    `kind = 'product'` (owner, 6 Nov ~10:45): `id` is the product's, `code` its code, `name` its
    description (else name), `list_price` its LP, `image` its lead photo, all read live."""

    kind: Literal["accessory", "product"] = "accessory"
    id: str
    name: str
    #: Plain text or sanitised rich HTML. Null = none. On a product entry: its price tag description.
    spec: Optional[str] = None
    remark: Optional[str] = None
    #: The first picture (kept for old callers); `images` is the whole ordered set.
    image: Optional[AccessoryPictureOut] = None
    images: List[AccessoryImageOut] = []
    #: Only in a product / combo list: the overrides stored on that row.
    entry: Optional[AccessoryEntryOut] = None
    code: Optional[str] = None
    list_price: Optional[float] = None
    #: How many products / combos list it (the library grid, and why a delete is refused).
    product_count: int = 0
    combo_count: int = 0


class AccessoryCreate(BaseModel):
    name: str = Field(max_length=500)
    #: Sanitised in the service, which then holds it to 4000 characters.
    spec: Optional[str] = Field(default=None, max_length=20000)
    remark: Optional[str] = Field(default=None, max_length=20000)


class AccessoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=500)
    #: Omitted = left alone; null or blank = cleared.
    spec: Optional[str] = Field(default=None, max_length=20000)
    remark: Optional[str] = Field(default=None, max_length=20000)


class AccessoryListOut(BaseModel):
    data: List[AccessoryOut] = []


class AccessoryListItemIn(BaseModel):
    """Exactly one of the two (checked in the service, a 422 otherwise)."""

    accessory_id: Optional[str] = None
    product_id: Optional[str] = None
    #: A picture of THIS accessory (never on a product entry). Blank strings below = no override.
    image_id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=1000)
    spec: Optional[str] = Field(default=None, max_length=20000)
    remark: Optional[str] = Field(default=None, max_length=20000)


class AccessoryItemsIn(BaseModel):
    #: The whole ordered list; replaces what was there.
    items: List[AccessoryListItemIn] = Field(default_factory=list, max_length=100)
