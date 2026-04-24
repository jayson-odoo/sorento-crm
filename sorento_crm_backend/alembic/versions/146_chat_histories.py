"""Create high-volume WhatsApp chat history table.

Revision ID: 146_whatsapp_chat_histories
Revises: 145_ai_assistant_permissions_sync
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa


revision = "146_whatsapp_chat_histories"
down_revision = "145_ai_assistant_permissions_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_chat_histories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.String(length=128), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_whatsapp_chat_histories_contact_sent_id",
        "whatsapp_chat_histories",
        ["contact_id", sa.text("sent_at DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "ix_whatsapp_chat_histories_phone_sent",
        "whatsapp_chat_histories",
        ["phone_number", sa.text("sent_at DESC")],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "ix_whatsapp_chat_histories_type_sent",
        "whatsapp_chat_histories",
        ["type", sa.text("sent_at DESC")],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_chat_histories_type_sent", table_name="whatsapp_chat_histories")
    op.drop_index("ix_whatsapp_chat_histories_phone_sent", table_name="whatsapp_chat_histories")
    op.drop_index("ix_whatsapp_chat_histories_contact_sent_id", table_name="whatsapp_chat_histories")
    op.drop_table("whatsapp_chat_histories")
