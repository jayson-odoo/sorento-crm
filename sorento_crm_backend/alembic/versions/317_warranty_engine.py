"""After-sales S2: what cover a thing carries, as four tables instead of one integer.

`products.warranty_months` is a single integer per product and is 0 of 11,415
populated. One Water Closet carries three simultaneous promises that disagree on
four dimensions - the part they attach to, whether the period is a number of months
or lifetime, which defects are in scope, and who pays for the callout - so the
column could not have held the answer even if somebody had filled it in (ADR-0010).
These four tables are what replaces it. The column itself is NOT dropped here: nine
modules still declare it and the drop worklist is frozen in
`tests/test_warranty_scope_guard.py`.

**`warranty_policies.company_id` is NOT NULL, and this table takes NO Sorento
default.** Migration 306 gave every owned `company_id` a DB-level DEFAULT of the
incumbent company so that raw `text()` inserts in scripts and seeds keep working.
That is exactly wrong here. `companies` holds both Sorento and Mocha, and the two
brands publish DIFFERENT durations for the same product kinds: Mocha's Version 4
gives a Water Closet's flushing fittings 3 years where Sorento's figures say 5, a
seat cover 1 year where they say 2, a stainless steel 304 kitchen sink 10 years
where they say 25, and it has no booster pump at all. Under 306's idiom a raw
insert of a Mocha policy that forgot its company would silently become a Sorento
policy and would then be quoted at Sorento customers. Here it fails loudly instead.
The table is new and empty, so there is no backfill window to keep it nullable for.
Terms are not separately scoped: a term is only reachable through its `policy_id`,
and a second copy of the same fact can disagree with the first.

**`covered_defect_type_ids` is `uuid[]`, not `varchar[]`.** It holds
`lookup_options.id` values. A varchar array holds the same characters and compares
to a uuid column only through a cast, which is how a defect-scope check ends up
silently matching nothing. Recorded and NOT fixed here, because it cannot be: an
array column carries no foreign key, so deleting a defect type quietly narrows the
scope of every term that referenced it.

**What the tests forced out into the open.** Three of these columns exist because
the red suite refused a shape that looked reasonable:
`warranty_product_kinds.code` is NOT NULL and UNIQUE because it is the seed's only
idempotence key and a null one makes the seed duplicate its whole output on every
run; `warranty_policies.effective_from` is NOT NULL because a policy with no start
date can never be "in force on the purchase date" and would silently never match,
while `effective_to` stays nullable because the current policy genuinely has no end
and a 9999-12-31 sentinel puts a magic value in the comparison;
`warranty_terms.installation_included` is NOT NULL because it decides who pays for
the callout (policy clause 15) and a null would render as "no" everywhere with
nobody noticing.

**What stays broken after this migration.** The tables are created and they are
EMPTY, and `scripts/seed_warranty_policy_v15.py` deliberately does not fill them.
Warranty Policy v15 is not in this repository, not in the `attachments` table and
not on disk; the only warranty document that exists anywhere is Mocha's Version 4,
which contradicts the golden set on most rows. No policy row, no term and no
duration is written until Sorento supplies the document, so warranty resolution
answers `unknown` for every purchase - which is the correct answer when no policy
is on record, and is why the golden-set assertions stay red. The kind RULES
(`warranty_kind_rules`) are unseeded for the same reason: a wrong mapping sends a
product to the wrong Kind and applies the wrong terms, which is the same class of
harm as a wrong duration.

Clause 17 (cover restricted to residential installations) is carried in
`policy_text` and `exclusions` and is enforced NOWHERE. 23 of 50 live Complaints
are Project cases; a branch on installation context would refuse half of them.

Every idempotency guard here is load-bearing: the shared dev database is stamped on
another worktree's chain, so this DDL gets applied by hand there and a plain
`create_table` would abort the whole upgrade.

Revision ID: 317_warranty_engine
Revises: 316_after_sales_parties
Create Date: 2026-08-02

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

# revision identifiers, used by Alembic.
revision = "317_warranty_engine"
down_revision = "316_after_sales_parties"
branch_labels = None
depends_on = None

_KINDS = "warranty_product_kinds"
_RULES = "warranty_kind_rules"
_POLICIES = "warranty_policies"
_TERMS = "warranty_terms"


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set:
    return set(_inspector().get_table_names())


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    tables = _tables()

    # --- what a thing IS, for warranty purposes (AC-D1)
    if _KINDS not in tables:
        op.create_table(
            _KINDS,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("consumer_label", sa.String(length=120), nullable=True),
            sa.Column("consumer_icon", sa.String(length=64), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.UniqueConstraint("code", name="uq_warranty_product_kinds_code"),
        )
    _create_index_if_missing("ix_warranty_product_kinds_is_active", _KINDS, ["is_active"])
    _create_index_if_missing("ix_warranty_product_kinds_sort_order", _KINDS, ["sort_order"])

    # --- how a product reaches a Kind (AC-D2). Never a single FK on products.
    if _RULES not in tables:
        op.create_table(
            _RULES,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("kind_id", UUID(as_uuid=False), nullable=False),
            sa.Column("match_type", sa.String(length=20), nullable=False),
            sa.Column("match_value", sa.Text(), nullable=False),
            # Higher wins, consulted before match-type specificity (AC-D20).
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(
                ["kind_id"], [f"{_KINDS}.id"], ondelete="CASCADE"
            ),
        )
    _create_index_if_missing("ix_warranty_kind_rules_kind_id", _RULES, ["kind_id"])
    _create_index_if_missing("ix_warranty_kind_rules_match_type", _RULES, ["match_type"])

    # --- the published, dated document (AC-D6, AC-D16)
    if _POLICIES not in tables:
        op.create_table(
            _POLICIES,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("version", sa.String(length=32), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("source_attachment_id", UUID(as_uuid=False), nullable=True),
            sa.Column("policy_text", sa.Text(), nullable=True),
            # NOT NULL, and NO server default. See the docstring.
            sa.Column("company_id", UUID(as_uuid=False), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(
                ["source_attachment_id"], ["attachments.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.UniqueConstraint(
                "company_id", "version", name="uq_warranty_policies_company_version"
            ),
        )
    _create_index_if_missing("ix_warranty_policies_company_id", _POLICIES, ["company_id"])
    _create_index_if_missing(
        "ix_warranty_policies_effective_from", _POLICIES, ["effective_from"]
    )
    _create_index_if_missing("ix_warranty_policies_effective_to", _POLICIES, ["effective_to"])

    # --- one promise, about one part of one Kind, under one Policy (AC-D3, AC-D4)
    if _TERMS not in tables:
        op.create_table(
            _TERMS,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("policy_id", UUID(as_uuid=False), nullable=False),
            sa.Column("kind_id", UUID(as_uuid=False), nullable=False),
            sa.Column("part_name", sa.String(length=120), nullable=False),
            # Nullable: a lifetime term has no number of months.
            sa.Column("duration_months", sa.Integer(), nullable=True),
            sa.Column(
                "is_lifetime", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            # uuid[], never varchar[]. NULL and empty both mean every defect.
            sa.Column("covered_defect_type_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
            sa.Column(
                "installation_included",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("registration_bonus_months", sa.Integer(), nullable=True),
            sa.Column("qualifications", sa.Text(), nullable=True),
            sa.Column("exclusions", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
            sa.ForeignKeyConstraint(["policy_id"], [f"{_POLICIES}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["kind_id"], [f"{_KINDS}.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "policy_id", "kind_id", "part_name", name="uq_warranty_terms_policy_kind_part"
            ),
        )
    _create_index_if_missing("ix_warranty_terms_policy_kind", _TERMS, ["policy_id", "kind_id"])


def downgrade() -> None:
    tables = _tables()
    # Children first: terms and rules both foreign-key what follows them.
    for table in (_TERMS, _RULES, _POLICIES, _KINDS):
        if table in tables:
            op.drop_table(table)
