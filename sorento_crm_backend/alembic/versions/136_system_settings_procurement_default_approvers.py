"""System settings: default approvers for purchase request and sponsorship form.

Revision ID: 136_system_settings_procurement_default_approvers
Revises: 136_commercial_core_structure
Create Date: 2026-04-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "136_system_settings_procurement_default_approvers"
down_revision = "136_commercial_core_structure"
branch_labels = None
depends_on = None


def _fk_names(insp, table: str) -> set:
    return {fk["name"] for fk in insp.get_foreign_keys(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("system_settings")}

    if "purchase_request_default_approver_user_id" not in cols:
        op.add_column(
            "system_settings",
            sa.Column("purchase_request_default_approver_user_id", sa.String(), nullable=True),
        )
    if "sponsorship_form_default_approver_user_id" not in cols:
        op.add_column(
            "system_settings",
            sa.Column("sponsorship_form_default_approver_user_id", sa.String(), nullable=True),
        )

    insp = inspect(bind)
    fks = _fk_names(insp, "system_settings")
    if "fk_system_settings_purchase_request_default_approver_user_id" not in fks:
        op.create_foreign_key(
            "fk_system_settings_purchase_request_default_approver_user_id",
            "system_settings",
            "users",
            ["purchase_request_default_approver_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "fk_system_settings_sponsorship_form_default_approver_user_id" not in fks:
        op.create_foreign_key(
            "fk_system_settings_sponsorship_form_default_approver_user_id",
            "system_settings",
            "users",
            ["sponsorship_form_default_approver_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS "
        "fk_system_settings_sponsorship_form_default_approver_user_id"
    )
    op.execute(
        "ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS "
        "fk_system_settings_purchase_request_default_approver_user_id"
    )
    op.drop_column("system_settings", "sponsorship_form_default_approver_user_id")
    op.drop_column("system_settings", "purchase_request_default_approver_user_id")
