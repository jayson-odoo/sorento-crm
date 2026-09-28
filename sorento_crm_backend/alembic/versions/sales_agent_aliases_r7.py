"""Sales agents gain "Also known as" names (`sales_agents.aliases`).

Fix lane round 7 on PR #1273 (owner retest of top selling round 5, part 2, 27 Sep 2026:
"WT is william, we need a way to have like alias for sales agent"). The master holds only
the AutoCount code (WT I, WT III, WT IV) and an empty description, so "sold by william"
named nobody. The owner types the other names a person goes by on the sales agent record,
comma separated; the chatbot matches an agent word against the code, the person label and
these names, whole words, and an alias covers every account of that person.

Nullable text, no seed: the owner enters the names. Additive and guarded, so a database
that already holds the column (the shared dev copy converges through `create_all`) is left
alone.

Revision ID: sales_agent_aliases_r7
Revises: chatbot_top_selling_vocab_r6
"""
import sqlalchemy as sa
from alembic import op

revision = "sales_agent_aliases_r7"
down_revision = "chatbot_top_selling_vocab_r6"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    return any(c["name"] == "aliases" for c in sa.inspect(op.get_bind()).get_columns("sales_agents"))


def upgrade() -> None:
    if not _has_column():
        op.add_column("sales_agents", sa.Column("aliases", sa.String(255), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column("sales_agents", "aliases")
