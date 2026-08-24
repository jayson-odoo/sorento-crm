"""What the catalogue proposes, before anybody agrees to it.

47 two-piece families exist across Sorento and Mocha and 23 of them have no bare
code at all, so roughly 94 sets would otherwise be typed by hand. The pass reads
the SHAPE of the product codes and derives candidates; a person ticks the ones
that are right, and only that tick reaches `product_sets`.

Nothing runs unattended (UAC D14). The role labels in this feature's own design
came out inverted at the start, and a regex that wrote by itself would have
propagated that across every row before anybody looked.

Deliberately thinner than `ProductSpecFlyerBatch`, which is the shape this
follows. That one wraps an LLM read on an RQ job, so it carries a status, an
error message and a job id; this pass is a synchronous pure derivation over code
shape, so there is no state to report and nothing to poll. Counts are derived on
read rather than stored, so they cannot drift from the rows they count.

UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 7.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CompanyScopedMixin


class ProductSetProposalBatch(Base, CompanyScopedMixin):
    """One pass over one company's catalogue.

    One open batch per company: re-running deletes the previous one and derives
    against the catalogue as it is NOW, rather than accumulating a second list
    nobody asked for. Nothing is lost by that - an applied proposal has already
    become a set, which is the record that matters.
    """

    __tablename__ = "product_set_proposal_batches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    proposals = relationship(
        "ProductSetProposal",
        back_populates="batch",
        cascade="all, delete-orphan",
        # The database cascade is the one that runs. Without this SQLAlchemy
        # loads every proposal just to delete it row by row, which is work the
        # FK already does.
        passive_deletes=True,
        order_by="ProductSetProposal.set_code",
    )


class ProductSetProposal(Base):
    """One candidate set: a code, a name and the members the shape implies.

    `members` holds product IDS and the price tick, never prices or
    descriptions. A stored price snapshot goes stale the moment somebody edits
    the product and becomes a second source of truth for the same number, so
    codes, descriptions and live list prices are hydrated from `products` at
    read time instead.

    Not `CompanyScopedMixin`: a proposal is reachable only through its batch,
    which is scoped, exactly as `ProductSpecFlyerProposal` reaches its scope
    through `ProductSpecFlyerBatch`.
    """

    __tablename__ = "product_set_proposals"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(
        UUID(as_uuid=False),
        ForeignKey("product_set_proposal_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The prefix and number the members share, e.g. `SRTWC8608`. Two candidates
    #: in one family are the same assembly in different trap variants, so the
    #: review screen shows them together and they are judged against each other.
    family_key = Column(String(100), nullable=False)
    #: The code the flyer prints: the anchor's code with its role letter removed.
    set_code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    #: `[{"product_id", "quantity", "contributes_to_price", "sort_order"}]`.
    members = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    batch = relationship("ProductSetProposalBatch", back_populates="proposals")

    __table_args__ = (
        # One candidate per code per pass. Two anchors cannot collapse onto one
        # set code today, but a duplicate would show as two identical cards and
        # apply twice, and the second apply would be a confusing 409.
        UniqueConstraint("batch_id", "set_code", name="uq_product_set_proposal_code"),
        Index("ix_product_set_proposals_batch", "batch_id"),
    )
