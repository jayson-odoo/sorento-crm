"""RESUBMITTED-STATUS: a form submitted again after a rejection carries status `resubmitted`.

Additive only. `new_product_applications.status` is the one status column with a CHECK, so
the constraint is widened to accept `resubmitted` (the other forms keep free-text status
columns and need no DDL). Downgrade puts any `resubmitted` row back to `submitted` first, so
the narrower constraint can return.

Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.

Revision ID: resub_0001_resubmitted_status
Revises: pp2_0001_view_own_perms
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "resub_0001_resubmitted_status"
down_revision = "pp2_0001_view_own_perms"
branch_labels = None
depends_on = None

_NPA_STATUSES_OLD = "'draft','submitted','approved','rejected','completed','cancelled'"
_NPA_STATUSES_NEW = "'draft','submitted','resubmitted','approved','rejected','completed','cancelled'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE new_product_applications "
        "DROP CONSTRAINT IF EXISTS ck_new_product_applications_status"
    )
    op.execute(
        "ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_status "
        f"CHECK (status IN ({_NPA_STATUSES_NEW}))"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE new_product_applications SET status = 'submitted' WHERE status = 'resubmitted'"
    )
    op.execute(
        "ALTER TABLE new_product_applications "
        "DROP CONSTRAINT IF EXISTS ck_new_product_applications_status"
    )
    op.execute(
        "ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_status "
        f"CHECK (status IN ({_NPA_STATUSES_OLD}))"
    )
