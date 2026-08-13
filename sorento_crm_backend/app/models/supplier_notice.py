"""What a supplier was told, on which channel, and when.

Core, not `scm`, and a copy rather than a view. A loading plan is planning: it re-runs in place
whenever the container count changes, and one nobody sent can be deleted without consequence. A
notice is the opposite - it left the building, and no later edit to the plan may change what it
says. So the lines are copied, and deleting the plan sets the link to NULL rather than taking
the record with it.
"""
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


class SupplierNotice(Base, CompanyScopedMixin):
    """One notice, on one channel, produced by approving one loading plan.

    One row PER CHANNEL rather than one row with a list of channels: an email that sent and a
    chat that failed are two different facts about two different attempts, and AC-F6 asks the
    screen to state what was sent, to whom, on which channel and when. A single row would have
    to pick one answer.
    """

    __tablename__ = "supplier_notices"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    loading_plan_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.loading_plan.id", ondelete="SET NULL"), nullable=True
    )

    notice_type = Column(String(40), nullable=False, server_default=text("'loading'"))

    channel = Column(String(20), nullable=False, server_default=text("'email'"))
    recipient = Column(String(320), nullable=True)

    #: `skipped` is an outcome, not a failure: a supplier with no address on file still gets a
    #: notice and a document Ms Tee can send by hand (AC-F3).
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    status_reason = Column(String(255), nullable=True)
    sent_at = Column(DateTime(timezone=False), nullable=True)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"))
    last_error = Column(Text, nullable=True)

    document_filename = Column(String(255), nullable=True)
    storage_provider = Column(String(16), nullable=True)
    storage_key = Column(String(512), nullable=True)

    container_type = Column(String(30), nullable=True)
    container_count = Column(Integer, nullable=True)
    planned_cbm = Column(Numeric, nullable=True)
    line_count = Column(Integer, nullable=False, server_default=text("0"))
    production_line_count = Column(Integer, nullable=False, server_default=text("0"))

    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines = relationship(
        "SupplierNoticeLine",
        back_populates="notice",
        cascade="all, delete-orphan",
        order_by="SupplierNoticeLine.sort_order",
    )

    __table_args__ = (
        CheckConstraint("channel IN ('email', 'chat')", name="ck_supplier_notice_channel"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_supplier_notice_status",
        ),
        Index("ix_supplier_notices_supplier", "supplier_id", "created_at"),
        Index("ix_supplier_notices_plan", "loading_plan_id"),
    )


class SupplierNoticeLine(Base, CompanyScopedMixin):
    """One line of what was asked for, as it read on the day it was asked.

    Item code and product name are copied, not joined. Renaming a product next month must not
    rewrite a document a supplier already has in their inbox.
    """

    __tablename__ = "supplier_notice_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    notice_id = Column(
        UUID(as_uuid=False), ForeignKey("supplier_notices.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    item_code = Column(String(100), nullable=True)
    product_name = Column(String(500), nullable=True)
    po_number = Column(String(100), nullable=True)

    qty = Column(Numeric, nullable=False, server_default=text("0"))
    cbm = Column(Numeric, nullable=True)

    #: `pack` is loadable now; `produce` has to be made first. The document states them
    #: separately because they are two different asks (AC-F2).
    kind = Column(String(20), nullable=False, server_default=text("'pack'"))
    sort_order = Column(Integer, nullable=False, server_default=text("0"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    notice = relationship("SupplierNotice", back_populates="lines")

    __table_args__ = (
        CheckConstraint("kind IN ('pack', 'produce')", name="ck_supplier_notice_line_kind"),
        Index("ix_supplier_notice_lines_notice", "notice_id", "sort_order"),
    )
