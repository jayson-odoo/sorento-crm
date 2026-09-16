"""Take `system.chatbot_config.manage` back off every role but the two administrator ones.

Chatbot turn re-architecture, security review fix (AC-1561).

`chatbot_rearch_s5` originally derived this grant from every role already holding
`system.chat_history.view`. On the production copy that set is `admin`, `guest`,
`integration_foundryx_esb` and `integration_n8n`: a read-only visitor and two machine
principals could have rewritten the policy the turn engine routes and narrows on. That
migration now grants only `superadmin` and `admin`, which corrects a database migrated
from here on - but not one that already ran the old sweep. This revokes the difference,
so both a fresh and an already-migrated database end in the same place.

Scoped to this one permission slug and nothing else, so a grant an operator made by hand
on some other permission is untouched. Idempotent; a no-op once it has run, and a no-op
on a database that never ran the old sweep.

There is no downgrade: re-granting write access on the engine's policy to `guest` and
two integration principals is not a state this migration will restore. `downgrade()` is
deliberately a no-op.

Revision ID: chatbot_rearch_s6c
Revises: chatbot_rearch_s6b
"""
import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6c"
down_revision = "chatbot_rearch_s6b"
branch_labels = None
depends_on = None

_TARGET = "system.chatbot_config.manage"
# `user_roles.slug`, matching `chatbot_rearch_s5` and `user_service`'s own
# administrator bypass.
_ADMIN_ROLE_SLUGS = ("superadmin", "admin")


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM user_role_permissions grant_row
            USING user_permissions tgt, user_roles r
            WHERE grant_row.permission_id = tgt.id
              AND grant_row.role_id = r.id
              AND tgt.slug = :target
              AND NOT (r.slug = ANY(:role_slugs))
            """
        ),
        {"target": _TARGET, "role_slugs": list(_ADMIN_ROLE_SLUGS)},
    )


def downgrade() -> None:
    """Nothing. See the module docstring: the revoked grants were the defect."""
