"""D7 (owner ruling, 8 Sep 2026): the cross-domain ladder climbs to the PO rung from
`incoming` too - stock -> incoming -> PO whichever domain the customer entered from.

Measured on the restored-DB pass: "hav incoming?" for CHS3220 (no incoming, no stock, an
open PO line) answered "No incoming and no stock for CHS3220." and offered escalation;
`_next_crossdomain_rung` had no second rung for origin `incoming` because migration 489's
default is `{"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}`.

Idempotent, same shape as 488's unsupported-domains update: the row is rewritten ONLY
where it still holds the exact 489 default (jsonb equality, key order immaterial), so a
tenant with a custom ladder is untouched. The column's server default moves with it, so a
row created after this migration ships the same ladder.

Revision ID: 491_chatbot_ladder_incoming_po
Revises: 490_chatbot_parser_growth
"""
import sqlalchemy as sa
from alembic import op

revision = "491_chatbot_ladder_incoming_po"
down_revision = "490_chatbot_parser_growth"
branch_labels = None
depends_on = None

_OLD = '{"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}'
_NEW = '{"inventory": ["incoming", "purchase_order"], "incoming": ["inventory", "purchase_order"]}'


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("system_settings")}
    if "chatbot_crossdomain_ladder" not in existing:
        return  # 489 never ran here; nothing to move
    bind.execute(
        sa.text(
            "UPDATE system_settings SET chatbot_crossdomain_ladder = CAST(:new AS jsonb) "
            "WHERE chatbot_crossdomain_ladder = CAST(:old AS jsonb)"
        ),
        {"new": _NEW, "old": _OLD},
    )
    op.alter_column(
        "system_settings",
        "chatbot_crossdomain_ladder",
        server_default=sa.text(f"'{_NEW}'::jsonb"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE system_settings SET chatbot_crossdomain_ladder = CAST(:old AS jsonb) "
            "WHERE chatbot_crossdomain_ladder = CAST(:new AS jsonb)"
        ),
        {"new": _NEW, "old": _OLD},
    )
    op.alter_column(
        "system_settings",
        "chatbot_crossdomain_ladder",
        server_default=sa.text(f"'{_OLD}'::jsonb"),
    )
