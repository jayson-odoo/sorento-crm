"""Pydantic schemas for price tag requests and tag templates."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Price tag request line schemas
# ---------------------------------------------------------------------------


class PriceTagRequestLineCreate(BaseModel):
    line_type: str = Field(..., pattern=r"^(product|product_set)$")
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    show_promo_price: bool = True
    quantity: int = Field(default=1, ge=1)
    alternatives: list[dict] = Field(default_factory=list)
    included_accessories: Optional[str] = None
    # None, not 0: the portal posts the table in order and sends no sort_order,
    # and a default of 0 gave EVERY line the same one, so the relationship's
    # `order_by(sort_order)` returned them in whatever order Postgres liked. The
    # row a refusal names (`line:<index>`) has to be the row the salesperson sees.
    sort_order: Optional[int] = None


class PriceTagRequestLineUpdate(BaseModel):
    marketing_price_override: Optional[Decimal] = None
    marketing_override_reason: Optional[str] = None


class PriceTagRequestLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str
    line_type: str
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    show_promo_price: bool
    quantity: int
    alternatives: list[Any] = []
    included_accessories: Optional[str] = None
    sort_order: int
    # float, not Decimal, on every money field a CLIENT reads. Pydantic
    # serialises a Decimal as a JSON string, and the detail page does
    # `marketing_price_override.toFixed(2)` - which on a string is not a
    # function, so the page threw the moment a line carried an override.
    # ``ResolvedLineData`` already answers in float; these now agree with it.
    marketing_price_override: Optional[float] = None
    marketing_override_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Resolved, not stored. A line row holds a product id and nothing a person
    # can read, so the CRM detail page draws these four - and it drew four
    # blanks until they were declared here, because ``response_model`` removes
    # an undeclared field without a word. Filled by the detail route from
    # ``tag_data_service``; the DOCUMENT still stores no figures (ADR 0008).
    code: str = ""
    name: str = ""
    list_price: Optional[float] = None
    sell_price: Optional[float] = None


# ---------------------------------------------------------------------------
# Price tag request schemas
# ---------------------------------------------------------------------------


class PriceTagRequestCreate(BaseModel):
    """What the portal posts when it saves a draft (D48a).

    Nothing is required. A draft is a form in progress, and the salesperson types
    it over several sittings; SUBMIT is where completeness is enforced, by
    ``PriceTagRequestService.validate_submittable``, which can name what is
    missing. Both nullable fields match columns that are nullable for the same
    reason.
    """

    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    promotion_id: Optional[str] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    lines: list[PriceTagRequestLineCreate] = Field(default_factory=list)


class PriceTagRequestUpdate(BaseModel):
    """A draft edit. ``lines`` omitted leaves the lines alone; ``lines`` given
    replaces them, which is what the form does when it re-saves a draft."""

    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    promotion_id: Optional[str] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    lines: Optional[list[PriceTagRequestLineCreate]] = None


class PriceTagRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_id: str
    company_id: Optional[str] = None
    debtor_code: Optional[str] = None
    # Optional since D48a: a draft may carry neither, and a non-optional field
    # refuses to serialise a None even though the schema declared it.
    debtor_name: Optional[str] = None
    promotion_id: Optional[str] = None
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    status: str
    doc_number: str
    page_id: Optional[str] = None
    portal_draft_at: Optional[datetime] = None
    created_by: Optional[str] = None
    # WHO is designing it. ``created_by`` is the creator and stays that; this is
    # what the header's "Assigned to" reads, and it read "Unclaimed" forever
    # because neither the column nor the name existed on the wire.
    assigned_to_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: list[PriceTagRequestLineResponse] = []

    # Resolved, not stored. Filled by
    # ``PriceTagRequestService.response_with_resolved_lines``; a request holds a
    # contact id, a user id and a promotion id, and every one of those is a UUID
    # the screen may not show. Declared here because ``response_model`` removes
    # what it does not know about without a word.
    assigned_to_name: Optional[str] = None
    contact_name: Optional[str] = None
    promotion_name: Optional[str] = None
    line_count: int = 0


class PriceTagRequestListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_id: str
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    status: str
    doc_number: str
    needed_by_date: Optional[date] = None
    notes: Optional[str] = None
    promotion_id: Optional[str] = None
    created_at: datetime
    # The four things the queue actually draws in its columns, and the four it
    # drew blank: the request row holds ids, and a listing may not show a UUID.
    # Resolved for the whole page in two set-based queries, never per row.
    assigned_to_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    contact_name: Optional[str] = None
    promotion_name: Optional[str] = None
    line_count: int = 0
    # A request that was saved and never submitted still carries status "new",
    # so this is the only thing that tells a draft from a submitted request. The
    # portal landing's Draft filter reads it (D45); without it every draft would
    # list as New, and a schema drops what it does not declare just as silently
    # as a response_model does.
    portal_draft_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Status transition
# ---------------------------------------------------------------------------


class TransitionPayload(BaseModel):
    status: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Tag template document (the layer model, in Python)
#
# The document itself is JSONB and the API takes it as a plain ``dict``, on
# purpose: the editor owns the shape and a template saved by an older build has
# to keep opening. What needs a schema is the SEED - eight documents nobody
# typed into the editor, written by hand from a PDF, whose only reader is a
# renderer that draws nothing at all for a layer kind it does not recognise. A
# mistyped ``price_badge`` would ship as a tag with no price on it and look like
# a pricing bug.
#
# Mirrors `lib/dealer-kit/tag-template-types.ts`. ``extra='forbid'`` throughout,
# because the error worth catching is a key spelled ``asset_id`` where the
# renderer reads ``assetId`` - which a permissive model accepts in silence.
# ---------------------------------------------------------------------------


SLOT_BINDINGS = (
    "product_image",
    "code",
    "name",
    "dimensions",
    "spec_lines",
    "included_accessories",
    "list_price",
    "sell_price",
    "badges",
    "alternatives",
    "accessories",
    "set_members",
)


class _StrictProps(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageSourceAsset(_StrictProps):
    type: Literal["asset"]
    assetId: str


class ImageSourceAttachment(_StrictProps):
    type: Literal["product_attachment"]
    attachmentId: str


class CropRect(_StrictProps):
    x: float
    y: float
    width: float
    height: float


class ImageLayerPropsDoc(_StrictProps):
    kind: Literal["image"]
    source: Optional[Union[ImageSourceAsset, ImageSourceAttachment]] = None
    fit: Literal["cover", "contain"] = "contain"
    cropRect: Optional[CropRect] = None
    maskShape: Optional[Literal["none", "circle"]] = "none"


class TextLayerPropsDoc(_StrictProps):
    kind: Literal["text"]
    text: str
    fontFamily: str
    fontSize: float
    fontWeight: int
    color: str
    align: Literal["left", "center", "right"]
    lineHeight: float
    letterSpacing: float


class ShapeLayerPropsDoc(_StrictProps):
    kind: Literal["shape"]
    shape: Literal["rect", "rounded_rect", "ellipse", "line"]
    fill: str
    stroke: str
    strokeWidth: float
    cornerRadius: float


class ProductSlotLayerPropsDoc(_StrictProps):
    kind: Literal["product_slot"]
    fieldKey: str


class PriceBadgeLayerPropsDoc(_StrictProps):
    kind: Literal["price_badge"]
    variant: Literal["list_only", "promo"]
    fill: str
    textColor: str
    cornerRadius: float
    showNett: bool


class BadgeLayerPropsDoc(_StrictProps):
    kind: Literal["badge"]
    assetId: str


class GroupBindingDoc(_StrictProps):
    product_id: Optional[str] = None
    product_set_id: Optional[str] = None


class GroupLayerPropsDoc(_StrictProps):
    kind: Literal["group"]
    children: list[str]
    binding: Optional[GroupBindingDoc] = None


TagLayerPropsDoc = Annotated[
    Union[
        ImageLayerPropsDoc,
        TextLayerPropsDoc,
        ShapeLayerPropsDoc,
        ProductSlotLayerPropsDoc,
        PriceBadgeLayerPropsDoc,
        BadgeLayerPropsDoc,
        GroupLayerPropsDoc,
    ],
    Field(discriminator="kind"),
]


class TagLayerDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal[
        "image", "text", "shape", "product_slot", "price_badge",
        "badge", "group",
    ]
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotation_deg: float = 0
    z_index: int
    locked: bool = False
    visible: bool = True
    slot_binding: Optional[Literal[SLOT_BINDINGS]] = None  # type: ignore[valid-type]
    text_override: Optional[str] = None
    props: TagLayerPropsDoc

    @model_validator(mode="after")
    def _type_agrees_with_props(self) -> "TagLayerDoc":
        """``type`` and ``props.kind`` are the same fact written twice.

        The renderers switch on ``props.kind`` and the inspector switches on
        ``type``; a layer where the two disagree draws as one thing and edits as
        another, which is not a state any code downstream checks for.
        """
        if self.type != self.props.kind:
            raise ValueError(
                f"layer type '{self.type}' does not match props kind '{self.props.kind}'"
            )
        return self


class TagTemplateDocModel(BaseModel):
    """The whole document, with every internal reference checked."""

    model_config = ConfigDict(extra="forbid")

    layers: list[TagLayerDoc]
    width_mm: float
    height_mm: float

    @model_validator(mode="after")
    def _references_resolve(self) -> "TagTemplateDocModel":
        ids = [layer.id for layer in self.layers]
        duplicates = {value for value in ids if ids.count(value) > 1}
        if duplicates:
            raise ValueError(f"duplicate layer ids: {sorted(duplicates)}")

        known = set(ids)
        for layer in self.layers:
            if isinstance(layer.props, GroupLayerPropsDoc):
                missing = [child for child in layer.props.children if child not in known]
                if missing:
                    raise ValueError(
                        f"group '{layer.id}' names layers that are not in the document: {missing}"
                    )
        return self


# ---------------------------------------------------------------------------
# Tag template schemas
# ---------------------------------------------------------------------------


class TagTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    family: str = Field(..., min_length=1, max_length=50)
    doc: dict = Field(default_factory=dict)
    print_size: dict = Field(default_factory=dict)


class TagTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    family: Optional[str] = Field(default=None, max_length=50)
    doc: Optional[dict] = None
    print_size: Optional[dict] = None


class TagTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    family: str
    doc: dict
    print_size: dict
    company_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Tag sheet design doc
# ---------------------------------------------------------------------------


class TagSheetDocPayload(BaseModel):
    """Payload for saving a tag sheet design version."""
    doc: dict
    commit_message: Optional[str] = None


class TagSheetDocResponse(BaseModel):
    """Response for getting/saving a tag sheet design."""
    page_id: str
    version: int
    doc: Optional[dict] = None


# ---------------------------------------------------------------------------
# Portal form visibility
# ---------------------------------------------------------------------------


class PortalFormVisibilityResponse(BaseModel):
    visible_types: list[str]


# ---------------------------------------------------------------------------
# Debtor lookup
# ---------------------------------------------------------------------------


class DebtorForAgentItem(BaseModel):
    customer_id: Optional[str] = None
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    source: str


# ---------------------------------------------------------------------------
# Tag sheet export
# ---------------------------------------------------------------------------


class TagSheetExportIn(BaseModel):
    """Body for POST /price-tag-requests/{id}/export."""
    sheet_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional filter: only render these sheet ids. None = all sheets.",
    )


class TagSheetExportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_id: str = Field(serialization_alias="downloadId")
    status: str
    filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Tag data for the canvas editor (S3b)
#
# Money crosses this boundary as `float`, not `Decimal`. The arithmetic is done
# in Decimal inside the pricing engine and never here; what a browser needs is a
# number it can format, and Pydantic serialises a Decimal as a JSON string,
# which the canvas would then have to parse back. Formatting happens at the
# edge, once - see the note at the top of `services/dealer_kit/pricing.py`.
# ---------------------------------------------------------------------------


class ProductSearchItem(BaseModel):
    """One row of the editor's product picker. Deliberately three fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    product_code: str
    product_name: str


class ProductSetSearchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    set_code: str
    name: str


class TagItemLookupItem(BaseModel):
    """One row of the portal lines table's single Item picker (D47).

    `kind` is what turns into the line's `line_type`, and `id` into whichever of
    `product_id` / `product_set_id` matches it. Both are the real row id: the
    column is a foreign key, and a code there is refused by Postgres.
    """

    kind: Literal["product", "product_set"]
    id: str
    code: str
    name: str


class PromotionLookupItem(BaseModel):
    """One row of the portal promotion dropdown (S4, #477).

    ``name`` is ``promotions.description`` - the column the rest of the price
    tag request already reads it off (``PriceTagRequestSummary.promotion_name``,
    ``resolved_labels``), so the portal and the CRM never disagree about what a
    promotion is called.
    """

    id: str
    name: str


class TagImage(BaseModel):
    """One photo of a bound product, signed for the viewer that asked."""

    attachment_id: str
    url: str
    is_primary: bool


class SpecValue(BaseModel):
    """One reviewed spec of a product, as `{{spec.<key>}}` draws it (D58)."""

    key: str
    label: str
    value: str
    unit: Optional[str] = None


class SpecKeyItem(BaseModel):
    """One key the merge-field catalogue offers under Specs."""

    key: str
    label: str
    unit: Optional[str] = None


class ProductTagData(BaseModel):
    """Everything a product block draws. Resolved per request, never stored."""

    id: str
    code: str
    name: str
    dimensions: str
    spec_lines: list[str] = []
    specs: list[SpecValue] = []
    images: list[TagImage] = []
    list_price: Optional[float] = None
    offer_price: Optional[float] = None
    promotion_id: Optional[str] = None


class ProductSetMemberTagData(BaseModel):
    product_id: str
    code: str
    name: str
    dimensions: str
    quantity: float


class ProductSetTagData(BaseModel):
    id: str
    set_code: str
    name: str
    members: list[ProductSetMemberTagData] = []
    list_price: Optional[float] = None
    offer_price: Optional[float] = None
    promotion_id: Optional[str] = None


class ResolvePreviewIn(BaseModel):
    """What the template editor wants priced.

    One of ``product_id`` / ``product_set_id`` is required; the route answers
    422 when neither is named, because a preview of nothing is a mistake rather
    than an empty result.
    """

    product_id: Optional[str] = None
    product_set_id: Optional[str] = None
    promotion_id: Optional[str] = None


class ResolvePreviewOut(BaseModel):
    product: Optional[ProductTagData] = None
    product_set: Optional[ProductSetTagData] = None


class ResolvedLineData(BaseModel):
    """Display data for one request line, for the designer and the print page."""

    line_id: str
    code: str
    name: str
    dimensions: str
    spec_lines: str
    specs: list[SpecValue] = []
    set_members: str = ""
    images: list[TagImage] = []
    list_price: Optional[float] = None
    sell_price: Optional[float] = None
    show_promo_price: bool
    included_accessories: str = ""
    quantity: int


class TagFont(BaseModel):
    """A brand font the editor and the print page load through ``@font-face``."""

    name: str
    family: str
    url: str


class AssetResponse(BaseModel):
    """One row of the Dealer Kit artwork library.

    ``url`` is null when the file cannot be signed - absent rather than broken,
    the same rule the catalogue uses for a background it cannot serve.
    """

    id: str
    name: str
    kind: str
    tags: list[str] = []
    url: Optional[str] = None
    mime_type: Optional[str] = None
