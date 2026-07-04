"""ai assistant per-turn trace (M2): ai_assistant_traces + ai_assistant_spans

Creates the two-table trace store (root trace + span tree), adds
``ai_assistant_messages.trace_id`` FK, and adds the three ``system_settings``
retention/payload-cap columns. Field names are OpenTelemetry GenAI-semconv-shaped
so a future OTLP export is a straight field-map. See
``docs/plans/PLAN-ai-assistant-node-trace.md`` §3/§9.

Revision ID: 259_ai_assistant_trace
Revises: 258_ai_prompt_registry
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "259_ai_assistant_trace"
down_revision = "258_ai_prompt_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "ai_assistant_traces" not in existing:
        op.create_table(
            "ai_assistant_traces",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("total_tokens_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_tokens_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_cost", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
            sa.Column("flagged", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("env", sa.String(length=32), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("span_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["ai_assistant_conversations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_ai_assistant_traces_message_id", "ai_assistant_traces", ["message_id"])
        op.create_index("ix_ai_assistant_traces_conversation_id", "ai_assistant_traces", ["conversation_id"])
        op.create_index("ix_ai_assistant_traces_status_created_at", "ai_assistant_traces", ["status", "created_at"])
        op.create_index("ix_ai_assistant_traces_created_at", "ai_assistant_traces", ["created_at"])

    if "ai_assistant_spans" not in existing:
        op.create_table(
            "ai_assistant_spans",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("parent_id", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("dotted_order", sa.Text(), nullable=False, server_default=""),
            sa.Column("span_kind", sa.String(length=16), nullable=False),
            sa.Column("name", sa.Text(), nullable=False, server_default=""),
            sa.Column("input_json", postgresql.JSONB(), nullable=True),
            sa.Column("output_json", postgresql.JSONB(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("start_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("end_time", sa.DateTime(timezone=False), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("request_model", sa.String(length=128), nullable=True),
            sa.Column("response_model", sa.String(length=128), nullable=True),
            sa.Column("finish_reason", sa.String(length=64), nullable=True),
            sa.Column("invocation_params", postgresql.JSONB(), nullable=True),
            sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("prompt_name", sa.String(length=64), nullable=True),
            sa.Column("prompt_version", sa.Integer(), nullable=True),
            sa.Column("tool_name", sa.String(length=128), nullable=True),
            sa.Column("tool_call_id", sa.String(length=128), nullable=True),
            sa.Column("tool_args", postgresql.JSONB(), nullable=True),
            sa.Column("tool_result", postgresql.JSONB(), nullable=True),
            sa.Column("query", sa.Text(), nullable=True),
            sa.Column("documents", postgresql.JSONB(), nullable=True),
            sa.Column("top_k", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["trace_id"], ["ai_assistant_traces.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_ai_assistant_spans_trace_id", "ai_assistant_spans", ["trace_id"])
        op.create_index("ix_ai_assistant_spans_trace_dotted", "ai_assistant_spans", ["trace_id", "dotted_order"])

    # ai_assistant_messages.trace_id FK (SET NULL). FK added separately so the
    # column exists before the traces table on fresh installs is irrelevant —
    # traces table is created above first.
    msg_cols = {c["name"] for c in insp.get_columns("ai_assistant_messages")}
    if "trace_id" not in msg_cols:
        op.add_column(
            "ai_assistant_messages",
            sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_ai_assistant_messages_trace_id",
            "ai_assistant_messages",
            "ai_assistant_traces",
            ["trace_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # system_settings retention + payload-cap columns (singleton table).
    ss_cols = {c["name"] for c in insp.get_columns("system_settings")}
    if "ai_trace_ttl_days" not in ss_cols:
        op.add_column("system_settings", sa.Column("ai_trace_ttl_days", sa.Integer(), nullable=False, server_default="30"))
    if "ai_trace_error_ttl_days" not in ss_cols:
        op.add_column("system_settings", sa.Column("ai_trace_error_ttl_days", sa.Integer(), nullable=False, server_default="90"))
    if "ai_trace_max_payload_bytes" not in ss_cols:
        op.add_column("system_settings", sa.Column("ai_trace_max_payload_bytes", sa.Integer(), nullable=False, server_default="16384"))
    # M2.5 role-split toggle (default off — behavioral change, opt-in).
    if "ai_assistant_role_split_enabled" not in ss_cols:
        op.add_column("system_settings", sa.Column("ai_assistant_role_split_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    ss_cols = {c["name"] for c in insp.get_columns("system_settings")}
    for col in (
        "ai_assistant_role_split_enabled",
        "ai_trace_max_payload_bytes",
        "ai_trace_error_ttl_days",
        "ai_trace_ttl_days",
    ):
        if col in ss_cols:
            op.drop_column("system_settings", col)

    msg_cols = {c["name"] for c in insp.get_columns("ai_assistant_messages")}
    if "trace_id" in msg_cols:
        op.drop_constraint("fk_ai_assistant_messages_trace_id", "ai_assistant_messages", type_="foreignkey")
        op.drop_column("ai_assistant_messages", "trace_id")

    existing = set(insp.get_table_names())
    if "ai_assistant_spans" in existing:
        op.drop_table("ai_assistant_spans")
    if "ai_assistant_traces" in existing:
        op.drop_table("ai_assistant_traces")
