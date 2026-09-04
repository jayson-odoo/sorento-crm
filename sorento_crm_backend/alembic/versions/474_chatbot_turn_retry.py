"""Turn trace admin API: retry bookkeeping, per-attempt uniqueness, manage slug.

Three changes, one migration, because the retry path needs all three to work:

1. `chatbot.turns.retry_requested_at`. R4 says a manual retry is the ONLY retry, and the
   turn ROW stays `failed` until the re-injected turn arrives as its own row - so
   "already retried" cannot be read off `status`. Without a column, a double click on the
   trace screen injects the envelope twice and the customer is answered twice.

2. The unique key becomes `(contact_respond_id, message_id, attempt)`. D15's dedup is
   "this respond message was already turned into a turn", and a RETRY of that same
   message is deliberately a second turn - attempt 2. On the old two-column key the
   retried envelope collided with the row it was retrying and the engine returned
   `duplicate: true` instead of running, which made Retry a no-op that looked like a
   success. The engine's duplicate query gains `attempt` to match.

3. `system.chat_history.manage`, registered and granted to **admin ONLY**. `.view` reads
   the trace; `.manage` re-injects a WhatsApp turn at a real customer, which is a
   different thing to hand out, so it is a different slug and a different grant.

   **Not derived from `.view` holders.** That was the first shape of this migration and it
   was wrong: measured on the prod-copy database, `.view` is held by `admin`,
   `integration_n8n` and `integration_foundryx_esb`, so deriving would have handed the
   Retry button to two integration API keys - principals that exist to READ, and whose
   keys travel in n8n workflows. Widening beyond admin is a deliberate act in the roles
   UI, not a side effect of a migration (migration 292's precedent).

4. An index on `(status, created_at)`. `GET /turns/failed-contacts` filters on exactly that
   pair over a table that only grows, and it is the one query on this table that does not
   start from a contact id.

Revision ID: 474_chatbot_turn_retry
Revises: 472_chatbot_turns
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "474_chatbot_turn_retry"
down_revision = "472_chatbot_turns"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_MANAGE = "system.chat_history.manage"
_OLD_UQ = "uq_chatbot_turns_contact_message"
_NEW_UQ = "uq_chatbot_turns_contact_message_attempt"


def upgrade():
    op.add_column(
        "turns",
        sa.Column("retry_requested_at", sa.DateTime(timezone=True), nullable=True),
        schema="chatbot",
    )

    # `GET /turns/failed-contacts` filters `status = 'failed'` over a created_at window and
    # is the only query here that does not start from a contact id.
    op.create_index(
        "ix_chatbot_turns_status_created",
        "turns",
        ["status", "created_at"],
        schema="chatbot",
    )

    op.drop_constraint(_OLD_UQ, "turns", schema="chatbot", type_="unique")
    op.create_unique_constraint(
        _NEW_UQ,
        "turns",
        ["contact_respond_id", "message_id", "attempt"],
        schema="chatbot",
    )

    _register_and_grant()


def _register_and_grant() -> None:
    from app.rbac.permission_registry import sync_permissions

    session = Session(bind=op.get_bind())
    try:
        created = sync_permissions(session)
        logger.info("474: registered %d new permission(s)", created)

        row = session.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _MANAGE}
        ).first()
        if row is None:
            # The route references this slug, so a role that can never hold it means a
            # permanently 403ing Retry button.
            raise RuntimeError(f"474: permission failed to register: {_MANAGE}")
        permission_id = row[0]

        # ADMIN ONLY. See the module docstring: `.view` is held by two integration roles
        # on the production data, and this slug re-injects a message at a real customer.
        role_ids = [
            r[0]
            for r in session.execute(
                sa.text("SELECT id FROM user_roles WHERE slug = 'admin'")
            )
        ]
        if not role_ids:
            logger.warning("474: no admin role found; granted nothing")

        granted = 0
        for role_id in role_ids:
            exists = session.execute(
                sa.text(
                    "SELECT 1 FROM user_role_permissions "
                    "WHERE role_id = :r AND permission_id = :p"
                ),
                {"r": role_id, "p": permission_id},
            ).first()
            if exists:
                continue
            session.execute(
                sa.text(
                    "INSERT INTO user_role_permissions (id, role_id, permission_id) "
                    "VALUES (gen_random_uuid()::text, :r, :p)"
                ),
                {"r": role_id, "p": permission_id},
            )
            granted += 1
        session.commit()
        logger.info("474: granted %s to %d role(s)", _MANAGE, granted)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade():
    """Reversible, and it DELETES retried turns to get there. Read this before running it.

    The two-column unique key cannot be recreated while a retried message has more than
    one row - that is the whole reason the third column exists. So the downgrade drops
    every attempt above the first for each `(contact, message_id)`, which throws away the
    trace of those turns. That is data loss, it is the only way back, and it is why this
    is spelled out rather than left for the operator to discover from a constraint
    violation at 2 a.m.

    On production, prefer rolling FORWARD.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :s)"
        ),
        {"s": _MANAGE},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _MANAGE})

    doomed = bind.execute(
        sa.text(
            "DELETE FROM chatbot.turns t USING ("
            "  SELECT contact_respond_id, message_id, max(attempt) AS keep"
            "  FROM chatbot.turns WHERE message_id IS NOT NULL"
            "  GROUP BY contact_respond_id, message_id HAVING count(*) > 1"
            ") d "
            "WHERE t.contact_respond_id = d.contact_respond_id "
            "  AND t.message_id = d.message_id "
            "  AND t.attempt <> d.keep"
        )
    ).rowcount
    if doomed:
        logger.warning(
            "474 downgrade: deleted %d retried turn row(s) to restore the two-column "
            "unique key; their traces are gone",
            doomed,
        )

    op.drop_constraint(_NEW_UQ, "turns", schema="chatbot", type_="unique")
    op.create_unique_constraint(
        _OLD_UQ, "turns", ["contact_respond_id", "message_id"], schema="chatbot"
    )
    op.drop_index("ix_chatbot_turns_status_created", table_name="turns", schema="chatbot")
    op.drop_column("turns", "retry_requested_at", schema="chatbot")
