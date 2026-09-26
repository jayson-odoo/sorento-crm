"""Mapping between Sorento records and the external documents they came from.

One table instead of `source_system`/`source_ref` columns on nine business
tables. The trade, stated plainly:

  + No DDL on products/orders/order_lines and no backfill across ~110k rows.
  + A tenth consumed entity needs no schema change.
  + "What came from AutoCount?" is one query, not nine.
 - No foreign keys. A polymorphic ``entity_id`` cannot reference nine tables,
    so nothing cascades on delete and integrity is the service layer's job.

Because of that last point, ``IntegrationReferenceService`` validates
``entity_type`` against an allowlist (it reaches a table name and arrives from
an ingest payload) and treats a reference whose target has been deleted as
absent, cleaning it up on discovery.

**Absence means locally created.** There is deliberately no `manual` row for
every pre-existing record: a reference exists only when a record genuinely came
from outside.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
import uuid


class IntegrationReference(Base):
    __tablename__ = "integration_references"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Which business table, and which row in it. Validated against the service's
    # allowlist -- never interpolated from caller input unchecked.
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String, nullable=False)

    # autocount-brands-ingest BL-056 (D11): the anchor company for a reference
    # to a company-scoped entity type; NULL for a shared type (`sales_agents`,
    # `IntegrationReferenceService.SHARED_TABLES`). Nullable because a shared
    # row genuinely has none - not because the anchor is ever optional for a
    # scoped one, which the service enforces itself.
    company_id = Column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )

    # 'autocount' today. Kept explicit so a second upstream can be added without
    # the existing rows becoming ambiguous.
    source_system = Column(String(30), nullable=False, default="autocount")

    # AutoCount's stable surrogate key (DocKey). NOT DocNo: that is mutable --
    # AutoCount exposes a NewDocNo field -- so correlating on it would break the
    # moment a document is renumbered, creating a duplicate instead of an update.
    source_ref = Column(String(255), nullable=False)
    # Human-facing document number, for display only. Expected to change.
    source_doc_no = Column(String(100), nullable=True)

    integration_id = Column(
        UUID(as_uuid=False), ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True
    )

    first_seen_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    last_synced_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # BL-056 (D12): one external document maps to one local record PER
        # COMPANY, not globally - two partial unique indexes, not the single
        # global constraint this replaces. Partial rather than a `NULLS NOT
        # DISTINCT` column so the guarantee holds on every Postgres version
        # this app runs (prod pg17, CI pg16).
        Index(
            "uq_integration_ref_source_company",
            "source_system",
            "entity_type",
            "source_ref",
            "company_id",
            unique=True,
            postgresql_where=text("company_id IS NOT NULL"),
        ),
        Index(
            "uq_integration_ref_source_shared",
            "source_system",
            "entity_type",
            "source_ref",
            unique=True,
            postgresql_where=text("company_id IS NULL"),
        ),
        # ...and one local record has exactly one origin. Two would make
        # "where did this come from?" unanswerable, which per-field ownership
        # rules later depend on.
        UniqueConstraint("entity_type", "entity_id", name="uq_integration_ref_entity"),
        # This table grows with every synced document, so the reverse lookup
        # ("is this record externally owned?") needs its own index rather than
        # relying on a scan.
        Index("ix_integration_references_entity", "entity_type", "entity_id"),
        Index("ix_integration_references_source_ref", "source_ref"),
        Index("ix_integration_references_integration_id", "integration_id"),
        Index("ix_integration_references_last_synced_at", "last_synced_at"),
    )
