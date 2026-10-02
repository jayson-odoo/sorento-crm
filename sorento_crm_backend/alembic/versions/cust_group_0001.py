"""CUSTOMER-GROUP: `customer_groups` and `customers.customer_group_id`, seeded once.

Revision ID: cust_group_0001
Revises: picker_no_cap_0001
Create Date: 2026-10-02

A group is one company's customer made of several ledgers. The chatbot used to join ledgers
by the name rule (`ledger_family_key`); the group is the office's own say-so and the rule is
the fallback for a ledger with no group.

The seed runs ONCE, here: per (company, `ledger_family_key`) family with 2+ rows and at
least one numbered row (`account_level` set), one group named by `ledger_family_label` of the
member with the lowest (level, code), and every member pointed at it. A family where any row
already carries a group is skipped whole, so a re-run is a no-op and an office edit is never
overwritten. A name clash inside a company reuses the existing group.
Additive: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, the FK only when absent.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "cust_group_0001"
down_revision = "picker_no_cap_0001"
branch_labels = None
depends_on = None


def plan_groups(rows) -> list[tuple[str, str, list[str]]]:
    """The groups the seed creates: `[(company_id, group name, [customer ids])]`.

    `rows` are `(id, company_id, customer_code, customer_name, account_level,
    customer_group_id)`. Pure (no DB), so `scripts/customer_groups_seed_sql.py` can print
    the same plan as SQL."""
    from app.services.ledger_family import ledger_family_key, shared_bracket_label

    families: dict[tuple[str, str], list] = {}
    for row in rows:
        _id, company_id, _code, name, _level, _group = row
        key = ledger_family_key(name) if name else ""
        if key:
            families.setdefault((str(company_id), key), []).append(row)

    plan: list[tuple[str, str, list[str]]] = []
    for (company_id, _key), members in families.items():
        if len(members) < 2 or all(m[4] is None for m in members):
            continue
        if any(m[5] is not None for m in members):
            continue
        lead = min(members, key=lambda m: (m[4] if m[4] is not None else 1 << 30, m[2]))
        plan.append((company_id, shared_bracket_label([lead[3]] + [m[3] for m in members]), [str(m[0]) for m in members]))
    return plan


def seed(connection) -> int:
    """Create the groups and point the members at them. Returns groups created."""
    rows = connection.execute(
        sa.text(
            "SELECT id, company_id, customer_code, customer_name, account_level, customer_group_id "
            "FROM customers WHERE customer_name IS NOT NULL"
        )
    ).fetchall()
    created = 0
    for company_id, name, member_ids in plan_groups(rows):
        group_id = connection.execute(
            sa.text(
                "SELECT id FROM customer_groups WHERE company_id = :c AND lower(name) = lower(:n)"
            ),
            {"c": company_id, "n": name},
        ).scalar()
        if group_id is None:
            group_id = str(uuid.uuid4())
            connection.execute(
                sa.text(
                    "INSERT INTO customer_groups (id, company_id, name, created_at, updated_at) "
                    "VALUES (:i, :c, :n, now(), now())"
                ),
                {"i": group_id, "c": company_id, "n": name},
            )
            created += 1
        connection.execute(
            sa.text(
                "UPDATE customers SET customer_group_id = :g "
                "WHERE id = ANY(CAST(:ids AS uuid[])) AND customer_group_id IS NULL"
            ),
            {"g": group_id, "ids": member_ids},
        )
    return created


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_groups (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id),
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_groups_company_id ON customer_groups (company_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_groups_company_name_lower "
        "ON customer_groups (company_id, lower(name))"
    )
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS customer_group_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_customers_customer_group_id'
            ) THEN
                ALTER TABLE customers
                    ADD CONSTRAINT fk_customers_customer_group_id
                    FOREIGN KEY (customer_group_id) REFERENCES customer_groups(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_customer_group_id ON customers (customer_group_id)"
    )
    seed(op.get_bind())


def downgrade() -> None:
    op.execute("ALTER TABLE customers DROP CONSTRAINT IF EXISTS fk_customers_customer_group_id")
    op.execute("DROP INDEX IF EXISTS ix_customers_customer_group_id")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS customer_group_id")
    op.execute("DROP TABLE IF EXISTS customer_groups")
