"""Chatbot stock ask v2 S5 (PLAN-chatbot-stock-ask-v2-24sep.md, R9): one row per stock
ask the chatbot answered for an "Availability only" contact.

The office works a row on the customer's Asks tab and the customer's sales agent works the
same row on the portal's Customer asks page: `state` and `note` are the only fields either
side edits. `notified_agent` / `notify_skip_reason` say whether the S4 salesman message went
out, and why not when it did not.

`customer_id` is nullable on purpose (R8 "record the ask"): a contact with no resolvable
customer still gets its row, with reason `no_customer`, and that row hangs on no customer tab
and no portal page. No `sales_agent_id` snapshot: the portal scope reads the customer's
CURRENT agent (R9).
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text

from app.database import Base
from app.models.base import CompanyScopedMixin

STOCK_ASK_BRANCHES = ("too_big", "in_stock", "incoming", "no_incoming")
STOCK_ASK_STATES = ("open", "done")
#: `console`: written by a chat console hand test (owner ruling 28 Sep 2026), not a dealer.
STOCK_ASK_SOURCES = ("live", "console")


class StockAsk(Base, CompanyScopedMixin):
    __tablename__ = "stock_asks"
    __table_args__ = (
        CheckConstraint(
            "branch IN ('too_big', 'in_stock', 'incoming', 'no_incoming')",
            name="ck_stock_asks_branch",
        ),
        CheckConstraint("state IN ('open', 'done')", name="ck_stock_asks_state"),
        CheckConstraint("source IN ('live', 'console')", name="ck_stock_asks_source"),
        Index("ix_stock_asks_customer_created", "customer_id", text("created_at DESC")),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_code = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    branch = Column(String(20), nullable=False)
    answer_summary = Column(Text, nullable=False)
    notified_agent = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    notify_skip_reason = Column(String(80), nullable=True)
    state = Column(String(10), nullable=False, default="open", server_default=text("'open'"))
    note = Column(Text, nullable=True)
    source = Column(String(10), nullable=False, default="live", server_default=text("'live'"))
    #: Set in one place (`stock_ask_service._apply_update`): when `state` last became done, and
    #: who did it (a CRM user, a portal contact, or both when the contact is also a user).
    #: Ids, never a name; `serialize` resolves the label.
    done_at = Column(DateTime(timezone=False), nullable=True)
    done_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    done_by_contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
