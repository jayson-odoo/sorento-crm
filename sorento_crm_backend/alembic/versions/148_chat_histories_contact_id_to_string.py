"""Ensure contact_id is string in chat history tables.

Revision ID: 148_chat_histories_contact_id_to_string
Revises: 147_generalize_chat_histories
Create Date: 2026-04-25
"""
from alembic import op


revision = "148_chat_histories_contact_id_to_string"
down_revision = "147_generalize_chat_histories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # For environments that already migrated with numeric contact_id,
    # force contact_id to text in both legacy and generalized tables.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'chat_histories'
                  AND column_name = 'contact_id'
                  AND data_type <> 'character varying'
            ) THEN
                ALTER TABLE chat_histories
                ALTER COLUMN contact_id TYPE VARCHAR(128)
                USING contact_id::text;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'whatsapp_chat_histories'
                  AND column_name = 'contact_id'
                  AND data_type <> 'character varying'
            ) THEN
                ALTER TABLE whatsapp_chat_histories
                ALTER COLUMN contact_id TYPE VARCHAR(128)
                USING contact_id::text;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Revert to bigint where tables exist and values are numeric.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'chat_histories'
                  AND column_name = 'contact_id'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE chat_histories
                ALTER COLUMN contact_id TYPE BIGINT
                USING NULLIF(regexp_replace(contact_id, '[^0-9-]', '', 'g'), '')::bigint;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'whatsapp_chat_histories'
                  AND column_name = 'contact_id'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE whatsapp_chat_histories
                ALTER COLUMN contact_id TYPE BIGINT
                USING NULLIF(regexp_replace(contact_id, '[^0-9-]', '', 'g'), '')::bigint;
            END IF;
        END $$;
        """
    )
