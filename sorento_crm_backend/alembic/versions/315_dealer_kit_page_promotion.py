"""A brochure links to exactly ONE promotion, explicitly and optionally.

A Sorento flyer IS a promotion in this system: `promotions.description` holds
the PDF's filename and audience variants are separate promotion rows, so the
2025-2026 A3 flyer's 883 priced products already exist. The page therefore needs
to say WHICH promotion prices it, not to carry prices of its own (PLAN D5, and
ADR 0008 - one viewer-resolved price).

Nullable, and it stays nullable: no link means list prices only (D6). Never
inferred - a human sets it, though the flyer seed may suggest the promotion
whose description matches the uploaded filename.

**ON DELETE SET NULL.** CASCADE would let marketing delete a promotion and take
a published catalogue down with it, silently and after the fact. RESTRICT would
let one brochure freeze marketing's own data. Unlinking degrades the page to
list prices, which is a defined, visible state.

**Applied to the shared dev database by hand, NOT stamped.** That database is
stamped at another worktree's revision (318) and cannot run `alembic upgrade`
here, so the DDL below was executed directly against it. Every statement is
therefore written idempotently (IF NOT EXISTS / a pg_constraint probe) so this
revision is a no-op wherever it has already been applied and still correct on a
database that has never seen it.

Revision ID: 315_dealer_kit_page_promotion
Revises: 314_brochure_image_single_primary
"""

from alembic import op

revision = "315_dealer_kit_page_promotion"
down_revision = "314_brochure_image_single_primary"
branch_labels = None
depends_on = None

CONSTRAINT = "fk_dealer_kit_page_promotion"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE dealer_kit.page
        ADD COLUMN IF NOT EXISTS promotion_id uuid
        """
    )
    # Postgres has no ADD CONSTRAINT IF NOT EXISTS, so probe the catalog.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{CONSTRAINT}'
            ) THEN
                ALTER TABLE dealer_kit.page
                ADD CONSTRAINT {CONSTRAINT}
                FOREIGN KEY (promotion_id) REFERENCES promotions (id)
                ON DELETE SET NULL;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE dealer_kit.page DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute("ALTER TABLE dealer_kit.page DROP COLUMN IF EXISTS promotion_id")
