"""The consumer ledger: who bought a thing, and when (Group L).

Its own module, not part of `warranty` and not core (fork 7). Uninstalling the
warranty engine must leave the consumer list and the receipts standing, because
the ledger is the strategic asset and the engine is the thing that reads it. Core
stays exactly one module (`base`), and a direct-selling tenant would never install
consumer data at all.

Six shapes here are decisions rather than transcription, and each is a place the
obvious version is wrong.

**`respond_contact_id` is TEXT, not uuid** (AC-L32). `respond_contacts.id` is a
TEXT column with a uuid-shaped default, and Postgres refuses a foreign key from a
uuid column to a text one. The plan's DDL printed `uuid` and could never have been
created. Third time this trap has been hit in this build.

**The profile carries its OWN normalised phone** (AC-L33). Identity lives on
`respond_contacts`, whose `phone_number` is unique on the RAW string - so
`0166372304` and `+60166372304` already coexist there as two rows, and a profile
keyed only 1:1 on the contact inherits exactly the split AC-L8 exists to prevent.
`phone_e164` is uniquely indexed so the dedupe survives two intake paths running at
once; enforcing it only in Python loses that race silently. It is NULLABLE because
erasure clears it, and many NULLs never collide in Postgres.

**No `marketing_consent` column** (fork 6). Consent is collected for warranty and
service only, so a marketing flag would be a field nobody may lawfully act on - and
a field that exists eventually gets used. Marketing needs fresh consent per person,
captured with wording that says so, not a column.

**`consumer_purchases` is company-scoped and the lines are not.** AC-L29 scopes
only the profile, but `consumer_profile_id` is nullable (fork 2), so an unscoped
ledger holds rows belonging to no company and Mocha's CS can read Sorento's dealer
sell-through. Lines are reachable only through their header, and a second copy of
the same fact can disagree with the first - the same reasoning `warranty_terms`
already uses.

**`consumer_purchases.policy_id` carries NO foreign key.** It snapshots which
policy answered, and a real FK would run from the ledger INTO the warranty module,
inverting fork 7's dependency and making a warranty purge either fail or take the
receipts with it. A dangling policy id on a purchase is readable history; a deleted
purchase is not.

**`consumer_purchase_lines` SNAPSHOTS its Kind** (AC-L36). `kind_code` is NOT NULL
and permanent; `kind_id` is nullable with ON DELETE SET NULL. Cover resolves from
the Kind, so a line that could lose it entirely would become unassessable - and a
NOT NULL `kind_id` would make a warranty purge impossible, because no ON DELETE
action preserves a child row whose column cannot be null. Carrying both keeps the
ledger a historical record of what was bought, whichever modules are installed.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class ConsumerProfile(Base, CompanyScopedMixin):
    """A person the ledger knows about, provisional until they authenticate.

    Company-scoped and audited (AC-L29): personal data changing with no record of
    who changed it is the thing PDPA asks about.
    """

    __tablename__ = "consumer_profiles"
    __audit_track__ = True
    __audit_entity_type__ = "consumer_profile"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # TEXT, matching respond_contacts.id. Nullable because fork 1's majority case is
    # a staff-typed phone that never authenticated and has no contact row yet.
    # UNIQUE because AC-L4 says 1:1 - two profiles on one contact split a person's
    # history in half and nothing detects it.
    respond_contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # The dedupe key (AC-L8). Nullable so erasure can clear it.
    phone_e164 = Column(String(20), nullable=True, unique=True)

    full_name = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    # A consumer may own several properties, each with its own purchases, so this is
    # a list rather than one varchar.
    addresses = Column(JSONB, nullable=True)

    # Fork 6. NOT NULL: a profile whose purpose is unknown is a profile nobody may
    # lawfully use for anything.
    consent_purpose = Column(String(32), nullable=False)
    # PDPA 2010 s.7(2) requires the collection notice in Bahasa Malaysia AND
    # English. "Which wording did this person actually see" is unanswerable without
    # recording the version.
    consent_notice_version = Column(String(32), nullable=True)
    consent_recorded_at = Column(DateTime(timezone=False), nullable=True)

    # AC-L5 / AC-L7. Provisional profiles are excluded from headline counts, so
    # "we have N consumers" is not inflated by staff typing a phone into a message.
    is_provisional = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    confirmed_at = Column(DateTime(timezone=False), nullable=True)

    # AC-L10. The losing side of a merge is RETAINED pointing at the survivor:
    # "where did this consumer go" must be answerable, and split is out of scope so
    # there is no second chance to get it right.
    merged_into_id = Column(
        UUID(as_uuid=False), ForeignKey("consumer_profiles.id", ondelete="SET NULL"), nullable=True
    )
    merged_at = Column(DateTime(timezone=False), nullable=True)
    merged_by = Column(Text, nullable=True)

    # Fork 6's erasure. The row survives so its purchases keep a parent; the person
    # does not.
    anonymised_at = Column(DateTime(timezone=False), nullable=True)
    anonymised_by = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_consumer_profiles_is_provisional", "is_provisional"),
        Index("ix_consumer_profiles_merged_into_id", "merged_into_id"),
    )


class ConsumerProfileReview(Base):
    """A name that arrived on a phone already holding a different one (AC-L9).

    Never auto-merged in either direction: a household shares a handset, so
    `Miss Ong daughter` landing on a phone holding `Ong Mei Ling` is genuinely
    ambiguous and a human call. Without a row the conflict is simply discarded and
    nobody ever decides.

    Not separately company-scoped: it is reachable only through its profile, which
    is scoped.
    """

    __tablename__ = "consumer_profile_reviews"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(
        UUID(as_uuid=False), ForeignKey("consumer_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # What arrived, kept verbatim. The human deciding needs both sides.
    incoming_name = Column(Text, nullable=True)
    incoming_phone_e164 = Column(String(20), nullable=True)
    existing_name = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_consumer_profile_reviews_profile_id", "profile_id"),
        Index("ix_consumer_profile_reviews_resolved_at", "resolved_at"),
    )


class ConsumerPurchase(Base, CompanyScopedMixin):
    """One purchase event: one receipt, whatever it covered (AC-L11, AC-L14).

    The header the ledger dedupes on, and the row cover resolves from. Named
    `consumer_purchases`, never `warranty_registrations`: registration survives only
    as the glossary term for the ACT, which is `registered_at` here. Two tables
    would be two answers to "when was this registered".
    """

    __tablename__ = "consumer_purchases"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Human-quotable, and carrying the PURCHASE's year rather than today's: a 2015
    # receipt entered in 2026 numbered CP2026 reads as a 2026 sale on every report
    # that groups by the number.
    purchase_number = Column(String(40), nullable=False, unique=True)

    # ADVISORY, and therefore nullable (fork 2, AC-L12). Policy clause 6 attaches
    # cover to the product and its purchase date, not to a person, so a
    # staff-reported sale may carry no profile and a house that changed hands does
    # not break the new occupant's claim.
    consumer_profile_id = Column(
        UUID(as_uuid=False), ForeignKey("consumer_profiles.id", ondelete="SET NULL"), nullable=True
    )

    # The Dealer. Routinely unresolved at intake (AC-L20), so nullable.
    customer_id = Column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    # As printed, plus a normalised copy. Both kept: the printed one is evidence, the
    # normalised one is the dedupe key.
    dealer_document_number = Column(Text, nullable=True)
    dealer_document_number_norm = Column(String(120), nullable=True)

    # NOT NULL. It is the only thing cover is computed from; a nullable one makes
    # every verdict on the row `unknown` and nothing says why.
    purchase_date = Column(Date, nullable=False)
    # AC-D12. Where the date came from is a fact about the RECEIPT and belongs here;
    # the assessment snapshots it so correcting this later cannot retro-label a
    # verdict a human already acted on.
    purchase_date_source = Column(
        String(16), nullable=False, default="stated", server_default="stated"
    )

    # AC-L22 / fork 4: as printed at the bottom of the receipt, nothing normalised.
    total_value = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(3), nullable=True)

    # The receipt itself, RETAINED - never discarded after extraction (AC-L14).
    proof_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )

    # AC-D8 / AC-L35. `registered_at` says a registration EXISTS, which is what
    # policy clause 3(b) is about. `registration_source` says whether a human chose
    # to register, which is what clause 26 pays 12 months for. Only the second earns
    # months - see BONUS_EARNING_REGISTRATION_SOURCES in the assessment service.
    registered_at = Column(DateTime(timezone=False), nullable=True)
    registration_source = Column(String(32), nullable=True)

    # AC-L20. An incomplete dedupe key still writes, and is flagged for the CS
    # review list. Flagging everything would be the same as flagging nothing.
    dedupe_pending = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    # Which policy answered, snapshotted. Deliberately NO foreign key: see the
    # module docstring. The ledger must outlive the warranty module.
    policy_id = Column(UUID(as_uuid=False), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        # AC-L17. PARTIAL, and that matters: a plain unique index over three
        # nullable columns constrains nothing in Postgres (NULLs never collide)
        # while LOOKING like this, and the first NOT NULL somebody adds to tidy it
        # up starts rejecting the incomplete rows AC-L20 requires to be written.
        Index(
            "uq_consumer_purchases_dedupe",
            "customer_id",
            "dealer_document_number_norm",
            "purchase_date",
            unique=True,
            postgresql_where=text(
                "customer_id IS NOT NULL AND dealer_document_number_norm IS NOT NULL "
                "AND purchase_date IS NOT NULL"
            ),
        ),
        Index("ix_consumer_purchases_consumer_profile_id", "consumer_profile_id"),
        Index("ix_consumer_purchases_customer_id", "customer_id"),
        Index("ix_consumer_purchases_purchase_date", "purchase_date"),
        Index("ix_consumer_purchases_dedupe_pending", "dedupe_pending"),
        Index("ix_consumer_purchases_proof_attachment_id", "proof_attachment_id"),
    )


class ConsumerPurchaseLine(Base):
    """One product on one receipt (AC-L15).

    `product_id` is nullable and `kind_id` is not, which is the whole ADR-0010
    ordering: `SRTWC8152` matches three real variants and resolves to none of them,
    so cover must be decidable from the Kind alone. A NOT NULL `product_id` makes
    the ordinary receipt unwritable; a nullable `kind_id` makes it unassessable.

    NOT separately company-scoped - reachable only through the header.
    """

    __tablename__ = "consumer_purchase_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    purchase_id = Column(
        UUID(as_uuid=False),
        ForeignKey("consumer_purchases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The exact variant, routinely unresolved (AC-C17).
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    # DEFERRABLE INITIALLY DEFERRED - see the module docstring. The alternative is a
    # warranty purge that cannot run at all.
    # AC-L36. The Kind is carried TWICE, and the split is the point.
    #
    # `kind_code` is what the line WAS, permanently: NOT NULL, and it is what keeps
    # the row assessable and readable after the warranty module is uninstalled. S2's
    # seed upserts Kinds on exactly this stable code, so reinstalling warranty
    # re-links rather than loses.
    #
    # `kind_id` is the live link and is NULLABLE with ON DELETE SET NULL, so purging
    # warranty genuinely leaves the ledger standing (AC-L2) instead of being refused
    # by the constraint. The earlier shape made this NOT NULL, which no ON DELETE
    # action can preserve, and a deferred constraint only moved the failure to
    # COMMIT - green tests over a production purge that could never run.
    kind_code = Column(String(64), nullable=False)
    kind_id = Column(
        UUID(as_uuid=False),
        ForeignKey("warranty_product_kinds.id", ondelete="SET NULL"),
        nullable=True,
    )
    # What the receipt or the consumer actually said, kept verbatim. It is the only
    # evidence when the variant never resolves.
    claimed_text = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=True)
    # Fork 4: USUALLY NULL. A receipt total is never spread across the lines that
    # share it - the document does not say what each item cost, and a number we
    # invented is indistinguishable on screen from one we read.
    line_value = Column(Numeric(14, 2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_consumer_purchase_lines_purchase_id", "purchase_id"),
        Index("ix_consumer_purchase_lines_kind_id", "kind_id"),
        Index("ix_consumer_purchase_lines_product_id", "product_id"),
    )
