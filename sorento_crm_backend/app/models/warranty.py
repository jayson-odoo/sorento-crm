"""The four tables the warranty entitlement engine answers from (AC-D1 to AC-D3,
AC-D16).

One module because they are one concept with one lifecycle: a Kind is meaningless
without the rules that reach it, and a Term without the Policy that dates it.
Splitting them across files is how the policy window ends up being read in two
places, which is how two callers start disagreeing about the same purchase.

Four things here are decisions rather than transcription, and each one is a place
the obvious version is wrong:

**`warranty_policies` is COMPANY-SCOPED and nothing else here is** (AC-D16). The
`companies` table holds both Sorento and Mocha, and the two brands publish
DIFFERENT durations for the same product kinds: Mocha's Version 4 gives a Water
Closet's flushing fittings 3 years where Sorento's figures say 5, a seat cover 1
year where they say 2, a stainless steel 304 kitchen sink 10 years where they say
25, and it has no booster pump at all. A policy row that cannot say which company
published it would answer a Sorento customer with Mocha's terms, silently and
plausibly. Resolution is therefore "the policy in force FOR THIS COMPANY on that
date", which the scope listener enforces for free on every SELECT.

Terms are NOT separately scoped: a Term is only ever reachable through its
`policy_id`, so scoping it again would be a second copy of the same fact that can
disagree with the first. Kinds and kind rules are NOT scoped either: "Water
Closet" is one physical thing whichever brand sells it, and a per-company kind
vocabulary would mean maintaining the product mapping twice.

**`covered_defect_type_ids` is `uuid[]`, not `varchar[]`.** It holds
`lookup_options.id` values, and a varchar array holds the same characters while
comparing to a uuid column only through a cast - which is how a defect-scope check
ends up silently matching nothing. Recorded and NOT fixable here: an array column
carries no foreign key, so deleting a defect type quietly narrows the scope of
every term that referenced it (AC-D18).

**`installation_included` is NOT NULL.** It decides who pays for the callout
(policy clause 15). A null would be rendered as "no" by every consumer of it and
nobody would ever notice.

**`effective_from` is NOT NULL and `effective_to` is nullable.** A policy with no
start date cannot be "in force on the purchase date" at all and would silently
never match; the current policy genuinely has no end, and a sentinel like
9999-12-31 puts a magic value in the comparison instead.

Clause 17 (cover restricted to residential installations, commercial and
industrial excluded) is MODELLED here - `policy_text` and `exclusions` carry it -
and deliberately NOT enforced anywhere (AC-D15). 23 of 50 live Complaints are
Project cases, so a branch on installation context would refuse half of Sorento's
complaints the day it shipped.
"""
from __future__ import annotations

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CompanyScopedMixin


class WarrantyProductKind(Base):
    """What a thing IS, for warranty purposes (AC-D1).

    The layer that exists so cover can be decided BEFORE the exact model is known:
    `SRTWC8152` matches three real product variants and resolves to none of them,
    yet all three are Water Closets (ADR-0010). It is also the level a homeowner
    recognises, which is what makes a picture-based chooser possible.
    """

    __tablename__ = "warranty_product_kinds"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The seed's idempotence key. NOT NULL + UNIQUE, or a re-run inserts duplicates.
    code = Column(String(64), nullable=False, unique=True)
    # Internal name, the one the policy document and the ACs use.
    name = Column(String(255), nullable=False)
    # What a Consumer is shown in the tiled chooser. A different string from `name`
    # on purpose: a homeowner does not call it a Water Closet.
    consumer_label = Column(String(120), nullable=True)
    consumer_icon = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_warranty_product_kinds_is_active", "is_active"),
        Index("ix_warranty_product_kinds_sort_order", "sort_order"),
    )


class WarrantyKindRule(Base):
    """How a product reaches a Kind (AC-D2). Data, never a column on `products`.

    A per-product FK could not express what the mapping needs: some terms name an
    explicit model list, some a series, and the codes people actually report
    (`SRTWC8152`, `WC189-G2`, `SRTWC8517-200mm`) resolve to no product row at all.
    It would also need maintaining on all 11,415 rows.
    """

    __tablename__ = "warranty_kind_rules"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind_id = Column(
        UUID(as_uuid=False),
        ForeignKey("warranty_product_kinds.id", ondelete="CASCADE"),
        nullable=False,
    )
    # One of KIND_RULE_MATCH_TYPES in app.services.warranty_service.
    match_type = Column(String(20), nullable=False)
    # A category code, a model-code prefix, a comma-separated model list, or a
    # series name. Text, because the model list in AC-D2 is four codes in one value.
    match_value = Column(Text, nullable=False)
    # Higher wins, and it is consulted BEFORE match-type specificity: the escape
    # hatch for the one model that belongs to a different Kind than its category
    # implies, without rewriting the ranking for everybody (AC-D20).
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_warranty_kind_rules_kind_id", "kind_id"),
        Index("ix_warranty_kind_rules_match_type", "match_type"),
    )


class WarrantyPolicy(Base, CompanyScopedMixin):
    """A published, dated warranty document (AC-D6, AC-D16, BRD Req #12).

    Company-scoped: see the module docstring. Clause 16 lets the publisher amend
    the document without notice, which is exactly why a Complaint is judged against
    the version in force on its purchase date and never against today's.
    """

    __tablename__ = "warranty_policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(String(32), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    # The PDF the text was extracted from, kept as the evidence behind policy_text
    # (BRD Req #12). Nullable: a policy typed in before its file is uploaded is
    # still a policy.
    source_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    # The extracted document. The ONLY thing the policy-answer surface may quote.
    policy_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "version", name="uq_warranty_policies_company_version"),
        Index("ix_warranty_policies_effective_from", "effective_from"),
        Index("ix_warranty_policies_effective_to", "effective_to"),
    )


class WarrantyTerm(Base):
    """One promise, about one part of one Kind, under one Policy (AC-D3, AC-D4).

    A Water Closet carries three of these simultaneously and they disagree on all
    four dimensions: the ceramic body is lifetime, covers cracking and leaking only
    and includes installation; the flushing fittings and the seat cover run out on
    different dates and exclude it. Any shape that collapses a product to a single
    number has to discard two of the three.
    """

    __tablename__ = "warranty_terms"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_policies.id", ondelete="CASCADE"), nullable=False
    )
    kind_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_product_kinds.id", ondelete="CASCADE"), nullable=False
    )
    part_name = Column(String(120), nullable=False)
    # Nullable: a lifetime term has no number of months.
    duration_months = Column(Integer, nullable=True)
    is_lifetime = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # lookup_options.id values from the `complaints_defect_type` set.
    # NULL and empty both mean EVERY defect - see the engine, which pins the two as
    # identical because nobody will maintain the distinction across a seed, an admin
    # form and a migration.
    covered_defect_type_ids = Column(ARRAY(UUID(as_uuid=False)), nullable=True)
    # Who pays for the callout (clause 15). NOT NULL on purpose.
    installation_included = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Clause 26: the booster pump's "2 + 1 year with online registration". NULL is
    # zero, and registration only ever LENGTHENS cover - it is never a precondition
    # of it (ADR-0010, BRD over policy clause 3(b)).
    registration_bonus_months = Column(Integer, nullable=True)
    qualifications = Column(Text, nullable=True)
    # Carries clause 17 where it applies. Modelled, never enforced (AC-D15).
    exclusions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "policy_id", "kind_id", "part_name", name="uq_warranty_terms_policy_kind_part"
        ),
        # AC-P3a / AC-P19. Lifetime OR a positive number of months, never both and
        # never neither. A term that records neither answers `unknown` on every
        # complaint forever; a zero-month term tells a customer their cover expired
        # on the day they bought it.
        #
        # Declared HERE as well as in migration 331 on purpose: CI builds its schema
        # from `Base.metadata.create_all` and then stamps alembic at head without
        # executing a migration body, so a constraint that lives only in the
        # migration exists on a developer machine and on prod and on no test
        # database anywhere.
        #
        # `duration_months IS NOT NULL` is spelled out rather than left to
        # `duration_months > 0`: a CHECK passes when it evaluates to NULL, so the
        # shorter form would silently ADMIT the neither-nor row it exists to refuse.
        CheckConstraint(
            "(is_lifetime AND duration_months IS NULL) OR "
            "(NOT is_lifetime AND duration_months IS NOT NULL AND duration_months > 0)",
            name="ck_warranty_terms_duration_xor_lifetime",
        ),
        Index("ix_warranty_terms_policy_kind", "policy_id", "kind_id"),
    )


class WarrantyAssessment(Base):
    """The engine's answer, written down against a real complaint (AC-D10 to AC-D12).

    In the WARRANTY module rather than the consumer one (fork 7): it points at a
    term, so uninstalling warranty must take it. The ledger it reads through stays.

    **One row per (complaint product line, TERM), unique on the pair** (AC-L30). The
    plan said one row per complaint product line and that cannot be built: a Water
    Closet resolves to THREE terms at once - ceramic body, flushing fittings, seat
    cover - and they disagree on the expiry, the defect scope and who pays for the
    callout. A single `term_id` per line holds one of the three, so CS would read
    the ceramic body's `covered` and dispatch against a seat cover whose two years
    had run out. The whole reason `resolve` returns a sequence is that no product
    gets one answer.

    `term_id` is NULLABLE because `unknown` and `no_term` are real verdicts with no
    term behind them (AC-D17) - a calendar gap and a policy that is silent about
    this Kind are exactly the two answers that matter most, and a NOT NULL term
    makes both unstorable.

    **`computed_*` and `confirmed_*` sit side by side and neither overwrites the
    other** (AC-D11). Six months later the interesting question is "what did the
    engine say, and who decided otherwise", and an overwritten row cannot answer
    either half.

    `part_name`, `policy_version` and the rest are SNAPSHOTS. A verdict must still
    read correctly after its term is edited or its policy superseded, and it must
    not need a join into tables the warranty module may no longer own.
    """

    __tablename__ = "warranty_assessments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_product_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("complaint_product_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL, not CASCADE: re-publishing a policy must not silently delete the
    # verdicts a human already acted on.
    term_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_terms.id", ondelete="SET NULL"), nullable=True
    )

    # --- what the engine computed. Never overwritten by a human decision.
    computed_verdict = Column(String(32), nullable=False)
    computed_expiry = Column(Date, nullable=True)
    computed_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    computed_reason = Column(Text, nullable=True)
    part_name = Column(String(120), nullable=True)
    is_lifetime = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Who pays for the callout (clause 15). Not derivable from anything else on the
    # row, and getting it wrong bills a customer who is inside warranty.
    installation_included = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    bonus_months_applied = Column(Integer, nullable=False, default=0, server_default="0")
    policy_id = Column(UUID(as_uuid=False), nullable=True)
    policy_version = Column(String(32), nullable=True)

    # AC-D12. NOT NULL: a NULL renders as "no" on every screen, and a verdict that
    # cannot say whether its date was machine-read is a verdict CS over-trusts.
    # Snapshotted at compute time, never re-read from the purchase.
    is_recommendation = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # --- what a human decided. Text `confirmed_by`, mirroring complaints.resolved_by.
    confirmed_verdict = Column(String(32), nullable=True)
    confirmed_by = Column(Text, nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    # Mandatory only when the human DISAGREES with the engine. Demanding a reason to
    # agree trains CS to type "ok" and destroys the signal.
    override_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    term = relationship("WarrantyTerm", foreign_keys=[term_id], lazy="joined")

    __table_args__ = (
        # A unique INDEX rather than a unique constraint, because it also has to be
        # the lookup path: every read of this table is "the verdicts for this
        # complaint line", and the leading column serves it.
        #
        # Postgres does not collide NULLs, so the `unknown` / `no_term` rows (whose
        # `term_id` is NULL by design) are not protected by this index. The upsert in
        # warranty_assessment_service matches them in Python instead.
        Index(
            "uq_warranty_assessments_line_term",
            "complaint_product_line_id",
            "term_id",
            unique=True,
        ),
        Index("ix_warranty_assessments_term_id", "term_id"),
    )
