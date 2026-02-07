"""Add work calendar tables and convert timestamps to naive.

Revision ID: 027_calendar_and_timestamp
Revises: 026_due_at_resolution
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "027_calendar_and_timestamp"
down_revision = "026_due_at_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_holidays",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("date", name="uq_public_holidays_date"),
    )
    op.create_index("ix_public_holidays_date", "public_holidays", ["date"])

    op.create_table(
        "work_calendar_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("config_key", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("monday", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tuesday", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("wednesday", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("thursday", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("friday", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("saturday", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sunday", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("config_key", name="uq_work_calendar_config_key"),
    )

    op.execute(
        "INSERT INTO work_calendar_configs (id, config_key, monday, tuesday, wednesday, thursday, friday, saturday, sunday) "
        f"VALUES ('{uuid.uuid4()}', 'default', true, true, true, true, true, false, false) "
        "ON CONFLICT (config_key) DO NOTHING"
    )

    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND data_type='timestamp with time zone'
          LOOP
            EXECUTE format(
              'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp without time zone USING %I AT TIME ZONE ''UTC''',
              r.table_name, r.column_name, r.column_name
            );
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND data_type='timestamp without time zone'
          LOOP
            EXECUTE format(
              'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp with time zone USING %I AT TIME ZONE ''UTC''',
              r.table_name, r.column_name, r.column_name
            );
          END LOOP;
        END $$;
        """
    )

    op.drop_table("work_calendar_configs")
    op.drop_index("ix_public_holidays_date", table_name="public_holidays")
    op.drop_table("public_holidays")
