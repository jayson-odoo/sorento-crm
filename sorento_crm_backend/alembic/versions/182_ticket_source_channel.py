"""Ticket source channel + polymorphic raised_by.

Adds source_channel/raised_by_kind/source_conversation_id/source_message_id/
source_space_id columns to ``tickets`` and makes ``raised_by`` nullable so a
ticket raised by a Respond.io contact (no system user) is first-class. Existing
rows are backfilled with ``source_channel='manual'`` and ``raised_by_kind='user'``.

``raised_by`` was a UUID FK pointing implicitly at users.id. We widen it to
String(100) (matches the existing ``users.id`` column type used by team_members
elsewhere) and drop the implicit UUID constraint so a respond_contacts.id (text)
can also live there. The discriminator column ``raised_by_kind`` resolves which
table to look up.

Revision ID: 182_ticket_source_channel
Revises: 181_drop_legacy_respond_contact_unique_index
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "182_ticket_source_channel"
down_revision = "181_drop_legacy_respond_contact_unique_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "source_channel",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "raised_by_kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.add_column("tickets", sa.Column("source_conversation_id", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("source_message_id", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("source_space_id", sa.Text(), nullable=True))

    op.alter_column(
        "tickets",
        "raised_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        type_=sa.String(length=100),
        existing_nullable=False,
        nullable=True,
        postgresql_using="raised_by::text",
    )

    op.create_index("ix_tickets_source_channel", "tickets", ["source_channel"])
    op.create_index(
        "ix_tickets_source_conversation",
        "tickets",
        ["source_channel", "source_conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_source_conversation", table_name="tickets")
    op.drop_index("ix_tickets_source_channel", table_name="tickets")

    op.alter_column(
        "tickets",
        "raised_by",
        existing_type=sa.String(length=100),
        type_=sa.dialects.postgresql.UUID(as_uuid=False),
        existing_nullable=True,
        nullable=False,
        postgresql_using="raised_by::uuid",
    )

    op.drop_column("tickets", "source_space_id")
    op.drop_column("tickets", "source_message_id")
    op.drop_column("tickets", "source_conversation_id")
    op.drop_column("tickets", "raised_by_kind")
    op.drop_column("tickets", "source_channel")
