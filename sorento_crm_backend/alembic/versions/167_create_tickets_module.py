"""Create tickets module tables.

Adds ``tickets`` (with full SLA-tracking + response/resolution payload
columns mirroring ConversationSLATracking), ``ticket_watchers`` (CC list),
and ``ticket_respond_contact_links`` (Respond.io contacts the Messages tab
loads conversations for). Models live in ``app/models/tickets.py``.

Status workflow: ``draft -> submitted -> assigned -> responded -> resolved``.

Revision ID: 167_create_tickets_module
Revises: 166_create_activities_module
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "167_create_tickets_module"
down_revision = "166_create_activities_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("ticket_number", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
        sa.Column(
            "category",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'question'"),
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("raised_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=False), nullable=True),
        # Response payload (rich text stored on the ticket itself).
        sa.Column("response_html", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("responded_by", postgresql.UUID(as_uuid=False), nullable=True),
        # Resolution payload.
        sa.Column("resolution_html", sa.Text(), nullable=True),
        sa.Column("resolution_text", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=False), nullable=True),
        # SLA timestamps + computed durations (numeric hours, 2dp).
        sa.Column("submitted_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sla_response_due_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sla_resolution_due_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("response_time_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("resolution_time_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("ticket_number", name="uq_tickets_ticket_number"),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_assigned_to", "tickets", ["assigned_to"])
    op.create_index("ix_tickets_raised_by", "tickets", ["raised_by"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_due_date", "tickets", ["due_date"])
    op.create_index(
        "ix_tickets_sla_response_due_at",
        "tickets",
        ["sla_response_due_at"],
    )

    op.create_table(
        "ticket_watchers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("added_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.UniqueConstraint("ticket_id", "user_id", name="uq_ticket_watcher_unique"),
    )
    op.create_index("ix_ticket_watchers_ticket", "ticket_watchers", ["ticket_id"])
    op.create_index("ix_ticket_watchers_user", "ticket_watchers", ["user_id"])

    op.create_table(
        "ticket_respond_contact_links",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("respond_contact_id", sa.Text(), nullable=False),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.UniqueConstraint(
            "ticket_id",
            "respond_contact_id",
            name="uq_ticket_respond_contact",
        ),
    )
    op.create_index(
        "ix_ticket_respond_contacts_ticket",
        "ticket_respond_contact_links",
        ["ticket_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticket_respond_contacts_ticket",
        table_name="ticket_respond_contact_links",
    )
    op.drop_table("ticket_respond_contact_links")

    op.drop_index("ix_ticket_watchers_user", table_name="ticket_watchers")
    op.drop_index("ix_ticket_watchers_ticket", table_name="ticket_watchers")
    op.drop_table("ticket_watchers")

    op.drop_index("ix_tickets_sla_response_due_at", table_name="tickets")
    op.drop_index("ix_tickets_due_date", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_raised_by", table_name="tickets")
    op.drop_index("ix_tickets_assigned_to", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_table("tickets")
