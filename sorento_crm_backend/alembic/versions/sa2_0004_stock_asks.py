"""Chatbot stock ask v2 S5 (PLAN-chatbot-stock-ask-v2-24sep.md, R9) - the asks record.

One `stock_asks` row per stock ask the chatbot answered for an "Availability only" contact.
Exactly R9's fields; `customer_id` nullable (R8 "record the ask": a contact with no
resolvable customer still gets a row). Deleting a customer removes its asks (AC-SA512).

`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` keep this re-runnable against a
schema `Base.metadata.create_all` already built (`scripts.bootstrap_env`).

Revision ID: sa2_0004_stock_asks
Revises: sales_agent_aliases_r7
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "sa2_0004_stock_asks"
down_revision = "sales_agent_aliases_r7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS stock_asks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id),
                customer_id UUID NULL REFERENCES customers(id) ON DELETE CASCADE,
                contact_id TEXT NULL REFERENCES respond_contacts(id) ON DELETE SET NULL,
                product_id UUID NULL REFERENCES products(id) ON DELETE SET NULL,
                product_code VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL,
                branch VARCHAR(20) NOT NULL,
                answer_summary TEXT NOT NULL,
                notified_agent BOOLEAN NOT NULL DEFAULT false,
                notify_skip_reason VARCHAR(80) NULL,
                state VARCHAR(10) NOT NULL DEFAULT 'open',
                note TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now(),
                CONSTRAINT ck_stock_asks_branch
                    CHECK (branch IN ('too_big', 'in_stock', 'incoming', 'no_incoming')),
                CONSTRAINT ck_stock_asks_state CHECK (state IN ('open', 'done'))
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_stock_asks_customer_created "
            "ON stock_asks (customer_id, created_at DESC)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_stock_asks_company_id ON stock_asks (company_id)"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DROP TABLE IF EXISTS stock_asks"))
