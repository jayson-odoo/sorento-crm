"""Add contact_access_types catalog and respond_access_type_mappings; add respond_contacts.access_type_code.

Revision ID: 094_contact_access_types
Revises: 093_agent_teams_tier
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "094_contact_access_types"
down_revision = "093_agent_teams_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_access_types",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contact_access_types_is_active", "contact_access_types", ["is_active"])

    op.create_table(
        "respond_access_type_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("access_type_code", sa.String(50), sa.ForeignKey("contact_access_types.code", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_respond_access_type_mappings_source_key", "respond_access_type_mappings", ["source_key"])
    op.create_index("ix_respond_access_type_mappings_access_type_code", "respond_access_type_mappings", ["access_type_code"])
    op.create_index("uq_respond_access_type_mappings_source_key", "respond_access_type_mappings", ["source_key"], unique=True)

    op.add_column("respond_contacts", sa.Column("access_type_code", sa.String(50), nullable=True))
    op.create_foreign_key(
        "fk_respond_contacts_access_type_code",
        "respond_contacts",
        "contact_access_types",
        ["access_type_code"],
        ["code"],
        ondelete="SET NULL",
    )
    op.create_index("ix_respond_contacts_access_type_code", "respond_contacts", ["access_type_code"])

    # Seed default catalog and mappings for backward compatibility
    op.execute(
        sa.text("""
            INSERT INTO contact_access_types (code, name, description, is_active, sort_order)
            VALUES
                ('end_user', 'End User', 'End user / consumer', true, 1),
                ('dealer', 'Dealer', 'Dealer', true, 2)
            ON CONFLICT (code) DO NOTHING
        """)
    )
    op.execute(
        sa.text("""
            INSERT INTO respond_access_type_mappings (id, source_key, access_type_code, is_active)
            SELECT gen_random_uuid(), 'end_user', 'end_user', true
            WHERE NOT EXISTS (SELECT 1 FROM respond_access_type_mappings WHERE source_key = 'end_user')
        """)
    )
    op.execute(
        sa.text("""
            INSERT INTO respond_access_type_mappings (id, source_key, access_type_code, is_active)
            SELECT gen_random_uuid(), 'dealer', 'dealer', true
            WHERE NOT EXISTS (SELECT 1 FROM respond_access_type_mappings WHERE source_key = 'dealer')
        """)
    )
    op.execute(
        sa.text("""
            INSERT INTO respond_access_type_mappings (id, source_key, access_type_code, is_active)
            SELECT gen_random_uuid(), 'End User', 'end_user', true
            WHERE NOT EXISTS (SELECT 1 FROM respond_access_type_mappings WHERE source_key = 'End User')
        """)
    )
    op.execute(
        sa.text("""
            INSERT INTO respond_access_type_mappings (id, source_key, access_type_code, is_active)
            SELECT gen_random_uuid(), 'Dealer', 'dealer', true
            WHERE NOT EXISTS (SELECT 1 FROM respond_access_type_mappings WHERE source_key = 'Dealer')
        """)
    )
    # Backfill respond_contacts.access_type_code from user_type where it matches a catalog code
    op.execute(
        sa.text("""
            UPDATE respond_contacts c
            SET access_type_code = c.user_type
            FROM contact_access_types t
            WHERE t.code = c.user_type AND t.is_active = true AND c.access_type_code IS NULL
        """)
    )
    op.execute(
        sa.text("""
            UPDATE respond_contacts c
            SET access_type_code = m.access_type_code
            FROM respond_access_type_mappings m
            WHERE m.source_key = c.user_type AND m.is_active = true AND c.access_type_code IS NULL
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_respond_contacts_access_type_code", table_name="respond_contacts")
    op.drop_constraint("fk_respond_contacts_access_type_code", "respond_contacts", type_="foreignkey")
    op.drop_column("respond_contacts", "access_type_code")

    op.drop_index("uq_respond_access_type_mappings_source_key", table_name="respond_access_type_mappings")
    op.drop_index("ix_respond_access_type_mappings_access_type_code", table_name="respond_access_type_mappings")
    op.drop_index("ix_respond_access_type_mappings_source_key", table_name="respond_access_type_mappings")
    op.drop_table("respond_access_type_mappings")

    op.drop_index("ix_contact_access_types_is_active", table_name="contact_access_types")
    op.drop_table("contact_access_types")
