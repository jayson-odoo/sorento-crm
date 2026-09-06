"""S8a: the chatbot retry ingress moves from the environment onto the workspace row.

Two nullable columns on `respond_workspaces`, the same shape the ideation intake pair
already has there: the URL in plain text, the key Fernet-encrypted
(`chatbot_retry_ingress_key_ciphertext`, read through `app/utils/field_encryption.py`).

NO BACKFILL, and that is the correct answer rather than an omission. The values these
replace (`CHATBOT_RETRY_INGRESS_URL` / `_KEY`) were environment variables, so there is
nothing in the database to copy from, and a migration cannot read the deployed `.env` of
the box it will run on. NULL is also the SAFE landing state: with no URL the retry
endpoint answers 409 `retry_unavailable` and makes no outbound call, so an install that
has not yet had the value entered cannot inject anything anywhere. The operator enters it
once on System > Respond Workspaces after this deploys; until then Retry is off, which is
exactly what an unset environment variable used to mean.

Revision ID: 479_chatbot_retry_ws
Revises: 478_chatbot_s3_copy
"""
import sqlalchemy as sa
from alembic import op

revision = "479_chatbot_retry_ws"
down_revision = "478_chatbot_s3_copy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "respond_workspaces",
        sa.Column("chatbot_retry_ingress_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "respond_workspaces",
        sa.Column("chatbot_retry_ingress_key_ciphertext", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("respond_workspaces", "chatbot_retry_ingress_key_ciphertext")
    op.drop_column("respond_workspaces", "chatbot_retry_ingress_url")
