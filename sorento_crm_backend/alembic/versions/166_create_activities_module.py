"""Create activities & notes module tables.

Adds the three generic per-entity tables that back the shared
ActivitiesNotesPanel: ``activity_events`` (system + user-update feed),
``internal_notes`` (private to author) and ``activity_mentions``
(@-mentions emitted from user updates).

Models live in ``app/models/activities.py``. Tables are entity-agnostic  - 
consumers reference them via ``(entity_type, entity_id)`` pairs.

Revision ID: 166_create_activities_module
Revises: 165_respond_workspace_is_default
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "166_create_activities_module"
down_revision = "165_respond_workspace_is_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'user_update'"),
        ),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("system_template", sa.String(length=100), nullable=True),
        sa.Column("system_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_activity_events_entity",
        "activity_events",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index("ix_activity_events_actor", "activity_events", ["actor_id"])

    op.create_table(
        "internal_notes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_internal_notes_entity_author",
        "internal_notes",
        ["entity_type", "entity_id", "author_id", "created_at"],
    )

    op.create_table(
        "activity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "activity_event_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("activity_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mentioned_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_activity_mentions_user_unseen",
        "activity_mentions",
        ["mentioned_user_id", "seen_at"],
    )
    op.create_index(
        "ix_activity_mentions_event",
        "activity_mentions",
        ["activity_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_mentions_event", table_name="activity_mentions")
    op.drop_index("ix_activity_mentions_user_unseen", table_name="activity_mentions")
    op.drop_table("activity_mentions")

    op.drop_index("ix_internal_notes_entity_author", table_name="internal_notes")
    op.drop_table("internal_notes")

    op.drop_index("ix_activity_events_actor", table_name="activity_events")
    op.drop_index("ix_activity_events_entity", table_name="activity_events")
    op.drop_table("activity_events")
