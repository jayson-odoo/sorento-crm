"""The two owner-operated chatbot switches move out of the environment (AC-810).

`CHATBOT_BUSINESS_LANE_ENABLED` and `CHATBOT_ORDERING_ENABLED` were `app/config.py`
flags, so turning a lane on meant editing an `.env` and restarting the API - a deploy
step for a decision the owner makes and reverses while watching live turns. They become
`system_settings` columns read per turn, toggled on System > Settings > Chatbot beside
`chatbot_completed_lanes`, which is the switch they are read together with.

Additive and default FALSE, which is the same state an unset environment variable meant,
so this deploy changes no behaviour anywhere. `CHATBOT_TURN_ON_WORKER` deliberately stays
in `config.py`: it is a deployment property (does this box run turns on the RQ worker),
not an owner preference, and it is not on the screen.

NO BACKFILL. The values these replace lived in the environment, so there is nothing in the
database to copy from and a migration cannot read the deployed `.env` of the box it runs
on. An install that had either flag on in its environment turns it back on once on the
settings screen; false is the safe landing state either way (the lane delegates to n8n and
`/complete` keeps answering, which is exactly today's default).

Revision ID: 480_chatbot_switches
Revises: 479_chatbot_retry_ws
"""
import sqlalchemy as sa
from alembic import op

revision = "480_chatbot_switches"
down_revision = "479_chatbot_retry_ws"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_business_lane_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_ordering_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_ordering_enabled")
    op.drop_column("system_settings", "chatbot_business_lane_enabled")
