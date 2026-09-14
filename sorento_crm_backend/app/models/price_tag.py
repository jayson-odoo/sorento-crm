"""Price tag request models.

A portal contact (Sorento salesperson) submits a request naming products, sets,
pricing mode and a dealer. Marketing designs the tags in the canvas editor and
the salesperson reviews the proof on the portal. See PLAN-price-tag-request.md.

``PriceTagRequest`` is company-scoped (``CompanyScopedMixin``).
``PriceTagRequestLine`` is not scoped itself - it hangs off the request.

``ContactPortalFormOverride`` lives here rather than in ``access.py`` because
it is portal-form infrastructure introduced by this feature; the access module
is already large and the override has no coupling to it beyond the FK.
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

DEALER_KIT_SCHEMA = "dealer_kit"


def _uuid_str():
    return str(uuid.uuid4())


class ContactPortalFormOverride(Base):
    """Per-contact toggle for portal form type visibility.

    ``is_enabled`` wins over the access-type-level ``portal_form_types`` default.
    A row here saying ``is_enabled=False`` hides the type even if every access
    type the contact holds includes it; ``is_enabled=True`` shows it even if none
    of them do.
    """

    __tablename__ = "contact_portal_form_overrides"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    form_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, nullable=False)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("contact_id", "form_type", name="uq_contact_portal_form_override"),
        Index("ix_contact_portal_form_overrides_contact_id", "contact_id"),
    )


class PriceTagRequest(Base, CompanyScopedMixin):
    """A salesperson's request for printed price tags.

    Lifecycle: new -> designing -> proof_ready -> approved -> ready
    Plus: changes_requested (loops back to designing), rejected, void.
    """

    __tablename__ = "price_tag_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id"),
        nullable=False,
    )
    debtor_code = Column(String(100), nullable=True)
    # Nullable since D48a: Save Draft validates nothing, so a half-typed request
    # has to be storable. Completeness is enforced on SUBMIT, in the service, where
    # the refusal can name the field that is missing.
    debtor_name = Column(String(255), nullable=True)
    promotion_id = Column(
        UUID(as_uuid=False),
        ForeignKey("promotions.id", ondelete="SET NULL"),
        nullable=True,
    )
    needed_by_date = Column(Date, nullable=True)  # nullable since D48a, see debtor_name
    notes = Column(Text, nullable=True)
    # Header-level price mode (D5, r7): 'list' | 'selling'. Replaces the old
    # per-line `show_promo_price` switch as the thing the salesperson picks;
    # every line's `show_promo_price` is re-derived from this on save.
    price_mode = Column(String(16), nullable=False, server_default="list")
    status = Column(String(30), nullable=False, server_default="new")
    doc_number = Column(String(30), nullable=False, unique=True)
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{DEALER_KIT_SCHEMA}.page.id", ondelete="SET NULL"),
        nullable=True,
    )
    portal_draft_at = Column(DateTime(timezone=False), nullable=True)
    po_extraction_result = Column(JSONB, nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    # WHO is designing this. Claiming used to write the user into ``created_by``,
    # which says who made the row and which nothing read back, so the page said
    # "Unclaimed" for the rest of the request's life. String, not UUID, because
    # ``users.id`` is TEXT - which is also why ``created_by`` has no FK and this
    # one does.
    assigned_to_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Portal submission revisions (R3-1, migration ptag_0006_revisions), denormalized
    # the same way StockInquiry / PurchaseRequestHeader carry their own pair.
    revision_no = Column(Integer, nullable=False, server_default="0", default=0)
    last_revised_at = Column(DateTime(timezone=False), nullable=True)
    # Who prints (r9 D7): 'office' | 'self'. NULL on every row created before
    # the choice existed, and required at submit from r9 onward - the answer
    # decides whether the request ends at `approved` or waits for a collection.
    print_by = Column(String(8), nullable=True)
    # The office hand-over (r9 D9). `collected_by_user_id` is the staffer who
    # ticked it off, `collected_by_contact_id` the salesperson who confirmed on
    # the portal; `collected_auto` is the sweep, which is neither.
    ready_for_collection_at = Column(DateTime(timezone=False), nullable=True)
    collected_at = Column(DateTime(timezone=False), nullable=True)
    collected_by_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    collected_by_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True
    )
    collected_auto = Column(Boolean, nullable=False, server_default="false")
    # How many proofs this design has been sent for review (r9 D4). COUNTED,
    # not derived: the "Marked proof ready" snapshot it used to be read from is
    # skipped whenever the designer saved first, so every round came back as 1.
    # 0 means it has never been sent - the first proof_ready makes it 1.
    review_round = Column(Integer, nullable=False, server_default="0", default=0)

    lines = relationship(
        "PriceTagRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PriceTagRequestLine.sort_order",
    )

    __table_args__ = (
        Index("ix_price_tag_requests_status", "status"),
        Index("ix_price_tag_requests_contact_id", "contact_id"),
        Index("ix_price_tag_requests_promotion_id", "promotion_id"),
        Index("ix_price_tag_requests_assigned_to_id", "assigned_to_id"),
        # company_id index is already created by CompanyScopedMixin (index=True).
    )


class PriceTagRequestLine(Base):
    """One product or product set on a price tag request.

    Not company-scoped: reachable only through its request, which carries the
    partition.
    """

    __tablename__ = "price_tag_request_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("price_tag_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_type = Column(String(20), nullable=False)
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # No FK to product_sets yet - table not merged from feat/product-sets.
    product_set_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_sets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    show_promo_price = Column(Boolean, nullable=False, server_default="true")
    quantity = Column(Integer, nullable=False, server_default="1")
    alternatives = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    included_accessories = Column(Text, nullable=True)
    # Free-text note on the line (D6, r7).
    remarks = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    marketing_price_override = Column(Numeric(15, 2), nullable=True)
    marketing_override_reason = Column(Text, nullable=True)
    # The product data gate (r9 D16). `pinned_tag_data` is the `LineTagData`
    # the resolver answered when designing started - what the tag is DRAWN
    # from, so a price edited in master data afterwards cannot rewrite a proof
    # that has already been approved. `data_change_ack_hash` is the live hash
    # somebody looked at and chose to keep, so the same change stops asking.
    pinned_tag_data = Column(JSONB, nullable=True)
    pinned_at = Column(DateTime(timezone=False), nullable=True)
    data_change_ack_hash = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    request = relationship("PriceTagRequest", back_populates="lines")

    __table_args__ = (
        CheckConstraint(
            "(line_type = 'product' AND product_id IS NOT NULL AND product_set_id IS NULL) "
            "OR (line_type = 'product_set' AND product_set_id IS NOT NULL AND product_id IS NULL)",
            name="ck_price_tag_request_lines_one_ref",
        ),
        UniqueConstraint("request_id", "product_id", name="uq_ptag_line_request_product"),
        UniqueConstraint("request_id", "product_set_id", name="uq_ptag_line_request_set"),
        Index("ix_price_tag_request_lines_request_id", "request_id"),
    )


class PriceTagReviewComment(Base, CompanyScopedMixin):
    """One pinned change request on a design (r9 D4).

    A salesperson does not describe a change, they point at it: the anchor is
    stored as FRACTIONS of the TAG's own box (0..1), never page millimetres, so
    re-arranging the sheet, paging or zooming cannot move a comment off the
    thing it was pointing at. A general comment carries no anchor at all and
    reads as being about the whole design.

    ``round`` is the number of ``Marked proof ready`` snapshots the design had
    when the comment was SENT, and it is stored rather than derived: a later
    proof must not renumber a round somebody has already worked off.
    """

    __tablename__ = "price_tag_review_comments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("price_tag_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL = a general comment about the whole design, not about one tag.
    line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
        nullable=True,
    )
    round = Column(Integer, nullable=False, server_default="1")
    # Fractions of the tag box. w/h are 0 for a point pin, > 0 for a box.
    x = Column(Numeric(6, 4), nullable=True)
    y = Column(Numeric(6, 4), nullable=True)
    w = Column(Numeric(6, 4), nullable=True)
    h = Column(Numeric(6, 4), nullable=True)
    body = Column(Text, nullable=False)
    # Exactly one of the two is set: the salesperson who sent it, or the
    # staffer whose rejection note was persisted as a general comment (D14).
    author_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True
    )
    author_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_ptag_review_comments_request_id", "request_id"),
        Index("ix_ptag_review_comments_line_id", "line_id"),
    )
