"""Chatbot stock ask v2 S5 fix round (PR #1333, owner ruling 28 Sep 2026): `stock_asks.source`.

A chat console turn now writes its asks rows too, so the owner can hand test the salesman
message and the Asks tab from the console. `source` says which rows are console hand tests
(`console`) and which came from a dealer on WhatsApp (`live`, every existing row).

Its own revision, not an edit of `sa2_0004`: the shared hand-test database already ran
`sa2_0004`. `ADD COLUMN IF NOT EXISTS` / a guarded constraint keep this re-runnable against
a schema `Base.metadata.create_all` already built (`scripts.bootstrap_env`).

Revision ID: sa2_0005_stock_ask_source
Revises: sa2_0004_stock_asks
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "sa2_0005_stock_ask_source"
down_revision = "sa2_0004_stock_asks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE stock_asks "
            "ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'live'"
        )
    )
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_stock_asks_source'
                ) THEN
                    ALTER TABLE stock_asks ADD CONSTRAINT ck_stock_asks_source
                        CHECK (source IN ('live', 'console'));
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE stock_asks DROP CONSTRAINT IF EXISTS ck_stock_asks_source"))
    bind.execute(sa.text("ALTER TABLE stock_asks DROP COLUMN IF EXISTS source"))
