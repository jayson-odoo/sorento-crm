"""R23: one link per send, carried by BOTH channel rows.

Revision ID: 434_notice_shared_token
Revises: 432_supplier_code_alias_dismiss
Create Date: 2026-08-27

Migration 428 gave `supplier_notices` a `public_token` and made it unique per ROW, because
the token was minted on the email row alone. The captain's ruling (27 Aug): "email and chat
need to both have link" - Ms Tee pastes the link into WeChat off the chat row as often as the
supplier clicks it in the email, and they are two ways to deliver ONE credential for one ask,
not two credentials.

So the token is now minted once per send and written to both rows, and the index widens to
(public_token, channel). It keeps the same NAME, so the model and the database agree whichever
way the table was created, and it keeps the guarantee the index was actually there for: a
token can never be reused by a second send. Still one live link per supplier - the sender
retires every live token before it writes the new rows.

Backfill: the chat row of a send whose link is STILL LIVE takes its sibling's token, matched
on the storage key (one random key per send, so it names exactly one send). Without it, the
request already sitting in a supplier's inbox would show "Copy link" on one row and nothing on
the other until somebody resent it. Sends whose link has already run out are left alone -
handing an expired credential to a second row is not a repair.
"""
from alembic import op

revision = "434_notice_shared_token"
down_revision = "432_supplier_code_alias_dismiss"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_supplier_notices_public_token", table_name="supplier_notices")
    op.create_index(
        "uq_supplier_notices_public_token",
        "supplier_notices",
        ["public_token", "channel"],
        unique=True,
    )

    op.execute(
        """
        UPDATE supplier_notices AS c
           SET public_token = e.public_token,
               public_token_expires_at = e.public_token_expires_at
          FROM supplier_notices AS e
         WHERE c.notice_type = 'container_request'
           AND c.channel = 'chat'
           AND c.public_token IS NULL
           AND c.storage_key IS NOT NULL
           AND e.supplier_id = c.supplier_id
           AND e.channel = 'email'
           AND e.storage_key = c.storage_key
           AND e.public_token IS NOT NULL
           AND e.public_token_expires_at > now()
        """
    )


def downgrade() -> None:
    # The shared half goes first, or the narrow unique index cannot be created.
    op.execute(
        """
        UPDATE supplier_notices AS c
           SET public_token = NULL,
               public_token_expires_at = NULL
         WHERE c.channel = 'chat'
           AND c.public_token IS NOT NULL
           AND EXISTS (
                 SELECT 1
                   FROM supplier_notices AS e
                  WHERE e.public_token = c.public_token
                    AND e.channel <> c.channel
               )
        """
    )
    op.drop_index("uq_supplier_notices_public_token", table_name="supplier_notices")
    op.create_index(
        "uq_supplier_notices_public_token",
        "supplier_notices",
        ["public_token"],
        unique=True,
    )
