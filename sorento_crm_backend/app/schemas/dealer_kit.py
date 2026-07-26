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
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)

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
    doc: dict[str, Any]
    versions: list[PageVersionOut] = Field(default_factory=list)


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

    name: str
    slug: str
    doc: dict[str, Any]


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
