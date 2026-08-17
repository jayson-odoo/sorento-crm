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
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # The page's default tile design. The editor needs both: the id to seed its
    # control, the name to say which one is in force without printing a uuid.
    tile_template_id: Optional[str] = Field(
        default=None, serialization_alias="tileTemplateId"
    )
    tile_template_name: Optional[str] = Field(
        default=None, serialization_alias="tileTemplateName"
    )
    doc: dict[str, Any]
    versions: list[PageVersionOut] = Field(default_factory=list)
    # assetId -> signed URL for the section backgrounds ``doc`` binds, resolved
    # exactly as the public payload resolves them. The builder cannot sign its
    # own: the document holds ids, and a second signer would be a second opinion
    # about which assets are unsignable - so a background could appear in the
    # editor and be missing on the published page, which is the disagreement the
    # shared renderer exists to prevent. Absent rather than broken, always.
    assets: dict[str, str] = Field(default_factory=dict)


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


class PageTileTemplateSet(BaseModel):
    """The design every collection block on this page uses by default.

    Same one-nullable-field shape as the promotion above, for the same reason:
    clearing is the same decision as choosing, made in the same control.
    """

    model_config = ConfigDict(populate_by_name=True)

    tile_template_id: Optional[str] = Field(
        default=None, validation_alias="tileTemplateId"
    )


class PageTileTemplateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    page_id: str = Field(serialization_alias="pageId")
    tile_template_id: Optional[str] = Field(
        default=None, serialization_alias="tileTemplateId"
    )
    # Its name, resolved server-side so no uuid reaches a screen.
    tile_template_name: Optional[str] = Field(
        default=None, serialization_alias="tileTemplateName"
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


class ProductThumbnailsIn(BaseModel):
    """Which products a picker is showing right now.

    Ids the CALLER already has, not a query: this endpoint does not decide which
    products exist, it only says what the ones on screen look like.
    """

    model_config = ConfigDict(populate_by_name=True)

    product_ids: list[str] = Field(default_factory=list, validation_alias="productIds")


class ProductThumbnailsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # productId -> signed thumbnail. A product with no permitted image is
    # ABSENT, so the card shows its no-image state rather than a broken one.
    urls: dict[str, str] = Field(default_factory=dict)


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
    # The design a collection block uses when it does not name one of its own.
    # Sent as an id rather than resolved into every block because the document
    # is the record of what was published and must not be rewritten on its way
    # to a reader: the block genuinely has no design, the PAGE does.
    default_tile_template_id: Optional[str] = Field(
        default=None, serialization_alias="defaultTileTemplateId"
    )
    # assetId -> signed URL, for the artwork sections use as a background. Sent
    # WITH the page rather than fetched per section: the same renderer is
    # printed by headless Chromium, which declares itself finished when the
    # network goes idle, and a background that arrives after that is a blank
    # band in a PDF nobody re-checks. An asset that cannot be signed is absent,
    # never a URL the CDN will answer 403 to.
    assets: dict[str, str] = Field(default_factory=dict)


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
    """One resolved tile. `price` / `offer_price` / `invoice_price` are strings
    the server has already decided this viewer may see; null means absent, not
    hidden. The promotion's id is deliberately not here: naming an offer to a
    reader who cannot have it is the same leak as sending its figure."""

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    price: Optional[str] = None
    # What the page's promotion charges THIS reader, when one applies to them.
    # Sent beside `price`, not instead of it, so the tile can strike the list
    # price through and show the saving (ADR 0008).
    offer_price: Optional[str] = Field(default=None, serialization_alias="offerPrice")
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


# ---------------------------------------------------------------------------
# Flyer readings and their match report (S7.3)
# ---------------------------------------------------------------------------


class CodeSuggestionOut(BaseModel):
    """The nearest existing code to one the master does not have.

    Carries its score because a reviewer clicking "apply" is entitled to see how
    confident the guess is: a suggestion with no number behind it reads as a
    fact, and applying it silently puts the wrong product in front of a customer.
    """

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    similarity: float


class MatchedCodeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    # Every page it was printed on, not just the first. A reviewer is holding the
    # flyer, and "it is wrong somewhere" is not a correction anybody can make.
    pages: list[int] = Field(default_factory=list)


class UnmatchedCodeOut(BaseModel):
    """A printed code the master does not have.

    No product id, deliberately: the gap is the point, and a reader of this
    object cannot accidentally treat the suggestion as the answer (PLAN D8).
    """

    model_config = ConfigDict(populate_by_name=True)

    code: str
    pages: list[int] = Field(default_factory=list)
    suggestion: Optional[CodeSuggestionOut] = None


class DimensionCandidateOut(BaseModel):
    """A size the flyer printed, beside the size the product currently holds.

    A review queue entry. Nothing is written to the product master from a
    reading (PLAN D9) - which of the two records is wrong is a decision for
    somebody holding the master-data permission.
    """

    model_config = ConfigDict(populate_by_name=True)

    code: str
    product_id: str = Field(serialization_alias="productId")
    pages: list[int] = Field(default_factory=list)
    printed_length_mm: float = Field(serialization_alias="printedLengthMm")
    printed_width_mm: float = Field(serialization_alias="printedWidthMm")
    printed_height_mm: float = Field(serialization_alias="printedHeightMm")
    current_length_mm: Optional[float] = Field(
        default=None, serialization_alias="currentLengthMm"
    )
    current_width_mm: Optional[float] = Field(
        default=None, serialization_alias="currentWidthMm"
    )
    current_height_mm: Optional[float] = Field(
        default=None, serialization_alias="currentHeightMm"
    )
    # missing / agrees / conflicts.
    verdict: str


class MatchReportOut(BaseModel):
    """Everything the review screen needs, and nothing it has to derive."""

    model_config = ConfigDict(populate_by_name=True)

    matched: list[MatchedCodeOut] = Field(default_factory=list)
    unmatched: list[UnmatchedCodeOut] = Field(default_factory=list)
    not_promoted: list[MatchedCodeOut] = Field(
        default_factory=list, serialization_alias="notPromoted"
    )
    dimension_candidates: list[DimensionCandidateOut] = Field(
        default_factory=list, serialization_alias="dimensionCandidates"
    )
    # code -> the pages it was printed on, for codes printed more than once.
    duplicates: dict[str, list[int]] = Field(default_factory=dict)
    promotion_id: Optional[str] = Field(default=None, serialization_alias="promotionId")


class FlyerReadingSummary(BaseModel):
    """One uploaded flyer, WITHOUT its report.

    The list screen only says which flyers have been read. Attaching a report to
    each row would run a match per row for a screen nobody reads them on.

    ``status`` is on the SUMMARY and not only the detail because the list is the
    surface a designer watches a read on: they post a flyer, the dialog closes,
    and this row is where they learn it is still going, finished, or failed.
    ``errorMessage`` travels beside it for the same reason - a Failed pill with
    no words sends them back to upload the same broken file.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    filename: str
    byte_size: int = Field(serialization_alias="byteSize")
    page_count: int = Field(default=0, serialization_alias="pageCount")
    code_count: int = Field(default=0, serialization_alias="codeCount")
    uploaded_at: datetime = Field(serialization_alias="uploadedAt")
    # ``processing`` / ``done`` / ``failed``. Defaulted so a row written before
    # migration 359 (or by a test building the model by hand) reads as done,
    # which is what happened to every one of them.
    status: str = Field(default="done")
    error_message: Optional[str] = Field(default=None, serialization_alias="errorMessage")
    finished_at: Optional[datetime] = Field(
        default=None, serialization_alias="finishedAt"
    )


class PageHeadingOut(BaseModel):
    """What the reader thinks page N is called.

    Heading detection is a heuristic (the largest non-card text in the top
    band) and it is wrong wherever the heading is part of the artwork. The
    review screen therefore has to show the heading rather than only warn that
    headings are guessed: a reviewer can correct only what they can see.

    ``text`` is null for a page the reader found no heading on. That page is
    still listed, because one missing from the list is one nobody checks.
    """

    model_config = ConfigDict(populate_by_name=True)

    page: int
    text: Optional[str] = None


class FlyerReadingOut(FlyerReadingSummary):
    """One flyer and what it means right now.

    ``report`` is recomputed on every read and never stored - see
    ``flyer_reading_service``. That is why it lives on the detail response and
    not on the row.

    ``headings`` comes off the STORED reading rather than the report: it is
    what the reader found, not what the master says, and the seed writes the
    same values as its section names.
    """

    report: MatchReportOut
    headings: list[PageHeadingOut] = Field(default_factory=list)


class FlyerReadingFromAttachmentIn(BaseModel):
    """Read a flyer that is already in the file library.

    The whole request is which file, because everything else about it - name,
    size, type, folder - is already known. ``promotionId`` is the same optional
    question the upload asks as a query parameter: which offer to report the
    printed products against.

    Both are ``UUID`` and not ``str``, so a malformed value is a 422 at the edge
    and can never reach a WHERE clause. This feature has produced that 500 once.
    """

    model_config = ConfigDict(populate_by_name=True)

    attachment_id: UUID = Field(validation_alias="attachmentId")
    promotion_id: Optional[UUID] = Field(default=None, validation_alias="promotionId")


# ---------------------------------------------------------------------------
# Seeding a brochure from a reading (S7.4)
# ---------------------------------------------------------------------------


class FlyerSeedIn(BaseModel):
    """Where a seed goes, and which offer prices it.

    ``pageId`` re-seeds an existing brochure as a new version; ``name`` plus
    ``slug`` create one. Exactly one of the two - see the validator.
    """

    model_config = ConfigDict(populate_by_name=True)

    page_id: Optional[str] = Field(default=None, validation_alias="pageId")
    name: Optional[str] = Field(default=None, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=200)
    # A UUID at the edge, not a str: a malformed value is then a 422 and can
    # never reach a WHERE clause. This feature has produced that 500 once.
    promotion_id: Optional[UUID] = Field(default=None, validation_alias="promotionId")
    commit_message: Optional[str] = Field(
        default=None, max_length=500, validation_alias="commitMessage"
    )

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, v: Optional[str]) -> Optional[str]:
        # Same rule as PageCreate: the slug becomes a public URL segment.
        if v is None:
            return None
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Address may use lowercase letters, numbers and single hyphens only"
            )
        return v

    @model_validator(mode="after")
    def _one_target(self) -> "FlyerSeedIn":
        from app.services.dealer_kit.flyer_seed_service import (
            assert_target_is_unambiguous,
        )

        assert_target_is_unambiguous(self.page_id, self.name, self.slug)
        return self


class FlyerSeedOut(BaseModel):
    """What the seed made, for the screen that asked for it.

    Counts rather than the document: the review screen sends the caller straight
    into the builder, which loads the page itself.
    """

    model_config = ConfigDict(populate_by_name=True)

    page_id: str = Field(serialization_alias="pageId")
    name: str
    slug: str
    public_path: Optional[str] = Field(default=None, serialization_alias="publicPath")
    version_id: str = Field(serialization_alias="versionId")
    version: int
    section_count: int = Field(default=0, serialization_alias="sectionCount")
    collection_count: int = Field(default=0, serialization_alias="collectionCount")
    seeded_product_count: int = Field(
        default=0, serialization_alias="seededProductCount"
    )
    # Printed codes that reached no tile, each with the nearest existing code as
    # a suggestion. The same shape the match report uses, because it is the same
    # answer - and a seed is only trustworthy if what it dropped is visible.
    skipped: list[UnmatchedCodeOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Applying a flyer's printed sizes to the product master (S7.6)
# ---------------------------------------------------------------------------


class DimensionApplyIn(BaseModel):
    """Which printed sizes to write, and nothing about what they are.

    Codes only, deliberately. The millimetres are read off the stored flyer, so
    a caller cannot put a figure of their own into the product master through
    this route - it would otherwise be a "write anything to products" endpoint
    reachable by anybody who can upload a PDF.
    """

    model_config = ConfigDict(populate_by_name=True)

    codes: list[str] = Field(default_factory=list, max_length=2000)
    # Permission to replace a value somebody entered deliberately, given for the
    # NAMED codes only. Default false: a conflict is a decision, not a
    # correction, and the dangerous case must never be the quiet one.
    overwrite_conflicts: bool = Field(
        default=False, validation_alias="overwriteConflicts"
    )

    @model_validator(mode="after")
    def _something_was_named(self) -> "DimensionApplyIn":
        from app.services.dealer_kit.dimension_apply_service import normalise_codes

        if not normalise_codes(self.codes):
            raise ValueError(
                "Name the sizes to apply. This never applies everything it found."
            )
        return self


class AppliedDimensionOut(BaseModel):
    """One product whose size now says what the flyer says.

    ``previous*`` is on the wire because it is the only place the replaced value
    still exists in front of the person who replaced it.
    """

    model_config = ConfigDict(populate_by_name=True)

    code: str
    # Named, never identified: no uuid reaches a screen.
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    pages: list[int] = Field(default_factory=list)
    length_mm: float = Field(serialization_alias="lengthMm")
    width_mm: float = Field(serialization_alias="widthMm")
    height_mm: float = Field(serialization_alias="heightMm")
    previous_length_mm: Optional[float] = Field(
        default=None, serialization_alias="previousLengthMm"
    )
    previous_width_mm: Optional[float] = Field(
        default=None, serialization_alias="previousWidthMm"
    )
    previous_height_mm: Optional[float] = Field(
        default=None, serialization_alias="previousHeightMm"
    )
    # True when this replaced a value the master already held.
    was_conflict: bool = Field(default=False, serialization_alias="wasConflict")


class RefusedDimensionOut(BaseModel):
    """One code that was asked for and not written, and why."""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    # conflict_not_confirmed / already_matches / product_not_found /
    # not_a_candidate. Separate reasons because each sends a reviewer somewhere
    # different, and one "failed" sends most of them to the wrong place.
    reason: str
    message: str


class DimensionApplyOut(BaseModel):
    """What was written and what was not - every code asked for, exactly once.

    The counts are on the wire rather than left to the screen so the two can
    never disagree, and so a client that renders only the successes still
    reports the failures.
    """

    model_config = ConfigDict(populate_by_name=True)

    applied: list[AppliedDimensionOut] = Field(default_factory=list)
    refused: list[RefusedDimensionOut] = Field(default_factory=list)
    applied_count: int = Field(default=0, serialization_alias="appliedCount")
    refused_count: int = Field(default=0, serialization_alias="refusedCount")


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
    # The promotion's price for this reader, when one reaches them. `line_total`
    # already reflects it, so the browser never multiplies anything (ADR 0008).
    offer_price: Optional[str] = Field(default=None, serialization_alias="offerPrice")
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


# ---------------------------------------------------------------------------
# Editions (S2.5)
# ---------------------------------------------------------------------------


class EditionCreateIn(BaseModel):
    """Start a revision cycle over a page.

    ``previousEditionId`` is set when this Edition was duplicated from the last
    one (AC-L9) and left null when somebody starts a fresh cycle. It is what
    lets the next slice badge "new since the last Edition" without guessing.
    """

    model_config = ConfigDict(populate_by_name=True)

    page_id: UUID = Field(validation_alias="pageId")
    name: str = Field(min_length=1, max_length=200)
    previous_edition_id: Optional[UUID] = Field(
        default=None, validation_alias="previousEditionId"
    )


class EditionRejectIn(BaseModel):
    """Why it is going back.

    Required, with a real minimum length: the Designer reads this and "no" on
    its own is a rejection nobody can act on. Re-checked in the service, which
    is the last place that can refuse a whitespace-only reason.
    """

    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(min_length=1, max_length=2000)


class EditionOut(BaseModel):
    """One Edition, as a screen reads it.

    ``status`` is the KEY, not the status id: the id is a uuid and no uuid
    reaches the UI. The label is sent beside it so a screen never has to keep
    its own copy of the vocabulary.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    page_id: str = Field(serialization_alias="pageId")
    page_name: Optional[str] = Field(default=None, serialization_alias="pageName")
    name: str
    status: str
    status_label: str = Field(serialization_alias="statusLabel")
    approved_version_id: Optional[str] = Field(
        default=None, serialization_alias="approvedVersionId"
    )
    done_version_id: Optional[str] = Field(
        default=None, serialization_alias="doneVersionId"
    )
    previous_edition_id: Optional[str] = Field(
        default=None, serialization_alias="previousEditionId"
    )
    submitted_at: Optional[datetime] = Field(
        default=None, serialization_alias="submittedAt"
    )
    approved_at: Optional[datetime] = Field(
        default=None, serialization_alias="approvedAt"
    )
    rejection_reason: Optional[str] = Field(
        default=None, serialization_alias="rejectionReason"
    )
    created_at: datetime = Field(serialization_alias="createdAt")


class ReviewedProductOut(BaseModel):
    """One product the inherited catalogue still shows."""

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: str = Field(serialization_alias="productCode")
    product_name: str = Field(serialization_alias="productName")
    stock_on_hand: int = Field(serialization_alias="stockOnHand")
    is_new_since_previous: bool = Field(serialization_alias="isNewSincePrevious")


class DroppedProductOut(BaseModel):
    """A product this catalogue names and can no longer show.

    ``productCode`` is null when the row is gone entirely - there is nothing
    left to name it by, and inventing a placeholder would read as a real code.
    """

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(serialization_alias="productId")
    product_code: Optional[str] = Field(default=None, serialization_alias="productCode")
    product_name: Optional[str] = Field(default=None, serialization_alias="productName")
    reason: str


class EditionReviewOut(BaseModel):
    """What changed in the catalogue since the previous Edition (AC-L9)."""

    model_config = ConfigDict(populate_by_name=True)

    members: list[ReviewedProductOut] = Field(default_factory=list)
    dropped: list[DroppedProductOut] = Field(default_factory=list)
    previous_edition_name: Optional[str] = Field(
        default=None, serialization_alias="previousEditionName"
    )


# --------------------------------------------------------------------------- #
# Flyer -> product specification proposals (PR 5)
#
# **These are snake_case on the wire, unlike everything above.** The rows they carry
# (`spec_key`, `stored_value`, `data_type`) go straight into
# `components/spec-proposals`, which is the product-specification domain's shared
# review component and speaks snake_case, as does every other spec endpoint. A
# camelCase batch wrapping snake_case rows is two conventions in one response, and the
# UAC names every field of these four routes in snake_case (AC-B.1, AC-B.2, AC-C.1).
# The contract block at the top of the frontend's `flyerSpecProposalService.ts` is the
# same shape, field for field.
# --------------------------------------------------------------------------- #
class FlyerSpecBatchOut(BaseModel):
    """One proposal pass over one flyer reading, as a list row or a page header.

    `id` is null exactly when `status` is `none`, which is what the per-reading GET
    answers for a flyer nobody has proposed from - never a 404, because "not proposed
    yet" is a state the screen has to render.

    `filename` and `read_at` come off the reading, and the two `*_by_name` fields are
    resolved to NAMES here: the list screen and the reading-page section have no second
    call to get either, and no uuid reaches the UI (AC-B.3).
    """

    id: Optional[str] = None
    reading_id: str
    filename: str
    # none | proposing | proposed | failed
    status: str
    error_message: Optional[str] = None

    product_count: int = 0
    proposal_count: int = 0
    new_count: int = 0
    change_count: int = 0
    conflict_count: int = 0
    unchanged_count: int = 0
    suppressed_count: int = 0
    applied_count: int = 0

    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    applied_by_name: Optional[str] = None


class FlyerSpecProposalOut(BaseModel):
    """One key the flyer states about one product, judged against what is stored.

    `id` is on the wire because the apply payload names these and nothing else; every
    other identifier here is human-readable.
    """

    id: str
    spec_key: str
    label: str
    data_type: str
    value: Any
    unit: Optional[str] = None
    evidence: str = ""
    # new | change | conflict | unchanged | suppressed
    kind: str
    stored_value: Any = None
    stored_unit: Optional[str] = None
    stored_source: Optional[str] = None
    # The key's vocabulary when it has a closed one, so the in-place edit widget can
    # render its dropdown without a second call per row (AC-F.5). Null - not an empty
    # list - for a key with no closed vocabulary: "there is no list" and "the list is
    # empty" are different instructions to a widget.
    allowed_values: Optional[list[Any]] = None
    # flyer | manual. Who put the row here, which is what decides whether the value is
    # written as `flyer` or as `human` (AC-G.2).
    origin: str = "flyer"
    # True once somebody has corrected this row's value on the review screen (AC-F.2).
    edited: bool = False
    # applied | already_matches | conflict_not_confirmed | product_spec_bad_value |
    # product_not_found. Null until somebody has decided about this row.
    outcome: Optional[str] = None
    applied_at: Optional[datetime] = None


class FlyerSpecProductGroupOut(BaseModel):
    """Every proposal for one product, in the order the flyer prints it."""

    product_id: str
    product_code: str
    product_name: str
    pages: list[int] = Field(default_factory=list)
    proposals: list[FlyerSpecProposalOut] = Field(default_factory=list)


class FlyerSpecProposalsOut(FlyerSpecBatchOut):
    """The batch, and its rows when it has any. Empty unless `status` is `proposed`."""

    groups: list[FlyerSpecProductGroupOut] = Field(default_factory=list)


class FlyerSpecApplyIn(BaseModel):
    """Which stored proposals to write, and nothing about what they say.

    Ids only, deliberately. The values are read off the stored proposals, which were
    read off the flyer, so a caller cannot put a value of its own into the product
    master through this route - it would otherwise be a "write anything to
    product_specifications" endpoint reachable by anybody who can upload a PDF (L8).

    `extra="forbid"`, so a body carrying `values` is refused rather than quietly
    ignored: a client that sent one believes it is being honoured.

    There is deliberately NO `max_length` here. The ceiling on one apply belongs to
    `product_spec_flyer_ingest.MAX_ROWS`, which refuses with a sentence naming the
    number sent and the number allowed; a second ceiling in this schema would 422 first
    with pydantic's own "List should have at most 5000 items" and that readable sentence
    would never be reached. One guard, in the place that can explain itself.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_ids: list[UUID] = Field(min_length=1)


class FlyerSpecProposalEditIn(BaseModel):
    """A corrected value for one proposal, and nothing else (AC-F.2).

    `extra="forbid"` for the same reason the apply body forbids extras: a client that
    sent a `kind` or a `source` believes it is choosing one, and it is not - the kind is
    recomputed against the live spec row and the source comes from the row's origin.
    """

    model_config = ConfigDict(extra="forbid")

    value: Any


class FlyerSpecProposalRowIn(BaseModel):
    """A specification the flyer did not print, added to a product it did (AC-G.1).

    The product is named by id because the screen already holds it from the GET, and
    the key by slug because that is what the registry is keyed on. There is no `kind`
    and no `origin` on the wire: the first is computed against the live spec row and the
    second is `manual` by the fact of this route being the one that was called.

    `UUID`, like the apply body's `proposal_ids`: `products.id` is a UUID column, and a
    `str` here handed "nope" straight to the driver for a 500 on a request the caller
    got wrong.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    spec_key: str
    value: Any


class AppliedFlyerSpecOut(BaseModel):
    """One row that is now on the product, named the way the reviewer ticked it."""

    proposal_id: str
    product_code: str
    spec_key: str
    value: Any


class RefusedFlyerSpecOut(BaseModel):
    """One row that was ticked and not written, and why, in words for a person."""

    proposal_id: str
    product_code: str
    spec_key: str
    reason: str
    message: str


class FlyerSpecApplyOut(BaseModel):
    """Every row, applied or refused. No counts: the screen counts what it renders.

    A count beside the list is a second answer that can disagree with the first, and
    the two arrays are the whole answer (AC-C.1).
    """

    applied: list[AppliedFlyerSpecOut] = Field(default_factory=list)
    refused: list[RefusedFlyerSpecOut] = Field(default_factory=list)
