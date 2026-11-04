"""PS-QUOTE-RULES: any discount needs approval, routed to a configurable approver.

Four nullable/defaulted columns and one permission rename, all additive:

1. ``projects.quotation_lines.is_discounted``: the line was priced below its default price
   when saved (stored like ``is_below_floor``, AC-E7). No backfill: existing lines were priced
   under the old rule and are judged the next time somebody saves them, exactly as a floor
   policy change is.
2. ``projects.quotation_documents.approver_user_id``: who the pending request was routed to.
3. ``projects.projects.discount_approver_user_id``: the per-project override.
4. ``system_settings.off_series_approver_user_id``: who approves a line outside the series, and
   ``system_settings.default_quotation_approver_user_id``: who approves when nothing else routes.
5. The approve grant's display name now says what it covers. The slug is unchanged, so every
   role that holds it keeps it.

Revision ID: pqr_0001_quote_rules_routing
Revises: pqm_0001_quote_matrix
"""
from alembic import op


revision = "pqr_0001_quote_rules_routing"
down_revision = "pqm_0001_quote_matrix"
branch_labels = None
depends_on = None

OLD_PERMISSION_NAME = "Approve Quotations Below Minimum Price"
NEW_PERMISSION_NAME = "Approve Quotation Discounts and Off-Series Lines"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.quotation_lines "
        "ADD COLUMN IF NOT EXISTS is_discounted BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE projects.quotation_documents "
        "ADD COLUMN IF NOT EXISTS approver_user_id VARCHAR(100) "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE projects.projects "
        "ADD COLUMN IF NOT EXISTS discount_approver_user_id VARCHAR(100) "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS off_series_approver_user_id VARCHAR "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS default_quotation_approver_user_id VARCHAR "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    # Matched on the SLUG alone: the row's current name depends on how far a database got
    # through earlier renames ("Approve Below-Floor Quotations" from 330, "... Below Minimum
    # Price" from pux_0001; the dev copy is a restore that predates the latter). Idempotent: a
    # re-run, or a row already carrying the new name, changes nothing.
    op.execute(
        "UPDATE user_permissions SET name = '" + NEW_PERMISSION_NAME + "' "
        "WHERE slug = 'projects.quotations.approve' "
        "AND name IS DISTINCT FROM '" + NEW_PERMISSION_NAME + "'"
    )


def downgrade() -> None:
    # Back to the name the previous head (pux_0001) leaves, whatever the row said before.
    op.execute(
        "UPDATE user_permissions SET name = '" + OLD_PERMISSION_NAME + "' "
        "WHERE slug = 'projects.quotations.approve' AND name = '" + NEW_PERMISSION_NAME + "'"
    )
    op.execute(
        "ALTER TABLE system_settings DROP COLUMN IF EXISTS default_quotation_approver_user_id"
    )
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS off_series_approver_user_id")
    op.execute("ALTER TABLE projects.projects DROP COLUMN IF EXISTS discount_approver_user_id")
    op.execute(
        "ALTER TABLE projects.quotation_documents DROP COLUMN IF EXISTS approver_user_id"
    )
    op.execute("ALTER TABLE projects.quotation_lines DROP COLUMN IF EXISTS is_discounted")
