"""Stock transfers: the physical move a supply decision implies
(`PLAN-scm-cs-planning-uat.md` section E, captain's Q2 ruling of 25 Aug 2026).

The captain, walking SO415472: "after Approve, stock taken from BRW - or borrowed from
anywhere else - has to physically move to the line's location. Nothing today says so."
This is the row that says so, and "a person needs to deliberately approve the transfer in
the transfer page" is why it has a state at all rather than being a derived read.

**Never demand and never supply.** `scm.committed_v` and `scm.on_order_v` do not know this
table exists: the quantity was already promised by the supply decision, and counting the
move as well would promise it twice. Stock figures change only when the next AutoCount
stock upload lands, which is also why nothing here closes automatically - `moved` means a
person keyed the movement into AutoCount and wrote its document number down, not that our
numbers have caught up.

In the `projects` schema because it is the planning module's own artifact (PRINCIPLES,
"Modular architecture"): uninstall the module and the core stock record is untouched. The
FKs to `sales_order_lines`, `warehouses` and `products` are ordinary cross-schema FKs to
CORE tables - `ForeignKey("sales_order_lines.id")` unqualified is `public.sales_order_lines`,
the CORE line, not `projects.sales_order_lines` (see the header of `app.models.project_so`).
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


#: Proposed by the confirmation that implied it. Nothing has been said to a warehouse yet.
TRANSFER_PROPOSED = "proposed"
#: A person looked at it and said move this. Still nothing has physically moved.
TRANSFER_APPROVED = "approved"
#: Keyed into AutoCount, `autocount_ref` names the document. Terminal here: our stock
#: figures follow on the next upload, and no code closes this row on their behalf.
TRANSFER_MOVED = "moved"
#: Superseded by a later revision, or called off by a person with a reason. Terminal.
TRANSFER_CANCELLED = "cancelled"

TRANSFER_STATES = (
    TRANSFER_PROPOSED,
    TRANSFER_APPROVED,
    TRANSFER_MOVED,
    TRANSFER_CANCELLED,
)

#: The states a supersede or a person may still call off. A `moved` row is history: the
#: stock is already somewhere else and cancelling the paperwork would not bring it back.
TRANSFER_OPEN_STATES = (TRANSFER_PROPOSED, TRANSFER_APPROVED)

#: Which rung of the ladder asked for the move, in the plan's section 2 words rather than
#: the engine's: `group_take` -> own_group, `pool` -> pool, either borrow -> borrow. The
#: warehouse reading the row cares that it is somebody else's stock, not which borrow.
TRANSFER_KIND_OWN_GROUP = "own_group"
TRANSFER_KIND_POOL = "pool"
TRANSFER_KIND_BORROW = "borrow"

TRANSFER_KINDS = (
    TRANSFER_KIND_OWN_GROUP,
    TRANSFER_KIND_POOL,
    TRANSFER_KIND_BORROW,
)


class StockTransfer(Base, CompanyScopedMixin):
    """One movement of one product between two warehouses, for one sales-order line."""

    __tablename__ = "stock_transfers"
    __audit_entity_type__ = "project_stock_transfers"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    #: `TR-000001`. Six digits and a per-company series, the same shape and the same
    #: discipline as `OrderInquiry.inquiry_no` - a warehouse is handed this number and
    #: nothing a person reads may be a UUID.
    transfer_no = Column(String(20), nullable=False)

    #: The CORE sales-order line the move serves. `SET NULL` rather than CASCADE, exactly
    #: as `order_inquiry_rows.so_line_id` is: a re-uploaded book that drops the line must
    #: not delete the record of stock that has already moved for it.
    so_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_sales_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The revision that asked for it. A reconfirm cancels this revision's open rows and
    #: writes fresh ones against the new revision, so the pair (decision, state) is what
    #: says whether a move is still wanted.
    supply_decision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.so_supply_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    from_warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    to_warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    qty = Column(Numeric(15, 4), nullable=False)
    kind = Column(String(16), nullable=False)
    state = Column(String(16), nullable=False, server_default=TRANSFER_PROPOSED)

    proposed_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    approved_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=False), nullable=True)
    moved_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    moved_at = Column(DateTime(timezone=False), nullable=True)
    cancelled_reason = Column(Text, nullable=True)
    #: The transfer document number a person keyed into AutoCount. Free text, because
    #: AutoCount is the ledger of record and is not integrated: this is the thread back to
    #: it, not a foreign key to anything we hold.
    autocount_ref = Column(String(80), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "transfer_no", name="uq_project_stock_transfer_no"),
        Index("ix_project_stock_transfers_order", "project_sales_order_id"),
        Index("ix_project_stock_transfers_decision", "supply_decision_id", "state"),
        Index("ix_project_stock_transfers_line", "so_line_id"),
        Index("ix_project_stock_transfers_state", "state"),
        {"schema": "projects"},
    )


#: `TR-000001`. Six digits, the width `OI-000001` and `PSO-000001` already use, so the
#: three documents a planning screen shows side by side are read the same way.
TRANSFER_NO_PREFIX = "TR-"
TRANSFER_NO_DIGITS = 6


def next_transfer_no(bind, company_id) -> str:
    """The next transfer number for one company: the highest already issued, plus one.

    Copied from `app.models.project_so.next_inquiry_no` deliberately and with its reason:
    HIGHEST plus one, never the count, because a number that has been issued is on a
    warehouse's paperwork and a cancelled transfer must not hand it to a different move.

    `bind` is whatever can execute a statement - the flush's own Connection when this runs
    from the stamp below, a Session when a caller asks directly.
    """
    table = StockTransfer.__table__
    latest = bind.execute(
        select(table.c.transfer_no)
        .where(
            table.c.company_id == company_id,
            table.c.transfer_no.like(f"{TRANSFER_NO_PREFIX}%"),
        )
        .order_by(func.length(table.c.transfer_no).desc(), table.c.transfer_no.desc())
        .limit(1)
    ).scalar()
    tail = (latest or "")[len(TRANSFER_NO_PREFIX):]
    highest = int(tail) if tail.isdigit() else 0
    return f"{TRANSFER_NO_PREFIX}{highest + 1:0{TRANSFER_NO_DIGITS}d}"


@event.listens_for(StockTransfer, "before_insert")
def _stamp_transfer_no(_mapper, connection, target) -> None:
    """Every transfer gets its number, whoever created it.

    A listener rather than a line in the writer, for the reason the inquiry number is one:
    the invariant is "no transfer exists without a number", and a confirmation writing six
    of them in one flush takes six consecutive numbers because the mint reads the flush's
    own connection.
    """
    if getattr(target, "transfer_no", None):
        return
    target.transfer_no = next_transfer_no(connection, target.company_id)
