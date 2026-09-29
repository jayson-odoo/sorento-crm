"""Migration `bcd_0001_brand_chatbot_default` (owner brief W5 on PR #833).

Adds `brands.is_chatbot_default` and seeds every brand named Sorento as the default,
unless its company already has one. The body is plain idempotent SQL (`ADD COLUMN IF NOT
EXISTS`, a guarded UPDATE), so it also runs as-is on the shared local database, which
converges through `create_all` and already has the column (backend CLAUDE.md), without an
`alembic upgrade`.

`pg_session` for the same reason as `test_migration_bftp_0001_flows_to_purchasing.py`.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from tests._pg_fixture import pg_session, unique_code

# ALTER TABLE brands and an unbounded UPDATE on the shared schema: out of the xdist pool
# (tests/conftest.py `serial_ddl`; PR #833 round 5 S3).
pytestmark = pytest.mark.serial_ddl

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "bcd_0001_brand_chatbot_default.py"
)
_COLUMN = "is_chatbot_default"


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_bcd_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(_module(), direction)()


def _columns(db) -> set[str]:
    return {c["name"] for c in sa.inspect(db.connection()).get_columns("brands")}


def _brand(db, name: str, *, company_id: str | None = None) -> str:
    brand_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO brands (id, brand_code, brand_name, is_active, company_id) "
            "VALUES (:id, :code, :name, true, :company)"
        ),
        {"id": brand_id, "code": unique_code("BCD"), "name": name, "company": company_id},
    )
    db.flush()
    return brand_id


def _flag(db, brand_id: str):
    return db.execute(text(f"SELECT {_COLUMN} FROM brands WHERE id = :id"), {"id": brand_id}).scalar()


def _company(db) -> str:
    return db.execute(text("SELECT id FROM companies ORDER BY created_at LIMIT 1")).scalar()


@pytest.fixture
def db():
    with pg_session() as session:
        session.execute(text("UPDATE brands SET brand_name = brand_name || ' zzt-old' WHERE lower(brand_name) = 'sorento'"))
        yield session


def test_revision_id_fits_and_the_graph_has_one_head_that_descends_from_it():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _module()
    assert len(module.revision) <= 32
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    # Lesson 95: one head, and this migration is an ANCESTOR of it (bcw_0001 now follows).
    assert len(heads) == 1
    assert module.revision in {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}


def test_upgrade_from_scratch_adds_the_column_and_seeds_sorento(db):
    db.execute(text(f"ALTER TABLE brands DROP COLUMN IF EXISTS {_COLUMN}"))
    company = _company(db)
    sorento = _brand(db, "SORENTO", company_id=company)
    mocha = _brand(db, "Mocha", company_id=company)

    _run(db)

    col = next(c for c in sa.inspect(db.connection()).get_columns("brands") if c["name"] == _COLUMN)
    assert col["nullable"] is False
    assert _flag(db, sorento) is True
    assert _flag(db, mocha) is False


def test_the_body_runs_again_on_a_database_that_already_has_the_column(db):
    """The shared local DB: `create_all` added the column, no alembic upgrade ran."""
    db.execute(text(f"ALTER TABLE brands ADD COLUMN IF NOT EXISTS {_COLUMN} BOOLEAN NOT NULL DEFAULT false"))
    company = _company(db)
    sorento = _brand(db, "Sorento", company_id=company)
    second = _brand(db, "SORENTO ", company_id=company)  # a second spelling of the same name

    _run(db)
    _run(db)

    # One of the two is the default, never both (they tie on created_at here).
    assert {_flag(db, sorento), _flag(db, second)} == {True, False}
    assert db.execute(
        text(f"SELECT count(*) FROM brands WHERE {_COLUMN} AND company_id = :c"), {"c": company}
    ).scalar() == 1


def test_a_company_that_already_chose_a_default_is_left_alone(db):
    db.execute(text(f"ALTER TABLE brands ADD COLUMN IF NOT EXISTS {_COLUMN} BOOLEAN NOT NULL DEFAULT false"))
    company = _company(db)
    db.execute(text(f"UPDATE brands SET {_COLUMN} = false WHERE company_id = :c"), {"c": company})
    mocha = _brand(db, "Mocha", company_id=company)
    db.execute(text(f"UPDATE brands SET {_COLUMN} = true WHERE id = :id"), {"id": mocha})
    sorento = _brand(db, "Sorento", company_id=company)

    _run(db)

    assert _flag(db, mocha) is True
    assert _flag(db, sorento) is False


def test_downgrade_drops_the_column(db):
    _run(db)
    _run(db, "downgrade")
    assert _COLUMN not in _columns(db)
    _run(db)
    assert _COLUMN in _columns(db)
