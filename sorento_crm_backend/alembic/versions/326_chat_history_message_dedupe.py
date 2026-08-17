"""One chat_histories row per Respond messageId, per contact (UAC AC-J5).

A drawer send now fires BOTH the direct respond-send-user webhook lane and
Respond's own outgoing-message trigger, and both lanes mirror the message back
through POST /api/v1/external/chat-history/messages. Without a uniqueness rule
that is two rows for one WhatsApp message, and the ingest cannot tell a mirror
from a genuinely new message.

WHY THE INDEX IS SCOPED TO NEW ROWS (created_at >= the cutover instant):

- Legacy rows carry a message_id that predates this contract, and at least one
  environment holds a pair sharing (contact_id, message_id) across the two
  traffic directions (hand-seeded while the quote-reply feature was built). A
  plain unique index would abort the migration there, and deleting historical
  chat rows to install an index is not a trade anyone should make.
- The cutover instant is a fixed literal, not a value read from the database, so
  the predicate is identical in every environment - which is what lets the
  ingest's ON CONFLICT clause infer this exact index (Postgres requires the
  inference predicate to imply the index predicate).
- Nothing is lost: deduplication only has to hold for traffic that arrives
  through the two-lane mirror, which starts with this deploy.

Revision ID: 326_chat_history_dedupe
Revises: 325_respond_contact_outbound
Create Date: 2026-08-14
"""
from alembic import op
from sqlalchemy import text


revision = "326_chat_history_dedupe"
down_revision = "325_respond_contact_outbound"
branch_labels = None
depends_on = None

# Keep in lockstep with app/models/chat_history.py and the ingest's ON CONFLICT
# clause in app/api/v1/external/chat_history.py. Changing it in one place only
# silently disables the dedupe (the arbiter index stops being inferable).
DEDUPE_CUTOVER = "2026-08-14 00:00:00"
INDEX_NAME = "uq_chat_histories_contact_message_dedupe"


def upgrade() -> None:
    conn = op.get_bind()
    in_window_duplicates = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(c - 1), 0)
            FROM (
                SELECT COUNT(*) AS c
                FROM chat_histories
                WHERE message_id IS NOT NULL
                  AND created_at >= TIMESTAMP :cutover
                GROUP BY contact_id, message_id
                HAVING COUNT(*) > 1
            ) t
            """.replace(":cutover", f"'{DEDUPE_CUTOVER}'")
        )
    ).scalar()
    if in_window_duplicates:
        # These are one WhatsApp message stored twice: same contact, same
        # Respond messageId. The pair renders as two identical bubbles and is
        # exactly what the index below exists to stop, so the redundant copies
        # go and the OLDEST row of each set stays (lowest id: the one every
        # existing reference and every reader already saw first).
        #
        # This runs in the migration's transaction, immediately before the
        # index, so a writer cannot slip a fresh duplicate in between: the
        # CREATE UNIQUE INDEX takes a lock that blocks writes to the table.
        #
        # Found the hard way: prod aborted this migration with
        # "could not create unique index ... Key (contact_id, message_id)=... is
        # duplicated", 20 rows, while every other environment had none. Warning
        # and continuing left the deploy dead - the migration has to make the
        # precondition true, not just report that it is false.
        print(
            f"[{revision}] {in_window_duplicates} duplicate chat_histories row(s) "
            f"at or after {DEDUPE_CUTOVER}; deleting the redundant copies, "
            f"keeping the oldest row of each (contact_id, message_id)."
        )
        deleted = conn.execute(
            text(
                f"""
                DELETE FROM chat_histories older
                USING chat_histories keeper
                WHERE older.contact_id = keeper.contact_id
                  AND older.message_id = keeper.message_id
                  AND older.message_id IS NOT NULL
                  AND older.created_at >= TIMESTAMP '{DEDUPE_CUTOVER}'
                  AND keeper.created_at >= TIMESTAMP '{DEDUPE_CUTOVER}'
                  AND older.id > keeper.id
                """
            )
        ).rowcount
        print(f"[{revision}] deleted {deleted} redundant chat_histories row(s).")

    op.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
            ON chat_histories (contact_id, message_id)
            WHERE message_id IS NOT NULL
              AND created_at >= TIMESTAMP '{DEDUPE_CUTOVER}'
            """
        )
    )


def downgrade() -> None:
    op.execute(text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))
