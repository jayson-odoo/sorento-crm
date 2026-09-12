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
