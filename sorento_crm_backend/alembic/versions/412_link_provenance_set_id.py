"""record which product set fanned a link out

A set code on a flyer links the file to every member. Without provenance nothing
can answer "why is this flyer attached to a seat cover", and nothing can clean up
when membership changes - the `-UF` seat cover replaces the old one and the stale
link sits there forever.

NULL means a person, or an exact product code, made this link. Only a set
expansion stamps it.

`ON DELETE SET NULL`: deleting a set must not delete the documents it once
linked. The link outlives its reason.

Revision ID: 412_link_provenance
Revises: 411_product_sets
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "412_link_provenance"
down_revision = "411_product_sets"
branch_labels = None
depends_on = None

_TABLES = ("product_attachments", "promotion_products")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("linked_via_set_id", UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_linked_via_set",
            table,
            "product_sets",
            ["linked_via_set_id"],
            ["id"],
            ondelete="SET NULL",
        )
        # Partial: the overwhelming majority of link rows were made by hand or by
        # an exact code and carry NULL here, and indexing those buys nothing.
        op.create_index(
            f"ix_{table}_linked_via_set_id",
            table,
            ["linked_via_set_id"],
            postgresql_where=sa.text("linked_via_set_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_linked_via_set_id", table_name=table)
        op.drop_constraint(f"fk_{table}_linked_via_set", table, type_="foreignkey")
        op.drop_column(table, "linked_via_set_id")
