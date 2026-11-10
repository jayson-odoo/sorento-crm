"""A section heading as its own quotation line row (PROPOSAL-FORM-COLLAPSE, owner 10 Nov 2026).

Owner: "a heading shouldnt be tied to line". Until now a heading was `band_label` on the first
line under it, so moving or deleting that line moved or dropped the heading. With
`is_section = true` a row IS the heading: it carries `band_label` and no product, set, quantity
or price, and has its own `sort_order`. Every reader of quotation lines skips it explicitly or
draws it as the band row it already draws.

Additive only, no backfill: a product line that still carries `band_label` keeps printing as
before; the editor writes it as a heading row on that version's next save. Issued versions never
change.

Revision ID: pfc_0001_line_is_section
Revises: ptag_0021_icon_conditions
"""
from alembic import op
import sqlalchemy as sa


revision = "pfc_0001_line_is_section"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.quotation_lines "
        "ADD COLUMN IF NOT EXISTS is_section BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.drop_column("quotation_lines", "is_section", schema="projects")
