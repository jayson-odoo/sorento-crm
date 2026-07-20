"""Chat latency SLA settings + the two scheduled tasks that drive it.

Thresholds live in system_settings so they are tunable without a deploy. Defaults:
p99 target 10s, hard ceiling 3x target, no-reply 5min, minimum sample 30 turns.

Two tasks:
- `chat_message_resolver` (60s) fills `respond_ts` from Respond so latency is measured
  on one clock. Inert until n8n starts sending `message_id`.
- `chat_latency_watchdog` (60s) evaluates the rolling p99, the per-turn hard ceiling,
  and unanswered turns.

Revision ID: 291_chat_latency_settings_and_tasks
Revises: 290_chat_history_latency_columns
"""
from alembic import op
import sqlalchemy as sa

revision = "291_chat_latency_settings_and_tasks"
down_revision = "290_chat_history_latency_columns"
branch_labels = None
depends_on = None


_SETTINGS = (
    ("chat_latency_p99_target_seconds", "10"),
    ("chat_latency_ceiling_multiplier", "3"),
    ("chat_latency_no_reply_minutes", "5"),
    ("chat_latency_min_sample", "30"),
)

_TASKS = (
    (
        "chat_message_resolver",
        "Chat message timestamp resolver",
        "Every minute: resolves the authoritative Respond-side timestamp and delivery "
        "status for chat messages carrying a message_id, so WhatsApp round-trip latency "
        "is measured on Respond's clock rather than n8n's. A message Respond has no "
        "record of after repeated attempts is marked not_sent.",
        "seconds",
        60,
    ),
    (
        "chat_latency_watchdog",
        "Chat latency watchdog",
        "Every minute: evaluates the WhatsApp round-trip p99 against its target, flags "
        "individual turns past the hard ceiling, and reports incoming messages left "
        "unanswered. De-duped via health_alert_state.",
        "seconds",
        60,
    ),
)


def upgrade():
    conn = op.get_bind()

    present = {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'system_settings'"
            )
        )
    }
    for name, default in _SETTINGS:
        if name not in present:
            op.add_column(
                "system_settings",
                sa.Column(name, sa.Integer(), nullable=False, server_default=default),
            )

    # Seeded idempotently: `key` is unique, and re-running must not raise.
    for key, name, description, unit, value in _TASKS:
        conn.execute(
            sa.text(
                """
                INSERT INTO scheduled_tasks
                    (id, key, name, description, enabled, interval_unit, interval_value, timezone)
                VALUES
                    (gen_random_uuid(), :key, :name, :description, true, :unit, :value, 'UTC')
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "name": name, "description": description, "unit": unit, "value": value},
        )


def downgrade():
    conn = op.get_bind()
    for key, *_ in _TASKS:
        conn.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = :key"), {"key": key})
    for name, _default in _SETTINGS:
        op.drop_column("system_settings", name)
