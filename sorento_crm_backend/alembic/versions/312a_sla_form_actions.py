"""Form SLA Undo: deferred actions table, per-stage grace, global grace default.

A form-SLA action clicked in the app no longer fires immediately when its stage
configures a grace window: it parks in `sla_form_actions` and runs when the window
closes. Undoing inside the window deletes the parked row, so nothing was written, no
email left and no WhatsApp reached the contact - which is the point, because a Respond.io
message to a customer cannot be unsent.

`grace_seconds` defaults to NULL per stage and 0 globally, so applying this migration
changes no behaviour at all until someone turns a stage on.

Revision ID: 312a_sla_form_actions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "312a_sla_form_actions"
down_revision = "311m_spec_tables_uuid_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sla_form_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("action_key", sa.String(length=64), nullable=False),
        sa.Column("source_entity_type", sa.String(length=50), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "prior_state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("requested_by_id", sa.String(), nullable=True),
        sa.Column(
            "channel", sa.String(length=16), nullable=False, server_default="immediate"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("commit_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("resolution_reason", sa.String(length=32), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("prior_tracking_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("spawned_tracking_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("undone_by_id", sa.String(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("undo_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["undone_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index(
        "ix_sla_form_actions_sweep", "sla_form_actions", ["status", "commit_at"]
    )
    op.create_index(
        "ix_sla_form_actions_last",
        "sla_form_actions",
        ["source_entity_type", "source_entity_id", "committed_at"],
    )
    # One pending action per form, enforced by the database. The service checks too,
    # but two concurrent clicks can both pass a service-level check.
    op.create_index(
        "uq_sla_form_actions_one_pending",
        "sla_form_actions",
        ["source_entity_type", "source_entity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Per-stage override. NULL means "use the global default", which is how a stage
    # stays on today's behaviour without carrying an explicit 0.
    op.add_column(
        "form_sla_configs", sa.Column("grace_seconds", sa.Integer(), nullable=True)
    )
    # Global default. 0 = no deferral anywhere, so this migration is inert on deploy.
    op.add_column(
        "system_settings",
        sa.Column(
            "form_sla_grace_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "form_sla_grace_seconds")
    op.drop_column("form_sla_configs", "grace_seconds")
    op.drop_index("uq_sla_form_actions_one_pending", table_name="sla_form_actions")
    op.drop_index("ix_sla_form_actions_last", table_name="sla_form_actions")
    op.drop_index("ix_sla_form_actions_sweep", table_name="sla_form_actions")
    op.drop_table("sla_form_actions")
