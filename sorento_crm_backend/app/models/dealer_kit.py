"""Dealer Kit module models - the catalogue page builder.

All tables live in a dedicated ``dealer_kit`` Postgres schema
(``__table_args__`` carries ``{"schema": "dealer_kit"}``), mirroring ``scm``.
They die with the module on uninstall; nothing in ``public`` does.

Cross-schema FKs into ``public`` are NORMAL Postgres foreign keys - public is on
the default search path, so those references are unqualified
(``ForeignKey("attachments.id")``). dealer_kit → dealer_kit FKs are
schema-qualified (``ForeignKey("dealer_kit.page.id")``).

All PKs/FKs are ``UUID(as_uuid=False)`` per the uuid-id principle.

The central invariant: a page document stores BINDINGS, never resolved values.
No price and no access decision is ever written into ``page_version.doc`` - that
is what lets one published page serve staff, dealers and consumers with the
price each is allowed to see (AC-G1).
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
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
    ``PageLabel`` - so the page itself is never rewritten when someone publishes.
    """

    __tablename__ = "page"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_dealer_kit_page_company_slug"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=False)
    # Public address segment. Unique per company, not globally: Sorento and Mocha
    # may each publish a "2026-bathroom".
    slug = Column(String(200), nullable=False)
    # WHICH promotion prices this brochure, when one does (PLAN D5). A Sorento
    # flyer IS a promotion here - `promotions.description` holds the PDF's
    # filename - so the page carries a binding, never a price. Null is normal
    # and means list prices only (D6), which is why it is optional and never
    # inferred.
    #
    # SET NULL, deliberately. CASCADE would let deleting a promotion delete a
    # published catalogue, and RESTRICT would let one brochure block marketing
    # from deleting their own row. Unlinking falls back to list prices, which is
    # the only outcome nobody has to discover from a customer.
    promotion_id = Column(
        UUID(as_uuid=False),
        ForeignKey("promotions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The design every collection block on this page uses unless it says
    # otherwise.
    #
    # It lives on the PAGE and not only on the block because a brochure seeded
    # from the printed flyer is 341 collection blocks, and "choose how a tile
    # looks" is one editorial decision about the document, not 341 identical
    # ones. Before this, the only control was per block, the seed bound a design
    # on none of them, and choosing one therefore appeared to do nothing.
    #
    # A block that sets its own `tileTemplateId` still wins - some rows really
    # are different - so this is a default and not an override.
    #
    # SET NULL for the same reason as the promotion above: deleting a design
    # must not be able to delete a catalogue, and must not be blocked by one.
    # Falling back to the built-in field list is a state the renderer has.
    tile_template_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.tile_template.id", ondelete="SET NULL"),
        nullable=True,
    )
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

    Not company-scoped itself - it is reachable only through its page, and the
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
    """A movable pointer at one version - ``published`` or ``staging``.

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
    like every other file. This table adds only the library semantics - name,
    kind, tags - so the Kit does not grow a second file store.

    A page document references the asset ID, never a filename, so renaming the
    underlying file cannot break a published page (AC-D3).
    """

    __tablename__ = "asset"
    __table_args__ = (
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
    to accounting. What gets ordered is always its components - the Bundle is the
    price and the name they are shown under. Its availability is derived from its
    components at read time and is deliberately not stored, so it can never claim
    to be orderable while a component is discontinued (AC-F10).
    """

    __tablename__ = "bundle"
    __table_args__ = (
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


class ExportRequest(Base):
    """The viewer context a catalogue PDF was requested with.

    ``user_downloads`` is the generic "a file is being made for you" row shared
    by every export in the system and deliberately has no params column. A
    catalogue PDF needs more: it has to be rendered AS SOMEBODY, because a
    dealer's copy and a consumer's copy of the same page carry different prices.

    That decision belongs to the moment the export is REQUESTED. Leaving the
    worker to work it out later is how it ends up falling back to a system
    principal and quietly rendering staff prices into a consumer's document.

    ``page_version_id`` is pinned here too: publishing again while a PDF is
    queued must not change what that PDF contains.

    Not company-scoped itself - it hangs off a page, and the page carries the
    partition.
    """

    __tablename__ = "export_request"
    __table_args__ = (
        UniqueConstraint("download_id", name="uq_dealer_kit_export_request_download"),
        Index("ix_dealer_kit_export_request_page_id", "page_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    download_id = Column(
        UUID(as_uuid=False),
        ForeignKey("user_downloads.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The AUDIENCE, not the requester. Staff exporting a dealer's copy is a
    # normal thing to want.
    audience = Column(String(20), nullable=False, server_default="staff")
    show_invoice_price = Column(Boolean, nullable=False, server_default="false")
    requested_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()

    page = relationship("Page")
    version = relationship("PageVersion")


class FlyerReadingRecord(Base, CompanyScopedMixin):
    """A printed flyer somebody uploaded, as this system READ it (S7.3).

    Named ``...Record`` rather than ``FlyerReading`` on purpose: that name
    already belongs to the extractor's dataclass
    (``app.services.dealer_kit.flyer_extraction.FlyerReading``), and the two are
    handled side by side in one service. Two classes under one name in one file
    is a bug waiting for a hurried import.

    **``reading_json`` holds the READING, never the report.** The report - what
    each printed code matched, what it did not, what the linked promotion does
    not carry - is DERIVED from the reading against the product master and the
    promotion, and it is recomputed on every read. Storing it would freeze an
    answer that is only true for the master it was computed against: create one
    product or change one promotion and a stored report starts telling marketing
    to close gaps somebody already closed. Matching the real flyer's 998 codes
    costs 0.4s, which is far less than the cost of a stale answer nobody can see
    is stale.

    ``sha256`` is the bytes' fingerprint, so "is this the same PDF I uploaded on
    Tuesday" is answerable without keeping the file. The bytes themselves are
    deliberately NOT kept here: what the seed needs is the structure, and the
    original document lives wherever marketing keeps it. It is NULLABLE because
    the library path has no bytes at enqueue time and the job fills it in.

    **The row is created before the flyer is read, not after.** The read takes
    tens of seconds and runs on the worker, so this row is the record of a read
    that was ASKED for: ``processing`` from the moment the POST answers,
    ``done`` or ``failed`` when the job says so. Existing rows read ``done``,
    which is what actually happened to them under the old synchronous route.

    ``reading_json`` on a ``processing`` row is the empty reading, so
    ``page_count`` / ``code_count`` / ``headings`` answer 0 / 0 / [] without a
    special case anywhere that reads them.
    """

    __tablename__ = "flyer_reading"
    __table_args__ = (
        Index("ix_dealer_kit_flyer_reading_company_created", "company_id", "created_at"),
        # ONE read in flight per source, enforced by the database rather than by
        # the service's read-then-insert. Two clicks landing together both find
        # nothing in flight, and without these the loser starts a second 20 to
        # 60 second extraction and stores a second set of banners.
        #
        # UNIQUE only bites where there is something to compare: `sha256` is
        # NULL until a library read's job fills it in, `source_attachment_id` is
        # NULL for every upload, and Postgres treats NULLs as distinct - which
        # is why this is two indexes and not one over both columns.
        Index(
            "ix_dealer_kit_flyer_reading_pending_attachment",
            "company_id",
            "source_attachment_id",
            unique=True,
            postgresql_where=text("status = 'processing'"),
        ),
        Index(
            "ix_dealer_kit_flyer_reading_pending_sha256",
            "company_id",
            "sha256",
            unique=True,
            postgresql_where=text("status = 'processing'"),
        ),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    filename = Column(String(255), nullable=False)
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=True)
    reading_json = Column(JSONB, nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()

    # ``processing`` / ``done`` / ``failed``, pinned by a CHECK in migration 359.
    status = Column(
        String(16), nullable=False, server_default=text("'done'"), default="done"
    )
    # Why it failed, in the words the request used to say. NULL on a row that
    # has not failed.
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    # The library file the read came from; NULL for an upload. No ForeignKey on
    # purpose: a reading is derived working material and must never block or
    # cascade an attachment delete.
    source_attachment_id = Column(UUID(as_uuid=False), nullable=True)
    # The RQ job, for an operator asking where a read went.
    job_id = Column(String(64), nullable=True)


class Selection(Base, CompanyScopedMixin):
    """What somebody chose. The spine the room and the quote hang off.

    Holds product ids and quantities and nothing price-shaped. Prices are
    resolved for whoever is reading, at read time, exactly as tiles are (AC-G1,
    AC-S2). A price written onto a line is a price that goes stale the moment
    the price list moves, and the first anyone hears of it is a customer holding
    a quote nobody can honour.

    The owner is a CRM user OR a contact, never both and never neither, and the
    CHECK below is the reason that stays true. Two owners means two people can
    edit one basket and one of them is wrong; no owner means data nobody can
    reach.
    """

    __tablename__ = "selection"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND contact_id IS NULL) "
            "OR (user_id IS NULL AND contact_id IS NOT NULL)",
            name="ck_dealer_kit_selection_one_owner",
        ),
        Index("ix_dealer_kit_selection_user_id", "user_id"),
        Index("ix_dealer_kit_selection_contact_id", "contact_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(200), nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=True
    )
    # Where they came in from, when they came from a catalogue at all. Null is a
    # designer opened cold, which is a normal way to start.
    source_page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The room, as an ordered list of points in millimetres, plus placements.
    # A polygon and not a bitmap, so it can be reopened and re-edited forever
    # (AC-R2). Area is DERIVED from it and never stored (AC-R5).
    room_json = Column(JSONB, nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()

    lines = relationship(
        "SelectionLine",
        back_populates="selection",
        cascade="all, delete-orphan",
        order_by="SelectionLine.sort_order",
    )


class SelectionLine(Base):
    """One product on a Selection, with a quantity and deliberately no price."""

    __tablename__ = "selection_line"
    __table_args__ = (
        UniqueConstraint(
            "selection_id", "product_id", name="uq_dealer_kit_selection_line"
        ),
        Index("ix_dealer_kit_selection_line_selection_id", "selection_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    selection_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.selection.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT, not CASCADE: deleting a product must not quietly rewrite what
    # somebody chose. A discontinued product stays on the line and is flagged.
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity = Column(Numeric(15, 4), nullable=False, server_default="1")
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = _created_at()

    selection = relationship("Selection", back_populates="lines")


class Edition(Base, CompanyScopedMixin):
    """One named revision cycle over a catalogue page (S2.5).

    An Edition is NOT a second document. The page, its immutable
    ``PageVersion`` rows and the movable ``PageLabel`` already hold the
    catalogue and decide what readers see; an Edition wraps that machinery in
    the question "has a human signed this off", and answers it with the core
    status engine rather than a bespoke enum (AC-L1).

    **``done`` is terminal.** There is no reopen path: revising a live
    catalogue means duplicating this Edition into a new one (AC-L9), which
    starts at ``draft`` while this one keeps the ``published`` label. That is
    what stops the live catalogue disappearing the moment somebody starts a
    revision, without a ``done -> draft`` edge that would let a finished record
    come back to life.

    **Two version ids, not one.** ``approved_version_id`` is what the Approver
    actually read; ``done_version_id`` is what went live. They are usually the
    same and are stored separately anyway, because the deferred price-drift work
    (AC-L4 to AC-L6) has nothing to compare without them - see
    ``PLAN-edition-approval.md``.
    """

    __tablename__ = "edition"
    __table_args__ = (
        # One OPEN Edition per page. Two people revising one catalogue against
        # each other has no story: whichever published second would silently
        # discard the first. Terminal Editions are excluded so a page can be
        # revised again and again - that is AC-L9's whole mechanism - and the
        # predicate names the open states rather than negating `done`, so a
        # status added later has to be classified deliberately.
        Index(
            "uq_dealer_kit_edition_one_open_per_page",
            "page_id",
            unique=True,
            postgresql_where=text(
                "status_key IN ('draft', 'pending_approval', 'approved', 'rejected')"
            ),
        ),
        Index("ix_dealer_kit_edition_company_page", "company_id", "page_id"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    page_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "Spring 2027". The one thing starting an Edition asks for.
    name = Column(String(200), nullable=False)

    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id"), nullable=False
    )
    # A DENORMALISED copy of the status's key, carried so the partial unique
    # index above can be expressed at all: a partial index cannot reach through
    # a foreign key. Written only by the transition service, never by a caller,
    # and asserted equal to the status row in the service's own tests - a drift
    # here would let a second open Edition exist.
    status_key = Column(String(64), nullable=False)

    approved_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    done_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.page_version.id", ondelete="SET NULL"),
        nullable=True,
    )

    # What this Edition was duplicated from, so AC-L9 can badge "new since the
    # last Edition" without guessing. SET NULL rather than CASCADE: deleting an
    # old Edition must not delete the one that succeeded it.
    previous_edition_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.edition.id", ondelete="SET NULL"),
        nullable=True,
    )

    submitted_by = Column(UUID(as_uuid=False), nullable=True)
    submitted_at = Column(DateTime(timezone=False), nullable=True)
    approved_by = Column(UUID(as_uuid=False), nullable=True)
    approved_at = Column(DateTime(timezone=False), nullable=True)
    # Kept on the Edition rather than in an event log because it is what the
    # Designer is shown when they pick the work back up, and a rejection with no
    # reason is a rejection they cannot act on.
    rejection_reason = Column(Text, nullable=True)

    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()

    page = relationship("Page")
