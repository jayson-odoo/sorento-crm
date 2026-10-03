"""Print the customer-group seed as idempotent SQL (CUSTOMER-GROUP).

The same plan `alembic/versions/cust_group_0001.py::seed` applies on a test copy, emitted as
text for a database that must not run the seed in-process. Reads `customers` with ONE
SELECT from DATABASE_URL and writes nothing; the output is what gets reviewed and run.

    venv/bin/python scripts/customer_groups_seed_sql.py > customer-groups-seed.sql

    venv/bin/python scripts/customer_groups_seed_sql.py --renames > customer-groups-renames.sql

`--renames` prints, for a group seeded under the OLD naming rule (the label of its lead member,
every bracketed run dropped) whose name is still that, an UPDATE to the shared-bracket name.
A group the office renamed no longer equals the old name and is left alone. Read-only SELECTs.

Never replay a pre-rename seed SQL file after renames: it recreates empty old-named groups.

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


def renames(connection, skipped: list[str] | None = None) -> list[tuple[str, str, str]]:
    """`[(group id, old name, new name)]` for groups still carrying the old seed name; the
    names of groups it cannot rename by that rule go to `skipped`."""
    from app.services.ledger_family import ledger_family_label, shared_bracket_label

    members: dict[str, list] = {}
    names: dict[str, str] = {}
    for gid, gname, cname, level, code in connection.execute(
        sa.text(
            "SELECT g.id, g.name, c.customer_name, c.account_level, c.customer_code "
            "FROM customer_groups g JOIN customers c ON c.customer_group_id = g.id "
            "WHERE c.customer_name IS NOT NULL"
        )
    ).fetchall():
        names[str(gid)] = gname
        members.setdefault(str(gid), []).append((level if level is not None else 1 << 30, code or "", cname))
    out = []
    for gid, rows in members.items():
        rows.sort(key=lambda r: (r[0], r[1]))
        old = ledger_family_label(rows[0][2])
        new = shared_bracket_label([r[2] for r in rows])
        if names[gid] == old and new != old:
            out.append((gid, old, new))
        elif names[gid] != old and skipped is not None:
            skipped.append(names[gid])
    return sorted(out, key=lambda r: r[2].lower())


def print_renames() -> None:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        skipped: list[str] = []
        plan = renames(connection, skipped)
    print("-- CUSTOMER-GROUP renames: %d groups. Idempotent (guarded by the old name)." % len(plan))
    for name in sorted(skipped, key=str.lower):
        print("-- skipped: %s (members changed)" % name.replace("\n", " "))
    print("BEGIN;")
    for gid, old, new in plan:
        o, n, g = _quote(old), _quote(new), _quote(gid)
        print(
            f"UPDATE customer_groups SET name = {n}, updated_at = now() WHERE id = {g}::uuid AND name = {o} "
            "AND NOT EXISTS (SELECT 1 FROM customer_groups x WHERE x.company_id = customer_groups.company_id "
            f"AND lower(x.name) = lower({n}) AND x.id <> customer_groups.id);"
        )
    print("COMMIT;")


def main() -> None:
    sys.path.insert(0, str(ROOT))
    if "--renames" in sys.argv[1:]:
        print_renames()
        return
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
