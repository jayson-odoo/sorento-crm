"""Per-contact field reveal grants (chatbot growth r1, Slice C).

One mechanism for two owner requirements: sellable stock defaults OFF for every
contact (D3), and a PO's supplier must never reach a dealer by default (D4). Both
are just a field a presenter marks `restricted=<key>` in `field_vocabulary`; this
migration adds the grant table plus the catalog column that carries which keys
exist, so a new restricted field reaches the admin checklist after a sync with no
FE change.

`contact_field_reveals`: one row per (contact, field_key) a grant has ever touched.
Absence of a row is the same as `granted=False` - default hidden.

`mcp_tools.restricted_fields`: JSONB list of `{"key", "label"}`, written by
`mcp_tool_registry_service.sync_catalog` from `ToolSpec.restricted_fields`. `[]`
default so every existing tool row stays inert.

Revision ID: 488_contact_field_reveals
Revises: 487_chatbot_warehouse_cue
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "488_contact_field_reveals"
down_revision = "487_chatbot_warehouse_cue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "contact_field_reveals" not in inspector.get_table_names():
        op.create_table(
            "contact_field_reveals",
            sa.Column(
                "id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True
            ),
            sa.Column("respond_contact_id", sa.Text(), nullable=False),
            sa.Column("field_key", sa.Text(), nullable=False),
            sa.Column(
                "granted", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["respond_contact_id"], ["respond_contacts.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "respond_contact_id",
                "field_key",
                name="uq_contact_field_reveals_contact_key",
            ),
        )
        op.create_index(
            "ix_contact_field_reveals_contact",
            "contact_field_reveals",
            ["respond_contact_id"],
        )

    mcp_tools_columns = {c["name"] for c in inspector.get_columns("mcp_tools")}
    if "restricted_fields" not in mcp_tools_columns:
        op.add_column(
            "mcp_tools",
            sa.Column(
                "restricted_fields",
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("mcp_tools", "restricted_fields")
    op.drop_table("contact_field_reveals")
