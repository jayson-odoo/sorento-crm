"""spec visibility policies: which product spec keys a chatbot contact may see

Explicit ``op.create_table`` rather than an autogenerate stub, same reasoning as
``416_stock_visibility_policy``: a new table is absent on a database built by
``create_all`` outside this repo's own test fixtures, and a migration carrying
only an index leaves the model with no table behind it.

Two seeds, both inert relative to what shipped before this feature: the DEFAULT
row hides ``thickness`` and ``board_thickness`` (the plan's ship-closed default),
and the ``project`` market segment row hides nothing - inserted only when that
segment code already exists, so a database with no ``project`` segment gets the
default row alone. Both are idempotent - re-running adds nothing.

Revision ID: 510_spec_visibility_policies
Revises: ptag_0006_revisions

Re-parented onto the lane's actual base at PR time (the plan's own revision line
named ``509_merge_508_summary_exclwh``, main's head when the plan was written;
main has since advanced past it).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "510_spec_visibility_policies"
down_revision = "ptag_0006_revisions"
branch_labels = None
depends_on = None

TABLE = "spec_visibility_policies"


def seed_default_and_project_rows(bind) -> None:
    """Insert the two seeded rows. Idempotent - re-running adds nothing."""
    bind.execute(
        sa.text(
            f"""
            INSERT INTO {TABLE} (id, contact_id, segment_code, spec_keys, excluded_spec_keys)
            SELECT gen_random_uuid(), NULL, NULL, NULL, ARRAY['thickness', 'board_thickness']
            WHERE NOT EXISTS (
                SELECT 1 FROM {TABLE} WHERE contact_id IS NULL AND segment_code IS NULL
            )
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO {TABLE} (id, contact_id, segment_code, spec_keys, excluded_spec_keys)
            SELECT gen_random_uuid(), NULL, 'project', NULL, ARRAY[]::text[]
            WHERE EXISTS (SELECT 1 FROM market_segments WHERE code = 'project')
              AND NOT EXISTS (SELECT 1 FROM {TABLE} WHERE segment_code = 'project')
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
            "segment_code",
            sa.String(length=50),
            sa.ForeignKey(
                "market_segments.code", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("spec_keys", ARRAY(sa.Text()), nullable=True),
        sa.Column("excluded_spec_keys", ARRAY(sa.Text()), nullable=True),
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
            "contact_id IS NULL OR segment_code IS NULL",
            name="ck_spec_visibility_policies_one_tier",
        ),
        sa.CheckConstraint(
            "spec_keys IS NULL OR excluded_spec_keys IS NULL",
            name="ck_spec_visibility_policies_one_rule",
        ),
    )
    op.create_index(
        "uq_spec_visibility_policies_contact",
        TABLE,
        ["contact_id"],
        unique=True,
        postgresql_where=sa.text("contact_id IS NOT NULL"),
    )
    op.create_index(
        "uq_spec_visibility_policies_segment",
        TABLE,
        ["segment_code"],
        unique=True,
        postgresql_where=sa.text("segment_code IS NOT NULL"),
    )
    op.create_index(
        "uq_spec_visibility_policies_default",
        TABLE,
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("contact_id IS NULL AND segment_code IS NULL"),
    )

    seed_default_and_project_rows(op.get_bind())


def downgrade() -> None:
    op.drop_index("uq_spec_visibility_policies_default", table_name=TABLE)
    op.drop_index("uq_spec_visibility_policies_segment", table_name=TABLE)
    op.drop_index("uq_spec_visibility_policies_contact", table_name=TABLE)
    op.drop_table(TABLE)
