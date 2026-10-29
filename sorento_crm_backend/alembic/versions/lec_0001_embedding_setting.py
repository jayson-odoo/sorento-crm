"""embedding setting: system_settings carries the lookup embedder (provider, model), the records-search
model and the backfill rate

Upgrade copies the production label of prompt key `chatbot_lookup_embedder` (provider, model) into
provider / model only where they are still NULL, and sets the records-search model to
`text-embedding-3-small` only where it is NULL, so a second run keeps every edit. Downgrade drops the
four columns.

Revision ID: lec_0001_embedding_setting
Revises: idea_capture_fields_0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "lec_0001_embedding_setting"
down_revision = "idea_capture_fields_0001"
branch_labels = None
depends_on = None

COLUMNS = (
    "embedding_provider",
    "embedding_model",
    "embedding_records_search_model",
    "embedding_backfill_rpm",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(32)"))
    bind.execute(sa.text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(128)"))
    bind.execute(
        sa.text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS embedding_records_search_model VARCHAR(128)")
    )
    bind.execute(
        sa.text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS embedding_backfill_rpm INTEGER DEFAULT 20")
    )
    label = bind.execute(
        sa.text(
            "SELECT provider, model FROM ai_prompt_labels "
            "WHERE name = 'chatbot_lookup_embedder' AND label = 'production' "
            "AND model ~ '^[A-Za-z0-9._-]{1,128}$' LIMIT 1"
        )
    ).first()
    if label is not None:
        bind.execute(
            sa.text(
                "UPDATE system_settings SET "
                "embedding_provider = COALESCE(embedding_provider, :p), "
                "embedding_model = COALESCE(embedding_model, :m) "
                "WHERE embedding_provider IS NULL OR embedding_model IS NULL"
            ),
            {"p": label[0] or None, "m": label[1] or None},
        )
    bind.execute(
        sa.text(
            "UPDATE system_settings SET embedding_records_search_model = 'text-embedding-3-small' "
            "WHERE embedding_records_search_model IS NULL"
        )
    )


def downgrade() -> None:
    for col in COLUMNS:
        op.execute(sa.text(f"ALTER TABLE system_settings DROP COLUMN IF EXISTS {col}"))
