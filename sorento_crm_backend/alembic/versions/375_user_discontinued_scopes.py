"""Per-(company, brand) recipient scopes for the product-discontinued notice.

Creates ``user_product_discontinued_scopes`` and backfills it so nobody's notices
change on deploy: every user who already had either discontinued channel toggled
on gets one (NULL company, NULL brand) row, which is "every company, every brand"
and therefore the exact batch they receive today.

The table is deliberately NOT one of the company-owned tables. It is a user
preference, and the scheduled task that fans a batch out runs under a per-task
company scope - an owned table would be filtered by that scope and would silently
drop recipients mid-run.

Trashed users are backfilled too: the row preserves the toggle state they already
had, and the fan-out filters trashed recipients on its own.

Revision ID: 375_user_discontinued_scopes
Revises: 374_merge_proj_media_flyer
Create Date: 2026-08-18
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "375_user_discontinued_scopes"
down_revision = "374_merge_proj_media_flyer"
branch_labels = None
depends_on = None

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_product_discontinued_scopes (
            id uuid PRIMARY KEY,
            user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
            brand_id uuid REFERENCES brands(id) ON DELETE CASCADE,
            created_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_product_discontinued_scopes_user_id "
        "ON user_product_discontinued_scopes (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_product_discontinued_scopes_company_id "
        "ON user_product_discontinued_scopes (company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_product_discontinued_scopes_brand_id "
        "ON user_product_discontinued_scopes (brand_id)"
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_product_discontinued_scopes
        ON user_product_discontinued_scopes (
            user_id,
            coalesce(company_id, '{NIL_UUID}'::uuid),
            coalesce(brand_id, '{NIL_UUID}'::uuid)
        )
        """
    )

    # Backfill. Guarded by NOT EXISTS on the all/all row rather than "insert where
    # the table is empty", so a partial prior run is completed instead of doubled.
    op.execute(
        """
        INSERT INTO user_product_discontinued_scopes (id, user_id, company_id, brand_id, created_at)
        SELECT gen_random_uuid(), u.id, NULL, NULL, now()
        FROM users u
        WHERE (u.notify_email_on_product_discontinued
               OR u.notify_whatsapp_on_product_discontinued)
          AND NOT EXISTS (
              SELECT 1 FROM user_product_discontinued_scopes s
              WHERE s.user_id = u.id
                AND s.company_id IS NULL
                AND s.brand_id IS NULL
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_product_discontinued_scopes")
