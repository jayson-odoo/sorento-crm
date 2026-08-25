"""stock visibility policies: which locations a contact may be told about

Explicit ``op.create_table`` rather than an autogenerate stub, for the reason
411_product_sets spells out: a new table is absent on a database built by
``create_all``, and a migration carrying only an index leaves the model with no
table behind it.

**The seed is deliberately inert.** One default row, ``mode='detailed'`` and
``warehouse_ids`` NULL, which is exactly what every contact gets today. No
``dealer`` access-type row is seeded: that one is created from the admin card
when the dealer roll-out is decided, so this deploy cannot change what any
existing contact sees. ``seed_default_row`` is a module-level function rather
than inline SQL so the test suite can exercise the seed on its own against a
``create_all`` schema, where ``upgrade()``'s ``create_table`` would collide.

Three PARTIAL uniques rather than one constraint: Postgres treats NULLs as
distinct, so a plain ``UNIQUE (contact_id, access_type_code)`` would happily
admit a second global default row and the resolution chain would then pick one
of them at random.

Revision ID: 416_stock_visibility_policy
Revises: 415_merge_pset_pushidea
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "416_stock_visibility_policy"
down_revision = "415_merge_pset_pushidea"
branch_labels = None
depends_on = None

TABLE = "stock_visibility_policies"


def seed_default_row(bind) -> None:
    """Insert the single inert default row. Idempotent - re-running adds nothing."""
    bind.execute(
        sa.text(
            f"""
            INSERT INTO {TABLE} (id, contact_id, access_type_code, mode, warehouse_ids)
            SELECT gen_random_uuid(), NULL, NULL, 'detailed', NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM {TABLE}
                WHERE contact_id IS NULL AND access_type_code IS NULL
            )
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "access_type_code",
            sa.String(length=50),
            sa.ForeignKey(
                "contact_access_types.code", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("warehouse_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('detailed', 'compact', 'availability')",
            name="ck_stock_visibility_policies_mode",
        ),
        sa.CheckConstraint(
            "contact_id IS NULL OR access_type_code IS NULL",
            name="ck_stock_visibility_policies_one_tier",
        ),
    )
    op.create_index(
        "uq_stock_visibility_policies_contact",
        TABLE,
        ["contact_id"],
        unique=True,
        postgresql_where=sa.text("contact_id IS NOT NULL"),
    )
    op.create_index(
        "uq_stock_visibility_policies_access_type",
        TABLE,
        ["access_type_code"],
        unique=True,
        postgresql_where=sa.text("access_type_code IS NOT NULL"),
    )
    op.create_index(
        "uq_stock_visibility_policies_default",
        TABLE,
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("contact_id IS NULL AND access_type_code IS NULL"),
    )

    seed_default_row(op.get_bind())


def downgrade() -> None:
    op.drop_index("uq_stock_visibility_policies_default", table_name=TABLE)
    op.drop_index("uq_stock_visibility_policies_access_type", table_name=TABLE)
    op.drop_index("uq_stock_visibility_policies_contact", table_name=TABLE)
    op.drop_table(TABLE)
