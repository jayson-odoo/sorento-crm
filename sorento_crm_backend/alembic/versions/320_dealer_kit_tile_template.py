"""dealer kit: a page-level default tile design

A brochure seeded from the printed A3 flyer is 341 collection blocks. "Which
design do the tiles use" is one editorial decision about the document, but the
only control was per block, and the seed bound a design on NONE of them - so
choosing one changed a single row out of 341 and read as doing nothing at all.

This is the default. A block that sets its own `tileTemplateId` still wins.

SET NULL rather than CASCADE or RESTRICT: deleting a design must not be able to
delete a catalogue, and a catalogue must not be able to stop marketing deleting
a design they no longer want. Falling back to the built-in field list is a state
the renderer already has.

Revision ID: 320_dealer_kit_tile_template
Revises: 319_merge_dealer_kit_form_sla
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "320_dealer_kit_tile_template"
down_revision = "319_merge_dealer_kit_form_sla"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"


def upgrade() -> None:
    op.add_column(
        "page",
        sa.Column("tile_template_id", UUID(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_dealer_kit_page_tile_template",
        "page",
        "tile_template",
        ["tile_template_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dealer_kit_page_tile_template", "page", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("page", "tile_template_id", schema=SCHEMA)
