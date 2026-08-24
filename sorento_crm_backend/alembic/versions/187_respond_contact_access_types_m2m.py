"""Replace single respond_contacts.access_type_code with respond_contact_access_types pivot.

Drops respond_contacts.user_type and respond_contacts.access_type_code (Respond.io is no
longer the source of truth for access type - multiple access types per contact are now
managed in the CRM directly). Drops respond_access_type_mappings (no longer needed).

Revision ID: 187_respond_contact_access_types_m2m
Revises: 186_complaint_required_on_site_support_default_false
Create Date: 2026-05-11
"""
import sqlalchemy as sa
from alembic import op


revision = "187_respond_contact_access_types_m2m"
down_revision = "186_complaint_required_on_site_support_default_false"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Pivot table for many-to-many between respond_contacts and contact_access_types.
    op.create_table(
        "respond_contact_access_types",
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_type_code",
            sa.String(50),
            sa.ForeignKey("contact_access_types.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("contact_id", "access_type_code", name="pk_respond_contact_access_types"),
    )
    op.create_index(
        "ix_respond_contact_access_types_contact_id",
        "respond_contact_access_types",
        ["contact_id"],
    )
    op.create_index(
        "ix_respond_contact_access_types_access_type_code",
        "respond_contact_access_types",
        ["access_type_code"],
    )

    # 2. Backfill from existing single-valued respond_contacts.access_type_code.
    op.execute(
        sa.text(
            """
            INSERT INTO respond_contact_access_types (contact_id, access_type_code)
            SELECT c.id, c.access_type_code
            FROM respond_contacts c
            JOIN contact_access_types t ON t.code = c.access_type_code
            WHERE c.access_type_code IS NOT NULL
            ON CONFLICT (contact_id, access_type_code) DO NOTHING
            """
        )
    )

    # 3. Drop the legacy single FK column on respond_contacts.
    op.drop_index("ix_respond_contacts_access_type_code", table_name="respond_contacts")
    op.drop_constraint(
        "fk_respond_contacts_access_type_code",
        "respond_contacts",
        type_="foreignkey",
    )
    op.drop_column("respond_contacts", "access_type_code")

    # 4. Drop the raw user_type column (Respond.io custom field no longer synced into CRM).
    op.drop_index("ix_respond_contacts_user_type", table_name="respond_contacts")
    op.drop_column("respond_contacts", "user_type")

    # 5. Drop the legacy Respond → catalog mapping table (replaced by direct M2M).
    op.drop_index(
        "uq_respond_access_type_mappings_source_key",
        table_name="respond_access_type_mappings",
    )
    op.drop_index(
        "ix_respond_access_type_mappings_access_type_code",
        table_name="respond_access_type_mappings",
    )
    op.drop_index(
        "ix_respond_access_type_mappings_source_key",
        table_name="respond_access_type_mappings",
    )
    op.drop_table("respond_access_type_mappings")


def downgrade() -> None:
    # Recreate respond_access_type_mappings (empty - admins re-seed if needed).
    op.create_table(
        "respond_access_type_mappings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column(
            "access_type_code",
            sa.String(50),
            sa.ForeignKey("contact_access_types.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_respond_access_type_mappings_source_key", "respond_access_type_mappings", ["source_key"])
    op.create_index("ix_respond_access_type_mappings_access_type_code", "respond_access_type_mappings", ["access_type_code"])
    op.create_index("uq_respond_access_type_mappings_source_key", "respond_access_type_mappings", ["source_key"], unique=True)

    # Recreate respond_contacts.user_type (cannot recover original raw values).
    op.add_column("respond_contacts", sa.Column("user_type", sa.Text(), nullable=True))
    op.create_index("ix_respond_contacts_user_type", "respond_contacts", ["user_type"])

    # Recreate single access_type_code FK column.
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

    # Backfill the single column from the pivot (first match wins; deterministic by code asc).
    op.execute(
        sa.text(
            """
            UPDATE respond_contacts c
            SET access_type_code = (
                SELECT p.access_type_code
                FROM respond_contact_access_types p
                WHERE p.contact_id = c.id
                ORDER BY p.access_type_code ASC
                LIMIT 1
            )
            """
        )
    )

    # Drop the pivot.
    op.drop_index(
        "ix_respond_contact_access_types_access_type_code",
        table_name="respond_contact_access_types",
    )
    op.drop_index(
        "ix_respond_contact_access_types_contact_id",
        table_name="respond_contact_access_types",
    )
    op.drop_table("respond_contact_access_types")
