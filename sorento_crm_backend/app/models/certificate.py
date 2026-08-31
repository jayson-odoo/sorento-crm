"""Certificate register models: identity, revisions and product coverage.

A certification PDF stops being an anonymous attachment and becomes a register
row. Three tables, mirroring migration ``311_certificate_register``:

``certificates``          the IDENTITY - scheme + certifying body + number.
``certificate_revisions`` one row per issue, each with its own PDF and window.
``certificate_products``  coverage, source-tagged, attached to the IDENTITY so a
                          renewal touches zero coverage rows.

Two things that look like omissions but are deliberate:

**No validity column.** ``expired`` / ``expiring_soon`` are derived at read time
from the current revision's dates (``certificate_service.derive_validity``). The
``status`` CHECK only admits ``active`` / ``archived``; a stored expiry state
becomes a lie the first day the scheduler does not run.

**No trigram index here.** ``ix_certificates_number_trgm`` is owned by the
migration, like every other ``gin_trgm_ops`` index in this codebase (see
``260_variant_graph_trgm``). Declaring it on the model would make
``Base.metadata.create_all`` - which the test fixtures run - fail outright on any
database without the ``pg_trgm`` extension.
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
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

# Lifecycle values admitted by ck_certificates_status. Validity is NEVER one of
# these - see the module docstring.
CERTIFICATE_STATUS_ACTIVE = "active"
CERTIFICATE_STATUS_ARCHIVED = "archived"
CERTIFICATE_STATUSES = (CERTIFICATE_STATUS_ACTIVE, CERTIFICATE_STATUS_ARCHIVED)

# Provenance of a revision or a coverage row.
CERTIFICATE_SOURCE_AI = "ai"
CERTIFICATE_SOURCE_MANUAL = "manual"
CERTIFICATE_SOURCES = (CERTIFICATE_SOURCE_AI, CERTIFICATE_SOURCE_MANUAL)


class Certificate(Base, CompanyScopedMixin):
    """One certification identity, owned by a company - or by none.

    A certificate FOLLOWS its filed attachment's company (R5,
    PLAN-shared-brand-attachments.md S6): a NULL ``company_id`` is a
    deliberate shared certificate (one document, one expiry alert, both
    companies' twins covered), not a legacy/unstamped row. Every write path
    stamps ``company_id`` explicitly (``CertificateService._new_certificate``
    / the ``bulk-company`` follow hook) rather than leaning on the
    ``before_insert`` auto-stamp, which skips shared models entirely.
    """

    __tablename__ = "certificates"
    __company_shared__ = True
    __audit_track__ = True
    __audit_entity_type__ = "certificate"
    # Identity and lifecycle only. Notification watermarks churn on every
    # reminder run and the revision pointer is bookkeeping, so both stay out of
    # the diff.
    __audit_columns__ = [
        "scheme",
        "certifying_body",
        "certificate_number",
        "issuer",
        "title",
        "status",
        "attachment_type_id",
        "possible_duplicate_of_certificate_id",
    ]

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    attachment_type_id = Column(
        UUID(as_uuid=False),
        ForeignKey("attachment_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    scheme = Column(String(60), nullable=False)
    certifying_body = Column(String(120), nullable=True)
    certificate_number = Column(String(120), nullable=False)
    issuer = Column(String(200), nullable=True)
    title = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, server_default="active", default=CERTIFICATE_STATUS_ACTIVE)
    # Pointer to the revision that is live right now. Cyclic FK with
    # certificate_revisions, so it is added by ALTER after both tables exist -
    # exactly what the migration does.
    current_revision_id = Column(
        UUID(as_uuid=False),
        ForeignKey(
            "certificate_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_certificates_current_revision",
        ),
        nullable=True,
    )
    # Set when a trigram probe found a near-identical number under the same
    # scheme. Advisory only - a near match still creates its own certificate and
    # is never auto-merged.
    possible_duplicate_of_certificate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("certificates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Expiry-reminder batch stamp, mirroring promotions: the reminder email
    # deep-links to ?expiry_notify_batch_id=<id> and the list filters on it.
    expiry_notified_at = Column(DateTime(timezone=False), nullable=True)
    expiry_notify_batch_id = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)

    revisions = relationship(
        "CertificateRevision",
        back_populates="certificate",
        foreign_keys="CertificateRevision.certificate_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CertificateRevision.revision_no",
    )
    # post_update breaks the insert-order cycle: the certificate row is written
    # first, then UPDATEd with the revision it points at.
    current_revision = relationship(
        "CertificateRevision",
        foreign_keys=[current_revision_id],
        post_update=True,
        uselist=False,
    )
    covered_products = relationship(
        "CertificateProduct",
        back_populates="certificate",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    possible_duplicate_of = relationship(
        "Certificate",
        remote_side=[id],
        foreign_keys=[possible_duplicate_of_certificate_id],
    )
    attachment_type = relationship("AttachmentType")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_certificates_status",
        ),
        # Identity: the scheme is part of the key, so PPS/04124FC and
        # SPAN/04124FC stay two rows while "PPS 0119" / "PPS-0119" / "pps0119"
        # collapse to one. company_id is coalesced to a sentinel zero-uuid
        # (never a real company id) so two NULL-company (shared) certificates
        # with the same identity cannot coexist - a plain unique index treats
        # every NULL as distinct, which would let a shared certificate be
        # re-filed indefinitely (PLAN-shared-brand-attachments S6, migration
        # 449). The certificate-sharing logic that writes a NULL company_id -
        # `AttachmentCompanyService._apply_certificate_follow` /
        # `CertificateService._resolve_new_certificate_company_id` - is wired
        # in the same slice this index landed in.
        Index(
            "uq_certificates_company_scheme_number",
            text("coalesce(company_id, '00000000-0000-0000-0000-000000000000')"),
            text("upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g'))"),
            unique=True,
        ),
        # ix_certificates_company_id comes from CompanyScopedMixin's index=True.
        Index("ix_certificates_attachment_type_id", "attachment_type_id"),
        Index("ix_certificates_status", "status"),
        Index("ix_certificates_scheme", "scheme"),
        Index("ix_certificates_expiry_notify_batch_id", "expiry_notify_batch_id"),
    )


class CertificateRevision(Base):
    """One issue of a certificate: its PDF and its validity window.

    Not company-scoped: the table carries no company_id and every read reaches
    it through its certificate, which is scoped.
    """

    __tablename__ = "certificate_revisions"
    __audit_track__ = True
    __audit_entity_type__ = "certificate_revision"
    __audit_columns__ = [
        "certificate_id",
        "revision_no",
        "attachment_id",
        "issued_at",
        "valid_from",
        "valid_until",
        "is_current",
        "needs_review",
        "reviewed_by",
    ]

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    certificate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("certificates.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_no = Column(Integer, nullable=False)
    # Nullable: a manually-filed revision may exist before its PDF, and a
    # trashed attachment SET NULLs here without taking the revision with it.
    attachment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
    )
    issued_at = Column(Date, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_current = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    source = Column(String(10), nullable=False, server_default="ai", default=CERTIFICATE_SOURCE_AI)
    needs_review = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    # List of {code, field?, detail?} objects - machine readable, never prose.
    review_reasons = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    # Raw model output, kept so a wrong date is attributable after the fact.
    extracted_json = Column(JSONB, nullable=True)
    # Every extracted product string that matched no product, verbatim.
    unmatched_products = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    reviewed_at = Column(DateTime(timezone=False), nullable=True)
    reviewed_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)

    certificate = relationship(
        "Certificate",
        back_populates="revisions",
        foreign_keys=[certificate_id],
    )
    attachment = relationship("Attachment", foreign_keys=[attachment_id])

    __table_args__ = (
        CheckConstraint(
            "source IN ('ai', 'manual')",
            name="ck_certificate_revisions_source",
        ),
        Index(
            "uq_certificate_revisions_cert_no",
            "certificate_id",
            "revision_no",
            unique=True,
        ),
        # At most one current revision per certificate; superseded rows are
        # unconstrained.
        Index(
            "uq_certificate_revisions_one_current",
            "certificate_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_certificate_revisions_certificate_id", "certificate_id"),
        Index("ix_certificate_revisions_attachment_id", "attachment_id"),
        Index("ix_certificate_revisions_valid_until", "valid_until"),
        Index("ix_certificate_revisions_needs_review", "needs_review"),
    )


class CertificateProduct(Base):
    """Coverage: which products this certificate identity covers.

    The only authoring surface for coverage. ``product_attachments`` rows for a
    cert-bearing attachment are a PROJECTION of this table crossed with the
    current revision, written exclusively by ``CertificateService``.
    """

    __tablename__ = "certificate_products"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    certificate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("certificates.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String(10), nullable=False, server_default="ai", default=CERTIFICATE_SOURCE_AI)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)

    certificate = relationship("Certificate", back_populates="covered_products")
    product = relationship("Product")

    __table_args__ = (
        CheckConstraint(
            "source IN ('ai', 'manual')",
            name="ck_certificate_products_source",
        ),
        Index(
            "uq_certificate_products_unique",
            "certificate_id",
            "product_id",
            unique=True,
        ),
        Index("ix_certificate_products_certificate_id", "certificate_id"),
        Index("ix_certificate_products_product_id", "product_id"),
    )
