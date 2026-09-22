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


def seed_chatbot_media_attachment_type(bind) -> None:
    """Insert the `chatbot_media` attachment type row. Idempotent - re-running adds
    nothing (AC-1838), keyed on the stable `code` column, not the `type_name` display
    label a later rename could change (review round note (d): the upgrade guard and
    the downgrade below must key on the same column).

    A module-level function rather than inline SQL in `upgrade()` so the test suite
    can invoke it directly against a `create_all` blank schema - `create_all` builds
    the table but never runs a migration's INSERT (see LESSONS "create_all vs
    migration seed gap") - the same shape 416_stock_visibility_policy's
    `seed_default_row` uses.
    """
    bind.execute(
        text(
            "INSERT INTO attachment_types "
            "(id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
            "SELECT gen_random_uuid(), 'chatbot_media', 'Chatbot Media', "
            "'jpg,jpeg,png,webp,gif,ogg,mp3,m4a,wav', 25, now() AT TIME ZONE 'utc' "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = 'chatbot_media')"
        )
    )


def upgrade() -> None:
    seed_chatbot_media_attachment_type(op.get_bind())


def downgrade() -> None:
    op.execute(text("DELETE FROM attachment_types WHERE code = 'chatbot_media'"))
