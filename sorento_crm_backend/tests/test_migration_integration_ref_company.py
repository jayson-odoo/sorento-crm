"""AC-16 - the migration that adds `integration_references.company_id`,
backfills it, and replaces the global unique with two partial ones.

PLAN: documentation/plans/autocount/PLAN-autocount-brands-ingest.md section 8, D11-D13.
UAC:  documentation/plans/autocount/autocount-brands-ingest-acceptance-criteria.md AC-16.

Driven through `apply()` / `revert()`, exactly like `test_migration_445_grant_
sweep.py` and `test_migration_brands_grant.py` - not `alembic upgrade`.

The module name is the one the coordinator named explicitly:
`alembic/versions/512_integration_ref_company.py`, with module-level
`apply(conn)` / `revert(conn)`. NOTE for the coder: this branch's current
alembic head is `512_hidden_by_default_col` (see `alembic heads`), so `512` as
a revision id PREFIX collides - the coder needs a distinct revision id for the
real file; `alembic-reparent.sh` at PR time re-chains it onto whatever main's
head is by then regardless, so the id picked now is not load-bearing, only
this constant is.

Substrate: a REAL connection (`app.database.engine`), one outer transaction
rolled back at teardown - the migration's own statements are plain
`ALTER TABLE` / `CREATE INDEX` / `UPDATE` against `integration_references`,
`products`, `companies` and `sales_agents`, which only exist for real outside
any scratch schema's `schema_translate_map` (see the note in
`test_migration_brands_grant.py`). Every seeded row carries a `ZZTREFMIG`
marker; nothing here reads or asserts a production row.
"""
from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
from sqlalchemy import text

from app.database import engine

MARKER = "ZZTREFMIG"

_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic",
    "versions",
    "512_integration_ref_company.py",
)


def _load_migration():
    if not os.path.exists(_MIG_PATH):
        pytest.fail(
            f"expected migration module at {_MIG_PATH} (coordinator's named "
            "revision - update _MIG_PATH here if it moves) with module-level "
            "apply(conn)/revert(conn)"
        )
    spec = importlib.util.spec_from_file_location("mig_512_ref_company", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bind():
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _company(bind, code_stem: str) -> str:
    cid = str(uuid.uuid4())
    bind.execute(
        text("INSERT INTO companies (id, name, code, is_active) VALUES (:i, :n, :c, true)"),
        {"i": cid, "n": f"{MARKER} {code_stem}", "c": f"{MARKER[:6]}{code_stem}{uuid.uuid4().hex[:4]}"},
    )
    return cid


def _category_and_uom(bind):
    cat_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
    bind.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, is_active) "
            "VALUES (:i, :c, :n, true)"
        ),
        {"i": cat_id, "c": f"{MARKER}-CAT-{uuid.uuid4().hex[:6]}", "n": f"{MARKER} cat"},
    )
    bind.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, is_active) "
            "VALUES (:i, :c, :n, true)"
        ),
        {"i": uom_id, "c": f"{MARKER}-UOM-{uuid.uuid4().hex[:6]}", "n": f"{MARKER} uom"},
    )
    return cat_id, uom_id


def _product(bind, company_id: str, cat_id: str, uom_id: str) -> str:
    pid = str(uuid.uuid4())
    bind.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
            "list_price, is_active, company_id) VALUES (:i, :c, :n, :cat, :uom, 10, true, :co)"
        ),
        {
            "i": pid,
            "c": f"{MARKER}-PRD-{uuid.uuid4().hex[:6]}",
            "n": f"{MARKER} product",
            "cat": cat_id,
            "uom": uom_id,
            "co": company_id,
        },
    )
    return pid


def _sales_agent(bind) -> str:
    aid = str(uuid.uuid4())
    bind.execute(
        text("INSERT INTO sales_agents (id, sales_agent, is_active) VALUES (:i, :n, true)"),
        {"i": aid, "n": f"{MARKER}-{uuid.uuid4().hex[:6].upper()}"},
    )
    return aid


def _link(bind, entity_type: str, entity_id: str, source_ref: str) -> None:
    bind.execute(
        text(
            "INSERT INTO integration_references "
            "(id, entity_type, entity_id, source_system, source_ref) "
            "VALUES (:i, :t, :e, 'autocount', :r)"
        ),
        {"i": str(uuid.uuid4()), "t": entity_type, "e": entity_id, "r": source_ref},
    )


def _company_id_of(bind, source_ref: str):
    """A `str`, never a `uuid.UUID` - callers compare it with the `str` ids
    every helper in this file seeds with, and psycopg2 hands raw `uuid`
    columns back as `uuid.UUID` objects."""
    value = bind.execute(
        text("SELECT company_id FROM integration_references WHERE source_ref = :r"),
        {"r": source_ref},
    ).scalar()
    return str(value) if value is not None else None


def _ref_exists(bind, source_ref: str) -> bool:
    return (
        bind.execute(
            text("SELECT 1 FROM integration_references WHERE source_ref = :r"),
            {"r": source_ref},
        ).first()
        is not None
    )


class TestBackfillAndCleanup:
    def test_scoped_backfilled_shared_null_orphan_deleted(self, bind):
        company_a = _company(bind, "A")
        cat_id, uom_id = _category_and_uom(bind)
        product = _product(bind, company_a, cat_id, uom_id)

        scoped_ref = f"{MARKER}:PRODUCT:{uuid.uuid4().hex[:8]}"
        _link(bind, "products", product, scoped_ref)

        agent = _sales_agent(bind)
        shared_ref = f"{MARKER}:AGENT:{uuid.uuid4().hex[:8]}"
        _link(bind, "sales_agents", agent, shared_ref)

        orphan_ref = f"{MARKER}:GHOST:{uuid.uuid4().hex[:8]}"
        _link(bind, "products", str(uuid.uuid4()), orphan_ref)

        mig = _load_migration()
        mig.apply(bind)

        assert _company_id_of(bind, scoped_ref) == company_a
        assert _company_id_of(bind, shared_ref) is None
        assert not _ref_exists(bind, orphan_ref), (
            "a scoped reference whose entity no longer exists must be removed, "
            "not left pointing at nothing with a NULL company_id"
        )

    def test_apply_twice_is_a_no_op(self, bind):
        company_a = _company(bind, "B")
        cat_id, uom_id = _category_and_uom(bind)
        product = _product(bind, company_a, cat_id, uom_id)
        scoped_ref = f"{MARKER}:PRODUCT2:{uuid.uuid4().hex[:8]}"
        _link(bind, "products", product, scoped_ref)

        mig = _load_migration()
        mig.apply(bind)
        first = _company_id_of(bind, scoped_ref)

        mig.apply(bind)  # must not raise, must not change the value
        second = _company_id_of(bind, scoped_ref)

        assert first == company_a
        assert second == company_a


# ============================================================ DDL shape (AC-16)
class TestDDLShape:
    """The kill test the reviewer named: neither test above notices if the
    index swap in `apply()` is deleted outright - a backfill can run to
    completion against a table that still carries only the old GLOBAL unique.
    Asserted directly against the real catalogue on `bind`'s own connection
    (plain `public`, no scratch schema in this file - see the module
    docstring), so a stubbed-out DDL statement fails one of these, not just
    silently passes the behavioural tests above.
    """

    def _indexes(self, bind) -> dict[str, str]:
        # schemaname = current_schema(): pg_indexes is catalog-wide, and this
        # SAME index name exists a second time in whatever scratch schema
        # `blank_session` built earlier in the run (the model now declares
        # these partial indexes too, per D12) - unfiltered, that schema's
        # copy answers this query regardless of what `revert()` just did to
        # the REAL table, and never goes away (that scratch schema lives for
        # the whole pytest session).
        rows = bind.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'integration_references' "
                "AND schemaname = current_schema()"
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    def _column_nullable(self, bind, column: str) -> str:
        return bind.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'integration_references' AND column_name = :c "
                "AND table_schema = current_schema()"
            ),
            {"c": column},
        ).scalar()

    def _fk_delete_rule(self, bind, column: str) -> str:
        """`confdeltype` for the FK on ``column`` - 'c' is CASCADE.

        `'integration_references'::regclass` already resolves through THIS
        connection's own `search_path` (`current_schema()` first), so it
        cannot pick up a leaked scratch schema's table the way the two
        unqualified catalog queries above could - but the namespace is
        pinned explicitly anyway, so this helper reads the same regardless
        of how the cast is ever changed.
        """
        return bind.execute(
            text(
                """
                SELECT con.confdeltype
                FROM pg_constraint con
                JOIN pg_attribute att
                  ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
                JOIN pg_class cls ON cls.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = cls.relnamespace
                WHERE cls.relname = 'integration_references'
                  AND ns.nspname = current_schema()
                  AND con.contype = 'f'
                  AND att.attname = :c
                """
            ),
            {"c": column},
        ).scalar()

    def test_apply_swaps_the_global_unique_for_two_partial_ones(self, bind):
        mig = _load_migration()
        # This DATABASE already carries a real, permanent post-migration
        # schema (its own `alembic_version` is at this revision) - so
        # asserting straight after `apply()` would pass even with `apply()`
        # gutted, because the shape it is "creating" already exists for real
        # and outlives this test's rolled-back transaction. `revert()` first
        # (safe: the table is empty, no unique-violation risk) puts THIS
        # transaction back to the pre-migration shape, so `apply()` is the
        # only thing that can produce the shape asserted below.
        mig.revert(bind)
        mig.apply(bind)

        indexes = self._indexes(bind)
        assert "uq_integration_ref_source" not in indexes, (
            "the old GLOBAL unique must be gone, or a company-B row can still "
            "collide with company-A's own claim on the same source_ref"
        )
        assert "uq_integration_ref_source_company" in indexes
        assert "company_id IS NOT NULL" in indexes["uq_integration_ref_source_company"]
        assert "uq_integration_ref_source_shared" in indexes
        assert "company_id IS NULL" in indexes["uq_integration_ref_source_shared"]

    def test_apply_adds_a_nullable_company_id_with_a_cascade_fk(self, bind):
        mig = _load_migration()
        # Same reset as above - this database's `company_id` column and its
        # FK already exist for real, independent of this test's own call.
        mig.revert(bind)
        mig.apply(bind)

        assert self._column_nullable(bind, "company_id") == "YES"
        assert self._fk_delete_rule(bind, "company_id") == "c"

    def test_revert_restores_the_global_unique(self, bind):
        mig = _load_migration()
        mig.revert(bind)  # start from the pre-migration shape, for the same reason
        mig.apply(bind)
        mig.revert(bind)

        indexes = self._indexes(bind)
        assert "uq_integration_ref_source" in indexes
        assert "uq_integration_ref_source_company" not in indexes
        assert "uq_integration_ref_source_shared" not in indexes
