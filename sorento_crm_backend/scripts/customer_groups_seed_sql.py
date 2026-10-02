"""Print the customer-group seed as idempotent SQL (CUSTOMER-GROUP).

The same plan `alembic/versions/cust_group_0001.py::seed` applies on a test copy, emitted as
text for a database that must not run the seed in-process. Reads `customers` with ONE
SELECT from DATABASE_URL and writes nothing; the output is what gets reviewed and run.

    venv/bin/python scripts/customer_groups_seed_sql.py > customer-groups-seed.sql

Re-running the output is a no-op: a group is inserted only when its (company, lower(name))
is absent, and members are pointed at it only while they have no group.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parent.parent
BATCH = 200


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _load_plan():
    path = ROOT / "alembic" / "versions" / "cust_group_0001.py"
    spec = importlib.util.spec_from_file_location("cust_group_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.plan_groups


def main() -> None:
    sys.path.insert(0, str(ROOT))
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT id, company_id, customer_code, customer_name, account_level, "
                "customer_group_id FROM customers WHERE customer_name IS NOT NULL"
            )
        ).fetchall()
    plan = sorted(_load_plan()(rows), key=lambda g: (g[0], g[1].lower()))

    print("-- CUSTOMER-GROUP seed: %d groups, %d ledgers. Idempotent." % (len(plan), sum(len(g[2]) for g in plan)))
    print("BEGIN;")
    for company_id, name, member_ids in plan:
        company, label = _quote(company_id), _quote(name)
        print(
            "INSERT INTO customer_groups (id, company_id, name, created_at, updated_at) "
            f"SELECT gen_random_uuid(), {company}::uuid, {label}, now(), now() "
            "WHERE NOT EXISTS (SELECT 1 FROM customer_groups "
            f"WHERE company_id = {company}::uuid AND lower(name) = lower({label}));"
        )
        for i in range(0, len(member_ids), BATCH):
            ids = ", ".join(_quote(m) for m in member_ids[i : i + BATCH])
            print(
                "UPDATE customers SET customer_group_id = (SELECT id FROM customer_groups "
                f"WHERE company_id = {company}::uuid AND lower(name) = lower({label})) "
                f"WHERE id IN ({ids}) AND customer_group_id IS NULL;"
            )
    print("COMMIT;")


if __name__ == "__main__":
    main()
