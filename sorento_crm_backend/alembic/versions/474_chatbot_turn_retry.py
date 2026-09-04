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

3. `system.chat_history.manage`, registered and granted to admin. `.view` reads the
   trace; `.manage` re-injects a WhatsApp turn at the customer, which is a different
   thing to hand out, so it is a different slug. A slug with no grant path is a
   permanently 403ing feature (migration 298's lesson), hence the grant here.

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

        # Every role that already holds `.view` is looking at this screen; `.manage` is
        # the button on it. Derived rather than typed out, so an install with a different
        # role set gets its own right answer instead of this repo's production data.
        role_ids = [
            r[0]
            for r in session.execute(
                sa.text(
                    "SELECT DISTINCT urp.role_id FROM user_role_permissions urp "
                    "JOIN user_permissions p ON p.id = urp.permission_id "
                    "WHERE p.slug = 'system.chat_history.view' "
                    "UNION "
                    "SELECT id FROM user_roles WHERE slug = 'admin'"
                )
            )
        ]
        if not role_ids:
            logger.warning("474: no admin or chat-history-view roles found; granted nothing")

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
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :s)"
        ),
        {"s": _MANAGE},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _MANAGE})
    op.drop_constraint(_NEW_UQ, "turns", schema="chatbot", type_="unique")
    op.create_unique_constraint(
        _OLD_UQ, "turns", ["contact_respond_id", "message_id"], schema="chatbot"
    )
    op.drop_column("turns", "retry_requested_at", schema="chatbot")
