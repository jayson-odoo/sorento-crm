"""`system_settings.chatbot_completed_lanes` - which lanes the CRM may FINISH.

The turn engine ships each lane inert. `contracts.CRM_COMPLETED_BRANCH_KINDS` says which
branch kinds the CODE can complete; this column says which it MAY, and a turn is completed
in the CRM only when its `branch_kind` is in BOTH. Default `[]`, so deploying a lane
changes nothing: every turn keeps delegating to n8n exactly as it did, the owner compares
the CRM's answer against n8n's for as long as they want, and then turns one lane on by
adding one string. The n8n Switch output for that lane is deleted after that, not before.

Without this the CRM starts answering the moment it deploys, and the n8n edit has to land
in the same window or the lane runs twice - which is exactly the ordering hazard S4's
cutover note had to describe before this column existed.

JSONB, not a column per lane: thirteen branch kinds, one decision repeated. `[]` and not
NULL so the engine never has to tell "off" from "unset", and NOT NULL so it cannot become
one later.

Revision ID: 476_chatbot_lanes
Revises: 475_chatbot_prompt_slim
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "476_chatbot_lanes"
down_revision = "475_chatbot_prompt_slim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_completed_lanes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_completed_lanes")
