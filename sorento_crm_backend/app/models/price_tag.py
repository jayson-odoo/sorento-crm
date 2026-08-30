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
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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
    sort_order = Column(Integer, nullable=False, server_default="0")
    marketing_price_override = Column(Numeric(15, 2), nullable=True)
    marketing_override_reason = Column(Text, nullable=True)
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
