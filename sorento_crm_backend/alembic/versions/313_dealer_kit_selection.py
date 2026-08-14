"""Dealer Kit selections - what somebody chose, and the room they put it in.

The spine of the designer. Lines carry a product and a quantity and NOTHING
price-shaped: prices are resolved per viewer at read time, so one selection
reads as dealer pricing for a dealer and consumer pricing for a consumer without
a second row existing. A price written here would be a price that goes stale the
moment the price list moves.

Two constraints do the real work:

- ``ck_dealer_kit_selection_one_owner`` - a selection belongs to a CRM user OR a
  contact, never both and never neither. Both means two people editing one
  basket; neither means data nobody can reach. A service-level check would be
  bypassed by the next caller who writes their own insert, so it lives here.
- ``product_id`` is ON DELETE RESTRICT, not CASCADE. Removing a product must not
  quietly rewrite what a customer chose - the line survives and reads as
  unavailable.

``room_json`` holds the outline as an ordered list of points in millimetres plus
the placements. A polygon, not a bitmap, so it can be reopened and re-edited
forever; the area is derived from it and never stored.

Revision ID: 313_dealer_kit_selection
Revises: 312_respond_contact_customers
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "313_dealer_kit_selection"
down_revision = "312_respond_contact_customers"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"


def upgrade() -> None:
    op.create_table(
        "selection",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "source_page_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("room_json", JSONB, nullable=True),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
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
            "(user_id IS NOT NULL AND contact_id IS NULL) "
            "OR (user_id IS NULL AND contact_id IS NOT NULL)",
            name="ck_dealer_kit_selection_one_owner",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_selection_user_id", "selection", ["user_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_dealer_kit_selection_contact_id", "selection", ["contact_id"], schema=SCHEMA
    )

    op.create_table(
        "selection_line",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "selection_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.selection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "selection_id", "product_id", name="uq_dealer_kit_selection_line"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_selection_line_selection_id",
        "selection_line",
        ["selection_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dealer_kit_selection_line_selection_id",
        table_name="selection_line",
        schema=SCHEMA,
    )
    op.drop_table("selection_line", schema=SCHEMA)
    op.drop_index(
        "ix_dealer_kit_selection_contact_id", table_name="selection", schema=SCHEMA
    )
    op.drop_index(
        "ix_dealer_kit_selection_user_id", table_name="selection", schema=SCHEMA
    )
    op.drop_table("selection", schema=SCHEMA)
