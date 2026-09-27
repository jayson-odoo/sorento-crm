"""Merge the two heads main carries after #1298 and #1302 (27 Sep).

`527_audit_logs_scrub_secrets` (#1298) and `spec_0003_rules_null_brand_pol` (#1302) both hang
off `merge_27sep_three_heads`, so main has two alembic heads. This empty revision joins them;
the sales lane (PR #1297) chains `sales_0003_targets` onto it so the lane has one head. If main
lands its own merge revision first, drop this file and re-run `./scripts/alembic-reparent.sh`.

Revision ID: merge_27sep_audit_spec
Revises: 527_audit_logs_scrub_secrets, spec_0003_rules_null_brand_pol
Create Date: 2026-09-27
"""

revision = "merge_27sep_audit_spec"
down_revision = ("527_audit_logs_scrub_secrets", "spec_0003_rules_null_brand_pol")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
