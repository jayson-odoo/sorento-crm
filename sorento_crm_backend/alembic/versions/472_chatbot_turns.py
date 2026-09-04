"""Chatbot module: schema `chatbot`, table `chatbot.turns`, settings flag, RBAC grant.

Four things, one migration, because none of them is usable without the others:

1. `CREATE SCHEMA IF NOT EXISTS chatbot` (D12). The module owns its own namespace so an
   uninstall drops its data and nothing else. `respond_contacts.session_vars` stays in
   `public` - it is shared with ideation and with n8n during the migration window.
2. `chatbot.turns` (AC-003): the turn inbox and its human-readable trace, indexed on
   `(contact_respond_id, status, created_at)` for the trace screen's list and UNIQUE on
   `(contact_respond_id, message_id)` for D15's idempotency. A NULL `message_id` (a
   console turn) does not participate in the unique index, which is Postgres's own
   NULL-distinct behaviour and exactly what is wanted.
3. `system_settings.chatbot_stock_denial_enabled` (R1, default FALSE). The port uses the
   CORRECT `check_stock` vocabulary, which would wake two lanes that have been dead by
   typo since they were written (0/150 live fixtures). Turning them on is a data change
   with a test, not a surprise on deploy.
4. The `integration.chat_turn.submit` slug plus its grant. A permission with no grant path
   silently 403s the feature it was meant to protect, and the failure reads as a broken
   integration rather than a missing grant - migration 298's own lesson, and the reason
   the grant set here is derived the same way: admin plus every `integration_*` role.

Revision ID: 472_chatbot_turns
Revises: 471_merge_tag_size_spo_numbering
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

revision = "472_chatbot_turns"
down_revision = "471_merge_tag_size_spo_numbering"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_SLUG = "integration.chat_turn.submit"


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS chatbot")

    op.create_table(
        "turns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("contact_respond_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=True),
        sa.Column("ingress", sa.String(length=32), nullable=False, server_default="webhook"),
        sa.Column("envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("branch_kind", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("shadow_of", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "contact_respond_id", "message_id", name="uq_chatbot_turns_contact_message"
        ),
        schema="chatbot",
    )
    op.create_index(
        "ix_chatbot_turns_contact_status_created",
        "turns",
        ["contact_respond_id", "status", "created_at"],
        schema="chatbot",
    )

    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_stock_denial_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    _register_and_grant()


def _register_and_grant() -> None:
    from app.rbac.permission_registry import sync_permissions

    session = Session(bind=op.get_bind())
    try:
        created = sync_permissions(session)
        logger.info("472: registered %d new permission(s)", created)

        row = session.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _SLUG}
        ).first()
        if row is None:
            # Fail loudly: the router references this slug, so a role that can never hold
            # it means a permanently 403ing endpoint.
            raise RuntimeError(f"472: permission failed to register: {_SLUG}")
        permission_id = row[0]

        target_roles = [
            r[0]
            for r in session.execute(
                sa.text(
                    "SELECT id FROM user_roles "
                    "WHERE slug = 'admin' OR slug LIKE 'integration\\_%'"
                )
            )
        ]
        if not target_roles:
            logger.warning("472: no admin or integration roles found; granted nothing")

        granted = 0
        for role_id in target_roles:
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
        logger.info("472: granted %s to %d role(s)", _SLUG, granted)
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
        {"s": _SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _SLUG})
    op.drop_column("system_settings", "chatbot_stock_denial_enabled")
    op.drop_index("ix_chatbot_turns_contact_status_created", table_name="turns", schema="chatbot")
    op.drop_table("turns", schema="chatbot")
    # The schema is dropped only when empty: another module could have been installed
    # into it, and CASCADE here would take its tables with it.
    op.execute("DROP SCHEMA IF EXISTS chatbot RESTRICT")
