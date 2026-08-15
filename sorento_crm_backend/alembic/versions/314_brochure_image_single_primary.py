"""At most one chosen brochure image per product.

`product_attachments.is_primary` decides which photo a catalogue tile shows -
`app/services/dealer_kit/product_images.py` has always ordered by it - and
nothing enforced that only one row per product could carry it. Two at once and
the tile's photo falls back to row order, which is the defect the brochure image
picker exists to remove; enforcing it only in the service would leave every
other write path (the existing attachment PUT, imports, a future script) able to
break it quietly.

**No backfill, deliberately.** The flag is false on all 1,087 photo rows behind
the 2025-2026 flyer's products, and there is no correct value to backfill:
choosing a product's photo from its filename would identify the right image for
509 of 535 products and the wrong one for the rest, and a wrong photo is a wrong
product in front of a customer. A human sets it, one product at a time.

Safe on live data: verified zero products currently carry more than one primary,
because zero carry any.

Revision ID: 314_brochure_image_single_primary
Revises: 313_dealer_kit_selection
"""

from alembic import op

revision = "314_brochure_image_single_primary"
down_revision = "313_dealer_kit_selection"
branch_labels = None
depends_on = None

INDEX = "uq_product_attachment_primary"


def upgrade() -> None:
    # IF NOT EXISTS because this database is shared between worktrees and the
    # index may already have been applied out of band.
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX}
        ON product_attachments (company_id, product_id)
        WHERE is_primary IS TRUE
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
