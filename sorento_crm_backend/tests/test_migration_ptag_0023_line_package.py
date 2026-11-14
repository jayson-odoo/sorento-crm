"""PRICETAG-ALA-CARTE AC-14: migration `ptag_0023_line_package`.

Contract: `documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md` AC-14.
The constraint `uq_ptag_line_request_product` (request_id, product_id) is dropped (IF EXISTS)
with no replacement unique; `uq_ptag_line_request_set` is untouched; the model's
`__table_args__` match. Downgrade re-adds the constraint and fails clearly when a request
holds one product twice.

Written test-FIRST: the revision file does not exist yet, so the file-reading tests fail with
FileNotFoundError and the model / scratch-schema tests fail on the constraint still present.

The up / down / up run happens in a scratch schema holding a minimal
`price_tag_request_lines` with both constraints, reached through a NullPool engine whose
search_path names only that schema, so the migration's unqualified DDL lands there and never
on the shared tables.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.pool import NullPool

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.database import engine

BACKEND = Path(__file__).resolve().parent.parent
REVISION = "ptag_0023_line_package"
REVISION_FILE = BACKEND / "alembic" / "versions" / f"{REVISION}.py"
OLD = "uq_ptag_line_request_product"
SET = "uq_ptag_line_request_set"


def _assigns() -> dict:
    tree = ast.parse(REVISION_FILE.read_text())
    return {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }


def _sections() -> tuple[str, str]:
    source = REVISION_FILE.read_text()
    upgrade, downgrade = source.split("def downgrade", 1)
    return upgrade.split("def upgrade", 1)[1], downgrade


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{REVISION}", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------- the revision file


def test_revision_id_and_one_head_descending_from_it():
    assigns = _assigns()
    assert assigns["revision"] == REVISION
    assert len(REVISION) <= 32

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, f"more than one alembic head: {heads}"
    known = {rev.revision for rev in script.walk_revisions()}
    assert assigns["down_revision"] in known and assigns["down_revision"] != REVISION
    ancestry = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert REVISION in ancestry


def test_upgrade_only_drops_the_product_constraint_if_it_exists():
    upgrade, _ = _sections()
    flat = " ".join(upgrade.split()).upper()
    assert OLD.upper() in flat
    assert "DROP CONSTRAINT IF EXISTS" in flat or "IF_EXISTS=TRUE" in flat.replace(" ", "")
    assert "price_tag_request_lines" in upgrade
    assert SET not in upgrade, "the set constraint is untouched"
    for word in ("CREATE UNIQUE", "CREATE INDEX", "UNIQUE INDEX", "COALESCE", "DROP TABLE", "DROP COLUMN", "DELETE FROM"):
        assert word not in flat, f"upgrade only drops {OLD}: found {word}"


def test_downgrade_re_adds_the_product_constraint():
    _, downgrade = _sections()
    assert OLD in downgrade
    assert "UNIQUE" in downgrade.upper() or "create_unique_constraint" in downgrade
    assert SET not in downgrade


# ------------------------------------------------------------------------- the model


def test_the_model_has_no_unique_over_request_and_product():
    from app.models.price_tag import PriceTagRequestLine

    table = PriceTagRequestLine.__table__
    uniques = {
        c.name: [col.name for col in c.columns]
        for c in table.constraints
        if isinstance(c, sa.UniqueConstraint)
    }
    unique_indexes = {ix.name: [col.name for col in ix.columns] for ix in table.indexes if ix.unique}
    assert OLD not in uniques
    assert uniques.get(SET) == ["request_id", "product_set_id"]
    for name, columns in {**uniques, **unique_indexes}.items():
        assert "product_id" not in columns, f"{name} still makes a product unique per request"


def test_the_scratch_schema_takes_one_product_twice_on_a_request():
    """`blank_session` is built from the model, so this is the model's table as created."""
    from app.models.price_tag import PriceTagRequestLine
    from tests import _ptag_combo_seed as seed
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        host = seed.product(db, "P-ALA-MIG")
        request = seed.submit_one(db, host)
        db.add(
            PriceTagRequestLine(
                request_id=request.id,
                line_type="product",
                product_id=host.id,
                quantity=1,
                sort_order=1,
                price_type="list",
            )
        )
        db.flush()
        count = db.query(PriceTagRequestLine).filter(PriceTagRequestLine.request_id == request.id).count()
        assert count == 2


# ------------------------------------------------------------------------- up / down / up


@contextmanager
def _scratch():
    """(schema, migration engine). A minimal lines table carrying both constraints."""
    schema = f"zzs_mig_ptag23_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            admin.exec_driver_sql(
                f'CREATE TABLE "{schema}".price_tag_request_lines ('
                "id uuid PRIMARY KEY, request_id uuid NOT NULL, product_id uuid, "
                "product_set_id uuid, combo_id uuid, "
                f"CONSTRAINT {OLD} UNIQUE (request_id, product_id), "
                f"CONSTRAINT {SET} UNIQUE (request_id, product_set_id))"
            )
            scoped = sa.create_engine(
                engine.url,
                poolclass=NullPool,
                connect_args={"options": f"-c timezone=utc -c search_path={schema}"},
            )
            try:
                yield schema, scoped
            finally:
                scoped.dispose()
        finally:
            admin.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _run(scoped, fn):
    """upgrade()/downgrade() as alembic/env.py runs it: a transactional MigrationContext."""
    with scoped.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx), ctx.begin_transaction():
            fn()
        conn.commit()


def _constraints(schema) -> set[str]:
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = :s"
                ),
                {"s": schema},
            )
        }


def _insert(schema, request_id, product_id):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".price_tag_request_lines (id, request_id, product_id) '
                "VALUES (:id, :r, :p)"
            ),
            {"id": str(uuid.uuid4()), "r": request_id, "p": product_id},
        )


def test_up_down_up_in_a_scratch_schema():
    module = _load()
    request_id, product_id = str(uuid.uuid4()), str(uuid.uuid4())
    with _scratch() as (schema, scoped):
        _run(scoped, module.upgrade)
        assert OLD not in _constraints(schema)
        assert SET in _constraints(schema)

        _insert(schema, request_id, product_id)
        _insert(schema, request_id, product_id)  # one product twice is now accepted

        # Down refuses, clearly, while a request holds one product twice.
        with pytest.raises(Exception) as exc_info:
            _run(scoped, module.downgrade)
        text = str(exc_info.value).lower()
        assert OLD in text or "twice" in text or "duplicate" in text, text
        assert OLD not in _constraints(schema)

        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'TRUNCATE "{schema}".price_tag_request_lines')
        _insert(schema, request_id, product_id)

        _run(scoped, module.downgrade)
        assert {OLD, SET} <= _constraints(schema)

        _run(scoped, module.upgrade)
        assert OLD not in _constraints(schema)
        assert SET in _constraints(schema)


def test_upgrade_is_a_no_op_when_the_constraint_is_already_gone():
    """IF EXISTS: a database that converged through create_all may never have had it."""
    module = _load()
    with _scratch() as (schema, scoped):
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'ALTER TABLE "{schema}".price_tag_request_lines DROP CONSTRAINT {OLD}')
        _run(scoped, module.upgrade)
        assert OLD not in _constraints(schema)
        assert SET in _constraints(schema)
