"""Sign-in background: the photograph an admin puts behind the sign-in card.

Two columns on `system_settings`, mirroring `users.avatar` / `users.avatar_storage_provider`:

- `signin_background` - the stable, NON-signed CDN URL the upload returns. A signed URL would
  put an expiry into the database and the row would silently rot.
- `signin_background_storage_provider` - which backend holds the bytes ('s3' or 'r2'), so a read
  asks that one for a fresh signed URL rather than guessing from the hostname.

Both nullable with no default and no backfill, deliberately: NULL means "no admin has uploaded
one", and the sign-in page then draws its designed default wash, which is a finished screen
rather than a missing image. There is nothing an existing row could be backfilled TO.

Revision ID: 445_signin_background
Revises: 444_notify_email_on_mention
"""
from alembic import op
import sqlalchemy as sa

revision = "445_signin_background"
down_revision = "444_notify_email_on_mention"
branch_labels = None
depends_on = None

TABLE = "system_settings"


def _columns() -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = current_schema()"
            ),
            {"t": TABLE},
        )
    }


def upgrade() -> None:
    existing = _columns()
    if "signin_background" not in existing:
        op.add_column(TABLE, sa.Column("signin_background", sa.String(), nullable=True))
    if "signin_background_storage_provider" not in existing:
        op.add_column(
            TABLE,
            sa.Column("signin_background_storage_provider", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    existing = _columns()
    if "signin_background_storage_provider" in existing:
        op.drop_column(TABLE, "signin_background_storage_provider")
    if "signin_background" in existing:
        op.drop_column(TABLE, "signin_background")
