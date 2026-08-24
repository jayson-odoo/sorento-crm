"""Make the ranker tunable: a scoring policy, and per-value house preferences.

Everything the ranker weighs was a module constant. That made two things impossible
without a deploy, both of which are ordinary merchandising decisions rather than
engineering ones:

  * "our own brand should come up first" - a preference for a VALUE of a key
  * "discontinued should rank lower"    - 4,969 active-but-discontinued products
                                            currently rank as if they were live

They are stored differently because they are different shapes. A house preference is
per key AND per value ("brand SORENTO"), so it belongs on the registry row next to that
key's other calibration. A scoring knob is global ("how hard is a contradiction
penalised"), so it gets its own table, which also lifts the remaining hardcoded
constants (class boost, relevance floor, ...) into something a person can see and change.

Both follow `rank_weight`: seeded once with today's behaviour, then owned by whoever
tunes them, never repaired by a deploy.

Ticket: jayson-odoo/sorento-crm#99.

Revision ID: 311h_spec_search_tuning
Revises: 311g_ai_prompt_label_model
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311h_spec_search_tuning"
down_revision = "311g_ai_prompt_label_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column("value_weights", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "product_spec_search_policy",
        sa.Column("policy_key", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("value", sa.Numeric(10, 3), nullable=False),
        sa.Column("help_text", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("product_spec_search_policy")
    op.drop_column("product_spec_registry", "value_weights")
