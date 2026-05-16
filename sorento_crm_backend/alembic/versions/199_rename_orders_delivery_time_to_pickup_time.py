"""Rename orders.delivery_time -> orders.pickup_time.

Revision ID: 199_rename_orders_delivery_time_to_pickup_time
Revises: 198_attachments_dirname_unique
Create Date: 2026-05-16
"""
from alembic import op


revision = "199_rename_orders_delivery_time_to_pickup_time"
down_revision = "198_attachments_dirname_unique"
branch_labels = None
depends_on = None


def _rewrite_listing_configs(old_key: str, new_key: str) -> None:
    """Rename a column slug inside user_list_column_configs.config JSONB.

    The JSONB has shape {version, columnOrder: string[], columnVisibility: {col: bool}}.
    Rewrites both columnOrder (array element) and columnVisibility (object key).
    """
    op.execute(
        f"""
        UPDATE user_list_column_configs
        SET config = jsonb_set(
            jsonb_set(
                config,
                '{{columnOrder}}',
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            CASE WHEN elem = to_jsonb('{old_key}'::text)
                                 THEN to_jsonb('{new_key}'::text)
                                 ELSE elem
                            END
                        )
                        FROM jsonb_array_elements(config->'columnOrder') elem
                    ),
                    config->'columnOrder'
                )
            ),
            '{{columnVisibility}}',
            CASE
                WHEN config->'columnVisibility' ? '{old_key}'
                THEN (config->'columnVisibility') - '{old_key}'
                     || jsonb_build_object('{new_key}', config->'columnVisibility'->'{old_key}')
                ELSE COALESCE(config->'columnVisibility', '{{}}'::jsonb)
            END
        )
        WHERE
            config->'columnOrder' @> to_jsonb('{old_key}'::text)
            OR config->'columnVisibility' ? '{old_key}';
        """
    )


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'delivery_time'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'pickup_time'
            ) THEN
                ALTER TABLE orders RENAME COLUMN delivery_time TO pickup_time;
            END IF;
        END$$;
        """
    )

    _rewrite_listing_configs("delivery_time", "pickup_time")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'pickup_time'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'orders' AND column_name = 'delivery_time'
            ) THEN
                ALTER TABLE orders RENAME COLUMN pickup_time TO delivery_time;
            END IF;
        END$$;
        """
    )

    _rewrite_listing_configs("pickup_time", "delivery_time")
