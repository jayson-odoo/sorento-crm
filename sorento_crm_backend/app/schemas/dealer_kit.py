"""Dealer Kit API schemas.

Field names are camelCase on the wire to match what the frontend page builder
already speaks, so the document round-trips without a translation layer that
could quietly drop a key.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PageCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    # Optional from the start: the flyer seed knows which promotion matches the
    # uploaded filename, and a page created by hand simply has no offer yet.
    promotion_id: Optional[str] = Field(default=None, validation_alias="promotionId")

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, v: str) -> str:
        # The slug becomes a public URL segment, so it is validated here rather
        # than left to whatever a Designer types.
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Address may use lowercase letters, numbers and single hyphens only"
            )
        return v


class PageSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    slug: str
    updated_at: datetime = Field(serialization_alias="updatedAt")
    published_version: Optional[int] = Field(
        default=None, serialization_alias="publishedVersion"
    )
    latest_version: int = Field(default=0, serialization_alias="latestVersion")
    # The shareable address, resolved server-side. See page_service.public_path.
    public_path: Optional[str] = Field(default=None, serialization_alias="publicPath")
    # Which promotion prices this brochure, when one does. Null is list prices
    # only, which is a normal state and not a defect (PLAN D5/D6).
    promotion_id: Optional[str] = Field(default=None, serialization_alias="promotionId")
    # Its description, resolved server-side so no id reaches a screen. Null when
    # nothing is linked OR when the promotion carries no description - the UI
    # supplies the words for the latter, never the uuid.
    promotion_label: Optional[str] = Field(
        default=None, serialization_alias="promotionLabel"
    )


class PageVersionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    version: int
    commit_message: Optional[str] = Field(default=None, serialization_alias="commitMessage")
    created_by: Optional[str] = Field(default=None, serialization_alias="createdBy")
    created_at: datetime = Field(serialization_alias="createdAt")
    labels: list[str] = Field(default_factory=list)


class PageDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    slug: str
    updated_at: datetime = Field(serialization_alias="updatedAt")
    published_version: Optional[int] = Field(
        default=None, serialization_alias="publishedVersion"
    )
    latest_version: int = Field(default=0, serialization_alias="latestVersion")
    public_path: Optional[str] = Field(default=None, serialization_alias="publicPath")
    promotion_id: Optional[str] = Field(default=None, serialization_alias="promotionId")
    promotion_label: Optional[str] = Field(
        default=None, serialization_alias="promotionLabel"
    )
    doc: dict[str, Any]
    versions: list[PageVersionOut] = Field(default_factory=list)


class PagePromotionSet(BaseModel):
    """Which promotion prices this brochure. ``null`` clears the link.

    One nullable field rather than a PUT/DELETE pair: clearing is the same
    editorial decision as choosing, made in the same control, and a null here
    says exactly what it means.
    """

    model_config = ConfigDict(populate_by_name=True)

    promotion_id: Optional[str] = Field(default=None, validation_alias="promotionId")


class PagePromotionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    page_id: str = Field(serialization_alias="pageId")
    promotion_id: Optional[str] = Field(default=None, serialization_alias="promotionId")
    promotion_label: Optional[str] = Field(
        default=None, serialization_alias="promotionLabel"
    )


class VersionCreate(BaseModel):
    doc: dict[str, Any]
    commit_message: Optional[str] = Field(
        default=None, max_length=500, validation_alias="commitMessage"
    )

    model_config = ConfigDict(populate_by_name=True)


class LabelMove(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version_id: str = Field(validation_alias="versionId")


class PublicPage(BaseModel):
    """What an unauthenticated reader receives.

    Carries the document and nothing about the page's editing history: version
    numbers and commit messages are internal, and a reader has no use for them.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    slug: str
    doc: dict[str, Any]
    # collectionId -> tiles, already priced for an anonymous reader.
    collections: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    tile_templates: dict[str, list[str]] = Field(
        default_factory=dict, serialization_alias="tileTemplates"
    )


# ---------------------------------------------------------------------------
# Collections and bundles (S2)
# ---------------------------------------------------------------------------


class CollectionWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scope: str = Field(default="page")
    page_id: Optional[str] = Field(default=None, validation_alias="pageId")
    name: Optional[str] = Field(default=None, max_length=200)
    conditions: Optional[dict[str, Any]] = None
    pinned_product_ids: list[str] = Field(
        default_factory=list, validation_alias="pinnedProductIds"
    )
    excluded_product_ids: list[str] = Field(
        default_factory=list, validation_alias="excludedProductIds"
    )
    manual_order: list[str] = Field(default_factory=list, validation_alias="manualOrder")


class CollectionRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CollectionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    scope: str
    name: Optional[str] = None
    page_id: Optional[str] = Field(default=None, serialization_alias="pageId")
    conditions: Optional[dict[str, Any]] = None
    pinned_product_ids: list[str] = Field(
        default_factory=list, serialization_alias="pinnedProductIds"
    )
    excluded_product_ids: list[str] = Field(
        default_factory=list, serialization_alias="excludedProductIds"
    )
    manual_order: list[str] = Field(default_factory=list, serialization_alias="manualOrder")
    member_count: int = Field(default=0, serialization_alias="memberCount")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class TileOut(BaseModel):
    """One resolved tile. `price` / `invoice_price` are strings the server has
    already decided this viewer may see; null means absent, not hidden."""

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    price: Optional[str] = None
    invoice_price: Optional[str] = Field(default=None, serialization_alias="invoicePrice")
    image_url: Optional[str] = Field(default=None, serialization_alias="imageUrl")
    dimensions: Optional[str] = None
    badges: list[str] = Field(default_factory=list)


class ResolvedCollectionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    collection_id: str = Field(serialization_alias="collectionId")
    name: Optional[str] = None
    tiles: list[TileOut] = Field(default_factory=list)


class BundleComponentWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(validation_alias="productId")
    quantity: int = Field(default=1, ge=1)


class BundleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0)
    components: list[BundleComponentWrite] = Field(min_length=1)


class BundleComponentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    quantity: int
    allocated: str
    available: bool


class ResolvedBundleOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    price: str
    available: bool
    unavailable_reason: Optional[str] = Field(
        default=None, serialization_alias="unavailableReason"
    )
    components: list[BundleComponentOut] = Field(default_factory=list)


class TileTemplateWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fields: list[str] = Field(min_length=1)


class TileTemplateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    fields: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ExportRequestIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # WHO the document is for, not who asked for it: staff exporting a dealer's
    # copy to email out is the normal case.
    audience: str = Field(default="staff")
    show_invoice_price: bool = Field(default=False, validation_alias="showInvoicePrice")
    version_id: Optional[str] = Field(default=None, validation_alias="versionId")


class ExportRequestOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_id: str = Field(serialization_alias="downloadId")
    status: str
    filename: Optional[str] = None
    audience: str


class SelectionCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(default=None, max_length=200)
    source_page_id: Optional[str] = Field(default=None, validation_alias="sourcePageId")


class SelectionRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SelectionLineWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(validation_alias="productId")
    # Absolute, not a delta: a client that retries a request must not order two.
    quantity: float = Field(default=1, ge=0)


class RoomWrite(BaseModel):
    """The room outline and what is standing in it.

    Free-form JSON on purpose: the shape of a placement is a FRONTEND concern
    that will move (rotation today, wall-mounted height tomorrow), and pinning
    it into a Pydantic model here would mean a backend release for every change
    to a drag handle. What the backend guarantees is that it round-trips
    unchanged, and that the outline is a polygon in millimetres.
    """

    model_config = ConfigDict(populate_by_name=True)

    outline: list[dict] = Field(default_factory=list)
    placements: list[dict] = Field(default_factory=list)
    # The one vertical number the room has. Ceiling height is what makes the 3D
    # view a room rather than a floor plan floating in space, and it is the only
    # Z measurement a dealer knows offhand - wall thickness is not asked for.
    ceiling_height_mm: Optional[float] = Field(
        default=None, validation_alias="ceilingHeightMm", serialization_alias="ceilingHeightMm"
    )
    # Doors and windows. Free-form for the same reason placements are: an
    # opening's shape is a frontend concern (a swing direction today, a handle
    # side tomorrow) and pinning it here would mean a backend release per
    # drag handle. They are NOT products - no price, never on a quote.
    openings: list[dict] = Field(default_factory=list)
    # Surface finishes: a floor id and per-wall ids. Ids, never colours - a
    # stored colour cannot be restyled and would ignore the theme forever.
    finishes: Optional[dict] = None


class QuoteRequest(BaseModel):
    """Which products the dealer is leaving OFF this quote.

    Product ids, not line ids: the caller is saying "not the mirror", and the
    line id is an implementation detail that changes when a quantity does.
    """

    model_config = ConfigDict(populate_by_name=True)

    excluded_product_ids: list[str] = Field(
        default_factory=list, validation_alias="excludedProductIds"
    )


class SelectionLineOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    line_id: str = Field(serialization_alias="lineId")
    product_id: str = Field(serialization_alias="productId")
    product_code: Optional[str] = Field(default=None, serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    quantity: float
    price: Optional[str] = None
    invoice_price: Optional[str] = Field(default=None, serialization_alias="invoicePrice")
    line_total: Optional[str] = Field(default=None, serialization_alias="lineTotal")
    dimensions_mm: Optional[dict] = Field(default=None, serialization_alias="dimensionsMm")
    is_available: bool = Field(serialization_alias="isAvailable")
    unavailable_reason: Optional[str] = Field(
        default=None, serialization_alias="unavailableReason"
    )


class QuoteLineOut(SelectionLineOut):
    """A quote line: a selection line plus whether it is on this quote."""

    included: bool = True


class QuoteOut(BaseModel):
    """What the design comes to, for the lines the dealer kept.

    Serialised through a model like every other dealer-kit response so the
    frontend reads camelCase everywhere. Returning the service dict raw is what
    made the first version of this screen show a priced row with no product
    code on it.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: Optional[str] = None
    currency: str = "MYR"
    lines: list[QuoteLineOut] = Field(default_factory=list)
    subtotal: str = "0.00"
    total: Optional[str] = None
    excluded_count: int = Field(default=0, serialization_alias="excludedCount")


class SelectionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: Optional[str] = None
    currency: str = "MYR"
    lines: list[SelectionLineOut] = Field(default_factory=list)
    total: Optional[str] = None
    unavailable_count: int = Field(default=0, serialization_alias="unavailableCount")
    room: Optional[dict] = None
    # Derived from the outline, never stored (AC-R5).
    room_area_sqm: Optional[float] = Field(default=None, serialization_alias="roomAreaSqm")
