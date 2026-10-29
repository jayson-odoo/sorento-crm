"""Lookup set sales_channel_alias: optional words for the dealer / project sales channels

Revision ID: chan_alias_0001_sales_channel
Revises: unpaid_0001_chatbot_ar_role
Create Date: 2026-10-29

CHAT-CHANNEL-LOOKUPSET (documentation/plans/chatbot/PLAN-chat-channel-lookupset.md).
Owner, 29 Oct 2026: "retail" means Dealer, and staff also say 经销商 / 零售 / peruncit.
The channel rows still come from the code values (`reports.ask.SALES_CHANNELS`);
this set only holds optional aliases keyed by those values, read like
`attachment_type_alias` (`chatbot_prompt_vars._alias_words`). The owner edits the
keywords afterwards on Master Data > Lookup sets.

Insert-only and idempotent: a re-run adds no duplicate and never overwrites a set,
option or keyword the owner has edited since. Downgrade drops the set; its options
and keywords cascade (`ondelete=CASCADE`).
"""
from alembic import op
import sqlalchemy as sa


revision = "chan_alias_0001_sales_channel"
down_revision = "unpaid_0001_chatbot_ar_role"
branch_labels = None
depends_on = None


SET_KEY = "sales_channel_alias"
SET_NAME = "Sales Channel Alias"
SET_DESCRIPTION = (
    "Other words for a sales channel (e.g. 'retail', '零售' -> dealer), so a chatbot sales "
    "ask names the right channel. Option values must stay dealer / project."
)

# (value, label, sort_order); every value is one of reports.ask.SALES_CHANNELS
OPTIONS = (
    ("dealer", "Dealer", 10),
    ("project", "Project", 20),
)

KEYWORDS = {
    "dealer": ["retail", "retailer", "经销商", "零售", "peruncit"],
    "project": ["project team"],
}

_SET_ID = (
    "SELECT id FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :set_key "
    "ORDER BY created_at ASC, id ASC LIMIT 1"
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, :set_key, :name, :description, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :set_key
            )
            """
        ).bindparams(set_key=SET_KEY, name=SET_NAME, description=SET_DESCRIPTION)
    )
    for value, label, sort_order in OPTIONS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :value, :label, :sort_order, TRUE
                FROM ({_SET_ID}) s
                ON CONFLICT (set_id, lower(value)) DO NOTHING
                """
            ).bindparams(set_key=SET_KEY, value=value, label=label, sort_order=sort_order)
        )
    for value, keywords in KEYWORDS.items():
        for keyword in keywords:
            # NOT EXISTS, not ON CONFLICT: the unique key includes `locale`, and NULLs never conflict.
            op.execute(
                sa.text(
                    f"""
                    INSERT INTO lookup_option_keywords (id, option_id, keyword, locale)
                    SELECT gen_random_uuid(), o.id, :keyword, NULL
                    FROM lookup_options o
                    WHERE o.set_id = ({_SET_ID}) AND lower(o.value) = :value
                      AND NOT EXISTS (
                          SELECT 1 FROM lookup_option_keywords k
                          WHERE k.option_id = o.id AND lower(k.keyword) = lower(:keyword)
                      )
                    """
                ).bindparams(set_key=SET_KEY, value=value, keyword=keyword)
            )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :set_key").bindparams(set_key=SET_KEY)
    )
