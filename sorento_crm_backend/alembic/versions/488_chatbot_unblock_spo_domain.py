"""A6 (chatbot-growth-r1, AC-911): unblock `spo_allocation` in the default
`system_settings.chatbot_unsupported_domains` list.

`crm_procurement_spo_last_receipt_list` now answers "last in for X" -
`spo_allocation` no longer needs to be refused. `goods_receive` stays
unsupported (nothing in this plan reads GRN data).

BACKFILL, targeted: only rows still holding the EXACT old default
(`["goods_receive", "spo_allocation"]`) are updated to the new one. A row an
admin customized to something else (AC-304's whole reason this is a column)
is left untouched - this migration removes ONE domain from the SHIPPED
default, never from a tenant's own edit.
"""
import sqlalchemy as sa
from alembic import op

revision = "488_chatbot_unblock_spo_domain"
down_revision = "487_chatbot_warehouse_cue"
branch_labels = None
depends_on = None

_OLD_DEFAULT = '["goods_receive", "spo_allocation"]'
_NEW_DEFAULT = '["goods_receive"]'


def upgrade() -> None:
    bind = op.get_bind()
    op.alter_column(
        "system_settings",
        "chatbot_unsupported_domains",
        server_default=sa.text(f"'{_NEW_DEFAULT}'::jsonb"),
    )
    bind.execute(
        sa.text(
            "UPDATE system_settings SET chatbot_unsupported_domains = :new_default "
            "WHERE chatbot_unsupported_domains = :old_default"
        ),
        {"new_default": _NEW_DEFAULT, "old_default": _OLD_DEFAULT},
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.alter_column(
        "system_settings",
        "chatbot_unsupported_domains",
        server_default=sa.text(f"'{_OLD_DEFAULT}'::jsonb"),
    )
    bind.execute(
        sa.text(
            "UPDATE system_settings SET chatbot_unsupported_domains = :old_default "
            "WHERE chatbot_unsupported_domains = :new_default"
        ),
        {"new_default": _NEW_DEFAULT, "old_default": _OLD_DEFAULT},
    )
