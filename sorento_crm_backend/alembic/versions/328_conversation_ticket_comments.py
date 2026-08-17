"""Internal comments on conversation intervention tickets (UAC AC-L1/L2/L3).

The CRM is the source of truth for comments: Respond.io can create one but has
no read-back endpoint, so nothing in this table can be rebuilt from Respond.

Two scopes share the table:

- a CRM-authored comment carries BOTH ``tracking_id`` and ``respond_contact_id``
  (it was written on one ticket);
- a Respond-ingested comment carries the contact ONLY, because Respond's own
  comments are contact-scoped - they render in every open ticket for that
  contact.

Hence the nullable ``tracking_id`` plus the CHECK that at least one scope is
set. ``respond_comment_id`` is uniquely indexed where present so a replayed
``comment.created`` webhook resolves to the row it already created.

Revision ID: 328_ticket_comments
Revises: 327_chat_history_trgm
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "328_ticket_comments"
down_revision = "327_chat_history_trgm"
branch_labels = None
depends_on = None

TABLE = "conversation_ticket_comments"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tracking_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("conversation_sla_tracking.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "respond_contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "author_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_name", sa.Text(), nullable=True),
        sa.Column("author_respond_user_id", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "mentioned_user_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("source", sa.String(16), nullable=False, server_default="crm"),
        sa.Column("respond_comment_id", sa.Text(), nullable=True),
        sa.Column(
            "respond_mirrored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tracking_id IS NOT NULL OR respond_contact_id IS NOT NULL",
            name="ck_conversation_ticket_comments_scope",
        ),
    )
    op.create_index("ix_conversation_ticket_comments_tracking_id", TABLE, ["tracking_id"])
    op.create_index(
        "ix_conversation_ticket_comments_contact_id", TABLE, ["respond_contact_id"]
    )
    op.create_index("ix_conversation_ticket_comments_created_at", TABLE, ["created_at"])
    op.create_index(
        "uq_conversation_ticket_comments_respond_comment_id",
        TABLE,
        ["respond_comment_id"],
        unique=True,
        postgresql_where=sa.text("respond_comment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_conversation_ticket_comments_respond_comment_id", table_name=TABLE)
    op.drop_index("ix_conversation_ticket_comments_created_at", table_name=TABLE)
    op.drop_index("ix_conversation_ticket_comments_contact_id", table_name=TABLE)
    op.drop_index("ix_conversation_ticket_comments_tracking_id", table_name=TABLE)
    op.drop_table(TABLE)
