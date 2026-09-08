"""A7 (chatbot-growth-r1): `system_settings.chatbot_crossdomain_ladder`.

Replaces `answer.py`'s hard-coded inventory<->incoming pair with a per-origin
list read from this column, so the PO rung (Foundre's rule: "no stock, no
incoming, but a PO is placed") can be added without a second hard pair, and a
tenant can turn a rung off by editing the setting instead of a deploy.

Same shape as `chatbot_unsupported_domains` (migration 478): one column, NOT
a table (AC-304's own test of what deserves a knob - this is the second list
the owner is expected to tune, not a hypothetical).

Revision ID: 489_chatbot_crossdomain_ladder
Revises: 488_chatbot_unblock_spo_domain
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "489_chatbot_crossdomain_ladder"
down_revision = "488_chatbot_unblock_spo_domain"
branch_labels = None
depends_on = None

_DEFAULT = '{"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}'


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("system_settings")}
    if "chatbot_crossdomain_ladder" not in existing:
        op.add_column(
            "system_settings",
            sa.Column(
                "chatbot_crossdomain_ladder",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text(f"'{_DEFAULT}'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_crossdomain_ladder")
