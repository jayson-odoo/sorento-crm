"""Flyer reading: adopting a printed code as an existing product.

`PLAN-flyer-code-adopt.md` S1. The unmatched list on a flyer reading is
read-only by design (D8: suggestions are shown, never applied), which leaves
34 printed cards on a real flyer with no way to say "this printed code IS
that product" - so their specs never reach the master. This adds the click.

Two columns on `dealer_kit.flyer_reading`, no new table - one reading, one map:

* `code_overrides` (`jsonb NOT NULL DEFAULT '{}'`) - `{"<printed code>": "<product id>"}`.
  Per READING, not a master-level alias: half the rows on the real flyer are
  real variants (`-S`, `-BI`, `-RL`/`-SC`) and a global alias would merge them.
* `code_overrides_changed_at` (`timestamp`, nullable) - bumped on adopt and
  undo, compared against a spec proposal batch's `created_at` to show the
  "propose again" hint later (S2). Undo removes the key from the map, so the
  timestamp cannot live inside it.

Hand-written, `ADD COLUMN IF NOT EXISTS`, matching `359_flyer_read_background_job`'s
reasoning: several worktrees share one local database and this may already
have been applied there by hand.

Chains onto `448_merge_s6b_ptag`, the single head on `main` after PR #427
joins the price-tag chain's head with the S6b reference-data head - not the
`444_notify_email_on_mention` the plan named before three merge revisions
landed ahead of it.

Revision ID: 449_flyer_reading_code_overrides
Revises: 448_merge_s6b_ptag
"""
from alembic import op

revision = "449_flyer_reading_code_overrides"
down_revision = "448_merge_s6b_ptag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE dealer_kit.flyer_reading
        ADD COLUMN IF NOT EXISTS code_overrides jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS code_overrides_changed_at timestamp without time zone
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE dealer_kit.flyer_reading
        DROP COLUMN IF EXISTS code_overrides_changed_at,
        DROP COLUMN IF EXISTS code_overrides
        """
    )
