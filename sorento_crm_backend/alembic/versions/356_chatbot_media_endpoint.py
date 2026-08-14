"""Chatbot media endpoint: the gate, the ledger, the job, and the settings columns.

Three tables plus sixteen columns on the `system_settings` singleton, per
`documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` section 2.

**There is deliberately no data backfill, and that is the point.** DoD gate item 2
asks that every existing contact start with media access OFF. That is satisfied by
*absence*: `contact_media_limit` has no row for anybody, and the endpoint treats a
missing row as denied. Fail-closed by construction beats a boolean default someone
can flip globally, and it avoids writing one row per contact for a feature almost
none of them will use. There is no system-wide "allow everyone" switch on purpose -
that would recreate, in reverse, the silent three-week gate outage this feature
exists to replace.

Two deliberate choices worth stating because they look like omissions:

* `media_image_degraded_model` ships with **no default**, so it is NULL. A NULL
  degraded model means degradation is impossible and the monthly quota becomes a
  hard refusal. Shipping a second paid model switched on for everyone is not a
  decision this migration gets to make; the operator turns it on from the settings
  page. It also keeps "set this back to nothing" writable, which a defaulted
  column would not be. (Superseded in part by migration 358: the corpus
  measurement named the tier, so 358 SEEDS `gpt-4o-mini` into the row once. It
  is still not a column default, so it stays clearable.)
* `contact_media_usage.media_ordinal` exists and is part of the unique key even
  though it will be 0 for every row we expect. Whether one WhatsApp message
  carrying several images yields one messageId or several cannot be answered from
  this repo. If it turns out to be one, n8n sends an ordinal and nothing needs a
  migration; if it does not, the column stays 0 and the key behaves exactly as
  `(respond_io_id, message_id, modality)`. One integer removes a schema risk.

Revision ID: 356_chatbot_media_endpoint
Revises: 885010d94677
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "356_chatbot_media_endpoint"
down_revision = "885010d94677"
branch_labels = None
depends_on = None


# (column, type, server_default). NULL-defaulted columns are listed with None and
# are the ones where NULL carries meaning rather than "not set yet".
SETTINGS_COLUMNS = [
    ("media_image_monthly_limit", sa.Integer(), "50"),
    ("media_voice_monthly_limit", sa.Integer(), "100"),
    ("media_voice_max_seconds", sa.Integer(), "120"),
    ("media_burst_limit", sa.Integer(), "5"),
    ("media_burst_window_seconds", sa.Integer(), "60"),
    ("media_warn_threshold_percent", sa.Integer(), "80"),
    ("media_image_provider", sa.Text(), None),
    ("media_image_model", sa.Text(), None),
    ("media_image_degraded_model", sa.Text(), None),
    ("media_transcribe_model", sa.Text(), "whisper-1"),
    ("media_language_mode", sa.String(length=16), "pinned"),
    ("media_language_pinned", sa.String(length=16), "en"),
    ("media_language_hints", sa.Text(), "en,ms,zh"),
    ("media_sync_wait_seconds", sa.Integer(), "30"),
    ("media_extraction_timeout_seconds", sa.Integer(), "45"),
    ("media_max_entities", sa.Integer(), "10"),
]


def upgrade() -> None:
    op.create_table(
        "contact_media_limit",
        # A uuid `id` even though `(contact_id, modality)` is the natural key:
        # tests/test_schema_uuid_id_principle.py holds every domain table to a uuid
        # PK, and its allowlist is meant to shrink. The pair keeps its uniqueness
        # as a constraint, which is what the plan's composite PK was buying.
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column(
            "is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("monthly_limit", sa.Integer(), nullable=True),
        sa.Column("max_clip_seconds", sa.Integer(), nullable=True),
        sa.Column("languages", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("warned_period", sa.String(length=7), nullable=True),
        sa.Column("degraded_notified_period", sa.String(length=7), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["respond_contacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contact_id", "modality", name="uq_contact_media_limit_contact_modality"
        ),
    )
    op.create_index(
        "ix_contact_media_limit_contact_id", "contact_media_limit", ["contact_id"]
    )

    op.create_table(
        "contact_media_usage",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("respond_io_id", sa.Text(), nullable=False),
        sa.Column("contact_id", sa.Text(), nullable=True),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column(
            "media_ordinal", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("turn_id", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["respond_contacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "respond_io_id",
            "message_id",
            "modality",
            "media_ordinal",
            name="uq_contact_media_usage_idempotency",
        ),
    )
    op.create_index(
        "ix_contact_media_usage_enforcement",
        "contact_media_usage",
        ["respond_io_id", "modality", "period_key"],
    )
    op.create_index(
        "ix_contact_media_usage_contact_created",
        "contact_media_usage",
        ["contact_id", "created_at"],
    )

    op.create_table(
        "media_extraction_job",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("usage_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="queued"
        ),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("callback_url", sa.Text(), nullable=True),
        sa.Column("callback_headers", postgresql.JSONB(), nullable=True),
        sa.Column("callback_status", sa.String(length=16), nullable=True),
        sa.Column(
            "callback_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("rq_job_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["usage_id"], ["contact_media_usage.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usage_id", name="uq_media_extraction_job_usage_id"),
    )
    op.create_index("ix_media_extraction_job_status", "media_extraction_job", ["status"])
    op.create_index(
        "ix_media_extraction_job_usage_id", "media_extraction_job", ["usage_id"]
    )

    for name, column_type, server_default in SETTINGS_COLUMNS:
        op.add_column(
            "system_settings",
            sa.Column(
                name,
                column_type,
                nullable=server_default is None,
                server_default=server_default,
            ),
        )


def downgrade() -> None:
    for name, _type, _default in reversed(SETTINGS_COLUMNS):
        op.drop_column("system_settings", name)

    op.drop_index("ix_media_extraction_job_usage_id", table_name="media_extraction_job")
    op.drop_index("ix_media_extraction_job_status", table_name="media_extraction_job")
    op.drop_table("media_extraction_job")

    op.drop_index(
        "ix_contact_media_usage_contact_created", table_name="contact_media_usage"
    )
    op.drop_index("ix_contact_media_usage_enforcement", table_name="contact_media_usage")
    op.drop_table("contact_media_usage")

    op.drop_index("ix_contact_media_limit_contact_id", table_name="contact_media_limit")
    op.drop_table("contact_media_limit")
