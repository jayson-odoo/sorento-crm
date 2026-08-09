"""Per-agent LLM: a label row may name the model that agent runs on.

Until now the whole CRM shared ONE model, from `ai_assistant_configs`. That is the
wrong grain: a semantic parser that has to read a misspelt customer sentence and a
recommendation explainer that writes a paragraph are not the same job, and forcing
them onto one model means every agent is tuned for the hardest of them or none.

The label row is already "this agent, in this environment, runs this version", so it
is where "…on this model" belongs. NULL means "whatever the global config says", which
is what every existing row means today — so this migration changes no behaviour until
someone sets a value. `staging` can therefore point at a different model to `production`
and be compared before switching.

Revision ID: 311g_ai_prompt_label_model
Revises: 311f_spec_registry_excluded_values
"""
import sqlalchemy as sa
from alembic import op

revision = "311g_ai_prompt_label_model"
down_revision = "311f_spec_registry_excluded_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_prompt_labels", sa.Column("provider", sa.String(64), nullable=True))
    op.add_column("ai_prompt_labels", sa.Column("model", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_prompt_labels", "model")
    op.drop_column("ai_prompt_labels", "provider")
