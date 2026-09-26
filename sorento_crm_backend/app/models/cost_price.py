"""Cost price from the supplier's price list: cost lists, change sets, lines (#1288, Lane A).

`PLAN-cost-price-supplier-26sep.md` section 4. Four new tables:

- `ProductSupplierCost` (`product_supplier_costs`): one dated (or "always") price row on a
  product-supplier link. `price_in_force` (`supplier_cost_service.py`) reads a link's rows and
  says which one is live today; `product_suppliers.unit_cost`/`currency` are kept equal to that
  answer by the same writer, never computed by a reader.
- `CostPriceChangeSet` (`cost_price_change_sets`) + `CostPriceChangeLine`
  (`cost_price_change_lines`): one upload (or one supplier submission) and its rows.
- `SupplierPriceLink` (`supplier_price_links`): the public share-link row (Lane B); created
  empty here so Lane B needs no migration of its own.

Deliberately NOT a `source_attachment_id` FK into `attachments`: the retained upload is stored
directly on the change set (`source_file_key`/`source_file_provider`/`source_file_size`/
`file_name`), through the same storage router every other retained import uses
(`app/services/import_source_store.py`'s pattern) - the plan's own attachments FK would work too,
but a second table for a file every set already has its own row for is machinery this slice does
not need.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import deferred
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ProductSupplierCost(Base, CompanyScopedMixin):
    """One cost-list row on a product-supplier link (Q3/Q4 rulings): raw unit price, in the
    supplier's own currency, with an optional validity range. Nothing about shipping, tax,
    terms or incoterm - that is the whole point of AC-CL-02."""

    __tablename__ = "product_supplier_costs"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("product_suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_cost = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # Which upload line made this row (J8, J14). NULL for a hand-added row.
    source_change_line_id = Column(
        UUID(as_uuid=False), ForeignKey("cost_price_change_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("unit_cost >= 0", name="ck_product_supplier_costs_unit_cost_nonneg"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_product_supplier_costs_end_after_start",
        ),
        Index("ix_product_supplier_costs_link_start", "product_supplier_id", "start_date"),
    )


class CostPriceChangeSet(Base, CompanyScopedMixin):
    """One upload (or one supplier submission) for one supplier (J1-J13)."""

    __tablename__ = "cost_price_change_sets"
    __audit_track__ = True
    # `source_file_bytes` left out on purpose: raw bytes are not JSON-serialisable (the
    # audit row's old/new values are JSONB), and a diff of a spreadsheet's contents would
    # be unreadable noise even if it were.
    __audit_columns__ = [
        "code", "supplier_id", "channel", "status", "currency", "start_date", "end_date",
        "file_name", "source_file_size", "created_by_user_id",
        "submitted_by_user_id", "submitted_at", "returned_reason", "returned_by_user_id",
        "returned_at", "applied_by_user_id", "applied_at", "verified",
    ]

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    code = Column(String(30), nullable=False)
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    channel = Column(String(20), nullable=False, server_default=text("'staff_upload'"))
    status = Column(String(24), nullable=False, server_default=text("'draft'"))
    currency = Column(String(3), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # The retained upload (staff_upload / supplier_upload channel; NULL for a table-only
    # supplier_page submission). A price list is small (a real one is a few hundred KB), so
    # the bytes are kept on the row itself rather than through the storage router - the
    # router needs real bucket credentials to round-trip, which a price list this size does
    # not need to pay for (`app/services/import_source_store.py`'s own tests mock the
    # backend for exactly that reason).
    file_name = Column(String(255), nullable=True)
    # `deferred`: a raw spreadsheet's bytes have no business loading on every list/detail
    # read of the set - only `get_source_file`'s own download route ever needs them
    # (S4, security review). `has_source_file`/list serialisation read `source_file_size`
    # instead, which never forces this column to load.
    source_file_bytes = deferred(Column(LargeBinary, nullable=True))
    source_file_size = Column(Integer, nullable=True)
    # File name, sheet names, header row per sheet, merged-cell fills, letterhead text.
    source_meta = Column(JSONB, nullable=True)

    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    submitted_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=False), nullable=True)
    submitted_via_link_id = Column(
        UUID(as_uuid=False), ForeignKey("supplier_price_links.id"), nullable=True
    )
    returned_reason = Column(Text, nullable=True)
    returned_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    returned_at = Column(DateTime(timezone=False), nullable=True)
    applied_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    applied_at = Column(DateTime(timezone=False), nullable=True)
    # NULL until applied; true/false after (AC-S2-17): whether a second person decided it.
    verified = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('staff_upload', 'supplier_page', 'supplier_upload')",
            name="ck_cost_price_change_sets_channel",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_verification', 'applied')",
            name="ck_cost_price_change_sets_status",
        ),
        # One open (draft/pending) set per supplier (AC-S1-14, Q10).
        Index(
            "uq_cost_price_change_sets_open_per_supplier",
            "company_id", "supplier_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'pending_verification')"),
        ),
        Index("ix_cost_price_change_sets_supplier", "supplier_id"),
        Index("ix_cost_price_change_sets_code", "company_id", "code"),
    )


class CostPriceChangeLine(Base):
    """One row of a change set: a supplier code, what it matched, price in force and the
    proposed price (plan section 4.4). Scoped through its `change_set_id`, not its own
    `company_id` - a line has no life outside the set that owns it."""

    __tablename__ = "cost_price_change_lines"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    change_set_id = Column(
        UUID(as_uuid=False), ForeignKey("cost_price_change_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet = Column(String(255), nullable=False)
    row_no = Column(Integer, nullable=False)
    line_no = Column(String(20), nullable=True)

    supplier_code_raw = Column(String(255), nullable=False)
    supplier_code = Column(String(255), nullable=False)
    code_note = Column(String(255), nullable=True)
    configuration = Column(Text, nullable=True)

    #: `configuration_from_merge`, `price_from_merge`, `duplicate_code`.
    flags = Column(ARRAY(String), nullable=False, server_default=text("'{}'"))

    match_outcome = Column(String(20), nullable=False, server_default=text("'unmatched'"))
    match_rung = Column(String(20), nullable=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id"), nullable=True)
    mapped_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    current_unit_cost = Column(Numeric(12, 2), nullable=True)
    current_currency = Column(String(3), nullable=True)
    new_unit_cost = Column(Numeric(12, 2), nullable=True)

    line_state = Column(String(20), nullable=False, server_default=text("'needs_attention'"))
    skipped = Column(Boolean, nullable=False, server_default=text("false"))
    skip_reason = Column(Text, nullable=True)
    new_link_lead_time_days = Column(Integer, nullable=True)

    decision = Column(String(20), nullable=True)
    decision_reason = Column(Text, nullable=True)
    decided_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)

    # Set when an Apply refused this line as stale (AC-S2-06): the live price the link
    # actually carried at that moment, so the review page can show what changed underneath
    # the set instead of just "try again".
    stale_live_unit_cost = Column(Numeric(12, 2), nullable=True)
    stale_live_currency = Column(String(3), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "match_outcome IN ('exact', 'alias', 'ladder', 'manual', 'unmatched')",
            name="ck_cost_price_change_lines_match_outcome",
        ),
        CheckConstraint(
            "line_state IN ('changed', 'unchanged', 'new_link', 'needs_attention', 'skipped')",
            name="ck_cost_price_change_lines_line_state",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('accepted', 'rejected')",
            name="ck_cost_price_change_lines_decision",
        ),
        Index("ix_cost_price_change_lines_set", "change_set_id"),
        Index("ix_cost_price_change_lines_product", "product_id"),
    )


class SupplierPriceLink(Base, CompanyScopedMixin):
    """The public share-link for a supplier's own price page (Lane B). Created empty here
    (no rows, no routes) so Lane B needs no migration of its own."""

    __tablename__ = "supplier_price_links"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), nullable=False)
    recipient_name = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=False), nullable=True)
    revoked_at = Column(DateTime(timezone=False), nullable=True)
    issued_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    revoked_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    last_opened_at = Column(DateTime(timezone=False), nullable=True)
    open_count = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_supplier_price_links_token", "token", unique=True),
        Index("ix_supplier_price_links_supplier", "supplier_id"),
    )
