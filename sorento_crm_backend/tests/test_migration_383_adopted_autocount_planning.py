"""Migration `383_adopted_autocount_planning` - what adoption needs from the schema.

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md`
section 4. Three things, and no new table:

1. `projects.sales_orders.project_id` becomes NULLABLE. An adopted order has no project
   registration and must not invent one (AC-FP07).
2. A partial unique index `uq_projects_so_core_order` on `(so_id) WHERE so_id IS NOT NULL`,
   so one core sales order can be planned exactly once (AC-FP10, AC-FP24 invariant 4).
3. The `adopted` status VALUE, which is a model constant and not DDL: the column is
   `String(24)` with no database enum.

The DDL half cannot be driven test-first in the usual sense - a schema change has no
behaviour to assert before the file exists - so the teeth here are the round trip: this
file runs `upgrade()`, then `downgrade()`, then `upgrade()` again, asserting the schema
after each. Delete either half of the migration body and the corresponding assertion
fails. The RED state before the file existed was `_load_migration()` raising
`FileNotFoundError`.

Runs against the REAL database (`pg_session`) rather than the scratch schema, and this is
deliberate: the migration's guards inspect `projects.*` by name, which a
`schema_translate_map` connection does not rewrite, so a scratch run would inspect one
schema and write to another. Postgres DDL is transactional, so the outer rollback in
`pg_session` discards every statement below. Nothing here reads or asserts a live row.
"""
from __future__ import annotations

import importlib.util
import pathlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests._pg_fixture import pg_session

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "383_adopted_autocount_planning.py"
)

INDEX = "uq_projects_so_core_order"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_383", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _project_id_is_nullable(db) -> bool:
    inspector = sa.inspect(db.connection())
    for column in inspector.get_columns("sales_orders", schema="projects"):
        if column["name"] == "project_id":
            return bool(column["nullable"])
    raise AssertionError("projects.sales_orders has no project_id column")


def _core_order_index(db):
    inspector = sa.inspect(db.connection())
    for index in inspector.get_indexes("sales_orders", schema="projects"):
        if index["name"] == INDEX:
            return index
    return None


def test_upgrade_makes_project_id_nullable_and_downgrade_puts_it_back():
    """DOWN first, deliberately.

    The database this runs against may already be at head, and a test that only ever
    upgrades would then assert a state the migration body did not have to produce - it
    would pass with the body deleted. Starting from the downgraded state makes each half
    of the body load-bearing: comment out `alter_column` and this fails.
    """
    with pg_session() as db:
        _run(db, "downgrade")
        assert _project_id_is_nullable(db) is False

        _run(db, "upgrade")
        assert _project_id_is_nullable(db) is True


def test_upgrade_adds_the_partial_unique_index_on_so_id_and_downgrade_drops_it():
    with pg_session() as db:
        _run(db, "downgrade")
        assert _core_order_index(db) is None

        _run(db, "upgrade")
        index = _core_order_index(db)
        assert index is not None, f"{INDEX} was not created"
        assert index["unique"] is True
        assert index["column_names"] == ["so_id"]
        # PARTIAL, or every unadopted order would collide on NULL under some engines
        # and the index would be a different promise from the one AC-FP10 makes.
        assert "so_id IS NOT NULL" in (index.get("dialect_options") or {}).get(
            "postgresql_where", ""
        )

        _run(db, "downgrade")
        assert _core_order_index(db) is None


def test_the_index_refuses_a_second_planning_record_for_one_core_sales_order():
    """The teeth of AC-FP10: the database, not the service, is what makes it impossible."""
    with pg_session() as db:
        _run(db, "downgrade")
        _run(db, "upgrade")
        company_id = db.execute(
            sa.text("select id from companies where code = 'SRT'")
        ).scalar()
        core_id = db.execute(
            sa.text(
                "insert into sales_orders (id, so_number, status, company_id) "
                "values (gen_random_uuid(), :n, 'open', :c) returning id"
            ),
            {"n": "ZZT-383-SO", "c": company_id},
        ).scalar()

        insert = sa.text(
            "insert into projects.sales_orders "
            "(id, project_id, so_id, provisional_ref, status, company_id) "
            "values (gen_random_uuid(), null, :so, :ref, 'adopted', :c)"
        )
        db.execute(insert, {"so": core_id, "ref": "ZZT-383-A", "c": company_id})
        try:
            db.execute(insert, {"so": core_id, "ref": "ZZT-383-B", "c": company_id})
            raise AssertionError("the second planning record was allowed")
        except sa.exc.IntegrityError as exc:
            assert INDEX in str(exc)
