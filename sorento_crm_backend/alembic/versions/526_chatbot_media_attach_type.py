"""Seed attachment type for chatbot media uploads (code=chatbot_media).

PLAN-chatbot-media-into-turn.md S4 (AC-1833 to AC-1838): the image/voice bytes a
media turn stores go through `attachments` like any other upload, under their own
type so they never share a quota with resource/product attachments.

Revision ID: 526_chatbot_media_attach_type
Revises: 525_committed_v_orderback
Create Date: 2026-09-22

"""
from alembic import op
from sqlalchemy import text


revision = "526_chatbot_media_attach_type"
down_revision = "525_committed_v_orderback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent on re-run (AC-1838): insert only when no row of this CODE exists
    # yet - the stable identifier, not the `type_name` display label a later
    # rename could change (review round note (d): the upgrade guard and the
    # downgrade below must key on the same column).
    op.execute(
        text(
            "INSERT INTO attachment_types "
            "(id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
            "SELECT gen_random_uuid(), 'chatbot_media', 'Chatbot Media', "
            "'jpg,jpeg,png,webp,gif,ogg,mp3,m4a,wav', 25, now() AT TIME ZONE 'utc' "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = 'chatbot_media')"
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM attachment_types WHERE code = 'chatbot_media'"))
