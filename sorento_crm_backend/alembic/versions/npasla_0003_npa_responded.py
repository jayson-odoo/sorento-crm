"""NPA-FORM-SLA: the New Product Application's Responded status, as the stock inquiry's.

Owner re-test 9 Nov ~12:35 ("make it same with stock inquiry"): Update & Reply moves an Approved
application to Responded. `new_product_applications.status` is the one plain status column with a
CHECK (resub_0001), so the constraint is widened to accept `responded`. No data changes.
Downgrade: a Responded row goes back to Approved, then the constraint narrows again.

Plan: documentation/plans/procurement/PLAN-npa-form-sla-08nov.md.

Revision ID: npasla_0003_npa_responded
Revises: npasla_0002_npa_revision_no
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasla_0003_npa_responded"
down_revision = "npasla_0002_npa_revision_no"
branch_labels = None
depends_on = None

_WITH = "'draft','submitted','resubmitted','approved','responded','rejected','completed','cancelled'"
_WITHOUT = "'draft','submitted','resubmitted','approved','rejected','completed','cancelled'"


def _constraint(values: str) -> None:
    op.execute(
        "ALTER TABLE new_product_applications DROP CONSTRAINT IF EXISTS ck_new_product_applications_status"
    )
    op.execute(
        "ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_status "
        f"CHECK (status IN ({values}))"
    )


def upgrade() -> None:
    _constraint(_WITH)


def downgrade() -> None:
    op.execute("UPDATE new_product_applications SET status = 'approved' WHERE status = 'responded'")
    _constraint(_WITHOUT)
