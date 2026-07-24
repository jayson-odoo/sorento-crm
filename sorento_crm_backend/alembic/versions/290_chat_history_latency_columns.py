"""Latency + delivery telemetry on chat_histories.

Measures the WhatsApp round trip: user presses send -> our reply is accepted by
Respond, against a p99 SLA.

Both ends of that measurement must sit on **Respond's clock** or the number carries
clock skew between n8n, our server and Respond. So:

- `sent_at` keeps holding what n8n sends (soon: the raw Respond `message.timestamp`).
- `respond_ts` holds the authoritative Respond-side timestamp, resolved out-of-band by
  `GET /v2/message/{id}` for rows that carry a `message_id`.
- `ingest_at` is our own server clock at write time. Not used for the SLA — it exists so
  webhook lag (`ingest_at - respond_ts`) is separable from agent time during triage.

`turn_id` is the n8n `$execution.id`, stamped on both the incoming and the outgoing save,
so a reply pairs to its trigger exactly. Rows without one are proactive sends and are
excluded from the SLA denominator rather than guessed at.

All columns are nullable with no backfill: existing rows genuinely have no Respond
timestamp and no turn, and inventing one would fabricate latency data (OBS-X-02).

Revision ID: 290_chat_history_latency_columns
Revises: 289_scheduled_task_grace_percent
"""
from alembic import op
import sqlalchemy as sa

revision = "290_chat_history_latency_columns"
down_revision = "289_scheduled_task_grace_percent"
branch_labels = None
depends_on = None


_COLUMNS = (
    # Authoritative Respond-side timestamp for this message. NULL until resolved.
    ("respond_ts", sa.DateTime(timezone=False), None),
    # Delivery lifecycle from Respond: sent | delivered | read | failed | not_sent.
    # Tracked and displayed, but deliberately NOT part of the SLA — a recipient with a
    # flat battery would otherwise own the p99 tail.
    ("delivery_status", sa.String(32), None),
    ("delivered_ts", sa.DateTime(timezone=False), None),
    ("read_ts", sa.DateTime(timezone=False), None),
    # Resolver bookkeeping. After N misses the message is treated as never sent.
    ("resolve_attempts", sa.Integer(), "0"),
    # n8n $execution.id — pairs an outgoing reply to the incoming that triggered it.
    ("turn_id", sa.String(64), None),
    # Our server clock at ingest. Diagnostic only (webhook lag), never the SLA clock.
    ("ingest_at", sa.DateTime(timezone=False), None),
)


def _existing_columns(conn) -> set[str]:
    rows = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'chat_histories'"
        )
    )
    return {r[0] for r in rows}


def upgrade():
    conn = op.get_bind()
    present = _existing_columns(conn)

    for name, type_, server_default in _COLUMNS:
        if name in present:
            continue
        op.add_column(
            "chat_histories",
            sa.Column(name, type_, nullable=True, server_default=server_default),
        )

    # Drives the resolver's hot query: unresolved rows that carry a message_id.
    # Partial, so it stays small — resolved rows leave the index entirely.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_histories_unresolved
        ON chat_histories (id)
        WHERE message_id IS NOT NULL AND respond_ts IS NULL
        """
    )
    # Turn pairing: incoming and outgoing rows of one turn.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_histories_turn
        ON chat_histories (turn_id, type, respond_ts)
        WHERE turn_id IS NOT NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_chat_histories_turn")
    op.execute("DROP INDEX IF EXISTS ix_chat_histories_unresolved")
    for name, _type, _default in _COLUMNS:
        op.drop_column("chat_histories", name)
