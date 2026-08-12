"""Derivation rules as data, and flyer text as a second source to read them against.

Two changes, one purpose: adding a specification should not need an engineer.

`derivation_rules` moves the token tables out of `product_spec_derivation` and onto the
registry row they belong to. Until now a new spec key could be CREATED in the UI but
nothing would ever populate it - the words that produce a value were a Python list. The
seed writes today's tables into these rows unchanged, so the catalog derives identically
on the day this lands; what changes is that the next rule is a form field.

`product_flyer_text` is the printed flyer, per product code. The A3 flyer states things
the product master never did - "S/Steel 304" on 219 cards (216 of them absent from that
product's description), "Matt Black" on 152 (147 absent), "With Drainer & Overflow" on
56 (55 absent). It is read with the SAME rules, as a gap-filler: the description still
wins where it says anything, and a value taken from the flyer records that in its
provenance so nobody has to guess where it came from.

Ticket: jayson-odoo/sorento-crm#102.

Revision ID: 311i_configurable_derivation_rules
Revises: 311h_spec_search_tuning
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311i_configurable_derivation_rules"
down_revision = "311h_spec_search_tuning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column("derivation_rules", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_table(
        "product_flyer_text",
        # Keyed on the CODE, like derivation itself: the same model exists once per
        # company and one flyer card describes both.
        sa.Column("product_code", sa.String(100), primary_key=True),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("lines", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("product_flyer_text")
    op.drop_column("product_spec_registry", "derivation_rules")
