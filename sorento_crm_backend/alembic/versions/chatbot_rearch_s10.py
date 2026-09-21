"""chatbot turn re-architecture S10: entity kinds gain a configurable roster_cap

PLAN-chatbot-answer-half-reattach.md "Roster cap" (owner ruling 20 Sep 2026,
approving `.lavish/chatbot-answer-half-reattach-plan.html`: "follow all your
recommendation, except the cap needs to be configurable, actually I prefer 10").

One integer column, `chatbot_entity_kinds.roster_cap` (NOT NULL, server default 10) -
the ceiling on any roster that kind is ever asked in: the gate's customer picker arm
(today a literal `[:8]` at `lanes/business/gate.py`), its product/attachment picker
arm (today uncapped), and the did-you-mean list (slice R4). A plain additive column
with a server default: `ADD COLUMN ... NOT NULL DEFAULT 10` backfills every existing
row in the same statement, so no separate data-seed step is needed (unlike the
sibling `chatbot_rearch_s6d`/`s7`/`s8`/`s9` migrations, which update ROW CONTENT and
so are also replayed by `scripts.bootstrap_env.seed_chatbot_policy` - this one is a
schema change `Base.metadata.create_all` already reproduces via the model's own
`server_default`, same as `sort_order`).

Revision ID: chatbot_rearch_s10
Revises: chatbot_rearch_s9
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s10"
down_revision = "chatbot_rearch_s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chatbot_entity_kinds",
        sa.Column("roster_cap", sa.Integer(), nullable=False, server_default="10"),
    )


def downgrade() -> None:
    op.drop_column("chatbot_entity_kinds", "roster_cap")
