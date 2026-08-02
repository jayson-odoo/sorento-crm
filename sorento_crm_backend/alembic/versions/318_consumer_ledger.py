"""After-sales S2b: who bought the thing, and what the engine said about it.

S2 built an entitlement engine over plain values that never touched a purchase row.
This migration creates the rows: a consumer, the receipts, the products on them, and
the verdicts written down against a real complaint. Five new tables and two new
columns on a table the complaints module owns.

**`consumer_profiles.respond_contact_id` is TEXT, not uuid** (AC-L32). The plan's
DDL printed `uuid UNIQUE REFERENCES respond_contacts(id)` and that constraint cannot
be created: `respond_contacts.id` is a TEXT column, and Postgres refuses a foreign
key from uuid to text. Every neighbouring id here IS a uuid, which is exactly what
makes the mistake natural. Third time this trap has been hit in this build (S1's
`respondent_contact_id`, S1's `user_id`, now this).

**`consumer_profiles.phone_e164` exists because the dedupe had no column to work on**
(AC-L33). The profile is 1:1 with `respond_contacts`, whose `phone_number` is unique
on the RAW string, so `0166372304` and `+60166372304` already coexist there as two
rows and a profile keyed only on the contact inherits precisely the split AC-L8
exists to prevent. Uniquely indexed, because dedupe enforced only in Python loses
the race the moment two intake paths run at once and the duplicate is silent.
Nullable, because erasure clears it and many NULLs never collide.

**The dedupe index is PARTIAL** (AC-L17). A plain unique index over three nullable
columns constrains nothing in Postgres while looking identical, and the first NOT
NULL somebody adds to tidy it up starts REJECTING the incomplete rows AC-L20
requires to be written. Two thirds of the key stay nullable on purpose: the dealer is
routinely unresolved and OCR routinely finds no document number.

**What the tests forced out into the open.** Three shapes here exist because the red
suite refused something that looked reasonable. `consumer_purchase_lines.kind_id` is
NOT NULL while `product_id` is nullable, because `SRTWC8152` matches three real
variants and resolves to none of them - so cover must be decidable from the Kind
alone, and a NOT NULL product makes the ordinary receipt unwritable.
`warranty_assessments` is unique on `(complaint_product_line_id, term_id)` rather
than one row per line (AC-L30), because a Water Closet carries three promises at once
and a single `term_id` holds one of them - CS would read the ceramic body's `covered`
and dispatch against a seat cover whose two years had run out. And `term_id` is
NULLABLE, because `unknown` and `no_term` are real verdicts with no term behind them.

**`consumer_purchases.policy_id` carries no foreign key on purpose.** It snapshots
which policy answered. A real FK would run from the ledger INTO the warranty module,
inverting the fork-7 dependency and making a warranty purge either fail or take the
receipts with it.

**The line SNAPSHOTS its Kind, and that is a correction** (AC-L36). The first
version of this migration made `consumer_purchase_lines.kind_id` a NOT NULL foreign
key into `warranty_product_kinds`, which cannot coexist with AC-L2: purging the
warranty module deletes those kinds, and no ON DELETE action preserves a child row
whose column cannot be null, so the parent delete is simply refused. Deferring the
constraint made both tests green while a real purge still failed at COMMIT - a green
test masking a production failure, which is worse than a red one.

So the Kind is carried twice. `kind_code` is NOT NULL and permanent: it is what the
line WAS, it keeps the row assessable and readable forever, and `seed_warranty_policy_v15`
upserts Kinds on exactly that stable code, so reinstalling `warranty` re-links the
ledger rather than losing it. `kind_id` is the live link, NULLABLE, ON DELETE SET
NULL, so a purge genuinely leaves the ledger standing. The ledger is a historical
record of what was bought and must not lose its meaning because a module was
uninstalled.

The two new columns on `complaint_product_lines` are additive and nullable, so no
backfill exists or is possible: `consumer_purchase_line_id` has no ledger to point
at for the 47 historical complaints, and `defect_type_id` has no source column to
derive from - `complaints.defects_discovered` records WHEN a defect was noticed, not
what it is (AC-L31). Guessing either would put a fabricated fact under a warranty
verdict.

Every idempotency guard here is load-bearing: the shared dev database is stamped on
another worktree's chain, so this DDL gets applied by hand there and a plain
`create_table` would abort the whole upgrade.

Revision ID: 318_consumer_ledger
Revises: 317_warranty_engine
Create Date: 2026-08-02

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "318_consumer_ledger"
down_revision = "317_warranty_engine"
branch_labels = None
depends_on = None

_PROFILES = "consumer_profiles"
_REVIEWS = "consumer_profile_reviews"
_PURCHASES = "consumer_purchases"
_LINES = "consumer_purchase_lines"
_ASSESSMENTS = "warranty_assessments"
_COMPLAINT_LINES = "complaint_product_lines"


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _create_index_if_missing(name: str, table: str, columns: list, **kw) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns, **kw)


def upgrade() -> None:
    tables = _tables()

    # --- the person, provisional until they authenticate (AC-L4 to AC-L10)
    if _PROFILES not in tables:
        op.create_table(
            _PROFILES,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            # TEXT, matching respond_contacts.id. See the docstring.
            sa.Column("respond_contact_id", sa.Text(), nullable=True),
            # The dedupe key (AC-L8, AC-L33). Nullable so erasure can clear it.
            sa.Column("phone_e164", sa.String(length=20), nullable=True),
            sa.Column("full_name", sa.Text(), nullable=True),
            sa.Column("email", sa.Text(), nullable=True),
            # A consumer may own several properties, each with its own purchases.
            sa.Column("addresses", JSONB(), nullable=True),
            # Fork 6. NOT NULL: a profile whose purpose is unknown is a profile
            # nobody may lawfully use for anything. No marketing_consent column
            # exists, and none may be added without fresh consent per person.
            sa.Column("consent_purpose", sa.String(length=32), nullable=False),
            # PDPA 2010 s.7(2) needs the notice in Bahasa Malaysia AND English, so
            # "which wording did this person see" must be answerable.
            sa.Column("consent_notice_version", sa.String(length=32), nullable=True),
            sa.Column("consent_recorded_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "is_provisional",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=True),
            # AC-L10: the losing side of a merge is retained pointing at the
            # survivor. A deleted row cannot answer "where did this consumer go",
            # and split is out of scope so there is no second chance.
            sa.Column("merged_into_id", UUID(as_uuid=False), nullable=True),
            sa.Column("merged_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("merged_by", sa.Text(), nullable=True),
            sa.Column("anonymised_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("anonymised_by", sa.Text(), nullable=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(
                ["respond_contact_id"], ["respond_contacts.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["merged_into_id"], [f"{_PROFILES}.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            # 1:1 with the contact (AC-L4). Two profiles on one contact split a
            # person's history in half and nothing detects it.
            sa.UniqueConstraint(
                "respond_contact_id", name="uq_consumer_profiles_respond_contact"
            ),
            sa.UniqueConstraint("phone_e164", name="uq_consumer_profiles_phone_e164"),
        )
    _create_index_if_missing("ix_consumer_profiles_is_provisional", _PROFILES, ["is_provisional"])
    _create_index_if_missing("ix_consumer_profiles_merged_into_id", _PROFILES, ["merged_into_id"])
    _create_index_if_missing("ix_consumer_profiles_company_id", _PROFILES, ["company_id"])

    # --- the name that arrived on a phone already holding one (AC-L9)
    if _REVIEWS not in tables:
        op.create_table(
            _REVIEWS,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("profile_id", UUID(as_uuid=False), nullable=False),
            sa.Column("incoming_name", sa.Text(), nullable=True),
            sa.Column("incoming_phone_e164", sa.String(length=20), nullable=True),
            sa.Column("existing_name", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("resolved_by", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["profile_id"], [f"{_PROFILES}.id"], ondelete="CASCADE"),
        )
    _create_index_if_missing("ix_consumer_profile_reviews_profile_id", _REVIEWS, ["profile_id"])
    _create_index_if_missing("ix_consumer_profile_reviews_resolved_at", _REVIEWS, ["resolved_at"])

    # --- one receipt, one purchase event (AC-L11, AC-L14)
    if _PURCHASES not in tables:
        op.create_table(
            _PURCHASES,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            # Carries the PURCHASE's year, not today's: a 2015 receipt entered in
            # 2026 numbered CP2026 reads as a 2026 sale on every report.
            sa.Column("purchase_number", sa.String(length=40), nullable=False),
            # ADVISORY and therefore nullable (fork 2). Cover attaches to the
            # product and its date, so a house changing hands does not break the new
            # occupant's claim.
            sa.Column("consumer_profile_id", UUID(as_uuid=False), nullable=True),
            sa.Column("customer_id", UUID(as_uuid=False), nullable=True),
            sa.Column("dealer_document_number", sa.Text(), nullable=True),
            sa.Column("dealer_document_number_norm", sa.String(length=120), nullable=True),
            # NOT NULL: the only thing cover is computed from.
            sa.Column("purchase_date", sa.Date(), nullable=False),
            sa.Column(
                "purchase_date_source",
                sa.String(length=16),
                nullable=False,
                server_default="stated",
            ),
            # As printed at the bottom of the receipt. Nothing normalised (fork 4).
            sa.Column("total_value", sa.Numeric(14, 2), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=True),
            # The receipt, RETAINED, never discarded after extraction.
            sa.Column("proof_attachment_id", UUID(as_uuid=False), nullable=True),
            # `registered_at` says a registration exists (clause 3(b));
            # `registration_source` says whether a human chose to register, which is
            # what clause 26's bonus months are paid for (AC-L35).
            sa.Column("registered_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("registration_source", sa.String(length=32), nullable=True),
            sa.Column(
                "dedupe_pending",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            # Snapshot, deliberately without a foreign key. See the docstring.
            sa.Column("policy_id", UUID(as_uuid=False), nullable=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(
                ["consumer_profile_id"], [f"{_PROFILES}.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["proof_attachment_id"], ["attachments.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.UniqueConstraint("purchase_number", name="uq_consumer_purchases_number"),
        )
    # AC-L17. PARTIAL, and that is the whole point of it.
    if "uq_consumer_purchases_dedupe" not in {
        ix["name"] for ix in _inspector().get_indexes(_PURCHASES)
    }:
        op.create_index(
            "uq_consumer_purchases_dedupe",
            _PURCHASES,
            ["customer_id", "dealer_document_number_norm", "purchase_date"],
            unique=True,
            postgresql_where=sa.text(
                "customer_id IS NOT NULL AND dealer_document_number_norm IS NOT NULL "
                "AND purchase_date IS NOT NULL"
            ),
        )
    _create_index_if_missing(
        "ix_consumer_purchases_consumer_profile_id", _PURCHASES, ["consumer_profile_id"]
    )
    _create_index_if_missing("ix_consumer_purchases_customer_id", _PURCHASES, ["customer_id"])
    _create_index_if_missing("ix_consumer_purchases_purchase_date", _PURCHASES, ["purchase_date"])
    _create_index_if_missing(
        "ix_consumer_purchases_dedupe_pending", _PURCHASES, ["dedupe_pending"]
    )
    _create_index_if_missing(
        "ix_consumer_purchases_proof_attachment_id", _PURCHASES, ["proof_attachment_id"]
    )
    _create_index_if_missing("ix_consumer_purchases_company_id", _PURCHASES, ["company_id"])

    # --- the products on that receipt (AC-L15)
    if _LINES not in tables:
        op.create_table(
            _LINES,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("purchase_id", UUID(as_uuid=False), nullable=False),
            # Nullable: the exact variant is routinely unresolved (AC-C17).
            sa.Column("product_id", UUID(as_uuid=False), nullable=True),
            # AC-L36. The Kind is snapshotted AND linked. `kind_code` is NOT NULL
            # and permanent, so the line stays assessable and readable after a
            # warranty purge; `kind_id` is the live link and goes NULL when the Kind
            # row is removed. See "what stays broken" above for what this replaced.
            sa.Column("kind_code", sa.String(length=64), nullable=False),
            sa.Column("kind_id", UUID(as_uuid=False), nullable=True),
            sa.Column("claimed_text", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=True),
            # USUALLY NULL (fork 4). A receipt total is never spread across the
            # lines that share it.
            sa.Column("line_value", sa.Numeric(14, 2), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["purchase_id"], [f"{_PURCHASES}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
            # SET NULL, so purging the warranty module leaves this row standing
            # (AC-L2) with its `kind_code` intact.
            sa.ForeignKeyConstraint(
                ["kind_id"], ["warranty_product_kinds.id"], ondelete="SET NULL"
            ),
        )
    _create_index_if_missing("ix_consumer_purchase_lines_purchase_id", _LINES, ["purchase_id"])
    _create_index_if_missing("ix_consumer_purchase_lines_kind_id", _LINES, ["kind_id"])
    _create_index_if_missing("ix_consumer_purchase_lines_product_id", _LINES, ["product_id"])

    # --- the stored verdict, one row per part (AC-D10 to AC-D12, AC-L30)
    if _ASSESSMENTS not in tables:
        op.create_table(
            _ASSESSMENTS,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("complaint_product_line_id", UUID(as_uuid=False), nullable=False),
            # Nullable: `unknown` and `no_term` have no term behind them.
            sa.Column("term_id", UUID(as_uuid=False), nullable=True),
            sa.Column("computed_verdict", sa.String(length=32), nullable=False),
            sa.Column("computed_expiry", sa.Date(), nullable=True),
            sa.Column(
                "computed_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("computed_reason", sa.Text(), nullable=True),
            # Snapshots, so a verdict still reads correctly after its term is edited
            # or its policy superseded.
            sa.Column("part_name", sa.String(length=120), nullable=True),
            sa.Column(
                "is_lifetime", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            # Who pays for the callout (clause 15). Not derivable from anything else
            # on the row, and getting it wrong bills a customer inside warranty.
            sa.Column(
                "installation_included",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "bonus_months_applied", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("policy_id", UUID(as_uuid=False), nullable=True),
            sa.Column("policy_version", sa.String(length=32), nullable=True),
            # AC-D12. NOT NULL: NULL renders as "no" on every screen, and a verdict
            # that cannot say its date was machine-read is one CS over-trusts.
            sa.Column(
                "is_recommendation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            # The human decision, beside the computed one and never on top of it.
            sa.Column("confirmed_verdict", sa.String(length=32), nullable=True),
            sa.Column("confirmed_by", sa.Text(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("override_reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(
                ["complaint_product_line_id"],
                [f"{_COMPLAINT_LINES}.id"],
                ondelete="CASCADE",
            ),
            # SET NULL, not CASCADE: re-publishing a policy must not silently delete
            # verdicts a human already acted on.
            sa.ForeignKeyConstraint(
                ["term_id"], ["warranty_terms.id"], ondelete="SET NULL"
            ),
        )
    # A unique INDEX rather than a unique constraint: it is also the lookup path,
    # since every read of this table is "the verdicts for this complaint line".
    # NULL `term_id` rows (`unknown` / `no_term`) do not collide in Postgres, so the
    # service matches those in Python.
    _create_index_if_missing(
        "uq_warranty_assessments_line_term",
        _ASSESSMENTS,
        ["complaint_product_line_id", "term_id"],
        unique=True,
    )
    _create_index_if_missing("ix_warranty_assessments_term_id", _ASSESSMENTS, ["term_id"])

    # --- the two columns on a table the complaints module owns (AC-L16, AC-L31)
    complaint_line_columns = _columns(_COMPLAINT_LINES)
    if "consumer_purchase_line_id" not in complaint_line_columns:
        op.add_column(
            _COMPLAINT_LINES,
            sa.Column("consumer_purchase_line_id", UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_complaint_product_lines_purchase_line",
            _COMPLAINT_LINES,
            _LINES,
            ["consumer_purchase_line_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "defect_type_id" not in complaint_line_columns:
        op.add_column(
            _COMPLAINT_LINES,
            sa.Column("defect_type_id", UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_complaint_product_lines_defect_type",
            _COMPLAINT_LINES,
            "lookup_options",
            ["defect_type_id"],
            ["id"],
            ondelete="SET NULL",
        )
    _create_index_if_missing(
        "ix_complaint_product_lines_purchase_line",
        _COMPLAINT_LINES,
        ["consumer_purchase_line_id"],
    )
    _create_index_if_missing(
        "ix_complaint_product_lines_defect_type_id", _COMPLAINT_LINES, ["defect_type_id"]
    )


def downgrade() -> None:
    tables = _tables()
    complaint_line_columns = _columns(_COMPLAINT_LINES) if _COMPLAINT_LINES in tables else set()
    if "defect_type_id" in complaint_line_columns:
        op.drop_column(_COMPLAINT_LINES, "defect_type_id")
    if "consumer_purchase_line_id" in complaint_line_columns:
        op.drop_column(_COMPLAINT_LINES, "consumer_purchase_line_id")

    # Children first: every table below foreign-keys something after it.
    for table in (_ASSESSMENTS, _LINES, _PURCHASES, _REVIEWS, _PROFILES):
        if table in tables:
            op.drop_table(table)
