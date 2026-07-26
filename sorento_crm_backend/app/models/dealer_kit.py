"""Dealer Kit module models — the catalogue page builder.

All tables live in a dedicated ``dealer_kit`` Postgres schema
(``__table_args__`` carries ``{"schema": "dealer_kit"}``), mirroring ``scm``.
They die with the module on uninstall; nothing in ``public`` does.

Cross-schema FKs into ``public`` are NORMAL Postgres foreign keys — public is on
the default search path, so those references are unqualified
(``ForeignKey("attachments.id")``). dealer_kit → dealer_kit FKs are
schema-qualified (``ForeignKey("dealer_kit.page.id")``).

All PKs/FKs are ``UUID(as_uuid=False)`` per the uuid-id principle.

The central invariant: a page document stores BINDINGS, never resolved values.
No price and no access decision is ever written into ``page_version.doc`` — that
is what lets one published page serve staff, dealers and consumers with the
price each is allowed to see (AC-G1).
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

SCHEMA = "dealer_kit"


def _uuid_str():
    return str(uuid.uuid4())


def _created_at():
    return Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


def _updated_at():
    return Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Page(Base, CompanyScopedMixin):
    """One publishable catalogue page.

    The page row holds identity and print settings only. Its CONTENT lives in
    ``PageVersion`` rows, and which of those is live is decided by a
    ``PageLabel`` — so the page itself is never rewritten when someone publishes.
    """

    __tablename__ = "page"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_dealer_kit_page_company_slug"),
        Index("ix_dealer_kit_page_company_id", "company_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=False)
    # Public address segment. Unique per company, not globally: Sorento and Mocha
    # may each publish a "2026-bathroom".
    slug = Column(String(200), nullable=False)
    print_profile = Column(JSONB, nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()

    versions = relationship(
        "PageVersion",
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="desc(PageVersion.version)",
    )
    labels = relationship(
        "PageLabel", back_populates="page", cascade="all, delete-orphan"
    )


class PageVersion(Base):
    """An immutable snapshot of a page's document.

    Never updated in place. Saving always writes ``max(version) + 1`` for that
    page, which is what makes rollback free: the older document is still there.

    Not company-scoped itself — it is reachable only through its page, and the
    page carries the partition.
    """

    __tablename__ = "page_version"
    __table_args__ = (
        UniqueConstraint("page_id", "version", name="uq_dealer_kit_page_version"),
        Index("ix_dealer_kit_page_version_page_id", "page_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    doc = Column(JSONB, nullable=False)
    commit_message = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()

    page = relationship("Page", back_populates="versions")


class PageLabel(Base):
    """A movable pointer at one version — ``published`` or ``staging``.

    Going live moves a label; it never edits a version. Rollback is the same
    operation aimed at an older version, which is why it costs nothing.
    """

    __tablename__ = "page_label"
    __table_args__ = (
        UniqueConstraint("page_id", "label", name="uq_dealer_kit_page_label"),
        Index("ix_dealer_kit_page_label_page_id", "page_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(String(20), nullable=False)
    version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    updated_by = Column(UUID(as_uuid=False), nullable=True)
    updated_at = _updated_at()

    page = relationship("Page", back_populates="labels")
    version = relationship("PageVersion")


class TileTemplate(Base, CompanyScopedMixin):
    """The design of a single product's card, authored once and reused."""

    __tablename__ = "tile_template"
    __table_args__ = (
        Index("ix_dealer_kit_tile_template_company_id", "company_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=False)
    doc = Column(JSONB, nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()


class Asset(Base, CompanyScopedMixin):
    """A reusable piece of artwork: logo, icon, badge, decorative element.

    The BYTES stay in ``public.attachments`` and go through the storage router
    like every other file. This table adds only the library semantics — name,
    kind, tags — so the Kit does not grow a second file store.

    A page document references the asset ID, never a filename, so renaming the
    underlying file cannot break a published page (AC-D3).
    """

    __tablename__ = "asset"
    __table_args__ = (
        Index("ix_dealer_kit_asset_company_id", "company_id"),
        Index("ix_dealer_kit_asset_kind", "kind"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    attachment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False, server_default="decorative")
    tags = Column(ARRAY(String), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()


class Collection(Base, CompanyScopedMixin):
    """A curated, ordered set of products: rule ∪ pins − exclusions.

    ``scope='page'`` is the ad-hoc set someone picked inside one editor session;
    it is invisible in the library and dies with its page. ``scope='library'`` is
    named and reusable, and a page-scoped one can be promoted into it.
    """

    __tablename__ = "collection"
    __table_args__ = (
        Index("ix_dealer_kit_collection_company_id", "company_id"),
        Index("ix_dealer_kit_collection_page_id", "page_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    scope = Column(String(20), nullable=False, server_default="page")
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
        nullable=True,
    )
    name = Column(String(200), nullable=True)
    # Evaluated by the EXISTING app/rule_engine (same evaluator as promo-expiry),
    # not a second filter implementation.
    conditions_json = Column(JSONB, nullable=True)
    pinned_product_ids = Column(ARRAY(UUID(as_uuid=False)), nullable=True)
    excluded_product_ids = Column(ARRAY(UUID(as_uuid=False)), nullable=True)
    manual_order = Column(ARRAY(UUID(as_uuid=False)), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()


class Bundle(Base, CompanyScopedMixin):
    """A named set of products sold together at its own price.

    A Bundle is NOT a product: it is never stocked, never costed, and never sent
    to accounting. What gets ordered is always its components — the Bundle is the
    price and the name they are shown under. Its availability is derived from its
    components at read time and is deliberately not stored, so it can never claim
    to be orderable while a component is discontinued (AC-F10).
    """

    __tablename__ = "bundle"
    __table_args__ = (
        Index("ix_dealer_kit_bundle_company_id", "company_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=False)
    price = Column(Numeric(15, 4), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()

    components = relationship(
        "BundleComponent",
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="BundleComponent.sort_order",
    )


class BundleComponent(Base):
    """One real SKU inside a Bundle. These are what reach an order."""

    __tablename__ = "bundle_component"
    __table_args__ = (
        UniqueConstraint(
            "bundle_id", "product_id", name="uq_dealer_kit_bundle_component"
        ),
        Index("ix_dealer_kit_bundle_component_bundle_id", "bundle_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    bundle_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.bundle.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = Column(Numeric(15, 4), nullable=False, server_default="1")
    sort_order = Column(Integer, nullable=False, server_default="0")

    bundle = relationship("Bundle", back_populates="components")
